"""Search places by name, for the trip form's origin and destination.

The service owns the query rules, so every client gets the same answer. It only finds
candidates: the driver picks one, and the route plan uses that pick's coordinates.
"""

from routing.domain.models import PlaceMatch
from routing.ports.geocoder import Geocoder
from routing.services.errors import InputValidationError, provider_errors

MIN_QUERY_CHARACTERS = 3  # not counting spaces; fewer matches too much to be useful
MAX_QUERY_CHARACTERS = 200
MAX_MATCHES = 5


class SearchPlacesService:
    def __init__(self, geocoder: Geocoder) -> None:
        self._geocoder = geocoder

    def run(self, query: str) -> list[PlaceMatch]:
        """Up to `MAX_MATCHES` places in provider order, best first, or a service error.

        The query is trimmed and each run of whitespace becomes one space before it is checked,
        so the limits apply to the text the provider sees.
        """
        text = ' '.join(query.split())
        if len(text.replace(' ', '')) < MIN_QUERY_CHARACTERS:
            raise InputValidationError('q', f'must have at least {MIN_QUERY_CHARACTERS} characters other than spaces')
        if len(text) > MAX_QUERY_CHARACTERS:
            raise InputValidationError('q', f'must be at most {MAX_QUERY_CHARACTERS} characters')
        with provider_errors('geocoding'):
            matches = self._geocoder.search(text, MAX_MATCHES)
        return matches[:MAX_MATCHES]
