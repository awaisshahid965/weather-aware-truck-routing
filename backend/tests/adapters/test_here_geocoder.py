import json
import logging
from pathlib import Path

import httpx
import pytest

from routing.adapters.here_geocoder import HereGeocoder
from routing.domain.models import GeoPoint, PlaceMatch
from routing.ports.errors import ProviderError, ProviderTimeoutError
from routing.ports.geocoder import Geocoder

FIXTURES = Path(__file__).parent / 'fixtures' / 'here'
API_KEY = 'test-key'

Document = dict[str, object]


class FakeHere:
    """Answers every request with one reply and keeps the requests."""

    def __init__(self, body: object, status: int = 200, headers: dict[str, str] | None = None) -> None:
        self._body = body
        self._status = status
        self._headers = headers
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self._status, json=self._body, headers=self._headers)


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def _search(
    here: FakeHere | httpx.MockTransport, query: str = 'Springfield', limit: int = 5, deadline_seconds: float = 5
) -> list[PlaceMatch]:
    transport = here if isinstance(here, httpx.MockTransport) else httpx.MockTransport(here)
    with httpx.Client(transport=transport) as client:
        geocoder: Geocoder = HereGeocoder(client, API_KEY, deadline_seconds=deadline_seconds)
        return geocoder.search(query, limit)


def _item(**fields: object) -> Document:
    """A usable item, with `fields` replacing its keys. A value of `...` removes the key."""
    item: Document = {'id': 'here:place:1', 'title': 'Pittsburgh, PA', 'position': {'lat': 40.4, 'lng': -80.0}}
    for name, value in fields.items():
        if value is ...:
            del item[name]
        else:
            item[name] = value
    return item


def test_the_recorded_answer_maps_to_5_matches_in_provider_order() -> None:
    document = _fixture('geocode_springfield.json')
    assert isinstance(document, dict)

    matches = _search(FakeHere(document))

    assert matches == [
        PlaceMatch(item['id'], item['title'], GeoPoint(item['position']['lat'], item['position']['lng']))
        for item in document['items']
    ]
    assert [match.label for match in matches] == [
        'Springfield, IL, United States',
        'Springfield, MO, United States',
        'Springfield, VA, United States',
        'Springfield, MA, United States',
        'Springfield, MB, Canada',
    ]


def test_one_recorded_match_is_one_place() -> None:
    matches = _search(FakeHere(_fixture('geocode_pittsburgh.json')), query='Pittsburgh')

    assert matches == [
        PlaceMatch('here:cm:namedplace:21010974', 'Pittsburgh, PA, United States', GeoPoint(40.43851, -79.99734))
    ]


