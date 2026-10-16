import json
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from django.conf import settings as django_settings
from django.test import Client
from pytest_django import Settings

from routing import bootstrap
from routing.domain.models import GeoPoint, PlaceMatch
from routing.http.throttles import DailyQuota
from routing.services.search_places import SearchPlacesService
from tests.http.fakes import ROUTES, plan_trip_service
from tests.services.fakes import FakeGeocoder, FakeRouteProvider

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse as TestResponse

BODY: dict[str, Any] = {
    'origin': {'label': 'Pittsburgh, PA', 'latitude': 40.4406, 'longitude': -79.9959},
    'destination': {'label': 'Cleveland, OH', 'latitude': 41.4993, 'longitude': -81.6944},
    'departureAt': '2026-11-17T13:00:00Z',
    'departureTimeZone': 'America/New_York',
    'loadWeightLb': 32000,
    'checkpointIntervalMiles': 25,
}
PITTSBURGH = PlaceMatch('here:cm:namedplace:21010974', 'Pittsburgh, PA, United States', GeoPoint(40.43851, -79.99734))

# 18:30 UTC, five and a half hours before the counts start again.
EVENING = datetime(2026, 11, 16, 18, 30, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _plan(client: Client, address: str = '203.0.113.1', **headers: str) -> TestResponse:
    return client.post(
        '/api/v1/route-plans',
        data=json.dumps(BODY),
        content_type='application/json',
        secure=True,
        REMOTE_ADDR=address,
        headers=headers,
    )


def _search(client: Client, address: str = '203.0.113.1') -> TestResponse:
    return client.get('/api/v1/places', {'q': 'Pittsburgh'}, secure=True, REMOTE_ADDR=address)


def _rate_limited(response: TestResponse) -> dict[str, Any]:
    body: dict[str, Any] = response.json()
    assert response.status_code == 429
    assert body['error']['code'] == 'RATE_LIMITED'
    assert body['error']['details'] == {'retryAfterSeconds': int(response['Retry-After'])}
    return body


@pytest.fixture
def routes(monkeypatch: pytest.MonkeyPatch) -> FakeRouteProvider:
    """Plans run the real service over fakes. The fake router counts what would have been HERE calls."""
    provider = FakeRouteProvider(ROUTES)
    service = plan_trip_service(provider)
    monkeypatch.setattr(bootstrap, 'get_plan_trip_service', lambda: service)
    return provider


@pytest.fixture
def geocoder(monkeypatch: pytest.MonkeyPatch) -> FakeGeocoder:
    fake = FakeGeocoder([PITTSBURGH])
    service = SearchPlacesService(fake)
    monkeypatch.setattr(bootstrap, 'get_search_places_service', lambda: service)
    return fake


def _use_from_another_process(arguments: tuple[str, int]) -> bool:
    path, limit = arguments
    return DailyQuota(Path(path)).try_use('route_plans', limit)


# The shared daily count


def test_a_daily_quota_counts_up_to_its_limit_then_refuses(tmp_path: Path) -> None:
    quota = DailyQuota(tmp_path / 'quota.json', Clock(EVENING))

    results = [quota.try_use('route_plans', 3) for _ in range(5)]

    assert results == [True, True, True, False, False]


def test_each_scope_has_its_own_count(tmp_path: Path) -> None:
    quota = DailyQuota(tmp_path / 'quota.json', Clock(EVENING))

    assert quota.try_use('route_plans', 1)

    assert quota.try_use('places', 1)
    assert not quota.try_use('route_plans', 1)


def test_the_count_starts_again_at_midnight_utc(tmp_path: Path) -> None:
    clock = Clock(EVENING)
    quota = DailyQuota(tmp_path / 'quota.json', clock)
    assert quota.try_use('route_plans', 1)
    assert not quota.try_use('route_plans', 1)

    clock.now = datetime(2026, 11, 17, 0, 0, tzinfo=UTC)

    assert quota.try_use('route_plans', 1)


def test_the_wait_runs_to_the_next_midnight_utc(tmp_path: Path) -> None:
    quota = DailyQuota(tmp_path / 'quota.json', Clock(EVENING))

    assert quota.seconds_until_reset() == 5.5 * 3600


def test_two_quotas_on_one_file_share_one_count(tmp_path: Path) -> None:
    path = tmp_path / 'quota.json'
    first, second = DailyQuota(path, Clock(EVENING)), DailyQuota(path, Clock(EVENING))

    assert first.try_use('route_plans', 2)
    assert second.try_use('route_plans', 2)

    assert not first.try_use('route_plans', 2)


def test_worker_processes_racing_never_pass_the_limit_together(tmp_path: Path) -> None:
    # Gunicorn's workers are separate processes, so this is the race the lock exists for.
    arguments = [(str(tmp_path / 'quota.json'), 100)] * 240

    with ProcessPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(_use_from_another_process, arguments))

    assert results.count(True) == 100


def test_an_unreadable_file_starts_the_day_at_zero(tmp_path: Path) -> None:
    path = tmp_path / 'quota.json'
    path.write_text('{"day": "2026-11-16", "counts": ', encoding='utf-8')
    quota = DailyQuota(path, Clock(EVENING))

    assert quota.try_use('route_plans', 1)

    assert json.loads(path.read_text(encoding='utf-8')) == {'day': '2026-11-16', 'counts': {'route_plans': 1}}


