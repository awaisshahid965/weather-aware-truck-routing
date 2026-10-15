# Plan 04: Root commands and local Docker stack

## Goal

Run the whole project from the repository root, in two ways:

1. **Development:** `npm run dev` starts the Django and Next.js dev servers together. One Ctrl+C stops both.
2. **Production-like:** `npm run stack:up` builds the production images and runs them together with Docker Compose.

When this plan is done:

- The root `package.json` has scripts that set up, run, check, and format both apps.
- `compose.yaml` runs the backend and frontend images, wired together for `localhost`.
- A CI workflow starts the stack and checks that the API, the web app, and CORS between them work.
- The root README and contributing guide describe the new commands.

## Why it is built this way

- **Root scripts only delegate.** Each script calls the app's own tooling: `uv --directory backend run poe <task>` or `npm --prefix frontend run <script>`. No build logic lives at the root, so the root cannot drift from the apps.
- **Compose runs the production images, not a dev environment.** This project has no database, cache, or queue. Native dev servers already reload instantly, and dev containers would need extra Dockerfile stages, source mounts, and a separate `node_modules` volume. Compose is for a different job: one command to run the real images together, and proof that they work together before deploying.
- **The backend runs over plain HTTP in this stack.** The image's default command runs `manage.py check --deploy`, which demands HTTPS. Compose overrides the command to start gunicorn directly and turns off the HTTPS-only settings. The image is unchanged, so production keeps its startup safety check.
- **`concurrently` runs the two dev servers.** npm cannot run scripts in parallel by itself. `concurrently` labels each line (`[api]`, `[web]`) and stops the whole process tree of both servers on Ctrl+C. `--kill-others` stops one server if the other exits, so a crash is never hidden.

## Scope

**In scope:** root scripts, one new root dev dependency, `compose.yaml`, a CI workflow for the stack, root README and contributing updates, a root `.gitignore` entry.

**Out of scope:** changes inside `backend/` or `frontend/`, dev containers, a reverse proxy, HTTPS on localhost, and deployment.

## Prerequisites

| Tool | Version | Check |
|---|---|---|
| Node.js | 24.22.0 | `node --version` |
| npm | 11.19.1 | `npm --version` |
| uv | 0.13.1 or newer | `uv --version` |
| Docker Engine | 25 or newer | `docker --version` |
| Docker Compose | v2.20 or newer (v5 works) | `docker compose version` |
| A POSIX shell | Linux, macOS, or WSL | Scripts use `test` and `cp`, like the git hooks |

**Docker without sudo.** `docker info` must work as your normal user. If it says "permission denied" on `/var/run/docker.sock`, run `sudo usermod -aG docker $USER`, then log out and back in. Docker is needed only for the `stack:*` scripts. Everything else works without it.

Starting state:

- The repository root has `package.json` with husky, lint-staged, and Prettier, plus root `.prettierrc.json` and `.prettierignore`.
- `backend/` exists, with `pyproject.toml` defining the poe tasks `dev`, `check`, and `format`, plus `.env.example` and a `Dockerfile` with a `/healthz` health check.
- `frontend/` exists, with `package.json` defining the scripts `dev`, `check`, and `format`, plus `.env.example` and a `Dockerfile` that takes `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_MAP_STYLE_URL` as build arguments.
- Ports 3000 and 8000 are free.

Check it:

```bash
grep -q '"lint-staged"' package.json && test -f backend/pyproject.toml && test -f frontend/package.json \
  && test -f backend/Dockerfile && test -f frontend/Dockerfile && echo "ready"
```

## Versions

Checked on 2026-10-15 against the npm registry.

| Package | Version | Why |
|---|---|---|
| concurrently | 10.0.6 | Latest. Runs both dev servers in one terminal. Needs Node 22 or newer. No install scripts. |

The stack reuses the images that `backend/Dockerfile` and `frontend/Dockerfile` build. It pins no other versions.

## Target layout

```text
.
├── compose.yaml                  new: production images, wired for localhost
├── package.json                  changed: new scripts, concurrently
├── package-lock.json             changed (by npm)
├── .gitignore                    changed: ignores a root .env
├── README.md                     changed: "Getting started" and "Run everything"
├── CONTRIBUTING.md               changed: "Setup" and "Before opening a pull request"
└── .github/workflows/stack.yml   new: starts the stack in CI and probes it
```

## Steps

### 1. Create a branch

Start from a branch that already contains the backend and frontend scaffolds (normally an up-to-date `main`).

```bash
git switch main
git switch -c chore/local-stack
```

All paths below are relative to the repository root.

### 2. Root scripts

Replace the root `package.json` with this content. It keeps the existing hook scripts and dev dependencies. The old root-only `format` and `format:check` scripts become `format:root` and `check:root`, because `format` and `check` now cover the whole repository.

**`package.json`**

