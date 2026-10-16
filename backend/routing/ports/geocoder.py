"""Where place search results come from."""

from typing import Protocol

from routing.domain.models import PlaceMatch


class Geocoder(Protocol):
    """Finds places that match free text, such as "Pittsburgh, PA".

    Returns at most `limit` matches, in provider order, best first. A result without usable
    coordinates is left out, never returned with a guess. Raises `ProviderError`, or
    `ProviderTimeoutError` when the provider runs out of time.
    """

    def search(self, query: str, limit: int) -> list[PlaceMatch]: ...
