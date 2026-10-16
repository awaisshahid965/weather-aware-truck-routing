"""Hourly wind, rain and snow from Open-Meteo.

Open-Meteo answers many points in one request: an object for one point, a list for more. It
snaps each point to its own grid and returns the snapped coordinates, so results are matched
to points by position, never by coordinates. Units come back in `hourly_units` and are
checked, never assumed.

Numbers are parsed as Decimal. Rain is `rain + showers`, and in binary floats 0.09 + 0.01 is
just under 0.10, a risk threshold, so a float sum would read one level too low.

A window past Open-Meteo's forecast fails in one of two ways: it refuses the window with
400, or the last hours come back with no value at all. Both raise `ForecastRangeError`, so
a departure too far ahead never looks like a provider failure.
"""

import logging
import math
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from routing.adapters.provider_http import get_json
from routing.domain.models import ONE_HOUR, GeoPoint, HourlySeries
from routing.ports.errors import ForecastRangeError, ProviderError, ProviderTimeoutError

logger = logging.getLogger(__name__)

FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
# A conservative bound, not a promise. Open-Meteo forecasts 16 days (`forecast_days`,
# https://open-meteo.com/en/docs), counted in whole UTC days from today. On 2026-10-16 the last
# 5 hours of day 16 came back null, so data ended at 18:00 UTC on day 16. 14 days 18 hours
# stays inside that from any time of day. The provider can still fall short; `hourly` then
# raises ForecastRangeError.
MAX_LEAD_HOURS = 14 * 24 + 18

# How many of each unit make one mph or one inch, keyed by Open-Meteo's `hourly_units` strings.
# Each factor is exact by definition: 1 mi = 1.609344 km and 1 in = 25.4 mm.
UNITS_PER_MPH = {'mp/h': Decimal(1), 'km/h': Decimal('1.609344'), 'm/s': Decimal('0.44704')}
UNITS_PER_INCH = {'inch': Decimal(1), 'mm': Decimal('25.4'), 'cm': Decimal('2.54')}

# Each hourly variable requested, and the table that converts it.
VARIABLES = (
    ('wind_speed_10m', UNITS_PER_MPH),
    ('rain', UNITS_PER_INCH),
    ('showers', UNITS_PER_INCH),
    ('snowfall', UNITS_PER_INCH),
)