# Limits on the endpoints


def test_a_visitor_over_the_hourly_limit_gets_a_429_with_a_retry_time(
    monkeypatch: pytest.MonkeyPatch, client: Client, routes: FakeRouteProvider
) -> None:
    monkeypatch.setattr(bootstrap, 'ROUTE_PLANS_PER_VISITOR', '3/hour')

    statuses = [_plan(client).status_code for _ in range(3)]
    refused = _plan(client)

    assert statuses == [200, 200, 200]
    body = _rate_limited(refused)
    assert body['error']['message'] == 'Too many requests from your connection. Try again in 60 minutes.'
    assert 3500 <= int(refused['Retry-After']) <= 3600
    assert len(routes.calls) == 3


def test_one_visitor_at_the_limit_doesnt_stop_another(
    monkeypatch: pytest.MonkeyPatch, client: Client, routes: FakeRouteProvider
) -> None:
    monkeypatch.setattr(bootstrap, 'ROUTE_PLANS_PER_VISITOR', '1/hour')
    assert _plan(client, '203.0.113.1').status_code == 200
    assert _plan(client, '203.0.113.1').status_code == 429

    response = _plan(client, '203.0.113.2')

    assert response.status_code == 200


def test_the_site_stops_at_its_daily_limit_until_midnight_utc(
    monkeypatch: pytest.MonkeyPatch, client: Client, routes: FakeRouteProvider
) -> None:
    monkeypatch.setattr(bootstrap, 'ROUTE_PLANS_PER_DAY', 2)
    assert _plan(client, '203.0.113.1').status_code == 200
    assert _plan(client, '203.0.113.2').status_code == 200

    refused = _plan(client, '203.0.113.3')

    body = _rate_limited(refused)
    assert body['error']['message'] == (
        'This demo has reached its daily limit for route plans, which keeps it free to run. '
        'Try again after midnight UTC.'
    )
    assert 1 <= int(refused['Retry-After']) <= 24 * 3600
    assert len(routes.calls) == 2  # the provider was never asked for the third


def test_a_request_a_visitor_limit_refuses_never_counts_toward_the_day(
    monkeypatch: pytest.MonkeyPatch, client: Client, routes: FakeRouteProvider
) -> None:
    monkeypatch.setattr(bootstrap, 'ROUTE_PLANS_PER_VISITOR', '2/hour')
    monkeypatch.setattr(bootstrap, 'ROUTE_PLANS_PER_DAY', 3)
    one_busy_visitor = [_plan(client, '203.0.113.1').status_code for _ in range(10)]

    another_visitor = _plan(client, '203.0.113.2')

    assert one_busy_visitor == [200, 200] + [429] * 8
    assert another_visitor.status_code == 200
    assert _plan(client, '203.0.113.3').status_code == 429  # the third use of the day was the other visitor's


def test_place_searches_have_their_own_daily_limit(
    monkeypatch: pytest.MonkeyPatch, client: Client, routes: FakeRouteProvider, geocoder: FakeGeocoder
) -> None:
    monkeypatch.setattr(bootstrap, 'PLACE_SEARCHES_PER_DAY', 1)
    assert _search(client, '203.0.113.1').status_code == 200

    refused = _search(client, '203.0.113.2')

    assert 'daily limit for place searches' in _rate_limited(refused)['error']['message']
    assert len(geocoder.calls) == 1
    assert _plan(client, '203.0.113.2').status_code == 200


def test_behind_the_proxy_each_forwarded_address_is_its_own_visitor(
    monkeypatch: pytest.MonkeyPatch, client: Client, settings: Settings, routes: FakeRouteProvider
) -> None:
    settings.REST_FRAMEWORK = {**django_settings.REST_FRAMEWORK, 'NUM_PROXIES': 1}
    monkeypatch.setattr(bootstrap, 'ROUTE_PLANS_PER_VISITOR', '1/hour')
    proxy = '172.18.0.4'  # every request reaches Django from Caddy's address
    assert _plan(client, proxy, **{'X-Forwarded-For': '198.51.100.7'}).status_code == 200

    other_visitor = _plan(client, proxy, **{'X-Forwarded-For': '198.51.100.8'})
    same_visitor = _plan(client, proxy, **{'X-Forwarded-For': '198.51.100.7'})

    assert other_visitor.status_code == 200
    assert same_visitor.status_code == 429


def test_without_a_proxy_a_forwarded_address_is_ignored(
    monkeypatch: pytest.MonkeyPatch, client: Client, routes: FakeRouteProvider
) -> None:
    monkeypatch.setattr(bootstrap, 'ROUTE_PLANS_PER_VISITOR', '1/hour')
    assert _plan(client, '203.0.113.1', **{'X-Forwarded-For': '198.51.100.7'}).status_code == 200

    response = _plan(client, '203.0.113.1', **{'X-Forwarded-For': '198.51.100.8'})

    assert response.status_code == 429  # a client can't become someone new by sending the header
