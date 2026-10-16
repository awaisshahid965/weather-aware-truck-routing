"""Place search from HERE Geocoding v1.

Each item's `title` becomes the label and its `position` the coordinates. An item we cannot
use is dropped, not repaired: a label without trustworthy coordinates would send a route to
the wrong place. A malformed document as a whole is a provider error.
"""

import logging
import math
from collections.abc import Mapping

import httpx

from routing.adapters.provider_http import get_json
from routing.domain.models import GeoPoint, PlaceMatch
from routing.ports.errors import ProviderError

logger = logging.getLogger(__name__)

GEOCODE_URL = 'https://geocode.search.hereapi.com/v1/geocode'


class HereGeocoder:
    """Implements `Geocoder`."""

    def __init__(self, client: httpx.Client, api_key: str, *, deadline_seconds: float) -> None:
        self._client = client
        self._api_key = api_key
        self._deadline_seconds = deadline_seconds

    def search(self, query: str, limit: int) -> list[PlaceMatch]:
        params = {'q': query, 'limit': str(limit), 'apiKey': self._api_key}
        document = get_json(self._client, GEOCODE_URL, params, deadline_seconds=self._deadline_seconds)
        try:
            items = _array(_object(document, 'response').get('items'), 'items')
        except ValueError as exc:
            raise ProviderError(f'HERE returned places we cannot use: {exc}') from exc

        matches: list[PlaceMatch] = []
        for index, item in enumerate(items):
            try:
                matches.append(_match(item, f'items[{index}]'))
            except ValueError as exc:
                # The reason names the field and its type, never the query or the item's text.
                logger.info('here place dropped', extra={'provider_position': index, 'reason': str(exc)})
        return matches[:limit]


def _match(value: object, where: str) -> PlaceMatch:
    item = _object(value, where)
    place_id = _text(item.get('id'), f'{where}.id')
    label = _text(item.get('title'), f'{where}.title')
    position = _object(item.get('position'), f'{where}.position')
    latitude = _number(position.get('lat'), f'{where}.position.lat')
    longitude = _number(position.get('lng'), f'{where}.position.lng')
    try:
        return PlaceMatch(place_id=place_id, label=label, point=GeoPoint(latitude=latitude, longitude=longitude))
    except ValueError as exc:
        raise ValueError(f'{where}: {exc}') from exc


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
    # bool is a subclass of int, and `true` must not read as 1 degree.
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f'{where} must be a number; got {type(value).__name__}')
    try:
        number = float(value)
    except OverflowError:  # an integer too large for a float
        number = math.inf
    # JSON has no NaN, but Python reads 1e999 as infinity.
    if not math.isfinite(number):
        raise ValueError(f'{where} must be finite')
    return number
