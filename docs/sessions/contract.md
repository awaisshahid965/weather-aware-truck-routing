# API contract and implementation policies

This file is the single source of truth for the API shape and for every policy the sessions implement. [`requirements.md`](../../requirements.md) overrides it. Each policy here is **our choice**, not a requirement from the assessment. The project README must say so (Session 15).

## Conventions

- JSON over `/api/v1`.
- Times are UTC ISO 8601 instants with a trailing `Z`, in requests and responses. The frontend displays them in the chosen departure time zone.
- GeoJSON coordinate order is `[longitude, latitude]`.
- Units: distance in miles, duration in seconds, load in pounds, wind in mph, rain and snow in inches per hour.

## Endpoints

### `GET /healthz`

Provided by the scaffold. It returns `{"status": "ok"}` and lives outside `/api/v1`. Sessions don't touch it.

### `GET /api/v1/places?q=...`

Returns up to five places: `[{ "id", "label", "latitude", "longitude" }]`.

- `q` needs at least 3 non-space characters and at most 200.
- The client debounces typing and requires an explicit selection.
- `id` is an opaque provider id. The server never fetches a URL built from it.

### `POST /api/v1/route-plans`

Creates an **ephemeral calculation**. Nothing is stored.

Request:

```json
{
  "origin": {"label": "Pittsburgh, PA", "latitude": 40.4406, "longitude": -79.9959},
  "destination": {"label": "Cleveland, OH", "latitude": 41.4993, "longitude": -81.6944},
  "departureAt": "2026-10-16T12:00:00Z",
  "departureTimeZone": "America/New_York",
  "loadWeightLb": 32000,
  "checkpointIntervalMiles": 25
}
```

Validation:

- Coordinates are finite. Latitude is −90..90 and longitude −180..180.
- Origin and destination are at least 0.1 mi apart.
- `departureAt` is a UTC instant with `Z`. It is in the future. It allows a full 48-hour heatmap inside the forecast range.
- `departureTimeZone` is a valid IANA name. It is display context only; the UTC instant is authoritative.
- `loadWeightLb` is finite and ≥ 0.
- `checkpointIntervalMiles` is 10, 25 or 50.
- Labels are non-empty and at most 200 characters.

Success is `200`. The shape below is **abbreviated**: arrays are shortened to show field names, and the numbers are placeholders. A real response has three routes, all checkpoints, and 49 complete frames.

```json
{
  "generatedAt": "2026-10-15T12:00:00Z",
  "departureAt": "2026-10-16T12:00:00Z",
  "departureTimeZone": "America/New_York",
  "origin": {"label": "Pittsburgh, PA", "latitude": 40.4406, "longitude": -79.9959},
  "destination": {"label": "Cleveland, OH", "latitude": 41.4993, "longitude": -81.6944},
  "checkpointIntervalMiles": 25,
  "routes": [
    {
      "id": "route-1",
      "name": "Route 1",
      "geometry": {"type": "LineString", "coordinates": [[-79.9959, 40.4406], [-81.6944, 41.4993]]},
      "distanceMiles": 133.2,
      "durationSeconds": 10440,
      "etaAt": "2026-10-16T14:54:00Z",
      "checkpoints": [
        {
          "distanceFromStartMiles": 0,
          "latitude": 40.4406,
          "longitude": -79.9959,
          "etaAt": "2026-10-16T12:00:00Z",
          "windMph": 18,
          "rainInPerHour": 0,
          "snowInPerHour": 0,
          "risk": "low",
          "drivers": []
        }
      ],
      "summary": {
        "noTravelMiles": 0,
        "severeMiles": 0,
        "highMiles": 0,
        "averageRisk": 0.4,
        "worstRisk": "moderate"
      },
      "recommended": true
    }
  ],
  "recommendedRouteId": "route-1",
  "heatmap": {
    "variable": "combinedRisk",
    "startAt": "2026-10-16T12:00:00Z",
    "stepHours": 1,
    "frames": [
      {
        "offsetHours": 0,
        "validAt": "2026-10-16T12:00:00Z",
        "points": [{"latitude": 40.4406, "longitude": -79.9959, "risk": "low", "riskScore": 0}]
      }
    ]
  },
  "notices": ["Forecast risk is an estimate, not a road-closure or dispatch clearance."]
}
```

