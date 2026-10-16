"""Plan a trip: three routes, the risk at each checkpoint's ETA, a recommendation, and the heatmap.

The service talks only to ports, so tests run it with fakes. One plan reads the clock once,
fetches every forecast in one call, and reads the risk rules once. A plan is never partial:
any gap in the forecast fails the whole plan.
"""

import logging
import math
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from routing.domain.corridor import HEATMAP_HOURS, build_frames, corridor_points
from routing.domain.errors import ForecastGapError
from routing.domain.forecast import sample_at
from routing.domain.geometry import haversine_miles
from routing.domain.models import (
    ONE_HOUR,
    AssessedCheckpoint,
    Checkpoint,
    GeoPoint,
    HeatmapFrame,
    HourlySeries,
    RankInput,
    RouteCandidate,
    RouteSummary,
)
from routing.domain.ranking import recommend, summarize
from routing.domain.risk import RiskRules, classify
from routing.domain.sampling import CHECKPOINT_INTERVALS_MILES, build_checkpoints
from routing.ports.errors import ForecastRangeError, ProviderError, ProviderTimeoutError
from routing.ports.forecast_provider import ForecastProvider
from routing.ports.risk_rules import RiskRulesSource
from routing.ports.route_provider import RouteProvider
from routing.services.errors import (
    ForecastUnavailableError,
    InputValidationError,
    InsufficientRoutesError,
    UpstreamError,
    UpstreamTimeoutError,
)

logger = logging.getLogger(__name__)

ROUTES_PER_PLAN = 3
MIN_TRIP_MILES = 0.1
ESTIMATE_NOTICE = 'Forecast risk is an estimate, not a road-closure or dispatch clearance.'
NO_TRAVEL_NOTICE = 'No Travel: every route has No Travel conditions, so no route is recommended.'


@dataclass(frozen=True, slots=True)
class Place:
    label: str
    point: GeoPoint


@dataclass(frozen=True, slots=True)
class PlanTripInput:
    origin: Place
    destination: Place
    departure_at: datetime  # aware UTC, authoritative
    departure_time_zone: str  # display only
    load_weight_lb: float
    checkpoint_interval_miles: int


@dataclass(frozen=True, slots=True)
class PlannedRoute:
    candidate: RouteCandidate
    checkpoints: tuple[AssessedCheckpoint, ...]
    summary: RouteSummary
    eta_at: datetime


@dataclass(frozen=True, slots=True)
class TripPlan:
    generated_at: datetime
    request: PlanTripInput
    routes: tuple[PlannedRoute, ...]  # provider order
    recommended_index: int | None  # into `routes`; None when every route has No Travel miles
    heatmap: tuple[HeatmapFrame, ...]
    notices: tuple[str, ...]
    rules_version: str  # which rules produced this plan


