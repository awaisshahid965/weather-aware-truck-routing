import copy
import json
import logging
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import Client
from pytest_django import Settings

from config.json_logging import JsonFormatter
from routing import bootstrap
from routing.domain.models import GeoPoint, RiskLevel
from routing.http.errors import INTERNAL_ERROR_MESSAGE
from routing.http.serializers import parse_plan_request
from routing.services.errors import (
    ForecastUnavailableError,
    InputValidationError,
    InsufficientRoutesError,
    UpstreamError,
    UpstreamTimeoutError,
)
from routing.services.plan_trip import NO_TRAVEL_NOTICE, TWO_ROUTES_NOTICE, Place, PlanTripInput
from tests.http.fakes import (
    CLEVELAND,
    DEPARTURE_AT,
    NEW_CASTLE,
    PITTSBURGH,
    ROUTES,
    FailingPlanTripService,
    plan_trip_service,
)
from tests.services.fakes import FakeForecastProvider, FakeRouteProvider, HourValues

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse as TestResponse

URL = '/api/v1/route-plans'
HERE_FIXTURES = Path(__file__).parent.parent / 'adapters' / 'fixtures'

BODY: dict[str, Any] = {
    'origin': {'label': 'Pittsburgh, PA', 'latitude': 40.4406, 'longitude': -79.9959},
    'destination': {'label': 'Cleveland, OH', 'latitude': 41.4993, 'longitude': -81.6944},
    'departureAt': '2026-11-17T13:00:00Z',
    'departureTimeZone': 'America/New_York',
    'loadWeightLb': 32000,
    'checkpointIntervalMiles': 25,
}

PLAN_KEYS = {
    'generatedAt',
    'departureAt',
    'departureTimeZone',
    'origin',
    'destination',
    'checkpointIntervalMiles',
    'routes',
    'recommendedRouteId',
    'heatmap',
    'notices',
}
PLACE_KEYS = {'label', 'latitude', 'longitude'}
ROUTE_KEYS = {
    'id',
    'name',
    'geometry',
    'distanceMiles',
    'durationSeconds',
    'etaAt',
    'checkpoints',
    'summary',
    'recommended',
}
CHECKPOINT_KEYS = {
    'distanceFromStartMiles',
    'latitude',
    'longitude',
    'etaAt',
    'windMph',
    'rainInPerHour',
    'snowInPerHour',
    'risk',
    'drivers',
}
SUMMARY_KEYS = {'noTravelMiles', 'severeMiles', 'highMiles', 'averageRisk', 'worstRisk'}
HEATMAP_KEYS = {'variable', 'startAt', 'stepHours', 'frames'}
FRAME_KEYS = {'offsetHours', 'validAt', 'points'}
HEATMAP_POINT_KEYS = {'latitude', 'longitude', 'risk', 'riskScore'}


def _post(client: Client, body: object, **headers: str) -> TestResponse:
    return client.post(URL, data=json.dumps(body), content_type='application/json', secure=True, headers=headers)


def _use(monkeypatch: pytest.MonkeyPatch, service: object) -> None:
    monkeypatch.setattr(bootstrap, 'get_plan_trip_service', lambda: service)


def _with(path: str, value: object) -> dict[str, Any]:
    """BODY with the field at a dotted path, such as `origin.latitude`, set to `value`."""
    body = copy.deepcopy(BODY)
    *parents, name = path.split('.')
    target = body
    for parent in parents:
        target = target[parent]
    target[name] = value
    return body


def _without(path: str) -> dict[str, Any]:
    body = copy.deepcopy(BODY)
    *parents, name = path.split('.')
    target = body
    for parent in parents:
        target = target[parent]
    del target[name]
    return body


def _assert_error_shape(response: TestResponse, status: int, code: str) -> dict[str, Any]:
    body: dict[str, Any] = response.json()
    assert response.status_code == status
    assert set(body) == {'error', 'requestId'}
    assert set(body['error']) == {'code', 'message', 'details'}
    assert body['error']['code'] == code
    assert body['requestId'] == response['X-Request-ID']
    return body


