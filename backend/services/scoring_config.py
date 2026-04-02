"""
Single source of truth for bid scoring configuration.

File: backend/scoring_config.json

Three configurable values:
  weights             — per-dimension weights for the bid score (must sum to 1.0)
  bid_threshold       — score at or above which a BID decision is issued (0–100)
  strategic_fit_weight — how much the strategic fit score blends into the final score (0.0–1.0)

Loading strategy:
  load_scoring_config() → reads file, validates, returns config dict.
  On any read/parse/validation error, falls back to DEFAULTS and logs a warning.
  This means the pipeline is never blocked by a bad config file at runtime.

Saving strategy:
  save_scoring_config(data) → validates first, then writes.
  Raises ValueError with an explicit message if validation fails.
  The API endpoint converts this ValueError into a 422 response.
"""
import json
import warnings
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).parent.parent / "scoring_config.json"

# These are the authoritative defaults — the file ships pre-filled with these values.
DEFAULTS: dict[str, Any] = {
    "weights": {
        "relevance_score":    0.30,
        "budget_fit":         0.25,
        "requirements_match": 0.25,
        "completeness":       0.20,
    },
    "bid_threshold":       60,
    "strategic_fit_weight": 0.20,
}

_REQUIRED_WEIGHT_KEYS = frozenset(DEFAULTS["weights"].keys())
_WEIGHT_SUM_TOLERANCE = 0.001


# ── Validation ────────────────────────────────────────────────────────────────

def validate_scoring_config(config: dict) -> None:
    """
    Raise ValueError with a clear message if the config is invalid.
    Called by both save_scoring_config (strict) and load_scoring_config (safe fallback).
    """
    if not isinstance(config, dict):
        raise ValueError("Scoring config must be a JSON object.")

    # ── weights ──────────────────────────────────────────────────────────────
    weights = config.get("weights")
    if not isinstance(weights, dict):
        raise ValueError("'weights' must be a JSON object.")

    extra = set(weights.keys()) - _REQUIRED_WEIGHT_KEYS
    if extra:
        raise ValueError(
            f"Unknown weight key(s): {sorted(extra)}. "
            f"Allowed: {sorted(_REQUIRED_WEIGHT_KEYS)}"
        )
    missing = _REQUIRED_WEIGHT_KEYS - set(weights.keys())
    if missing:
        raise ValueError(f"Missing required weight key(s): {sorted(missing)}")

    for key, value in weights.items():
        if not isinstance(value, (int, float)):
            raise ValueError(f"Weight '{key}' must be a number, got: {type(value).__name__}")
        if not (0.0 <= float(value) <= 1.0):
            raise ValueError(
                f"Weight '{key}' must be in [0.0, 1.0], got: {value}"
            )

    total = sum(float(v) for v in weights.values())
    if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
        raise ValueError(
            f"Weights must sum to 1.0 (±{_WEIGHT_SUM_TOLERANCE}), "
            f"got {total:.6f}. "
            f"Current values: {dict(weights)}"
        )

    # ── bid_threshold ─────────────────────────────────────────────────────────
    threshold = config.get("bid_threshold")
    if threshold is None:
        raise ValueError("'bid_threshold' is required.")
    if not isinstance(threshold, (int, float)):
        raise ValueError(f"'bid_threshold' must be a number, got: {type(threshold).__name__}")
    if not (0 <= float(threshold) <= 100):
        raise ValueError(f"'bid_threshold' must be in [0, 100], got: {threshold}")

    # ── strategic_fit_weight ──────────────────────────────────────────────────
    sf_weight = config.get("strategic_fit_weight")
    if sf_weight is None:
        raise ValueError("'strategic_fit_weight' is required.")
    if not isinstance(sf_weight, (int, float)):
        raise ValueError(
            f"'strategic_fit_weight' must be a number, got: {type(sf_weight).__name__}"
        )
    if not (0.0 <= float(sf_weight) <= 1.0):
        raise ValueError(
            f"'strategic_fit_weight' must be in [0.0, 1.0], got: {sf_weight}"
        )


# ── I/O ───────────────────────────────────────────────────────────────────────

def load_scoring_config() -> dict:
    """
    Load and validate the scoring config from disk.

    Falls back to DEFAULTS (never raises) so the pipeline is never blocked.
    A warning is emitted when falling back so operators can detect the issue.
    """
    try:
        raw = json.loads(CONFIG_PATH.read_text())
        validate_scoring_config(raw)
        return raw
    except FileNotFoundError:
        warnings.warn(
            f"scoring_config.json not found at {CONFIG_PATH}; using defaults.",
            stacklevel=2,
        )
        return _copy_defaults()
    except (json.JSONDecodeError, ValueError) as exc:
        warnings.warn(
            f"scoring_config.json is invalid ({exc}); using defaults.",
            stacklevel=2,
        )
        return _copy_defaults()


def save_scoring_config(data: dict) -> dict:
    """
    Validate then persist the scoring config.
    Raises ValueError with a specific message if validation fails — never silently saves bad config.
    """
    validate_scoring_config(data)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))
    return data


def _copy_defaults() -> dict:
    """Return a deep copy of DEFAULTS so callers can't mutate the module-level dict."""
    return {
        "weights": dict(DEFAULTS["weights"]),
        "bid_threshold": DEFAULTS["bid_threshold"],
        "strategic_fit_weight": DEFAULTS["strategic_fit_weight"],
    }
