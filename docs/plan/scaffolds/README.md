# Scaffold plans

These plans build the project's foundation: repository tooling, a Django API skeleton, and a Next.js app skeleton. They set up structure, configuration, tooling, tests, containers, and CI. They build no features.

## The plans

| Order | Plan | Creates |
|---|---|---|
| 1 | [01-repository.md](01-repository.md) | Root files: git hooks, commit rules, editor settings, Dependabot, README, contributing guide, license |
| 2 | [02-backend.md](02-backend.md) | `backend/`: Django 6.1 + DRF API skeleton, with Docker image and CI |
| 3 | [03-frontend.md](03-frontend.md) | `frontend/`: Next.js 16 + React 19 app skeleton, with Docker image and CI |

- Run plan 01 first. It installs the git hooks that the other two plug into.
- Plans 02 and 03 do not depend on each other. Run them in either order.
- Each plan is self-contained: prerequisites, versions, every file's full content, every command, verification, and the commit.
- Each plan is one branch and one pull request.

## Scope boundary

**The scaffold provides:**

- Folder structure and layer boundaries (enforced in the backend).
- Pinned toolchains and dependencies, with lockfiles.
- Settings from environment variables, with safe defaults and startup validation.
- Formatting, linting, strict type checking, and a working test setup in each app.
- A health probe, structured logging, and production security settings in the backend.
- Production Docker images, CI workflows, Dependabot, and git hooks.
- The libraries features will need, so feature work never installs packages: httpx, flexpolyline, tzdata, Hypothesis, and MapLibre GL.
- The settings features will need: `HERE_API_KEY`, `NEXT_PUBLIC_API_BASE_URL`, and `NEXT_PUBLIC_MAP_STYLE_URL`.

**Left to feature work:**

- API endpoints, serializers, views, and the API error format.
- Request-ID and request-logging middleware.
- Domain models, rules, ports, adapters, and the composition root (`routing/bootstrap.py`).
- Frontend types, the HTTP client, services, context, components, the map, and the heatmap.

## Version policy

All versions were checked on 2026-10-15. The rule: the latest stable release, unless a compatibility constraint holds it back. Every exception is stated with its reason.

