import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from routing.domain.geometry import EARTH_RADIUS_MILES, bearing_degrees, destination_point, haversine_miles
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
