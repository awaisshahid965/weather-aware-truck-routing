"""The API's one error shape, for every exception a view raises.

`{"error": {"code", "message", "details"}, "requestId"}`. Messages state the rule that failed.
They never carry a key, a raw provider body or a stack trace.
"""

import logging
from collections.abc import Iterator, Mapping
from http import HTTPStatus
from typing import Any

from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.settings import api_settings

from routing.http.middleware import current_request_id
from routing.services.errors import (
    ForecastUnavailableError,
    InputValidationError,
    InsufficientRoutesError,
    UpstreamError,
    UpstreamTimeoutError,
)

logger = logging.getLogger(__name__)

VALIDATION_MESSAGE = 'The request is invalid. See details for each field.'
FORECAST_UNAVAILABLE_MESSAGE = 'The forecast is missing a value this plan needs, so there is no plan. Try again later.'
INTERNAL_ERROR_MESSAGE = 'Something went wrong on our side. Try again.'


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    """DRF's `EXCEPTION_HANDLER`. Views only raise; status, code and message are decided here."""
    match exc:
        case InputValidationError():
            return _error(
                HTTPStatus.BAD_REQUEST,
                'VALIDATION_ERROR',
                f'{exc.field} {exc.message}.',
                {exc.field: [_sentence(exc.message)]},
            )
        case InsufficientRoutesError():
            return _error(
                HTTPStatus.UNPROCESSABLE_CONTENT,
                'INSUFFICIENT_ROUTES',
                _sentence(str(exc)),
                {'availableCount': exc.available_count},
            )
        case ForecastUnavailableError():
            _log_failure('FORECAST_UNAVAILABLE', exc)
            return _error(
                HTTPStatus.UNPROCESSABLE_CONTENT,
                'FORECAST_UNAVAILABLE',
                FORECAST_UNAVAILABLE_MESSAGE,
                {'reason': exc.reason},
            )
        case UpstreamTimeoutError():  # before UpstreamError, its parent class
            _log_failure('PROVIDER_TIMEOUT', exc)
            return _error(HTTPStatus.GATEWAY_TIMEOUT, 'PROVIDER_TIMEOUT', _sentence(str(exc)))
        case UpstreamError():
            _log_failure('PROVIDER_ERROR', exc)
            return _error(HTTPStatus.BAD_GATEWAY, 'PROVIDER_ERROR', _sentence(str(exc)))
        case exceptions.ValidationError():
            return _error(HTTPStatus.BAD_REQUEST, 'VALIDATION_ERROR', VALIDATION_MESSAGE, _field_messages(exc.detail))
        case exceptions.ParseError():
            # Malformed JSON is invalid input, and the contract has one code for a 400.
            return _error(HTTPStatus.BAD_REQUEST, 'VALIDATION_ERROR', _sentence(str(exc.detail)))
        case exceptions.APIException():
            return _error(exc.status_code, exc.default_code.upper(), _sentence(str(exc.detail)))
        case _:
            logger.exception('unhandled error', exc_info=exc, extra={'request_id': current_request_id()})
            return _error(HTTPStatus.INTERNAL_SERVER_ERROR, 'INTERNAL_ERROR', INTERNAL_ERROR_MESSAGE)


def _error(status: int, code: str, message: str, details: Mapping[str, object] | None = None) -> Response:
    body = {
        'error': {'code': code, 'message': message, 'details': dict(details or {})},
        'requestId': current_request_id(),
    }
    return Response(body, status=status)


def _log_failure(code: str, exc: Exception) -> None:
    # The cause names the provider call by path and status, which the response leaves out.
    logger.warning(
        'request failed',
        extra={
            'code': code,
            'reason': str(exc),
            'cause': None if exc.__cause__ is None else str(exc.__cause__),
            'request_id': current_request_id(),
        },
    )


def _field_messages(detail: object) -> dict[str, list[str]]:
    """DRF's nested errors as flat paths, such as `origin.latitude`, each with its messages."""
    messages: dict[str, list[str]] = {}
    for field, message in _flatten(detail, ''):
        messages.setdefault(field, []).append(message)
    return messages


def _flatten(detail: object, path: str) -> Iterator[tuple[str, str]]:
    non_field = api_settings.NON_FIELD_ERRORS_KEY
    if isinstance(detail, Mapping):
        for key, value in detail.items():
            # A nested object's own error, such as "expected a dictionary", belongs to the object.
            child = path if key == non_field else f'{path}.{key}' if path else str(key)
            yield from _flatten(value, child)
    elif isinstance(detail, list):
        for item in detail:
            yield from _flatten(item, path)
    else:
        yield path or non_field, str(detail)


def _sentence(text: str) -> str:
    text = text[:1].upper() + text[1:]
    return text if text.endswith('.') else f'{text}.'
