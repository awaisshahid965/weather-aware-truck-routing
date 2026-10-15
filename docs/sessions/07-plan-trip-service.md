# Session 07 — PlanTrip service (FR-01 to FR-04, FR-06)

| | |
|---|---|
| Covers | The full calculation behind `POST /api/v1/route-plans`. |
| Needs | 01–06 |
| Layer | Backend service |
| Branch | `feat/plan-trip-service` · commit type `feat(backend)` |
| Files | `backend/routing/services/errors.py`, `backend/routing/services/plan_trip.py`, `backend/tests/services/__init__.py`, `backend/tests/services/fakes.py`, `backend/tests/services/test_plan_trip.py` |

## Goal

One method runs the whole pipeline. It talks only to ports. Tests use fakes.

## Read first

- [Contract → `POST /api/v1/route-plans`](contract.md#post-apiv1route-plans): the validation list.
- [Contract → Errors](contract.md#errors) and [Limits](contract.md#limits).
- [Contract → Risk policy](contract.md#risk-policy), items 7–9.

## Build

### Input and output (`plan_trip.py`)

```python
@dataclass(frozen=True, slots=True)
class Place:
    label: str
    point: GeoPoint


@dataclass(frozen=True, slots=True)
class PlanTripInput:
    origin: Place
    destination: Place
    departure_at: datetime  # aware UTC, authoritative
    departure_time_zone: str  # display only
    load_weight_lb: float
    checkpoint_interval_miles: int


@dataclass(frozen=True, slots=True)
class PlannedRoute:
    candidate: RouteCandidate
    checkpoints: tuple[AssessedCheckpoint, ...]
    summary: RouteSummary
    eta_at: datetime


@dataclass(frozen=True, slots=True)
class TripPlan:
    generated_at: datetime
    request: PlanTripInput
    routes: tuple[PlannedRoute, ...]
    recommended_index: int | None
    heatmap: tuple[HeatmapFrame, ...]
    notices: tuple[str, ...]
    rules_version: str  # which rules produced this plan
```

### Service errors (`services/errors.py`)

| Error | Raised when | HTTP code (Session 08) |
|---|---|---|
| `InputValidationError(field, message)` | A business rule on the input fails | `VALIDATION_ERROR` |
| `InsufficientRoutesError(available_count)` | Fewer than 3 routes | `INSUFFICIENT_ROUTES` |
| `ForecastUnavailableError(reason)` | Any `ForecastGapError` | `FORECAST_UNAVAILABLE` |
| `UpstreamError` | A port raised `ProviderError` | `PROVIDER_ERROR` |
| `UpstreamTimeoutError(UpstreamError)` | A port raised `ProviderTimeoutError` | `PROVIDER_TIMEOUT` |

- The service translates port errors into these, chained with `from`. The HTTP layer then imports only service errors.
- `field` uses the contract's names, such as `departureAt`.

### Constructor

```python
class PlanTripService:
    def __init__(
        self,
        routes: RouteProvider,
        forecast: ForecastProvider,
        risk_rules: RiskRulesSource,
        *,
        clock: Callable[[], datetime],
        max_route_miles: float,
        max_heatmap_points: int,
        forecast_dedupe_miles: float,
    ) -> None: ...

    def run(self, request: PlanTripInput) -> TripPlan: ...
```

Inject the clock. Tests need a fixed "now". The composition root (Session 08) passes the constants from the contract.

### `run()` steps

1. **Validate.**
   - `departure_at` is aware and after now.
   - `departure_at + 48 h ≤ now + forecast.max_lead_hours`.
   - Origin and destination are at least 0.1 mi apart.
   - Load is finite and ≥ 0. The interval is 10, 25 or 50.
2. **Routes.** `routes.find_routes(...)`. Fewer than 3 → `InsufficientRoutesError(len)`. More than 3 → keep the first 3.
3. **Length cap.** Any route over `max_route_miles` → `InputValidationError`. Check this before any weather call.
4. **Checkpoints** per route (Session 02).
5. **Corridor points** (Session 06).
6. **Dedupe forecast points.** Take all checkpoints plus corridor points. A point within `forecast_dedupe_miles` of a kept point reuses it. Keep an index map from original point to kept point.
7. **Window.** Start is `departure_at` floored to the hour. End is `max(last ETA, departure + 48 h)` ceiled to the hour.
8. **Fetch.** `forecast.hourly(kept_points, start, end)`, as one call.
9. **Rules.** `rules = self._risk_rules.current()`, **once**. Pass this one value to every `classify` and to `build_frames`. A rule change mid-request then can't mix two rule sets in one plan.
10. **Classify.** For each checkpoint: `sample_at` → `classify(..., rules)` → `AssessedCheckpoint`.
11. **Summaries** (Session 03) and **frames** (Session 06, with the same `rules`).
12. **Recommend.** If `None`, add the No Travel notice.
13. **Notices.** Always add: "Forecast risk is an estimate, not a road-closure or dispatch clearance."
14. **Gaps.** A `ForecastGapError` anywhere → `ForecastUnavailableError`. Never return a partial plan.
15. **Log** one line: `logger.info('trip planned', extra={...})` with `rules_version`, route count, checkpoint count, forecast point count and elapsed ms. Never log labels or coordinates.

## Tests

`tests/services/fakes.py`:

- `FakeRouteProvider(routes)` records its calls.
- `FakeForecastProvider(values_at)` builds series from `values_at(point, hour)`. It records the requested points and window. `max_lead_hours` is settable.
- `FakeRiskRulesSource(rules)` returns the given rules (default `SPEC_RULES`) and counts calls.

Cases:

- **Happy path:** 3 straight routes, calm weather → 3 routes, 49 frames, checkpoints at the interval, and the recommended route is the one with the shortest duration.
- 2 routes → `InsufficientRoutesError(2)`. Forecast never called.
- Wind 60 mph everywhere → recommended `None`, No Travel notice present.
- Null at one checkpoint's hour → `ForecastUnavailableError`.
- Series ends before the last ETA → `ForecastUnavailableError`.
- Overlapping routes → fewer points requested than raw points. Kept points are ≥ 3 mi apart.
- Window: start ≤ departure. End ≥ last ETA and ≥ departure + 48 h.
- Departure in the past (fixed clock) → `InputValidationError('departureAt', …)`.
- Departure beyond the forecast range → `InputValidationError('departureAt', …)`.
- Same origin and destination → `InputValidationError`.
- Route over `max_route_miles` → `InputValidationError`. Forecast never called.
- Fake raises `ProviderTimeoutError` → `UpstreamTimeoutError`, with the original as `__cause__`.
- **Rules:** `current()` is called exactly once per `run()`. `TripPlan.rules_version` matches the source.
- **Rules are injected:** the same weather with stricter rules → a different recommendation or summary.

## Done when

- [ ] `uv run poe check` passes. The import contracts confirm the service imports no adapter, Django or httpx.

## Not in this session

- JSON and HTTP status codes (08). Real providers in `bootstrap.py` (08).

## Pitfalls

- Keep `run()` short. Each step is a small private method or one domain call.
- One forecast call for everything, not one per route.
- Dedupe is O(n²). That's fine at a few hundred points. Measure before optimizing.
- Services never read Django settings. Every limit arrives through the constructor.
- Don't call `current()` inside the per-checkpoint loop. Once per plan, or a database source could change rules mid-plan.