class PlanTripService:
    """Runs the whole plan for one request. Every limit arrives through the constructor."""

    def __init__(
        self,
        routes: RouteProvider,
        forecast: ForecastProvider,
        risk_rules: RiskRulesSource,
        *,
        clock: Callable[[], datetime],
        max_route_miles: float,
        max_heatmap_points: int,
        forecast_dedupe_miles: float,
    ) -> None:
        """`clock` returns aware UTC "now". Tests pass a fixed one."""
        if not (math.isfinite(max_route_miles) and max_route_miles > 0):
            raise ValueError(f'max_route_miles must be finite and > 0, got {max_route_miles!r}')
        if max_heatmap_points < 1:
            raise ValueError(f'max_heatmap_points must be >= 1, got {max_heatmap_points}')
        if not (math.isfinite(forecast_dedupe_miles) and forecast_dedupe_miles >= 0):
            raise ValueError(f'forecast_dedupe_miles must be finite and >= 0, got {forecast_dedupe_miles!r}')
        self._routes = routes
        self._forecast = forecast
        self._risk_rules = risk_rules
        self._clock = clock
        self._max_route_miles = max_route_miles
        self._max_heatmap_points = max_heatmap_points
        self._forecast_dedupe_miles = forecast_dedupe_miles

    def run(self, request: PlanTripInput) -> TripPlan:
        """The full plan, or a service error.

        `RiskRulesUnavailableError` passes through untranslated: bad rules are a server fault,
        and the deploy check rejects them before any request arrives.
        """
        started = time.perf_counter()
        now = self._clock()
        self._validate(request, now)
        routes = self._find_routes(request)
        checkpoints = [
            build_checkpoints(route, request.checkpoint_interval_miles, request.departure_at) for route in routes
        ]
        heatmap_points = corridor_points(routes, max_points=self._max_heatmap_points)
        # Checkpoints first, so they keep their own forecast and heatmap points share theirs.
        checkpoint_points = [checkpoint.point for route_checkpoints in checkpoints for checkpoint in route_checkpoints]
        fetch_points, slot_of = _share_forecasts([*checkpoint_points, *heatmap_points], self._forecast_dedupe_miles)
        series = self._fetch(fetch_points, *_forecast_window(request.departure_at, checkpoints))
        forecast_of = {point: series[slot] for point, slot in slot_of.items()}
        rules = self._risk_rules.current()  # once: a rule change mid-plan must not mix two rule sets
        load_lb = request.load_weight_lb
        try:
            planned = tuple(
                _plan_route(route, route_checkpoints, forecast_of, load_lb, rules)
                for route, route_checkpoints in zip(routes, checkpoints, strict=True)
            )
            heatmap = build_frames(
                heatmap_points, [forecast_of[point] for point in heatmap_points], request.departure_at, load_lb, rules
            )
        except ForecastGapError as exc:
            # Unknown weather never reads as Low, so there is no plan from partial data.
            raise ForecastUnavailableError(str(exc)) from exc
        recommended_index = _recommended_index(planned)
        logger.info(
            'trip planned',
            extra={
                'rules_version': rules.version,
                'routes': len(planned),
                'checkpoints': len(checkpoint_points),
                'forecast_points': len(fetch_points),
                'elapsed_ms': round((time.perf_counter() - started) * 1000),
            },
        )
        return TripPlan(
            generated_at=now,
            request=request,
            routes=planned,
            recommended_index=recommended_index,
            heatmap=heatmap,
            notices=_notices(recommended_index),
            rules_version=rules.version,
        )

    def _validate(self, request: PlanTripInput, now: datetime) -> None:
        """The business rules on the input, checked before any provider call."""
        departure_at = request.departure_at
        if departure_at.utcoffset() is None:
            raise InputValidationError('departureAt', 'must include its UTC offset')
        if departure_at <= now:
            raise InputValidationError('departureAt', 'must be in the future')
        # Conservative, not a promise: `_fetch` still turns the provider's own refusal into this error.
        lead_hours = self._forecast.max_lead_hours
        # A difference, not a sum: adding 48 h to a departure late in year 9999 overflows.
        if departure_at - now > timedelta(hours=lead_hours - HEATMAP_HOURS):
            raise InputValidationError(
                'departureAt',
                f'must be at most {lead_hours - HEATMAP_HOURS} hours from now, '
                f'so the {HEATMAP_HOURS}-hour heatmap stays inside the forecast',
            )
        if haversine_miles(request.origin.point, request.destination.point) < MIN_TRIP_MILES:
            raise InputValidationError('destination', f'must be at least {MIN_TRIP_MILES} miles from the origin')
        if not (math.isfinite(request.load_weight_lb) and request.load_weight_lb >= 0):
            raise InputValidationError('loadWeightLb', 'must be a finite number of pounds, 0 or more')
        if request.checkpoint_interval_miles not in CHECKPOINT_INTERVALS_MILES:
            raise InputValidationError(
                'checkpointIntervalMiles', f'must be one of {sorted(CHECKPOINT_INTERVALS_MILES)}'
            )

    def _find_routes(self, request: PlanTripInput) -> tuple[RouteCandidate, ...]:
        """The first 3 routes in provider order. Each is checked against the length cap before any weather call."""
        with _provider_errors('routing'):
            found = self._routes.find_routes(request.origin.point, request.destination.point, request.departure_at)
        if len(found) < ROUTES_PER_PLAN:
            raise InsufficientRoutesError(len(found))
        routes = tuple(found[:ROUTES_PER_PLAN])
        for number, route in enumerate(routes, start=1):
            if route.distance_miles > self._max_route_miles:
                raise InputValidationError(
                    'destination',
                    f'is too far: route {number} is {route.distance_miles:,.1f} miles, '
                    f'over the {self._max_route_miles:,.0f}-mile limit',
                )
        return routes

    def _fetch(self, points: Sequence[GeoPoint], start_at: datetime, end_at: datetime) -> list[HourlySeries]:
        """Every forecast the plan reads, in one call."""
        try:
            with _provider_errors('forecast'):
                series = self._forecast.hourly(points, start_at, end_at)
        except ForecastRangeError as exc:
            # Not a ProviderError: the provider answered, but the trip reaches past its forecast.
            raise InputValidationError(
                'departureAt', 'is too far ahead: the forecast does not reach this trip'
            ) from exc
        # Series pair with points by position, so a short list would hand points the wrong weather.
        if len(series) != len(points):
            raise UpstreamError(f'the forecast provider returned {len(series)} series for {len(points)} points')
        return series


