from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import combinations, pairwise
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from routing.domain.corridor import (
    HEATMAP_DEDUPE_MILES,
    HEATMAP_HOURS,
    HEATMAP_LATERAL_MILES,
    build_frames,
    corridor_points,
)
from routing.domain.errors import ForecastGapError
from routing.domain.geometry import bearing_degrees, destination_point, haversine_miles
from routing.domain.models import GeoPoint, HourlySeries, RiskLevel, RouteCandidate, RouteSection
from tests.spec_rules import SPEC_RULES, at_least

DEPARTURE_AT = datetime(2026, 11, 17, 13, 0, tzinfo=UTC)
ORIGIN = GeoPoint(40, -80)
POINTS = (GeoPoint(40.44, -79.99), GeoPoint(41.50, -81.69))


def _route(*waypoints: GeoPoint) -> RouteCandidate:
    """One straight section per leg, as long as its shape, at 60 mph."""
    sections = tuple(
        RouteSection((a, b), length_miles=haversine_miles(a, b), duration_seconds=60 * haversine_miles(a, b))
        for a, b in pairwise(waypoints)
    )
    return RouteCandidate(provider_index=0, sections=sections)


def _due_north(miles: float) -> RouteCandidate:
    return _route(ORIGIN, destination_point(ORIGIN, 0, miles))


def _split(points: Sequence[GeoPoint], centers: int) -> list[tuple[GeoPoint, GeoPoint, GeoPoint]]:
    """One route's points as (center, left, right). Centers come first, then two laterals per center."""
    laterals = points[centers:]
    return [(points[i], laterals[2 * i], laterals[2 * i + 1]) for i in range(centers)]


# Corridor points


def test_a_straight_100_mile_route_gives_5_centers_and_10_laterals() -> None:
    points = corridor_points([_due_north(100)], max_points=90)

    assert len(points) == 15
    assert [haversine_miles(ORIGIN, center) for center in points[:5]] == pytest.approx([0, 25, 50, 75, 100])


def test_each_lateral_sits_15_miles_to_one_side_of_its_center() -> None:
    points = corridor_points([_due_north(100)], max_points=90)

    for center, left, right in _split(points, centers=5):
        assert haversine_miles(center, left) == pytest.approx(HEATMAP_LATERAL_MILES, abs=0.1)
        assert haversine_miles(center, right) == pytest.approx(HEATMAP_LATERAL_MILES, abs=0.1)
        # Heading north, left is west and right is east.
        assert left.longitude < center.longitude < right.longitude


def test_on_a_north_south_route_laterals_share_their_centers_latitude() -> None:
    points = corridor_points([_due_north(100)], max_points=90)

    for center, left, right in _split(points, centers=5):
        assert left.latitude == pytest.approx(center.latitude, abs=0.01)
        assert right.latitude == pytest.approx(center.latitude, abs=0.01)


def test_the_heading_at_each_end_comes_from_the_road_just_inside_it() -> None:
    # 50 mi north, then 50 mi east: the start heads north, the end heads east.
    corner = destination_point(ORIGIN, 0, 50)
    end = destination_point(corner, 90, 50)

    points = corridor_points([_route(ORIGIN, corner, end)], max_points=90)

    triples = _split(points, centers=5)
    start_center, start_left, start_right = triples[0]
    end_center, end_left, end_right = triples[-1]
    assert bearing_degrees(start_center, start_left) == pytest.approx(270, abs=1)
    assert bearing_degrees(start_center, start_right) == pytest.approx(90, abs=1)
    assert bearing_degrees(end_center, end_left) == pytest.approx(0, abs=1)
    assert bearing_degrees(end_center, end_right) == pytest.approx(180, abs=1)


def test_the_same_route_three_times_gives_the_same_points_as_once() -> None:
    route = _due_north(100)
    copies = [replace(route, provider_index=index) for index in range(3)]

    points = corridor_points(copies, max_points=90)

    assert len(points) == 15
    assert points == corridor_points([route], max_points=90)


def test_too_many_points_widen_the_spacing_until_they_fit() -> None:
    # 25 mi and 31.25 mi give 15 points; 39.0625 mi gives 4 centers and 8 laterals.
    points = corridor_points([_due_north(100)], max_points=12)

    assert len(points) == 12
    assert [haversine_miles(ORIGIN, center) for center in points[:4]] == pytest.approx([0, 39.0625, 78.125, 100])


def test_three_1500_mile_routes_fit_in_90_points_the_same_way_every_run() -> None:
    start = GeoPoint(30, -100)
    routes = [_route(start, destination_point(start, bearing, 1500)) for bearing in (0, 45, 90)]

    first = corridor_points(routes, max_points=90)

    assert 0 < len(first) <= 90
    assert corridor_points(routes, max_points=90) == first


def test_a_cap_too_small_for_the_endpoints_alone_is_rejected() -> None:
    # One route's endpoints and their laterals are 6 points.
    with pytest.raises(ValueError, match='too few'):
        corridor_points([_due_north(100)], max_points=5)


def test_a_cap_below_1_is_rejected() -> None:
    with pytest.raises(ValueError, match='max_points'):
        corridor_points([_due_north(100)], max_points=0)


# A route is 1 to 3 legs from ORIGIN, each (bearing, miles). Shared starts make the routes overlap.
legs = st.lists(
    st.tuples(st.floats(min_value=0, max_value=360, exclude_max=True), st.floats(min_value=1, max_value=300)),
    min_size=1,
    max_size=3,
)


