# Session 01 — Risk rules and classifier (FR-03)

| | |
|---|---|
| Covers | FR-03. AC: "Wind, rain, snow, and load-dependent risk rules produce the expected classifications." |
| Needs | Scaffold only |
| Layer | Backend domain + rules source (port and JSON adapter) |
| Branch | `feat/risk-classifier` · commit type `feat(backend)` |
| Files | `backend/routing/domain/models.py`, `backend/routing/domain/risk.py`, `backend/routing/ports/errors.py`, `backend/routing/ports/risk_rules.py`, `backend/routing/adapters/json_risk_rules.py`, `backend/routing/rules/risk_rules.json`, `backend/tests/spec_rules.py`, `backend/tests/domain/__init__.py`, `backend/tests/domain/test_risk.py`, `backend/tests/adapters/__init__.py`, `backend/tests/adapters/test_json_risk_rules.py` |

## Goal

Turn one weather sample, one load weight and one rule set into a risk level. Name the conditions that caused it.

The rules are data, loaded from a JSON file through a port. A database-backed source can replace the file later, with no change to the classifier or its callers.

## Read first

- [Contract → Risk policy](contract.md#risk-policy), items 1–3 and 9.
- [`requirements.md` §5–6](../../requirements.md#5-weather-risk-thresholds).

## Part A — Domain

### Types (`models.py`)

```python
class RiskLevel(StrEnum):
    LOW = 'low'
    MODERATE = 'moderate'
    HIGH = 'high'
    SEVERE = 'severe'
    NO_TRAVEL = 'no_travel'

    @property
    def score(self) -> int:
        """0 for LOW up to 4 for NO_TRAVEL. Definition order is risk order."""
        return list(RiskLevel).index(self)


class Condition(StrEnum):
    WIND = 'wind'
    RAIN = 'rain'
    SNOW = 'snow'


@dataclass(frozen=True, slots=True)
class WeatherSample:
    wind_mph: float
    rain_in_per_hour: float
    snow_in_per_hour: float
    # __post_init__: every value finite and >= 0, else ValueError


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    level: RiskLevel
    drivers: tuple[Condition, ...]  # conditions tied at `level`; empty when LOW
```

The enum values are the contract's API strings, so the HTTP layer needs no mapping.

### Rule types (`risk.py`)

The contract mixes two boundary styles. Most cuts start **at** the boundary. The No Travel cuts for rain and snow start **above** it. Each cut stores which one it uses.

```python
@dataclass(frozen=True, slots=True)
class Cut:
    """The lower edge of one risk level."""

    at: float
    inclusive: bool  # True: value >= at moves up. False: value > at moves up.


@dataclass(frozen=True, slots=True)
class LoadOverride:
    base_wind_level: RiskLevel
    load_above_lb: float  # strictly greater than
    result: RiskLevel
    # __post_init__: result.score > base_wind_level.score, else ValueError


@dataclass(frozen=True, slots=True)
class RiskRules:
    version: str
    wind_cuts: tuple[Cut, ...]
    rain_cuts: tuple[Cut, ...]
    snow_cuts: tuple[Cut, ...]
    load_overrides: tuple[LoadOverride, ...]
    # __post_init__ checks the invariants below, else ValueError
```

`RiskRules` invariants. Every source (file now, database later) gets them for free:

- `version` is not blank.
- Each cuts tuple has exactly 4 cuts. Cut `i` (1-based) is the lower edge of the level with score `i`.
- Cut values are finite, ≥ 0 and strictly ascending.
- No two load overrides share a `base_wind_level`.

The domain holds **no** rule values. The JSON file is the single source.

### Functions (`risk.py`)

```python
def level_for(value: float, cuts: tuple[Cut, ...]) -> RiskLevel: ...
def wind_level(wind_mph: float, load_lb: float, rules: RiskRules) -> RiskLevel: ...
def classify(sample: WeatherSample, load_lb: float, rules: RiskRules) -> RiskAssessment: ...
```

- `level_for` walks the cuts until one is not crossed.
- `wind_level` takes the base wind level, then applies a matching load override. An override only raises a level; wind ≥ 55 mph is already No Travel from the cuts.
- `classify` takes the highest `score` of the three levels.
- `drivers` lists every condition at that level, in the order wind, rain, snow. It is empty when the level is LOW.
- A negative or non-finite load raises `ValueError`.

## Part B — Rules source

### 1. Port error (`ports/errors.py`)

```python
class RiskRulesUnavailableError(Exception):
    """The risk rules could not be loaded or are invalid."""
```

Session 04 adds the provider errors to this file.

### 2. Port (`ports/risk_rules.py`)

```python
class RiskRulesSource(Protocol):
    def current(self) -> RiskRules: ...
```

Callers ask once per plan and pass the result down (Session 07).

### 3. Rules file (`routing/rules/risk_rules.json`)

```json
{
  "version": "assessment-2026-10",
  "wind_mph": [
    {"level": "moderate", "when": ">=", "value": 25},
    {"level": "high", "when": ">=", "value": 35},
    {"level": "severe", "when": ">=", "value": 45},
    {"level": "no_travel", "when": ">=", "value": 55}
  ],
  "rain_in_per_hour": [
    {"level": "moderate", "when": ">=", "value": 0.10},
    {"level": "high", "when": ">=", "value": 0.25},
    {"level": "severe", "when": ">=", "value": 0.50},
    {"level": "no_travel", "when": ">", "value": 1.00}
  ],
  "snow_in_per_hour": [
    {"level": "moderate", "when": ">=", "value": 0.5},
    {"level": "high", "when": ">=", "value": 1.0},
    {"level": "severe", "when": ">=", "value": 2.0},
    {"level": "no_travel", "when": ">", "value": 3.0}
  ],
  "load_overrides": [
    {"wind_level": "severe", "load_above_lb": 30000, "result": "no_travel"},
    {"wind_level": "high", "load_above_lb": 40000, "result": "severe"}
  ]
}
```

Each entry names the level it starts, so the file reads as the spec does.

### 4. Adapter (`adapters/json_risk_rules.py`)

```python
class JsonRiskRules:
    def __init__(self, path: Path) -> None: ...  # loads and validates now: fail fast
    def current(self) -> RiskRules: ...
```

- Read with `encoding='utf-8'`. Parse with the standard `json` module.
- Narrow the JSON to typed values. Reject unknown keys, so a typo can't silently drop a rule.
- Levels in each list must be exactly `moderate`, `high`, `severe`, `no_travel`, in that order.
- `when` is `">="` (inclusive) or `">"` (not inclusive).
- Numbers must be `int` or `float`, never `bool`.
- Wrap every failure in `RiskRulesUnavailableError`, chained with `from`: missing file, bad JSON, wrong shape, or a `ValueError` from the domain invariants. The message names the file and the rule that failed.

### 5. Spec rules for tests (`tests/spec_rules.py`)

`SPEC_RULES`: the assessment's values, built in Python. Domain and service tests use it, so they never read the file.

## Tests

Use `pytest.mark.parametrize` tables. Pass `SPEC_RULES` to every call.

**Wind, load 0:** 0 → LOW · 24.99 → LOW · 25 → MODERATE · 34.99 → MODERATE · 35 → HIGH · 44.99 → HIGH · 45 → SEVERE · 54.99 → SEVERE · 55 → NO_TRAVEL · 90 → NO_TRAVEL

**Rain:** 0.09 → LOW · 0.10 → MODERATE · 0.25 → HIGH · 0.50 → SEVERE · **1.00 → SEVERE** · 1.01 → NO_TRAVEL

**Snow:** 0.49 → LOW · 0.5 → MODERATE · 1.0 → HIGH · 2.0 → SEVERE · **3.0 → SEVERE** · 3.01 → NO_TRAVEL

**Load overrides:**

| Wind mph | Load lb | Expected | Why |
|---|---|---|---|
| 45 | 30,000 | SEVERE | Not strictly above 30,000 |
| 45 | 30,001 | NO_TRAVEL | Rule 2 |
| 54.99 | 30,001 | NO_TRAVEL | Rule 2, top of band |
| 35 | 40,000 | HIGH | Not strictly above 40,000 |
| 35 | 40,001 | SEVERE | Rule 3 |
| 44.99 | 40,001 | SEVERE | Rule 3, top of band |
| 40 | 35,000 | HIGH | Rule 3 needs > 40,000 |
| 50 | 45,000 | NO_TRAVEL | Rule 2 applies |
| 55 | 0 | NO_TRAVEL | Rule 1, any load |
| 30 | 80,000 | MODERATE | No rule below 35 mph |

**Combined:**

- Wind LOW, rain HIGH, snow MODERATE → HIGH, drivers `(RAIN,)`.
- Wind SEVERE, snow SEVERE → SEVERE, drivers `(WIND, SNOW)`.
- All LOW → LOW, drivers `()`.
- A load override raises wind to the top → drivers include `WIND`.

**Rules are injected, not built in:** a `RiskRules` with wind cuts at 10/20/30/40 classifies 25 mph as HIGH.

**`RiskRules` invariants:** 3 cuts → `ValueError`. Descending cuts → `ValueError`. Two overrides for one base level → `ValueError`. Blank version → `ValueError`.

**Ordering:** `[level.score for level in RiskLevel] == [0, 1, 2, 3, 4]`.

**Invalid input:** NaN, inf or a negative value in `WeatherSample` → `ValueError`. Negative load → `ValueError`.

**Property tests (Hypothesis):**

- More wind never lowers the score.
- More load never lowers the score.
- `classify().level.score` is ≥ each single-condition score.

**Adapter** (write variants to `tmp_path`):

- **The shipped file equals `SPEC_RULES`.** This pins the spec: an accidental edit to the JSON fails CI.
- Missing file, invalid JSON, `"when": "=>"`, a misspelled level, an unknown key, `true` as a value, and descending values → `RiskRulesUnavailableError` naming the file.

## Done when

- [ ] `uv run poe check` passes: format, Ruff, import contracts, mypy strict, tests.
- [ ] No rule value appears in `routing/` outside the JSON file.

## Not in this session

- Loading the rules once per plan (07). Wiring the adapter and failing the deploy on a bad file (08).
- Fetching weather or choosing the forecast hour (05).
- Missing weather data. A `WeatherSample` is always complete. Gaps are caught before one is built.
- A database-backed source and admin. They need a database, which the scaffold leaves out on purpose.

## Pitfalls

- **`StrEnum` compares as text.** `RiskLevel.HIGH < RiskLevel.LOW` is `True`, because `'high' < 'low'`. Plain `max(levels)` picks the wrong level too. Always compare `.score`, or use `max(levels, key=attrgetter('score'))`.
- `isinstance(True, int)` is `True` in Python. Check for `bool` first, or `"value": true` would load as 1.
- JSON `0.10` parses to the same float as the Python literal `0.10`. The equality test against `SPEC_RULES` relies on that; it holds.
- Don't round inputs. `24.999` is LOW.
