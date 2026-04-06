"""
Central logging configuration for SimpleSeed.

Usage
-----
    from logging_config import setup_logging
    setup_logging()   # call once at app startup

Context tracking
----------------
    from logging_config import analysis_id_var, request_id_var
    request_id_var.set("ab12cd34")   # set by RequestLoggingMiddleware
    analysis_id_var.set(rfp_id)      # set in _run_analysis() when rfp_id is created

Every log record — from any logger in any module — automatically includes
the current request_id and analysis_id (first 8 chars each) via _ContextFilter.

Environment variables
---------------------
    LOG_LEVEL   DEBUG | INFO | WARNING | ERROR   (default: INFO)
"""

import logging
import os
from contextvars import ContextVar

# ---------------------------------------------------------------------------
# Context variables — set once per request / per analysis; propagate via async
# ---------------------------------------------------------------------------

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
analysis_id_var: ContextVar[str] = ContextVar("analysis_id", default="-")


# ---------------------------------------------------------------------------
# Filter: attach context IDs to every log record
# ---------------------------------------------------------------------------

class _ContextFilter(logging.Filter):
    """Inject request_id and analysis_id from ContextVars into each LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = request_id_var.get("-")
        aid = analysis_id_var.get("-")
        # Display at most 8 chars; use "-" padding when value is default
        record.request_id = rid[:8] if rid != "-" else "-       "
        record.analysis_id = aid[:8] if aid != "-" else "-       "
        return True


# ---------------------------------------------------------------------------
# Log format
# ---------------------------------------------------------------------------

_LOG_FORMAT = (
    "%(asctime)s %(levelname)-8s "
    "[req=%(request_id)s rfp=%(analysis_id)s] "
    "%(name)s: %(message)s"
)
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# ---------------------------------------------------------------------------
# Public setup function
# ---------------------------------------------------------------------------

def setup_logging() -> None:
    """
    Configure application-level logging.  Call exactly once at startup.

    - Reads LOG_LEVEL from environment (default INFO).
    - Attaches a StreamHandler (console) to the root logger.
    - Injects request_id / rfp_id into every log line via _ContextFilter.
    - Silences noisy third-party loggers (anthropic, httpx, sqlalchemy, etc.).
    - Safe to call more than once (idempotent: skips handler if already added).
    """
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(log_level)

    already_configured = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root.handlers
    )

    if not already_configured:
        handler = logging.StreamHandler()
        handler.setLevel(log_level)
        formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
        handler.setFormatter(formatter)
        handler.addFilter(_ContextFilter())
        root.addHandler(handler)
    else:
        # Ensure the context filter is present on existing handlers
        ctx_filter = _ContextFilter()
        for h in root.handlers:
            if not any(isinstance(f, _ContextFilter) for f in h.filters):
                h.addFilter(ctx_filter)

    # ── Suppress noisy third-party loggers ─────────────────────────────────
    _silence = [
        "anthropic", "httpx", "httpcore",
        "urllib3", "multipart", "python_multipart",
        "sqlalchemy.engine", "sqlalchemy.pool",
    ]
    for name in _silence:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Uvicorn access log produces its own per-request lines; our middleware
    # replaces that coverage at INFO level, so silence the built-in access log.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
