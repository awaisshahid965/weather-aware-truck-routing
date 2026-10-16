"""Request limits that keep the public site inside the providers' free allowances.

HERE bills for use past its free monthly allowance, and it has no setting that stops at a cap.
So the API stops first, in two steps:

- **Per visitor:** a rolling hourly limit, so one client can't use up everyone's day. Each worker
  process keeps its own count, so this one is approximate. It is about fairness, not cost.
- **For the whole site:** a daily limit per endpoint. Gunicorn runs several worker processes,
  and an in-memory count would give each its own. This count lives in one file, changed only
  under an exclusive lock, so every worker shares it exactly. The worst month is 31 times the
  daily limit, and `bootstrap` keeps that under each provider's allowance.

The visitor check runs first, and a request it refuses never counts toward the day. Counting
happens before the view, so a request that later fails validation still counts: the count can
run ahead of the provider calls made, never behind.
"""

import fcntl
import json
import logging
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.throttling import BaseThrottle, SimpleRateThrottle
from rest_framework.views import APIView

from routing import bootstrap

logger = logging.getLogger(__name__)


class DailyLimitReachedError(exceptions.Throttled):
    """The whole site has used today's allowance for one endpoint. It opens again at midnight UTC."""

    def __init__(self, what: str, wait: float) -> None:
        super().__init__(wait=wait)
        self.what = what
        self.retry_after_seconds = wait


class DailyQuota:
    """How many times each scope was used today (UTC), shared by every process through one file."""

    def __init__(self, path: Path, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        """`clock` returns aware UTC "now". Tests pass a fixed one."""
        self._path = path
        # A separate lock file: the data file is replaced on every write, and a lock on a replaced file guards nothing.
        self._lock_path = path.with_name(f'{path.name}.lock')
        self._clock = clock

    def try_use(self, scope: str, limit: int) -> bool:
        """Count one use and return True, or return False and count nothing once today's `limit` is reached."""
        today = self._clock().date().isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)  # released when the file closes
            counts = self._read(today)
            used = counts.get(scope, 0)
            if used >= limit:
                return False
            counts[scope] = used + 1
            self._write(today, counts)
            return True

    def seconds_until_reset(self) -> float:
        now = self._clock()
        tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        return (tomorrow - now).total_seconds()

    def _read(self, today: str) -> dict[str, int]:
        try:
            document = json.loads(self._path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {}
        except OSError, ValueError:
            # Writes are atomic, so only an outside edit gets here. Starting the day again beats refusing every request.
            logger.warning('daily quota file unreadable, starting today at zero', extra={'path': str(self._path)})
            return {}
        if not isinstance(document, dict) or document.get('day') != today:
            return {}
        counts = document.get('counts')
        if not isinstance(counts, dict):
            return {}
        return {
            scope: used
            for scope, used in counts.items()
            if isinstance(scope, str) and isinstance(used, int) and not isinstance(used, bool)
        }

    def _write(self, today: str, counts: dict[str, int]) -> None:
        # Written beside the file, then renamed over it: a crash mid-write never leaves half a file.
        handle, temporary = tempfile.mkstemp(dir=self._path.parent, prefix=f'{self._path.name}.', suffix='.tmp')
        with os.fdopen(handle, 'w', encoding='utf-8') as file:
            json.dump({'day': today, 'counts': counts}, file)
        Path(temporary).replace(self._path)


class _VisitorThrottle(SimpleRateThrottle):
    """A rolling limit per client address. Behind the proxy, `NUM_PROXIES` makes the address the visitor's."""

    def __init__(self, scope: str, rate: str) -> None:
        self.scope = scope
        self.rate = rate  # set before `super().__init__`, so it doesn't look the rate up in settings
        super().__init__()

    def get_cache_key(self, request: Request, view: APIView) -> str:
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class ProviderQuotaThrottle(BaseThrottle):
    """The visitor's hourly limit, then the site's daily one. Subclasses name the scope and read limits from bootstrap."""

    scope: str
    what: str  # plural noun for messages, such as `route plans`

    def visitor_rate(self) -> str:
        raise NotImplementedError

    def daily_limit(self) -> int:
        raise NotImplementedError

    def allow_request(self, request: Request, view: APIView) -> bool:
        self._visitor = _VisitorThrottle(self.scope, self.visitor_rate())
        if not self._visitor.allow_request(request, view):
            return False
        quota = DailyQuota(bootstrap.DAILY_QUOTA_PATH)
        limit = self.daily_limit()
        if not quota.try_use(self.scope, limit):
            logger.warning('daily limit reached', extra={'scope': self.scope, 'limit': limit})
            raise DailyLimitReachedError(self.what, wait=quota.seconds_until_reset())
        return True

    def wait(self) -> float | None:
        return self._visitor.wait()


class RoutePlansThrottle(ProviderQuotaThrottle):
    scope = 'route_plans'
    what = 'route plans'

    def visitor_rate(self) -> str:
        return bootstrap.ROUTE_PLANS_PER_VISITOR

    def daily_limit(self) -> int:
        return bootstrap.ROUTE_PLANS_PER_DAY


class PlacesThrottle(ProviderQuotaThrottle):
    scope = 'places'
    what = 'place searches'

    def visitor_rate(self) -> str:
        return bootstrap.PLACE_SEARCHES_PER_VISITOR

    def daily_limit(self) -> int:
        return bootstrap.PLACE_SEARCHES_PER_DAY