@pytest.fixture
def planned(monkeypatch: pytest.MonkeyPatch, client: Client) -> dict[str, Any]:
    """Sara's calm trip, through the real service over port fakes."""
    _use(monkeypatch, plan_trip_service())
    response = _post(client, BODY)
    assert response.status_code == 200
    plan: dict[str, Any] = response.json()
    return plan


# Success


def test_a_plan_has_exactly_the_contract_keys(planned: dict[str, Any]) -> None:
    assert set(planned) == PLAN_KEYS
    assert set(planned['origin']) == set(planned['destination']) == PLACE_KEYS
    assert set(planned['heatmap']) == HEATMAP_KEYS
    for route in planned['routes']:
        assert set(route) == ROUTE_KEYS
        assert set(route['summary']) == SUMMARY_KEYS
        assert set(route['geometry']) == {'type', 'coordinates'}
        for checkpoint in route['checkpoints']:
            assert set(checkpoint) == CHECKPOINT_KEYS
    for frame in planned['heatmap']['frames']:
        assert set(frame) == FRAME_KEYS
        for point in frame['points']:
            assert set(point) == HEATMAP_POINT_KEYS


def test_a_plan_has_3_numbered_routes_and_one_recommended(planned: dict[str, Any]) -> None:
    routes = planned['routes']

    assert [route['id'] for route in routes] == ['route-1', 'route-2', 'route-3']
    assert [route['name'] for route in routes] == ['Route 1', 'Route 2', 'Route 3']
    # Akron (provider index 1) is the fastest, so calm weather recommends it.
    assert [route['recommended'] for route in routes] == [False, True, False]
    assert planned['recommendedRouteId'] == 'route-2'


def test_a_plan_echoes_the_request(planned: dict[str, Any]) -> None:
    assert planned['origin'] == BODY['origin']
    assert planned['destination'] == BODY['destination']
    assert planned['departureAt'] == BODY['departureAt']
    assert planned['departureTimeZone'] == BODY['departureTimeZone']
    assert planned['checkpointIntervalMiles'] == BODY['checkpointIntervalMiles']


def test_the_heatmap_has_49_hourly_frames_from_the_departure(planned: dict[str, Any]) -> None:
    heatmap = planned['heatmap']

    assert heatmap['variable'] == 'combinedRisk'
    assert heatmap['startAt'] == BODY['departureAt']
    assert heatmap['stepHours'] == 1
    assert [frame['offsetHours'] for frame in heatmap['frames']] == list(range(49))
    assert heatmap['frames'][48]['validAt'] == '2026-11-19T13:00:00Z'


def test_every_time_is_utc_with_a_z(planned: dict[str, Any]) -> None:
    times = [planned['generatedAt'], planned['departureAt'], planned['heatmap']['startAt']]
    times += [frame['validAt'] for frame in planned['heatmap']['frames']]
    for route in planned['routes']:
        times += [route['etaAt'], *(checkpoint['etaAt'] for checkpoint in route['checkpoints'])]

    for moment in times:
        assert moment.endswith('Z')
        assert datetime.fromisoformat(moment).utcoffset() == timedelta(0)


def test_coordinates_are_lon_lat_rounded_to_5_decimals(planned: dict[str, Any]) -> None:
    route = planned['routes'][0]
    checkpoint = route['checkpoints'][1]
    point = planned['heatmap']['frames'][0]['points'][0]

    assert route['geometry']['type'] == 'LineString'
    # A US trip: longitude first, so the first value is negative.
    assert route['geometry']['coordinates'][0] == [-79.9959, 40.4406]
    for value in (*checkpoint.values(), *point.values()):
        if isinstance(value, float):
            assert value == round(value, 5)
    assert checkpoint['longitude'] < 0 < checkpoint['latitude']


def test_the_geometry_joins_sections_without_repeating_the_shared_point(planned: dict[str, Any]) -> None:
    coordinates = planned['routes'][0]['geometry']['coordinates']

    # Two straight sections meet at New Castle: it appears once, and the straight runs need no other points.
    assert coordinates == [
        [PITTSBURGH.longitude, PITTSBURGH.latitude],
        [NEW_CASTLE.longitude, NEW_CASTLE.latitude],
        [CLEVELAND.longitude, CLEVELAND.latitude],
    ]