- Every value comes from provider data.
- Exactly three **distinct** routes, in provider order, with ids `route-1` … `route-3`. The ids are local to the response.
- Exactly 49 heatmap frames, offsets 0–48.
- Never extrapolate a forecast beyond its coverage.

### Errors

Every error uses one shape:

```json
{ "error": { "code": "...", "message": "...", "details": {} }, "requestId": "..." }
```

| Status | `code` | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Invalid input. `details` maps field → messages. |
| 422 | `INSUFFICIENT_ROUTES` | Fewer than 3 routes. `details.availableCount` gives the count. |
| 422 | `FORECAST_UNAVAILABLE` | A required forecast value is missing, invalid or out of range. |
| 502 | `PROVIDER_ERROR` | A provider failed or returned bad data. |
| 504 | `PROVIDER_TIMEOUT` | A provider timed out. |
| 500 | `INTERNAL_ERROR` | Anything unexpected. The message is generic. |

Errors never contain keys, raw provider bodies or stack traces. The UI shows the message and a retry action. It never invents routes to make up a shortfall.

## Limits

These are named constants in `routing/bootstrap.py`, passed into constructors. They are not environment settings.

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

Gunicorn kills a request after 60 s (scaffold). The deadlines keep a full plan well under that.

## Risk policy

The thresholds and load overrides below live in `backend/routing/rules/risk_rules.json`, version `assessment-2026-10`. That file is the single source of the values. A test pins it to this section, and a startup check rejects an invalid file.

1. Risk levels are ordered `low`, `moderate`, `high`, `severe`, `no_travel`, with scores 0–4.
2. At shared boundaries, the more dangerous level starts **at** the boundary, except for the rain and snow No Travel cuts:
   - wind `<25`, `[25,35)`, `[35,45)`, `[45,55)`, `>=55`
   - rain `<0.10`, `[0.10,0.25)`, `[0.25,0.50)`, `[0.50,1.00]`, `>1.00`
   - snow `<0.5`, `[0.5,1.0)`, `[1.0,2.0)`, `[2.0,3.0]`, `>3.0`

   So rain at exactly 1.00 and snow at exactly 3.0 are Severe. This matches the source's explicit `>` for No Travel.
3. Load overrides apply after the base wind level:
   - `>=55` mph → No Travel at any load.
   - `[45,55)` mph and load `>30000` lb → No Travel.
   - `[35,45)` mph and load `>40000` lb → Severe.

   Exactly 30000 or 40000 does **not** trigger an override. The checkpoint level is the max of wind, rain and snow. `drivers` names every condition tied at that max, such as `["wind", "snow"]`. `drivers` is empty when the level is `low`.
4. Forecast data (Open-Meteo):
   - Wind is `wind_speed_10m` (sustained, not gusts).
   - Rain is `rain + showers`. Snow is `snowfall`. Both are sums over the preceding hour, used as the hourly rate.
   - For a moment `t`, use the first hourly timestamp **at or after** `t`. On an exact hour, use that hour. The same rule applies to wind.
   - Verify unit metadata; never assume it.
   - Null, negative, NaN or missing values at a used hour are rejected.
   - Round for display only, never before classifying.