def test_an_item_without_a_position_is_dropped_and_the_rest_keep_their_order(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    matches = _search(FakeHere(_fixture('geocode_springfield_no_position.json')))

    assert [match.label for match in matches] == [
        'Springfield, IL, United States',
        'Springfield, VA, United States',
        'Springfield, MA, United States',
        'Springfield, MB, Canada',
    ]
    [record] = [record for record in caplog.records if record.getMessage() == 'here place dropped']
    assert vars(record)['provider_position'] == 1
    assert vars(record)['reason'] == 'items[1].position must be an object; got NoneType'


def test_no_match_is_an_empty_list() -> None:
    assert _search(FakeHere(_fixture('geocode_empty.json')), query='Qxzvqxzv Zzqv') == []


@pytest.mark.parametrize(
    ('item', 'reason'),
    [
        pytest.param('Pittsburgh', 'items[0] must be an object; got str', id='not an object'),
        pytest.param(_item(position=None), 'position must be an object; got NoneType', id='null position'),
        pytest.param(_item(position={'lat': 40.4}), 'position.lng must be a number; got NoneType', id='no longitude'),
        pytest.param(
            _item(position={'lat': '40.4', 'lng': -80.0}), 'position.lat must be a number; got str', id='text latitude'
        ),
        pytest.param(
            _item(position={'lat': True, 'lng': -80.0}), 'position.lat must be a number; got bool', id='bool latitude'
        ),
        pytest.param(
            _item(position={'lat': 40.4, 'lng': 10**400}), 'position.lng must be finite', id='huge integer longitude'
        ),
        pytest.param(_item(position={'lat': 95.0, 'lng': -80.0}), 'latitude must be within', id='off the globe'),
        pytest.param(_item(id=...), 'id must be a string; got NoneType', id='no id'),
        pytest.param(_item(id='  '), 'place_id must not be blank', id='blank id'),
        pytest.param(_item(title=...), 'title must be a string; got NoneType', id='no title'),
        pytest.param(_item(title=''), 'label must not be blank', id='empty title'),
    ],
)
def test_an_item_we_cannot_use_is_dropped(item: object, reason: str, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    usable = _item(id='here:place:2', title='Cleveland, OH')

    matches = _search(FakeHere({'items': [item, usable]}))

    assert [match.place_id for match in matches] == ['here:place:2']
    [record] = [record for record in caplog.records if record.getMessage() == 'here place dropped']
    assert reason in vars(record)['reason']


def test_an_infinite_coordinate_is_dropped() -> None:
    # JSON has no Infinity, but a number too large for a float reads as one.
    body = b'{"items": [{"id": "here:place:1", "title": "Pittsburgh, PA", "position": {"lat": 1e999, "lng": -80.0}}]}'

    matches = _search(httpx.MockTransport(lambda request: httpx.Response(200, content=body)))

    assert matches == []


def test_no_more_than_the_limit_comes_back() -> None:
    matches = _search(FakeHere(_fixture('geocode_springfield.json')), limit=2)

    assert [match.label for match in matches] == ['Springfield, IL, United States', 'Springfield, MO, United States']


@pytest.mark.parametrize(
    ('document', 'reason'),
    [
        pytest.param([], 'response must be an object', id='not an object'),
        pytest.param({}, 'items must be a list; got NoneType', id='no items key'),
        pytest.param({'items': {'id': 'here:place:1'}}, 'items must be a list; got dict', id='items not a list'),
    ],
)
def test_a_document_we_cannot_use_is_a_provider_error(document: object, reason: str) -> None:
    with pytest.raises(ProviderError, match=reason):
        _search(FakeHere(document))


def test_the_request_asks_here_for_5_places_matching_the_query() -> None:
    here = FakeHere(_fixture('geocode_pittsburgh.json'))

    _search(here, query='Pittsburgh, PA')

    [request] = here.requests
    assert request.url.host == 'geocode.search.hereapi.com'
    assert request.url.path == '/v1/geocode'
    assert dict(request.url.params) == {'q': 'Pittsburgh, PA', 'limit': '5', 'apiKey': API_KEY}


def test_a_rejected_request_is_a_provider_error_without_a_retry() -> None:
    here = FakeHere({'error': 'Unauthorized', 'error_description': f'apiKey {API_KEY} invalid'}, status=401)

    with pytest.raises(ProviderError, match='answered 401') as caught:
        _search(here)

    assert len(here.requests) == 1
    assert API_KEY not in str(caught.value)


def test_a_5xx_is_retried_twice_and_then_is_a_provider_error() -> None:
    # Retry-After: 0 keeps the test from waiting out the real backoff.
    here = FakeHere({'title': 'Service Unavailable'}, status=503, headers={'Retry-After': '0'})

    with pytest.raises(ProviderError, match='answered 503') as caught:
        _search(here)

    assert type(caught.value) is ProviderError
    assert len(here.requests) == 3


def test_a_timeout_is_a_provider_timeout_error() -> None:
    requests: list[httpx.Request] = []

    def times_out(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ReadTimeout('timed out', request=request)

    # The shortest backoff (0.25 s) ends past this deadline, so no retry is tried and nothing waits.
    with pytest.raises(ProviderTimeoutError, match='timed out') as caught:
        _search(httpx.MockTransport(times_out), deadline_seconds=0.2)

    assert len(requests) == 1
    assert API_KEY not in str(caught.value)
