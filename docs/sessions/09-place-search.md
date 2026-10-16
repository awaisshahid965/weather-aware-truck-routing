# Session 09 — Place search

| | |
|---|---|
| Covers | Section 3 inputs: origin and destination. AC: "A driver can enter origin, destination, …" (backend half) |
| Needs | 08 (error handler, request ID, bootstrap) |
| Layer | Backend port + adapter + service + HTTP |
| Branch | `feat/place-search` · commit type `feat(backend)` |
| Files | `backend/routing/domain/models.py`, `backend/routing/ports/geocoder.py`, `backend/routing/adapters/here_geocoder.py`, `backend/routing/services/search_places.py`, `backend/routing/bootstrap.py`, `backend/routing/http/serializers.py`, `backend/routing/http/views.py`, `backend/routing/http/urls.py`, `backend/tests/services/fakes.py`, `backend/tests/services/test_search_places.py`, `backend/tests/adapters/test_here_geocoder.py`, `backend/tests/http/test_places.py`, `backend/tests/adapters/fixtures/here/geocode_*.json` |

## Goal

`GET /api/v1/places?q=...` returns up to five places with coordinates.

## Read first

- [Contract → `GET /api/v1/places`](contract.md#get-apiv1placesq).
- [Contract → Providers](contract.md#providers): HERE Geocoding.

## Build

### 1. Domain type and port

```python
@dataclass(frozen=True, slots=True)
class PlaceMatch:  # domain/models.py
    place_id: str  # opaque provider id; the API calls it `id`
    label: str
    point: GeoPoint


class Geocoder(Protocol):  # ports/geocoder.py
    def search(self, query: str, limit: int) -> list[PlaceMatch]: ...
```

### 2. Service (`services/search_places.py`)

- Trim the query and collapse whitespace.
- Fewer than 3 non-space characters → `InputValidationError('q', …)`.
- Over 200 characters → `InputValidationError('q', …)`.
- Always ask for `limit=5`.
- Translate `ProviderError` / `ProviderTimeoutError` into `UpstreamError` / `UpstreamTimeoutError`, as in Session 07.

### 3. Record fixtures

```bash
curl -s "https://geocode.search.hereapi.com/v1/geocode?q=Pittsburgh&limit=5&apiKey=$HERE_API_KEY" \
  | jq . > backend/tests/adapters/fixtures/here/geocode_pittsburgh.json
```

Hand-edit one variant where an item has no `position`.

### 4. Adapter (`adapters/here_geocoder.py`)

```python
class HereGeocoder:
    def __init__(self, client: httpx.Client, api_key: str, *, deadline_seconds: float) -> None: ...
```

- Use `get_json` from Session 04.
- Map `id`, `title` and `position.lat` / `position.lng`.
- Drop malformed items: a missing position, or non-finite coordinates.
- Keep provider order.

### 5. Wiring and HTTP

- `bootstrap.py`: build `HereGeocoder` with `GEOCODING_DEADLINE_SECONDS`. Expose `get_search_places_service()`.
- `GET /api/v1/places?q=...` → `200 [{id, label, latitude, longitude}]`.
- Errors go through the handler from Session 08.

## Tests

- `FakeGeocoder` in `tests/services/fakes.py` records queries.
- The fixture maps to up to 5 results, in order.
- An item without a position is dropped.
- `q="ab"` → 400. `q="   abc  "` → passes as `abc`.
- A 201-character query → 400.
- Provider 5xx after retries → 502. Timeout → 504.
- The response has exactly the contract fields. No raw HERE fields leak.
- The key never appears in a body or log.

## Done when

- [x] `uv run poe check` passes.

## Not in this session

- Debounce, keyboard selection, UI (11).
- Upstream rate limiting. Session 15 lists it as optional, because it needs a new error code.

## Pitfalls

- Never accept a label without coordinates downstream. The route plan uses coordinates only.
- `id` is opaque. Never fetch a URL built from it.
