# Session 12 — Route comparison (FR-04, UI)

| | |
|---|---|
| Covers | FR-04 "Show the recommended route and the information used to compare it." AC: summaries by Severe miles, High miles, average risk and travel time, plus the recommendation. |
| Needs | 10 |
| Layer | Frontend components |
| Branch | `feat/route-comparison` · commit type `feat(frontend)` |
| Files | `frontend/src/shared/utils/risk-display.ts` (+ `.test.ts`), `frontend/src/shared/utils/format.ts` (+ `.test.ts`), `frontend/src/shared/components/risk-badge/` (with `risk-badge.styles.ts`), `frontend/src/shared/components/route-comparison/` (with a `route-card/` subfolder), `frontend/src/shared/components/trip-planner/hooks/use-trip-planner.ts` |

## Goal

Three cards make the comparison obvious. The recommended route stands out. No Travel is impossible to miss.

## Read first

- [Contract → Risk policy](contract.md#risk-policy), item 7.
- [Contract → Errors](contract.md#errors): `INSUFFICIENT_ROUTES`.

## Build

### 1. Risk display (`risk-display.ts`)

The one place for risk labels and map colors:

```ts
export const RISK_LABELS: Record<RiskLevel, string> = {
    low: 'Low',
    moderate: 'Moderate',
    high: 'High',
    severe: 'Severe',
    ['no_travel']: 'No Travel', // computed key: see Pitfalls
}

export const RISK_COLORS: Record<RiskLevel, string> = { ... } // hex, for MapLibre paint (13, 14)
```

- Colors get darker or stronger as risk rises, so they still read in grayscale.
- Every color appears with its text label. Check text contrast.

### 2. Risk badge (`components/risk-badge/`)

- `risk-badge.styles.ts`: `riskBadgeClasses: Record<RiskLevel, string>`, with Tailwind classes written out in full.
- The badge shows the label text, never color alone.

### 3. Formatters (`format.ts`)

| Value | Example |
|---|---|
| Miles | `133.2 mi` |
| Duration | `2 h 54 min` (from 10,440 s) |
| ETA | `Fri 2:54 PM EDT`, in the plan's `departureTimeZone` |
| Average risk | `0.40` (two decimals, scale 0–4) |

Rounding happens here, for display only.

### 4. Route card

Show for each route, in provider order:

- Name. A **Recommended** badge when `route.recommended`.
- Distance, drive time, ETA.
- No Travel, Severe and High miles.
- Average risk. Worst risk as a risk badge.
- A prominent warning when `noTravelMiles > 0`.

### 5. Comparison panel

- The priority explainer, in plain words:
  > We recommend the route with the fewest Severe miles. Ties go to fewest High miles, then lowest average risk, then shortest drive time. Routes with any No Travel miles are never recommended.
- All routes have No Travel (`recommendedRouteId === null`) → a **No route recommended** banner with the reason.
- Show `notices` from the response.
- An `INSUFFICIENT_ROUTES` error → "The routing provider returned {availableCount} routes. Three are needed to compare." Plus a retry action.

### 6. Selection

- Clicking a card or pressing Enter on it selects the route. Use button semantics with `aria-pressed`.
- `selectedRouteId` lives in `use-trip-planner`. Default: the recommended route, or route 1.
- Selection never changes the recommendation.

## Tests

- Three cards in provider order.
- The badge appears only on `recommendedRouteId`.
- A route with No Travel miles shows the warning.
- All No Travel → banner, no badge.
- Clicking a card calls the select handler. `aria-pressed` follows.
- `INSUFFICIENT_ROUTES` with `availableCount: 2` → the message shows "2".
- Formatters: 10,440 s → `2 h 54 min`. 133.24 → `133.2 mi`. ETA formatted in the given zone.
- Every `RiskLevel` has a label, a color and a badge class.
- Notices render.

## Done when

- [ ] `npm run check` passes.
- [ ] No component compares summaries to pick a winner. It reads `recommended`.

## Not in this session

- Map highlighting of the selected route (13).

## Pitfalls

- **`no_travel` as an object key.** ESLint's `camelcase` rule rejects a bare `no_travel` key. Prettier strips plain quotes from `'no_travel'`, so the error comes back. Write the key as `['no_travel']`; both tools accept that. (A scaffold-level `camelcase` allow-list would remove the need.)
- Don't sort cards by risk. The contract keeps provider order. The badge marks the winner.
- Don't hide No Travel miles because they aren't one of the four priorities. The contract shows them on every card.
- Never build Tailwind classes from fragments like `` `bg-${color}-500` ``. Tailwind only ships classes it sees written out in full.