class OpenMeteoForecast:
    """Implements `ForecastProvider`."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        batch_size: int,
        deadline_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """`clock` and `sleep` let tests run the shared deadline without waiting."""
        if batch_size < 1:
            raise ValueError(f'batch_size must be >= 1, got {batch_size}')
        if not deadline_seconds > 0:
            raise ValueError(f'deadline_seconds must be > 0, got {deadline_seconds!r}')
        self._client = client
        self._batch_size = batch_size
        self._deadline_seconds = deadline_seconds
        self._clock = clock
        self._sleep = sleep

    @property
    def max_lead_hours(self) -> int:
        return MAX_LEAD_HOURS

    def hourly(self, points: Sequence[GeoPoint], start_at: datetime, end_at: datetime) -> list[HourlySeries]:
        if start_at.utcoffset() is None or end_at.utcoffset() is None:
            raise ValueError('start_at and end_at must be timezone-aware')
        if start_at > end_at:
            raise ValueError(f'start_at must not be after end_at; got {start_at.isoformat()} > {end_at.isoformat()}')
        window = (_hour_at_or_after(start_at), _hour_at_or_after(end_at))

        # One deadline for every batch. One each would let ten batches take ten times as long.
        ends_at = self._clock() + self._deadline_seconds
        series: list[HourlySeries] = []
        for first in range(0, len(points), self._batch_size):
            batch = points[first : first + self._batch_size]
            remaining_seconds = ends_at - self._clock()
            if remaining_seconds <= 0:
                raise ProviderTimeoutError(f'the forecast did not finish within {self._deadline_seconds:g} s')
            document = get_json(
                self._client,
                FORECAST_URL,
                _params(batch, window),
                deadline_seconds=remaining_seconds,
                parse_float=Decimal,
                explain_rejection=lambda status, body: _range_refusal(status, body, window),
                clock=self._clock,
                sleep=self._sleep,
            )
            try:
                locations = _locations(document, len(batch))
                series.extend(
                    _series(location, window, f'locations[{index}]') for index, location in enumerate(locations)
                )
            except ValueError as exc:
                raise ProviderError(f'Open-Meteo returned a forecast we cannot use: {exc}') from exc
            logger.info(
                'open-meteo batch fetched',
                extra={'points': len(batch), 'generationtime_ms': _generation_ms(locations)},
            )
        return series


def _hour_at_or_after(moment: datetime) -> datetime:
    utc = moment.astimezone(UTC)
    hour = utc.replace(minute=0, second=0, microsecond=0)
    return hour if hour == utc else hour + ONE_HOUR


def _params(points: Sequence[GeoPoint], window: tuple[datetime, datetime]) -> dict[str, str]:
    first_hour, last_hour = window
    return {
        # 4 decimals is about 11 m: far finer than the forecast grid, and it keeps the URL short.
        'latitude': ','.join(f'{point.latitude:.4f}' for point in points),
        'longitude': ','.join(f'{point.longitude:.4f}' for point in points),
        'hourly': ','.join(name for name, _ in VARIABLES),
        'wind_speed_unit': 'mph',
        'precipitation_unit': 'inch',
        'timeformat': 'unixtime',
        'timezone': 'GMT',
        # Both ends are inclusive and read in `timezone`.
        'start_hour': first_hour.strftime('%Y-%m-%dT%H:%M'),
        'end_hour': last_hour.strftime('%Y-%m-%dT%H:%M'),
    }


def _range_refusal(status: int, body: object, window: tuple[datetime, datetime]) -> ForecastRangeError | None:
    # Open-Meteo refuses hours outside its range with 400 and a reason such as
    # "Parameter 'end_hour' is out of allowed range from 2026-07-15 to 2026-10-31".
    # Any other refusal stays a ProviderError: it means our request is wrong.
    if status != 400 or not isinstance(body, dict):
        return None
    reason = body.get('reason')
    if not (isinstance(reason, str) and 'out of allowed range' in reason):
        return None
    first_hour, last_hour = window
    return ForecastRangeError(f'Open-Meteo has no forecast for all of {_utc(first_hour)} to {_utc(last_hour)}')


def _locations(document: object, count: int) -> list[object]:
    locations: list[object] = [document] if isinstance(document, dict) else _array(document, 'response')
    if len(locations) != count:
        raise ValueError(f'response has {len(locations)} locations for {count} points')
    return locations


def _series(value: object, window: tuple[datetime, datetime], where: str) -> HourlySeries:
    location = _object(value, where)
    units = _object(location.get('hourly_units'), f'{where}.hourly_units')
    hourly = _object(location.get('hourly'), f'{where}.hourly')
    if units.get('time') != 'unixtime':
        raise ValueError(f"{where}.hourly_units.time must be 'unixtime'; got {units.get('time')!r}")
    raw_hours = _array(hourly.get('time'), f'{where}.hourly.time')
    hours = tuple(_hour(raw, f'{where}.hourly.time', index) for index, raw in enumerate(raw_hours))
    wind, rain, showers, snow = (
        _column(hourly.get(name), _units_per(units, name, table, where), len(hours), f'{where}.hourly.{name}')
        for name, table in VARIABLES
    )
    try:
        series = HourlySeries(
            hours=hours,
            wind_mph=_floats(wind),
            rain_in_per_hour=tuple(_rain_plus_showers(r, s) for r, s in zip(rain, showers, strict=True)),
            snow_in_per_hour=_floats(snow),
        )
    except ValueError as exc:
        raise ValueError(f'{where}: {exc}') from exc

    first_hour, last_hour = window
    if not hours or hours[0] > first_hour or hours[-1] < last_hour:
        span = f'{_utc(hours[0])} to {_utc(hours[-1])}' if hours else 'no hours'
        raise ValueError(f'{where} covers {span}, not {_utc(first_hour)} to {_utc(last_hour)} as asked')
    # Hours with no value at all at the end mean the forecast stops there: the window reaches
    # past it. A series with no value anywhere is a gap at that point instead, left to `sample_at`.
    last_with_data = _last_hour_with_data(series)
    if last_with_data is not None and last_with_data < last_hour:
        raise ForecastRangeError(
            f'the Open-Meteo forecast for {where} ends at {_utc(last_with_data)}, before {_utc(last_hour)}'
        )
    return series


def _last_hour_with_data(series: HourlySeries) -> datetime | None:
    rows = zip(series.hours, series.wind_mph, series.rain_in_per_hour, series.snow_in_per_hour, strict=True)
    with_data = [hour for hour, *values in rows if any(value is not None for value in values)]
    return with_data[-1] if with_data else None


def _units_per(units: Mapping[str, object], name: str, table: Mapping[str, Decimal], where: str) -> Decimal:
    unit = units.get(name)
    if not isinstance(unit, str) or unit not in table:
        raise ValueError(f'{where}.hourly_units.{name} is {unit!r}, not one of {", ".join(table)}')
    return table[unit]


def _hour(value: object, where: str, index: int) -> datetime:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f'{where}[{index}] must be whole seconds; got {type(value).__name__}')
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f'{where}[{index}] is not a usable time: {value}') from exc


def _column(value: object, units_per: Decimal, count: int, where: str) -> list[Decimal | None]:
    """Each value in mph or inches, still exact. A null stays None."""
    values = _array(value, where)
    if len(values) != count:
        raise ValueError(f'{where} has {len(values)} values for {count} hours')
    converted: list[Decimal | None] = []
    for index, item in enumerate(values):
        number = _measure(item, where, index)
        converted.append(None if number is None else number / units_per)
    return converted


def _measure(value: object, where: str, index: int) -> Decimal | None:
    # Nulls and negatives pass: they make an hour unusable only if that hour is read.
    if value is None:
        return None
    # bool is a subclass of int, and `true` must not read as 1 mph.
    if isinstance(value, bool) or not isinstance(value, int | Decimal):
        raise ValueError(f'{where}[{index}] must be a number or null; got {type(value).__name__}')
    number = Decimal(value)
    # No weather reading overflows a float. One that does marks a broken answer.
    if not math.isfinite(float(number)):
        raise ValueError(f'{where}[{index}] is too large to be a reading')
    return number


def _rain_plus_showers(rain_inches: Decimal | None, showers_inches: Decimal | None) -> float | None:
    if rain_inches is None or showers_inches is None:
        return None
    # A sum would let a positive part hide a negative one. The negative is kept, so `sample_at` rejects that hour.
    if rain_inches < 0 or showers_inches < 0:
        return float(min(rain_inches, showers_inches))
    return float(rain_inches + showers_inches)


def _floats(values: list[Decimal | None]) -> tuple[float | None, ...]:
    return tuple(None if value is None else float(value) for value in values)


def _generation_ms(locations: list[object]) -> float | None:
    # Only for the log, so a malformed value is skipped instead of failing the forecast.
    times = [
        location['generationtime_ms']
        for location in locations
        if isinstance(location, dict) and isinstance(location.get('generationtime_ms'), int | Decimal)
    ]
    return round(float(sum(times)), 3) if times else None


def _utc(moment: datetime) -> str:
    return moment.isoformat().replace('+00:00', 'Z')


def _object(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f'{where} must be an object; got {type(value).__name__}')
    return value


def _array(value: object, where: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f'{where} must be a list; got {type(value).__name__}')
    return value
