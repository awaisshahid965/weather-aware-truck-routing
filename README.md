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

1. Install Node.js 24.22.0 (`nvm use` reads `.nvmrc`).
2. Run `npm install` in the repository root. This installs the git hooks.
3. Set up the API: [backend/README.md](backend/README.md).
4. Set up the web app: [frontend/README.md](frontend/README.md).

## Contributing

Branches, commit messages, and checks: [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
