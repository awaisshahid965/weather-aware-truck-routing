import logging
import math
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import combinations, pairwise

import pytest

from routing.domain.corridor import HEATMAP_HOURS, corridor_points
from routing.domain.geometry import destination_point, haversine_miles
from routing.domain.models import ONE_HOUR, GeoPoint, HourlySeries, RiskLevel, RouteCandidate, RouteSection
from routing.domain.sampling import build_checkpoints
from routing.ports.errors import ForecastRangeError, ProviderError, ProviderTimeoutError
from routing.services.errors import (
    ForecastUnavailableError,
    InputValidationError,
    InsufficientRoutesError,
    UpstreamError,
    UpstreamTimeoutError,
)
from routing.services.plan_trip import (
    ESTIMATE_NOTICE,
    NO_TRAVEL_NOTICE,
    Place,
    PlanTripInput,
    PlanTripService,
)
from tests.services.fakes import (
    CALM,
    FakeForecastProvider,
    FakeRiskRulesSource,
    FakeRouteProvider,
    HourValues,
    ValuesAt,
)
from tests.spec_rules import SPEC_RULES, at_least

LOW = RiskLevel.LOW
MODERATE = RiskLevel.MODERATE
SEVERE = RiskLevel.SEVERE
NO_TRAVEL = RiskLevel.NO_TRAVEL

# Sara's trip: Pittsburgh to Cleveland, Tue 2026-11-17 at 8:00 AM EST, 32,000 lb, every 25 mi.
NOW = datetime(2026, 11, 17, 1, 0, tzinfo=UTC)
DEPARTURE_AT = datetime(2026, 11, 17, 13, 0, tzinfo=UTC)
PITTSBURGH = GeoPoint(40.4406, -79.9959)
CLEVELAND = GeoPoint(41.4993, -81.6944)
NEW_CASTLE = GeoPoint(41.0034, -80.3470)
AKRON = GeoPoint(41.0814, -81.5190)
YOUNGSTOWN = GeoPoint(41.0998, -80.6495)
NORTHERN = GeoPoint(41.40, -80.60)

MAX_LEAD_HOURS = 354  # the fake forecast's default
LAST_DEPARTURE_AT = NOW + timedelta(hours=MAX_LEAD_HOURS - HEATMAP_HOURS)

REQUEST = PlanTripInput(
    origin=Place('Pittsburgh, PA', PITTSBURGH),
    destination=Place('Cleveland, OH', CLEVELAND),
    departure_at=DEPARTURE_AT,
    departure_time_zone='America/New_York',
    load_weight_lb=32_000,
    checkpoint_interval_miles=25,
)

STRICT_RULES = replace(
    SPEC_RULES, version='strict-test', wind_cuts=(at_least(5), at_least(10), at_least(15), at_least(20))
)

_LOG_RECORD_ATTRIBUTES = frozenset(vars(logging.makeLogRecord({}))) | {'message', 'asctime'}


def _route(provider_index: int, *waypoints: GeoPoint, mph: float) -> RouteCandidate:
    """One straight section per leg, as long as its shape, driven at `mph`."""
    sections = tuple(
        RouteSection((a, b), length_miles=haversine_miles(a, b), duration_seconds=haversine_miles(a, b) / mph * 3600)
        for a, b in pairwise(waypoints)
    )
    return RouteCandidate(provider_index=provider_index, sections=sections)


# Turnpike, Akron, Northern. Akron is the fastest, so calm weather recommends it.
ROUTES = (
    _route(0, PITTSBURGH, NEW_CASTLE, CLEVELAND, mph=55),
    _route(1, PITTSBURGH, AKRON, CLEVELAND, mph=65),
    _route(2, PITTSBURGH, NORTHERN, CLEVELAND, mph=50),
)


