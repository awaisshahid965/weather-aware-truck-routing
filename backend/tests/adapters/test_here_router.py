import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import flexpolyline  # type: ignore[import-untyped]  # the package ships no type hints
import httpx
import pytest

from routing.adapters.here_router import METERS_PER_MILE, HereRouter
from routing.domain.geometry import haversine_miles
from routing.domain.models import GeoPoint, RouteCandidate
from routing.ports.errors import ProviderError
from routing.ports.route_provider import RouteProvider

FIXTURES = Path(__file__).parent / 'fixtures' / 'here'
API_KEY = 'test-key'
PITTSBURGH = GeoPoint(40.4406, -79.9959)
CLEVELAND = GeoPoint(41.4993, -81.6944)
DEPARTURE_AT = datetime(2026, 11, 17, 13, 0, tzinfo=UTC)

Document = dict[str, object]


class FakeHere:
    """Answers every request with one recorded reply and keeps the requests."""

    def __init__(self, body: object, status: int = 200) -> None:
        self._body = body
        self._status = status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self._status, json=self._body)


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def _find_routes(here: FakeHere, departure_at: datetime = DEPARTURE_AT) -> list[RouteCandidate]:
    with httpx.Client(transport=httpx.MockTransport(here)) as client:
        router: RouteProvider = HereRouter(client, API_KEY, deadline_seconds=15)
        return router.find_routes(PITTSBURGH, CLEVELAND, departure_at)


def _section(
    points: list[tuple[float, float]], *, length_meters: object = 1609.344, duration_seconds: object = 60
) -> Document:
    return {'polyline': flexpolyline.encode(points), 'summary': {'length': length_meters, 'duration': duration_seconds}}


def _document(*routes: list[Document]) -> Document:
    return {'routes': [{'sections': sections} for sections in routes]}


def _straight(start_latitude: float) -> list[Document]:
    """A one-section route going north from `start_latitude`. Different starts give distinct routes."""
    return [_section([(start_latitude, -80.0), (start_latitude + 0.1, -80.0)])]


def test_three_routes_become_three_candidates_in_provider_order() -> None:
    document = _fixture('routes_three.json')
    assert isinstance(document, dict)
    recorded = [route['sections'] for route in document['routes']]

    candidates = _find_routes(FakeHere(document))

    assert [candidate.provider_index for candidate in candidates] == [0, 1, 2]
    for candidate, sections in zip(candidates, recorded, strict=True):
        assert [
            (len(section.points), section.length_miles, section.duration_seconds) for section in candidate.sections
        ] == [
            (
                len(flexpolyline.decode(section['polyline'])),
                section['summary']['length'] / METERS_PER_MILE,
                section['summary']['duration'],
            )
            for section in sections
        ]


def test_each_route_starts_at_the_origin_and_ends_at_the_destination() -> None:
    candidates = _find_routes(FakeHere(_fixture('routes_three.json')))

    for candidate in candidates:
        assert haversine_miles(candidate.sections[0].points[0], PITTSBURGH) < 1
        assert haversine_miles(candidate.sections[-1].points[-1], CLEVELAND) < 1


def test_1609_344_meters_is_1_mile() -> None:
    document = _document([_section([(40.0, -80.0), (40.01, -80.0)], length_meters=1609.344)])

    [candidate] = _find_routes(FakeHere(document))

    assert candidate.distance_miles == 1.0


def test_each_section_is_decoded_on_its_own() -> None:
    first = [(40.0, -80.0), (40.1, -80.0)]
    second = [(40.1, -80.0), (40.2, -80.0), (40.2, -80.1)]
    document = _document([_section(first, length_meters=1000), _section(second, length_meters=2000)])

    [candidate] = _find_routes(FakeHere(document))

    assert [section.points for section in candidate.sections] == [
        tuple(GeoPoint(latitude, longitude) for latitude, longitude in first),
        tuple(GeoPoint(latitude, longitude) for latitude, longitude in second),
    ]
    assert [section.length_miles for section in candidate.sections] == [
        1000 / METERS_PER_MILE,
        2000 / METERS_PER_MILE,
    ]


def test_a_third_dimension_is_dropped() -> None:
    polyline = flexpolyline.encode([(40.0, -80.0, 300), (40.1, -80.0, 310)], third_dim=flexpolyline.ALTITUDE)
    document = _document([{'polyline': polyline, 'summary': {'length': 11000, 'duration': 600}}])

    [candidate] = _find_routes(FakeHere(document))

    assert candidate.sections[0].points == (GeoPoint(40.0, -80.0), GeoPoint(40.1, -80.0))


def test_one_route_stays_one_candidate() -> None:
    candidates = _find_routes(FakeHere(_fixture('routes_one.json')))

    assert [candidate.provider_index for candidate in candidates] == [0]


def test_an_exact_duplicate_is_dropped() -> None:
    candidates = _find_routes(FakeHere(_fixture('routes_duplicate.json')))

    assert [candidate.provider_index for candidate in candidates] == [0]


def test_routes_after_a_dropped_duplicate_are_renumbered_in_order() -> None:
    document = _document(_straight(40.0), _straight(41.0), _straight(40.0), _straight(42.0))

    candidates = _find_routes(FakeHere(document))

    assert [candidate.provider_index for candidate in candidates] == [0, 1, 2]
    assert [candidate.sections[0].points[0].latitude for candidate in candidates] == [40.0, 41.0, 42.0]


