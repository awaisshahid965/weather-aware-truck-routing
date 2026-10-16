from datetime import UTC, datetime, timedelta

import httpx
import pytest

from routing.adapters.open_meteo_forecast import OpenMeteoForecast
from routing.domain.forecast import sample_at
from routing.domain.models import GeoPoint
from routing.ports.errors import ForecastRangeError

PITTSBURGH = GeoPoint(40.4406, -79.9959)
CLEVELAND = GeoPoint(41.4993, -81.6944)


@pytest.mark.live
def test_open_meteo_forecasts_two_points_for_the_next_6_hours() -> None:
    start_at = datetime.now(UTC)
    end_at = start_at + timedelta(hours=6)

    with httpx.Client(timeout=httpx.Timeout(10, connect=3)) as client:
        series = OpenMeteoForecast(client, batch_size=50, deadline_seconds=25).hourly(
            [PITTSBURGH, CLEVELAND], start_at, end_at
        )

    assert len(series) == 2
    for one in series:
        # The hours that hold the window's start and end, and every hour between: 7 in all.
        assert len(one.hours) == 7
        assert None not in one.wind_mph + one.rain_in_per_hour + one.snow_in_per_hour
        sample_at(one, start_at)
        sample_at(one, end_at)


@pytest.mark.live
def test_open_meteo_refuses_a_window_past_its_range_as_a_range_error() -> None:
    # The adapter recognises the refusal by Open-Meteo's wording. This catches a change to it.
    start_at = datetime.now(UTC) + timedelta(days=30)

    with (
        httpx.Client(timeout=httpx.Timeout(10, connect=3)) as client,
        pytest.raises(ForecastRangeError, match='no forecast for all of'),
    ):
        OpenMeteoForecast(client, batch_size=50, deadline_seconds=25).hourly(
            [PITTSBURGH], start_at, start_at + timedelta(hours=48)
        )
