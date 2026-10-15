# Session 01 — Risk classifier (FR-03)

| | |
|---|---|
| Covers | FR-03. AC: "Wind, rain, snow, and load-dependent risk rules produce the expected classifications." |
| Needs | Scaffold only |
| Layer | Backend domain |
| Branch | `feat/risk-classifier` · commit type `feat(backend)` |
| Files | `backend/routing/domain/models.py`, `backend/routing/domain/risk.py`, `backend/tests/domain/__init__.py`, `backend/tests/domain/test_risk.py` |

## Goal

Turn one weather sample and one load weight into a risk level. Name the conditions that caused it.

## Read first

- [Contract → Risk policy](contract.md#risk-policy), items 1–3.
- [`requirements.md` §5–6](../../requirements.md#5-weather-risk-thresholds).

## Build

1. Add the value types to `models.py`.
2. Write the threshold tables in `risk.py` as data.
3. Write `level_for()`: one value plus one table gives a level.
4. Write `wind_level()`: the base wind level, then load overrides.
5. Write `classify()`: the worst of wind, rain and snow, plus drivers.

### Types

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

### Thresholds as data

The contract mixes two boundary styles. Most cuts start **at** the boundary. The No Travel cuts for rain and snow start **above** it. Store that per cut.

```python
@dataclass(frozen=True, slots=True)
class Cut:
    at: float
    inclusive: bool  # True: value >= at moves up. False: value > at moves up.


WIND_CUTS = (Cut(25, True), Cut(35, True), Cut(45, True), Cut(55, True))
RAIN_CUTS = (Cut(0.10, True), Cut(0.25, True), Cut(0.50, True), Cut(1.00, False))
SNOW_CUTS = (Cut(0.5, True), Cut(1.0, True), Cut(2.0, True), Cut(3.0, False))
```

Cut `i` (1-based) is the lower edge of the level with score `i`. Walk the cuts until one is not crossed.

### Load overrides as data

```python
@dataclass(frozen=True, slots=True)
class LoadOverride:
    base_wind_level: RiskLevel
    load_above_lb: float  # strictly greater than
    result: RiskLevel


LOAD_OVERRIDES = (
    LoadOverride(RiskLevel.SEVERE, 30_000, RiskLevel.NO_TRAVEL),  # wind [45, 55)
    LoadOverride(RiskLevel.HIGH, 40_000, RiskLevel.SEVERE),  # wind [35, 45)
)
```

- Wind ≥ 55 mph is already No Travel from the table. It needs no override.
- An override only raises a level. It never lowers one.

### Functions

```python
def level_for(value: float, cuts: tuple[Cut, ...]) -> RiskLevel: ...
def wind_level(wind_mph: float, load_lb: float) -> RiskLevel: ...
def classify(sample: WeatherSample, load_lb: float) -> RiskAssessment: ...
```

- `classify` takes the highest `score` of the three levels.
- `drivers` lists every condition at that level, in the order wind, rain, snow.
- `drivers` is empty when the level is LOW.
- A negative or non-finite load raises `ValueError`.

## Tests

Use `pytest.mark.parametrize` tables.

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

**Ordering:** `[level.score for level in RiskLevel] == [0, 1, 2, 3, 4]`.

**Invalid input:** NaN, inf or a negative value in `WeatherSample` → `ValueError`. Negative load → `ValueError`.

**Property tests (Hypothesis):**

- More wind never lowers the score.
- More load never lowers the score.
- `classify().level.score` is ≥ each single-condition score.

## Done when

- [ ] `uv run poe check` passes: format, Ruff, import contracts, mypy strict, tests.
- [ ] Changing a threshold means editing one tuple, nothing else.

## Not in this session

- Fetching weather or choosing the forecast hour (Session 05).
- Missing data. A `WeatherSample` is always complete. Gaps are caught before one is built.

## Pitfalls

- **`StrEnum` compares as text.** `RiskLevel.HIGH < RiskLevel.LOW` is `True`, because `'high' < 'low'`. Plain `max(levels)` picks the wrong level too. Always compare `.score`, or use `max(levels, key=attrgetter('score'))`.
- Don't write if/else ladders per condition. The tables are the rules.
- Don't round inputs. `24.999` is LOW.
