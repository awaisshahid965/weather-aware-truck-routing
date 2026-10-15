"""The one way adapters GET JSON from a provider.

It applies the contract's retry policy: at most two retries, only for failures that can
pass on their own (a timeout, a dropped connection, 429, 5xx), with jittered backoff and
one total deadline. Every httpx exception stops here and leaves as a port error.

Provider keys travel in the query string, so logs and errors name the URL path only.
"""

import json
import logging
import random
import time
from collections.abc import Callable, Mapping
from typing import NoReturn
from urllib.parse import urlsplit

import httpx

from routing.ports.errors import ProviderError, ProviderTimeoutError

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
MAX_BODY_BYTES = 5 * 1024 * 1024  # far above any real answer; a runaway body must not fill memory
BACKOFF_SECONDS = 0.5  # the first retry waits 0.25 to 0.5 s; each later ceiling doubles


def get_json(
    client: httpx.Client,
    url: str,
    params: Mapping[str, str],
    *,
    deadline_seconds: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> object:
    """GET `url` with `params` and return the decoded JSON body.

    `deadline_seconds` bounds the whole call, retries and waits included. Each attempt keeps
    the client's own per-phase timeouts, cut down to the time left. `clock` and `sleep` let
    tests run the retry policy without waiting.

    Raises `ProviderTimeoutError` when time runs out and `ProviderError` for any other failure.
    """
    if not deadline_seconds > 0:
        raise ValueError(f'deadline_seconds must be > 0, got {deadline_seconds!r}')
    return _Call(client, url, params, deadline_seconds, clock).run(sleep)


class _TransientError(Exception):
    """A failure that may pass on retry. `final` is what the caller gets if no retry is left."""

    def __init__(self, final: ProviderError, retry_after_seconds: float | None = None) -> None:
        super().__init__(str(final))
        self.final = final
        self.retry_after_seconds = retry_after_seconds


class _Call:
    """One `get_json` call: its target, its deadline and its attempts."""

    def __init__(
        self,
        client: httpx.Client,
        url: str,
        params: Mapping[str, str],
        deadline_seconds: float,
        clock: Callable[[], float],
    ) -> None:
        self._client = client
        self._url = url
        self._params = params
        self._deadline_seconds = deadline_seconds
        self._clock = clock
        self._ends_at = clock() + deadline_seconds
        self._path = urlsplit(url).path

    def run(self, sleep: Callable[[float], None]) -> object:
        retries = 0
        while True:
            try:
                body = self._attempt()
            except _TransientError as failure:
                delay = failure.retry_after_seconds
                if delay is None:
                    delay = _backoff_seconds(retries)
                # A wait that ends at the deadline leaves no time for the next attempt.
                if retries == MAX_RETRIES or self._clock() + delay >= self._ends_at:
                    raise failure.final from None
                retries += 1
                logger.warning(
                    'provider request retrying',
                    extra={
                        'path': self._path,
                        'retry': retries,
                        'reason': str(failure.final),
                        'delay_seconds': round(delay, 3),
                    },
                )
                sleep(delay)
                continue
            return _decode(body, self._path)

    def _attempt(self) -> bytes:
        remaining = self._ends_at - self._clock()
        if remaining <= 0:
            raise self._out_of_time()
        # `from None` below: an httpx message can quote the full URL, key included.
        try:
            with self._client.stream(
                'GET', self._url, params=self._params, timeout=_capped(self._client.timeout, remaining)
            ) as response:
                return self._read(response)
        except httpx.TimeoutException:
            raise _TransientError(ProviderTimeoutError(f'GET {self._path} timed out')) from None
        except (httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            raise _TransientError(
                ProviderError(f'GET {self._path} lost the connection: {type(exc).__name__}')
            ) from None
        except (httpx.HTTPError, httpx.InvalidURL, httpx.StreamError) as exc:
            raise ProviderError(f'GET {self._path} failed: {type(exc).__name__}') from None

    def _read(self, response: httpx.Response) -> bytes:
        status = response.status_code
        if status == 429 or 500 <= status < 600:
            raise _TransientError(
                ProviderError(f'GET {self._path} answered {status}'), _retry_after_seconds(response.headers)
            )
        if not 200 <= status < 300:
            raise ProviderError(f'GET {self._path} answered {status}')

        declared = response.headers.get('Content-Length', '')
        if declared.isascii() and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            raise self._too_large()
        # Count decoded bytes as they arrive: the header may be absent, or describe a compressed body.
        body = bytearray()
        for chunk in response.iter_bytes():
            body += chunk
            if len(body) > MAX_BODY_BYTES:
                raise self._too_large()
            if self._clock() >= self._ends_at:
                raise self._out_of_time()
        return bytes(body)

    def _too_large(self) -> ProviderError:
        return ProviderError(f'GET {self._path} answered with a body over {MAX_BODY_BYTES} bytes')

    def _out_of_time(self) -> ProviderTimeoutError:
        return ProviderTimeoutError(f'GET {self._path} did not finish within {self._deadline_seconds:g} s')


def _capped(timeout: httpx.Timeout, seconds: float) -> httpx.Timeout:
    """The client's per-phase timeouts, none longer than `seconds`. A phase without a limit gets `seconds`."""

    def cap(phase: float | None) -> float:
        return seconds if phase is None else min(phase, seconds)

    return httpx.Timeout(
        connect=cap(timeout.connect), read=cap(timeout.read), write=cap(timeout.write), pool=cap(timeout.pool)
    )


def _backoff_seconds(retries_done: int) -> float:
    # Half fixed, half random: retries stay spaced out, and clients that failed together spread apart.
    ceiling = BACKOFF_SECONDS * 2.0**retries_done
    return ceiling / 2 + random.uniform(0, ceiling / 2)  # noqa: S311 - jitter spreads load; it guards no secret


def _retry_after_seconds(headers: httpx.Headers) -> float | None:
    """`Retry-After` in seconds. The rare HTTP-date form falls back to normal backoff."""
    value = headers.get('Retry-After', '').strip()
    return float(value) if value.isascii() and value.isdigit() else None


def _decode(body: bytes, path: str) -> object:
    try:
        return json.loads(body, parse_constant=_reject_constant)
    except ValueError, RecursionError:
        # RecursionError: deeply nested arrays exhaust the parser's stack.
        raise ProviderError(f'GET {path} answered with invalid JSON') from None


def _reject_constant(name: str) -> NoReturn:
    # Python's parser accepts NaN and Infinity. JSON does not, and NaN slips past range checks.
    raise ValueError(f'{name} is not valid JSON')
