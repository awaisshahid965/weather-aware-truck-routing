import json
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import Client
from pytest_django import Settings

from config.json_logging import JsonFormatter
from routing import bootstrap
from routing.domain.models import GeoPoint, PlaceMatch
from routing.http.errors import INTERNAL_ERROR_MESSAGE
from routing.ports.errors import ProviderError, ProviderTimeoutError
from routing.services.search_places import SearchPlacesService
from tests.services.fakes import FakeGeocoder

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse as TestResponse

URL = '/api/v1/places'
HERE_FIXTURES = Path(__file__).parent.parent / 'adapters' / 'fixtures' / 'here'
PLACE_KEYS = {'id', 'label', 'latitude', 'longitude'}

PITTSBURGH = PlaceMatch('here:cm:namedplace:21010974', 'Pittsburgh, PA, United States', GeoPoint(40.43851, -79.99734))
CLEVELAND = PlaceMatch('here:cm:namedplace:21027692', 'Cleveland, OH, United States', GeoPoint(41.50473, -81.69074))


def _get(client: Client, **params: str) -> TestResponse:
    return client.get(URL, params, secure=True)


def _use(monkeypatch: pytest.MonkeyPatch, geocoder: FakeGeocoder) -> None:
    """The real service over a fake geocoder, in place of the composition root's."""
    service = SearchPlacesService(geocoder)
    monkeypatch.setattr(bootstrap, 'get_search_places_service', lambda: service)


def _assert_error_shape(response: TestResponse, status: int, code: str) -> dict[str, Any]:
    body: dict[str, Any] = response.json()
    assert response.status_code == status
    assert set(body) == {'error', 'requestId'}
    assert set(body['error']) == {'code', 'message', 'details'}
    assert body['error']['code'] == code
    assert body['requestId'] == response['X-Request-ID']
    return body


# Success


def test_matches_have_exactly_the_contract_fields_in_provider_order(
    monkeypatch: pytest.MonkeyPatch, client: Client
) -> None:
    _use(monkeypatch, FakeGeocoder([PITTSBURGH, CLEVELAND]))

    response = _get(client, q='Pittsburgh')

    assert response.status_code == 200
    assert response.json() == [
        {
            'id': 'here:cm:namedplace:21010974',
            'label': 'Pittsburgh, PA, United States',
            'latitude': 40.43851,
            'longitude': -79.99734,
        },
        {
            'id': 'here:cm:namedplace:21027692',
            'label': 'Cleveland, OH, United States',
            'latitude': 41.50473,
            'longitude': -81.69074,
        },
    ]


def test_coordinates_are_rounded_to_5_decimals(monkeypatch: pytest.MonkeyPatch, client: Client) -> None:
    _use(monkeypatch, FakeGeocoder([PlaceMatch('here:place:1', 'Pittsburgh', GeoPoint(40.4385149, -79.9973449))]))

    [place] = _get(client, q='Pittsburgh').json()

    assert (place['latitude'], place['longitude']) == (40.43851, -79.99734)


def test_no_match_is_an_empty_list(monkeypatch: pytest.MonkeyPatch, client: Client) -> None:
    _use(monkeypatch, FakeGeocoder([]))

    response = _get(client, q='Qxzvqxzv Zzqv')

    assert response.status_code == 200
    assert response.json() == []


def test_a_padded_query_is_searched_trimmed(monkeypatch: pytest.MonkeyPatch, client: Client) -> None:
    geocoder = FakeGeocoder([PITTSBURGH])
    _use(monkeypatch, geocoder)

    response = _get(client, q='   abc  ')

    assert response.status_code == 200
    assert geocoder.calls == [('abc', 5)]


# Invalid input


