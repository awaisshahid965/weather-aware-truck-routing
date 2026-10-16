import json
import logging
import uuid

import pytest
from django.conf import settings
from django.test import Client

from config.json_logging import JsonFormatter
from routing import bootstrap
from routing.http.middleware import REQUEST_ID_HEADER, current_request_id
from tests.http.fakes import plan_trip_service

URL = '/api/v1/route-plans'  # a GET answers 405 without calling any service


def _request_logs(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == 'routing.http.middleware']


def test_a_valid_incoming_request_id_is_echoed_in_the_header_and_the_body(client: Client) -> None:
    response = client.get(URL, secure=True, headers={REQUEST_ID_HEADER: 'Sara-trip-42'})

    assert response[REQUEST_ID_HEADER] == 'Sara-trip-42'
    assert response.json()['requestId'] == 'Sara-trip-42'


@pytest.mark.parametrize(
    'incoming',
    [
        pytest.param('', id='empty'),
        pytest.param('has space', id='space'),
        pytest.param('semi;colon', id='punctuation'),
        pytest.param('trailing-newline\n', id='trailing-newline'),
        pytest.param('a' * 65, id='over-64-characters'),
    ],
)
def test_an_invalid_request_id_is_replaced_by_a_uuid4(client: Client, incoming: str) -> None:
    response = client.get(URL, secure=True, headers={REQUEST_ID_HEADER: incoming})

    request_id = response[REQUEST_ID_HEADER]
    assert request_id != incoming
    assert uuid.UUID(request_id).version == 4
    assert response.json()['requestId'] == request_id


def test_a_request_without_an_id_gets_a_uuid4(client: Client) -> None:
    response = client.get(URL, secure=True)

    assert uuid.UUID(response[REQUEST_ID_HEADER]).version == 4


def test_a_response_from_outside_the_api_views_gets_an_id_too(client: Client) -> None:
    response = client.get('/api/v1/nowhere', secure=True)

    assert response.status_code == 404
    assert uuid.UUID(response[REQUEST_ID_HEADER]).version == 4


def test_each_request_logs_one_line_with_its_outcome(client: Client, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    client.get(URL, secure=True, headers={REQUEST_ID_HEADER: 'Sara-trip-42'})

    [record] = _request_logs(caplog)
    fields = vars(record)
    assert record.getMessage() == 'request completed'
    assert (fields['method'], fields['path'], fields['status'], fields['request_id']) == (
        'GET',
        URL,
        405,
        'Sara-trip-42',
    )
    assert isinstance(fields['duration_ms'], int)
    assert fields['duration_ms'] >= 0


def test_no_log_line_holds_a_label_a_coordinate_or_the_query(
    monkeypatch: pytest.MonkeyPatch, client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(bootstrap, 'get_plan_trip_service', plan_trip_service)
    caplog.set_level(logging.DEBUG)
    body = {
        'origin': {'label': 'Pittsburgh, PA', 'latitude': 40.4406, 'longitude': -79.9959},
        'destination': {'label': 'Cleveland, OH', 'latitude': 41.4993, 'longitude': -81.6944},
        'departureAt': '2026-11-17T13:00:00Z',
        'departureTimeZone': 'America/New_York',
        'loadWeightLb': 32000,
        'checkpointIntervalMiles': 25,
    }

    response = client.post(
        f'{URL}?note=private-note', data=json.dumps(body), content_type='application/json', secure=True
    )

    assert response.status_code == 200
    [record] = _request_logs(caplog)
    assert vars(record)['path'] == URL
    lines = [JsonFormatter().format(record) for record in caplog.records]
    for private in ('Pittsburgh', 'Cleveland', '40.4406', '79.9959', '41.4993', '81.6944', 'private-note'):
        assert not any(private in line for line in lines), private


def test_healthz_still_answers_and_logs_nothing(client: Client, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    response = client.get('/healthz')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
    assert REQUEST_ID_HEADER not in response
    assert caplog.records == []


def test_the_middleware_sits_right_after_the_health_check() -> None:
    middleware = list(settings.MIDDLEWARE)

    position = middleware.index('routing.http.middleware.RequestIdMiddleware')

    assert position == middleware.index('config.health.HealthCheckMiddleware') + 1


def test_the_request_id_is_cleared_when_the_request_ends(client: Client) -> None:
    client.get(URL, secure=True)

    assert current_request_id() is None
