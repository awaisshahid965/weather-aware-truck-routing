# Implementation sessions

Each file is one working session. One session is one branch and one pull request. It ends with every check green.

## Before session 01

All three scaffold plans in [`docs/plan/scaffolds/`](../plan/scaffolds/README.md) are merged: 01 repository, 02 backend, 03 frontend.

Sessions never do project setup:

- No new packages.
- No new environment variables.
- No tooling, Docker or CI changes.

If a session truly needs one, change the scaffold plan first.

Tunables are named constants in `routing/bootstrap.py` (see [contract → Limits](contract.md#limits)). Only `HERE_API_KEY` comes from settings.

### What the scaffold already provides

| Sessions rely on | From |
|---|---|
| `routing/{domain,ports,services,adapters,http}` with import-linter contracts | Backend plan |
| httpx, flexpolyline, tzdata, Hypothesis | Backend plan |
| pytest marker `live`, run with `uv run poe test:live` | Backend plan |
| `HERE_API_KEY` setting, JSON logging, `/healthz` | Backend plan |
| maplibre-gl, Vitest, React Testing Library, user-event | Frontend plan |
| `API_BASE_URL`, `MAP_STYLE_URL` in `@/shared/config/app-config` | Frontend plan |
| Folders `context/` and `shared/{components,ui,services,types,utils}` | Frontend plan |

### What the scaffold leaves to sessions

The scaffold README names these as feature work:

| Feature work | Session |
|---|---|
| Domain rules, ports, adapters | 01–06, 09 |
| `routing/bootstrap.py` (composition root) | 08 |
| Endpoints, serializers, views | 08, 09 |
| API error format and its exception handler | 08 |
| Request-ID and request-logging middleware, registered in `config/settings.py` | 08 |
| Frontend types, HTTP client, services, context | 10 |
| Components, map, heatmap | 11–14 |

## Source of truth

1. [`requirements.md`](../../requirements.md): what the product must do.
2. [`contract.md`](contract.md): API shape and every implementation policy.
3. `backend/CONVENTIONS.md` and `frontend/CONVENTIONS.md`: structure, naming and style.
4. The session file: how to build one slice.

If a session disagrees with the contract, the contract wins. If it disagrees with a conventions file on style, the conventions file wins. Fix the session file.

## How to run a session

1. Branch from `main` with the name in the session header.
2. Read the session file and the contract sections it links.
3. Build the tasks in order.
4. Write the listed tests. Add any you find missing.
5. Run the full check: `uv run poe check` in `backend/`, or `npm run check` in `frontend/`.
6. Commit with the session's message type (for example `feat(backend): ...`). Open a pull request.
7. Tick the session in the index after it merges.

## Pipeline

```text
Place search (09) ─► Trip form (11) ─► POST /api/v1/route-plans (08)
                                          └─► PlanTrip service (07)
                                                ├─ HERE routes ........................ 04
                                                ├─ Checkpoints + ETAs ................. 02
                                                ├─ Corridor points .................... 06
                                                ├─ Open-Meteo hourly + forecast at ETA  05
                                                ├─ Risk per checkpoint and frame ...... 01
                                                └─ Summaries + recommendation ......... 03
Response ─► Route cards (12) · Route map (13) · Heatmap slider (14)
```

## Index

| # | Session | Layer | Covers | Needs | Done |
|---|---|---|---|---|---|
| 01 | [Risk rules and classifier](01-risk-classifier.md) | Backend domain + rules source | FR-03 | — | [x] |
| 02 | [Route checkpoints and ETAs](02-route-checkpoints.md) | Backend domain | FR-02 | 01 | [x] |
| 03 | [Summaries and recommendation](03-route-ranking.md) | Backend domain | FR-04 | 01, 02 | [x] |
| 04 | [HERE routing adapter](04-here-routing-adapter.md) | Backend port + adapter | FR-01 | 02 | [x] |
| 05 | [Forecast adapter, forecast at ETA](05-forecast-adapter.md) | Backend domain + adapter | FR-02 | 01, 04 | [x] |
| 06 | [Corridor heatmap data](06-corridor-heatmap.md) | Backend domain | FR-06 | 02, 05 | [x] |
| 07 | [PlanTrip service](07-plan-trip-service.md) | Backend service | FR-01–04, 06 | 01–06 | [x] |
| 08 | [Route plans API](08-route-plans-api.md) | Backend HTTP | Inputs, all FR data | 07 | [x] |
| 09 | [Place search](09-place-search.md) | Backend slice | Inputs | 08 | [x] |
| 10 | [Frontend contract and state](10-frontend-contract-state.md) | Frontend | — | contract | [ ] |
| 11 | [Trip form](11-trip-form.md) | Frontend | Inputs | 10 | [ ] |
| 12 | [Route comparison](12-route-comparison.md) | Frontend | FR-04 | 10 | [ ] |
| 13 | [Route map](13-route-map.md) | Frontend | FR-05 | 10, 12 | [ ] |
| 14 | [Heatmap timeline](14-heatmap-timeline.md) | Frontend | FR-06 | 13 | [ ] |
| 15 | [Acceptance](15-acceptance.md) | Both | All AC | all | [ ] |

Sessions 10–12 need only the contract. They can run alongside the backend sessions, using test factories.

## Rules for every session

**Backend** (details in `backend/CONVENTIONS.md`):

- The domain imports the standard library only. import-linter fails the check otherwise.
- Values are `@dataclass(frozen=True, slots=True)`. Closed sets are `StrEnum`. Ports are `Protocol`s.
- A number carries its unit in its name: `distance_miles`, `wind_mph`.
- Datetimes are aware UTC. Pass "now" in. The domain never reads the clock.
- Each failing layer has its own `errors.py`. Adapters raise port errors. Services translate them. HTTP maps them once.
- Exception names end in `Error`. Ruff rule `N818` fails the check otherwise.
- Fakes are `Fake<Port>` classes in `tests/services/fakes.py`. Adapter tests replay recorded JSON through `httpx.MockTransport`.
- Test names say the behaviour: `test_wind_at_55_mph_is_no_travel`. Separate arrange, act and assert with blank lines.
- Logs use a constant message plus `extra=`. Never log keys or provider payloads.
- A new test folder needs an `__init__.py`. The scaffold's test folders are packages.

**Frontend** (details in `frontend/CONVENTIONS.md`):

- Next.js 16 differs from older versions. Read the guide in `node_modules/next/dist/docs/` before using a Next.js API (see `frontend/AGENTS.md`).
- Components are typed `FC` arrow functions with a default export. Logic lives in `hooks/use-<name>.ts`.
- Closed sets come from `as const` arrays. No `enum`, no `any`.
- Components never call `fetch`; services do. Configuration comes only from `app-config.ts`.
- Tests sit next to the code as `*.test.ts(x)` under `src/`. Factories and fixtures live in `frontend/tests/`.
- Delete a folder's `.gitkeep` when its first real file lands.

**Both:**

- Never round before classifying or ranking. Round for display only.
- Default tests never touch the network.
- The frontend never classifies risk or ranks routes.

## Acceptance criteria map

| Acceptance criterion (requirements §8) | Sessions |
|---|---|
| Driver enters origin, destination, departure, load | 08, 09, 11 |
| Three route alternatives retrieved and displayed | 04, 07, 12, 13 |
| Checkpoints spaced at 10/25/50 miles | 02, 07 |
| Forecast at each checkpoint's ETA | 02, 05, 07 |
| Wind, rain, snow and load rules classify correctly | 01 |
| Summaries compare Severe, High, average risk, time | 03, 12 |
| Recommendation follows the four priorities in order | 03, 12 |
| Map shows routes, checkpoints, risk, ETAs, summaries, recommendation | 12, 13 |
| Corridor heatmap with 0–48 h slider | 06, 14 |
| Hosted app, GitHub repo, Loom | Delivery, not in sessions |
