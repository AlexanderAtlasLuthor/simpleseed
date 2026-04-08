"""
Feedback service: record and query win/loss outcomes for RFP analyses.

Data model
----------
Each Feedback row is linked to an rfp_id (nullable for resilience), carries
an outcome (won/lost/no_bid), a result_date, optional notes, and a snapshot
of the signals that existed at the time of recording.

First concrete use of feedback data
-------------------------------------
get_feedback_summary() returns:
  - win/loss/no_bid counts
  - win rate overall and broken down by score band
  - win rate by industry (when >= 2 records in that industry)
  - a calibration insight: whether the current bid_threshold appears well-placed
    based on the distribution of wins vs losses across score bands

What this IS and is NOT
-----------------------
This is descriptive statistics + a heuristic calibration signal.
There is NO automatic model updating, NO weight retraining, NO ML.
The calibration insight is purely informational — it surfaces a human-readable
observation to help operators decide whether to adjust the threshold manually.
"""
import json
import uuid
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from models.feedback import Feedback
from models.rfp import RFP

VALID_OUTCOMES = {"won", "lost", "no_bid"}

# Minimum records needed before emitting calibration insights
_MIN_CALIBRATION_RECORDS = 3


# ── Write ─────────────────────────────────────────────────────────────────────

def record_feedback(
    db: Session,
    rfp_id: str,
    outcome: str,
    result_date: Optional[str],
    notes: Optional[str],
) -> Feedback:
    """
    Record a win/loss/no_bid outcome for a prior analysis.

    Validates outcome, resolves result_date, snapshots relevant signals
    from the rfp row (if it still exists), then persists and returns the row.

    Raises ValueError for invalid inputs.
    """
    if outcome not in VALID_OUTCOMES:
        raise ValueError(
            f"Invalid outcome '{outcome}'. Must be one of: {sorted(VALID_OUTCOMES)}"
        )

    # Resolve and validate result_date
    if result_date:
        try:
            date.fromisoformat(result_date)
        except ValueError:
            raise ValueError(
                f"result_date must be an ISO date string (YYYY-MM-DD), got: '{result_date}'"
            )
    else:
        result_date = date.today().isoformat()

    # Check that the rfp exists (we still allow recording feedback even if it doesn't,
    # but we warn callers via the returned snapshot being empty)
    rfp: Optional[RFP] = db.query(RFP).filter(RFP.id == rfp_id).first()

    # Build snapshot from live rfp data
    original_score    = rfp.score    if rfp else None
    original_decision = rfp.decision if rfp else None
    industry          = rfp.industry if rfp else None

    strategic_fit_overall = None
    risk_count = None
    risk_summary_json = None

    if rfp:
        sf = _safe_json(rfp.strategic_fit, {})
        strategic_fit_overall = sf.get("overall")  # "high" | "medium" | "low" | None

        risks = _safe_json(rfp.risks, [])
        risk_count = len(risks)
        risk_summary_json = json.dumps([
            r.get("title", "") if isinstance(r, dict) else str(r)
            for r in risks
        ])

    fb = Feedback(
        id                    = str(uuid.uuid4()),
        rfp_id                = rfp_id,
        outcome               = outcome,
        result_date           = result_date,
        notes                 = notes,
        original_score        = original_score,
        original_decision     = original_decision,
        industry              = industry,
        strategic_fit_overall = strategic_fit_overall,
        risk_count            = risk_count,
        risk_summary          = risk_summary_json,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


# ── Read ──────────────────────────────────────────────────────────────────────

def get_feedback_for_rfp(db: Session, rfp_id: str) -> list[dict]:
    """Return all feedback records linked to a specific RFP analysis."""
    rows = (
        db.query(Feedback)
        .filter(Feedback.rfp_id == rfp_id)
        .order_by(Feedback.created_at.desc())
        .all()
    )
    return [_serialize(fb) for fb in rows]


def get_all_feedback(db: Session, user_id: str, limit: int = 200) -> list[dict]:
    """Return the most recent feedback records for analyses owned by user_id."""
    rows = (
        db.query(Feedback)
        .join(RFP, Feedback.rfp_id == RFP.id)
        .filter(RFP.user_id == user_id)
        .order_by(Feedback.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_serialize(fb) for fb in rows]


def get_feedback_summary(db: Session, user_id: str) -> dict:
    """
    Compute aggregate metrics from all feedback records.

    Returns:
      - counts by outcome
      - win rate overall and by score band
      - win rate by industry (min 2 records)
      - win rate by strategic_fit level
      - calibration insight: is the current threshold well-placed?

    All values are derived from observed data. No interpolation or prediction.
    """
    rows = (
        db.query(Feedback)
        .join(RFP, Feedback.rfp_id == RFP.id)
        .filter(RFP.user_id == user_id)
        .all()
    )
    total = len(rows)

    if total == 0:
        return {
            "total_feedback_records": 0,
            "wins": 0,
            "losses": 0,
            "no_bids": 0,
            "win_rate_overall": None,
            "win_rate_by_score_band": {},
            "win_rate_by_industry": {},
            "win_rate_by_strategic_fit": {},
            "calibration_insight": {
                "status": "insufficient_data",
                "message": "No feedback records yet. Record win/loss outcomes to enable calibration insights.",
                "records_needed": _MIN_CALIBRATION_RECORDS,
            },
        }

    wins    = sum(1 for r in rows if r.outcome == "won")
    losses  = sum(1 for r in rows if r.outcome == "lost")
    no_bids = sum(1 for r in rows if r.outcome == "no_bid")

    # Only bids (won+lost) are used for win-rate calculations
    bid_rows = [r for r in rows if r.outcome in ("won", "lost")]
    win_rate_overall = _win_rate(bid_rows) if bid_rows else None

    # ── Win rate by score band ────────────────────────────────────────────────
    bands = {
        "0-49":   lambda s: s is not None and s < 50,
        "50-59":  lambda s: s is not None and 50 <= s < 60,
        "60-69":  lambda s: s is not None and 60 <= s < 70,
        "70-79":  lambda s: s is not None and 70 <= s < 80,
        "80-100": lambda s: s is not None and s >= 80,
    }
    win_rate_by_score_band = {}
    for label, pred in bands.items():
        band_rows = [r for r in bid_rows if pred(r.original_score)]
        if len(band_rows) >= 1:
            win_rate_by_score_band[label] = {
                "win_rate": _win_rate(band_rows),
                "count": len(band_rows),
            }

    # ── Win rate by industry ──────────────────────────────────────────────────
    win_rate_by_industry = {}
    industries = {r.industry for r in bid_rows if r.industry}
    for ind in sorted(industries):
        ind_rows = [r for r in bid_rows if r.industry == ind]
        if len(ind_rows) >= 2:  # min 2 for meaningful rate
            win_rate_by_industry[ind] = {
                "win_rate": _win_rate(ind_rows),
                "count": len(ind_rows),
            }

    # ── Win rate by strategic_fit level ──────────────────────────────────────
    win_rate_by_strategic_fit = {}
    fit_levels = {r.strategic_fit_overall for r in bid_rows if r.strategic_fit_overall}
    for level in sorted(fit_levels):
        fit_rows = [r for r in bid_rows if r.strategic_fit_overall == level]
        if len(fit_rows) >= 2:
            win_rate_by_strategic_fit[level] = {
                "win_rate": _win_rate(fit_rows),
                "count": len(fit_rows),
            }

    # ── Calibration insight ───────────────────────────────────────────────────
    calibration = _compute_calibration(bid_rows, win_rate_by_score_band)

    return {
        "total_feedback_records":  total,
        "wins":    wins,
        "losses":  losses,
        "no_bids": no_bids,
        "win_rate_overall": round(win_rate_overall, 3) if win_rate_overall is not None else None,
        "win_rate_by_score_band":      win_rate_by_score_band,
        "win_rate_by_industry":        win_rate_by_industry,
        "win_rate_by_strategic_fit":   win_rate_by_strategic_fit,
        "calibration_insight":         calibration,
    }


# ── Calibration heuristic ─────────────────────────────────────────────────────

def _compute_calibration(bid_rows: list, band_rates: dict) -> dict:
    """
    Emit a human-readable calibration signal based on observed win rates.

    Logic:
    - "insufficient_data": fewer than _MIN_CALIBRATION_RECORDS bid rows
    - "well_calibrated":   win rate clearly rises as score rises; threshold band >= 0.5
    - "threshold_may_be_too_high": win rate in the 50-59 band is high (>= 0.5)
      — many wins are being left below the threshold
    - "threshold_may_be_too_low": win rate in the 60-69 band is low (< 0.35)
      — many losses are just above the threshold
    - "observe_more_data": not enough signal to distinguish

    This is a heuristic insight, not a model recommendation.
    """
    from services.scoring_config import load_scoring_config
    cfg = load_scoring_config()
    threshold = int(cfg["bid_threshold"])

    if len(bid_rows) < _MIN_CALIBRATION_RECORDS:
        return {
            "status": "insufficient_data",
            "message": (
                f"At least {_MIN_CALIBRATION_RECORDS} bid/loss records needed for calibration insights. "
                f"Currently: {len(bid_rows)}."
            ),
            "current_threshold": threshold,
            "records_used": len(bid_rows),
        }

    below_band = band_rates.get("50-59", {})
    above_band = band_rates.get("60-69", {})
    below_wr   = below_band.get("win_rate") if below_band else None
    above_wr   = above_band.get("win_rate") if above_band else None

    if below_wr is not None and below_wr >= 0.50:
        status  = "threshold_may_be_too_high"
        message = (
            f"Win rate for scores 50–59 is {below_wr:.0%}, meaning many winning bids "
            f"are scoring below the current threshold of {threshold}. "
            "Consider lowering the threshold."
        )
    elif above_wr is not None and above_wr < 0.35:
        status  = "threshold_may_be_too_low"
        message = (
            f"Win rate for scores 60–69 is {above_wr:.0%}, meaning many bids just above "
            f"the current threshold of {threshold} are losing. "
            "Consider raising the threshold."
        )
    else:
        status  = "observe_more_data"
        message = (
            f"Not enough signal yet to assess threshold calibration at {threshold}. "
            "Continue recording outcomes."
        )

    return {
        "status":            status,
        "message":           message,
        "current_threshold": threshold,
        "records_used":      len(bid_rows),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _win_rate(rows: list) -> float:
    """Fraction of rows with outcome == 'won'. Excludes no_bid rows."""
    bid_rows = [r for r in rows if r.outcome in ("won", "lost")]
    if not bid_rows:
        return 0.0
    return round(sum(1 for r in bid_rows if r.outcome == "won") / len(bid_rows), 3)


def _safe_json(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _serialize(fb: Feedback) -> dict:
    return {
        "id":                   fb.id,
        "rfp_id":               fb.rfp_id,
        "outcome":              fb.outcome,
        "result_date":          fb.result_date,
        "notes":                fb.notes,
        "original_score":       fb.original_score,
        "original_decision":    fb.original_decision,
        "industry":             fb.industry,
        "strategic_fit_overall": fb.strategic_fit_overall,
        "risk_count":           fb.risk_count,
        "risk_summary":         _safe_json(fb.risk_summary, []),
        "created_at":           fb.created_at.isoformat() if fb.created_at else None,
    }