def _service(
    route_provider: FakeRouteProvider | None = None,
    forecast: FakeForecastProvider | None = None,
    rules: FakeRiskRulesSource | None = None,
) -> PlanTripService:
    return PlanTripService(
        route_provider or FakeRouteProvider(ROUTES),
        forecast or FakeForecastProvider(),
        rules or FakeRiskRulesSource(),
        clock=lambda: NOW,
        max_route_miles=2_500,
        max_heatmap_points=90,
        forecast_dedupe_miles=3,
    )


def _steady_wind(mph: float) -> ValuesAt:
    def values_at(point: GeoPoint, hour: datetime) -> HourValues:
        return (mph, 0.0, 0.0)

    return values_at


# The plan


def test_a_calm_trip_plans_3_routes_and_recommends_the_fastest() -> None:
    plan = _service().run(REQUEST)

    assert [route.candidate for route in plan.routes] == list(ROUTES)
    assert len(plan.heatmap) == 49
    durations = [route.candidate.duration_seconds for route in plan.routes]
    assert plan.recommended_index == durations.index(min(durations)) == 1
    assert plan.notices == (ESTIMATE_NOTICE,)
    assert plan.generated_at == NOW
    assert plan.request is REQUEST
    assert {checkpoint.risk.level for route in plan.routes for checkpoint in route.checkpoints} == {LOW}


@pytest.mark.parametrize('interval_miles', [10, 25, 50])
def test_checkpoints_sit_at_the_interval_and_the_route_eta_is_the_destinations(interval_miles: int) -> None:
    plan = _service().run(replace(REQUEST, checkpoint_interval_miles=interval_miles))

    for route in plan.routes:
        distances = [checkpoint.checkpoint.distance_from_start_miles for checkpoint in route.checkpoints]
        assert distances[:-1] == [k * interval_miles for k in range(len(distances) - 1)]
        assert distances[-1] == route.candidate.distance_miles
        assert route.eta_at == route.checkpoints[-1].checkpoint.eta_at
        assert route.eta_at == DEPARTURE_AT + timedelta(seconds=route.candidate.duration_seconds)


def test_the_heatmap_has_49_hourly_frames_over_the_corridor_points() -> None:
    plan = _service().run(REQUEST)

    assert [frame.offset_hours for frame in plan.heatmap] == list(range(49))
    assert [frame.valid_at for frame in plan.heatmap] == [DEPARTURE_AT + k * ONE_HOUR for k in range(49)]
    corridor = corridor_points(ROUTES, max_points=90)
    for frame in plan.heatmap:
        assert tuple(heatmap_point.point for heatmap_point in frame.points) == corridor


def test_one_routing_call_and_one_forecast_call_serve_the_whole_plan() -> None:
    route_provider = FakeRouteProvider(ROUTES)
    forecast = FakeForecastProvider()

    _service(route_provider, forecast).run(REQUEST)

    assert route_provider.calls == [(PITTSBURGH, CLEVELAND, DEPARTURE_AT)]
    assert len(forecast.calls) == 1


def test_more_than_3_routes_keeps_the_first_3() -> None:
    fourth = _route(3, PITTSBURGH, CLEVELAND, mph=70)

    plan = _service(FakeRouteProvider([*ROUTES, fourth])).run(REQUEST)

    assert [route.candidate for route in plan.routes] == list(ROUTES)


@pytest.mark.parametrize('available_count', [0, 1, 2])
def test_fewer_than_3_routes_is_insufficient_and_no_forecast_is_fetched(available_count: int) -> None:
    forecast = FakeForecastProvider()
    rules = FakeRiskRulesSource()

    with pytest.raises(InsufficientRoutesError) as caught:
        _service(FakeRouteProvider(ROUTES[:available_count]), forecast, rules).run(REQUEST)

    assert caught.value.available_count == available_count
    assert forecast.calls == []
    assert rules.calls == 0


# Risk