def test_heatmap_points_carry_the_risk_and_its_score(planned: dict[str, Any]) -> None:
    points = [point for frame in planned['heatmap']['frames'] for point in frame['points']]

    assert {(point['risk'], point['riskScore']) for point in points} == {('low', 0)}


def test_no_travel_everywhere_recommends_no_route(monkeypatch: pytest.MonkeyPatch, client: Client) -> None:
    def gale(point: GeoPoint, hour: datetime) -> HourValues:
        return (60.0, 0.0, 0.0)

    _use(monkeypatch, plan_trip_service(forecast=FakeForecastProvider(gale)))

    plan = _post(client, BODY).json()

    assert plan['recommendedRouteId'] is None
    assert [route['recommended'] for route in plan['routes']] == [False, False, False]
    assert NO_TRAVEL_NOTICE in plan['notices']
    assert {route['summary']['worstRisk'] for route in plan['routes']} == {RiskLevel.NO_TRAVEL.value}
    checkpoint = plan['routes'][0]['checkpoints'][0]
    assert (checkpoint['risk'], checkpoint['drivers']) == ('no_travel', ['wind'])


def test_two_routes_from_the_provider_are_a_plan_with_a_notice(monkeypatch: pytest.MonkeyPatch, client: Client) -> None:
    _use(monkeypatch, plan_trip_service(FakeRouteProvider(ROUTES[:2])))

    response = _post(client, BODY)

    plan = response.json()
    assert response.status_code == 200
    assert [route['id'] for route in plan['routes']] == ['route-1', 'route-2']
    assert plan['recommendedRouteId'] == 'route-2'
    assert TWO_ROUTES_NOTICE in plan['notices']
    assert len(plan['heatmap']['frames']) == 49


def test_the_request_reaches_the_service_as_typed_input(monkeypatch: pytest.MonkeyPatch, client: Client) -> None:
    route_provider = FakeRouteProvider(ROUTES)
    _use(monkeypatch, plan_trip_service(route_provider))

    _post(client, BODY)

    assert route_provider.calls == [(PITTSBURGH, CLEVELAND, DEPARTURE_AT)]


def test_parsing_builds_the_services_input() -> None:
    parsed = parse_plan_request(_with('departureAt', '2026-11-17T13:00:00.250Z'))

    assert parsed == PlanTripInput(
        origin=Place('Pittsburgh, PA', PITTSBURGH),
        destination=Place('Cleveland, OH', CLEVELAND),
        departure_at=DEPARTURE_AT + timedelta(milliseconds=250),
        departure_time_zone='America/New_York',
        load_weight_lb=32_000,
        checkpoint_interval_miles=25,
    )
    assert parsed.departure_at.tzinfo is UTC


# Invalid input


