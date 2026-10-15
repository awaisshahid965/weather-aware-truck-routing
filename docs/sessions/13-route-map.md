# Session 13 — Route map (FR-05)

| | |
|---|---|
| Covers | FR-05. AC: "The map displays routes, checkpoints, risk levels, ETAs, summaries, and the recommendation." |
| Needs | 10, 12 (risk display, selection) |
| Layer | Frontend map |
| Branch | `feat/route-map` · commit type `feat(frontend)` |
| Files | `frontend/src/shared/components/route-map/` (`route-map.tsx`, `hooks/use-route-layers.ts`, `checkpoint-details/`, `risk-legend/`), `frontend/src/shared/utils/geojson.ts` (+ `.test.ts`) |

## Goal

All three routes and their checkpoints are on one map. The recommended and selected routes are obvious. Each checkpoint shows its ETA and risk.

## Read first

- [Contract → Conventions](contract.md#conventions): `[longitude, latitude]` order.
- [Contract → Heatmap policy](contract.md#heatmap-policy): checkpoints keep their own-ETA risk.
- `frontend/CONVENTIONS.md` → Components (browser-only libraries).

## Build

### 1. Map lifecycle

- MapLibre is browser-only. Load `route-map.tsx` with `next/dynamic` and `ssr: false`, from inside a client component.
- Create the map once in an effect. Keep it in a ref. Call `map.remove()` on unmount.
- The style URL is `MAP_STYLE_URL` from `@/shared/config/app-config`. Keep the attribution control.
- Add sources and layers on `load`. Re-add them after any style reload.

### 2. GeoJSON builders (`geojson.ts`, pure)

```ts
export const routesToFeatures = (plan: RoutePlan): FeatureCollection<LineString> => { ... }
export const checkpointsToFeatures = (plan: RoutePlan): FeatureCollection<Point> => { ... }
```

- Route properties: `routeId`, `name`, `recommended`.
- Checkpoint properties: `routeId`, `mile`, `etaAt`, `risk`, `windMph`, `rainInPerHour`, `snowInPerHour`, `drivers`.
- Import the types with `import type { FeatureCollection, LineString, Point } from 'geojson'`. `@types/geojson` is a dependency of `maplibre-gl`, so no new package is needed.
- Memoize by plan identity.

### 3. Layers, bottom to top

1. Heatmap (empty until Session 14).
2. Route casing: a wide, dark outline for contrast.
3. Route lines: muted for alternatives, strong and wider for the recommended route.
4. Selected-route highlight via `feature-state`. Set `promoteId: 'routeId'` on the source.
5. Checkpoint circles. Color with a `match` on `risk`, built from `RISK_COLORS`. Add a white stroke. The radius grows with zoom.

### 4. Interaction

- Click a checkpoint → the details panel shows route, mile, ETA in the plan's zone, wind, rain, snow, risk badge and drivers.
- Pointer cursor on hover over checkpoints.
- Keyboard and screen readers: the details panel also lists the selected route's checkpoints as buttons.
- A selected route card highlights its line. Selection changes `feature-state` only, never `setData`.

### 5. Framing and legend

- On a new plan, `fitBounds` to all routes. Pad for the side panel on wide screens.
- A risk legend with text labels. Attribution stays visible.

### 6. Updates

- A new plan → `setData` on both sources.
- Checkpoints always show risk **at their own ETA**. The slider in Session 14 does not change them.

## Tests

`maplibre-gl` doesn't run in jsdom. Mock the module with `vi.mock('maplibre-gl', …)`. Test the logic, not the canvas.

- `routesToFeatures`: 3 features, `[lon, lat]` order, `recommended` flags.
- `checkpointsToFeatures`: one feature per checkpoint, properties copied exactly.
- Same plan → same memoized object.
- With MapLibre mocked: a new plan calls `setData` once per source. Selecting a route calls `setFeatureState` and not `setData`.
- The details panel renders the ETA in the plan's zone, the risk label and the drivers.
- `page.test.tsx` and the planner tests now render the map. Mock the `route-map` module in them.

**Browser check** (manual, desktop and phone widths):

- [ ] Three lines visible. The recommended route is clearly emphasized.
- [ ] Selecting a card highlights its line.
- [ ] Clicking a checkpoint shows correct details.
- [ ] Legend and attribution are visible.

## Done when

- [ ] `npm run check` and `npm run build` pass, and the browser check passes.
- [ ] No DOM marker per checkpoint. Everything is a layer.

## Not in this session

- The heatmap layer and slider (14).

## Pitfalls

- Import `maplibre-gl/dist/maplibre-gl.css` in the map component. Without it, controls and popups break.
- Don't recreate the map on React re-renders. It's the most common cause of slow maps.
- `feature-state` needs an id. `promoteId` gives one without changing the data.
- `react-hooks/exhaustive-deps` is on. Keep the map in a ref, so effects don't re-run on every render.