def test_wind_at_60_mph_everywhere_recommends_no_route_and_says_no_travel() -> None:
    plan = _service(forecast=FakeForecastProvider(_steady_wind(60))).run(REQUEST)

    assert plan.recommended_index is None
    assert plan.notices == (NO_TRAVEL_NOTICE, ESTIMATE_NOTICE)
    for route in plan.routes:
        assert route.summary.no_travel_miles == pytest.approx(route.candidate.distance_miles)
    assert {heatmap_point.risk for frame in plan.heatmap for heatmap_point in frame.points} == {NO_TRAVEL}


@pytest.mark.parametrize(('load_weight_lb', 'level'), [(30_000, SEVERE), (30_001, NO_TRAVEL)])
def test_the_load_reaches_every_checkpoint_and_frame(load_weight_lb: float, level: RiskLevel) -> None:
    forecast = FakeForecastProvider(_steady_wind(50))

    plan = _service(forecast=forecast).run(replace(REQUEST, load_weight_lb=load_weight_lb))

    assert {checkpoint.risk.level for route in plan.routes for checkpoint in route.checkpoints} == {level}
    assert {heatmap_point.risk for frame in plan.heatmap for heatmap_point in frame.points} == {level}
    assert (plan.recommended_index is None) is (level is NO_TRAVEL)


def test_each_checkpoint_reads_the_forecast_at_its_own_eta() -> None:
    windy_from = DEPARTURE_AT + 2 * ONE_HOUR

    def windy_later(point: GeoPoint, hour: datetime) -> HourValues:
        return (60.0 if hour >= windy_from else 0.0, 0.0, 0.0)

    plan = _service(forecast=FakeForecastProvider(windy_later)).run(REQUEST)

    for route in plan.routes:
        for assessed in route.checkpoints:
            # A moment reads the first hour at or after it, so any ETA after 14:00 reads the windy 15:00.
            windy = assessed.checkpoint.eta_at > windy_from - ONE_HOUR
            assert assessed.risk.level is (NO_TRAVEL if windy else LOW)
    assert {checkpoint.risk.level for route in plan.routes for checkpoint in route.checkpoints} == {LOW, NO_TRAVEL}
    # The heatmap shows hour k after departure, not the truck's ETA.
    assert [frame.points[0].risk for frame in plan.heatmap[:3]] == [LOW, LOW, NO_TRAVEL]


def test_each_checkpoint_reads_the_forecast_of_a_point_within_3_miles() -> None:
    # Each fetched point's weather spells out where it is: wind is its latitude, rain its longitude + 180.
    def where(point: GeoPoint, hour: datetime) -> HourValues:
        return (point.latitude, point.longitude + 180, 0.0)

    plan = _service(forecast=FakeForecastProvider(where)).run(replace(REQUEST, checkpoint_interval_miles=10))

    for route in plan.routes:
        for assessed in route.checkpoints:
            read_from = GeoPoint(assessed.weather.wind_mph, assessed.weather.rain_in_per_hour - 180)
            assert haversine_miles(read_from, assessed.checkpoint.point) < 3


def test_each_heatmap_point_reads_the_forecast_near_it() -> None:
    windy_west_of = -80.8

    def windy_west(point: GeoPoint, hour: datetime) -> HourValues:
        return (60.0 if point.longitude < windy_west_of else 0.0, 0.0, 0.0)

    plan = _service(forecast=FakeForecastProvider(windy_west)).run(REQUEST)

    checked = 0
    for frame in plan.heatmap:
        for heatmap_point in frame.points:
            # A point may read a forecast up to 3 mi away, about 0.06° of longitude here. Skip points near the line.
            if abs(heatmap_point.point.longitude - windy_west_of) > 0.1:
                checked += 1
                assert heatmap_point.risk is (NO_TRAVEL if heatmap_point.point.longitude < windy_west_of else LOW)
    assert checked > 49 * 10


# Forecast gaps


