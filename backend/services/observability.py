"""
Observability utilities for the SimpleSeed pipeline.

Provides four capabilities:
  1. request_id propagation via Python ContextVar (no thread-local, safe for async)
  2. Structured JSON step logging (never raises — logging must not break pipelines)
  3. TrackedAnthropicClient: wraps anthropic.Anthropic to auto-record token usage
  4. Cost estimation using a static per-model pricing map

Design rules:
  - Every public function is safe to call even if the DB session is unavailable.
  - No import-time side effects except logger creation.
  - All DB writes happen inside try/except so a DB failure cannot bubble up.
"""
import contextvars
import json
import logging
import os
import time
import uuid
from typing import Optional

# ── Logger ────────────────────────────────────────────────────────────────────
logger = logging.getLogger("simpleseed")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
logger.setLevel(logging.INFO)


# ── Context vars ──────────────────────────────────────────────────────────────
# These propagate automatically through async tasks spawned from the same context.

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "simpleseed_request_id", default=""
)
_service_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "simpleseed_service", default="unknown"
)


def get_request_id() -> str:
    return _request_id_var.get()


def set_request_id(rid: str) -> None:
    _request_id_var.set(rid)


def set_service(name: str) -> None:
    """Called by each LLM service's get_client() to identify the call origin."""
    _service_var.set(name)


# ── Structured step logging ───────────────────────────────────────────────────

def log_step(
    step: str,
    status: str,
    duration_ms: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> None:
    """
    Emit one structured JSON log line for a pipeline step.

    Format:
        {"request_id": "...", "step": "retrieval", "status": "success",
         "duration_ms": 82, "metadata": {...}}

    Never raises — absorbs all exceptions so logging cannot kill the pipeline.
    """
    try:
        entry: dict = {
            "request_id": get_request_id() or "no-request-id",
            "step": step,
            "status": status,
        }
        if duration_ms is not None:
            entry["duration_ms"] = duration_ms
        if metadata:
            entry["metadata"] = metadata
        logger.info(json.dumps(entry))
    except Exception:
        pass  # absorb — observability must never break business logic


# ── Cost estimation ───────────────────────────────────────────────────────────
# Prices in USD per token.
# Source: https://www.anthropic.com/pricing (2025-04)
# Update this map when Anthropic changes pricing.

MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {
        "input":  0.80  / 1_000_000,   # $0.80 per 1M input tokens
        "output": 4.00  / 1_000_000,   # $4.00 per 1M output tokens
    },
    "claude-sonnet-4-5": {
        "input":  3.00  / 1_000_000,
        "output": 15.00 / 1_000_000,
    },
    "claude-opus-4-5": {
        "input":  15.00 / 1_000_000,
        "output": 75.00 / 1_000_000,
    },
    # Alias patterns for forward compatibility
    "claude-haiku-4-5": {
        "input":  0.80  / 1_000_000,
        "output": 4.00  / 1_000_000,
    },
}

_DEFAULT_PRICING = {"input": 0.80 / 1_000_000, "output": 4.00 / 1_000_000}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return estimated USD cost for the given token counts and model."""
    pricing = MODEL_PRICING.get(model, _DEFAULT_PRICING)
    return round(
        input_tokens * pricing["input"] + output_tokens * pricing["output"],
        8,
    )


# ── DB usage recording ────────────────────────────────────────────────────────

def _record_usage(
    model: str,
    service: str,
    input_tokens: int,
    output_tokens: int,
    request_id: str,
) -> None:
    """
    Write one LLMUsage row using an independent DB session.  Completely safe — never raises.

    Uses its own SessionLocal() so that a write failure cannot roll back or corrupt
    the caller's pipeline session.
    """
    try:
        from database import SessionLocal
        from models.llm_usage import LLMUsage  # local import avoids circular at module load
        db = SessionLocal()
        try:
            row = LLMUsage(
                id=str(uuid.uuid4()),
                request_id=request_id or None,
                user_id=None,       # populated once auth is wired up
                model=model,
                service=service,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                estimated_cost=estimate_cost(model, input_tokens, output_tokens),
            )
            db.add(row)
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            db.close()
    except Exception:
        pass


# ── Tracked Anthropic client ──────────────────────────────────────────────────

class _TrackedMessages:
    """
    Proxy for anthropic.Anthropic().messages.

    Intercepts create() to:
      - record token usage to DB via _record_usage()
      - emit a structured log line via log_step()

    All interception is transparent: the original response is returned unchanged.
    If interception logic fails, the response is still returned (never re-raises).
    """

    def __init__(self, raw_messages):
        self._raw = raw_messages

    def create(self, **kwargs):
        model = kwargs.get("model", "unknown")
        t0 = time.time()
        response = self._raw.create(**kwargs)
        elapsed_ms = int((time.time() - t0) * 1000)

        try:
            usage = getattr(response, "usage", None)
            input_tokens  = int(getattr(usage, "input_tokens",  0) or 0)
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            service = _service_var.get()
            rid     = get_request_id()

            _record_usage(
                model=model,
                service=service,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                request_id=rid,
            )
            log_step(
                step="llm_call",
                status="success",
                duration_ms=elapsed_ms,
                metadata={
                    "service": service,
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "estimated_cost_usd": estimate_cost(model, input_tokens, output_tokens),
                },
            )
        except Exception:
            pass  # never let observability code break the LLM response

        return response

    # Pass through any other attribute accesses (e.g. stream, count_tokens)
    def __getattr__(self, name):
        return getattr(self._raw, name)


class TrackedAnthropicClient:
    """
    Drop-in replacement for anthropic.Anthropic().

    Each service's get_client() returns this instead of a raw client.
    The messages attribute is replaced with _TrackedMessages; everything else
    is delegated to the underlying client unchanged.
    """

    def __init__(self):
        import anthropic
        self._inner = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.messages = _TrackedMessages(self._inner.messages)

    def __getattr__(self, name):
        return getattr(self._inner, name)


_tracked_client: Optional[TrackedAnthropicClient] = None


def get_anthropic_client() -> TrackedAnthropicClient:
    """
    Return the singleton tracked Anthropic client.

    All LLM services should call this instead of constructing their own
    anthropic.Anthropic() instance.
    """
    global _tracked_client
    if _tracked_client is None:
        _tracked_client = TrackedAnthropicClient()
    return _tracked_client
