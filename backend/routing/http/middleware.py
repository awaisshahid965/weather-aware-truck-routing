"""A request ID for every request, and one log line when it completes.

The ID lives in a ContextVar, so the error handler and log calls read it without hanging
untyped attributes on the request.
"""

import logging
import re
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar

from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = 'X-Request-ID'
# Short and plain, so a client's ID can't forge log lines or bloat every record. Used with
# `fullmatch`: `$` would also accept a trailing newline.
_ACCEPTED_REQUEST_ID = re.compile(r'[A-Za-z0-9-]{1,64}')

_request_id: ContextVar[str | None] = ContextVar('request_id', default=None)


def current_request_id() -> str | None:
    """The ID of the request this thread is serving, or None outside a request."""
    return _request_id.get()


class RequestIdMiddleware:
    """Keeps a valid incoming `X-Request-ID`, or makes a uuid4, and echoes it on the response.

    Sits right after the health check, so probes are neither logged nor given an ID.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(REQUEST_ID_HEADER, '')
        request_id = incoming if _ACCEPTED_REQUEST_ID.fullmatch(incoming) else str(uuid.uuid4())
        token = _request_id.set(request_id)
        started = time.perf_counter()
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response[REQUEST_ID_HEADER] = request_id
        # The path only: a query string can carry what a user typed.
        logger.info(
            'request completed',
            extra={
                'method': request.method,
                'path': request.path,
                'status': response.status_code,
                'duration_ms': round((time.perf_counter() - started) * 1000),
                'request_id': request_id,
            },
        )
        return response