def test_a_null_at_one_checkpoints_hour_fails_the_plan() -> None:
    # Route 1's second checkpoint is the second point fetched (10 mi from the first), so it keeps its own forecast.
    checkpoint = build_checkpoints(ROUTES[0], 10, DEPARTURE_AT)[1]

    def gap_at_checkpoint(point: GeoPoint, hour: datetime) -> HourValues:
        if point == checkpoint.point and checkpoint.eta_at <= hour < checkpoint.eta_at + ONE_HOUR:
            return (None, 0.0, 0.0)
        return CALM

    forecast = FakeForecastProvider(gap_at_checkpoint)

    with pytest.raises(ForecastUnavailableError, match='wind_mph'):
        _service(forecast=forecast).run(replace(REQUEST, checkpoint_interval_miles=10))


def test_a_gap_that_only_the_last_heatmap_frame_reads_fails_the_plan() -> None:
    last_frame_at = DEPARTURE_AT + timedelta(hours=HEATMAP_HOURS)

    def gap_at_last_frame(point: GeoPoint, hour: datetime) -> HourValues:
        return (0.0, None, 0.0) if hour == last_frame_at else CALM

    with pytest.raises(ForecastUnavailableError, match='rain_in_per_hour'):
        _service(forecast=FakeForecastProvider(gap_at_last_frame)).run(REQUEST)


def test_a_series_that_ends_before_the_last_eta_fails_the_plan() -> None:
    forecast = FakeForecastProvider(ends_at=DEPARTURE_AT + ONE_HOUR)

    with pytest.raises(ForecastUnavailableError, match='does not cover'):
        _service(forecast=forecast).run(REQUEST)


# Forecast points and window


def test_overlapping_routes_share_forecast_points_kept_at_least_3_miles_apart() -> None:
    # All three share the first leg, to Youngstown.
    routes = [
        _route(0, PITTSBURGH, YOUNGSTOWN, CLEVELAND, mph=55),
        _route(1, PITTSBURGH, YOUNGSTOWN, AKRON, CLEVELAND, mph=55),
        _route(2, PITTSBURGH, YOUNGSTOWN, NORTHERN, CLEVELAND, mph=55),
    ]
    raw_count = sum(len(build_checkpoints(route, 25, DEPARTURE_AT)) for route in routes) + len(
        corridor_points(routes, max_points=90)
    )
    forecast = FakeForecastProvider()

    _service(FakeRouteProvider(routes), forecast).run(REQUEST)

    [call] = forecast.calls
    assert len(call.points) < raw_count
    assert min(haversine_miles(a, b) for a, b in combinations(call.points, 2)) >= 3


def test_the_window_runs_from_the_departure_hour_to_48_hours_later() -> None:
    forecast = FakeForecastProvider()
    departure_at = DEPARTURE_AT + timedelta(minutes=20)

    plan = _service(forecast=forecast).run(replace(REQUEST, departure_at=departure_at))

    [call] = forecast.calls
    assert call.start_at == DEPARTURE_AT  # 13:20 floored to 13:00
    assert call.end_at == DEPARTURE_AT + timedelta(hours=HEATMAP_HOURS + 1)  # 13:20 + 48 h, ceiled to 14:00
    assert call.end_at >= max(route.eta_at for route in plan.routes)


def test_the_window_reaches_the_last_eta_when_a_route_takes_longer_than_48_hours() -> None:
    crawling = _route(2, PITTSBURGH, NORTHERN, CLEVELAND, mph=2)  # about 65 h
    forecast = FakeForecastProvider()

    plan = _service(FakeRouteProvider([*ROUTES[:2], crawling]), forecast).run(REQUEST)

    last_eta = plan.routes[2].eta_at
    assert last_eta > DEPARTURE_AT + timedelta(hours=HEATMAP_HOURS)
    [call] = forecast.calls
    assert last_eta <= call.end_at < last_eta + ONE_HOUR


# Input validation