def test_routes_beyond_the_third_are_ignored() -> None:
    document = _document(_straight(40.0), _straight(41.0), _straight(42.0), _straight(43.0))

    candidates = _find_routes(FakeHere(document))

    assert [candidate.sections[0].points[0].latitude for candidate in candidates] == [40.0, 41.0, 42.0]


def test_no_route_is_an_empty_list_and_the_notice_codes_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    candidates = _find_routes(FakeHere(_fixture('routes_empty.json')))

    assert candidates == []
    [record] = [record for record in caplog.records if record.getMessage() == 'here found no route']
    assert vars(record)['notice_codes'] == ['couldNotMatchOrigin']


def test_a_section_without_a_polyline_is_a_provider_error() -> None:
    with pytest.raises(ProviderError, match=r'routes\[1\]\.sections\[0\]\.polyline must be a string'):
        _find_routes(FakeHere(_fixture('routes_bad_section.json')))


def test_a_rejected_request_is_a_provider_error_without_a_retry() -> None:
    here = FakeHere(_fixture('error_400.json'), status=400)

    with pytest.raises(ProviderError, match='answered 400') as caught:
        _find_routes(here)

    assert len(here.requests) == 1
    assert API_KEY not in str(caught.value)


def test_the_request_asks_here_for_a_truck_route_and_two_alternatives() -> None:
    here = FakeHere(_fixture('routes_three.json'))

    _find_routes(here)

    [request] = here.requests
    assert request.url.host == 'router.hereapi.com'
    assert request.url.path == '/v8/routes'
    assert dict(request.url.params) == {
        'transportMode': 'truck',
        'routingMode': 'fast',
        'origin': '40.4406,-79.9959',
        'destination': '41.4993,-81.6944',
        'departureTime': '2026-11-17T13:00:00Z',
        'alternatives': '2',
        'return': 'polyline,summary,routeLabels',
        'apiKey': API_KEY,
    }


def test_the_departure_time_is_sent_in_utc_with_z() -> None:
    here = FakeHere(_fixture('routes_three.json'))
    eight_am_in_pittsburgh = datetime(2026, 11, 17, 8, 0, tzinfo=ZoneInfo('America/New_York'))

    _find_routes(here, departure_at=eight_am_in_pittsburgh)

    assert here.requests[0].url.params['departureTime'] == '2026-11-17T13:00:00Z'


def test_a_naive_departure_time_is_rejected_before_any_request() -> None:
    here = FakeHere(_fixture('routes_three.json'))

    with pytest.raises(ValueError, match='timezone-aware'):
        _find_routes(here, departure_at=datetime(2026, 11, 17, 13, 0))  # noqa: DTZ001 - naive on purpose

    assert here.requests == []


@pytest.mark.parametrize(
    ('document', 'reason'),
    [
        pytest.param([], 'response must be an object', id='not an object'),
        pytest.param({'notices': []}, 'routes must be a list', id='no routes key'),
        pytest.param(_document([]), r'routes\[0\] has no sections', id='a route without sections'),
        pytest.param(_document([_section([(40.0, -80.0)])]), 'at least 2 points', id='one point'),
        pytest.param(
            _document([{'polyline': 'not a polyline', 'summary': {'length': 1, 'duration': 1}}]),
            'not a valid flexible polyline',
            id='garbled polyline',
        ),
        pytest.param(
            _document([{'polyline': '', 'summary': {'length': 1, 'duration': 1}}]),
            'not a valid flexible polyline',
            id='empty polyline',
        ),
        pytest.param(
            _document([_section([(95.0, -80.0), (96.0, -80.0)])]),
            'latitude must be within',
            id='a point off the globe',
        ),
        pytest.param(
            _document([_section([(40.0, -80.0), (40.1, -80.0)], length_meters=0)]),
            'length_miles must be finite and > 0',
            id='zero length',
        ),
        pytest.param(
            _document([_section([(40.0, -80.0), (40.1, -80.0)], duration_seconds=0)]),
            r'routes\[0\] has a total duration of 0 s',
            id='zero duration',
        ),
        pytest.param(
            _document([_section([(40.0, -80.0), (40.1, -80.0)], duration_seconds=-5)]),
            'duration_seconds must be finite and >= 0',
            id='negative duration',
        ),
        pytest.param(
            _document([_section([(40.0, -80.0), (40.1, -80.0)], length_meters='1000')]),
            r'summary\.length must be a number; got str',
            id='length as text',
        ),
        pytest.param(
            _document([_section([(40.0, -80.0), (40.1, -80.0)], length_meters=True)]),
            r'summary\.length must be a number; got bool',
            id='length as a boolean',
        ),
        pytest.param(
            _document([_section([(40.0, -80.0), (40.1, -80.0)], length_meters=10**400)]),
            r'summary\.length must be finite',
            id='length too large for a float',
        ),
    ],
)
def test_a_route_we_cannot_use_is_a_provider_error(document: object, reason: str) -> None:
    with pytest.raises(ProviderError, match=reason):
        _find_routes(FakeHere(document))
