# Session 17 — Provider request limits

| | |
|---|---|
| Covers | Hosting: keep the public site inside HERE's free allowance |
| Needs | 16 |
| Layer | Backend HTTP |
| Branch | `feat/provider-quota` · commit types `feat(backend)`, `test(frontend)`, `docs` |
| Files | `routing/http/throttles.py`, `routing/http/errors.py`, `routing/http/views.py`, `routing/bootstrap.py`, `config/settings.py`, `tests/conftest.py`, `tests/http/test_throttles.py`, [contract](contract.md) |

## Goal

A public link can never cost money.

## Why

- HERE bills past its free monthly allowance: 5,000 truck routes and 30,000 geocodes. It has no setting that stops at a cap. Usage alerts only email, and only on some account types.
- Oracle's Always Free VM and Open-Meteo can't bill. Open-Meteo blocks for the day instead.

## Build

1. [Contract](contract.md): `429 RATE_LIMITED` with `details.retryAfterSeconds` and `Retry-After`; the limits table; a Request limits section.
2. `bootstrap.py`: `ROUTE_PLANS_PER_DAY = 125`, `PLACE_SEARCHES_PER_DAY = 600`, `ROUTE_PLANS_PER_VISITOR = '10/hour'`, `PLACE_SEARCHES_PER_VISITOR = '60/hour'`, `DAILY_QUOTA_PATH`.
3. `throttles.py`:
   - `DailyQuota`: counts per scope per UTC day in one JSON file, under `fcntl.flock` on a separate lock file. Writes go to a temporary file, then replace the old one.
   - `ProviderQuotaThrottle`: the visitor's DRF rate limit first, then the daily quota. A refused visitor never counts. At the daily limit it raises `DailyLimitReachedError`, with the wait to midnight UTC.
4. `errors.py`: both throttles become `429 RATE_LIMITED`, with a message and `Retry-After`.
5. `settings.py`: `NUM_PROXIES` is `0`, or `1` behind the TLS proxy. Unset, DRF trusts any `X-Forwarded-For`.

The frontend already shows the API's error message, so it needs no change.

## Tests

- The quota counts to its limit, keeps scopes apart, starts again at midnight UTC, shares one file, survives an unreadable file, and holds against 6 processes racing.
- Endpoints: a visitor over the hourly limit, another visitor unaffected, the site's daily limit with no provider call, refused requests not counted, place searches limited apart, and `X-Forwarded-For` trusted only behind the proxy.
- Frontend: the planner shows the daily limit message.

## Done when

- [ ] `uv run poe check`, `npm run check` and `npm run build` pass. CI is green.
- [ ] Deployed. The live site answers `429` past the visitor limit.