| Tool | Chosen | Newest | Why it is held back |
|---|---|---|---|
| Node.js | 24.22.0 | 26.12.0 | Node 26 is "Current", not LTS. Production uses the newest LTS. |
| npm | 11.19.1 | 12.2.0 | Uses the npm bundled with Node 24.22.0, so no second install is needed. |
| Python | 3.14.8 | 3.15.0 | Django 6.1 officially supports Python 3.12 to 3.14 only. |
| TypeScript | 6.0.3 | 7.0.2 | typescript-eslint 8.71.2 (inside Next's ESLint config) supports TypeScript below 6.1 only. |
| ESLint | 9.39.5 | 10.12.0 | Next's ESLint plugins (react, import, jsx-a11y) declare ESLint 9 at most. |
| @types/node | 24.19.2 | 26.6.5 | Types must match the Node 24 runtime. |

Everything else is at its newest stable release.

## How the plans were checked

All three plans were run literally in a fresh scratch repository. A script extracted every file from the plans, then the plans' own commands ran with Node 24.22.0, uv 0.13.1, and Python 3.14.8. Results:

- Plan 01: hooks install; a bad commit message is rejected; root formatting passes.
- Plan 02: format, Ruff, 4 import contracts, mypy strict, and 18 tests pass. The deployment check rejects the development key and passes with a real one. The dev server answers `/healthz`. Gunicorn serves `/healthz` from a runtime-only environment.
- Plan 03: format, ESLint, type check, and 3 tests pass. The production build and the standalone server work. The production dependency audit is clean.
- Commits go through the hooks in all three. Both workflows pass actionlint.

Not run locally: the Docker image builds, and the GitHub Actions workflows themselves. Each workflow builds and smoke-tests its image on the first pull request.

## Conventions taken from the reference repositories

The backend reference is a TypeScript/Express service. Its principles are carried into Django, not its Node-specific code. The frontend reference is a Next.js app. Its structure is carried over directly.

| Practice in the references | How the scaffold applies it |
|---|---|
| Ports and adapters: services depend on interfaces, adapters implement them, one composition root wires them | `routing/{domain,ports,services,adapters,http}`, plus `bootstrap.py` later. import-linter enforces the dependency direction. |
| Caching as a decorator around a port, not a layer | `cached_<port>.py` naming rule |
| In-memory fakes for tests | `Fake<Port>` naming rule. Tests prefer fakes over mocks. |
| Typed config, read once, with defaults | `config/env.py` plus env-driven settings. Invalid values fail at startup. |
| Fail at boot, not on the first request | Env parsing raises at import. The container runs `check --deploy` before serving. |
| Liveness probe mounted before logging | `HealthCheckMiddleware`, first in the stack |
| Structured JSON logs with context fields | `JsonFormatter`, with context passed through `extra=` |
| Typed errors per layer, translated once at the HTTP edge | Convention. The exception handler arrives with the first endpoint. |
| Docstrings that explain decisions | Package docstrings state each layer's rule |
| Thin route handlers | Thin DRF views: parse, call one service, serialize |
| Prettier: no semicolons, single quotes, trailing commas, 120 columns, 4 spaces, LF | Frontend Prettier config. Ruff format makes the same choices for Python. |
| ESLint `camelcase` and `require-await` | Frontend ESLint rules |
| Husky pre-commit runs lint-staged | Root husky. lint-staged uses one config per app. |
| Commit-msg hook with type prefixes | Conventional Commits: `type(scope): summary` |
| Feature branches, merged by pull request | `CONTRIBUTING.md` |
| `.nvmrc`, `engine-strict`, `engines`, `packageManager` | Root and frontend. The Python equivalents: `.python-version`, `requires-python`, uv `required-version`. |
| Committed lockfiles | `package-lock.json` and `uv.lock`. CI installs with `npm ci` and `uv sync --locked`. |
| Next.js App Router, `src/`, `@/*` alias, Tailwind | Same, on Next.js 16 and Tailwind 4 |
| Folders `app/`, `context/`, `shared/{components,ui,services,types,utils}` | Same, plus `shared/config` |
| Component folders with `.types.ts`, `.styles.ts`, `.utils.ts`, `hooks/` | Same |
| Context split into `.interface.ts`, `.context.ts`, `.container.tsx` | Same, with a `null` default and a hook that throws outside its provider |
| Services as classes extending `HttpClient`, with static methods | Same |
| kebab-case files, PascalCase components, camelCase functions, UPPER_SNAKE constants | Same in the frontend. Python uses snake_case modules. |
| Variant class maps keyed by a closed set | Same, keyed by union types |
| Items on the backend reference's own to-do list: multi-stage non-root Dockerfile, `npm ci`, CI running types and lint, `.env.example`, a real test suite | All present from the first commit |

**Deliberately not carried over:**

| In a reference | Instead | Why |
|---|---|---|
| `react-hooks/exhaustive-deps` turned off | Left on | Turning it off hides stale-closure bugs |
| `'use client'` on the root layout | Server Components by default | A client root layout makes the whole tree client-side |
| Root `font-size: 10px` | Browser default | It overrides users' font-size settings |
| A committed `.env` | Only `.env.example` is committed | Secrets and local values stay out of git |
| UTF-16, CRLF `.npmrc` and `.nvmrc` | UTF-8, LF everywhere | Enforced by `.gitattributes` and `.editorconfig` |
| `exec 1> /dev/tty` in the pre-commit hook | Removed | It breaks GUI git clients and CI |
| Bash `[[ ]]` in a `sh` hook | POSIX `case` and `grep` | Works in every shell |
| Formatting rules in ESLint (indent, quotes, semi) | Prettier formats; `eslint-config-prettier` | Two tools must not own formatting |
| Context defaults with throwing stub functions | `null` default and a throwing hook | Clearer error, less boilerplate |
| `I` prefix on interfaces; TypeScript `enum` | Plain names; string-literal unions | Unions are erased at build time and match JSON from the API |
| A conventions doc saying 2-space indents while Prettier used 4 | The formatter config is the single source | Docs and tools cannot disagree |
| Single-stage Docker image, `npm install`, running as root | Multi-stage, lockfile installs, non-root user | Smaller, reproducible, safer images |
| Commented-out code | Not allowed | Git keeps history |
| Invalid numeric env values silently replaced by defaults | Startup error | Misconfiguration should be loud |