@pytest.mark.parametrize(
    ('body', 'field'),
    [
        pytest.param(_without('origin'), 'origin', id='origin-missing'),
        pytest.param(_with('origin', 'Pittsburgh'), 'origin', id='origin-not-an-object'),
        pytest.param(_without('origin.latitude'), 'origin.latitude', id='latitude-missing'),
        pytest.param(_with('origin.latitude', 90.01), 'origin.latitude', id='latitude-over-90'),
        pytest.param(_with('origin.latitude', -90.01), 'origin.latitude', id='latitude-under-minus-90'),
        pytest.param(_with('destination.longitude', 180.01), 'destination.longitude', id='longitude-over-180'),
        pytest.param(_with('destination.longitude', -180.01), 'destination.longitude', id='longitude-under-minus-180'),
        pytest.param(_with('origin.latitude', '40.4406'), 'origin.latitude', id='latitude-as-a-string'),
        pytest.param(_with('origin.latitude', 'NaN'), 'origin.latitude', id='latitude-nan-string'),
        pytest.param(_with('origin.latitude', True), 'origin.latitude', id='latitude-as-a-boolean'),
        pytest.param(_with('origin.latitude', None), 'origin.latitude', id='latitude-null'),
        pytest.param(_with('origin.label', ''), 'origin.label', id='label-empty'),
        pytest.param(_with('origin.label', '   '), 'origin.label', id='label-blank'),
        pytest.param(_with('destination.label', 'x' * 201), 'destination.label', id='label-over-200'),
        pytest.param(_without('departureAt'), 'departureAt', id='departure-missing'),
        pytest.param(_with('departureAt', '2026-11-17T13:00:00'), 'departureAt', id='departure-without-zone'),
        pytest.param(_with('departureAt', '2026-11-17T13:00:00+00:00'), 'departureAt', id='departure-offset-zero'),
        pytest.param(_with('departureAt', '2026-11-17'), 'departureAt', id='departure-date-only'),
        pytest.param(_with('departureAt', '2026-02-30T13:00:00Z'), 'departureAt', id='departure-no-such-day'),
        pytest.param(_with('departureAt', 'tomorrow'), 'departureAt', id='departure-not-a-time'),
        pytest.param(_with('departureAt', 1_795_352_400), 'departureAt', id='departure-as-a-number'),
        pytest.param(_with('departureTimeZone', 'Mars/Olympus_Mons'), 'departureTimeZone', id='zone-unknown'),
        pytest.param(_with('departureTimeZone', '../../etc/passwd'), 'departureTimeZone', id='zone-a-path'),
        pytest.param(_with('departureTimeZone', 'zone.tab'), 'departureTimeZone', id='zone-a-data-file'),
        pytest.param(_with('departureTimeZone', ''), 'departureTimeZone', id='zone-empty'),
        pytest.param(_with('loadWeightLb', -1), 'loadWeightLb', id='load-negative'),
        pytest.param(_with('loadWeightLb', '32000'), 'loadWeightLb', id='load-as-a-string'),
        pytest.param(_with('loadWeightLb', 10**400), 'loadWeightLb', id='load-too-large-for-a-float'),
        pytest.param(_with('checkpointIntervalMiles', 20), 'checkpointIntervalMiles', id='interval-20'),
        pytest.param(_with('checkpointIntervalMiles', '25'), 'checkpointIntervalMiles', id='interval-as-a-string'),
        pytest.param(_with('checkpointIntervalMiles', 25.0), 'checkpointIntervalMiles', id='interval-as-a-float'),
        pytest.param(_with('checkpointIntervalMiles', True), 'checkpointIntervalMiles', id='interval-as-a-boolean'),
    ],
)
def test_an_invalid_field_is_a_400_that_names_it(
    monkeypatch: pytest.MonkeyPatch, client: Client, body: dict[str, Any], field: str
) -> None:
    _use(monkeypatch, plan_trip_service())

    response = _post(client, body)

    error = _assert_error_shape(response, 400, 'VALIDATION_ERROR')['error']
    assert list(error['details']) == [field]
    assert all(isinstance(message, str) and message for message in error['details'][field])


def test_a_departure_with_a_non_utc_offset_is_a_400(monkeypatch: pytest.MonkeyPatch, client: Client) -> None:
    _use(monkeypatch, plan_trip_service())

    response = _post(client, _with('departureAt', '2026-10-16T12:00:00+05:00'))

    assert _assert_error_shape(response, 400, 'VALIDATION_ERROR')['error']['details'].keys() == {'departureAt'}


def test_an_infinite_number_is_a_400_that_names_its_field(monkeypatch: pytest.MonkeyPatch, client: Client) -> None:
    _use(monkeypatch, plan_trip_service())
    # Valid JSON that Python reads as infinity.
    raw = json.dumps(BODY).replace('"loadWeightLb": 32000', '"loadWeightLb": 1e999')

    response = client.post(URL, data=raw, content_type='application/json', secure=True)

    assert _assert_error_shape(response, 400, 'VALIDATION_ERROR')['error']['details'].keys() == {'loadWeightLb'}


def test_every_bad_field_is_named_at_once(monkeypatch: pytest.MonkeyPatch, client: Client) -> None:
    _use(monkeypatch, plan_trip_service())
    body = _with('origin.latitude', 91)
    body['checkpointIntervalMiles'] = 30

    response = _post(client, body)

    details = _assert_error_shape(response, 400, 'VALIDATION_ERROR')['error']['details']
    assert set(details) == {'origin.latitude', 'checkpointIntervalMiles'}


