"""Value objects shared by the routing rules."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from itertools import pairwise

ONE_HOUR = timedelta(hours=1)


class RiskLevel(StrEnum):
    """How dangerous conditions are for a truck. The values are the API's strings."""

    LOW = 'low'
    MODERATE = 'moderate'
    HIGH = 'high'
    SEVERE = 'severe'
    NO_TRAVEL = 'no_travel'

    @property
    def score(self) -> int:
        """0 for LOW up to 4 for NO_TRAVEL. Definition order is risk order."""
        return list(RiskLevel).index(self)


class Condition(StrEnum):
    WIND = 'wind'
    RAIN = 'rain'
    SNOW = 'snow'


def require_non_negative(name: str, value: float) -> None:
    """Raise `ValueError` unless `value` is finite and >= 0.

    NaN compares false against every threshold, so it would quietly classify as
    LOW. Unknown weather must never read as safe, so it is rejected instead.
    """
    if not (math.isfinite(value) and value >= 0):
        raise ValueError(f'{name} must be finite and >= 0, got {value!r}')


@dataclass(frozen=True, slots=True)
class WeatherSample:
    """Weather at one place and hour. Always complete: gaps are caught before one is built."""

    wind_mph: float
    rain_in_per_hour: float
    snow_in_per_hour: float

    def __post_init__(self) -> None:
        require_non_negative('wind_mph', self.wind_mph)
        require_non_negative('rain_in_per_hour', self.rain_in_per_hour)
        require_non_negative('snow_in_per_hour', self.snow_in_per_hour)


@dataclass(frozen=True, slots=True)
class HourlySeries:
    """A provider's hourly forecast at one place.

    Values stay as the provider sent them, gaps included. A gap matters only at an hour
    someone reads, so `sample_at` judges each value when it is used.
    """

    hours: tuple[datetime, ...]  # aware UTC, ascending, 1 h apart
    wind_mph: tuple[float | None, ...]
    rain_in_per_hour: tuple[float | None, ...]  # rain + showers
    snow_in_per_hour: tuple[float | None, ...]

    def __post_init__(self) -> None:
        for name, values in (
            ('wind_mph', self.wind_mph),
            ('rain_in_per_hour', self.rain_in_per_hour),
            ('snow_in_per_hour', self.snow_in_per_hour),
        ):
            if len(values) != len(self.hours):
                raise ValueError(f'{name} has {len(values)} values for {len(self.hours)} hours')
        for hour in self.hours:
            # A naive hour has no offset, so it fails here too.
            if hour.utcoffset() != timedelta(0):
                raise ValueError(f'hours must be aware UTC, got {hour.isoformat()}')
        for earlier, later in pairwise(self.hours):
            if later - earlier != ONE_HOUR:
                raise ValueError(f'hours must be 1 h apart, got {later.isoformat()} after {earlier.isoformat()}')


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    level: RiskLevel
    drivers: tuple[Condition, ...]  # conditions tied at `level`; empty when LOW


@dataclass(frozen=True, slots=True)
class GeoPoint:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        # NaN fails these comparisons too, so it is rejected with the out-of-range values.
        if not -90 <= self.latitude <= 90:
            raise ValueError(f'latitude must be within [-90, 90], got {self.latitude!r}')
        if not -180 <= self.longitude <= 180:
            raise ValueError(f'longitude must be within [-180, 180], got {self.longitude!r}')


@dataclass(frozen=True, slots=True)
class PlaceMatch:
    """A place a search found. It always has coordinates: a route plan uses them, never the label."""

    place_id: str  # opaque provider id; the API calls it `id`
    label: str
    point: GeoPoint

    def __post_init__(self) -> None:
        if not self.place_id.strip():
            raise ValueError('place_id must not be blank')
        if not self.label.strip():
            raise ValueError('label must not be blank')


@dataclass(frozen=True, slots=True)
class RouteSection:
    """One provider section. Its length is the distance that counts; the shape only places points along it."""

    points: tuple[GeoPoint, ...]  # decoded shape, at least 2 points
    length_miles: float  # from the provider, > 0
    duration_seconds: float  # from the provider, >= 0

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError(f'a section needs at least 2 points, got {len(self.points)}')
        # Sampling divides by the length to find how far into the section a mile falls.
        if not (math.isfinite(self.length_miles) and self.length_miles > 0):
            raise ValueError(f'length_miles must be finite and > 0, got {self.length_miles!r}')
        require_non_negative('duration_seconds', self.duration_seconds)


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    provider_index: int  # 0-based provider order
    sections: tuple[RouteSection, ...]

    def __post_init__(self) -> None:
        if self.provider_index < 0:
            raise ValueError(f'provider_index must be >= 0, got {self.provider_index}')
        if not self.sections:
            raise ValueError('a route needs at least 1 section')

    # fsum gives one correctly rounded total, whatever the order. Sampling relies on that
    # to put the destination exactly at `distance_miles` and `duration_seconds`.
    @property
    def distance_miles(self) -> float:
        return math.fsum(section.length_miles for section in self.sections)

    @property
    def duration_seconds(self) -> float:
        return math.fsum(section.duration_seconds for section in self.sections)


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """A place on a route where the weather is checked, at the time the truck gets there."""

    distance_from_start_miles: float
    point: GeoPoint
    eta_at: datetime  # aware UTC
    cell_miles: float  # the stretch of road this checkpoint's weather stands for


@dataclass(frozen=True, slots=True)
class AssessedCheckpoint:
    checkpoint: Checkpoint
    weather: WeatherSample
    risk: RiskAssessment


@dataclass(frozen=True, slots=True)
class RouteSummary:
    """How much of a route sits at each risky level. Level miles are exclusive: a No Travel cell is not Severe."""

    no_travel_miles: float
    severe_miles: float
    high_miles: float
    average_risk: float  # mile-weighted mean score, 0 to 4; unrounded, because ranking compares it
    worst_risk: RiskLevel

    def __post_init__(self) -> None:
        # Ranking compares these. NaN fails every comparison, so the winner would depend on input order.
        require_non_negative('no_travel_miles', self.no_travel_miles)
        require_non_negative('severe_miles', self.severe_miles)
        require_non_negative('high_miles', self.high_miles)
        require_non_negative('average_risk', self.average_risk)


@dataclass(frozen=True, slots=True)
class RankInput:
    """What the recommendation needs to know about one route."""

    provider_index: int  # 0-based provider order; breaks a full tie
    duration_seconds: float
    summary: RouteSummary

    def __post_init__(self) -> None:
        if self.provider_index < 0:
            raise ValueError(f'provider_index must be >= 0, got {self.provider_index}')
        require_non_negative('duration_seconds', self.duration_seconds)


@dataclass(frozen=True, slots=True)
class Recommendation:
    provider_index: int | None  # None when every route has No Travel miles


@dataclass(frozen=True, slots=True)
class HeatmapPoint:
    point: GeoPoint
    risk: RiskLevel


@dataclass(frozen=True, slots=True)
class HeatmapFrame:
    """The risk around the routes at one hour. Not where the truck is then: checkpoints say that."""

    offset_hours: int  # 0..48
    valid_at: datetime  # departure_at + offset, aware UTC
    points: tuple[HeatmapPoint, ...]
