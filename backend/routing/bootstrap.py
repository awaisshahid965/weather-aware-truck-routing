"""The composition root: the one module that reads provider settings and builds adapters.

Views ask it for ready services. Tests replace its provider functions to inject fakes. The
limits are named constants here (contract → Limits), not environment settings.
"""

import atexit
import tempfile
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

import httpx
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from routing.adapters.here_geocoder import HereGeocoder
from routing.adapters.here_router import HereRouter
from routing.adapters.json_risk_rules import JsonRiskRules
from routing.adapters.open_meteo_forecast import OpenMeteoForecast
from routing.ports.risk_rules import RiskRulesSource
from routing.services.plan_trip import PlanTripService
from routing.services.search_places import SearchPlacesService

MAX_ROUTE_MILES = 2_500
MAX_HEATMAP_POINTS = 90
FORECAST_BATCH_SIZE = 50
FORECAST_DEDUPE_MILES = 3
HTTP_CONNECT_TIMEOUT_SECONDS = 3
HTTP_READ_TIMEOUT_SECONDS = 10
ROUTING_DEADLINE_SECONDS = 15
FORECAST_DEADLINE_SECONDS = 25
GEOCODING_DEADLINE_SECONDS = 5

# HERE's free monthly allowance is 5,000 truck routes and 30,000 geocodes, and use past it is billed.
# A month at these daily limits (31 x 125 = 3,875 and 31 x 600 = 18,600) stays under both, with room
# left for development, which uses the same key. Each plan also reads about 40 Open-Meteo locations,
# so 125 plans stay under Open-Meteo's 10,000 a day too.
ROUTE_PLANS_PER_DAY = 125
PLACE_SEARCHES_PER_DAY = 600
# Per client address, so one visitor can't use up the day. Typing two places is a few searches.
ROUTE_PLANS_PER_VISITOR = '10/hour'
PLACE_SEARCHES_PER_VISITOR = '60/hour'
# The site-wide daily counts. Inside the container, so a redeploy starts the day's counts again.
DAILY_QUOTA_PATH = Path(tempfile.gettempdir()) / 'truck-routing' / 'daily-quota.json'

RISK_RULES_PATH = Path(__file__).resolve().parent / 'rules' / 'risk_rules.json'


def build_risk_rules_source() -> RiskRulesSource:
    """A new source that reads and checks the rules file now. Moving the rules to a database replaces this."""
    return JsonRiskRules(RISK_RULES_PATH)


@cache
def get_risk_rules_source() -> RiskRulesSource:
    return build_risk_rules_source()


@cache
def get_plan_trip_service() -> PlanTripService:
    """Built on first use, so a missing key fails a request, not every management command."""
    api_key = _here_api_key()
    client = _http_client()
    return PlanTripService(
        HereRouter(client, api_key, deadline_seconds=ROUTING_DEADLINE_SECONDS),
        OpenMeteoForecast(client, batch_size=FORECAST_BATCH_SIZE, deadline_seconds=FORECAST_DEADLINE_SECONDS),
        get_risk_rules_source(),
        clock=lambda: datetime.now(UTC),
        max_route_miles=MAX_ROUTE_MILES,
        max_heatmap_points=MAX_HEATMAP_POINTS,
        forecast_dedupe_miles=FORECAST_DEDUPE_MILES,
    )


@cache
def get_search_places_service() -> SearchPlacesService:
    """Built on first use, like the plan service, and sharing its HTTP client."""
    return SearchPlacesService(
        HereGeocoder(_http_client(), _here_api_key(), deadline_seconds=GEOCODING_DEADLINE_SECONDS)
    )


@cache
def _http_client() -> httpx.Client:
    """One pooled client per process, shared by every adapter.

    Built lazily, after Gunicorn forks its workers, so no two processes share a socket.
    """
    client = httpx.Client(timeout=httpx.Timeout(HTTP_READ_TIMEOUT_SECONDS, connect=HTTP_CONNECT_TIMEOUT_SECONDS))
    atexit.register(client.close)
    return client


def _here_api_key() -> str:
    api_key: str = settings.HERE_API_KEY
    if not api_key:
        raise ImproperlyConfigured(
            'HERE_API_KEY is empty. Set it in backend/.env (see .env.example) to plan trips and search places.'
        )
    return api_key
