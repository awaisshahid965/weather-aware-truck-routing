import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from routing.domain.geometry import EARTH_RADIUS_MILES
from routing.domain.models import GeoPoint, RouteCandidate, RouteSection
from routing.domain.sampling import (
    CHECKPOINT_INTERVALS_MILES,
    build_checkpoints,
    cell_miles,
    checkpoint_distances,
    elapsed_seconds_at,
    point_at,
    point_locator,
    spaced_distances,
)

DEPARTURE_AT = datetime(2026, 11, 17, 13, 0, tzinfo=UTC)
ORIGIN = GeoPoint(40, -80)
# Along a meridian, the haversine distance is exactly this many miles per degree.
MILES_PER_DEGREE_OF_LATITUDE = EARTH_RADIUS_MILES * math.pi / 180


def _north(start: GeoPoint, miles: float) -> GeoPoint:
    return GeoPoint(start.latitude + miles / MILES_PER_DEGREE_OF_LATITUDE, start.longitude)


def _due_north_route(*legs: tuple[float, float]) -> RouteCandidate:
    """Sections laid end to end, due north from ORIGIN. Each leg is (length_miles, duration_seconds).

    Each shape is exactly as long as its provider length.
    """
    sections: list[RouteSection] = []
    start = ORIGIN
    for length_miles, duration_seconds in legs:
        end = _north(start, length_miles)
        sections.append(RouteSection((start, end), length_miles, duration_seconds))
        start = end
    return RouteCandidate(provider_index=0, sections=tuple(sections))


def _offsets_seconds(route: RouteCandidate, interval_miles: int) -> list[float]:
    return [(c.eta_at - DEPARTURE_AT).total_seconds() for c in build_checkpoints(route, interval_miles, DEPARTURE_AT)]


# Spacing


@pytest.mark.parametrize(
    ('total_miles', 'interval_miles', 'expected'),
    [
        (60, 25, [0, 25, 50, 60]),
        pytest.param(50, 25, [0, 25, 50], id='exact multiple has one destination'),
        pytest.param(10, 25, [0, 10], id='shorter than one interval'),
        (35, 10, [0, 10, 20, 30, 35]),
    ],
)
def test_checkpoints_sit_every_interval_then_at_the_destination(
    total_miles: float, interval_miles: int, expected: list[float]
) -> None:
    distances = checkpoint_distances(total_miles, interval_miles)

    assert distances == expected


@pytest.mark.parametrize('interval_miles', [0, 5, 20, 100, -10])
def test_an_unsupported_interval_is_rejected(interval_miles: int) -> None:
    with pytest.raises(ValueError, match='interval_miles must be one of'):
        checkpoint_distances(60, interval_miles)


@pytest.mark.parametrize('total_miles', [0, -1, math.nan, math.inf])
def test_a_route_total_must_be_finite_and_positive(total_miles: float) -> None:
    with pytest.raises(ValueError, match='total_miles'):
        checkpoint_distances(total_miles, 25)


@given(
    total_miles=st.floats(min_value=0.01, max_value=2_500),
    interval_miles=st.sampled_from(sorted(CHECKPOINT_INTERVALS_MILES)),
)
def test_spacing_is_exact_and_ends_once_at_the_destination(total_miles: float, interval_miles: int) -> None:
    distances = checkpoint_distances(total_miles, interval_miles)

    assert distances[0] == 0
    assert distances[-1] == total_miles
    assert all(distances[k] == k * interval_miles for k in range(len(distances) - 1))
    assert 0 < distances[-1] - distances[-2] <= interval_miles


def test_any_spacing_steps_the_same_way() -> None:
    distances = spaced_distances(100, 31.25)

    assert distances == [0, 31.25, 62.5, 93.75, 100]


@pytest.mark.parametrize('spacing_miles', [0, -1, math.nan, math.inf])
def test_a_spacing_must_be_finite_and_positive(spacing_miles: float) -> None:
    with pytest.raises(ValueError, match='spacing_miles'):
        spaced_distances(60, spacing_miles)


# ETA


def test_one_section_keeps_one_pace() -> None:
    route = _due_north_route((60, 3600))

    offsets = _offsets_seconds(route, 25)

    assert offsets == [0, 1500, 3000, 3600]


