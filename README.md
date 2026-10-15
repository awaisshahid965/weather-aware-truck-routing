# Weather-Aware Truck Routing

A web app that helps truck drivers pick the safest route. It weighs weather, load weight, and travel time.

The app compares three routes. It checks the forecast at points along each route for the time the truck will reach them. Then it recommends one route.

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

## Contributing

Branches, commit messages, and checks: [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