@contextmanager
def _provider_errors(provider: str) -> Iterator[None]:
    """Turn a port's provider errors into service errors. The original stays as `__cause__` for the logs."""
    try:
        yield
    except ProviderTimeoutError as exc:
        raise UpstreamTimeoutError(f'the {provider} provider did not answer in time') from exc
    except ProviderError as exc:
        raise UpstreamError(f'the {provider} provider failed') from exc


def _share_forecasts(points: Iterable[GeoPoint], dedupe_miles: float) -> tuple[list[GeoPoint], dict[GeoPoint, int]]:
    """The points to fetch, and which of them each point reads.

    Greedy, in input order: a point within `dedupe_miles` of a kept point reads the nearest
    kept point's forecast. Identical points always share. O(n²), fine at a few hundred points.
    """
    kept: list[GeoPoint] = []
    slot_of: dict[GeoPoint, int] = {}
    for point in points:
        if point in slot_of:
            continue
        distances = [haversine_miles(point, other) for other in kept]
        nearest = min(range(len(kept)), key=distances.__getitem__, default=None)
        if nearest is not None and distances[nearest] < dedupe_miles:
            slot_of[point] = nearest
        else:
            slot_of[point] = len(kept)
            kept.append(point)
    return kept, slot_of


def _forecast_window(departure_at: datetime, checkpoints: Iterable[Sequence[Checkpoint]]) -> tuple[datetime, datetime]:
    """Whole hours covering everything the plan reads: checkpoints up to the last ETA, the heatmap to +48 h."""
    last_eta = max(checkpoint.eta_at for route_checkpoints in checkpoints for checkpoint in route_checkpoints)
    heatmap_end = departure_at + timedelta(hours=HEATMAP_HOURS)
    return _floor_hour(departure_at), _ceil_hour(max(last_eta, heatmap_end))


def _floor_hour(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _ceil_hour(moment: datetime) -> datetime:
    floor = _floor_hour(moment)
    return floor if floor == moment else floor + ONE_HOUR


def _plan_route(
    route: RouteCandidate,
    checkpoints: Sequence[Checkpoint],
    forecast_of: dict[GeoPoint, HourlySeries],
    load_lb: float,
    rules: RiskRules,
) -> PlannedRoute:
    """Each checkpoint classified on the weather at its own ETA, then the route's summary."""
    assessed: list[AssessedCheckpoint] = []
    for checkpoint in checkpoints:
        weather = sample_at(forecast_of[checkpoint.point], checkpoint.eta_at)
        assessed.append(AssessedCheckpoint(checkpoint, weather, classify(weather, load_lb, rules)))
    return PlannedRoute(
        candidate=route,
        checkpoints=tuple(assessed),
        summary=summarize(assessed, route.distance_miles),
        eta_at=checkpoints[-1].eta_at,  # the destination is always the last checkpoint
    )


def _recommended_index(routes: Sequence[PlannedRoute]) -> int | None:
    # Position is provider order: routes arrive in that order and only the first 3 are kept.
    ranked = [
        RankInput(provider_index=position, duration_seconds=route.candidate.duration_seconds, summary=route.summary)
        for position, route in enumerate(routes)
    ]
    return recommend(ranked).provider_index


def _notices(recommended_index: int | None) -> tuple[str, ...]:
    if recommended_index is None:
        return (NO_TRAVEL_NOTICE, ESTIMATE_NOTICE)
    return (ESTIMATE_NOTICE,)
