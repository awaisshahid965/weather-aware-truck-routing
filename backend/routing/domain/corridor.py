"""The heatmap around the routes: where its points sit, and their risk at each hour.

It is an indicative weather field, not road risk. A point shows the weather `k` hours after
departure, not when the truck gets there; checkpoints show that.
"""

from collections.abc import Callable, Iterable, Iterator, Sequence
from datetime import UTC, datetime, timedelta

from routing.domain.forecast import sample_at
from routing.domain.geometry import bearing_degrees, destination_point, haversine_miles
from routing.domain.models import GeoPoint, HeatmapFrame, HeatmapPoint, HourlySeries, RouteCandidate
from routing.domain.risk import RiskRules, classify
from routing.domain.sampling import point_locator, spaced_distances

HEATMAP_SPACING_MILES = 25
HEATMAP_LATERAL_MILES = 15
HEATMAP_DEDUPE_MILES = 5
HEATMAP_SPACING_GROWTH = 1.25  # the spacing grows by this factor until the points fit
HEATMAP_HOURS = 48

# How far behind and ahead of a center to look for the road's direction there.
_HEADING_SPAN_MILES = 1


def corridor_points(routes: Sequence[RouteCandidate], *, max_points: int) -> tuple[GeoPoint, ...]:
    """Centers along every route, each with a point to either side: at most `max_points`.

    The spacing starts at `HEATMAP_SPACING_MILES` and grows until the points fit. The same
    routes always give the same points, in the same order.
    """
    if max_points < 1:
        raise ValueError(f'max_points must be >= 1, got {max_points}')
    # Measure each shape once, not once per spacing tried.
    measured = [(route.distance_miles, point_locator(route)) for route in routes]
    longest_miles = max((route.distance_miles for route in routes), default=0.0)
    spacing_miles = float(HEATMAP_SPACING_MILES)
    while True:
        kept = _dedupe(_candidates(measured, spacing_miles), max_points)
        if len(kept) <= max_points:
            return tuple(kept)
        # Every route is down to its endpoints, so a wider spacing would give the same points.
        if spacing_miles >= longest_miles:
            raise ValueError(f'max_points={max_points} is too few even for the route endpoints alone')
        spacing_miles *= HEATMAP_SPACING_GROWTH


def build_frames(
    points: Sequence[GeoPoint],
    series: Sequence[HourlySeries],
    departure_at: datetime,
    load_lb: float,
    rules: RiskRules,
) -> tuple[HeatmapFrame, ...]:
    """Each point's risk at every hour from departure to `HEATMAP_HOURS` later.

    `series[i]` is the forecast at `points[i]`. A missing value at any point and hour raises
    `ForecastGapError`: the plan then fails rather than show unknown weather as calm.
    """
    if len(series) != len(points):
        raise ValueError(f'need one series per point, got {len(series)} for {len(points)} points')
    if departure_at.utcoffset() is None:
        raise ValueError('departure_at must be timezone-aware')
    # Add hours in UTC. On local wall-clock time a frame would be an hour off across a DST change.
    start_at = departure_at.astimezone(UTC)
    frames: list[HeatmapFrame] = []
    for offset_hours in range(HEATMAP_HOURS + 1):
        valid_at = start_at + timedelta(hours=offset_hours)
        risks = (classify(sample_at(forecast, valid_at), load_lb, rules).level for forecast in series)
        frames.append(
            HeatmapFrame(
                offset_hours=offset_hours,
                valid_at=valid_at,
                points=tuple(HeatmapPoint(point, risk) for point, risk in zip(points, risks, strict=True)),
            )
        )
    return tuple(frames)


def _candidates(
    routes: Iterable[tuple[float, Callable[[float], GeoPoint]]], spacing_miles: float
) -> Iterator[GeoPoint]:
    """Route 1's centers, then its laterals, then route 2's, and so on.

    The order is fixed, so dedupe keeps the same points every run. Each route is (length, locator).
    """
    for total_miles, locate in routes:
        laterals: list[GeoPoint] = []
        for distance_miles in spaced_distances(total_miles, spacing_miles):
            center = locate(distance_miles)
            yield center
            heading = bearing_degrees(
                locate(max(distance_miles - _HEADING_SPAN_MILES, 0.0)),
                locate(min(distance_miles + _HEADING_SPAN_MILES, total_miles)),
            )
            laterals.append(destination_point(center, heading - 90, HEATMAP_LATERAL_MILES))
            laterals.append(destination_point(center, heading + 90, HEATMAP_LATERAL_MILES))
        yield from laterals


def _dedupe(candidates: Iterable[GeoPoint], max_points: int) -> list[GeoPoint]:
    """Keep each point unless it is within `HEATMAP_DEDUPE_MILES` of one already kept.

    Stops at `max_points + 1` kept points: one too many already shows they don't fit.
    """
    kept: list[GeoPoint] = []
    for candidate in candidates:
        if all(haversine_miles(candidate, point) >= HEATMAP_DEDUPE_MILES for point in kept):
            kept.append(candidate)
            if len(kept) > max_points:
                break
    return kept
