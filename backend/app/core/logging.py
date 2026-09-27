"""
Structured logging setup.

Two output shapes, chosen by `settings.ENV`:
- development: single-line, human-readable ("2026-01-01 12:00:00 INFO app.api
  request_completed method=POST path=/api/auth/login status=200 duration_ms=42")
- production: one JSON object per line, so a log shipper (CloudWatch, Loki,
  whatever) can parse fields without a custom grok pattern.

Call `configure_logging()` once, at import time in `app/main.py`, before any
other module logs anything. Every other module just does:

    import logging
    logger = logging.getLogger(__name__)

which is the standard library's normal pattern — nothing app-specific to
import, no risk of a circular import with `app/config.py`.
"""
import json
import logging
import sys
import time
from contextvars import ContextVar

from app.config import settings

# Populated per-request by RequestLoggingMiddleware, read by JsonFormatter /
# TextFormatter so every log line emitted while handling a request is
# automatically tagged with that request's id — without every call site
# having to pass it explicitly.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k
            not in (
                "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                "created", "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "message", "request_id", "taskName",
            )
        }
        extra_str = " ".join(f"{k}={v}" for k, v in extras.items())
        return f"{base} request_id={record.request_id}" + (f" {extra_str}" if extra_str else "")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        skip = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "request_id", "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in skip:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_plagiarism_checker_configured", False):
        return  # idempotent — safe to call more than once (e.g. in tests)

    root.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_ContextFilter())
    if settings.ENV == "production":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextFormatter("%(asctime)s %(levelname)-8s %(name)s %(message)s"))
    root.addHandler(handler)

    # Noisy third-party loggers: keep them at WARNING so app logs aren't
    # drowned out, but don't silence them entirely (a driver-level warning is
    # often the first sign something is wrong).
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx", "transformers", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root._plagiarism_checker_configured = True  # type: ignore[attr-defined]


def new_request_id() -> str:
    import uuid

    return uuid.uuid4().hex[:12]


class Timer:
    """Small helper: `with Timer() as t: ...` then `t.elapsed_ms`."""

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed_ms = round((time.perf_counter() - self._start) * 1000, 2)
