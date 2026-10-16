# Weather-Aware Truck Routing

A web app that helps truck drivers pick the safest route. It weighs weather, load weight, and travel time.

The app compares up to three routes. It checks the forecast at points along each route for the time the truck will reach them. Then it recommends one route.

## Repository layout

```text
backend/           Django REST API (Python 3.14, Django 6.1)
frontend/          Next.js web app (Node 24, Next.js 16, React 19)
docs/              Plans and working notes
requirements.md    Product requirements
```

## Getting started

1. Install the tools: Node.js 24.22.0 (`nvm use` reads `.nvmrc`) and [uv](https://docs.astral.sh/uv/) 0.13.1 or newer.
2. Run `npm install` in the repository root. This installs the git hooks and the root tools.
3. Run `npm run setup`. This installs both apps and creates their local env files.
4. Run `npm run dev`. The web app is on http://localhost:3000, the API on http://localhost:8000.

Each app's README has more detail: [backend/README.md](backend/README.md), [frontend/README.md](frontend/README.md).

## Run everything

All commands run from the repository root. `npm run` lists them.

| Command | What it does |
|---|---|
| `npm run setup` | Install both apps and create missing local env files |
| `npm run dev` | Both dev servers. Ctrl+C stops both. |
| `npm run check` | Every check for root config, backend, and frontend |
| `npm run format` | Format everything |
| `npm run stack:up` | Build the production images and run them with Docker Compose |
| `npm run stack:down` | Stop the Docker stack |
| `npm run stack:logs` | Follow the Docker stack's logs |

`npm run dev` and `npm run stack:up` both use ports 3000 and 8000. Run one at a time.

The Docker stack runs the production images over plain HTTP on localhost. It turns off the backend's HTTPS-only settings for that reason. See the comments in `compose.yaml`.

## Implementation policies

The assessment leaves these details open ([`requirements.md` §11](requirements.md#11-decisions-not-defined-by-the-assessment)). Each one below is **our choice, not a requirement**. The full API shape and every rule live in [`docs/sessions/contract.md`](docs/sessions/contract.md).

### Providers

- **Our choice:** HERE Routing v8 (truck mode, `alternatives=2`) for routes. HERE Geocoding v1 for place search. Open-Meteo for hourly forecasts. MapLibre GL for the map.
- **Our choice:** the driver picks the checkpoint spacing (10, 25 or 50 mi) in the form. The default is 25 mi.

### Time

- **Our choice:** the driver enters a local date and time and picks an IANA time zone. The browser turns that into one UTC instant. The API works only in UTC. It uses the time zone only to show times.
- **Our choice:** a local time that doesn't exist (spring forward) or happens twice (fall back) is a form error. The app never guesses.

### Travel progress and forecasts

- **Our choice:** checkpoints sit at 0, the spacing, twice the spacing, and so on, plus the destination. A route shorter than the spacing gets 2 checkpoints.
- **Our choice:** a checkpoint's ETA is departure plus the earlier sections' durations, plus its share of its own section's duration. HERE supplies each section's length and duration. This is an approximation, not traffic modelling.
- **Our choice:** the forecast hour for a moment is the first hourly value **at or after** that moment. On an exact hour, that hour is used.
- **Our choice:** wind is sustained wind at 10 m (`wind_speed_10m`), not gusts. Rain is `rain + showers`. Snow is `snowfall`. Both are sums over the hour before, used as the hourly rate.

### Risk rules

- **Our choice, boundaries:** at a shared boundary, the more dangerous level starts **at** the boundary. The one exception is the No Travel cut for rain and snow, where the source says `>`:
  - wind `<25`, `[25,35)`, `[35,45)`, `[45,55)`, `>=55` mph
  - rain `<0.10`, `[0.10,0.25)`, `[0.25,0.50)`, `[0.50,1.00]`, `>1.00` in/h
  - snow `<0.5`, `[0.5,1.0)`, `[1.0,2.0)`, `[2.0,3.0]`, `>3.0` in/h

  So wind at 25 mph is Moderate. Rain at exactly 1.00 in/h and snow at exactly 3.0 in/h are Severe.
- **Requirement, not ours:** the load overrides. A load of exactly 30,000 or 40,000 lb triggers no override.
- **Our choice:** the rules live in [`backend/routing/rules/risk_rules.json`](backend/routing/rules/risk_rules.json), version `assessment-2026-10`. To change them, edit the file and deploy. `manage.py check` rejects a broken file with `routing.E001`. The file sits behind a port, so a database-backed source can replace it later.
- **Our choice:** a checkpoint's risk is the **highest** of its wind, rain and snow levels. Its drivers are every condition tied at that level.

### Route summaries and the recommendation

- **Our choice:** risk scores are Low 0, Moderate 1, High 2, Severe 3, No Travel 4.
- **Our choice:** each checkpoint owns the stretch of road between the midpoints to its neighbours. Severe, High and No Travel miles add up those stretches. Each stretch counts only at its own level.
- **Our choice:** average risk is weighted by distance: the sum of (stretch miles × score), divided by route miles. It is never rounded before sorting.
- **Our choice:** a route with any No Travel miles can't be recommended. If every route has them, no route is recommended and a No Travel banner shows.
- **Requirement, not ours:** among the other routes, the four priorities in order: Severe miles, High miles, average risk, travel time. **Our choice:** a full tie goes to HERE's order.

### Missing data

- **Our choice:** a missing, null, negative or unreadable forecast value at any hour the plan uses fails the whole plan with `FORECAST_UNAVAILABLE`. Unknown weather is never treated as Low.
- **Our choice:** when HERE finds only 1 or 2 routes, the plan shows those, compares them by the same rules, and says how many were found. For example, Dallas to Houston has 2. The app never pads with made-up routes. Only when HERE finds no route does the plan fail, with `INSUFFICIENT_ROUTES`.
- **Our choice:** a trip, or its 48-hour heatmap, that reaches past the forecast range is refused as `VALIDATION_ERROR` on `departureAt`. A forecast is never stretched past its range.

### Heatmap

- **Our choice:** the heatmap shows combined risk from the same rules, with the truck's load, at each point and hour. It is a picture of the weather around the corridor, not a road-by-road risk.
- **Our choice:** the slider covers 0–48 hours from the entered departure, in 1-hour steps. Checkpoints keep showing risk at their own ETA. The slider shows its own valid time.
- **Our choice:** points sit every 25 mi along each route, plus points 15 mi to each side. A point within 5 mi of a kept point is dropped. With more than 90 points, the spacing grows ×1.25 until they fit.
- **Our choice:** under the slider, the app names the highest level at that hour, or says every point is Low. Low has no color, so a calm hour would otherwise look like a broken map.
- **Our choice:** the server computes all 49 frames in one response. MapLibre's heatmap layer blends between points. Moving the slider makes no network call.

### Limits

These are named constants in [`backend/routing/bootstrap.py`](backend/routing/bootstrap.py), not settings.

| Constant | Value | Why |
|---|---|---|
| `MAX_ROUTE_MILES` | 2,500 | Covers most US long hauls. Bounds forecast calls. |
| `MAX_HEATMAP_POINTS` | 90 | Bounds forecast calls and payload size. |
| `FORECAST_BATCH_SIZE` | 50 | Points per Open-Meteo request. |
| `FORECAST_DEDUPE_MILES` | 3 | Points this close share one forecast. |
| `HTTP_CONNECT_TIMEOUT_SECONDS` | 3 | Per attempt. |
| `HTTP_READ_TIMEOUT_SECONDS` | 10 | Per attempt. |
| `ROUTING_DEADLINE_SECONDS` | 15 | Total for one routing call, retries included. |
| `FORECAST_DEADLINE_SECONDS` | 25 | Total for all forecast batches. |
| `GEOCODING_DEADLINE_SECONDS` | 5 | Total for one place search. |

### Known limits

- No rest stops or hours-of-service rules. ETAs assume continuous driving.
- The load isn't sent to HERE as truck weight. It drives weather risk only, and HERE uses its default truck.
- Forecasts are estimates, not road-closure or dispatch clearances.
- Open-Meteo's free API is for non-commercial use. Commercial hosting needs its paid plan.
- Open-Meteo counts each location in a batch toward its daily quota. One Pittsburgh to Cleveland plan uses about 38 locations.
- The API doesn't compress responses. A plan is about 155 KB as JSON, or about 8 KB gzipped if the host compresses it.

## Traceability

Each acceptance criterion in [`requirements.md` §8](requirements.md#8-acceptance-criteria), with the tests that prove it. Paths are under `backend/tests/` or `frontend/src/shared/`.

| Acceptance criterion | Tests |
|---|---|
| Driver enters origin, destination, departure, load | `http/test_route_plans.py`, `http/test_places.py`, `components/trip-form/trip-form.test.tsx`, `components/trip-planner/trip-planner.acceptance.test.tsx` |
| Three route alternatives retrieved and displayed | `adapters/test_here_router.py`, `services/test_plan_trip.py`, `http/test_route_plan_end_to_end.py`, `components/route-comparison/route-comparison.test.tsx`, `components/route-map/route-map.test.tsx` |
| Checkpoints spaced at 10/25/50 miles | `domain/test_sampling.py`, `services/test_plan_trip.py`, `http/test_route_plan_end_to_end.py` |
| Forecast at each checkpoint's ETA | `domain/test_forecast.py`, `adapters/test_open_meteo_forecast.py`, `services/test_plan_trip.py` |
| Wind, rain, snow and load rules classify correctly | `domain/test_risk.py`, `adapters/test_json_risk_rules.py`, `test_checks.py` |
| Summaries compare Severe, High, average risk, time | `domain/test_ranking.py`, `components/route-comparison/route-comparison.test.tsx` |
| Recommendation follows the four priorities in order | `domain/test_ranking.py`, `http/test_route_plan_end_to_end.py`, `components/trip-planner/trip-planner.acceptance.test.tsx` |
| Map shows routes, checkpoints, risk, ETAs, summaries, recommendation | `components/route-map/route-map.test.tsx` (including the selected route's summary on the map), `components/route-comparison/route-comparison.test.tsx`, `components/trip-planner/trip-planner.acceptance.test.tsx` |
| Corridor heatmap with 0–48 h slider | `domain/test_corridor.py`, `utils/geojson.test.ts`, `components/weather-timeline/weather-timeline.test.tsx`, `components/route-map/route-map.test.tsx` |
| Hosted app, GitHub repo, Loom | Delivery tasks, not tests |

### End-to-end tests

- **Backend:** [`http/test_route_plan_end_to_end.py`](backend/tests/http/test_route_plan_end_to_end.py) runs one whole plan through the real HERE and Open-Meteo adapters. They replay recorded answers instead of calling the network, so the result never changes.
- **Frontend:** [`trip-planner.acceptance.test.tsx`](frontend/src/shared/components/trip-planner/trip-planner.acceptance.test.tsx) enters the same trip in the form and renders the backend's saved response.
- The saved response is [`frontend/tests/fixtures/route-plan.json`](frontend/tests/fixtures/route-plan.json). A backend test keeps it equal to what the API returns.

### Edge cases

| Case | Test |
|---|---|
| 1 or 2 routes → a plan of those routes, with a notice | `services/test_plan_trip.py::test_two_routes_are_planned_compared_and_named_in_a_notice`, `::test_one_route_is_planned_and_recommended_when_it_has_no_no_travel_miles`, `http/test_route_plans.py::test_two_routes_from_the_provider_are_a_plan_with_a_notice`, `utils/contract-guards.test.ts` "accepts 1 or 2 routes", `route-comparison.test.tsx` "fewer than three" |
| No route → `INSUFFICIENT_ROUTES`, shown in the UI with a retry | `services/test_plan_trip.py::test_no_route_is_insufficient_and_no_forecast_is_fetched`, `http/test_route_plans.py::test_each_service_error_has_its_status_and_code`, `trip-planner.test.tsx` "says when the provider found no route" |
| All routes No Travel → no recommendation, banner shown | `domain/test_ranking.py::test_no_route_is_recommended_when_every_route_has_no_travel_miles`, `http/test_route_plans.py::test_no_travel_everywhere_recommends_no_route`, `route-comparison.test.tsx` "shows a banner and no badge" |
| Null forecast at a used hour → `FORECAST_UNAVAILABLE`, no partial plan | `services/test_plan_trip.py::test_a_null_at_one_checkpoints_hour_fails_the_plan`, `::test_a_gap_that_only_the_last_heatmap_frame_reads_fails_the_plan` |
| Trip past forecast coverage → `VALIDATION_ERROR` on `departureAt` | `services/test_plan_trip.py::test_a_forecast_range_refusal_is_a_departure_error_not_a_provider_error`, `adapters/test_open_meteo_forecast.py::test_a_forecast_that_ends_inside_the_window_is_a_range_error` |
| Route shorter than the spacing → 2 checkpoints | `domain/test_sampling.py::test_checkpoints_sit_every_interval_then_at_the_destination` (`shorter than one interval`) |
| Nonexistent and ambiguous local times → form errors | `utils/date.test.ts`, `trip-form.test.tsx` (the `it.each` for departure times) |
| Provider timeout → 504, UI message with retry | `adapters/test_provider_http.py::test_timeouts_until_the_deadline_raise_provider_timeout`, `http/test_route_plans.py::test_each_service_error_has_its_status_and_code`, `trip-planner.test.tsx` "shows why a plan failed, with a retry" |
| Same origin and destination → 400 | `http/test_route_plans.py::test_the_same_origin_and_destination_is_a_400_naming_the_destination`, `trip-form.test.tsx` "refuses the same place" |
| Load exactly 30,000 and 40,000 → no override | `domain/test_risk.py::test_load_overrides_raise_the_wind_level` |
| Rain 1.00 and snow 3.0 → Severe | `domain/test_risk.py::test_rain_maps_to_its_band`, `::test_snow_maps_to_its_band` |
| Rain 0.09 + showers 0.01 → Moderate | `adapters/test_open_meteo_forecast.py::test_rain_and_showers_add_exactly` |
| The shipped `risk_rules.json` equals the spec | `adapters/test_json_risk_rules.py::test_the_shipped_file_equals_the_spec_rules` |
| A broken `risk_rules.json` → `manage.py check` fails with `routing.E001` | `test_checks.py::test_manage_py_check_runs_it` |

### Live smoke run

`uv run poe test:live` in `backend/` calls the real providers. Routes and forecasts change over time, so this records one day.

- **2026-10-16:** all 5 live tests passed. Three plans from Pittsburgh to Cleveland each returned 3 routes. With rain near Cleveland, the 4:00 PM EDT departure that day recommended Route 2, the only route that stayed Low. Calm departures on 2026-10-17 and 2026-10-19 recommended Route 1, the fastest. Dallas to Houston and Seattle to Portland each gave a plan of 2 routes, with the notice.
- **Duration:** the request log's `duration_ms` was about 1.7 s for the first plan, while connections opened, and about 0.5 s after that.
- **Size:** about 155 KB per plan, with 21 checkpoints and 37–38 heatmap points.

## Contributing

Branches, commit messages, and checks: [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
