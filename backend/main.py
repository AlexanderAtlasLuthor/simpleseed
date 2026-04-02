import json
import shutil
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import get_db, init_db
from models.rfp import RFP
from services.extractor import extract_requirements
from services.generator import generate_proposal
from services.parser import parse_pdf
from services.scoring import score_bid

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


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/analyze")
async def analyze_rfp(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}.pdf"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        text = parse_pdf(str(file_path))
        if not text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF. Ensure the PDF contains selectable text.")

        requirements = extract_requirements(text)
        proposal = generate_proposal(requirements)
        score_result = score_bid(requirements)

        rfp = RFP(
            id=file_id,
            filename=file.filename,
            original_text=text[:12000],
            requirements=json.dumps(requirements),
            proposal=proposal,
            score=score_result["score"],
            decision=score_result["decision"],
            score_breakdown=json.dumps(score_result["breakdown"]),
            reasoning=score_result["reasoning"],
        )
        db.add(rfp)
        db.commit()
        db.refresh(rfp)

        return {
            "id": rfp.id,
            "filename": rfp.filename,
            "requirements": requirements,
            "proposal": proposal,
            "score": score_result,
            "created_at": rfp.created_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rfps")
async def list_rfps(db: Session = Depends(get_db)):
    rfps = db.query(RFP).order_by(RFP.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "score": r.score,
            "decision": r.decision,
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

    return {
        "id": rfp.id,
        "filename": rfp.filename,
        "requirements": _safe_json_load(rfp.requirements, {}),
        "proposal": rfp.proposal,
        "score": {
            "score": rfp.score,
            "decision": rfp.decision,
            "breakdown": _safe_json_load(rfp.score_breakdown, {}),
            "reasoning": rfp.reasoning,
        },
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


def _safe_json_load(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default