```json
{
  "name": "weather-aware-truck-routing",
  "private": true,
  "description": "Repository tooling: git hooks and commands that run both apps.",
  "engines": {
    "node": ">=24.22.0",
    "npm": ">=11.19.1"
  },
  "packageManager": "npm@11.19.1",
  "scripts": {
    "prepare": "husky",
    "lint-staged": "lint-staged",
    "setup": "npm run setup:backend && npm run setup:frontend",
    "setup:backend": "uv --directory backend sync && (test -f backend/.env || cp backend/.env.example backend/.env)",
    "setup:frontend": "npm --prefix frontend install && (test -f frontend/.env.local || cp frontend/.env.example frontend/.env.local)",
    "dev": "concurrently --names api,web --prefix-colors blue,magenta --kill-others \"npm:dev:backend\" \"npm:dev:frontend\"",
    "dev:backend": "uv --directory backend run poe dev",
    "dev:frontend": "npm --prefix frontend run dev",
    "check": "npm run check:root && npm run check:backend && npm run check:frontend",
    "check:root": "prettier --check .",
    "check:backend": "uv --directory backend run poe check",
    "check:frontend": "npm --prefix frontend run check",
    "format": "npm run format:root && npm run format:backend && npm run format:frontend",
    "format:root": "prettier --write .",
    "format:backend": "uv --directory backend run poe format",
    "format:frontend": "npm --prefix frontend run format",
    "stack:up": "docker compose up --build --wait && echo 'Web app: http://localhost:3000   API: http://localhost:8000/api/v1/'",
    "stack:down": "docker compose down",
    "stack:logs": "docker compose logs --follow"
  },
  "devDependencies": {
    "husky": "9.1.7",
    "lint-staged": "17.6.0",
    "prettier": "3.9.10"
  }
}
```

Add `concurrently`. `save-exact` in the root `.npmrc` pins it exactly.

```bash
npm install --save-dev concurrently@10.0.6
npm install-scripts ls
```

The second command must print `No packages with unreviewed install scripts.`

What each script does:

| Script | What it runs |
|---|---|
| `npm run setup` | `uv sync` in `backend/`, `npm install` in `frontend/`, and creates `backend/.env` and `frontend/.env.local` from their templates if they are missing. Existing env files are never overwritten. |
| `npm run dev` | Both dev servers: API on http://localhost:8000, web app on http://localhost:3000. Ctrl+C stops both. |
| `npm run dev:backend` / `dev:frontend` | One dev server only |
| `npm run check` | Root Prettier check, then every backend check, then every frontend check. Stops at the first failure. |
| `npm run check:root` / `check:backend` / `check:frontend` | One part only |
| `npm run format` | Formats root config, backend, and frontend |
| `npm run format:root` / `format:backend` / `format:frontend` | One part only |
| `npm run stack:up` | Builds both production images and starts them. Returns once both are healthy. |
| `npm run stack:down` | Stops the stack and removes its containers |
| `npm run stack:logs` | Follows the stack's logs |

`npm run dev` and `npm run stack:up` use the same ports (3000 and 8000). Run one or the other.

### 3. Docker Compose file

`compose.yaml` is the default file name Docker Compose looks for.

- **backend:** built from `backend/`. The command override and environment are explained in the comments.
- **frontend:** built from `frontend/`. The public URLs are build arguments, because Next.js inlines them at build time. The browser runs on your machine, so it reaches the API at `localhost:8000`.
- The frontend starts after the backend reports healthy. The backend image's own health check probes `/healthz`.
- `HERE_API_KEY` comes from your shell or from a root `.env` file, which Compose reads automatically. It may be empty.

**`compose.yaml`**

```yaml
# Runs the production images together on this machine: one command for anyone who
# wants the whole app without installing Python or Node. Day-to-day development uses
# `npm run dev` instead (native dev servers, instant reload).

name: weather-aware-truck-routing

services:
  backend:
    build:
      context: backend
    image: truck-routing-backend:local
    # The image's default command runs `manage.py check --deploy`, which demands HTTPS.
    # This stack serves plain HTTP on localhost, so it starts gunicorn directly and
    # turns off the HTTPS-only settings below. Production keeps the image's command.
    command: ['gunicorn', 'config.wsgi']
    environment:
      DJANGO_DEBUG: 'false'
      DJANGO_SECRET_KEY: local-compose-only-key-never-use-in-production
      DJANGO_ALLOWED_HOSTS: localhost,127.0.0.1
      CORS_ALLOWED_ORIGINS: http://localhost:3000
      DJANGO_SECURE_SSL_REDIRECT: 'false'
      DJANGO_SECURE_HSTS_SECONDS: '0'
      HERE_API_KEY: ${HERE_API_KEY:-}
    ports:
      - '8000:8000'

  frontend:
    build:
      context: frontend
      # Inlined into the browser bundle at build time. The browser runs on the host,
      # so it reaches the API through the published port on localhost.
      args:
        NEXT_PUBLIC_API_BASE_URL: http://localhost:8000/api/v1
        NEXT_PUBLIC_MAP_STYLE_URL: https://tiles.openfreemap.org/styles/liberty
    image: truck-routing-frontend:local
    ports:
      - '3000:3000'
    depends_on:
      backend:
        condition: service_healthy
```

The secret key above is safe to commit. It only signs data inside this local stack, and the production image refuses any key that has not been set on purpose.

### 4. Ignore a root `.env`

