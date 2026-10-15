# Session 15 — Acceptance

| | |
|---|---|
| Covers | Every acceptance criterion in [`requirements.md` §8](../../requirements.md#8-acceptance-criteria), except hosting and the Loom. |
| Needs | 01–14 |
| Layer | Both |
| Branch | `test/acceptance` · commit types `test(backend)`, `test(frontend)`, `docs` |
| Files | `backend/tests/http/test_route_plan_end_to_end.py`, `frontend/tests/fixtures/route-plan.json`, `frontend/src/shared/components/trip-planner/trip-planner.test.tsx`, root `README.md` (policy and traceability sections only) |

## Goal

Prove each acceptance criterion with a named test. Write down every policy we chose.

## Build

### 1. Deterministic end-to-end test (backend)

- Use the recorded HERE and Open-Meteo fixtures (Sessions 04, 05). The Open-Meteo fixture must cover the trip window.
- Build the real adapters on an `httpx.MockTransport` that serves the fixtures. Inject them by overriding `bootstrap.get_plan_trip_service`.
- `POST /api/v1/route-plans` through the Django test client.
- Assert: 3 routes, checkpoint spacing, 49 frames, the recommended route id and its summary numbers.
- Save the response as `frontend/tests/fixtures/route-plan.json`.

### 2. Deterministic end-to-end test (frontend)

- Render the planner with the saved response (mock `TripService.createPlan` to return it).
- Assert: three cards, the recommendation badge, the legend, and the slider labels at 0 and 48.

### 3. Live smoke run

- `uv run poe test:live` with a real key in `backend/.env`.
- Record the date, route count and recommended route in the README. Alternatives and forecasts change over time.

### 4. Edge-case sweep

Each line must point to a test that passes:

- [ ] Fewer than 3 routes → `INSUFFICIENT_ROUTES` with the count, shown in the UI.
- [ ] All routes No Travel → no recommendation, banner shown.
- [ ] Null forecast at a used hour → `FORECAST_UNAVAILABLE`, no partial plan.
- [ ] Trip ending beyond forecast coverage → `FORECAST_UNAVAILABLE`.
- [ ] Route shorter than the interval → 2 checkpoints.
- [ ] Nonexistent and ambiguous local times → form errors.
- [ ] Provider timeout → 504, UI message with retry.
- [ ] Same origin and destination → 400.
- [ ] Load exactly 30,000 and 40,000 → no override.
- [ ] Rain 1.00 and snow 3.0 → Severe.
- [ ] Rain 0.09 + showers 0.01 → Moderate.

### 5. Browser and performance check

- [ ] Desktop and phone widths: form, cards and map all usable.
- [ ] Keyboard only: complete a trip from empty form to result.
- [ ] Slider: smooth, no network while dragging.
- [ ] The request log shows route-plan duration. Note typical duration and response size in the README.

### 6. README sections

Add two sections to the root `README.md`. The requirements ask for policies to be documented there.

**Implementation policies.** Mark each one as our choice, not a requirement:

- Boundary rules ([contract → Risk policy](contract.md#risk-policy), item 2).
- Combined risk = max; drivers = ties.
- Forecast hour = first hour at or after the moment.
- Cell miles by midpoints. Average risk weighted by distance.
- No Travel routes are ineligible.
- Missing data fails the plan. Fewer than 3 routes fails the plan.
- Heatmap: hours from departure, 25 mi spacing, 15 mi laterals, 5 mi dedupe, cap 90.
- The limits table from the contract.
- Known limits:
  - No rest stops or hours-of-service rules.
  - No truck weight sent to routing.
  - Forecasts are estimates.
  - Open-Meteo's free API is for non-commercial use.
  - Open-Meteo counts each location in a batch toward its daily quota.

**Traceability.** Copy the acceptance map from the [session index](README.md#acceptance-criteria-map). Add the test file for each row.

### 7. Optional, only if time remains

- A rate limit on `/places`. This needs a new error code in the contract first.
- `decided_by` on the recommendation (Session 03). This also needs a contract change.
- A play button on the slider.

## Done when

- [ ] Every acceptance row has a passing test or a completed manual check.
- [ ] Every policy is in the README and marked as a policy.
- [ ] `uv run poe check`, `npm run check` and `npm run build` pass. CI is green on the pull request.

## Not in this session

- Hosting, deployment and the Loom walkthrough. Those are delivery tasks, outside the sessions.
