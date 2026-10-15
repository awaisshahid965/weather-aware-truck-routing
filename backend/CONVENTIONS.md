# Backend conventions

Rules for code in `backend/`. Tools enforce most of them. Reviews enforce the rest.

## Architecture: ports and adapters

Dependencies point inward. Business rules never know which provider, framework, or transport is in use.

```text
HTTP request
    │
    ▼
routing.http ──────────► routing.bootstrap ──────────► routing.adapters
 (DRF views,              (composition root:             (HERE, weather API,
  serializers)             builds adapters,               caches)
    │                      injects them)                      │
    ▼                            │                            │ implements
routing.services ◄───────────────┘                            ▼
 (use cases) ──────────────────────────────────────────► routing.ports
                                                          (Protocols)
                                                              │
                                                              ▼
                                                        routing.domain
                                                         (pure rules)
```

| Package | Holds | May import | Must not import |
|---|---|---|---|
| `routing.domain` | Business rules and value objects | Standard library | Anything else |
| `routing.ports` | `typing.Protocol` interfaces and their typed errors | `domain` | `services`, `adapters`, `http`, Django, httpx |
| `routing.services` | Use cases | `domain`, `ports` | `adapters`, `http`, Django, httpx |
| `routing.adapters` | Port implementations for real providers | `domain`, `ports`, httpx, provider libraries | `services`, `http` |
| `routing.http` | DRF views, serializers, routes, error translation | `services`, `domain`, `bootstrap`, DRF | `adapters` directly |
| `routing.bootstrap` | Composition root | Everything in `routing`, Django settings | — |
| `config` | Django project and shared infrastructure | Django | `routing` code (dotted-path strings in settings and URLs are fine) |

`uv run poe lint` runs import-linter. It enforces the first five rows. A broken contract fails CI.

**Composition root.** `routing/bootstrap.py` is created with the first service. It is the only module that reads provider settings and constructs adapters. It exposes small provider functions, such as `get_plan_trip_service()`. Views call them. Tests replace them to inject fakes.

**Cross-cutting behaviour is a decorator, not a layer.** For example, caching wraps a port: `CachedForecast` implements the same Protocol as the real adapter and holds it. Services never know caching exists. Turning it off is a one-line change in the composition root.

## Naming

| Thing | Style | Example |
|---|---|---|
| Package, module | `snake_case` | `routing/adapters/here_router.py` |
| Class | `PascalCase` | `HereRouter`, `RoutePlan` |
| Function, method, variable | `snake_case` | `plan_trip`, `arrival_time` |
| Constant | `UPPER_SNAKE_CASE` | `MAX_CHECKPOINTS` |
| Private name | Leading underscore | `_parse_route` |
| Port | The role it plays, no `I` prefix | `RouteProvider` |
| Adapter module | `<vendor>_<capability>.py` | `open_meteo_forecast.py` → `OpenMeteoForecast` |
| Decorator adapter | `<concern>_<port>.py` | `cached_forecast.py` → `CachedForecast` |
| Test fake | `Fake<Port>` in `tests/<layer>/fakes.py` | `FakeRouteProvider` |
| Test | `test_<expected_behaviour>` | `test_wind_at_55_mph_is_no_travel` |

## Code

- Annotate every function. mypy runs in strict mode on all code, tests included.
- Value objects are `@dataclass(frozen=True, slots=True)`. Closed sets are `enum.StrEnum`. Outside capabilities are `typing.Protocol`.
- `Any` stays at untrusted boundaries: provider JSON and request bodies. Narrow it to a typed value right away. Never pass raw provider dictionaries inward.
- Datetimes are timezone-aware. Ruff's `DTZ` rules reject naive ones.
- A number with a unit carries the unit in its name: `distance_miles`, `wind_mph`, `duration_seconds`.
- Domain functions are pure. Pass the current time in; never read the clock in the domain.
- Keep modules small and single-purpose. Split a module when it needs a table of contents.

## Errors

- Each layer that can fail defines typed exceptions in its own `errors.py`.
- Adapters catch provider and transport failures and raise the port's errors. httpx exceptions never leave an adapter.
- The HTTP layer turns errors into responses in one place: a DRF exception handler. Views do not catch and format errors themselves.
- Error messages state the rule that failed. They never contain secrets or raw provider payloads.

## Configuration

- Only `config/settings.py` reads environment variables, always through `config/env.py`.
- Defaults are safe for local development and tests. Production values come from the environment.
- Every variable is listed in `.env.example`, with a comment.
- Services receive settings as constructor arguments from the composition root. `domain` and `services` never import `django.conf.settings`.

## HTTP API

- Every endpoint lives under `/api/v1/`. JSON in, JSON out.
- A view parses input with a serializer, calls one service, and returns the serialized result. No business rules in views.
- `/healthz` is the liveness probe. It is middleware, not a route.

## Logging

- Declare `logger = logging.getLogger(__name__)` at the top of the module.
- Keep the message constant. Put context in `extra`: `logger.info('route planned', extra={'routes': 3})`.
- Never log secrets, API keys, or full provider payloads.
- Production logs one JSON object per line (`LOG_FORMAT=json`). Local development uses `text`.

## Tests

- pytest. Tests live in `tests/` and mirror the package: `tests/domain/`, `tests/services/`, `tests/adapters/`, `tests/http/`.
- Prefer small hand-written fakes that implement a port over mocks.
- Default tests never touch the network. Adapter tests replay recorded JSON through `httpx.MockTransport`.
- Tests that call real provider APIs carry `@pytest.mark.live`. They are skipped by default. Run them with `uv run poe test:live`.
- Use Hypothesis for rules that must hold for every input, such as thresholds and orderings.
- Structure each test as arrange, act, assert, separated by blank lines.

## Comments and docstrings

- Every package has a docstring that states its rule.
- Docstrings and comments explain why: the decision, the constraint, the trade-off. The code already says what.
- No commented-out code. Delete it; git keeps the history.

## Formatting

Ruff formats everything: 4-space indents, single quotes, 120-column lines, LF endings. Do not format by hand. Run `uv run poe format`.