@pytest.mark.parametrize(
    ('params', 'message'),
    [
        pytest.param({'q': 'ab'}, 'Must have at least 3 characters other than spaces.', id='2 characters'),
        pytest.param({'q': '  a b  '}, 'Must have at least 3 characters other than spaces.', id='2 after trimming'),
        pytest.param({'q': 'a' * 201}, 'Must be at most 200 characters.', id='201 characters'),
        pytest.param({}, 'This field is required.', id='no q'),
        pytest.param({'q': 'Pitts\x00burgh'}, 'Null characters are not allowed.', id='null character'),
    ],
)
def test_an_invalid_query_is_a_400_that_names_q_before_any_search(
    monkeypatch: pytest.MonkeyPatch, client: Client, params: dict[str, str], message: str
) -> None:
    geocoder = FakeGeocoder([PITTSBURGH])
    _use(monkeypatch, geocoder)

    response = _get(client, **params)

    body = _assert_error_shape(response, 400, 'VALIDATION_ERROR')
    assert body['error']['details'] == {'q': [message]}
    assert geocoder.calls == []


def test_a_post_is_a_405_in_the_contract_shape(client: Client) -> None:
    response = client.post(URL, data='{}', content_type='application/json', secure=True)

    _assert_error_shape(response, 405, 'METHOD_NOT_ALLOWED')


# Provider failures


@pytest.mark.parametrize(
    ('error', 'status', 'code', 'message'),
    [
        pytest.param(
            ProviderTimeoutError('GET /v1/geocode did not finish within 5 s'),
            504,
            'PROVIDER_TIMEOUT',
            'The geocoding provider did not answer in time.',
            id='timeout',
        ),
        pytest.param(
            ProviderError('GET /v1/geocode answered 503'),
            502,
            'PROVIDER_ERROR',
            'The geocoding provider failed.',
            id='failure',
        ),
    ],
)
def test_a_provider_failure_has_its_status_and_code(
    monkeypatch: pytest.MonkeyPatch, client: Client, error: Exception, status: int, code: str, message: str
) -> None:
    _use(monkeypatch, FakeGeocoder(error=error))

    response = _get(client, q='Pittsburgh')

    body = _assert_error_shape(response, status, code)
    assert body['error']['message'] == message
    assert body['error']['details'] == {}


@pytest.mark.parametrize(
    ('geocoder', 'query', 'status'),
    [
        pytest.param(FakeGeocoder([PITTSBURGH]), 'Pittsburgh, PA', 200, id='found'),
        pytest.param(FakeGeocoder(), 'Pittsburgh, PA ' * 14, 400, id='too long'),
        pytest.param(
            FakeGeocoder(error=ProviderError('GET /v1/geocode answered 503')), 'Pittsburgh, PA', 502, id='502'
        ),
        pytest.param(
            FakeGeocoder(error=ProviderTimeoutError('GET /v1/geocode timed out')), 'Pittsburgh, PA', 504, id='504'
        ),
    ],
)
def test_no_log_line_holds_what_the_driver_typed(
    monkeypatch: pytest.MonkeyPatch,
    client: Client,
    caplog: pytest.LogCaptureFixture,
    geocoder: FakeGeocoder,
    query: str,
    status: int,
) -> None:
    _use(monkeypatch, geocoder)
    caplog.set_level(logging.DEBUG)

    response = _get(client, q=query)

    assert response.status_code == status
    formatter = JsonFormatter()
    assert caplog.records
    for record in caplog.records:
        assert 'Pittsburgh' not in formatter.format(record)


# The composition root, with the real adapter on a fake network

SENTINEL_KEY = 'sentinel-here-key-3c9a'
RAW_HERE_FIELDS = ('title', 'position', 'address', 'resultType', 'mapView', 'scoring')


@pytest.fixture
def fresh_bootstrap() -> Iterator[None]:
    bootstrap.get_search_places_service.cache_clear()
    yield
    bootstrap.get_search_places_service.cache_clear()


