# Session 05 — Forecast adapter and forecast at ETA (FR-02, part 2)

| | |
|---|---|
| Covers | FR-02 forecast at arrival. AC: "Forecast lookups use each checkpoint's estimated arrival time." |
| Needs | 01, 04 (provider HTTP helper, port errors) |
| Layer | Backend domain + port + adapter |
| Branch | `feat/forecast-adapter` · commit type `feat(backend)` |
| Files | `backend/routing/domain/models.py`, `backend/routing/domain/errors.py`, `backend/routing/domain/forecast.py`, `backend/routing/ports/errors.py`, `backend/routing/ports/forecast_provider.py`, `backend/routing/adapters/provider_http.py`, `backend/routing/adapters/open_meteo_forecast.py`, `backend/tests/domain/test_forecast.py`, `backend/tests/adapters/fakes.py`, `backend/tests/adapters/test_provider_http.py`, `backend/tests/adapters/test_open_meteo_forecast.py`, `backend/tests/adapters/test_open_meteo_forecast_live.py`, `backend/tests/adapters/fixtures/open_meteo/*.json` |

## Goal

Fetch hourly wind, rain and snow for many points. Pick the right hour for any moment. Turn it into a `WeatherSample`.

## Read first

- [Contract → Risk policy](contract.md#risk-policy), items 4 and 8.
- [Contract → Providers](contract.md#providers): Open-Meteo.
- [Contract → Limits](contract.md#limits): batch size and the forecast deadline.

## Build

### 1. Series type (`domain/models.py`)

```python
@dataclass(frozen=True, slots=True)
class HourlySeries:
    hours: tuple[datetime, ...]  # aware UTC, ascending, 1 h apart
    wind_mph: tuple[float | None, ...]
    rain_in_per_hour: tuple[float | None, ...]  # rain + showers
    snow_in_per_hour: tuple[float | None, ...]
```

It lives in the domain, so domain code can read it. The port imports it from there.

### 2. Domain error (`domain/errors.py`)

```python
class ForecastGapError(Exception):
    """No valid forecast value exists for the moment asked about."""
```

### 3. Forecast at a moment (`domain/forecast.py`)

```python
def sample_at(series: HourlySeries, at: datetime) -> WeatherSample: ...
```

- Pick the first hour **at or after** `at`. On an exact hour, use that hour.
- The picked hour must be less than 1 h after `at`. Otherwise the series doesn't cover `at` → `ForecastGapError`.
- No such hour → `ForecastGapError`.
- None, NaN or a negative value at the picked hour → `ForecastGapError`.
- Gaps at hours you don't pick don't matter.

Why at-or-after: rain and snow are sums over the preceding hour. The hour that ends after arrival covers the arrival moment.

### 4. Port (`ports/forecast_provider.py`)

```python
class ForecastProvider(Protocol):
    @property
    def max_lead_hours(self) -> int: ...

    def hourly(self, points: Sequence[GeoPoint], start_at: datetime, end_at: datetime) -> list[HourlySeries]: ...
```

- `max_lead_hours` is a conservative bound on how far ahead the provider forecasts. Callers check against it first. It is not a promise.
- `hourly` returns one series per point, in the order of `points`.
- Each series covers every hour `sample_at` reads for a moment from `start_at` to `end_at`: the first hour at or after `start_at`, through the first hour at or after `end_at`.
- When the forecast doesn't reach the whole window, `hourly` raises `ForecastRangeError`. Add it to `ports/errors.py`. It is **not** a `ProviderError`: the provider answered, but the request reaches too far ahead. Session 07 reports it as a validation error on `departureAt`.

```python
class ForecastRangeError(Exception):
    """The forecast does not reach the whole window asked about."""
```

### 5. Record fixtures

```bash
curl -s "https://api.open-meteo.com/v1/forecast?latitude=40.44,41.50&longitude=-79.99,-81.69\
&hourly=wind_speed_10m,rain,showers,snowfall&wind_speed_unit=mph&precipitation_unit=inch\
&timeformat=unixtime&timezone=GMT&forecast_days=3" \
  | jq . > backend/tests/adapters/fixtures/open_meteo/two_points.json
```

- Record a one-point response too. It is an object, not a list.
- Record one without the unit params. That gives you the metric unit strings.
- Hand-edit variants: nulls, mismatched array lengths, an unknown unit.
- Record the range's end: a window past it (400 `out of allowed range`), and a window over the last hours of day 16 (every value `null`). Record one other 400 too, such as an unknown variable.
- Copy the exact `hourly_units` strings into the converter table.

### 6. Adapter (`adapters/open_meteo_forecast.py`)

```python
class OpenMeteoForecast:
    def __init__(self, client: httpx.Client, *, batch_size: int, deadline_seconds: float) -> None: ...
```

- Use the params from the contract. Bound the time window to the request; Open-Meteo has `start_hour` and `end_hour` for this.
- Split points into batches of `batch_size`. All batches share **one** deadline.
- Format coordinates with 4 decimals.
- Normalize the shape: one point gives an object, many give a list.
- Match results by **index**, not coordinates. Open-Meteo snaps to its grid and returns different lat/lon.
- Every hourly array must have the length of `time`. Otherwise raise `ProviderError`.
- Units: map each unit string to a factor (mph, km/h, m/s; inch, mm, cm). An unknown string → `ProviderError`.
- Parse JSON with `parse_float=Decimal`. Add `parse_float` to `get_json` for this. Add rain + showers as `Decimal`, then convert to float.
- Range: a 400 whose `reason` says `out of allowed range` → `ForecastRangeError`. Add an `explain_rejection(status, body)` hook to `get_json` so the adapter can read a refusal's body; never store or quote that body. Any other 400 stays `ProviderError`.
- Range: when a series' last hours have no value at all, before the window ends → `ForecastRangeError`. A point with no value anywhere is a gap instead; `sample_at` decides.
- Times: `datetime.fromtimestamp(seconds, tz=UTC)`.
- Keep None for nulls. `sample_at` decides later.
- `max_lead_hours` = 354 (14 days 18 hours). Keep it as a named constant that cites the source. Open-Meteo forecasts 16 whole UTC days, and its last 5 hours came back `null` on 2026-10-16. 354 stays inside that from any time of day. It is still not a guarantee.
- Log `generationtime_ms` and batch sizes with `extra=`, never raw bodies.

### 7. Live test

Mark it `@pytest.mark.live`. Fetch two real points for the next 6 hours. Assert both series are complete.

## Tests

**`sample_at`**, with hours 14:00 and 15:00 UTC:

| `at` | Uses |
|---|---|
| 13:30 | 14:00 |
| 14:00:00 | 14:00 |
| 14:00:01 | 15:00 |
| 14:20 | 15:00 |
| 15:00 | 15:00 |
| 15:00:01 | `ForecastGapError` |
| 12:30 | `ForecastGapError` (over 1 h before the first hour) |

- None at the picked hour → `ForecastGapError`. None at the other hour → fine.
- Negative value → `ForecastGapError`.

**Adapter:**

- `two_points.json` → 2 series in request order.
- One-point object → 1 series.
- 120 points with batch size 50 → 3 requests. Order is preserved across batches.
- Metric fixture → values converted to mph and inches.
- Unknown unit → `ProviderError`.
- Array length mismatch → `ProviderError`.
- **Float trap:** rain 0.09 + showers 0.01 → exactly 0.10 → MODERATE via `classify(..., SPEC_RULES)`. Plain float addition gives `0.09999999999999999`, which is LOW. This test proves the `Decimal` path.
- Request params include `wind_speed_unit=mph`, `precipitation_unit=inch`, `timezone=GMT` and `timeformat=unixtime`.
- **Range:** the recorded `out of allowed range` 400 → `ForecastRangeError`, not `ProviderError`. Another 400 → `ProviderError`.
- **Range:** the recorded `null` tail inside the window → `ForecastRangeError`. The same tail after the window's end → fine.
- A last hour missing only some values → a gap at `sample_at`, not a range error.
- Live: a window 30 days out → `ForecastRangeError`. It catches a change in Open-Meteo's wording.

## Done when

- [ ] `uv run poe check` passes.

## Not in this session

- Deduplicating nearby points (07). Choosing the time window (07). Heatmap frames (06).

## Pitfalls

- Never default a missing value to 0. That reports unknown weather as Low risk.
- Don't use `precipitation`. It includes snow water. Use `rain + showers`.
- `snowfall` is snow depth. That matches the in/hr snow table.
- One deadline per batch would let 10 batches take 10× as long. Share one.
- Open-Meteo's mph unit string is `mp/h`, not `mph`.
- A too-far departure must never look like a provider failure. Only the two range signals above become `ForecastRangeError`.
