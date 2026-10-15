import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from routing.domain.geometry import EARTH_RADIUS_MILES, haversine_miles
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


@pytest.mark.parametrize(
    ('latitude', 'longitude'),
    [(90.01, 0), (-90.01, 0), (math.nan, 0), (0, 180.01), (0, -180.01), (0, math.inf)],
)
def test_geo_point_rejects_coordinates_off_the_globe(latitude: float, longitude: float) -> None:
    with pytest.raises(ValueError, match='must be within'):
        GeoPoint(latitude, longitude)
