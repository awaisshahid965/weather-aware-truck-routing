"""Where hourly forecasts come from."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from routing.domain.models import GeoPoint, HourlySeries


class ForecastProvider(Protocol):
    """Hourly wind, rain and snow for many points.

    Raises `ForecastRangeError` when the forecast does not reach the whole window: the
    provider refuses it, or its values stop before the window ends. Raises `ProviderError`
    for any failure, or `ProviderTimeoutError` when the provider runs out of time.
    """

    @property
    def max_lead_hours(self) -> int:
        """A conservative bound on how many hours past now the forecast reaches.

        Callers check their window against it before asking. It is not a promise, so
        `hourly` can still raise `ForecastRangeError`.
        """
        ...

    def hourly(self, points: Sequence[GeoPoint], start_at: datetime, end_at: datetime) -> list[HourlySeries]:
        """One series per point, in the order of `points`.

        Each series holds every hour `sample_at` reads for a moment from `start_at` to `end_at`:
        the first hour at or after `start_at`, through the first hour at or after `end_at`.
        Values the provider lacks stay None; `sample_at` decides whether they matter.
        """
        ...