def _walk(route_legs: list[tuple[float, float]]) -> RouteCandidate:
    waypoints = [ORIGIN]
    for bearing, miles in route_legs:
        waypoints.append(destination_point(waypoints[-1], bearing, miles))
    return _route(*waypoints)


@settings(deadline=None)
@given(routes=st.lists(legs, min_size=1, max_size=3), max_points=st.integers(min_value=18, max_value=90))
def test_kept_points_are_spread_out_and_within_the_cap(
    routes: list[list[tuple[float, float]]], max_points: int
) -> None:
    points = corridor_points([_walk(route_legs) for route_legs in routes], max_points=max_points)

    assert len(points) <= max_points
    assert all(haversine_miles(a, b) >= HEATMAP_DEDUPE_MILES for a, b in combinations(points, 2))


# Frames


def _series(start_at: datetime, hours: int, wind_mph: Sequence[float] = (10,)) -> HourlySeries:
    """`hours` hours from `start_at`. Wind follows `wind_mph`, then holds its last value. No rain or snow."""
    winds = [wind_mph[min(k, len(wind_mph) - 1)] for k in range(hours)]
    return HourlySeries(
        hours=tuple(start_at + timedelta(hours=k) for k in range(hours)),
        wind_mph=tuple(winds),
        rain_in_per_hour=(0.0,) * hours,
        snow_in_per_hour=(0.0,) * hours,
    )


def _two_day(wind_mph: float = 10) -> HourlySeries:
    """Every hour a frame reads, from DEPARTURE_AT to 48 h later."""
    return _series(DEPARTURE_AT, HEATMAP_HOURS + 1, (wind_mph,))


def test_there_is_a_frame_for_each_hour_from_departure_to_48_hours_later() -> None:
    frames = build_frames(POINTS, [_two_day(), _two_day()], DEPARTURE_AT, 0, SPEC_RULES)

    assert [frame.offset_hours for frame in frames] == list(range(49))
    assert [frame.valid_at for frame in frames] == [DEPARTURE_AT + timedelta(hours=k) for k in range(49)]
    assert all(tuple(p.point for p in frame.points) == POINTS for frame in frames)


@pytest.mark.parametrize(
    ('load_lb', 'expected'),
    [(30_000, RiskLevel.SEVERE), (30_001, RiskLevel.NO_TRAVEL)],
)
def test_each_point_gets_the_classifier_level_for_its_weather_and_the_load(load_lb: float, expected: RiskLevel) -> None:
    frames = build_frames(POINTS, [_two_day(50), _two_day(50)], DEPARTURE_AT, load_lb, SPEC_RULES)

    assert {p.risk for frame in frames for p in frame.points} == {expected}


def test_the_rules_passed_in_are_the_rules_used() -> None:
    stricter = replace(
        SPEC_RULES, version='stricter', wind_cuts=(at_least(10), at_least(20), at_least(30), at_least(40))
    )

    spec_frames = build_frames(POINTS, [_two_day(30), _two_day(30)], DEPARTURE_AT, 0, SPEC_RULES)
    strict_frames = build_frames(POINTS, [_two_day(30), _two_day(30)], DEPARTURE_AT, 0, stricter)

    assert {p.risk for frame in spec_frames for p in frame.points} == {RiskLevel.MODERATE}
    assert {p.risk for frame in strict_frames for p in frame.points} == {RiskLevel.SEVERE}


def test_one_forecast_ending_40_hours_after_departure_fails_the_whole_heatmap() -> None:
    short = _series(DEPARTURE_AT, 41)

    with pytest.raises(ForecastGapError):
        build_frames(POINTS, [_two_day(), short], DEPARTURE_AT, 0, SPEC_RULES)


def test_a_departure_between_hours_reads_the_hour_at_or_after_each_frame() -> None:
    departure_at = datetime(2026, 11, 17, 12, 20, tzinfo=UTC)
    # 12:00 Severe, 13:00 Low, 14:00 Moderate, then Low. The last frame, 12:20 + 48 h, reads 13:00.
    forecast = _series(datetime(2026, 11, 17, 12, tzinfo=UTC), 50, (50, 10, 30, 10))

    frames = build_frames(POINTS[:1], [forecast], departure_at, 0, SPEC_RULES)

    assert frames[0].valid_at == departure_at
    assert frames[0].points[0].risk is RiskLevel.LOW
    assert frames[1].points[0].risk is RiskLevel.MODERATE


def test_frames_step_in_utc_hours_across_a_dst_change() -> None:
    # US clocks fall back at 2 AM on 2026-11-01. 00:30 EDT is 04:30 UTC.
    departure_at = datetime(2026, 11, 1, 0, 30, tzinfo=ZoneInfo('America/New_York'))
    start_at = datetime(2026, 11, 1, 4, 30, tzinfo=UTC)
    forecast = _series(datetime(2026, 11, 1, 5, tzinfo=UTC), HEATMAP_HOURS + 1)

    frames = build_frames(POINTS[:1], [forecast], departure_at, 0, SPEC_RULES)

    assert [frame.valid_at for frame in frames] == [start_at + timedelta(hours=k) for k in range(49)]
    assert all(frame.valid_at.tzinfo is UTC for frame in frames)


def test_each_point_needs_its_own_series() -> None:
    with pytest.raises(ValueError, match='one series per point'):
        build_frames(POINTS, [_two_day()], DEPARTURE_AT, 0, SPEC_RULES)


def test_a_naive_departure_is_rejected() -> None:
    with pytest.raises(ValueError, match='timezone-aware'):
        build_frames(POINTS, [_two_day(), _two_day()], DEPARTURE_AT.replace(tzinfo=None), 0, SPEC_RULES)
