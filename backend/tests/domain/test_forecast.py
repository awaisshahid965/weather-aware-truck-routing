import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from routing.domain.errors import ForecastGapError
from routing.domain.forecast import sample_at
from routing.domain.models import ONE_HOUR, HourlySeries, WeatherSample

TWO_PM = datetime(2026, 11, 17, 14, 0, tzinfo=UTC)
THREE_PM = TWO_PM + ONE_HOUR
AT_TWO_PM = WeatherSample(wind_mph=12, rain_in_per_hour=0.05, snow_in_per_hour=0)
AT_THREE_PM = WeatherSample(wind_mph=30, rain_in_per_hour=0.2, snow_in_per_hour=0.6)
FIELDS = ('wind_mph', 'rain_in_per_hour', 'snow_in_per_hour')
UNUSABLE = [
    pytest.param(None, id='None'),
    pytest.param(-0.01, id='negative'),
    pytest.param(math.nan, id='NaN'),
    pytest.param(math.inf, id='infinite'),
]


def _at(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 11, 17, hour, minute, second, tzinfo=UTC)


def _two_hours(
    two_pm: Sequence[float | None] = (12, 0.05, 0), three_pm: Sequence[float | None] = (30, 0.2, 0.6)
) -> HourlySeries:
    """14:00 and 15:00 UTC. Each row is (wind, rain, snow)."""
    wind, rain, snow = zip(two_pm, three_pm, strict=True)
    return HourlySeries(hours=(TWO_PM, THREE_PM), wind_mph=wind, rain_in_per_hour=rain, snow_in_per_hour=snow)


def _with(field: str, value: float | None) -> list[float | None]:
    """The 15:00 row with one field replaced."""
    row: list[float | None] = [30, 0.2, 0.6]
    row[FIELDS.index(field)] = value
    return row


@pytest.mark.parametrize(
    ('at', 'expected'),
    [
        pytest.param(_at(13, 0, 1), AT_TWO_PM, id='13:00:01 uses 14:00'),
        pytest.param(_at(13, 30), AT_TWO_PM, id='13:30 uses 14:00'),
        pytest.param(_at(14), AT_TWO_PM, id='14:00:00 uses 14:00'),
        pytest.param(_at(14, 0, 1), AT_THREE_PM, id='14:00:01 uses 15:00'),
        pytest.param(_at(14, 20), AT_THREE_PM, id='14:20 uses 15:00'),
        pytest.param(_at(15), AT_THREE_PM, id='15:00 uses 15:00'),
    ],
)
def test_the_first_hour_at_or_after_the_moment_is_used(at: datetime, expected: WeatherSample) -> None:
    sample = sample_at(_two_hours(), at)

    assert sample == expected


@pytest.mark.parametrize(
    'at',
    [
        pytest.param(_at(15, 0, 1), id='15:00:01 is past the last hour'),
        pytest.param(_at(13), id='13:00 is a full hour before the first hour'),
        pytest.param(_at(12, 30), id='12:30 is over an hour before the first hour'),
    ],
)
def test_a_moment_the_series_does_not_cover_is_a_gap(at: datetime) -> None:
    with pytest.raises(ForecastGapError, match='does not cover'):
        sample_at(_two_hours(), at)


def test_a_moment_in_another_time_zone_uses_its_utc_hour() -> None:
    twenty_past_nine_in_pittsburgh = datetime(2026, 11, 17, 9, 20, tzinfo=ZoneInfo('America/New_York'))

    sample = sample_at(_two_hours(), twenty_past_nine_in_pittsburgh)

    assert sample == AT_THREE_PM


def test_an_empty_series_covers_nothing() -> None:
    series = HourlySeries(hours=(), wind_mph=(), rain_in_per_hour=(), snow_in_per_hour=())

    with pytest.raises(ForecastGapError, match='does not cover'):
        sample_at(series, TWO_PM)


@pytest.mark.parametrize('value', UNUSABLE)
@pytest.mark.parametrize('field', FIELDS)
def test_an_unusable_value_at_the_hour_used_is_a_gap(field: str, value: float | None) -> None:
    series = _two_hours(three_pm=_with(field, value))

    with pytest.raises(ForecastGapError, match=f'{field} at 2026-11-17T15:00:00Z'):
        sample_at(series, THREE_PM)


@pytest.mark.parametrize('value', UNUSABLE)
@pytest.mark.parametrize('field', FIELDS)
def test_an_unusable_value_at_another_hour_does_not_matter(field: str, value: float | None) -> None:
    series = _two_hours(three_pm=_with(field, value))

    sample = sample_at(series, TWO_PM)

    assert sample == AT_TWO_PM


def test_a_naive_moment_is_rejected() -> None:
    with pytest.raises(ValueError, match='timezone-aware'):
        sample_at(_two_hours(), datetime(2026, 11, 17, 14, 0))  # noqa: DTZ001 - naive on purpose


DAY_AND_A_HALF = tuple(TWO_PM + offset * ONE_HOUR for offset in range(37))
# Each hour's wind is its own position, so a sample tells which hour was read.
NUMBERED = HourlySeries(
    hours=DAY_AND_A_HALF,
    wind_mph=tuple(float(position) for position in range(len(DAY_AND_A_HALF))),
    rain_in_per_hour=(0.0,) * len(DAY_AND_A_HALF),
    snow_in_per_hour=(0.0,) * len(DAY_AND_A_HALF),
)


# Hypothesis takes naive bounds and attaches the time zone itself.
@given(
    at=st.datetimes(
        min_value=(DAY_AND_A_HALF[0] - ONE_HOUR + timedelta(microseconds=1)).replace(tzinfo=None),
        max_value=DAY_AND_A_HALF[-1].replace(tzinfo=None),
        timezones=st.just(UTC),
    )
)
def test_the_hour_read_is_the_one_that_holds_the_moment(at: datetime) -> None:
    sample = sample_at(NUMBERED, at)

    hour = DAY_AND_A_HALF[int(sample.wind_mph)]
    assert hour - ONE_HOUR < at <= hour


@pytest.mark.parametrize(
    ('hours', 'reason'),
    [
        pytest.param((TWO_PM, TWO_PM + 2 * ONE_HOUR), '1 h apart', id='a missing hour'),
        pytest.param((THREE_PM, TWO_PM), '1 h apart', id='descending'),
        pytest.param((TWO_PM, TWO_PM), '1 h apart', id='a repeated hour'),
        pytest.param((TWO_PM.replace(tzinfo=None), THREE_PM.replace(tzinfo=None)), 'aware UTC', id='naive'),
        pytest.param(
            (TWO_PM.astimezone(ZoneInfo('America/New_York')), THREE_PM.astimezone(ZoneInfo('America/New_York'))),
            'aware UTC',
            id='not UTC',
        ),
    ],
)
def test_a_series_needs_utc_hours_1_hour_apart(hours: tuple[datetime, ...], reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        HourlySeries(hours=hours, wind_mph=(1, 2), rain_in_per_hour=(0, 0), snow_in_per_hour=(0, 0))


def test_a_series_needs_one_value_per_hour() -> None:
    with pytest.raises(ValueError, match='rain_in_per_hour has 1 values for 2 hours'):
        HourlySeries(hours=(TWO_PM, THREE_PM), wind_mph=(1, 2), rain_in_per_hour=(0,), snow_in_per_hour=(0, 0))
