import math
from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from routing.domain.geometry import (
    EARTH_RADIUS_MILES,
    bearing_degrees,
    destination_point,
    haversine_miles,
    simplify,
)
from routing.domain.models import GeoPoint

points = st.builds(
    GeoPoint,
    latitude=st.floats(min_value=-90, max_value=90),
    longitude=st.floats(min_value=-180, max_value=180),
)


def test_one_degree_of_latitude_at_the_equator_is_about_69_miles() -> None:
    distance = haversine_miles(GeoPoint(0, 0), GeoPoint(1, 0))

    assert distance == pytest.approx(69.093, abs=0.01)


def test_a_point_is_zero_miles_from_itself() -> None:
    point = GeoPoint(40.44, -79.99)

    assert haversine_miles(point, point) == 0


def test_antipodal_points_are_half_the_circumference_apart() -> None:
    distance = haversine_miles(GeoPoint(0, 0), GeoPoint(0, 180))

    assert distance == pytest.approx(math.pi * EARTH_RADIUS_MILES)


@given(a=points, b=points)
def test_distance_is_the_same_both_ways(a: GeoPoint, b: GeoPoint) -> None:
    there = haversine_miles(a, b)
    back = haversine_miles(b, a)

    assert there == pytest.approx(back, abs=1e-9)
    assert 0 <= there <= math.pi * EARTH_RADIUS_MILES + 1e-9


def test_a_point_due_north_has_a_bearing_of_zero() -> None:
    bearing = bearing_degrees(GeoPoint(40, -80), GeoPoint(41, -80))

    assert bearing == pytest.approx(0, abs=1e-9)


@pytest.mark.parametrize(
    ('end', 'expected'),
    [
        pytest.param(GeoPoint(0, 1), 90, id='east'),
        pytest.param(GeoPoint(-1, 0), 180, id='south'),
        pytest.param(GeoPoint(0, -1), 270, id='west'),
    ],
)
def test_bearings_run_clockwise_from_north(end: GeoPoint, expected: float) -> None:
    bearing = bearing_degrees(GeoPoint(0, 0), end)

    assert bearing == pytest.approx(expected)


@given(a=points, b=points)
def test_a_bearing_is_at_least_0_and_below_360(a: GeoPoint, b: GeoPoint) -> None:
    assert 0 <= bearing_degrees(a, b) < 360


def test_15_miles_due_east_measures_15_miles_back() -> None:
    start = GeoPoint(40.44, -79.99)

    east = destination_point(start, 90, 15)

    assert haversine_miles(start, east) == pytest.approx(15, abs=0.01)
    assert east.longitude > start.longitude


def test_a_destination_across_the_antimeridian_wraps_its_longitude() -> None:
    start = GeoPoint(0, 179.9)

    east = destination_point(start, 90, 20)

    assert -180 < east.longitude < -179.5
    assert haversine_miles(start, east) == pytest.approx(20)


@given(
    start=st.builds(
        GeoPoint,
        latitude=st.floats(min_value=-80, max_value=80),
        longitude=st.floats(min_value=-180, max_value=180),
    ),
    bearing=st.floats(min_value=0, max_value=360, exclude_max=True),
    miles=st.floats(min_value=0.1, max_value=500),
)
def test_a_destination_lies_at_the_distance_and_bearing_asked(start: GeoPoint, bearing: float, miles: float) -> None:
    end = destination_point(start, bearing, miles)

    assert haversine_miles(start, end) == pytest.approx(miles, abs=1e-6)
    # Compare angles on a circle, so 359.9° and 0.1° are 0.2° apart.
    turned = (bearing_degrees(start, end) - bearing + 180) % 360 - 180
    assert turned == pytest.approx(0, abs=1e-6)


@pytest.mark.parametrize(
    ('latitude', 'longitude'),
    [(90.01, 0), (-90.01, 0), (math.nan, 0), (0, 180.01), (0, -180.01), (0, math.inf)],
)
def test_geo_point_rejects_coordinates_off_the_globe(latitude: float, longitude: float) -> None:
    with pytest.raises(ValueError, match='must be within'):
        GeoPoint(latitude, longitude)


