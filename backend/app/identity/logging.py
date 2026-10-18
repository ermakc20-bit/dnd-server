from __future__ import annotations

import logging
import re

JOIN_URL = re.compile(
    r'(/(?:api/v1/)?join/)[^/?#\s"]+((?:/[^?#\s"]*)?)(?:[?#][^\s"]*)?',
    re.IGNORECASE,
)


def _redact_join_url(value: str) -> str:
    # Preserve the operation suffix, but never log invitation paths or their query values.
    return JOIN_URL.sub(r"\1[REDACTED]\2", value)


class JoinTokenLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact_join_url(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                _redact_join_url(value) if isinstance(value, str) else value
                for value in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: _redact_join_url(value) if isinstance(value, str) else value
                for key, value in record.args.items()
            }
        return True


def configure_access_log_redaction() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, JoinTokenLogFilter) for item in logger.filters):
        logger.addFilter(JoinTokenLogFilter())