def test_a_business_rule_from_the_service_is_a_400_naming_the_field(
    monkeypatch: pytest.MonkeyPatch, client: Client
) -> None:
    _use(monkeypatch, plan_trip_service())

    response = _post(client, _with('departureAt', '2026-11-16T13:00:00Z'))  # before the fixed clock

    error = _assert_error_shape(response, 400, 'VALIDATION_ERROR')['error']
    assert error['details'] == {'departureAt': ['Must be in the future.']}
    assert error['message'] == 'departureAt must be in the future.'


def test_the_same_origin_and_destination_is_a_400_naming_the_destination(
    monkeypatch: pytest.MonkeyPatch, client: Client
) -> None:
    _use(monkeypatch, plan_trip_service())

    response = _post(client, _with('destination', BODY['origin']))

    error = _assert_error_shape(response, 400, 'VALIDATION_ERROR')['error']
    assert error['details'] == {'destination': ['Must be at least 0.1 miles from the origin.']}


def test_a_body_that_is_not_an_object_is_a_400(monkeypatch: pytest.MonkeyPatch, client: Client) -> None:
    _use(monkeypatch, plan_trip_service())

    response = _post(client, [BODY])

    assert _assert_error_shape(response, 400, 'VALIDATION_ERROR')['error']['details'].keys() == {'non_field_errors'}


def test_malformed_json_is_a_400(monkeypatch: pytest.MonkeyPatch, client: Client) -> None:
    _use(monkeypatch, plan_trip_service())

    response = client.post(URL, data='{"origin": ', content_type='application/json', secure=True)

    _assert_error_shape(response, 400, 'VALIDATION_ERROR')


def test_a_non_json_body_is_a_415_in_the_contract_shape(monkeypatch: pytest.MonkeyPatch, client: Client) -> None:
    _use(monkeypatch, plan_trip_service())

    response = client.post(URL, data='origin=Pittsburgh', content_type='text/plain', secure=True)

    _assert_error_shape(response, 415, 'UNSUPPORTED_MEDIA_TYPE')


def test_a_get_is_a_405_in_the_contract_shape(client: Client) -> None:
    response = client.get(URL, secure=True)

    _assert_error_shape(response, 405, 'METHOD_NOT_ALLOWED')
    assert response['Allow'] == 'POST, OPTIONS'


# Service errors


@pytest.mark.parametrize(
    ('error', 'status', 'code', 'details'),
    [
        pytest.param(
            InputValidationError('destination', 'must be at least 0.1 miles from the origin'),
            400,
            'VALIDATION_ERROR',
            {'destination': ['Must be at least 0.1 miles from the origin.']},
            id='input',
        ),
        pytest.param(InsufficientRoutesError(0), 422, 'INSUFFICIENT_ROUTES', {'availableCount': 0}, id='no-route'),
        pytest.param(
            ForecastUnavailableError('the forecast does not cover 2026-11-17T16:00:00Z'),
            422,
            'FORECAST_UNAVAILABLE',
            {'reason': 'the forecast does not cover 2026-11-17T16:00:00Z'},
            id='forecast-unavailable',
        ),
        pytest.param(
            UpstreamTimeoutError('the routing provider did not answer in time'),
            504,
            'PROVIDER_TIMEOUT',
            {},
            id='timeout',
        ),
        pytest.param(UpstreamError('the forecast provider failed'), 502, 'PROVIDER_ERROR', {}, id='provider'),
    ],
)
def test_each_service_error_has_its_status_and_code(
    monkeypatch: pytest.MonkeyPatch,
    client: Client,
    error: Exception,
    status: int,
    code: str,
    details: dict[str, object],
) -> None:
    _use(monkeypatch, FailingPlanTripService(error))

    response = _post(client, BODY, **{'X-Request-ID': 'sara-trip-1'})

    body = _assert_error_shape(response, status, code)
    assert body['error']['details'] == details
    assert body['requestId'] == 'sara-trip-1'


