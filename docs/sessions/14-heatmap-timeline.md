# Session 14 — Heatmap timeline (FR-06, UI)

| | |
|---|---|
| Covers | FR-06. AC: "The corridor weather heatmap supports a 0-48 hour forecast slider." |
| Needs | 13 |
| Layer | Frontend map + controls |
| Branch | `feat/heatmap-timeline` · commit type `feat(frontend)` |
| Files | `frontend/src/shared/components/weather-timeline/` (`weather-timeline.tsx`, `hooks/use-weather-timeline.ts`), `frontend/src/shared/components/route-map/hooks/use-heatmap-layer.ts`, `frontend/src/shared/utils/geojson.ts` (+ `.test.ts`) |

## Goal

A slider from 0 to 48 hours changes the heatmap instantly, with no network call.

## Read first

- [Contract → Heatmap policy](contract.md#heatmap-policy).

## Build

### 1. Frame data

```ts
export const frameToFeatures = (frame: HeatmapFrame): FeatureCollection<Point> => { ... } // props: riskScore
```

Build all 49 collections once per plan and memoize them. The slider then picks one.

### 2. Layer

- A `heatmap` source and one heatmap layer per colored level, **below** the route casing from Session 13: `heatmap-risk-moderate`, `-high`, `-severe`, `-no-travel`, worst on top. Low has no layer, so it stays clear.
- Each layer draws the points at its level or worse: `filter: ['>=', ['get', 'riskScore'], score]`, with the default weight of 1.
- `heatmap-color`: a see-through copy of the level's `RISK_COLORS` at density 0, full color from density 0.2. A lone point peaks at 0.4, so its core shows full color. Overlapping points stay at full color.
- `heatmap-radius`: 25 mi, the spacing between points, in pixels. Use `['interpolate', ['exponential', 2], ['zoom'], …]` so the radius doubles each zoom level.
- `heatmap-opacity` about 0.6, so routes stay readable.
- Why not one layer weighted by `riskScore / 4`: the heatmap adds weights. A lone Severe point among Low ones draws as Moderate, and a wide Moderate band draws hotter than Moderate. Found in the browser check on 2026-10-16.

### 3. Slider (`weather-timeline`)

- `<input type="range" min="0" max="48" step="1">`.
- Label: `+6 h · Fri 6:00 PM EDT`, from `frames[k].validAt` in the plan's zone.
- `aria-valuetext` uses the same label.
- On change → `setData(collections[k])`. Coalesce rapid changes to one per animation frame.
- Keep the hour in local state, not in context.

### 4. Controls and copy

- A show/hide toggle that sets the layer's `visibility`. No refetch.
- A combined-risk legend. "No color = Low".
- The note required by the contract:
  > The heatmap shows conditions at the selected hour. Checkpoints show conditions when the truck reaches them.

## Tests

- `frameToFeatures`: one feature per point, `[lon, lat]`, `riskScore` copied.
- 49 memoized collections per plan. Same plan → same objects.
- Slider at 0 and 48 → labels match `frames[0].validAt` and `frames[48].validAt` in the zone.
- With MapLibre mocked: moving the slider calls `setData` with collection `k`. `TripService` is never called.
- The toggle sets `visibility` to `none` and back.
- Checkpoint data does not change when the slider moves.

**Browser check:**

- [ ] Dragging the slider is smooth. The DevTools Network tab shows no requests while dragging.
- [ ] Hours 0 and 48 look different for a trip with changing weather.
- [ ] Routes and checkpoints stay readable above the heatmap.
- [ ] Works at phone width.

## Done when

- [ ] `npm run check` and `npm run build` pass, and the browser check passes.

## Not in this session

- Animation or a play button. Add one only after acceptance (Session 15), if time allows.

## Pitfalls

- A heatmap layer adds up nearby weights. Never encode the level as weight in one layer: lone points read too cool, and dense ones too hot. Real points sit 5–15 mi apart where routes run side by side. Don't add points on the client.
- A fixed `heatmap-radius` looks right at one zoom only.
- `noUncheckedIndexedAccess`: `collections[k]` may be `undefined`. Guard it.
