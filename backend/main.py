import json
import uuid
from typing import Optional
from pathlib import Path

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from config import MAX_FILE_BYTES
from database import get_db, init_db
from models.rfp import RFP
from services.extractor import extract_requirements
from services.feedback import get_all_feedback, get_feedback_for_rfp, get_feedback_summary, record_feedback
from services.knowledge import get_document, list_documents, search_knowledge, upload_document
from services.fetcher import fetch_url_text
from services.generator import generate_proposal
from services.industry import SUPPORTED_INDUSTRIES, resolve_industry
from services.parser import parse_pdf
from services.profile import evaluate_strategic_fit, load_profile, save_profile
from services.risks import identify_risks
from services.sam_gov import get_opportunity_text, search_opportunities
from services.scoring import score_bid
from services.scoring_config import load_scoring_config, save_scoring_config, validate_scoring_config

app = FastAPI(title="SimpleSeed API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).parent / "files"
UPLOAD_DIR.mkdir(exist_ok=True)


class AnalyzeURLRequest(BaseModel):
    url: HttpUrl
    industry: Optional[str] = None


class SAMAnalyzeRequest(BaseModel):
    industry: Optional[str] = None


class FeedbackRequest(BaseModel):
    outcome: str                       # "won" | "lost" | "no_bid"
    result_date: Optional[str] = None  # ISO date "YYYY-MM-DD"; defaults to today
    notes: Optional[str] = None


class ScoringConfigWeights(BaseModel):
    relevance_score:    float
    budget_fit:         float
    requirements_match: float
    completeness:       float


class ScoringConfigRequest(BaseModel):
    weights:              ScoringConfigWeights
    bid_threshold:        float
    strategic_fit_weight: float


class CompanyProfileRequest(BaseModel):
    company_name: Optional[str] = None
    industries: list[str] = []
    capabilities: list[str] = []
    services: list[str] = []
    target_contract_size: dict = {}
    geographies: list[str] = []
    certifications: list[str] = []
    past_performance_keywords: list[str] = []
    preferred_project_types: list[str] = []
    excluded_project_types: list[str] = []
    capacity_constraints: list[str] = []


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/industries")
async def list_industries():
    """Return all supported industry identifiers."""
    from services.industry import INDUSTRY_CONTEXT, DEFAULT_INDUSTRY
    return {
        "default": DEFAULT_INDUSTRY,
        "industries": [
            {"id": k, "label": v["label"]}
            for k, v in INDUSTRY_CONTEXT.items()
        ],
    }


@app.get("/api/profile")
async def get_profile():
    """Return the current company profile. Returns null values when not configured."""
    from services.profile import PROFILE_PATH
    import json as _json
    if not PROFILE_PATH.exists():
        return {"configured": False, "profile": None}
    try:
        raw = _json.loads(PROFILE_PATH.read_text())
        raw.pop("_note", None)
        return {"configured": bool(raw.get("company_name")), "profile": raw}
    except Exception:
        return {"configured": False, "profile": None}


@app.put("/api/profile")
async def update_profile(body: CompanyProfileRequest):
    """Save the company profile. Set company_name to enable strategic fit evaluation."""
    saved = save_profile(body.model_dump())
    return {"configured": bool(saved.get("company_name")), "profile": saved}


@app.post("/api/rfps/{rfp_id}/feedback")
async def add_feedback(
    rfp_id: str, body: FeedbackRequest, db: Session = Depends(get_db)
):
    """Record a win/loss/no_bid outcome for a completed analysis."""
    try:
        fb = record_feedback(
            db=db,
            rfp_id=rfp_id,
            outcome=body.outcome,
            result_date=body.result_date,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    from services.feedback import _serialize
    return _serialize(fb)


@app.get("/api/rfps/{rfp_id}/feedback")
async def list_rfp_feedback(rfp_id: str, db: Session = Depends(get_db)):
    """Return all feedback records for a specific analysis."""
    return get_feedback_for_rfp(db, rfp_id)


@app.get("/api/feedback/summary")
async def feedback_summary(db: Session = Depends(get_db)):
    """
    Return aggregate win/loss metrics and a threshold calibration insight.
    This is the first concrete use of historical feedback data in the MVP.
    Win rates are computed from observed outcomes only — no prediction or ML.
    """
    return get_feedback_summary(db)


@app.get("/api/feedback")
async def list_feedback(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Return recent feedback records across all analyses."""
    return get_all_feedback(db, limit=limit)


# ---------------------------------------------------------------------------
# Knowledge base endpoints
# ---------------------------------------------------------------------------

@app.post("/api/knowledge")
async def upload_knowledge_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload a PDF or plain-text file to the internal knowledge base.
    The extracted text is indexed for keyword search via GET /api/knowledge/search.
    """
    file_bytes = await file.read()
    try:
        doc = upload_document(
            db=db,
            filename=file.filename or "upload",
            content_type=file.content_type or "",
            file_bytes=file_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    from services.knowledge import _serialize
    result = _serialize(doc)
    return {
        "success": doc.processing_status == "completed",
        **result,
    }


@app.get("/api/knowledge")
async def list_knowledge_documents(db: Session = Depends(get_db)):
    """List all documents in the knowledge base with their metadata."""
    return list_documents(db)


@app.get("/api/knowledge/{doc_id}")
async def get_knowledge_document(doc_id: str, db: Session = Depends(get_db)):
    """Get metadata for a specific knowledge document."""
    doc = get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@app.get("/api/scoring-config")
async def get_scoring_config():
    """Return the active scoring configuration (weights, threshold, strategic_fit_weight)."""
    return load_scoring_config()


@app.put("/api/scoring-config")
async def update_scoring_config(body: ScoringConfigRequest):
    """
    Save a new scoring configuration.
    Returns 422 if weights don't sum to 1.0, values are out of range, or fields are missing.
    """
    data = body.model_dump()
    try:
        saved = save_scoring_config(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return saved


@app.post("/api/analyze")
async def analyze_rfp(
    file: UploadFile = File(...),
    industry: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}.pdf"

    try:
        received = 0
        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_FILE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum allowed size is {MAX_FILE_BYTES // (1024 * 1024)} MB.",
                    )
                f.write(chunk)

        text = parse_pdf(str(file_path))
        if not text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF.")
        return await _run_analysis(text=text, filename=file.filename, industry=industry, db=db)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if file_path.exists():
            file_path.unlink()


@app.get("/api/rfps")
async def list_rfps(db: Session = Depends(get_db)):
    rfps = db.query(RFP).order_by(RFP.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "score": r.score,
            "decision": r.decision,
            "industry": r.industry or "general",
            "created_at": r.created_at.isoformat(),
            "summary": _safe_json_load(r.requirements, {}).get("summary", ""),
        }
        for r in rfps
    ]


@app.get("/api/rfps/{rfp_id}")
async def get_rfp(rfp_id: str, db: Session = Depends(get_db)):
    rfp = db.query(RFP).filter(RFP.id == rfp_id).first()
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    knowledge_refs = _safe_json_load(rfp.knowledge_refs, [])
    grounding = _safe_json_load(rfp.grounding_report, {})
    evidence_used = grounding.get("evidence_used", [])
    return {
        "id": rfp.id,
        "filename": rfp.filename,
        "industry": rfp.industry or "general",
        "requirements": _safe_json_load(rfp.requirements, {}),
        "risks": _safe_json_load(rfp.risks, []),
        "strategic_fit": _safe_json_load(rfp.strategic_fit, {"status": "unknown"}),
        "proposal": rfp.proposal,
        "score": {
            "score": rfp.score,
            "decision": rfp.decision,
            "breakdown": _safe_json_load(rfp.score_breakdown, {}),
            "reasoning": rfp.reasoning,
        },
        "knowledge_results": knowledge_refs,
        "knowledge_used": [
            {"document_id": r["document_id"], "filename": r["filename"]}
            for r in knowledge_refs
        ],
        "knowledge_status": "used" if knowledge_refs else "no_relevant_documents_found",
        "evidence_used": evidence_used,
        "information_gaps": grounding.get("information_gaps", []),
        "unsupported_claims_avoided": grounding.get("unsupported_claims_avoided", []),
        "grounding_status": (
            "grounded_with_kb" if any(e.get("source") == "internal_document" for e in evidence_used)
            else "rfp_only" if evidence_used
            else "ungrounded"
        ),
        "created_at": rfp.created_at.isoformat(),
    }


@app.delete("/api/rfps/{rfp_id}")
async def delete_rfp(rfp_id: str, db: Session = Depends(get_db)):
    rfp = db.query(RFP).filter(RFP.id == rfp_id).first()
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    file_path = UPLOAD_DIR / f"{rfp_id}.pdf"
    if file_path.exists():
        file_path.unlink()

    db.delete(rfp)
    db.commit()
    return {"message": "Deleted"}


@app.post("/api/analyze-url")
async def analyze_url(body: AnalyzeURLRequest, db: Session = Depends(get_db)):
    url_str = str(body.url)
    try:
        text, source_name = await fetch_url_text(url_str)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch URL: {e}")

    return await _run_analysis(text=text, filename=source_name, industry=body.industry, db=db)


# ---------------------------------------------------------------------------
# SAM.gov endpoints
# ---------------------------------------------------------------------------

@app.get("/api/sam/search")
async def sam_search(
    q: str = Query(..., description="Keywords to search"),
    naics: str = Query("", description="NAICS code filter"),
    limit: int = Query(10, ge=1, le=25),
    offset: int = Query(0, ge=0),
):
    try:
        result = await search_opportunities(keywords=q, naics_code=naics, limit=limit, offset=offset)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@app.post("/api/sam/analyze/{notice_id}")
async def sam_analyze(
    notice_id: str,
    body: SAMAnalyzeRequest = Body(default=SAMAnalyzeRequest()),
    db: Session = Depends(get_db),
):
    try:
        text, title = await get_opportunity_text(notice_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return await _run_analysis(
        text=text, filename=f"SAM.gov — {title}", industry=body.industry, db=db
    )


# ---------------------------------------------------------------------------
# Shared analysis pipeline
# ---------------------------------------------------------------------------

async def _run_analysis(
    text: str, filename: str, db: Session, industry: Optional[str] = None
) -> dict:
    """Run the full extract → generate → score pipeline and persist."""
    if not text.strip():
        raise HTTPException(status_code=400, detail="No text content could be extracted.")

    resolved_industry = resolve_industry(industry)

    try:
        requirements = extract_requirements(text)
        risks = identify_risks(requirements, industry=resolved_industry)

        # ── Knowledge retrieval ──────────────────────────────────────────────
        # Build query from extracted keywords + summary (best available signal
        # from the RFP without an extra LLM call).
        kb_query_parts = list(requirements.get("keywords") or [])
        if requirements.get("summary"):
            kb_query_parts.append(requirements["summary"])
        kb_query = " ".join(kb_query_parts).strip()
        knowledge_results = search_knowledge(kb_query) if kb_query else []

        proposal_result = generate_proposal(
            requirements,
            industry=resolved_industry,
            knowledge_context=knowledge_results,
        )
        proposal_text             = proposal_result["proposal"]
        information_gaps          = proposal_result.get("information_gaps", [])
        unsupported_claims_avoided = proposal_result.get("unsupported_claims_avoided", [])
        evidence_used             = proposal_result.get("evidence_used", [])

        raw_score = score_bid(requirements, industry=resolved_industry)

        # Strategic fit: compare RFP against company profile.
        # When a configured profile is present, the final score is blended:
        #   final = raw_score * (1 - sf_weight) + strategic_fit_score * sf_weight
        # When no profile is configured, the score is unchanged (backward compatible).
        # All three values (sf_weight, bid_threshold) come from scoring_config.json.
        scoring_cfg = load_scoring_config()
        sf_weight = float(scoring_cfg["strategic_fit_weight"])
        bid_threshold = float(scoring_cfg["bid_threshold"])

        profile = load_profile()
        strategic_fit = evaluate_strategic_fit(requirements, profile)

        if strategic_fit.get("status") == "evaluated":
            fit_score = strategic_fit["score"]
            adjusted = round(raw_score["score"] * (1 - sf_weight) + fit_score * sf_weight)
            score_result = {
                **raw_score,
                "score": adjusted,
                "decision": "BID" if adjusted >= bid_threshold else "NO BID",
                "strategic_fit_weight": sf_weight,
            }
        else:
            score_result = raw_score

        # ── Knowledge traceability ───────────────────────────────────────────
        knowledge_used = [
            {"document_id": r["document_id"], "filename": r["filename"]}
            for r in knowledge_results
        ]
        knowledge_status = "used" if knowledge_results else "no_relevant_documents_found"

        grounding_report = {
            "information_gaps": information_gaps,
            "unsupported_claims_avoided": unsupported_claims_avoided,
            "evidence_used": evidence_used,
        }
        grounding_status = (
            "grounded_with_kb" if any(e.get("source") == "internal_document" for e in evidence_used)
            else "rfp_only" if evidence_used
            else "ungrounded"
        )

        rfp_id = str(uuid.uuid4())
        rfp = RFP(
            id=rfp_id,
            filename=filename,
            original_text=text[:12000],
            requirements=json.dumps(requirements),
            risks=json.dumps(risks),
            strategic_fit=json.dumps(strategic_fit),
            proposal=proposal_text,
            score=score_result["score"],
            decision=score_result["decision"],
            score_breakdown=json.dumps(score_result["breakdown"]),
            reasoning=score_result["reasoning"],
            industry=resolved_industry,
            knowledge_refs=json.dumps(knowledge_results),
            grounding_report=json.dumps(grounding_report),
        )
        db.add(rfp)
        db.commit()
        db.refresh(rfp)

        return {
            "id": rfp.id,
            "filename": rfp.filename,
            "industry": resolved_industry,
            "requirements": requirements,
            "risks": risks,
            "strategic_fit": strategic_fit,
            "proposal": proposal_text,
            "score": score_result,
            "knowledge_results": knowledge_results,
            "knowledge_used": knowledge_used,
            "knowledge_status": knowledge_status,
            "evidence_used": evidence_used,
            "information_gaps": information_gaps,
            "unsupported_claims_avoided": unsupported_claims_avoided,
            "grounding_status": grounding_status,
            "created_at": rfp.created_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _safe_json_load(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default
