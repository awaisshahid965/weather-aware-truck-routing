import httpx
import pytest
from django.conf import settings

from routing.adapters.here_geocoder import HereGeocoder
from routing.domain.geometry import haversine_miles
from routing.domain.models import GeoPoint

PITTSBURGH = GeoPoint(40.4406, -79.9959)


@pytest.mark.live
def test_here_finds_pittsburgh() -> None:
    if not settings.HERE_API_KEY:
        pytest.skip('HERE_API_KEY is not set')

    with httpx.Client(timeout=httpx.Timeout(10, connect=3)) as client:
        matches = HereGeocoder(client, settings.HERE_API_KEY, deadline_seconds=5).search('Pittsburgh, PA', 5)

    assert 1 <= len(matches) <= 5
    assert 'Pittsburgh' in matches[0].label
    assert haversine_miles(matches[0].point, PITTSBURGH) < 10