@pytest.mark.parametrize(
    ('distance_miles', 'expected_seconds'),
    [
        pytest.param(25, 3000, id='inside the slow section'),
        pytest.param(30, 3600, id='the boundary starts the fast section'),
        pytest.param(50, 3600 + (20 / 30) * 1200, id='inside the fast section'),
        pytest.param(60, 4800, id='destination'),
    ],
)
def test_section_durations_drive_the_eta_not_a_constant_speed(distance_miles: float, expected_seconds: float) -> None:
    slow_then_fast = _due_north_route((30, 3600), (30, 1200))

    elapsed = elapsed_seconds_at(slow_then_fast, distance_miles)

    assert elapsed == pytest.approx(expected_seconds)


def test_etas_are_utc_even_when_departure_is_local() -> None:
    # US clocks fall back at 2 AM on 2026-11-01. Two hours after 00:30 EDT is 01:30 EST, not 02:30.
    departure_at = datetime(2026, 11, 1, 0, 30, tzinfo=ZoneInfo('America/New_York'))
    route = _due_north_route((60, 7200))

    checkpoints = build_checkpoints(route, 25, departure_at)

    assert checkpoints[0].eta_at == datetime(2026, 11, 1, 4, 30, tzinfo=UTC)
    assert checkpoints[-1].eta_at == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
    assert all(c.eta_at.tzinfo is UTC for c in checkpoints)


def test_a_naive_departure_is_rejected() -> None:
    route = _due_north_route((60, 3600))

    with pytest.raises(ValueError, match='timezone-aware'):
        build_checkpoints(route, 25, DEPARTURE_AT.replace(tzinfo=None))


def test_build_checkpoints_rejects_an_unsupported_interval() -> None:
    route = _due_north_route((60, 3600))

    with pytest.raises(ValueError, match='interval_miles'):
        build_checkpoints(route, 20, DEPARTURE_AT)


legs = st.lists(
    st.tuples(st.floats(min_value=0.1, max_value=300), st.floats(min_value=0, max_value=20_000)),
    min_size=1,
    max_size=4,
)


@given(legs=legs, interval_miles=st.sampled_from(sorted(CHECKPOINT_INTERVALS_MILES)))
def test_checkpoints_run_from_departure_to_arrival_in_order(
    legs: list[tuple[float, float]], interval_miles: int
) -> None:
    route = _due_north_route(*legs)

    checkpoints = build_checkpoints(route, interval_miles, DEPARTURE_AT)

    etas = [c.eta_at for c in checkpoints]
    assert etas[0] == DEPARTURE_AT
    assert etas[-1] == DEPARTURE_AT + timedelta(seconds=route.duration_seconds)
    assert etas == sorted(etas)
    assert checkpoints[-1].distance_from_start_miles == route.distance_miles
    assert math.fsum(c.cell_miles for c in checkpoints) == pytest.approx(route.distance_miles)


# Position


def test_the_midpoint_distance_lands_halfway_along_a_straight_section() -> None:
    start, end = GeoPoint(40, -80), GeoPoint(41, -80)
    route = RouteCandidate(0, (RouteSection((start, end), length_miles=69.09, duration_seconds=3600),))

    midpoint = point_at(route, 69.09 / 2)

    assert midpoint.latitude == pytest.approx(40.5)
    assert midpoint.longitude == pytest.approx(-80)


def test_provider_miles_map_onto_the_shape_by_fraction() -> None:
    # The provider says 31 mi; the shape measures 30 mi, with an uneven vertex at shape mile 10.
    shape = (ORIGIN, _north(ORIGIN, 10), _north(ORIGIN, 30))
    route = RouteCandidate(0, (RouteSection(shape, length_miles=31, duration_seconds=1860),))

    assert point_at(route, 31) == shape[-1]
    assert point_at(route, 15.5).latitude == pytest.approx(_north(ORIGIN, 15).latitude)
    assert point_at(route, 0) == shape[0]


def test_duplicate_shape_points_are_stepped_over() -> None:
    a, b, c = ORIGIN, _north(ORIGIN, 10), _north(ORIGIN, 20)
    route = RouteCandidate(0, (RouteSection((a, a, b, b, b, c, c), length_miles=20, duration_seconds=1200),))

    assert point_at(route, 10) == b
    assert point_at(route, 15).latitude == pytest.approx(_north(ORIGIN, 15).latitude)
    assert point_at(route, 20) == c


