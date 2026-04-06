"""
Application settings — single source of truth for runtime configuration.

All values are read from environment variables at import time.
Invalid or missing values raise ValueError immediately (fail-fast).
"""
import os

# ---------------------------------------------------------------------------
# LLM model
# ---------------------------------------------------------------------------

_DEFAULT_LLM_MODEL = "claude-haiku-4-5-20251001"

def _resolve_llm_model() -> str:
    value = os.getenv("LLM_MODEL", _DEFAULT_LLM_MODEL).strip()
    if not value:
        raise ValueError(
            "LLM_MODEL is set but empty. "
            f"Provide a valid model name (e.g. {_DEFAULT_LLM_MODEL!r})."
        )
    if not value.startswith("claude-"):
        raise ValueError(
            f"LLM_MODEL={value!r} does not look like a valid Claude model. "
            f"Expected a value starting with 'claude-' "
            f"(e.g. {_DEFAULT_LLM_MODEL!r})."
        )
    return value


llm_model: str = _resolve_llm_model()
