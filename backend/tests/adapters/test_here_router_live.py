from datetime import UTC, datetime, timedelta

import httpx
import pytest
from django.conf import settings

from routing.adapters.here_router import HereRouter
from routing.domain.models import GeoPoint

PITTSBURGH = GeoPoint(40.4406, -79.9959)
CLEVELAND = GeoPoint(41.4993, -81.6944)


@pytest.mark.live
def test_here_finds_a_truck_route_from_pittsburgh_to_cleveland() -> None:
    if not settings.HERE_API_KEY:
        pytest.skip('HERE_API_KEY is not set')
    tomorrow = datetime.now(UTC) + timedelta(days=1)

    with httpx.Client(timeout=httpx.Timeout(10, connect=3)) as client:
        routes = HereRouter(client, settings.HERE_API_KEY, deadline_seconds=15).find_routes(
            PITTSBURGH, CLEVELAND, tomorrow
        )

    assert len(routes) >= 1
