"""Weather-aware truck routing.

Layers, from the inside out. Each package docstring states its rule, and
import-linter enforces the rules (see `[tool.importlinter]` in pyproject.toml).

- `domain`: business rules as plain Python.
- `ports`: interfaces for what the services need from outside.
- `services`: use cases that combine domain rules and ports.
- `adapters`: port implementations against real providers.
- `http`: the Django REST Framework boundary.
"""
