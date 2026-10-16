import json
import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from routing.adapters.open_meteo_forecast import MAX_LEAD_HOURS, OpenMeteoForecast
from routing.domain.errors import ForecastGapError
from routing.domain.forecast import sample_at
from routing.domain.models import ONE_HOUR, GeoPoint, HourlySeries, RiskLevel
from routing.domain.risk import classify
from routing.ports.errors import ForecastRangeError, ProviderError, ProviderTimeoutError
from routing.ports.forecast_provider import ForecastProvider
from tests.adapters.fakes import FakeClock
from tests.spec_rules import SPEC_RULES

FIXTURES = Path(__file__).parent / 'fixtures' / 'open_meteo'
PITTSBURGH = GeoPoint(40.4406, -79.9959)
CLEVELAND = GeoPoint(41.4993, -81.6944)
TWO_PM = datetime(2026, 11, 17, 14, 0, tzinfo=UTC)
CLIENT_TIMEOUT = httpx.Timeout(10, connect=3)
DEADLINE_SECONDS = 25
BATCH_SIZE = 50
INCH_UNITS = {'time': 'unixtime', 'wind_speed_10m': 'mp/h', 'rain': 'inch', 'showers': 'inch', 'snowfall': 'inch'}

Document = dict[str, object]
Reply = Callable[[httpx.Request], object]


class FakeOpenMeteo:
    """Answers each request with `reply(request)` and keeps the requests.

    A reply in bytes is sent as is; anything else is sent as JSON. With a clock, each
    request takes `seconds_per_call` of it, like a slow provider.
    """

    def __init__(
        self, reply: Reply, *, status: int = 200, clock: FakeClock | None = None, seconds_per_call: float = 0
    ) -> None:
        self._reply = reply
        self._status = status
        self._clock = clock
        self._seconds_per_call = seconds_per_call
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._clock is not None:
            self._clock.now += self._seconds_per_call
        body = self._reply(request)
        return httpx.Response(self._status, content=body if isinstance(body, bytes) else json.dumps(body).encode())


def _hourly(
    open_meteo: FakeOpenMeteo,
    points: Sequence[GeoPoint],
    start_at: datetime,
    end_at: datetime,
    *,
    batch_size: int = BATCH_SIZE,
    clock: FakeClock | None = None,
) -> list[HourlySeries]:
    clock = clock or FakeClock()
    with httpx.Client(transport=httpx.MockTransport(open_meteo), timeout=CLIENT_TIMEOUT) as client:
        provider: ForecastProvider = OpenMeteoForecast(
            client, batch_size=batch_size, deadline_seconds=DEADLINE_SECONDS, clock=clock, sleep=clock.sleep
        )
        return provider.hourly(points, start_at, end_at)


def _recorded(name: str) -> Reply:
    content = (FIXTURES / name).read_bytes()
    return lambda _request: content


def _recorded_locations(name: str) -> list[Any]:
    """The fixture as a list of locations, with plain floats: fine to compare, not to add."""
    document = json.loads((FIXTURES / name).read_text(encoding='utf-8'))
    return document if isinstance(document, list) else [document]


def _recorded_window(name: str) -> tuple[datetime, datetime]:
    """The first and last hour the fixture holds, so a request asks for exactly those."""
    times = _recorded_locations(name)[0]['hourly']['time']
    return datetime.fromtimestamp(times[0], tz=UTC), datetime.fromtimestamp(times[-1], tz=UTC)


def _always(document: object) -> Reply:
    return lambda _request: document


def _hours(start: datetime, count: int) -> list[datetime]:
    return [start + offset * ONE_HOUR for offset in range(count)]


def _location(
    hours: Sequence[datetime],
    *,
    latitude: float = 40.445118,
    units: Mapping[str, object] | None = None,
    hourly: Mapping[str, object] | None = None,
) -> Document:
    """One location in Open-Meteo's shape. Each variable is calm unless `hourly` gives it."""
    calm: dict[str, object] = {
        'wind_speed_10m': [10.0] * len(hours),
        'rain': [0.0] * len(hours),
        'showers': [0.0] * len(hours),
        'snowfall': [0.0] * len(hours),
    }
    return {
        'latitude': latitude,
        'longitude': -80.005745,
        'generationtime_ms': 0.25,
        'utc_offset_seconds': 0,
        'timezone': 'GMT',
        'hourly_units': INCH_UNITS | dict(units or {}),
        'hourly': {'time': [int(hour.timestamp()) for hour in hours], **calm, **(hourly or {})},
    }


