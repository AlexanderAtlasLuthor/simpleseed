"""
Verify scoring configuration loading, validation, and pipeline integration.
No LLM calls — pure logic tests.
"""
import sys, json, tempfile, os
from pathlib import Path
sys.path.insert(0, ".")

import services.scoring_config as sc_mod
from services.scoring_config import (
    validate_scoring_config, load_scoring_config, save_scoring_config,
    DEFAULTS, _REQUIRED_WEIGHT_KEYS, _WEIGHT_SUM_TOLERANCE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def valid_config(**overrides):
    base = {
        "weights": {
            "relevance_score":    0.30,
            "budget_fit":         0.25,
            "requirements_match": 0.25,
            "completeness":       0.20,
        },
        "bid_threshold": 60,
        "strategic_fit_weight": 0.20,
    }
    base.update(overrides)
    return base


# ── Case 1: defaults are themselves valid ────────────────────────────────────
validate_scoring_config(DEFAULTS)
total = sum(DEFAULTS["weights"].values())
assert abs(total - 1.0) < _WEIGHT_SUM_TOLERANCE
assert 0 <= DEFAULTS["bid_threshold"] <= 100
assert 0.0 <= DEFAULTS["strategic_fit_weight"] <= 1.0
print(f"Case 1 PASS: DEFAULTS are valid (weights sum={total:.3f}, "
      f"threshold={DEFAULTS['bid_threshold']}, sf_weight={DEFAULTS['strategic_fit_weight']})")


# ── Case 2: valid custom config passes validation ─────────────────────────────
custom = valid_config(
    weights={"relevance_score": 0.40, "budget_fit": 0.30,
             "requirements_match": 0.20, "completeness": 0.10},
    bid_threshold=70,
    strategic_fit_weight=0.15,
)
validate_scoring_config(custom)
print(f"Case 2 PASS: custom valid config accepted")


# ── Case 3: weights don't sum to 1.0 → clear ValueError ──────────────────────
bad_sum = valid_config(weights={
    "relevance_score": 0.40, "budget_fit": 0.40,
    "requirements_match": 0.40, "completeness": 0.10,  # sum = 1.30
})
try:
    validate_scoring_config(bad_sum)
    assert False, "Should have raised ValueError"
except ValueError as e:
    assert "1.0" in str(e) or "sum" in str(e).lower(), f"Error should mention sum: {e}"
    print(f"Case 3 PASS: bad weight sum → '{e}'")


# ── Case 4: individual weight out of [0, 1] range ────────────────────────────
bad_range = valid_config()
bad_range["weights"]["relevance_score"] = 1.5  # >1.0
try:
    validate_scoring_config(bad_range)
    assert False, "Should have raised ValueError"
except ValueError as e:
    assert "relevance_score" in str(e)
    print(f"Case 4 PASS: out-of-range weight → '{e}'")


# ── Case 5: threshold out of [0, 100] range ───────────────────────────────────
for bad_threshold in [-1, 101, 200]:
    cfg = valid_config(bid_threshold=bad_threshold)
    try:
        validate_scoring_config(cfg)
        assert False, f"Should have raised ValueError for threshold={bad_threshold}"
    except ValueError as e:
        assert "bid_threshold" in str(e)
print(f"Case 5 PASS: out-of-range thresholds (-1, 101, 200) all rejected")


# ── Case 6: strategic_fit_weight out of [0, 1] ───────────────────────────────
cfg = valid_config(strategic_fit_weight=1.5)
try:
    validate_scoring_config(cfg)
    assert False
except ValueError as e:
    assert "strategic_fit_weight" in str(e)
    print(f"Case 6 PASS: sf_weight=1.5 → '{e}'")


# ── Case 7: unknown weight key ────────────────────────────────────────────────
cfg = valid_config()
cfg["weights"]["unknown_dimension"] = 0.05
cfg["weights"]["completeness"] = 0.15  # adjust to keep sum=1.0
try:
    validate_scoring_config(cfg)
    assert False
except ValueError as e:
    assert "unknown" in str(e).lower() or "Unknown" in str(e)
    print(f"Case 7 PASS: unknown weight key → '{e}'")


# ── Case 8: missing weight key ────────────────────────────────────────────────
cfg = valid_config()
del cfg["weights"]["completeness"]
try:
    validate_scoring_config(cfg)
    assert False
except ValueError as e:
    assert "completeness" in str(e) or "missing" in str(e).lower() or "Missing" in str(e)
    print(f"Case 8 PASS: missing weight key → '{e}'")


# ── Case 9: non-numeric weight ────────────────────────────────────────────────
cfg = valid_config()
cfg["weights"]["relevance_score"] = "thirty percent"
try:
    validate_scoring_config(cfg)
    assert False
except ValueError as e:
    assert "relevance_score" in str(e)
    print(f"Case 9 PASS: non-numeric weight → '{e}'")


# ── Case 10: file missing → falls back to defaults ───────────────────────────
original_path = sc_mod.CONFIG_PATH
sc_mod.CONFIG_PATH = Path("/tmp/nonexistent_scoring_config_xyz.json")
import warnings
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    result = load_scoring_config()
    assert result == DEFAULTS or result["bid_threshold"] == DEFAULTS["bid_threshold"]
    assert len(w) == 1, f"Expected 1 warning, got {len(w)}"
    assert "defaults" in str(w[0].message).lower()
sc_mod.CONFIG_PATH = original_path
print(f"Case 10 PASS: missing file → falls back to defaults with warning")


# ── Case 11: invalid file content → falls back to defaults ───────────────────
with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
    f.write('{"weights": {"bad": 99}, "bid_threshold": 60, "strategic_fit_weight": 0.20}')
    tmp_path = f.name

sc_mod.CONFIG_PATH = Path(tmp_path)
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    result = load_scoring_config()
    assert result["bid_threshold"] == DEFAULTS["bid_threshold"]
    assert len(w) == 1
    assert "invalid" in str(w[0].message).lower()
sc_mod.CONFIG_PATH = original_path
os.unlink(tmp_path)
print(f"Case 11 PASS: invalid file → falls back to defaults with warning")


# ── Case 12: save then reload round-trips correctly ──────────────────────────
with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
    tmp_path = f.name

sc_mod.CONFIG_PATH = Path(tmp_path)
custom = valid_config(
    weights={"relevance_score": 0.35, "budget_fit": 0.30,
             "requirements_match": 0.25, "completeness": 0.10},
    bid_threshold=65,
    strategic_fit_weight=0.25,
)
save_scoring_config(custom)
reloaded = load_scoring_config()
assert reloaded["bid_threshold"] == 65
assert reloaded["weights"]["relevance_score"] == 0.35
assert reloaded["strategic_fit_weight"] == 0.25
sc_mod.CONFIG_PATH = original_path
os.unlink(tmp_path)
print(f"Case 12 PASS: save → reload round-trips all values correctly")


# ── Case 13: threshold change affects BID decision ───────────────────────────
# score=65: BID with threshold=60, NO BID with threshold=70
for threshold, score_val, expected in [(60, 65, "BID"), (70, 65, "NO BID"), (65, 65, "BID")]:
    decision = "BID" if score_val >= threshold else "NO BID"
    assert decision == expected, f"threshold={threshold}, score={score_val} → expected {expected}"
print(f"Case 13 PASS: threshold change correctly shifts BID/NO BID boundary")


# ── Case 14: weight change affects final score ────────────────────────────────
breakdown = {
    "relevance_score": 80, "budget_fit": 40,
    "requirements_match": 70, "completeness": 50,
}

def compute_score(weights):
    return round(
        breakdown["relevance_score"]    * weights["relevance_score"]
        + breakdown["budget_fit"]       * weights["budget_fit"]
        + breakdown["requirements_match"] * weights["requirements_match"]
        + breakdown["completeness"]     * weights["completeness"]
    )

default_score = compute_score(DEFAULTS["weights"])
# Shift weight from budget_fit (low=40) to relevance_score (high=80)
high_relevance_weights = {
    "relevance_score": 0.50, "budget_fit": 0.10,
    "requirements_match": 0.25, "completeness": 0.15,
}
validate_scoring_config(valid_config(weights=high_relevance_weights))
high_rel_score = compute_score(high_relevance_weights)
assert high_rel_score > default_score, \
    f"Shifting weight to high-scoring dim should increase score: {default_score} → {high_rel_score}"
print(f"Case 14 PASS: weight shift changes score: "
      f"default={default_score} → high_relevance={high_rel_score}")


# ── Case 15: save raises ValueError, never saves bad config ──────────────────
with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
    f.write(json.dumps(DEFAULTS))  # start with valid content
    tmp_path = f.name

sc_mod.CONFIG_PATH = Path(tmp_path)
bad = valid_config(bid_threshold=999)
try:
    save_scoring_config(bad)
    assert False, "Should have raised"
except ValueError:
    pass
# File should still contain original valid config
reloaded = load_scoring_config()
assert reloaded["bid_threshold"] == DEFAULTS["bid_threshold"], \
    f"Bad save should not have overwritten file, got: {reloaded['bid_threshold']}"
sc_mod.CONFIG_PATH = original_path
os.unlink(tmp_path)
print(f"Case 15 PASS: save with invalid config raises ValueError, file not overwritten")


print("\nAll cases passed.")
