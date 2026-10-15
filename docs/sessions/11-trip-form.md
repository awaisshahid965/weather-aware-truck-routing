# Session 11 — Trip form and page

| | |
|---|---|
| Covers | Section 3 inputs. AC: "A driver can enter origin, destination, departure date/time, and load weight." |
| Needs | 10 |
| Layer | Frontend page + components |
| Branch | `feat/trip-form` · commit type `feat(frontend)` |
| Files | `frontend/src/app/page.tsx`, `frontend/src/app/page.test.tsx`, `frontend/src/shared/components/trip-planner/` (with `hooks/use-trip-planner.ts`), `frontend/src/shared/components/trip-form/` (with a `place-search-input/` subfolder and its `hooks/use-place-search.ts`), `frontend/src/shared/ui/` controls as needed, `frontend/src/shared/utils/date.ts` (+ `.test.ts`) |

## Goal

The page exists. A driver fills in the trip and submits it. The request matches the contract exactly.

## Read first

- [Contract → `POST /api/v1/route-plans`](contract.md#post-apiv1route-plans): the request and its validation.
- `frontend/CONVENTIONS.md` → Components, State.

## Build

### 1. Page composition

- `app/page.tsx` stays a Server Component. It renders `<TripContainer><TripPlanner /></TripContainer>`.
- `TripPlanner` (`'use client'`) lays out the form, the comparison panel (12) and the map (13).
  - Wide screens: form and cards in a side panel, a large map beside them.
  - Narrow screens: form, then cards, then the map, stacked. The map keeps a usable height.
- Before the first result, the panel explains what to enter. It never shows sample results.
- Update `page.test.tsx`: the placeholder text is gone, but the `h1` stays.

### 2. Place search input

Each input gets its own `usePlaceSearch` hook instance.

- Search after 300 ms of no typing, and only with ≥ 3 non-space characters.
- Each new search aborts the previous one.
- Follow the ARIA combobox pattern: `role="combobox"`, `aria-expanded`, `aria-controls`, `aria-activedescendant`, and a `listbox` of `option`s.
- Keys: ↓/↑ move, Enter selects, Escape closes.
- Selecting stores the `Place` (id, label, latitude, longitude).
- Typing after a selection clears it.
- Show loading, no-results and error states.

### 3. Departure

- Native date and time inputs.
- A time zone select. Default: `Intl.DateTimeFormat().resolvedOptions().timeZone`. Options: `Intl.supportedValuesOf('timeZone')`.
- Show the chosen zone next to the time.
- Default departure: the next full hour, set **after mount** (see Pitfalls).

### 4. Local time → UTC (`date.ts`)

```ts
export interface WallTime {
    year: number
    month: number
    day: number
    hour: number
    minute: number
}

export type ResolvedWallTime =
    | { kind: 'ok'; instant: Date }
    | { kind: 'nonexistent' } // skipped by a spring-forward change
    | { kind: 'ambiguous' } // repeated by a fall-back change

export const resolveWallTime = (wall: WallTime, timeZone: string): ResolvedWallTime => { ... }
```

The algorithm needs no library:

1. `guess = Date.UTC(wall…)`, treating the wall time as if it were UTC.
2. Read the zone's offset at `guess − 24 h` and `guess + 24 h`. Together they cover both sides of any change.
3. For each distinct offset, compute `candidate = guess − offset`.
4. Keep the candidates that format back to the same wall time in that zone.
5. 0 kept → `nonexistent`. 1 → `ok`. 2 → `ambiguous`.

Read offsets and wall times with `Intl.DateTimeFormat('en-US', { timeZone, hourCycle: 'h23', … }).formatToParts`.

### 5. Load and interval

- Load weight in lb: a finite number ≥ 0.
- Interval: a select with 10, 25 or 50. Default 25.

### 6. Validate on submit

- Both places are selected, not just typed.
- The places differ (different id and coordinates).
- The departure resolves to `ok` and is in the future.
- The load is valid.
- Show errors next to their fields with `aria-describedby`. Focus the first invalid field.

### 7. Submit

- Build `RoutePlanRequest`. `departureAt` = the instant as ISO with `Z`, without milliseconds (`2026-10-16T12:00:00Z`).
- Call `createPlan`. Disable submit while loading.
- When the form differs from `planRequest`, label the shown result **Previous plan**. The label clears on the next success.

Delete the `.gitkeep` files in `shared/components/` and `shared/ui/`.

## Tests

**`resolveWallTime`:**

| Wall time | Zone | Expected |
|---|---|---|
| 2026-10-16 08:00 | America/New_York | ok → `2026-10-16T12:00:00Z` |
| 2026-03-08 02:30 | America/New_York | nonexistent |
| 2026-11-01 01:30 | America/New_York | ambiguous |
| 2026-10-16 08:00 | UTC | ok → `2026-10-16T08:00:00Z` |

**Form** (mock `PlaceService.search` and the context's `createPlan`):

- Submit with empty fields → a message on each required field.
- Typing a label without selecting → an origin error.
- Typing after a selection clears the selection.
- Same origin and destination → an error.
- Nonexistent and ambiguous times → clear messages.
- Fast typing (fake timers) → one search after 300 ms.
- A stale search is aborted.
- Keyboard only: ↓, Enter selects a suggestion.
- A valid submit sends exactly the contract fields.
- Submit is disabled while loading.
- Changing a field after success shows **Previous plan**.

## Done when

- [ ] `npm run check` and `npm run build` pass.
- [ ] The whole form works by keyboard.

## Not in this session

- Route cards (12), map (13), heatmap (14).

## Pitfalls

- `cacheComponents` is on (scaffold). Reading the clock during render can break prerendering in `next build`. Compute "now" in an effect or an event handler, not in render.
- Some engines format midnight as `24` unless you set `hourCycle: 'h23'`.
- `toISOString()` adds `.000`. Strip it to match the contract.
- The browser's zone is not always the origin's zone. The visible zone label makes that clear to the driver.
- Keep `'use client'` as deep as possible. `page.tsx` and `layout.tsx` stay Server Components.
