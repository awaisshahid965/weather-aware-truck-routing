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

- A `heatmap` source and a `heatmap-risk` layer, **below** the route casing from Session 13.
- `heatmap-weight`: `['/', ['get', 'riskScore'], 4]`. Low has weight 0, so it stays clear.
- `heatmap-color`: transparent at density 0, then `RISK_COLORS` as density rises.
- `heatmap-radius`: must cover the gap between points at every zoom. Points are about 25 mi apart. Use `['interpolate', ['exponential', 2], ['zoom'], …]` so the radius doubles each zoom level. Tune by eye.
- `heatmap-opacity` about 0.6, so routes stay readable.

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

- The heatmap layer adds up nearby weights. Overlapping points look "hotter". The backend's dedupe (Session 06) keeps spacing even. Don't add points on the client.
- A fixed `heatmap-radius` looks right at one zoom only.
- `noUncheckedIndexedAccess`: `collections[k]` may be `undefined`. Guard it.
