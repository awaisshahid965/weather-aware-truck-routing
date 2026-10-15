# Session 06 — Corridor heatmap data (FR-06, backend)

| | |
|---|---|
| Covers | FR-06 data. AC: "The corridor weather heatmap supports a 0-48 hour forecast slider." (backend half) |
| Needs | 01, 02, 05 |
| Layer | Backend domain |
| Branch | `feat/corridor-heatmap` · commit type `feat(backend)` |
| Files | `backend/routing/domain/models.py`, `backend/routing/domain/geometry.py`, `backend/routing/domain/corridor.py`, `backend/tests/domain/test_geometry.py`, `backend/tests/domain/test_corridor.py` |

## Goal

Pick up to 90 weather points around the three routes. Classify each one for every hour from departure +0 to +48.

## Read first

- [Contract → Heatmap policy](contract.md#heatmap-policy).

## Build

### Types (`models.py`)

```python
@dataclass(frozen=True, slots=True)
class HeatmapPoint:
    point: GeoPoint
    risk: RiskLevel


@dataclass(frozen=True, slots=True)
class HeatmapFrame:
    offset_hours: int  # 0..48
    valid_at: datetime  # departure_at + offset
    points: tuple[HeatmapPoint, ...]
```

### Geometry helpers (`geometry.py`)

```python
def bearing_degrees(a: GeoPoint, b: GeoPoint) -> float: ...
def destination_point(start: GeoPoint, bearing_deg: float, distance_miles: float) -> GeoPoint: ...
```

Use the standard spherical formulas.

### Corridor points (`corridor.py`)

```python
HEATMAP_SPACING_MILES = 25
HEATMAP_LATERAL_MILES = 15
HEATMAP_DEDUPE_MILES = 5


def corridor_points(routes: Sequence[RouteCandidate], *, max_points: int) -> tuple[GeoPoint, ...]: ...
```

1. **Centers.** Per route: 0, spacing, 2×spacing … plus the end. Reuse `checkpoint_distances` logic and `point_at` from Session 02.
2. **Bearing.** At each center, take the bearing from `point_at(d − 1)` to `point_at(d + 1)`, clamped to the route.
3. **Laterals.** Two points at bearing ± 90°, `HEATMAP_LATERAL_MILES` away.
4. **Order.** Route 1 centers, then route 1 laterals, then route 2, then route 3. A fixed order gives the same output every run.
5. **Dedupe.** Greedy: skip any point within `HEATMAP_DEDUPE_MILES` of a kept point.
6. **Cap.** If over `max_points`, multiply the spacing by 1.25 and start again. Repeat until it fits.

Step 6 always ends: at large spacing each route keeps only its endpoints.

`checkpoint_distances` only accepts 10, 25 or 50. Factor its stepping into a private helper that takes any spacing. Both functions then use it.

### Frames (`corridor.py`)

```python
HEATMAP_HOURS = 48


def build_frames(
    points: Sequence[GeoPoint],
    series: Sequence[HourlySeries],
    departure_at: datetime,
    load_lb: float,
) -> tuple[HeatmapFrame, ...]: ...
```

- `series[i]` belongs to `points[i]`.
- 49 frames. Offset `k` → `valid_at = departure_at + k hours`.
- Each point gets `classify(sample_at(series[i], valid_at), load_lb).level`.
- Let any `ForecastGapError` raise. The contract fails the whole plan.

## Tests

**Geometry:**

- `destination_point` 15 mi due east, then `haversine_miles` back → 15 ± 0.01 mi.
- `bearing_degrees` from (40, −80) to (41, −80) ≈ 0°.

**Corridor:**

- A straight 100-mi north–south route gives 5 centers + 10 laterals = 15 points.
- Each lateral is 15 ± 0.1 mi from its center.
- On a north–south route, laterals share their center's latitude (±0.01°).
- The same route passed 3 times gives the same 15 points.
- No two kept points are closer than the dedupe distance.
- Three 1,500-mi routes give ≤ 90 points. Two runs give identical output.

**Frames:**

- 49 frames, offsets 0..48, `valid_at = departure + k h`.
- Constant wind 50 mph: load 30,000 → all SEVERE. Load 30,001 → all NO_TRAVEL.
- A series ending 40 h after departure → `ForecastGapError`.
- Departure 12:20 → frame 0 uses the 13:00 hour (the at-or-after rule).

## Done when

- [ ] `uv run poe check` passes.

## Not in this session

- Fetching forecasts (07 calls the port). Rendering (14).

## Pitfalls

- Don't lay a grid over the bounding box. Diagonal routes would explode the point count.
- Heatmap points are not checkpoints. They show the weather at hour `k`, not the weather when the truck arrives.
