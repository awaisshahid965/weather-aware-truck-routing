# Session 16 — Fewer routes and map summary

| | |
|---|---|
| Covers | FR-01 (fewer routes), FR-05 (summaries on the map), FR-06 (calm hours) |
| Needs | 15 |
| Layer | Both |
| Branch | `feat/partial-routes` · commit types `feat(backend)`, `feat(frontend)`, `docs` |
| Files | `routing/services/plan_trip.py`, `routing/services/errors.py`, `shared/types/route-plan.ts`, `shared/utils/contract-guards.ts`, `shared/components/route-stats/`, `shared/components/recommended-badge/`, `shared/components/route-map/selected-route/`, `shared/components/weather-timeline/`, [contract](contract.md), root `README.md` |

## Goal

Never show an empty screen when HERE has routes. Make the map explain itself.

## Why

Session 15's check found three problems a reviewer would hit:

- HERE gives only 2 routes for many common trips: Dallas to Houston, LA to Las Vegas, Seattle to Portland, Minneapolis to Duluth. Asking for 4 or 6 alternatives still gives 2. The old policy failed those plans.
- Route summaries sat beside the map, not on it (FR-05).
- Low has no heatmap color, so a calm hour looked like a broken map.

## Build

### 1. Plans of 1 or 2 routes (contract change first)

- [Contract](contract.md): one to three routes, ids `route-1` … `route-N`. With fewer than three, `notices` says how many were found. `INSUFFICIENT_ROUTES` now means no route at all.
- Service: keep up to the first 3 routes. Raise `InsufficientRoutesError(0)` only for none. Add `ONE_ROUTE_NOTICE` or `TWO_ROUTES_NOTICE` after any No Travel notice.
- Frontend guard: accept 1 to `MAX_ROUTE_COUNT` routes. The `INSUFFICIENT_ROUTES` message says no route was found.

### 2. Selected route summary on the map

- `RouteStats`: the No Travel warning plus every comparison number. The route card and the map both use it.
- `SelectedRoute` in the map's side panel: "Selected route", the name, the Recommended badge, and `RouteStats`.

### 3. Highest risk at the slider's hour

- Under the slider: "Every point is Low at this hour, so the heatmap is clear", or "Highest risk at this hour" with a badge.
- It reads the API's levels. The frontend still never classifies.

## Tests

- Service: no route fails before any forecast call; 2 routes plan, recommend and notice; 1 route is recommended; 1 No Travel route shows both notices.
- HTTP: 2 routes from the provider give a 200 with `route-1`, `route-2` and the notice.
- Frontend: the guard accepts 1 and 2 routes and rejects 0 and 4; two cards with the notice; the map summary with and without the badge; the calm and highest-risk lines.
- Live: Dallas to Houston gives a plan of 2 routes.

## Done when

- [ ] `uv run poe check`, `npm run check` and `npm run build` pass. CI is green.
- [ ] Browser check: a 2-route trip shows two cards, two lines and the notice. The map panel shows the selected route. The slider line changes with the hour.
