import json
import logging
import sys

from django.test import RequestFactory

from config.json_logging import JsonFormatter


def _format(record: logging.LogRecord) -> dict[str, object]:
    entry: dict[str, object] = json.loads(JsonFormatter().format(record))
    return entry


def test_extra_fields_become_top_level_keys() -> None:
    record = logging.makeLogRecord(
        {'name': 'routing', 'levelname': 'INFO', 'levelno': logging.INFO, 'msg': 'route planned', 'routes': 3}
    )

    entry = _format(record)

    assert entry['level'] == 'info'
    assert entry['logger'] == 'routing'
    assert entry['message'] == 'route planned'
    assert entry['routes'] == 3


def test_exceptions_are_included() -> None:
    try:
        raise ValueError('provider timed out')
    except ValueError:
        record = logging.makeLogRecord({'levelname': 'ERROR', 'msg': 'request failed', 'exc_info': sys.exc_info()})

    entry = _format(record)

    assert 'ValueError: provider timed out' in str(entry['exception'])


def test_a_request_is_logged_as_its_method_and_path_without_the_query() -> None:
    request = RequestFactory().get('/api/v1/places', {'q': 'Pittsburgh, PA'})
    record = logging.makeLogRecord(
        {'levelname': 'WARNING', 'msg': 'Bad Request: %s', 'args': (request.path,), 'request': request}
    )

    entry = _format(record)

    assert entry['request'] == 'GET /api/v1/places'
    assert 'Pittsburgh' not in JsonFormatter().format(record)
