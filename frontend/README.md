# Frontend

Next.js web app for weather-aware truck routing.

## Requirements

- Node.js 24.22.0 and npm 11.19.1. With nvm: `nvm use` reads `.nvmrc`.

## First run

```bash
cd frontend
npm install
cp .env.example .env.local    # API and map style URLs
npm run dev                   # http://localhost:3000
```

The app calls the API at `NEXT_PUBLIC_API_BASE_URL`. Run the backend locally for anything that needs data.

## Commands

| Command | What it does |
|---|---|
| `npm run dev` | Development server with Turbopack on port 3000 |
| `npm run check` | Everything CI runs before the build: format check, lint, types, tests |
| `npm run build` | Production build (standalone server in `.next/standalone`) |
| `npm run start` | Serve the production build |
| `npm run lint` / `npm run lint:fix` | ESLint, with zero warnings allowed |
| `npm run format` / `npm run format:check` | Prettier |
| `npm run typecheck` | Generate route types, then `tsc --noEmit` |
| `npm run test` / `npm run test:watch` | Vitest |

## Layout

```text
src/app/            Routes only: layouts, pages, route folders
src/context/        Shared state, one folder per context
src/shared/         Components, UI controls, services, types, utils, config
tests/              Shared test setup, fixtures, and factories
```

Structure, naming, and coding rules: [CONVENTIONS.md](CONVENTIONS.md).

## Configuration

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Base URL of the Django API, including `/api/v1` |
| `NEXT_PUBLIC_MAP_STYLE_URL` | MapLibre style JSON for the base map |

Both are public and inlined at build time. Both are required. `src/shared/config/app-config.ts` is the only module that reads them.

## Production

```bash
docker build -t truck-routing-frontend \
  --build-arg NEXT_PUBLIC_API_BASE_URL=https://api.example.com/api/v1 \
  --build-arg NEXT_PUBLIC_MAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty \
  .
docker run --rm -p 3000:3000 truck-routing-frontend
```

Public variables are fixed when the image is built. Build a new image to change them.

## Known audit findings

`npm audit` lists high-severity advisories for `braces`, reached through `@next/eslint-plugin-next`. They affect only local lint runs on our own files. The shipped app is clean: CI runs `npm audit --omit=dev --audit-level=high`. Recheck when `eslint-config-next` updates.