def _latitude_as_wind(request: httpx.Request) -> object:
    """Calm weather over exactly the hours asked. Each point's wind is its latitude, to tell them apart.

    Like Open-Meteo, it returns grid-snapped coordinates, and an object for a single point.
    """
    params = request.url.params
    first = datetime.fromisoformat(params['start_hour']).replace(tzinfo=UTC)
    last = datetime.fromisoformat(params['end_hour']).replace(tzinfo=UTC)
    hours = _hours(first, (last - first) // ONE_HOUR + 1)
    locations = [
        _location(
            hours, latitude=round(float(latitude), 1) + 0.03, hourly={'wind_speed_10m': [float(latitude)] * len(hours)}
        )
        for latitude in params['latitude'].split(',')
    ]
    return locations[0] if len(locations) == 1 else locations


def test_two_points_become_two_series_in_request_order() -> None:
    recorded = _recorded_locations('two_points.json')
    start_at, end_at = _recorded_window('two_points.json')

    series = _hourly(FakeOpenMeteo(_recorded('two_points.json')), [PITTSBURGH, CLEVELAND], start_at, end_at)

    assert [one.wind_mph for one in series] == [tuple(location['hourly']['wind_speed_10m']) for location in recorded]
    assert series[0].wind_mph != series[1].wind_mph
    assert [(one.hours[0], one.hours[-1], len(one.hours)) for one in series] == [(start_at, end_at, 72)] * 2


def test_one_point_answers_with_an_object_and_becomes_one_series() -> None:
    start_at, end_at = _recorded_window('one_point.json')

    [series] = _hourly(FakeOpenMeteo(_recorded('one_point.json')), [PITTSBURGH], start_at, end_at)

    assert len(series.hours) == 24


def test_points_are_split_into_batches_and_keep_their_order() -> None:
    points = [GeoPoint(latitude=position * 0.5, longitude=-80.0) for position in range(120)]
    open_meteo = FakeOpenMeteo(_latitude_as_wind)

    series = _hourly(open_meteo, points, TWO_PM, TWO_PM + ONE_HOUR)

    assert [len(request.url.params['latitude'].split(',')) for request in open_meteo.requests] == [50, 50, 20]
    assert [one.wind_mph[0] for one in series] == [point.latitude for point in points]


def test_a_batch_of_one_point_reads_the_object_form() -> None:
    points = [GeoPoint(latitude=position * 0.5, longitude=-80.0) for position in range(3)]
    open_meteo = FakeOpenMeteo(_latitude_as_wind)

    series = _hourly(open_meteo, points, TWO_PM, TWO_PM, batch_size=2)

    assert len(open_meteo.requests) == 2
    assert [one.wind_mph[0] for one in series] == [0.0, 0.5, 1.0]


def test_metric_units_are_converted_to_mph_and_inches() -> None:
    recorded = _recorded_locations('two_points_metric.json')
    start_at, end_at = _recorded_window('two_points_metric.json')

    series = _hourly(FakeOpenMeteo(_recorded('two_points_metric.json')), [PITTSBURGH, CLEVELAND], start_at, end_at)

    for one, location in zip(series, recorded, strict=True):
        hourly = location['hourly']
        rain_mm = [rain + showers for rain, showers in zip(hourly['rain'], hourly['showers'], strict=True)]
        assert list(one.wind_mph) == pytest.approx([kmh / 1.609344 for kmh in hourly['wind_speed_10m']])
        assert list(one.rain_in_per_hour) == pytest.approx([mm / 25.4 for mm in rain_mm])
        assert list(one.snow_in_per_hour) == pytest.approx([cm / 2.54 for cm in hourly['snowfall']])
    assert any(rain > 0 for one in series for rain in one.rain_in_per_hour if rain is not None)


@pytest.mark.parametrize(
    ('variable', 'unit', 'reading', 'field'),
    [
        pytest.param('wind_speed_10m', 'km/h', 1.609344, 'wind_mph', id='km/h'),
        pytest.param('wind_speed_10m', 'm/s', 0.44704, 'wind_mph', id='m/s'),
        pytest.param('rain', 'mm', 25.4, 'rain_in_per_hour', id='rain in mm'),
        pytest.param('showers', 'mm', 25.4, 'rain_in_per_hour', id='showers in mm'),
        pytest.param('snowfall', 'cm', 2.54, 'snow_in_per_hour', id='snow in cm'),
    ],
)
def test_one_mile_or_one_inch_in_another_unit_converts_to_exactly_1(
    variable: str, unit: str, reading: float, field: str
) -> None:
    document = _location([TWO_PM], units={variable: unit}, hourly={variable: [reading]})

    [series] = _hourly(FakeOpenMeteo(_always(document)), [PITTSBURGH], TWO_PM, TWO_PM)

    assert getattr(series, field) == (1.0,)


def test_an_unknown_unit_is_a_provider_error() -> None:
    start_at, end_at = _recorded_window('unknown_unit.json')

    with pytest.raises(ProviderError, match=r"hourly_units\.wind_speed_10m is 'kn'"):
        _hourly(FakeOpenMeteo(_recorded('unknown_unit.json')), [PITTSBURGH], start_at, end_at)


def test_an_array_shorter_than_time_is_a_provider_error() -> None:
    start_at, end_at = _recorded_window('length_mismatch.json')

    with pytest.raises(ProviderError, match=r'hourly\.showers has 23 values for 24 hours'):
        _hourly(FakeOpenMeteo(_recorded('length_mismatch.json')), [PITTSBURGH], start_at, end_at)


def test_nulls_stay_none_and_are_never_read_as_0() -> None:
    start_at, end_at = _recorded_window('nulls.json')

    [series] = _hourly(FakeOpenMeteo(_recorded('nulls.json')), [PITTSBURGH], start_at, end_at)

    assert [position for position, wind in enumerate(series.wind_mph) if wind is None] == [2]
    assert [position for position, snow in enumerate(series.snow_in_per_hour) if snow is None] == [5]
    with pytest.raises(ForecastGapError, match='wind_mph'):
        sample_at(series, series.hours[2])
    sample_at(series, series.hours[3])


def test_a_window_open_meteo_refuses_as_out_of_range_is_a_range_error() -> None:
    open_meteo = FakeOpenMeteo(_recorded('error_out_of_range.json'), status=400)

    with pytest.raises(ForecastRangeError) as caught:
        _hourly(open_meteo, [PITTSBURGH], TWO_PM, TWO_PM + 48 * ONE_HOUR)

    assert str(caught.value) == 'Open-Meteo has no forecast for all of 2026-11-17T14:00:00Z to 2026-11-19T14:00:00Z'
    assert not isinstance(caught.value, ProviderError)
    assert len(open_meteo.requests) == 1


def test_any_other_refusal_stays_a_provider_error() -> None:
    open_meteo = FakeOpenMeteo(_recorded('error_400.json'), status=400)

    with pytest.raises(ProviderError, match='answered 400'):
        _hourly(open_meteo, [PITTSBURGH], TWO_PM, TWO_PM)


def test_a_forecast_that_ends_inside_the_window_is_a_range_error() -> None:
    # Recorded: the last 5 hours of Open-Meteo's range came back with every value null.
    start_at, end_at = _recorded_window('range_end_nulls.json')

    with pytest.raises(ForecastRangeError, match='ends at 2026-10-31T18:00:00Z, before 2026-10-31T23:00:00Z') as caught:
        _hourly(FakeOpenMeteo(_recorded('range_end_nulls.json')), [PITTSBURGH], start_at, end_at)

    assert not isinstance(caught.value, ProviderError)


def test_empty_hours_after_the_window_do_not_matter() -> None:
    start_at, _ = _recorded_window('range_end_nulls.json')
    end_at = datetime(2026, 10, 31, 18, 0, tzinfo=UTC)

    [series] = _hourly(FakeOpenMeteo(_recorded('range_end_nulls.json')), [PITTSBURGH], start_at, end_at)

    sample_at(series, end_at)


def test_a_last_hour_missing_only_some_values_is_a_gap_not_a_range_error() -> None:
    document = _location(_hours(TWO_PM, 2), hourly={'rain': [0.0, None]})

    [series] = _hourly(FakeOpenMeteo(_always(document)), [PITTSBURGH], TWO_PM, TWO_PM + ONE_HOUR)

    with pytest.raises(ForecastGapError, match='rain_in_per_hour'):
        sample_at(series, TWO_PM + ONE_HOUR)


def test_a_point_with_no_values_at_all_is_a_gap_not_a_range_error() -> None:
    nothing = [None, None]
    document = _location(
        _hours(TWO_PM, 2),
        hourly={'wind_speed_10m': nothing, 'rain': nothing, 'showers': nothing, 'snowfall': nothing},
    )

    [series] = _hourly(FakeOpenMeteo(_always(document)), [PITTSBURGH], TWO_PM, TWO_PM + ONE_HOUR)

    with pytest.raises(ForecastGapError, match='wind_mph'):
        sample_at(series, TWO_PM)


def test_rain_and_showers_add_exactly() -> None:
    # The trap this guards against: in binary floats the sum is just under the 0.10 threshold.
    assert 0.09 + 0.01 < 0.10
    document = _location([TWO_PM], hourly={'rain': [0.09], 'showers': [0.01]})

    [series] = _hourly(FakeOpenMeteo(_always(document)), [PITTSBURGH], TWO_PM, TWO_PM)

    assert series.rain_in_per_hour == (0.10,)
    assert classify(sample_at(series, TWO_PM), 0, SPEC_RULES).level is RiskLevel.MODERATE


def test_a_negative_part_is_not_hidden_by_the_sum() -> None:
    document = _location([TWO_PM], hourly={'rain': [-0.05], 'showers': [0.10]})

    [series] = _hourly(FakeOpenMeteo(_always(document)), [PITTSBURGH], TWO_PM, TWO_PM)

    with pytest.raises(ForecastGapError, match='rain_in_per_hour'):
        sample_at(series, TWO_PM)


def test_the_request_carries_the_params() -> None:
    open_meteo = FakeOpenMeteo(_latitude_as_wind)

    _hourly(open_meteo, [PITTSBURGH, CLEVELAND], TWO_PM, TWO_PM + 48 * ONE_HOUR)

    [request] = open_meteo.requests
    assert request.url.host == 'api.open-meteo.com'
    assert request.url.path == '/v1/forecast'
    assert dict(request.url.params) == {
        'latitude': '40.4406,41.4993',
        'longitude': '-79.9959,-81.6944',
        'hourly': 'wind_speed_10m,rain,showers,snowfall',
        'wind_speed_unit': 'mph',
        'precipitation_unit': 'inch',
        'timeformat': 'unixtime',
        'timezone': 'GMT',
        'start_hour': '2026-11-17T14:00',
        'end_hour': '2026-11-19T14:00',
    }


def test_coordinates_are_sent_with_4_decimals() -> None:
    open_meteo = FakeOpenMeteo(_latitude_as_wind)

    _hourly(open_meteo, [GeoPoint(40.123456, -79.98765)], TWO_PM, TWO_PM)

    assert open_meteo.requests[0].url.params['latitude'] == '40.1235'
    assert open_meteo.requests[0].url.params['longitude'] == '-79.9877'


def test_the_window_runs_to_the_hours_that_hold_its_ends() -> None:
    open_meteo = FakeOpenMeteo(_latitude_as_wind)
    twenty_past_eight_in_pittsburgh = datetime(2026, 11, 17, 8, 20, tzinfo=ZoneInfo('America/New_York'))

    [series] = _hourly(
        open_meteo, [PITTSBURGH], twenty_past_eight_in_pittsburgh, twenty_past_eight_in_pittsburgh + 48 * ONE_HOUR
    )

    params = open_meteo.requests[0].url.params
    assert (params['start_hour'], params['end_hour']) == ('2026-11-17T14:00', '2026-11-19T14:00')
    sample_at(series, twenty_past_eight_in_pittsburgh)
    sample_at(series, twenty_past_eight_in_pittsburgh + 48 * ONE_HOUR)


def test_an_answer_that_misses_an_hour_asked_for_is_a_provider_error() -> None:
    document = _location(_hours(TWO_PM, 2))

    with pytest.raises(ProviderError, match=r'covers 2026-11-17T14:00:00Z to 2026-11-17T15:00:00Z, not'):
        _hourly(FakeOpenMeteo(_always(document)), [PITTSBURGH], TWO_PM, TWO_PM + 2 * ONE_HOUR)


def test_all_batches_share_one_deadline() -> None:
    clock = FakeClock()
    # 9 s each: every batch fits 25 s alone, but the third ends at 27 s.
    open_meteo = FakeOpenMeteo(_latitude_as_wind, clock=clock, seconds_per_call=9)

    with pytest.raises(ProviderTimeoutError):
        _hourly(open_meteo, [PITTSBURGH, CLEVELAND, PITTSBURGH], TWO_PM, TWO_PM, batch_size=1, clock=clock)

    # The client allows 10 s per read. The third batch starts at 18 s, so only 7 s are left for it.
    assert [request.extensions['timeout']['read'] for request in open_meteo.requests] == [10, 10, 7]


def test_no_points_need_no_request() -> None:
    open_meteo = FakeOpenMeteo(_latitude_as_wind)

    series = _hourly(open_meteo, [], TWO_PM, TWO_PM + ONE_HOUR)

    assert series == []
    assert open_meteo.requests == []


@pytest.mark.parametrize(
    ('start_at', 'end_at', 'reason'),
    [
        pytest.param(TWO_PM.replace(tzinfo=None), TWO_PM, 'timezone-aware', id='naive start'),
        pytest.param(TWO_PM, TWO_PM.replace(tzinfo=None), 'timezone-aware', id='naive end'),
        pytest.param(TWO_PM + ONE_HOUR, TWO_PM, 'must not be after', id='start after end'),
    ],
)
def test_a_bad_window_is_rejected_before_any_request(start_at: datetime, end_at: datetime, reason: str) -> None:
    open_meteo = FakeOpenMeteo(_latitude_as_wind)

    with pytest.raises(ValueError, match=reason):
        _hourly(open_meteo, [PITTSBURGH], start_at, end_at)

    assert open_meteo.requests == []


@pytest.mark.parametrize(
    ('document', 'reason'),
    [
        pytest.param('forecast', 'response must be a list; got str', id='neither object nor list'),
        pytest.param([], 'response has 0 locations for 1 points', id='no locations'),
        pytest.param({'hourly_units': INCH_UNITS}, r'hourly must be an object; got NoneType', id='no hourly'),
        pytest.param(
            _location([TWO_PM], units={'time': 'iso8601'}),
            r"hourly_units\.time must be 'unixtime'; got 'iso8601'",
            id='time not in unix seconds',
        ),
        pytest.param(
            _location([TWO_PM], hourly={'time': ['2026-11-17T14:00']}),
            r'hourly\.time\[0\] must be whole seconds; got str',
            id='time as text',
        ),
        pytest.param(
            _location([TWO_PM], hourly={'wind_speed_10m': ['10']}),
            r'hourly\.wind_speed_10m\[0\] must be a number or null; got str',
            id='a value as text',
        ),
        pytest.param(
            _location([TWO_PM], hourly={'wind_speed_10m': [True]}),
            r'hourly\.wind_speed_10m\[0\] must be a number or null; got bool',
            id='a value as a boolean',
        ),
        pytest.param(
            _location([TWO_PM], hourly={'wind_speed_10m': [10**400]}),
            r'hourly\.wind_speed_10m\[0\] is too large to be a reading',
            id='a value too large for a float',
        ),
        pytest.param(
            _location([TWO_PM], hourly={'snowfall': None}),
            r'hourly\.snowfall must be a list; got NoneType',
            id='a variable missing',
        ),
        pytest.param(
            _location([TWO_PM], units={'snowfall': 'ft'}),
            r"hourly_units\.snowfall is 'ft', not one of inch, mm, cm",
            id='an unknown snow unit',
        ),
        pytest.param(
            _location([TWO_PM], units={'rain': None}),
            r'hourly_units\.rain is None',
            id='a unit missing',
        ),
        pytest.param(
            _location([TWO_PM, TWO_PM + 2 * ONE_HOUR]),
            '1 h apart',
            id='hours not 1 h apart',
        ),
    ],
)
def test_a_forecast_we_cannot_use_is_a_provider_error(document: object, reason: str) -> None:
    with pytest.raises(ProviderError, match=reason):
        _hourly(FakeOpenMeteo(_always(document)), [PITTSBURGH], TWO_PM, TWO_PM)


def test_each_batch_is_logged_with_its_size_and_generation_time(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    _hourly(FakeOpenMeteo(_latitude_as_wind), [PITTSBURGH, CLEVELAND], TWO_PM, TWO_PM)

    [record] = [record for record in caplog.records if record.getMessage() == 'open-meteo batch fetched']
    assert (vars(record)['points'], vars(record)['generationtime_ms']) == (2, 0.5)


def test_the_lead_bound_stays_inside_the_hours_open_meteo_fills() -> None:
    with httpx.Client() as client:
        provider = OpenMeteoForecast(client, batch_size=BATCH_SIZE, deadline_seconds=DEADLINE_SECONDS)

    # 14 days 18 hours: from any time of day, it ends by 18:00 UTC on day 16, where data stopped.
    assert provider.max_lead_hours == MAX_LEAD_HOURS == 354


@pytest.mark.parametrize(
    ('batch_size', 'deadline_seconds', 'reason'),
    [
        pytest.param(0, DEADLINE_SECONDS, 'batch_size must be >= 1', id='no batch'),
        pytest.param(BATCH_SIZE, 0, 'deadline_seconds must be > 0', id='no time'),
        pytest.param(BATCH_SIZE, float('nan'), 'deadline_seconds must be > 0', id='NaN time'),
    ],
)
def test_the_limits_must_be_positive(batch_size: int, deadline_seconds: float, reason: str) -> None:
    with httpx.Client() as client, pytest.raises(ValueError, match=reason):
        OpenMeteoForecast(client, batch_size=batch_size, deadline_seconds=deadline_seconds)
