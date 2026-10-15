"""Typed readers for environment variables.

Settings read the environment only through these helpers. Every variable is
parsed in one place, an empty value counts as unset, and a malformed value stops
the process at startup instead of failing the first request that needs it.
"""

import os

from django.core.exceptions import ImproperlyConfigured

_TRUE = frozenset({'1', 'true', 'yes', 'on'})
_FALSE = frozenset({'0', 'false', 'no', 'off'})


def _read(name: str) -> str | None:
    value = os.environ.get(name, '').strip()
    return value or None


def env_str(name: str, default: str) -> str:
    return _read(name) or default


def env_bool(name: str, default: bool) -> bool:
    value = _read(name)
    if value is None:
        return default
    if value.lower() in _TRUE:
        return True
    if value.lower() in _FALSE:
        return False
    raise ImproperlyConfigured(f'{name} must be true or false, got {value!r}')


def env_int(name: str, default: int) -> int:
    value = _read(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        raise ImproperlyConfigured(f'{name} must be an integer, got {value!r}') from None


def env_list(name: str, default: list[str]) -> list[str]:
    """Reads a comma-separated list, dropping blank items."""
    value = _read(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(',') if item.strip()]


def env_choice(name: str, default: str, choices: frozenset[str]) -> str:
    value = env_str(name, default)
    if value not in choices:
        raise ImproperlyConfigured(f'{name} must be one of {sorted(choices)}, got {value!r}')
    return value
