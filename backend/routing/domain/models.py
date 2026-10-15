"""Value objects shared by the routing rules."""

import math
from dataclasses import dataclass
from enum import StrEnum


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
class RiskAssessment:
    level: RiskLevel
    drivers: tuple[Condition, ...]  # conditions tied at `level`; empty when LOW
