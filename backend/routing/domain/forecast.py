"""Read the weather for one moment from an hourly forecast.

Rain and snow at each hour are totals over the hour that ends there. The hour that holds a
moment is the first one ending at or after it, so that hour is read. Wind is read from the
same hour, so one moment always reads one row of the forecast.
"""

import math
from bisect import bisect_left
from datetime import UTC, datetime

from routing.domain.errors import ForecastGapError
from routing.domain.models import ONE_HOUR, HourlySeries, WeatherSample


def sample_at(series: HourlySeries, at: datetime) -> WeatherSample:
    """The weather in the hour that holds `at`: the first hour at or after it.

    Raises `ForecastGapError` when the series does not reach `at`, or when a value at that hour
    is missing, NaN or negative. Unknown weather must never read as calm.
    """
    if at.utcoffset() is None:
        raise ValueError('at must be timezone-aware')
    index = bisect_left(series.hours, at)
    # An hour that ends 1 h or more after `at` totals a later hour, not the one `at` falls in.
    if index == len(series.hours) or series.hours[index] - at >= ONE_HOUR:
        raise ForecastGapError(f'the forecast does not cover {_utc(at)}')
    hour = series.hours[index]
    return WeatherSample(
        wind_mph=_usable('wind_mph', series.wind_mph[index], hour),
        rain_in_per_hour=_usable('rain_in_per_hour', series.rain_in_per_hour[index], hour),
        snow_in_per_hour=_usable('snow_in_per_hour', series.snow_in_per_hour[index], hour),
    )


def _usable(name: str, value: float | None, hour: datetime) -> float:
    if value is None or not (math.isfinite(value) and value >= 0):
        raise ForecastGapError(f'{name} at {_utc(hour)} is not a usable forecast value: {value!r}')
    return value


def _utc(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace('+00:00', 'Z')
