# Session 04 — HERE routing adapter (FR-01)

| | |
|---|---|
| Covers | FR-01. AC: "The app retrieves and displays three route alternatives when the routing provider supplies them." (backend half) |
| Needs | 02 (route types) |
| Layer | Backend port + adapter |
| Branch | `feat/here-routing-adapter` · commit type `feat(backend)` |
| Files | `backend/routing/ports/errors.py`, `backend/routing/ports/route_provider.py`, `backend/routing/adapters/provider_http.py`, `backend/routing/adapters/here_router.py`, `backend/tests/adapters/test_provider_http.py`, `backend/tests/adapters/test_here_router.py`, `backend/tests/adapters/test_here_router_live.py`, `backend/tests/adapters/fixtures/here/*.json` |

## Goal

Ask HERE for a truck route plus two alternatives. Return them as `RouteCandidate`s. Fail only with the port's typed errors.

## Read first

- [Contract → Providers](contract.md#providers): HERE Routing v8 and the "All providers" rules.
- [Contract → Limits](contract.md#limits): timeouts and the routing deadline.

## Build

### 1. Port errors (`ports/errors.py`)

Add these to the file Session 01 created.

```python
class ProviderError(Exception):
    """A provider failed, rejected the request, or returned data we cannot use."""


class ProviderTimeoutError(ProviderError):
    """A provider did not answer within the deadline."""
```

### 2. Port (`ports/route_provider.py`)

```python
class RouteProvider(Protocol):
    def find_routes(self, origin: GeoPoint, destination: GeoPoint, departure_at: datetime) -> list[RouteCandidate]: ...
```

It returns 0–3 distinct routes in provider order. It never invents routes.

### 3. Shared provider HTTP helper (`adapters/provider_http.py`)

Every adapter uses one function:

```python
def get_json(client: httpx.Client, url: str, params: Mapping[str, str], *, deadline_seconds: float) -> object: ...
```

- Retry at most 2 times, only for timeouts, connection errors, 429 and 5xx.
- Back off with jitter. Respect `Retry-After` if it fits in the deadline.
- Past the total deadline → `ProviderTimeoutError`.
- Reject bodies over a size limit (for example 5 MB) → `ProviderError`.
- Never retry any other 4xx.
- Catch every httpx exception here. httpx errors never leave an adapter.
- Logs and errors show the URL path only. The query string holds the key.

### 4. Record fixtures

Record one real response once. Use a future departure time.

```bash
curl -s "https://router.hereapi.com/v8/routes?transportMode=truck&routingMode=fast\
&origin=40.4406,-79.9959&destination=41.4993,-81.6944\
&departureTime=<future UTC, e.g. 2026-10-20T12:00:00Z>&alternatives=2\
&return=polyline,summary,routeLabels&apiKey=$HERE_API_KEY" \
  | jq . > backend/tests/adapters/fixtures/here/routes_three.json
```

Check it holds 3 routes. Then hand-edit small variants:

| Fixture | Edit |
|---|---|
| `routes_one.json` | Keep one route |
| `routes_empty.json` | Recorded: `origin=999,999`. HERE answers 200 with `"routes": []` and a `couldNotMatchOrigin` notice |
| `routes_duplicate.json` | Two routes with identical section polylines |
| `routes_bad_section.json` | A section without `polyline` |
| `error_400.json` | Recorded: `origin=not-a-place`. HERE answers 400 with its error body |

### 5. Adapter (`adapters/here_router.py`)

```python
class HereRouter:
    def __init__(self, client: httpx.Client, api_key: str, *, deadline_seconds: float) -> None: ...
```

- Use the params from the contract. Send `departureTime` as UTC with `Z`.
- For each route, for each section:
  - Decode `section.polyline` with `flexpolyline.decode`. Keep lat and lng only.
  - `length_miles = summary.length / 1609.344`
  - `duration_seconds = summary.duration`
- Narrow the JSON to typed values right away. No raw dict goes past this module.
- Validate: at least 2 points per section, and route length and duration above 0. Otherwise raise `ProviderError`.
- Drop exact duplicates: the same section polylines in the same order.
- Empty `routes` → return `[]`. Log HERE's notice codes with `extra=`, never the key.
- Keep provider order: `provider_index` 0, 1, 2.

### 6. Live test (`test_here_router_live.py`)

Mark it `@pytest.mark.live`. Read the key from `django.conf.settings.HERE_API_KEY`; skip when it's empty. Assert that at least one route comes back. Run it with `uv run poe test:live`.

## Tests

Use `httpx.MockTransport`. No network.

**HTTP helper:**

- 503 then 200 → success, 2 calls.
- 400 → `ProviderError`, 1 call.
- 429 with `Retry-After: 0`, then 200 → success.
- Timeouts until the deadline → `ProviderTimeoutError`, at most 3 calls.
- Oversized body → `ProviderError`.
- The key value never appears in error messages or log records (`caplog`).

**Adapter:**

- `routes_three.json` → 3 candidates. Sections preserved.
- The first point is near the origin and the last near the destination (< 1 mi).
- 1609.344 m → 1.0 mi.
- `routes_one.json` → 1 candidate. Nothing synthesized.
- `routes_duplicate.json` → 1 candidate.
- `routes_empty.json` → `[]`.
- `routes_bad_section.json` → `ProviderError`.
- Request params include `transportMode=truck` and `alternatives=2`, and `departureTime` ends with `Z`.

## Done when

- [x] `uv run poe check` passes. The import contracts confirm the adapter imports neither `services` nor `http`.
- [x] Fixtures contain no API key.

## Not in this session

- What "fewer than 3" means for the user. Session 07 raises `InsufficientRoutesError`.
- Wiring the adapter into `bootstrap.py` (08).

## Pitfalls

- Decode **per section**. Don't join polyline strings.
- HERE flexible polyline is not Google's polyline format.
- Ruff rule `S311` flags `random` used for jitter. Jitter isn't security-sensitive. Add `# noqa: S311` on that one line, with the reason.
- Don't send load as truck weight. Load only drives weather risk (contract → Product boundaries).
- httpx logs every request's full URL at INFO, key included. The backend scaffold sets the `httpx` logger to WARNING. The `caplog` key test runs at DEBUG, so it fails if that setting goes.