5. Checkpoints sit at `0, interval, 2×interval, …` plus the destination when it isn't already a sample. Route distance comes from HERE section lengths. A point's position is interpolated along its section's shape by geodesic length. ETA is departure plus the earlier sections' durations plus the section fraction × that section's duration. This is a transparent approximation, not traffic modelling.
6. Each checkpoint owns a cell bounded by the midpoints to its neighbours and by the route start and end. Cells sum to the route length. `highMiles`, `severeMiles` and `noTravelMiles` are **exclusive** level miles. `averageRisk = Σ(cellMiles × score) / routeMiles`, unrounded for sorting. `worstRisk` is the max checkpoint level.
7. Recommendation:
   - A route with `noTravelMiles > 0` is ineligible.
   - If every route is ineligible: `recommendedRouteId: null`, every `recommended: false`, and a prominent No Travel notice.
   - Among eligible routes, use these priorities in order: `severeMiles`, then `highMiles`, then `averageRisk`, then `durationSeconds`. A full tie goes to provider order.
   - No Travel miles show on every card, even though the four priorities don't mention them.
8. If any checkpoint, or any of the 49 heatmap frames, lacks a valid forecast, the whole plan fails with `FORECAST_UNAVAILABLE`. Unknown weather is never treated as Low. There is no recommendation from partial data.
9. Rules are read once per plan. Every checkpoint and heatmap frame in one plan uses the same rules. The rules version is logged with each plan.

## Heatmap policy

- The slider covers 0–48 hours **from the entered departure**, in one-hour steps.
- The heatmap shows combined weather and load risk, from the same classifier at each point and hour. It is an indicative weather field, not a road segment risk.
- Points sit around the union of the three routes:
  - Centers every 25 mi along each route, plus points 15 mi to each side.
  - Points within 5 mi of a kept point are dropped.
  - With more than 90 points, the spacing grows ×1.25 until they fit.
- The server computes all 49 frames. MapLibre's heatmap layer interpolates them visually.
- Checkpoint markers keep showing risk **at their own ETA** while the slider moves. The UI labels the slider's valid time separately, so the two meanings can't be confused.
- The heatmap can be hidden and shown again without a refetch.

## Providers

**HERE Routing v8:** `GET https://router.hereapi.com/v8/routes` with:

- `transportMode=truck`, `routingMode=fast`
- `origin=lat,lng`, `destination=lat,lng`
- UTC `departureTime`
- `alternatives=2` (the main route plus up to two alternatives)
- `return=polyline,summary,routeLabels`
- `apiKey`

HERE may return fewer alternatives. That is reported honestly, never padded. References: [routes](https://docs.here.com/routing/reference/routing-api-v8-calculateroutes), [geometry](https://docs.here.com/routing/docs/routing-v8-route-geometry).

**HERE Geocoding v1:** `GET https://geocode.search.hereapi.com/v1/geocode` with `q`, `limit=5`, `apiKey`. Reference: [request guide](https://docs.here.com/geocoding-and-search/docs/request-constructing).

**Open-Meteo Forecast:** `GET https://api.open-meteo.com/v1/forecast` with:

- comma-separated `latitude` and `longitude`
- `hourly=wind_speed_10m,rain,showers,snowfall`
- `wind_speed_unit=mph`, `precipitation_unit=inch`
- `timeformat=unixtime`, `timezone=GMT`
- a time window covering every checkpoint ETA and departure + 48 h

Reference: [docs](https://open-meteo.com/en/docs). The free public API is for non-commercial use. Commercial hosting needs Open-Meteo's paid endpoint and key, which would be a new scaffold setting.

**All providers:**

- Bounded timeouts.
- At most two retries, only on transient GET failures (timeout, connection error, 429, 5xx), with jitter and a total deadline.
- Never retry other 4xx.
- Never log the key or a query string that holds it.

## Product boundaries

- No accounts, saved trips, database, cache or background jobs. Add one only for a measured need.
- Risk rules change by editing `risk_rules.json` and deploying. They sit behind the `RiskRulesSource` port, so a database-backed source with an admin can replace the JSON adapter later without touching the classifier. That needs a database, which is out of scope now.
- Load weight drives weather risk only. It is not sent to routing as truck weight; HERE uses its default truck profile.
- The frontend never classifies risk or ranks routes. The API is authoritative.
