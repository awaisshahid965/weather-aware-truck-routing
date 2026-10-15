import logging
import traceback
from collections.abc import Callable, Iterator

import httpx
import pytest

from routing.adapters.provider_http import MAX_BODY_BYTES, MAX_RETRIES, get_json
from routing.ports.errors import ProviderError, ProviderTimeoutError

URL = 'https://provider.example/v1/data'
KEY = 'key-that-must-stay-secret'
PARAMS = {'q': 'pittsburgh', 'apiKey': KEY}
DEADLINE_SECONDS = 15.0
CLIENT_TIMEOUT = httpx.Timeout(10, connect=3)
OK = {'ok': True}

Reply = Callable[[httpx.Request], httpx.Response]


class FakeClock:
    """Monotonic time that moves only when told: by `sleep`, or by a provider that is slow to fail."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class ScriptedProvider:
    """Answers each request with the next reply. The last reply repeats."""

    def __init__(self, *replies: Reply, clock: FakeClock | None = None, seconds_per_call: float = 0) -> None:
        self._replies = replies
        self._clock = clock
        self._seconds_per_call = seconds_per_call
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._clock is not None:
            self._clock.now += self._seconds_per_call
        return self._replies[min(len(self.requests), len(self._replies)) - 1](request)


def _status(code: int, headers: dict[str, str] | None = None) -> Reply:
    return lambda _request: httpx.Response(code, json=OK, headers=headers)


def _failure(error: type[httpx.TransportError]) -> Reply:
    def reply(request: httpx.Request) -> httpx.Response:
        raise error('scripted failure', request=request)

    return reply


def _get(provider: ScriptedProvider, clock: FakeClock, *, deadline_seconds: float = DEADLINE_SECONDS) -> object:
    with httpx.Client(transport=httpx.MockTransport(provider), timeout=CLIENT_TIMEOUT) as client:
        return get_json(client, URL, PARAMS, deadline_seconds=deadline_seconds, clock=clock, sleep=clock.sleep)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def test_a_503_then_200_succeeds_on_the_second_call(clock: FakeClock) -> None:
    provider = ScriptedProvider(_status(503), _status(200))

    result = _get(provider, clock)

    assert result == OK
    assert len(provider.requests) == 2
    assert len(clock.sleeps) == 1
    assert 0.25 <= clock.sleeps[0] <= 0.5


def test_the_request_carries_the_params(clock: FakeClock) -> None:
    provider = ScriptedProvider(_status(200))

    _get(provider, clock)

    assert provider.requests[0].method == 'GET'
    assert provider.requests[0].url.path == '/v1/data'
    assert dict(provider.requests[0].url.params) == PARAMS


@pytest.mark.parametrize('code', [302, 400, 401, 403, 404, 422])
def test_other_statuses_fail_without_a_retry(clock: FakeClock, code: int) -> None:
    provider = ScriptedProvider(_status(code), _status(200))

    with pytest.raises(ProviderError, match=f'answered {code}') as caught:
        _get(provider, clock)

    assert type(caught.value) is ProviderError
    assert len(provider.requests) == 1


def test_a_429_with_retry_after_0_is_retried_at_once(clock: FakeClock) -> None:
    provider = ScriptedProvider(_status(429, {'Retry-After': '0'}), _status(200))

    result = _get(provider, clock)

    assert result == OK
    assert len(provider.requests) == 2
    assert clock.sleeps == [0]


def test_a_retry_after_that_fits_the_deadline_is_waited(clock: FakeClock) -> None:
    provider = ScriptedProvider(_status(503, {'Retry-After': '3'}), _status(200))

    _get(provider, clock)

    assert clock.sleeps == [3]


def test_a_retry_after_past_the_deadline_fails_at_once(clock: FakeClock) -> None:
    provider = ScriptedProvider(_status(429, {'Retry-After': '60'}), _status(200))

    with pytest.raises(ProviderError, match='answered 429'):
        _get(provider, clock)

    assert len(provider.requests) == 1
    assert clock.sleeps == []


def test_a_5xx_is_retried_at_most_twice(clock: FakeClock) -> None:
    provider = ScriptedProvider(_status(500))

    with pytest.raises(ProviderError, match='answered 500'):
        _get(provider, clock)

    assert len(provider.requests) == MAX_RETRIES + 1


def test_backoff_grows_after_each_retry(clock: FakeClock) -> None:
    provider = ScriptedProvider(_status(502))

    with pytest.raises(ProviderError):
        _get(provider, clock)

    first, second = clock.sleeps
    assert 0.25 <= first <= 0.5
    assert 0.5 <= second <= 1.0


@pytest.mark.parametrize(
    'error', [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError]
)
def test_timeouts_and_lost_connections_are_retried(clock: FakeClock, error: type[httpx.TransportError]) -> None:
    provider = ScriptedProvider(_failure(error), _status(200))

    result = _get(provider, clock)

    assert result == OK
    assert len(provider.requests) == 2


@pytest.mark.parametrize(
    ('seconds_per_timeout', 'calls'),
    [
        pytest.param(4, 3, id='three attempts fit'),
        pytest.param(10, 2, id='the deadline stops the third attempt'),
    ],
)
def test_timeouts_until_the_deadline_raise_provider_timeout(
    clock: FakeClock, seconds_per_timeout: float, calls: int
) -> None:
    provider = ScriptedProvider(_failure(httpx.ConnectTimeout), clock=clock, seconds_per_call=seconds_per_timeout)

    with pytest.raises(ProviderTimeoutError, match='timed out'):
        _get(provider, clock)

    assert len(provider.requests) == calls


def test_a_lost_connection_after_the_last_retry_is_a_provider_error(clock: FakeClock) -> None:
    provider = ScriptedProvider(_failure(httpx.ConnectError))

    with pytest.raises(ProviderError, match='lost the connection: ConnectError') as caught:
        _get(provider, clock)

    assert type(caught.value) is ProviderError
    assert len(provider.requests) == MAX_RETRIES + 1


def test_a_body_that_arrives_past_the_deadline_is_a_timeout(clock: FakeClock) -> None:
    def slow_body() -> Iterator[bytes]:
        for chunk in (b'{"ok": ', b'true}'):
            clock.now += 10
            yield chunk

    provider = ScriptedProvider(lambda _request: httpx.Response(200, content=slow_body()))

    with pytest.raises(ProviderTimeoutError, match='did not finish within 15 s'):
        _get(provider, clock)

    assert len(provider.requests) == 1


def test_each_attempt_timeout_is_cut_to_the_time_left(clock: FakeClock) -> None:
    provider = ScriptedProvider(_status(200))

    _get(provider, clock, deadline_seconds=5)

    timeout = provider.requests[0].extensions['timeout']
    assert timeout == {'connect': 3, 'read': 5, 'write': 5, 'pool': 5}


def test_a_body_declared_over_the_limit_is_rejected(clock: FakeClock) -> None:
    provider = ScriptedProvider(lambda _request: httpx.Response(200, content=b' ' * (MAX_BODY_BYTES + 1)))

    with pytest.raises(ProviderError, match='body over'):
        _get(provider, clock)


def test_a_streamed_body_over_the_limit_is_rejected(clock: FakeClock) -> None:
    megabyte = b' ' * 1024 * 1024

    # An iterator body has no Content-Length, so only counting the bytes can catch it.
    provider = ScriptedProvider(lambda _request: httpx.Response(200, content=iter([megabyte] * 6)))

    with pytest.raises(ProviderError, match='body over'):
        _get(provider, clock)


@pytest.mark.parametrize(
    'body',
    [
        pytest.param(b'not json', id='not JSON'),
        pytest.param(b'{"length": NaN}', id='NaN'),
        pytest.param(b'{"length": Infinity}', id='Infinity'),
        pytest.param(b'[' * 100_000 + b']' * 100_000, id='nested too deep'),
    ],
)
def test_a_body_that_is_not_json_is_rejected(clock: FakeClock, body: bytes) -> None:
    provider = ScriptedProvider(lambda _request: httpx.Response(200, content=body))

    with pytest.raises(ProviderError, match='invalid JSON'):
        _get(provider, clock)


def test_a_retry_is_logged_with_the_path(clock: FakeClock, caplog: pytest.LogCaptureFixture) -> None:
    provider = ScriptedProvider(_status(503), _status(200))

    _get(provider, clock)

    [record] = [record for record in caplog.records if record.getMessage() == 'provider request retrying']
    assert record.levelno == logging.WARNING
    assert vars(record)['path'] == '/v1/data'
    assert vars(record)['retry'] == 1


def _connect_error_quoting_the_url(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError(f'cannot reach {request.url}', request=request)


@pytest.mark.parametrize(
    'reply',
    [
        pytest.param(_status(400), id='rejected'),
        pytest.param(_status(503), id='retried until it gives up'),
        pytest.param(_connect_error_quoting_the_url, id='an httpx error that quotes the URL'),
    ],
)
def test_the_key_never_reaches_errors_or_logs(clock: FakeClock, caplog: pytest.LogCaptureFixture, reply: Reply) -> None:
    # DEBUG on the root logger: only the logging settings keep httpx from logging the full URL.
    caplog.set_level(logging.DEBUG)
    provider = ScriptedProvider(reply)

    with pytest.raises(ProviderError) as caught:
        _get(provider, clock)

    assert '/v1/data' in str(caught.value)
    assert KEY not in ''.join(traceback.format_exception(caught.value))
    assert all(KEY not in str(vars(record)) for record in caplog.records)


@pytest.mark.parametrize('deadline_seconds', [0, -1, float('nan')])
def test_the_deadline_must_be_positive(clock: FakeClock, deadline_seconds: float) -> None:
    provider = ScriptedProvider(_status(200))

    with pytest.raises(ValueError, match='deadline_seconds must be > 0'):
        _get(provider, clock, deadline_seconds=deadline_seconds)

    assert provider.requests == []
