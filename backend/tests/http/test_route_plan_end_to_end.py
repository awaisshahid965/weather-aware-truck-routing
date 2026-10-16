"""One whole plan, from the HTTP request to the response, on recorded provider answers.

The real composition, minus the network: the HERE and Open-Meteo adapters run on an
`httpx.MockTransport` that replays what the providers answered. HERE's answer is the three
Pittsburgh to Cleveland routes. Open-Meteo's is the forecast for every point this plan
reads, recorded live on 2026-10-16 for a 3:00 PM EDT departure that day. Rain near Cleveland
makes each route's last checkpoint Moderate, and the heatmap's early hours show it moving through.

The response is also the frontend's fixture, `frontend/tests/fixtures/route-plan.json`, and
the last test keeps the two equal. After an intended change, rewrite it from `backend/` with
`UPDATE_FIXTURES=1 uv run pytest tests/http/test_route_plan_end_to_end.py`, then run
`npm run format` in `frontend/`.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from django.test import Client

from routing import bootstrap
from routing.adapters.here_router import HereRouter
from routing.adapters.open_meteo_forecast import OpenMeteoForecast
from routing.services.plan_trip import ESTIMATE_NOTICE, PlanTripService

FIXTURES = Path(__file__).parent.parent / 'adapters' / 'fixtures'
HERE_ROUTES = FIXTURES / 'here' / 'routes_three.json'
FORECAST_EXCHANGES = FIXTURES / 'open_meteo' / 'trip_window.json'
FRONTEND_FIXTURE = Path(__file__).parents[3] / 'frontend' / 'tests' / 'fixtures' / 'route-plan.json'

# An hour before departure, as when the forecast was recorded.
NOW = datetime(2026, 10, 16, 18, 0, tzinfo=UTC)
DEPARTURE_AT = datetime(2026, 10, 16, 19, 0, tzinfo=UTC)

BODY: dict[str, Any] = {
    'origin': {'label': 'Pittsburgh, PA', 'latitude': 40.4406, 'longitude': -79.9959},
    'destination': {'label': 'Cleveland, OH', 'latitude': 41.4993, 'longitude': -81.6944},
    'departureAt': '2026-10-16T19:00:00Z',
    'departureTimeZone': 'America/New_York',
    'loadWeightLb': 32000,
    'checkpointIntervalMiles': 25,
}


def _replay(request: httpx.Request) -> httpx.Response:
    """The recorded answer to this exact request. Any other request fails the plan."""
    if request.url.host == 'router.hereapi.com':
        return httpx.Response(200, content=HERE_ROUTES.read_bytes(), headers={'content-type': 'application/json'})
    if request.url.host == 'api.open-meteo.com':
        exchanges: list[dict[str, Any]] = json.loads(FORECAST_EXCHANGES.read_text(encoding='utf-8'))
        query = dict(request.url.params)
        for exchange in exchanges:
            if exchange['query'] == query:
                return httpx.Response(200, json=exchange['response'])
    raise AssertionError(f'no recorded answer for {request.url.host}{request.url.path}')


def _service() -> PlanTripService:
    """`bootstrap.get_plan_trip_service`, with a replaying client and a fixed clock."""
    client = httpx.Client(transport=httpx.MockTransport(_replay))
    return PlanTripService(
        HereRouter(client, 'recorded', deadline_seconds=bootstrap.ROUTING_DEADLINE_SECONDS),
        OpenMeteoForecast(
            client, batch_size=bootstrap.FORECAST_BATCH_SIZE, deadline_seconds=bootstrap.FORECAST_DEADLINE_SECONDS
        ),
        bootstrap.get_risk_rules_source(),
        clock=lambda: NOW,
        max_route_miles=bootstrap.MAX_ROUTE_MILES,
        max_heatmap_points=bootstrap.MAX_HEATMAP_POINTS,
        forecast_dedupe_miles=bootstrap.FORECAST_DEDUPE_MILES,
    )


@pytest.fixture
def plan(monkeypatch: pytest.MonkeyPatch, client: Client) -> dict[str, Any]:
    monkeypatch.setattr(bootstrap, 'get_plan_trip_service', _service)

    response = client.post('/api/v1/route-plans', data=json.dumps(BODY), content_type='application/json', secure=True)

    assert response.status_code == 200, response.json()
    body: dict[str, Any] = response.json()
    return body


def test_the_plan_has_the_3_provider_routes_in_order(plan: dict[str, Any]) -> None:
    routes = plan['routes']

    assert [route['id'] for route in routes] == ['route-1', 'route-2', 'route-3']
    assert [round(route['distanceMiles'], 1) for route in routes] == [135.0, 142.0, 137.7]
    assert [round(route['durationSeconds']) for route in routes] == [7894, 8636, 8477]


def test_checkpoints_sit_every_25_miles_and_end_at_the_destination(plan: dict[str, Any]) -> None:
    for route in plan['routes']:
        checkpoints = route['checkpoints']
        miles = [checkpoint['distanceFromStartMiles'] for checkpoint in checkpoints]

        assert miles[:-1] == [25 * index for index in range(len(miles) - 1)]
        assert 0 < miles[-1] - miles[-2] <= 25
        assert miles[-1] == pytest.approx(route['distanceMiles'])
        assert checkpoints[0]['etaAt'] == BODY['departureAt']
        assert checkpoints[-1]['etaAt'] == route['etaAt']
        assert [checkpoints[-1]['latitude'], checkpoints[-1]['longitude']] == pytest.approx(
            [41.4993, -81.6944], abs=1e-3
        )


def test_the_heatmap_has_49_hourly_frames_from_departure(plan: dict[str, Any]) -> None:
    frames = plan['heatmap']['frames']

    assert [frame['offsetHours'] for frame in frames] == list(range(49))
    assert [frame['validAt'] for frame in frames] == [
        (DEPARTURE_AT + timedelta(hours=hour)).isoformat().replace('+00:00', 'Z') for hour in range(49)
    ]
    assert len({len(frame['points']) for frame in frames}) == 1


def test_route_1_is_recommended_with_its_summary_numbers(plan: dict[str, Any]) -> None:
    summaries = [route['summary'] for route in plan['routes']]

    # No Severe or High miles anywhere, so average risk decides. Route 1 is also the fastest, so this plan
    # can't tell the third priority from the fourth; tests/domain/test_ranking.py pins their order.
    assert plan['recommendedRouteId'] == 'route-1'
    assert [route['recommended'] for route in plan['routes']] == [True, False, False]
    assert [summary['severeMiles'] for summary in summaries] == [0, 0, 0]
    assert [summary['highMiles'] for summary in summaries] == [0, 0, 0]
    assert [summary['noTravelMiles'] for summary in summaries] == [0, 0, 0]
    assert [summary['averageRisk'] for summary in summaries] == pytest.approx([0.03692, 0.05992, 0.04621], abs=5e-6)
    assert [summary['worstRisk'] for summary in summaries] == ['moderate', 'moderate', 'moderate']
    assert plan['notices'] == [ESTIMATE_NOTICE]


def test_the_frontend_fixture_is_this_response(plan: dict[str, Any]) -> None:
    if os.environ.get('UPDATE_FIXTURES'):
        FRONTEND_FIXTURE.write_text(json.dumps(plan, separators=(',', ':')) + '\n', encoding='utf-8')

    saved = json.loads(FRONTEND_FIXTURE.read_text(encoding='utf-8'))

    assert saved == plan, 'The plan changed. Rewrite the frontend fixture as the module docstring says.'
