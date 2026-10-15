# Session 02 — Route checkpoints and ETAs (FR-02, part 1)

| | |
|---|---|
| Covers | FR-02 spacing and ETA. AC: "Every route is assessed using weather checkpoints spaced at a supported 10/25/50-mile interval." |
| Needs | 01 (`models.py` exists) |
| Layer | Backend domain |
| Branch | `feat/route-checkpoints` · commit type `feat(backend)` |
| Files | `backend/routing/domain/models.py`, `backend/routing/domain/geometry.py`, `backend/routing/domain/sampling.py`, `backend/tests/domain/test_geometry.py`, `backend/tests/domain/test_sampling.py` |

## Goal

Place checkpoints every N miles along a route. Each checkpoint gets a position, a mile marker, an ETA and a cell length in miles.

## Read first

- [Contract → Risk policy](contract.md#risk-policy), items 5 and 6.

## Build

### Types (`models.py`)

```python
@dataclass(frozen=True, slots=True)
class GeoPoint:
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class RouteSection:
    points: tuple[GeoPoint, ...]  # decoded shape, at least 2 points
    length_miles: float  # from the provider, > 0
    duration_seconds: float  # from the provider, >= 0


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    provider_index: int  # 0-based provider order
    sections: tuple[RouteSection, ...]
    # properties: distance_miles and duration_seconds, summed over sections


@dataclass(frozen=True, slots=True)
class Checkpoint:
    distance_from_start_miles: float
    point: GeoPoint
    eta_at: datetime  # aware UTC
    cell_miles: float
```

### Geometry (`geometry.py`)

```python
EARTH_RADIUS_MILES = 3958.7613  # mean radius; the spherical model is accurate enough here


def haversine_miles(a: GeoPoint, b: GeoPoint) -> float: ...
```

Sessions 06 and 08 add more helpers here.

### Sampling (`sampling.py`)

```python
CHECKPOINT_INTERVALS_MILES = frozenset({10, 25, 50})


def checkpoint_distances(total_miles: float, interval_miles: int) -> list[float]: ...
def point_at(route: RouteCandidate, distance_miles: float) -> GeoPoint: ...
def elapsed_seconds_at(route: RouteCandidate, distance_miles: float) -> float: ...
def cell_miles(distances: Sequence[float]) -> list[float]: ...
def build_checkpoints(route: RouteCandidate, interval_miles: int, departure_at: datetime) -> tuple[Checkpoint, ...]: ...
```

### Rules

1. **Distance.** Provider section lengths are the route distance. The geometry is only for position.
2. **Spacing.** Distances are `0, I, 2I, …` while below the total, then the destination. If the total is an exact multiple, the destination appears once.
3. **Interval.** It must be in `CHECKPOINT_INTERVALS_MILES`. Anything else raises `ValueError`.
4. **Locate.** Find section `s` where `start_s ≤ d < start_s + length_s`. The fraction is `(d − start_s) / length_s`. At `d == total`, use the last section with fraction 1.
5. **Position.** Multiply the fraction by the section's geometric length. Walk the shape by haversine segments. Interpolate lat/lon linearly inside the segment.
6. **Time.** Add the earlier sections' durations, plus `fraction × s.duration_seconds`.
7. **ETA.** `departure_at + elapsed`. `departure_at` must be timezone-aware.
8. **Cells.** Each cell is bounded by the midpoints to its neighbours and by the route start and end. Cells sum to the total.

## Tests

**Haversine:** (0, 0) → (1, 0) ≈ 69.093 mi (±0.01).

**Spacing:**

| Total mi | Interval | Distances |
|---|---|---|
| 60 | 25 | 0, 25, 50, 60 |
| 50 | 25 | 0, 25, 50 |
| 10 | 25 | 0, 10 |
| 35 | 10 | 0, 10, 20, 30, 35 |

- Interval 20 → `ValueError`.

**ETA:**

- One section, 60 mi, 3600 s, interval 25 → offsets 0, 1500, 3000, 3600 s.
- Two sections: A is 30 mi in 3600 s (slow). B is 30 mi in 1200 s (fast).
  - Mile 25 → 3000 s.
  - Mile 50 → 3600 + (20/30) × 1200 = 4400 s.
  - This proves section durations drive ETA, not constant speed.
- ETAs never decrease. The first equals departure. The last equals departure + route duration.
- A naive `departure_at` → `ValueError`.

**Position:**

- A straight section from (40, −80) to (41, −80): the midpoint distance gives latitude ≈ 40.5.
- Provider length 31 mi, shape 30 mi: mile 31 lands on the last shape point. Mile 15.5 lands on the shape midpoint.

**Cells:**

- `[0, 25, 50, 60]` → `[12.5, 25, 17.5, 5]`. Sum 60.
- `[0, 10]` → `[5, 5]`.

## Done when

- [ ] `uv run poe check` passes.

## Not in this session

- Weather (05). HERE parsing (04). Heatmap points (06). Display simplification (08).

## Pitfalls

- No duplicate final checkpoint when the total is an exact multiple.
- Don't use geometry length as route distance. The contract uses provider lengths.
- Consecutive duplicate shape points make zero-length segments. Skip them when walking.
- Compute `k × I`. Don't add `I` in a loop; float error builds up.
- Ruff's `DTZ` rules catch naive datetimes in tests too. Build test times with `tzinfo=UTC`.
