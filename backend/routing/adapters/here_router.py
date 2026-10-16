"""Truck routes from HERE Routing v8.

HERE splits a route into sections, each with its own polyline and summary. Each polyline
is decoded on its own: every encoded string starts with its own header, so joining them
would corrupt the shape. The format is HERE's flexible polyline, not Google's.
"""

import logging
import math
from collections.abc import Mapping
from datetime import UTC, datetime

import flexpolyline  # type: ignore[import-untyped]  # the package ships no type hints
import httpx

from routing.adapters.provider_http import get_json
from routing.domain.models import GeoPoint, RouteCandidate, RouteSection
from routing.ports.errors import ProviderError

logger = logging.getLogger(__name__)

ROUTES_URL = 'https://router.hereapi.com/v8/routes'
METERS_PER_MILE = 1609.344
ALTERNATIVES = 2  # the main route plus up to two alternatives
MAX_ROUTES = 1 + ALTERNATIVES


class HereRouter:
    """Implements `RouteProvider`."""

    def __init__(self, client: httpx.Client, api_key: str, *, deadline_seconds: float) -> None:
        self._client = client
        self._api_key = api_key
        self._deadline_seconds = deadline_seconds

    def find_routes(self, origin: GeoPoint, destination: GeoPoint, departure_at: datetime) -> list[RouteCandidate]:
        # The load is not sent as truck weight. It drives weather risk only; HERE keeps its default truck.
        params = {
            'transportMode': 'truck',
            'routingMode': 'fast',
            'origin': _here_point(origin),
            'destination': _here_point(destination),
            'departureTime': _here_time(departure_at),
            'alternatives': str(ALTERNATIVES),
            'return': 'polyline,summary,routeLabels',
            'apiKey': self._api_key,
        }
        document = get_json(self._client, ROUTES_URL, params, deadline_seconds=self._deadline_seconds)
        try:
            routes = _distinct_routes(document)
        except ValueError as exc:
            raise ProviderError(f'HERE returned routes we cannot use: {exc}') from exc
        return [RouteCandidate(provider_index=index, sections=sections) for index, sections in enumerate(routes)]


def _here_point(point: GeoPoint) -> str:
    return f'{point.latitude},{point.longitude}'


def _here_time(moment: datetime) -> str:
    if moment.utcoffset() is None:
        raise ValueError('departure_at must be timezone-aware')
    return moment.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


def _distinct_routes(document: object) -> list[tuple[RouteSection, ...]]:
    """Each route's sections, in provider order, without exact duplicates, at most `MAX_ROUTES`."""
    response = _object(document, 'response')
    entries = _array(response.get('routes'), 'routes')
    if not entries:
        logger.info('here found no route', extra={'notice_codes': _notice_codes(response.get('notices'))})
        return []

    # Keyed by the encoded polylines in order: two routes with the same ones are the same road.
    routes: dict[tuple[str, ...], tuple[RouteSection, ...]] = {}
    for index, entry in enumerate(entries):
        polylines, sections = _route(entry, f'routes[{index}]')
        if polylines in routes:
            logger.info('here duplicate route dropped', extra={'provider_position': index})
            continue
        routes[polylines] = sections
    return list(routes.values())[:MAX_ROUTES]


def _route(value: object, where: str) -> tuple[tuple[str, ...], tuple[RouteSection, ...]]:
    entries = _array(_object(value, where).get('sections'), f'{where}.sections')
    if not entries:
        raise ValueError(f'{where} has no sections')
    parsed = [_section(entry, f'{where}.sections[{index}]') for index, entry in enumerate(entries)]
    # Every checkpoint ETA is departure plus a share of this; zero would put the whole route at departure.
    if not math.fsum(section.duration_seconds for _, section in parsed) > 0:
        raise ValueError(f'{where} has a total duration of 0 s')
    return tuple(polyline for polyline, _ in parsed), tuple(section for _, section in parsed)


def _section(value: object, where: str) -> tuple[str, RouteSection]:
    section = _object(value, where)
    polyline = _text(section.get('polyline'), f'{where}.polyline')
    summary = _object(section.get('summary'), f'{where}.summary')
    points = _points(polyline, f'{where}.polyline')
    length_miles = _number(summary.get('length'), f'{where}.summary.length') / METERS_PER_MILE
    duration_seconds = _number(summary.get('duration'), f'{where}.summary.duration')
    try:
        return polyline, RouteSection(points=points, length_miles=length_miles, duration_seconds=duration_seconds)
    except ValueError as exc:
        raise ValueError(f'{where}: {exc}') from exc


def _points(encoded: str, where: str) -> tuple[GeoPoint, ...]:
    try:
        # A third dimension, such as elevation, is dropped.
        return tuple(GeoPoint(latitude=row[0], longitude=row[1]) for row in flexpolyline.decode(encoded))
    except (ValueError, RuntimeError) as exc:
        # The decoder raises RuntimeError when the string ends inside its header.
        raise ValueError(f'{where} is not a valid flexible polyline: {exc}') from exc


def _notice_codes(value: object) -> list[str]:
    # Notices only explain an answer, so a malformed one is skipped instead of failing the plan.
    if not isinstance(value, list):
        return []
    return [notice['code'] for notice in value if isinstance(notice, dict) and isinstance(notice.get('code'), str)]


def _object(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f'{where} must be an object; got {type(value).__name__}')
    return value


def _array(value: object, where: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f'{where} must be a list; got {type(value).__name__}')
    return value


def _text(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f'{where} must be a string; got {type(value).__name__}')
    return value


def _number(value: object, where: str) -> float:
    # bool is a subclass of int, and `true` must not read as 1 m.
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f'{where} must be a number; got {type(value).__name__}')
    try:
        number = float(value)
    except OverflowError:  # an integer too large for a float
        number = math.inf
    if not math.isfinite(number):
        raise ValueError(f'{where} must be finite')
    return number
