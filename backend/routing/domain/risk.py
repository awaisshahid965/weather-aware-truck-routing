"""Classify weather and load into a risk level.

The rule values are data, passed in as `RiskRules`. This module holds none of
them, so a new rule set needs no code change.
"""

from dataclasses import dataclass
from itertools import pairwise

from routing.domain.models import Condition, RiskAssessment, RiskLevel, WeatherSample, require_non_negative

# One cut per level above LOW.
_LEVELS_ABOVE_LOW = tuple(RiskLevel)[1:]


@dataclass(frozen=True, slots=True)
class Cut:
    """The lower edge of one risk level."""

    at: float
    inclusive: bool  # True: value >= at moves up. False: value > at moves up.

    def is_crossed_by(self, value: float) -> bool:
        return value >= self.at if self.inclusive else value > self.at


@dataclass(frozen=True, slots=True)
class LoadOverride:
    """A heavy load raises one base wind level to a higher one."""

    base_wind_level: RiskLevel
    load_above_lb: float  # strictly greater than
    result: RiskLevel

    def __post_init__(self) -> None:
        require_non_negative('load_above_lb', self.load_above_lb)
        if self.result.score <= self.base_wind_level.score:
            raise ValueError(
                f'a load override must raise the level; {self.base_wind_level} wind cannot become {self.result}'
            )


@dataclass(frozen=True, slots=True)
class RiskRules:
    """One versioned rule set. Every source (file now, database later) gets these checks."""

    version: str
    wind_cuts: tuple[Cut, ...]
    rain_cuts: tuple[Cut, ...]
    snow_cuts: tuple[Cut, ...]
    load_overrides: tuple[LoadOverride, ...]

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError('version must not be blank')
        _check_cuts('wind_cuts', self.wind_cuts)
        _check_cuts('rain_cuts', self.rain_cuts)
        _check_cuts('snow_cuts', self.snow_cuts)
        _check_load_overrides(self.load_overrides)


def _check_cuts(name: str, cuts: tuple[Cut, ...]) -> None:
    if len(cuts) != len(_LEVELS_ABOVE_LOW):
        raise ValueError(f'{name} needs {len(_LEVELS_ABOVE_LOW)} cuts, one per level above low; got {len(cuts)}')
    for index, cut in enumerate(cuts):
        require_non_negative(f'{name}[{index}]', cut.at)
    for lower, upper in pairwise(cuts):
        if upper.at <= lower.at:
            raise ValueError(f'{name} must be strictly ascending; got {upper.at} after {lower.at}')


def _check_load_overrides(overrides: tuple[LoadOverride, ...]) -> None:
    # A second override for the same base level would be ambiguous: which one wins?
    seen: set[RiskLevel] = set()
    for override in overrides:
        if override.base_wind_level in seen:
            raise ValueError(f'load_overrides has more than one rule for {override.base_wind_level} wind')
        seen.add(override.base_wind_level)


def level_for(value: float, cuts: tuple[Cut, ...]) -> RiskLevel:
    """The level whose band holds `value`. Cuts are ascending, so the walk stops at the first one not crossed."""
    require_non_negative('value', value)
    level = RiskLevel.LOW
    for cut, next_level in zip(cuts, _LEVELS_ABOVE_LOW, strict=True):
        if not cut.is_crossed_by(value):
            break
        level = next_level
    return level


def wind_level(wind_mph: float, load_lb: float, rules: RiskRules) -> RiskLevel:
    """The base wind level, raised by a matching load override."""
    require_non_negative('load_lb', load_lb)
    base = level_for(wind_mph, rules.wind_cuts)
    for override in rules.load_overrides:
        if override.base_wind_level is base and load_lb > override.load_above_lb:
            return override.result
    return base


def classify(sample: WeatherSample, load_lb: float, rules: RiskRules) -> RiskAssessment:
    """The highest of the wind, rain and snow levels, and every condition tied at it."""
    # Insertion order is the drivers' order: wind, rain, snow.
    levels = {
        Condition.WIND: wind_level(sample.wind_mph, load_lb, rules),
        Condition.RAIN: level_for(sample.rain_in_per_hour, rules.rain_cuts),
        Condition.SNOW: level_for(sample.snow_in_per_hour, rules.snow_cuts),
    }
    # Compare scores, not the enum: StrEnum compares as text, and 'high' < 'low'.
    top = max(levels.values(), key=lambda level: level.score)
    if top is RiskLevel.LOW:
        return RiskAssessment(top, drivers=())
    return RiskAssessment(top, drivers=tuple(condition for condition, level in levels.items() if level is top))
