# Session 08 — Route plans API

| | |
|---|---|
| Covers | Section 3 inputs (backend validation). Exposes the FR-01–04 and FR-06 data. |
| Needs | 07 |
| Layer | Backend HTTP + composition root |
| Branch | `feat/route-plans-api` · commit type `feat(backend)` |
| Files | `backend/routing/bootstrap.py`, `backend/routing/checks.py`, `backend/routing/apps.py`, `backend/tests/test_checks.py`, `backend/routing/http/serializers.py`, `backend/routing/http/views.py`, `backend/routing/http/urls.py`, `backend/routing/http/errors.py`, `backend/routing/http/middleware.py`, `backend/routing/domain/geometry.py`, `backend/config/settings.py` (two entries), `backend/tests/http/test_route_plans.py`, `backend/tests/http/test_middleware.py`, `backend/tests/http/test_route_plans_live.py`, `backend/tests/domain/test_geometry.py` |

## Goal

`POST /api/v1/route-plans` returns the contract JSON. Every failure returns the contract error shape. Each request is logged once, with an ID.

## Read first

- [Contract](contract.md), all of it.
- `backend/CONVENTIONS.md` → Composition root, Errors, HTTP API, Logging.

## Build

### 1. Composition root (`routing/bootstrap.py`)

- Name the [contract limits](contract.md#limits) as module constants.
- Build one shared `httpx.Client` with the connect and read timeouts. Close it with `atexit`.
- Read `settings.HERE_API_KEY`. When it is empty, raise `ImproperlyConfigured` with a clear message on first use.
- `RISK_RULES_PATH = Path(__file__).resolve().parent / 'rules' / 'risk_rules.json'`.
- `build_risk_rules_source()` returns `JsonRiskRules(RISK_RULES_PATH)`, uncached. `get_risk_rules_source()` caches it. Switching to a database later replaces this one function.
- Build `HereRouter`, `OpenMeteoForecast` and `PlanTripService`, passing `get_risk_rules_source()`. Pass `clock=lambda: datetime.now(UTC)`.
- Expose `get_plan_trip_service()`, cached so it builds once.

### 1b. Fail the deploy on bad rules (`routing/checks.py`)

- A Django system check calls `bootstrap.build_risk_rules_source()`. On `RiskRulesUnavailableError` it returns `Error(..., id='routing.E001')` with the reason.
- Register it in `RoutingConfig.ready()` (`routing/apps.py`) with `register(check_risk_rules)`. An explicit call needs no side-effect import.
- The container runs `check --deploy` before serving, and CI runs it too. A bad rules file then stops the deploy, not the first request. `runserver` runs it on start.

### 2. Request serializer (`http/serializers.py`)

- Field names exactly as in the contract (camelCase).
- Coordinates finite and in range.
- `departureAt`: ISO 8601 with a trailing `Z` only.
- `departureTimeZone`: a valid IANA name (`zoneinfo.ZoneInfo`; tzdata ships with the scaffold).
- `loadWeightLb` finite and ≥ 0. `checkpointIntervalMiles` is 10, 25 or 50. Labels non-empty, ≤ 200 characters.
- Build `PlanTripInput`. Business rules (future time, distinct endpoints) stay in the service.

### 3. Response mapping (`http/serializers.py`)

A plain function `present_trip_plan(plan: TripPlan) -> dict[str, object]` is enough.

- Route ids `route-1` … `route-3` in provider order. Names `Route 1` … `Route 3`.
- `risk` is `level.value`. `riskScore` is `level.score`. `drivers` as strings.
- All times are UTC with `Z`.
- Geometry: GeoJSON `LineString`, `[lon, lat]`. Join the section points and drop each repeated boundary point.
- Simplify the geometry for display (step 6). Round output coordinates to 5 decimals.
- A `recommended` flag per route. `recommendedRouteId` or `null`.
- Heatmap block: `variable: "combinedRisk"`, `startAt` = `departureAt`, `stepHours: 1`, 49 frames.

### 4. Error handler (`http/errors.py`)

```python
def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response: ...
```

| Exception | Status | `code` |
|---|---|---|
| DRF `ValidationError`, `InputValidationError` | 400 | `VALIDATION_ERROR` (`details`: field → messages) |
| `InsufficientRoutesError` | 422 | `INSUFFICIENT_ROUTES` (`details.availableCount`) |
| `ForecastUnavailableError` | 422 | `FORECAST_UNAVAILABLE` |
| `UpstreamTimeoutError` | 504 | `PROVIDER_TIMEOUT` |
| `UpstreamError` | 502 | `PROVIDER_ERROR` |
| Any other DRF `APIException` | its status | a matching code, e.g. `UNSUPPORTED_MEDIA_TYPE` |
| Anything else | 500 | `INTERNAL_ERROR`, generic message, logged with `logger.exception` |

- Check `UpstreamTimeoutError` before `UpstreamError`; it is a subclass.
- The body is `{ "error": { "code", "message", "details" }, "requestId" }`.
- Register it in `config/settings.py`: `REST_FRAMEWORK['EXCEPTION_HANDLER'] = 'routing.http.errors.api_exception_handler'`. A dotted-path string is allowed by the layer rules.

### 5. Request ID and request log (`http/middleware.py`)

- Use the incoming `X-Request-ID` if it matches `^[A-Za-z0-9-]{1,64}$`. Otherwise generate a `uuid4`.
- Keep it in a `ContextVar`, so the error handler and logs read it without untyped request attributes.
- Echo it in the `X-Request-ID` response header.
- Log one line per request: `logger.info('request completed', extra={...})` with `method`, `path`, `status`, `duration_ms` and `request_id`. Never log labels, coordinates or keys.
- Register it in `config/settings.py` `MIDDLEWARE`, right **after** `HealthCheckMiddleware`. Health probes then stay unlogged.

The scaffold README lists the error handler and this middleware as feature work. These two `settings.py` entries are part of this session, not setup.

### 6. Display simplification (`domain/geometry.py`)

`simplify(points, tolerance_miles=0.01)`: Ramer–Douglas–Peucker, standard library only. Use it for display only. Never simplify before sampling.

### 7. View and route

- `http/views.py`: parse → `bootstrap.get_plan_trip_service().run(...)` → present → 200. Nothing else.
- `http/urls.py`: add `route-plans`.

### 8. Live smoke test

Mark it `@pytest.mark.live`. POST the contract's Pittsburgh → Cleveland trip with a departure 2 hours ahead. Assert 200 or `INSUFFICIENT_ROUTES`. Both are honest answers.

## Tests

Override the service with a fake: `monkeypatch.setattr(bootstrap, 'get_plan_trip_service', ...)`.

- **200:** keys match the contract. 3 routes, 49 frames. Times end with `Z`. Coordinates are `[lon, lat]`, so a US trip's first value is negative.
- Each invalid field → 400, and `details` names the field.
- `departureAt: "2026-10-16T12:00:00+05:00"` → 400.
- Each service error → the right status and code. `requestId` appears in the body and the header.
- A non-JSON body → 415 in the contract error shape.
- An unexpected exception → 500, with no stack trace or exception text in the body.
- A valid incoming `X-Request-ID` is echoed. An invalid one is replaced.
- `/healthz` still answers and logs nothing.
- **Secrets:** set `settings.HERE_API_KEY` to a sentinel. It never appears in any body or log record.
- **Simplify:** collinear points → endpoints only. Max deviation ≤ tolerance. Endpoints always kept.
- **Rules check:** the shipped file → no errors. `RISK_RULES_PATH` pointed at a broken file (`monkeypatch`) → one `routing.E001` naming the reason.

## Done when

- [ ] `uv run poe check` passes. The import contracts confirm `http` reaches adapters only through `bootstrap`.
- [ ] `curl -X POST localhost:8000/api/v1/route-plans` with a real key returns a plan or a contract error.
- [ ] Breaking `risk_rules.json` locally makes `uv run python manage.py check` fail with `routing.E001`. Restore the file afterwards.

## Not in this session

- The places endpoint (09). Caching (left out on purpose; see contract → Product boundaries).

## Pitfalls

- `[lat, lon]` vs `[lon, lat]`. Only this layer flips the order.
- An `if` about risk in a view belongs in the domain.
- Views must call `bootstrap.get_plan_trip_service()` through the module. Importing the function directly defeats `monkeypatch`.
- DRF's handler covers exceptions raised in views only. Middleware errors still get Django's plain 500.
- `extra=` keys must not reuse `LogRecord` attribute names such as `name`, `message`, `module` or `args`. `logging` raises `KeyError` if they do.
- The system check must use the **uncached** builder. A cached failure, or a cached good file, would hide the real state of the file.