@pytest.mark.parametrize(
    ('request_', 'field'),
    [
        pytest.param(replace(REQUEST, departure_at=NOW - ONE_HOUR), 'departureAt', id='departure-in-the-past'),
        pytest.param(replace(REQUEST, departure_at=NOW), 'departureAt', id='departure-now'),
        pytest.param(replace(REQUEST, departure_at=DEPARTURE_AT.replace(tzinfo=None)), 'departureAt', id='naive'),
        pytest.param(
            replace(REQUEST, departure_at=LAST_DEPARTURE_AT + timedelta(seconds=1)),
            'departureAt',
            id='heatmap-beyond-forecast-range',
        ),
        pytest.param(replace(REQUEST, destination=REQUEST.origin), 'destination', id='same-place'),
        pytest.param(
            replace(REQUEST, destination=Place('Next door', destination_point(PITTSBURGH, 90, 0.05))),
            'destination',
            id='under-0.1-mi-apart',
        ),
        pytest.param(replace(REQUEST, load_weight_lb=-1), 'loadWeightLb', id='negative-load'),
        pytest.param(replace(REQUEST, load_weight_lb=math.nan), 'loadWeightLb', id='nan-load'),
        pytest.param(replace(REQUEST, load_weight_lb=math.inf), 'loadWeightLb', id='infinite-load'),
        pytest.param(replace(REQUEST, checkpoint_interval_miles=0), 'checkpointIntervalMiles', id='interval-0'),
        pytest.param(replace(REQUEST, checkpoint_interval_miles=20), 'checkpointIntervalMiles', id='interval-20'),
    ],
)
def test_an_invalid_input_is_rejected_before_any_provider_call(request_: PlanTripInput, field: str) -> None:
    route_provider = FakeRouteProvider(ROUTES)
    forecast = FakeForecastProvider()

    with pytest.raises(InputValidationError) as caught:
        _service(route_provider, forecast).run(request_)

    assert caught.value.field == field
    assert route_provider.calls == []
    assert forecast.calls == []


def test_a_departure_whose_heatmap_ends_at_the_forecast_range_is_accepted() -> None:
    plan = _service().run(replace(REQUEST, departure_at=LAST_DEPARTURE_AT))

    assert len(plan.heatmap) == 49


def test_a_forecast_range_refusal_is_a_departure_error_not_a_provider_error() -> None:
    refusal = ForecastRangeError('the forecast ends before the window does')

    with pytest.raises(InputValidationError) as caught:
        _service(forecast=FakeForecastProvider(error=refusal)).run(REQUEST)

    assert caught.value.field == 'departureAt'
    assert caught.value.__cause__ is refusal


def _one_section_route(provider_index: int, length_miles: float) -> RouteCandidate:
    section = RouteSection((PITTSBURGH, CLEVELAND), length_miles=length_miles, duration_seconds=length_miles * 60)
    return RouteCandidate(provider_index=provider_index, sections=(section,))


def test_a_route_over_the_length_cap_is_rejected_before_any_weather_call() -> None:
    routes = [*ROUTES[:2], _one_section_route(2, 2_500.1)]
    forecast = FakeForecastProvider()

    with pytest.raises(InputValidationError, match=r'route 3 is 2,500\.1 miles') as caught:
        _service(FakeRouteProvider(routes), forecast).run(REQUEST)

    assert caught.value.field == 'destination'
    assert forecast.calls == []


def test_a_route_at_the_length_cap_is_planned() -> None:
    routes = [*ROUTES[:2], _one_section_route(2, 2_500)]

    plan = _service(FakeRouteProvider(routes)).run(REQUEST)

    assert plan.routes[2].candidate.distance_miles == 2_500


# Provider failures


@pytest.mark.parametrize(
    ('raised_type', 'expected_type'),
    [
        pytest.param(ProviderTimeoutError, UpstreamTimeoutError, id='timeout'),
        pytest.param(ProviderError, UpstreamError, id='failure'),
    ],
)
@pytest.mark.parametrize('failing', ['routing', 'forecast'])
def test_a_provider_failure_becomes_an_upstream_error_caused_by_it(
    failing: str, raised_type: type[ProviderError], expected_type: type[UpstreamError]
) -> None:
    raised = raised_type('HERE answered 503')
    route_provider = FakeRouteProvider(ROUTES, error=raised if failing == 'routing' else None)
    forecast = FakeForecastProvider(error=raised if failing == 'forecast' else None)

    with pytest.raises(expected_type) as caught:
        _service(route_provider, forecast).run(REQUEST)

    assert type(caught.value) is expected_type
    assert caught.value.__cause__ is raised
    # The service names the provider. The details stay on the cause, for the logs.
    assert failing in str(caught.value)
    assert '503' not in str(caught.value)