def _here_network(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, answer: Callable[[httpx.Request], httpx.Response]
) -> list[httpx.Request]:
    """Sends the composition root's HTTP client to `answer`, with the sentinel key. Returns the requests."""
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return answer(request)

    settings.HERE_API_KEY = SENTINEL_KEY
    monkeypatch.setattr(bootstrap, '_http_client', lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    return sent


def _recorded(name: str) -> Callable[[httpx.Request], httpx.Response]:
    body = json.loads((HERE_FIXTURES / name).read_text(encoding='utf-8'))
    return lambda request: httpx.Response(200, json=body)


@pytest.mark.usefixtures('fresh_bootstrap')
def test_a_recorded_here_answer_leaves_with_only_the_contract_fields(
    monkeypatch: pytest.MonkeyPatch, client: Client, settings: Settings
) -> None:
    _here_network(monkeypatch, settings, _recorded('geocode_springfield.json'))

    response = _get(client, q='Springfield')

    assert response.status_code == 200
    places = response.json()
    assert len(places) == 5
    assert all(set(place) == PLACE_KEYS for place in places)
    assert places[0] == {
        'id': 'here:cm:namedplace:21004800',
        'label': 'Springfield, IL, United States',
        'latitude': 39.8013,
        'longitude': -89.6436,
    }
    text = response.content.decode()
    for field in RAW_HERE_FIELDS:
        assert f'"{field}"' not in text


@pytest.mark.usefixtures('fresh_bootstrap')
def test_a_here_item_without_a_position_never_reaches_the_client(
    monkeypatch: pytest.MonkeyPatch, client: Client, settings: Settings
) -> None:
    _here_network(monkeypatch, settings, _recorded('geocode_springfield_no_position.json'))

    places = _get(client, q='Springfield').json()

    assert 'Springfield, MO, United States' not in [place['label'] for place in places]
    assert len(places) == 4


@pytest.mark.usefixtures('fresh_bootstrap')
def test_a_here_5xx_after_two_retries_is_a_502(
    monkeypatch: pytest.MonkeyPatch, client: Client, settings: Settings
) -> None:
    # Retry-After: 0 keeps the test from waiting out the real backoff.
    sent = _here_network(
        monkeypatch, settings, lambda request: httpx.Response(503, headers={'Retry-After': '0'}, json={})
    )

    response = _get(client, q='Pittsburgh')

    _assert_error_shape(response, 502, 'PROVIDER_ERROR')
    assert len(sent) == 3


def _here_rejects_the_key(request: httpx.Request) -> httpx.Response:
    return httpx.Response(401, json={'error': 'Unauthorized', 'error_description': f'apiKey {SENTINEL_KEY} invalid'})


def _transport_error_quotes_the_url(request: httpx.Request) -> httpx.Response:
    raise httpx.UnsupportedProtocol(f'cannot GET {request.url}', request=request)


@pytest.mark.usefixtures('fresh_bootstrap')
@pytest.mark.parametrize('network', [_here_rejects_the_key, _transport_error_quotes_the_url])
def test_the_here_key_never_reaches_a_body_a_header_or_a_log(
    monkeypatch: pytest.MonkeyPatch,
    client: Client,
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
    network: Callable[[httpx.Request], httpx.Response],
) -> None:
    sent = _here_network(monkeypatch, settings, network)
    caplog.set_level(logging.DEBUG)

    response = _get(client, q='Pittsburgh')

    _assert_error_shape(response, 502, 'PROVIDER_ERROR')
    assert any(SENTINEL_KEY in str(request.url) for request in sent)  # the key really was used
    assert SENTINEL_KEY not in response.content.decode()
    assert SENTINEL_KEY not in str(dict(response.headers))
    formatter = JsonFormatter()
    assert caplog.records
    for record in caplog.records:
        assert SENTINEL_KEY not in formatter.format(record)


@pytest.mark.usefixtures('fresh_bootstrap')
def test_an_empty_here_key_fails_the_search_with_a_generic_500(
    client: Client, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    settings.HERE_API_KEY = ''

    response = _get(client, q='Pittsburgh')

    assert _assert_error_shape(response, 500, 'INTERNAL_ERROR')['error']['message'] == INTERNAL_ERROR_MESSAGE
    record = next(record for record in caplog.records if record.getMessage() == 'unhandled error')
    assert record.exc_info is not None
    assert isinstance(record.exc_info[1], ImproperlyConfigured)
    assert 'HERE_API_KEY' in str(record.exc_info[1])
