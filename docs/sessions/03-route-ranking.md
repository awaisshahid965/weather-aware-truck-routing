# Session 03 — Route summaries and recommendation (FR-04)

| | |
|---|---|
| Covers | FR-04. AC: "Route summaries support comparison by Severe miles, High miles, average risk, and travel time." and "The route recommendation follows the four stated priorities in order." |
| Needs | 01, 02 |
| Layer | Backend domain |
| Branch | `feat/route-ranking` · commit type `feat(backend)` |
| Files | `backend/routing/domain/models.py`, `backend/routing/domain/ranking.py`, `backend/tests/domain/test_ranking.py` |

## Goal

Summarize each route from its checkpoints. Pick one route by the ordered priorities, or none.

## Read first

- [Contract → Risk policy](contract.md#risk-policy), items 6 and 7.
- [`requirements.md` §7](../../requirements.md#7-route-recommendation-priorities).

## Build

### Types (`models.py`)

```python
@dataclass(frozen=True, slots=True)
class AssessedCheckpoint:
    checkpoint: Checkpoint
    weather: WeatherSample
    risk: RiskAssessment


@dataclass(frozen=True, slots=True)
class RouteSummary:
    no_travel_miles: float
    severe_miles: float
    high_miles: float
    average_risk: float
    worst_risk: RiskLevel


@dataclass(frozen=True, slots=True)
class RankInput:
    provider_index: int
    duration_seconds: float
    summary: RouteSummary


@dataclass(frozen=True, slots=True)
class Recommendation:
    provider_index: int | None  # None when every route has No Travel miles
```

### Functions (`ranking.py`)

```python
def summarize(checkpoints: Sequence[AssessedCheckpoint], route_miles: float) -> RouteSummary: ...
def recommend(routes: Sequence[RankInput]) -> Recommendation: ...
```

### Summary rules

- Level miles are **exclusive**. A No Travel cell does not count as Severe miles.
- `average_risk = Σ(cell_miles × level.score) / route_miles`. Keep it unrounded.
- `worst_risk` is the checkpoint level with the highest score.

### Recommendation rules

1. Drop routes with `no_travel_miles > 0`. They are ineligible.
2. If none are left, return `provider_index=None`.
3. Sort the rest by this key. The first one wins.

```python
def _priority_key(route: RankInput) -> tuple[float, float, float, float, int]:
    return (
        route.summary.severe_miles,  # P1: fewest Severe miles
        route.summary.high_miles,  # P2: fewest High miles
        route.summary.average_risk,  # P3: lowest average risk
        route.duration_seconds,  # P4: shortest travel time
        route.provider_index,  # full tie: provider order (policy)
    )
```

Tuples compare left to right. A later field only matters when every earlier field ties. That gives ordered priorities with no weights.

### Optional: why it won

`decided_by` is the first key where the winner differs from the runner-up. Values: `severe_miles`, `high_miles`, `average_risk`, `duration_seconds`, `provider_order` or `only_eligible`. The UI could show it.

It is **not** in the [contract](contract.md). Add it to the contract first, or skip it.

## Tests

**Summary:**

- Cells `[12.5, 25, 17.5, 5]`, levels `[LOW, SEVERE, HIGH, SEVERE]`, route 60 mi:
  - severe 30, high 17.5, no_travel 0
  - average (3×25 + 2×17.5 + 3×5) / 60 = 125/60 ≈ 2.0833
  - worst SEVERE
- A NO_TRAVEL cell adds to `no_travel_miles` only.
- Miles at all five levels add up to the route miles.

**Recommendation.** In each row, the earlier keys tie and the named key decides:

| Test | Route A | Route B | Winner |
|---|---|---|---|
| P1 | severe 10 | severe 20, better on everything else | A |
| P2 | high 5 | high 15 | A |
| P3 | average 0.4 | average 0.6 | A |
| P4 | 3600 s | 4000 s | A |
| Full tie | equal | equal | lower `provider_index` |

**Order beats size:** A has severe 0, high 100, 9 h. B has severe 1, high 0, 4 h. A wins.

**No Travel:**

- A has 1 No Travel mile and wins every other key → B wins.
- All routes have No Travel → `None`.

**Input order (Hypothesis):** shuffling the input never changes the winner.

## Done when

- [ ] `uv run poe check` passes.

## Not in this session

- Building checkpoints (02). Weather (05). Response fields (08).

## Pitfalls

- No weights, no score formula. Requirements §7 forbids it.
- `worst_risk` needs `key=attrgetter('score')`. Plain `max()` on `StrEnum` sorts alphabetically.
- The contract sorts unrounded values. Zero-vs-zero ties, the common case, are exact.
- Don't drop No Travel routes from the result. They stay visible; they are just never recommended.