def test_a_section_boundary_is_the_start_of_the_next_section() -> None:
    route = _due_north_route((30, 3600), (30, 1200))

    point = point_at(route, 30)

    assert point == route.sections[1].points[0]


@pytest.mark.parametrize('distance_miles', [-0.01, 60.01, math.nan])
def test_a_distance_off_the_route_is_rejected(distance_miles: float) -> None:
    route = _due_north_route((60, 3600))

    with pytest.raises(ValueError, match='distance_miles must be within'):
        point_at(route, distance_miles)


def test_build_checkpoints_places_points_and_times_like_the_single_lookups() -> None:
    route = _due_north_route((30, 3600), (17, 900), (40, 2400))

    checkpoints = build_checkpoints(route, 10, DEPARTURE_AT)

    for checkpoint in checkpoints:
        distance = checkpoint.distance_from_start_miles
        assert checkpoint.point == point_at(route, distance)
        assert checkpoint.eta_at == DEPARTURE_AT + timedelta(seconds=elapsed_seconds_at(route, distance))


@given(legs=legs, fraction=st.floats(min_value=0, max_value=1))
def test_a_locator_places_points_like_point_at(legs: list[tuple[float, float]], fraction: float) -> None:
    route = _due_north_route(*legs)
    distance = fraction * route.distance_miles

    assert point_locator(route)(distance) == point_at(route, distance)


# Cells


@pytest.mark.parametrize(
    ('distances', 'expected'),
    [
        ([0, 25, 50, 60], [12.5, 25, 17.5, 5]),
        ([0, 10], [5, 5]),
    ],
)
def test_each_cell_runs_between_the_midpoints_to_its_neighbours(distances: list[float], expected: list[float]) -> None:
    cells = cell_miles(distances)

    assert cells == expected
    assert sum(cells) == distances[-1]


@pytest.mark.parametrize('distances', [[], [0], [0, 0], [10, 0], [0, math.nan, 10]])
def test_cells_need_a_strictly_ascending_start_and_end(distances: list[float]) -> None:
    with pytest.raises(ValueError, match='distances'):
        cell_miles(distances)


def test_build_checkpoints_gives_each_checkpoint_its_cell() -> None:
    route = _due_north_route((60, 3600))

    checkpoints = build_checkpoints(route, 25, DEPARTURE_AT)

    assert [c.distance_from_start_miles for c in checkpoints] == [0, 25, 50, 60]
    assert [c.cell_miles for c in checkpoints] == [12.5, 25, 17.5, 5]


# Route types


def test_a_route_totals_its_sections() -> None:
    route = _due_north_route((30, 3600), (30, 1200))

    assert route.distance_miles == 60
    assert route.duration_seconds == 4800


def test_a_section_needs_two_points() -> None:
    with pytest.raises(ValueError, match='at least 2 points'):
        RouteSection((ORIGIN,), length_miles=1, duration_seconds=60)


@pytest.mark.parametrize('length_miles', [0, -1, math.nan, math.inf])
def test_a_section_needs_a_finite_positive_length(length_miles: float) -> None:
    with pytest.raises(ValueError, match='length_miles'):
        RouteSection((ORIGIN, _north(ORIGIN, 1)), length_miles=length_miles, duration_seconds=60)


@pytest.mark.parametrize('duration_seconds', [-1, math.nan, math.inf])
def test_a_section_needs_a_finite_non_negative_duration(duration_seconds: float) -> None:
    with pytest.raises(ValueError, match='duration_seconds'):
        RouteSection((ORIGIN, _north(ORIGIN, 1)), length_miles=1, duration_seconds=duration_seconds)


def test_a_route_needs_a_section() -> None:
    with pytest.raises(ValueError, match='at least 1 section'):
        RouteCandidate(provider_index=0, sections=())


def test_a_route_needs_a_provider_index_of_zero_or_more() -> None:
    section = RouteSection((ORIGIN, _north(ORIGIN, 1)), length_miles=1, duration_seconds=60)

    with pytest.raises(ValueError, match='provider_index'):
        RouteCandidate(provider_index=-1, sections=(section,))
