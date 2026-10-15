"""One JSON object per log line.

Hosting platforms index these fields without a parser. Anything a call site
passes through `extra=` becomes a top-level field, so context is added as
`logger.info('route planned', extra={'routes': 3})`, never by formatting it into
the message.
"""

import json
import logging
from datetime import UTC, datetime
from typing import override

# Attributes every LogRecord carries. Anything else on a record came from `extra=`.
_RECORD_ATTRIBUTES = frozenset(logging.makeLogRecord({}).__dict__) | {'message', 'asctime'}


class JsonFormatter(logging.Formatter):
    @override
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            'timestamp': datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec='milliseconds'),
            'level': record.levelname.lower(),
            'logger': record.name,
            'message': record.getMessage(),
        }
        entry.update({key: value for key, value in record.__dict__.items() if key not in _RECORD_ATTRIBUTES})
        if record.exc_info:
            entry['exception'] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)