def test_a_provider_failure_is_logged_with_its_cause(
    monkeypatch: pytest.MonkeyPatch, client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    error = UpstreamError('the routing provider failed')
    error.__cause__ = RuntimeError('GET /v8/routes answered 401')
    _use(monkeypatch, FailingPlanTripService(error))

    response = _post(client, BODY)

    record = next(record for record in caplog.records if record.getMessage() == 'request failed')
    assert vars(record)['code'] == 'PROVIDER_ERROR'
    assert vars(record)['cause'] == 'GET /v8/routes answered 401'
    assert vars(record)['request_id'] == response['X-Request-ID']


def test_an_unexpected_error_is_a_generic_500_and_is_logged(
    monkeypatch: pytest.MonkeyPatch, client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    _use(monkeypatch, FailingPlanTripService(ZeroDivisionError('internal detail 42')))

    response = _post(client, BODY)

    body = _assert_error_shape(response, 500, 'INTERNAL_ERROR')
    assert body['error'] == {'code': 'INTERNAL_ERROR', 'message': INTERNAL_ERROR_MESSAGE, 'details': {}}
    text = response.content.decode()
    assert 'internal detail 42' not in text
    assert 'Traceback' not in text
    assert 'ZeroDivisionError' not in text
    record = next(record for record in caplog.records if record.getMessage() == 'unhandled error')
    assert record.exc_info is not None
    assert isinstance(record.exc_info[1], ZeroDivisionError)


# The composition root, with the real adapters on a fake network

SENTINEL_KEY = 'sentinel-here-key-7d1f'


@pytest.fixture
def fresh_bootstrap() -> Iterator[None]:
    bootstrap.get_plan_trip_service.cache_clear()
    yield
    bootstrap.get_plan_trip_service.cache_clear()


def _fixture(name: str) -> object:
    return json.loads((HERE_FIXTURES / name).read_text(encoding='utf-8'))


def _here_rejects_the_key(request: httpx.Request) -> httpx.Response:
    return httpx.Response(401, json={'error': 'Unauthorized', 'error_description': f'apiKey {SENTINEL_KEY} invalid'})


def _transport_error_quotes_the_url(request: httpx.Request) -> httpx.Response:
    raise httpx.UnsupportedProtocol(f'cannot GET {request.url}', request=request)


def _forecast_fails_after_routes(request: httpx.Request) -> httpx.Response:
    if request.url.host == 'router.hereapi.com':
        return httpx.Response(200, json=_fixture('here/routes_three.json'))
    return httpx.Response(400, json=_fixture('open_meteo/error_400.json'))


@pytest.mark.usefixtures('fresh_bootstrap')
@pytest.mark.parametrize(
    'network', [_here_rejects_the_key, _transport_error_quotes_the_url, _forecast_fails_after_routes]
)
def test_the_here_key_never_reaches_a_body_a_header_or_a_log(
    monkeypatch: pytest.MonkeyPatch,
    client: Client,
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
    network: Callable[[httpx.Request], httpx.Response],
) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return network(request)

    settings.HERE_API_KEY = SENTINEL_KEY
    monkeypatch.setattr(bootstrap, '_http_client', lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    caplog.set_level(logging.DEBUG)
    departure_at = (datetime.now(UTC) + timedelta(hours=2)).replace(microsecond=0)

    response = _post(client, _with('departureAt', departure_at.isoformat().replace('+00:00', 'Z')))

    _assert_error_shape(response, 502, 'PROVIDER_ERROR')
    assert any(SENTINEL_KEY in str(request.url) for request in sent)  # the key really was used
    assert SENTINEL_KEY not in response.content.decode()
    assert SENTINEL_KEY not in str(dict(response.headers))
    formatter = JsonFormatter()
    assert caplog.records
    for record in caplog.records:
        assert SENTINEL_KEY not in formatter.format(record)


@pytest.mark.usefixtures('fresh_bootstrap')
def test_an_empty_here_key_fails_the_first_plan_with_a_generic_500(
    client: Client, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    settings.HERE_API_KEY = ''

    response = _post(client, BODY)

    assert _assert_error_shape(response, 500, 'INTERNAL_ERROR')['error']['message'] == INTERNAL_ERROR_MESSAGE
    record = next(record for record in caplog.records if record.getMessage() == 'unhandled error')
    assert record.exc_info is not None
    assert isinstance(record.exc_info[1], ImproperlyConfigured)
    assert 'HERE_API_KEY' in str(record.exc_info[1])