# Simplify for display

MILES_PER_DEGREE = EARTH_RADIUS_MILES * math.pi / 180
FlatPoint = tuple[float, float]


def _flat(point: GeoPoint) -> FlatPoint:
    """Miles east and north of 40°N 80°W. Flat is close enough over the few hundred feet these lines span."""
    return (
        (point.longitude + 80) * MILES_PER_DEGREE * math.cos(math.radians(40)),
        (point.latitude - 40) * MILES_PER_DEGREE,
    )


def _miles_to_segment(point: FlatPoint, start: FlatPoint, end: FlatPoint) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    px, py = point[0] - start[0], point[1] - start[1]
    length_squared = dx * dx + dy * dy
    t = 0.0 if length_squared == 0 else min(1.0, max(0.0, (px * dx + py * dy) / length_squared))
    return math.hypot(px - t * dx, py - t * dy)


@pytest.mark.parametrize(
    'line',
    [
        pytest.param([GeoPoint(40 + k * 0.01, -80) for k in range(11)], id='along-a-meridian'),
        pytest.param([GeoPoint(40, -80 + k * 0.01) for k in range(11)], id='along-a-parallel'),
        pytest.param([GeoPoint(40 + k * 0.001, -80 + k * 0.001) for k in range(11)], id='diagonal'),
    ],
)
def test_collinear_points_simplify_to_the_endpoints(line: list[GeoPoint]) -> None:
    simplified = simplify(line)

    assert simplified == [line[0], line[-1]]


@pytest.mark.parametrize(('offset_miles', 'kept'), [(0.009, False), (0.011, True)])
def test_a_point_is_dropped_only_within_the_tolerance(offset_miles: float, kept: bool) -> None:
    start, end = GeoPoint(40, -80), GeoPoint(40.1, -80)
    bump = destination_point(GeoPoint(40.05, -80), 90, offset_miles)

    simplified = simplify([start, bump, end], tolerance_miles=0.01)

    assert (bump in simplified) is kept


@pytest.mark.parametrize(
    'line',
    [
        pytest.param([], id='empty'),
        pytest.param([GeoPoint(40, -80)], id='one-point'),
        pytest.param([GeoPoint(40, -80), GeoPoint(40, -80)], id='two-equal-points'),
    ],
)
def test_a_line_under_3_points_is_returned_as_is(line: list[GeoPoint]) -> None:
    assert simplify(line) == line


@given(line=st.lists(points, min_size=2, max_size=30))
def test_simplify_keeps_both_endpoints_and_only_input_points_in_order(line: list[GeoPoint]) -> None:
    simplified = simplify(line)

    assert simplified[0] == line[0]
    assert simplified[-1] == line[-1]
    remaining = iter(line)
    assert all(point in remaining for point in simplified)  # a subsequence of the input


# Each step north is about 0.035 mi; each wiggle reaches about twice the tolerance, so some points go and some stay.
wiggles = st.lists(
    st.tuples(st.floats(min_value=-0.0003, max_value=0.0003), st.floats(min_value=-0.0003, max_value=0.0003)),
    min_size=3,
    max_size=40,
)


@given(offsets=wiggles)
def test_no_point_is_farther_than_the_tolerance_from_the_simplified_line(offsets: list[tuple[float, float]]) -> None:
    line = [GeoPoint(40 + k * 0.0005 + d_lat, -80 + d_lon) for k, (d_lat, d_lon) in enumerate(offsets)]

    simplified = [_flat(point) for point in simplify(line, tolerance_miles=0.01)]

    for point in line:
        deviation = min(_miles_to_segment(_flat(point), a, b) for a, b in pairwise(simplified))
        assert deviation <= 0.01 * 1.01  # 1% for the flat approximation


@pytest.mark.parametrize('tolerance_miles', [-0.01, math.nan, math.inf])
def test_simplify_rejects_an_impossible_tolerance(tolerance_miles: float) -> None:
    with pytest.raises(ValueError, match='tolerance_miles'):
        simplify([GeoPoint(40, -80)], tolerance_miles=tolerance_miles)