A root `.env` holds values that Compose reads, such as `HERE_API_KEY`. It must never be committed. Add these lines to the end of the root `.gitignore`:

```gitignore

# Local values for Docker Compose (for example HERE_API_KEY)
.env
```

### 5. CI workflow for the stack

The backend and frontend workflows build and test each image alone. This workflow starts both together, the same way `npm run stack:up` does, and probes three things:

1. The API's `/healthz`.
2. The web app's home page.
3. A CORS preflight from the web app's origin to the API.

It is also the check that runs when your own machine has no Docker.

**`.github/workflows/stack.yml`**

```yaml
name: Stack

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  compose:
    name: Start the stack and probe it
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Build the images and start the stack
        run: docker compose up --build --wait --wait-timeout 180
      - name: Probe the API, the web app, and CORS between them
        run: |
          curl --fail --silent http://localhost:8000/healthz
          curl --fail --silent --output /dev/null http://localhost:3000/
          curl --silent --include --request OPTIONS \
            --header 'Origin: http://localhost:3000' \
            --header 'Access-Control-Request-Method: POST' \
            http://localhost:8000/api/v1/ | grep --ignore-case '^access-control-allow-origin: http://localhost:3000'
      - name: Show the logs
        if: failure()
        run: docker compose logs
      - name: Stop the stack
        if: always()
        run: docker compose down
```

### 6. Root README

In `README.md`, replace the whole `## Getting started` section, up to but not including `## Contributing`, with:

````markdown
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
````

### 7. Contributing guide

In `CONTRIBUTING.md`, replace the whole `## Setup` section, up to but not including `## Branches`, with:

```markdown
## Setup

With Node.js 24.22.0 and uv installed, run these once in the repository root:

1. `npm install`: installs the git hooks and root tools.
2. `npm run setup`: installs both apps and creates their local env files.

```

Then replace the whole `## Before opening a pull request` section, up to but not including `## Dependencies`, with:

```markdown
## Before opening a pull request

Run `npm run check` in the repository root. It runs the root formatting check and every backend and frontend check. CI runs the same app checks.

To check one app only: `npm run check:backend` or `npm run check:frontend`.

Fill in the pull request template: what changed, why, and how you tested it.

```

### 8. Format the root files

```bash
npm run check:root
```

Expected: `All matched files use Prettier code style!`. If it lists a file, run `npm run format:root`, then check again.

## Verify

Run from the repository root.

| # | Command | Expected |
|---|---|---|
| 1 | `npm install` | Exits cleanly, `found 0 vulnerabilities` |
| 2 | `npm install-scripts ls` | `No packages with unreviewed install scripts.` |
| 3 | `npm run setup` | `uv sync` and the frontend `npm install` finish. `backend/.env` and `frontend/.env.local` exist. |
| 4 | Add a line to `backend/.env`, then run `npm run setup` again | The line is still there. Existing env files are kept. |
| 5 | `npm run check` | Root Prettier passes. Backend: 4 layer contracts kept, mypy clean, 18 tests passed. Frontend: lint clean, 3 tests passed. |
| 6 | `npm run dev` | Output lines are prefixed `[api]` and `[web]`. http://localhost:8000/healthz returns `{"status": "ok"}`. http://localhost:3000 shows "Weather-Aware Truck Routing". |
| 7 | Press Ctrl+C in the `npm run dev` terminal | Both servers stop. `ss -ltn \| grep -E ':(3000\|8000)\b'` prints nothing. |
| 8 | `docker compose config --quiet` | No output: the file is valid. Works without the Docker daemon. |
| 9 | (Docker) `npm run stack:up` | Both images build. The command returns once both containers are healthy, then prints the two URLs. |
| 10 | (Docker) `curl http://localhost:8000/healthz` and open http://localhost:3000 | `{"status": "ok"}`, and the home page |
| 11 | (Docker) `curl -si -X OPTIONS -H 'Origin: http://localhost:3000' -H 'Access-Control-Request-Method: POST' http://localhost:8000/api/v1/` | The headers include `access-control-allow-origin: http://localhost:3000` |
| 12 | (Docker) `npm run stack:down` | Both containers stop and are removed |
| 13 | `actionlint .github/workflows/stack.yml`, if you have actionlint | No findings |

If Docker is not available on your machine, rows 9 to 12 run in CI instead: the Stack workflow does the same steps on every pull request.

## Commit

```bash
git add package.json package-lock.json compose.yaml .gitignore README.md CONTRIBUTING.md .github/workflows/stack.yml
git commit -m "chore: add root dev commands and local Docker stack"
git push -u origin chore/local-stack
```

The pre-commit hook formats the staged root JSON and YAML. Open a pull request into `main`. All CI workflows, including Stack, must be green before merging.

## Done when

- [ ] `npm run setup`, `npm run check`, and `npm run dev` work from the repository root.
- [ ] Ctrl+C stops both dev servers.
- [ ] The Stack workflow passes on the pull request. If you have Docker locally, `npm run stack:up` passes too.
- [ ] The README and contributing guide list the new commands.
- [ ] The pull request is merged into `main`.
