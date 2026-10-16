"""Where route alternatives come from."""

from datetime import datetime
from typing import Protocol

from routing.domain.models import GeoPoint, RouteCandidate


class RouteProvider(Protocol):
    """Finds a truck route plus up to two alternatives.

    Returns 0 to 3 distinct routes in provider order, numbered 0, 1, 2 by that order. It never
    invents a route to make up a shortfall; what too few means is the caller's decision.
    Raises `ProviderError`, or `ProviderTimeoutError` when the provider runs out of time.
    """

    def find_routes(self, origin: GeoPoint, destination: GeoPoint, departure_at: datetime) -> list[RouteCandidate]: ...
