"""Checkpoints along a route: where each sits, when the truck gets there, and how much road it covers.

The provider's section lengths and durations are the truth. The decoded shape only says where a
mile falls on the map. ETAs follow each section's own pace: a transparent approximation, not
traffic modelling.
"""

import math
from bisect import bisect_left
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from itertools import accumulate, count, pairwise

from routing.domain.geometry import haversine_miles
from routing.domain.models import Checkpoint, GeoPoint, RouteCandidate

CHECKPOINT_INTERVALS_MILES = frozenset({10, 25, 50})


def checkpoint_distances(total_miles: float, interval_miles: int) -> list[float]:
    """`0, I, 2I, …` while below the total, then the destination. The destination never appears twice."""
    if interval_miles not in CHECKPOINT_INTERVALS_MILES:
        raise ValueError(f'interval_miles must be one of {sorted(CHECKPOINT_INTERVALS_MILES)}, got {interval_miles!r}')
    if not (math.isfinite(total_miles) and total_miles > 0):
        raise ValueError(f'total_miles must be finite and > 0, got {total_miles!r}')
    distances: list[float] = []
    # k * I, never a running sum: adding I again and again lets float error build up.
    for k in count():
        distance_miles = float(k * interval_miles)
        if distance_miles >= total_miles:
            break
        distances.append(distance_miles)
    distances.append(total_miles)
    return distances


def point_at(route: RouteCandidate, distance_miles: float) -> GeoPoint:
    """Where the truck is after `distance_miles` of provider distance."""
    index, fraction = _locate(route, distance_miles)
    points = route.sections[index].points
    return _point_along(points, _shape_miles(points), fraction)


def elapsed_seconds_at(route: RouteCandidate, distance_miles: float) -> float:
    """Seconds from departure. Each section keeps its own pace, so a slow stretch stays slow."""
    index, fraction = _locate(route, distance_miles)
    return _elapsed_seconds(route, index, fraction)


def cell_miles(distances: Sequence[float]) -> list[float]:
    """Each checkpoint's share of the road, from the midpoint before it to the midpoint after it.

    The first and last distances are the route's start and end, so the cells sum to the route length.
    """
    if len(distances) < 2:
        raise ValueError(f'cells need at least 2 distances, the start and the end; got {len(distances)}')
    # `not a < b` also catches NaN, which every comparison rejects.
    if not all(a < b for a, b in pairwise(distances)):
        raise ValueError('distances must be strictly ascending')
    midpoints = [(a + b) / 2 for a, b in pairwise(distances)]
    bounds = [distances[0], *midpoints, distances[-1]]
    return [end - start for start, end in pairwise(bounds)]


def build_checkpoints(route: RouteCandidate, interval_miles: int, departure_at: datetime) -> tuple[Checkpoint, ...]:
    """Checkpoints every `interval_miles` plus the destination, each with its ETA and cell."""
    if departure_at.utcoffset() is None:
        raise ValueError('departure_at must be timezone-aware')
    distances = checkpoint_distances(route.distance_miles, interval_miles)
    # Measure each shape once. Calling `point_at` per checkpoint would re-measure the whole
    # section every time, and a long route's shape has tens of thousands of points.
    shapes = [_shape_miles(section.points) for section in route.sections]
    # Add elapsed time in UTC. On local wall-clock time it would be an hour off across a DST change.
    start_at = departure_at.astimezone(UTC)
    checkpoints: list[Checkpoint] = []
    for distance_miles, cell in zip(distances, cell_miles(distances), strict=True):
        index, fraction = _locate(route, distance_miles)
        checkpoints.append(
            Checkpoint(
                distance_from_start_miles=distance_miles,
                point=_point_along(route.sections[index].points, shapes[index], fraction),
                eta_at=start_at + timedelta(seconds=_elapsed_seconds(route, index, fraction)),
                cell_miles=cell,
            )
        )
    return tuple(checkpoints)


def _locate(route: RouteCandidate, distance_miles: float) -> tuple[int, float]:
    """The section holding `distance_miles`, and how far into it the distance falls, from 0 to 1."""
    total_miles = route.distance_miles
    if not 0 <= distance_miles <= total_miles:
        raise ValueError(f'distance_miles must be within [0, {total_miles}], got {distance_miles!r}')
    last_index = len(route.sections) - 1
    if distance_miles == total_miles:
        return last_index, 1.0
    start_miles = 0.0
    for index, section in enumerate(route.sections):
        if distance_miles < start_miles + section.length_miles:
            return index, (distance_miles - start_miles) / section.length_miles
        start_miles += section.length_miles
    # Reached only when the running sum rounds a hair below the exact total.
    return last_index, 1.0


def _elapsed_seconds(route: RouteCandidate, index: int, fraction: float) -> float:
    # fsum, like `RouteCandidate.duration_seconds`: at the destination the two totals match exactly.
    earlier = [section.duration_seconds for section in route.sections[:index]]
    return math.fsum([*earlier, fraction * route.sections[index].duration_seconds])


def _shape_miles(points: Sequence[GeoPoint]) -> list[float]:
    """Running geodesic miles at each shape point, starting at 0."""
    return list(accumulate((haversine_miles(a, b) for a, b in pairwise(points)), initial=0.0))


def _point_along(points: Sequence[GeoPoint], shape_miles: Sequence[float], fraction: float) -> GeoPoint:
    """The point `fraction` of the way along the shape's own length.

    The provider's length and the shape's length differ a little, so the fraction is what carries over.
    """
    target_miles = fraction * shape_miles[-1]
    if target_miles <= 0:
        return points[0]
    if target_miles >= shape_miles[-1]:
        return points[-1]
    # The first point at or past the target. The point before it is strictly behind the target,
    # so duplicate points (zero-length segments) are stepped over, never divided by.
    end = bisect_left(shape_miles, target_miles)
    segment_start_miles = shape_miles[end - 1]
    t = (target_miles - segment_start_miles) / (shape_miles[end] - segment_start_miles)
    a, b = points[end - 1], points[end]
    # (1 - t)*a + t*b lands exactly on a or b at the ends; a + t*(b - a) can miss b by a rounding step.
    return GeoPoint(
        latitude=(1 - t) * a.latitude + t * b.latitude,
        longitude=(1 - t) * a.longitude + t * b.longitude,
    )
