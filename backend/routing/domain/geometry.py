"""Distances on the Earth's surface, standard library only."""

import math

from routing.domain.models import GeoPoint

EARTH_RADIUS_MILES = 3958.7613  # mean radius; the spherical model is accurate enough here


def haversine_miles(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance. Haversine stays accurate for the short hops between shape points."""
    lat_a = math.radians(a.latitude)
    lat_b = math.radians(b.latitude)
    half_chord = (
        math.sin((lat_b - lat_a) / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(math.radians(b.longitude - a.longitude) / 2) ** 2
    )
    # Rounding can push the value a hair above 1 for near-antipodal points; asin would then fail.
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(min(half_chord, 1.0)))


def bearing_degrees(a: GeoPoint, b: GeoPoint) -> float:
    """The initial great-circle bearing from `a` to `b`: degrees clockwise from north, in [0, 360)."""
    lat_a = math.radians(a.latitude)
    lat_b = math.radians(b.latitude)
    d_lon = math.radians(b.longitude - a.longitude)
    y = math.sin(d_lon) * math.cos(lat_b)
    x = math.cos(lat_a) * math.sin(lat_b) - math.sin(lat_a) * math.cos(lat_b) * math.cos(d_lon)
    # atan2 gives (-180, 180]. Adding 360 first keeps `%` on positive numbers, where it is exact.
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def destination_point(start: GeoPoint, bearing_deg: float, distance_miles: float) -> GeoPoint:
    """Where a great circle leaving `start` at `bearing_deg` is after `distance_miles`."""
    lat = math.radians(start.latitude)
    bearing = math.radians(bearing_deg)
    angle = distance_miles / EARTH_RADIUS_MILES
    sin_lat_end = math.sin(lat) * math.cos(angle) + math.cos(lat) * math.sin(angle) * math.cos(bearing)
    # Rounding can push the sine a hair past ±1 near a pole; asin would then fail.
    sin_lat_end = max(-1.0, min(1.0, sin_lat_end))
    d_lon = math.atan2(
        math.sin(bearing) * math.sin(angle) * math.cos(lat),
        math.cos(angle) - math.sin(lat) * sin_lat_end,
    )
    longitude = start.longitude + math.degrees(d_lon)
    return GeoPoint(
        latitude=math.degrees(math.asin(sin_lat_end)),
        # Wrap across the antimeridian into [-180, 180).
        longitude=(longitude + 540) % 360 - 180,
    )
