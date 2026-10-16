"""Services that stand in for the composition root's in the HTTP tests."""

from datetime import UTC, datetime
from itertools import pairwise

from routing.domain.geometry import haversine_miles
from routing.domain.models import GeoPoint, RouteCandidate, RouteSection
from routing.services.plan_trip import PlanTripInput, PlanTripService, TripPlan
from tests.services.fakes import FakeForecastProvider, FakeRiskRulesSource, FakeRouteProvider

# Sara's trip: Pittsburgh to Cleveland, Tue 2026-11-17 at 8:00 AM EST, planned the night before.
NOW = datetime(2026, 11, 17, 1, 0, tzinfo=UTC)
DEPARTURE_AT = datetime(2026, 11, 17, 13, 0, tzinfo=UTC)
PITTSBURGH = GeoPoint(40.4406, -79.9959)
CLEVELAND = GeoPoint(41.4993, -81.6944)
NEW_CASTLE = GeoPoint(41.0034, -80.3470)
AKRON = GeoPoint(41.0814, -81.5190)
NORTHERN = GeoPoint(41.40, -80.60)


def _route(provider_index: int, *waypoints: GeoPoint, mph: float) -> RouteCandidate:
    """One straight section per leg, as long as its shape, driven at `mph`."""
    sections = tuple(
        RouteSection((a, b), length_miles=haversine_miles(a, b), duration_seconds=haversine_miles(a, b) / mph * 3600)
        for a, b in pairwise(waypoints)
    )
    return RouteCandidate(provider_index=provider_index, sections=sections)


# Turnpike, Akron, Northern. Akron is the fastest, so calm weather recommends it.
ROUTES = (
    _route(0, PITTSBURGH, NEW_CASTLE, CLEVELAND, mph=55),
    _route(1, PITTSBURGH, AKRON, CLEVELAND, mph=65),
    _route(2, PITTSBURGH, NORTHERN, CLEVELAND, mph=50),
)


def plan_trip_service(
    route_provider: FakeRouteProvider | None = None, forecast: FakeForecastProvider | None = None
) -> PlanTripService:
    """The real service over port fakes, with the clock fixed at `NOW`."""
    return PlanTripService(
        route_provider or FakeRouteProvider(ROUTES),
        forecast or FakeForecastProvider(),
        FakeRiskRulesSource(),
        clock=lambda: NOW,
        max_route_miles=2_500,
        max_heatmap_points=90,
        forecast_dedupe_miles=3,
    )


class FailingPlanTripService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def run(self, request: PlanTripInput) -> TripPlan:
        raise self.error