class _ShortForecast(FakeForecastProvider):
    """Drops the last series, as a broken adapter might."""

    def hourly(self, points: Sequence[GeoPoint], start_at: datetime, end_at: datetime) -> list[HourlySeries]:
        return super().hourly(points, start_at, end_at)[:-1]


def test_a_forecast_with_a_series_missing_is_an_upstream_error() -> None:
    with pytest.raises(UpstreamError, match='series for'):
        _service(forecast=_ShortForecast()).run(REQUEST)


# Rules


def test_the_rules_are_read_exactly_once_per_plan() -> None:
    rules = FakeRiskRulesSource()

    _service(rules=rules).run(replace(REQUEST, checkpoint_interval_miles=10))

    assert rules.calls == 1


def test_the_plan_names_the_rules_that_produced_it() -> None:
    rules = FakeRiskRulesSource(replace(SPEC_RULES, version='assessment-2026-11'))

    plan = _service(rules=rules).run(REQUEST)

    assert plan.rules_version == 'assessment-2026-11'


def test_stricter_rules_on_the_same_weather_change_the_plan() -> None:
    forecast = FakeForecastProvider(_steady_wind(30))

    spec_plan = _service(forecast=forecast).run(REQUEST)
    strict_plan = _service(forecast=forecast, rules=FakeRiskRulesSource(STRICT_RULES)).run(REQUEST)

    assert [route.summary.worst_risk for route in spec_plan.routes] == [MODERATE] * 3
    assert [route.summary.worst_risk for route in strict_plan.routes] == [NO_TRAVEL] * 3
    assert spec_plan.recommended_index == 1
    assert strict_plan.recommended_index is None


# Logging and construction


def test_one_log_line_carries_the_counts_and_never_a_place(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    forecast = FakeForecastProvider()

    plan = _service(forecast=forecast).run(REQUEST)

    [record] = [record for record in caplog.records if record.getMessage() == 'trip planned']
    extra = {key: value for key, value in vars(record).items() if key not in _LOG_RECORD_ATTRIBUTES}
    # Exactly these keys, so no label or coordinate can ride along.
    assert extra.keys() == {'rules_version', 'routes', 'checkpoints', 'forecast_points', 'elapsed_ms'}
    assert extra['rules_version'] == SPEC_RULES.version
    assert extra['routes'] == 3
    assert extra['checkpoints'] == sum(len(route.checkpoints) for route in plan.routes)
    assert extra['forecast_points'] == len(forecast.calls[0].points)
    assert isinstance(extra['elapsed_ms'], int)
    assert extra['elapsed_ms'] >= 0


@pytest.mark.parametrize(
    ('max_route_miles', 'max_heatmap_points', 'forecast_dedupe_miles', 'message'),
    [
        (0, 90, 3, 'max_route_miles'),
        (math.nan, 90, 3, 'max_route_miles'),
        (2_500, 0, 3, 'max_heatmap_points'),
        (2_500, 90, -1, 'forecast_dedupe_miles'),
        (2_500, 90, math.inf, 'forecast_dedupe_miles'),
    ],
)
def test_the_constructor_rejects_impossible_limits(
    max_route_miles: float, max_heatmap_points: int, forecast_dedupe_miles: float, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        PlanTripService(
            FakeRouteProvider(ROUTES),
            FakeForecastProvider(),
            FakeRiskRulesSource(),
            clock=lambda: NOW,
            max_route_miles=max_route_miles,
            max_heatmap_points=max_heatmap_points,
            forecast_dedupe_miles=forecast_dedupe_miles,
        )
