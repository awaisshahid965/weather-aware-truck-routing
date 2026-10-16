"""Distances on the Earth's surface, standard library only."""

import math
from collections.abc import Sequence

from routing.domain.models import GeoPoint

EARTH_RADIUS_MILES = 3958.7613  # mean radius; the spherical model is accurate enough here
DISPLAY_TOLERANCE_MILES = 0.01  # about 16 m: too small to see at any zoom that shows a whole route
_MERCATOR_MAX_LATITUDE = 85.05112878  # Web Mercator's edge; the poles would project to infinity


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


def simplify(points: Sequence[GeoPoint], tolerance_miles: float = DISPLAY_TOLERANCE_MILES) -> list[GeoPoint]:
    """Ramer-Douglas-Peucker: fewer points, none of the dropped ones more than `tolerance_miles` off the line.

    For drawing only. Checkpoints are sampled from the full shape; a simplified one would move
    them off the road. The map draws each segment straight in Web Mercator, so the deviation is
    measured there and converted to miles at each point's latitude. Both endpoints are kept.
    """
    if not (math.isfinite(tolerance_miles) and tolerance_miles >= 0):
        raise ValueError(f'tolerance_miles must be finite and >= 0, got {tolerance_miles!r}')
    if len(points) < 3:
        return list(points)
    xs, ys = zip(*(_web_mercator(point) for point in points), strict=True)
    # Mercator stretches lengths by 1 / cos(latitude), so this undoes it at each point.
    miles_per_unit = [EARTH_RADIUS_MILES * math.cos(math.radians(point.latitude)) for point in points]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    # A stack, not recursion: a long winding route can split deeper than Python's recursion limit.
    spans = [(0, len(points) - 1)]
    while spans:
        first, last = spans.pop()
        start_x, start_y = xs[first], ys[first]
        dx, dy = xs[last] - start_x, ys[last] - start_y
        length_squared = dx * dx + dy * dy
        farthest, deviation_miles = first, 0.0
        for index in range(first + 1, last):
            px, py = xs[index] - start_x, ys[index] - start_y
            # Distance to the segment, not the infinite line: a route can double back past its ends.
            t = 0.0 if length_squared == 0 else min(1.0, max(0.0, (px * dx + py * dy) / length_squared))
            miles = math.hypot(px - t * dx, py - t * dy) * miles_per_unit[index]
            if miles > deviation_miles:
                farthest, deviation_miles = index, miles
        if deviation_miles > tolerance_miles:
            keep[farthest] = True
            spans += [(first, farthest), (farthest, last)]
    return [point for point, kept in zip(points, keep, strict=True) if kept]


def _web_mercator(point: GeoPoint) -> tuple[float, float]:
    """The point on a Web Mercator plane, in Earth radii. Longitude is used as is: truck routes never cross ±180°."""
    latitude = math.radians(max(-_MERCATOR_MAX_LATITUDE, min(_MERCATOR_MAX_LATITUDE, point.latitude)))
    return math.radians(point.longitude), math.asinh(math.tan(latitude))
