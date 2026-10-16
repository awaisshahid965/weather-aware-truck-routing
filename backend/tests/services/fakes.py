"""Fakes for the ports the services use. Each one records how it was called."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from routing.domain.models import ONE_HOUR, GeoPoint, HourlySeries, PlaceMatch, RouteCandidate
from routing.domain.risk import RiskRules
from tests.spec_rules import SPEC_RULES

# Wind mph, rain in/h and snow in/h at one point and hour. None is a gap, as a provider sends it.
HourValues = tuple[float | None, float | None, float | None]
ValuesAt = Callable[[GeoPoint, datetime], HourValues]

CALM: HourValues = (0.0, 0.0, 0.0)


def calm(point: GeoPoint, hour: datetime) -> HourValues:
    return CALM


class FakeRouteProvider:
    def __init__(self, routes: Sequence[RouteCandidate], *, error: Exception | None = None) -> None:
        self.routes = list(routes)
        self.error = error
        self.calls: list[tuple[GeoPoint, GeoPoint, datetime]] = []

    def find_routes(self, origin: GeoPoint, destination: GeoPoint, departure_at: datetime) -> list[RouteCandidate]:
        self.calls.append((origin, destination, departure_at))
        if self.error is not None:
            raise self.error
        return list(self.routes)


@dataclass(frozen=True, slots=True)
class ForecastCall:
    points: tuple[GeoPoint, ...]
    start_at: datetime
    end_at: datetime


class FakeForecastProvider:
    """Series built hour by hour from `values_at(point, hour)`.

    Like the real provider, a series runs from the first hour at or after `start_at` through the
    first hour at or after `end_at`. `ends_at` cuts every series short at that hour.
    """

    def __init__(
        self,
        values_at: ValuesAt = calm,
        *,
        max_lead_hours: int = 354,  # the Open-Meteo adapter's bound
        ends_at: datetime | None = None,
        error: Exception | None = None,
    ) -> None:
        self.values_at = values_at
        self.max_lead_hours = max_lead_hours
        self.ends_at = ends_at
        self.error = error
        self.calls: list[ForecastCall] = []

    def hourly(self, points: Sequence[GeoPoint], start_at: datetime, end_at: datetime) -> list[HourlySeries]:
        self.calls.append(ForecastCall(tuple(points), start_at, end_at))
        if self.error is not None:
            raise self.error
        last_hour = _hour_at_or_after(end_at)
        if self.ends_at is not None:
            last_hour = min(last_hour, self.ends_at)
        hours: list[datetime] = []
        hour = _hour_at_or_after(start_at)
        while hour <= last_hour:
            hours.append(hour)
            hour += ONE_HOUR
        return [self._series(point, hours) for point in points]

    def _series(self, point: GeoPoint, hours: Sequence[datetime]) -> HourlySeries:
        values = [self.values_at(point, hour) for hour in hours]
        return HourlySeries(
            hours=tuple(hours),
            wind_mph=tuple(wind for wind, _, _ in values),
            rain_in_per_hour=tuple(rain for _, rain, _ in values),
            snow_in_per_hour=tuple(snow for _, _, snow in values),
        )


class FakeGeocoder:
    """Returns `matches` for every query, cut to the limit asked for, as the real adapter does."""

    def __init__(self, matches: Sequence[PlaceMatch] = (), *, error: Exception | None = None) -> None:
        self.matches = list(matches)
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, limit: int) -> list[PlaceMatch]:
        self.calls.append((query, limit))
        if self.error is not None:
            raise self.error
        return self.matches[:limit]


class FakeRiskRulesSource:
    def __init__(self, rules: RiskRules = SPEC_RULES) -> None:
        self.rules = rules
        self.calls = 0

    def current(self) -> RiskRules:
        self.calls += 1
        return self.rules


def _hour_at_or_after(moment: datetime) -> datetime:
    utc = moment.astimezone(UTC)
    hour = utc.replace(minute=0, second=0, microsecond=0)
    return hour if hour == utc else hour + ONE_HOUR
