# Session 10 — Frontend contract and state

| | |
|---|---|
| Covers | The typed boundary between the UI and the API. No FR on its own; every UI session builds on it. |
| Needs | [Contract](contract.md) only. Can run before the backend is done. |
| Layer | Frontend types, services, context |
| Branch | `feat/frontend-contract-state` · commit type `feat(frontend)` |
| Files | `frontend/src/shared/types/risk.ts`, `frontend/src/shared/types/route-plan.ts`, `frontend/src/shared/types/place.ts`, `frontend/src/shared/utils/contract-guards.ts` (+ `.test.ts`), `frontend/src/shared/services/api-error.ts`, `frontend/src/shared/services/http-client.ts` (+ `.test.ts`), `frontend/src/shared/services/place-service.ts`, `frontend/src/shared/services/trip-service.ts`, `frontend/src/context/trip/trip.interface.ts`, `frontend/src/context/trip/trip.context.ts`, `frontend/src/context/trip/trip.container.tsx` (+ `.test.tsx`), `frontend/tests/factories/route-plan.ts` |

## Goal

The UI receives only validated, typed data. One container owns the plan request.

## Read first

- [Contract](contract.md), all of it.
- `frontend/CONVENTIONS.md` → Types, State, Services and data.

## Build

### 1. Types

`risk.ts`:

```ts
export const RISK_LEVELS = ['low', 'moderate', 'high', 'severe', 'no_travel'] as const
export type RiskLevel = (typeof RISK_LEVELS)[number]
```

`route-plan.ts` and `place.ts`: interfaces that mirror the contract field by field. Use `RoutePlanRequest`, `RoutePlan`, `PlannedRoute`, `Checkpoint`, `RouteSummary`, `HeatmapFrame`, `HeatmapPoint`, `PlaceRef` (label + coordinates) and `Place` (search result with `id`).

### 2. Contract guards (`contract-guards.ts`)

`parseRoutePlan(json: unknown): RoutePlan` and `parsePlaces(json: unknown): Place[]`.

- Throw a `ContractError` that names the failing path, e.g. `routes[1].checkpoints[4].risk`.
- Check that numbers are finite, risk values are in `RISK_LEVELS`, there are exactly 49 frames with offsets 0–48, and geometry is a `LineString`.
- Hand-written guards. The scaffold has no schema library; sessions don't add packages.

### 3. HTTP client (`http-client.ts`, `api-error.ts`)

A base class with protected static helpers, as `CONVENTIONS.md` describes.

- Base URL from `API_BASE_URL` in `@/shared/config/app-config`.
- Send JSON headers. Accept an `AbortSignal`.
- `!response.ok` with the contract error body → throw `ApiError` (status, code, message, requestId, details).
- `!response.ok` without a JSON body → `ApiError` with code `HTTP_ERROR`.
- `fetch` rejects (no network) → `ApiError` with code `NETWORK_ERROR`.
- An abort passes through unchanged. Callers ignore it.

### 4. Services

- `PlaceService.search(query, signal)` → `parsePlaces(...)`.
- `TripService.createPlan(request, signal)` → `parseRoutePlan(...)`.
- Each service keeps its endpoint paths in one constant object.

### 5. Trip context

```ts
export interface TripContextValue {
    plan: RoutePlan | null
    planRequest: RoutePlanRequest | null // the request that produced `plan`
    status: TripStatus // 'idle' | 'loading' | 'success' | 'error', from an `as const` array
    error: ApiError | null
    createPlan: (request: RoutePlanRequest) => void
    clearError: () => void
}
```

- `planRequest` lets the form mark an old result. The response doesn't echo the load weight.
- `trip.context.ts`: `createContext<TripContextValue | null>(null)` and `useTripContext()`, which throws outside the provider.
- `trip.container.tsx` (`'use client'`): keeps an `AbortController` in a ref. A new `createPlan` aborts the previous one.
- Keep the old `plan` while loading. Replace it only on success.

### 6. Test factory (`frontend/tests/factories/route-plan.ts`)

`makeRoutePlan(overrides?)` builds a **valid** `RoutePlan`: 3 routes, a few checkpoints each, and 49 frames. UI tests use it until a recorded API response exists (Session 15).

Delete the `.gitkeep` files in `context/`, `shared/types/`, `shared/services/` and `shared/utils/`.

## Tests

**HttpClient.** This is the one test that stubs `fetch` (`vi.stubGlobal`). Every other test mocks the service.

- 200 JSON → parsed body.
- 422 contract error → `ApiError` with code, message, requestId and details.
- 502 HTML → `ApiError('HTTP_ERROR')`.
- `fetch` rejects → `ApiError('NETWORK_ERROR')`.
- Abort → `AbortError`, not an `ApiError`.

**Guards:**

- The factory output passes.
- An unknown risk value fails and names the path.
- 48 frames fail.
- A `NaN` coordinate fails.

**Container** (mock `TripService.createPlan` with `vi.spyOn`):

- `idle → loading → success`.
- `idle → loading → error`. `clearError` resets the error.
- A second `createPlan` aborts the first. The first's late result is ignored.
- `useTripContext()` outside the provider throws a clear error.

## Done when

- [x] `npm run check` passes: format, lint, types, tests.
- [x] No component calls `fetch`.

## Not in this session

- Any visible UI (11–14).

## Pitfalls

- TypeScript types don't validate network data. The guards do.
- `noUncheckedIndexedAccess` is on. `frames[k]` is `HeatmapFrame | undefined`; handle it.
- Don't put the slider hour, hover state or the selected route in context. Those are local UI state.
- Test files outside `src/` are not run. Vitest only includes `src/**/*.test.{ts,tsx}`.
