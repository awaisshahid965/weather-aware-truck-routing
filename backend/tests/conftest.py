from collections.abc import Iterator
from pathlib import Path

import pytest
from django.core.cache import cache

from routing import bootstrap


@pytest.fixture(autouse=True)
def fresh_request_limits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Every test starts with nothing counted: its own daily quota file and an empty per-visitor cache."""
    monkeypatch.setattr(bootstrap, 'DAILY_QUOTA_PATH', tmp_path / 'quota' / 'daily-quota.json')
    cache.clear()
    yield
    cache.clear()
