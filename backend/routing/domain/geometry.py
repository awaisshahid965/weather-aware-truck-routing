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
