"""
Minimal test for extractor chunking + merge logic.
Does NOT call the LLM — only exercises pure-Python functions.
"""
import sys
sys.path.insert(0, ".")
import services.extractor as ext

# ── Case 1: short doc stays in single-pass path ─────────────────────────────
short = "RFP cloud services budget 500k deadline April. " * 30  # ~1,400 chars
assert len(short) < ext._SINGLE_PASS_LIMIT
print(f"Case 1 PASS: {len(short):,} chars < limit {ext._SINGLE_PASS_LIMIT:,} → single-pass")

# ── Case 2: chunking with tiny chunk size ────────────────────────────────────
ext._CHUNK_SIZE = 150
ext._CHUNK_OVERLAP = 20   # must stay < CHUNK_SIZE

text = (
    "CLIENT: DeptTech. DEADLINE: April 30.\n"
    + "pad " * 30
    + "REQ-MID: real-time pipeline.\n"
    + "pad " * 30
    + "EVAL-END: technical merit 40%.\n"
)

chunks = ext._split_into_chunks(text)
req_found  = any("REQ-MID"  in c for c in chunks)
eval_found = any("EVAL-END" in c for c in chunks)
assert req_found,  "REQ-MID not found in any chunk"
assert eval_found, "EVAL-END not found in any chunk"
print(f"Case 2 PASS: {len(chunks)} chunks cover REQ-MID={req_found} EVAL-END={eval_found}")

# ── Case 3: merge captures info from all chunk partials ──────────────────────
partials = [
    {"summary": "Agency seeks cloud vendor.", "client": "DeptTech",
     "deadline": "April 30, 2025", "budget": "$750,000",
     "requirements": [{"text": "Intro req", "category": "mandatory",
                        "reason": "uses 'must'", "type": "technical",
                        "type_reason": "system architecture"}],
     "unclear_requirements": [],
     "evaluation_criteria": [], "deliverables": [], "keywords": ["cloud"],
     "missing_information": [], "extraction_status": "partial",
     "confidence": "high", "notes": None},
    {"summary": "", "client": None, "deadline": None, "budget": None,
     "requirements": ["REQ-MID-1: real-time pipeline", "REQ-MID-2: OAuth 2.0"],
     "unclear_requirements": [{"text": "possible SLA requirement", "reason": "implied but not stated"}],
     "evaluation_criteria": [], "deliverables": [], "keywords": ["pipeline"],
     "missing_information": ["Submission deadline"], "extraction_status": "partial",
     "confidence": "medium", "notes": None},
    {"summary": "", "client": None, "deadline": None, "budget": None,
     "requirements": [],
     "unclear_requirements": [],
     "evaluation_criteria": ["EVAL-END-1: Technical merit 40%"],
     "deliverables": ["DEL-END-1: Final report", "DEL-END-3: 90-day support"],
     "keywords": ["evaluation"],
     "missing_information": [], "extraction_status": "partial",
     "confidence": "medium", "notes": None},
]

m = ext._merge_extractions(partials)
assert m["client"]   == "DeptTech",        f"client wrong: {m['client']}"
assert m["deadline"] == "April 30, 2025",  f"deadline wrong: {m['deadline']}"
assert m["budget"]   == "$750,000",        f"budget wrong: {m['budget']}"
assert any(
    (r["text"] if isinstance(r, dict) else r) == "REQ-MID-1: real-time pipeline"
    for r in m["requirements"]
), "REQ-MID-1 lost in merge"
assert any("EVAL-END-1" in c for c in m["evaluation_criteria"]), "EVAL-END-1 lost in merge"
assert any("DEL-END-3" in d for d in m["deliverables"]),         "DEL-END-3 lost in merge"
assert len(m["unclear_requirements"]) == 1, f"unclear_requirements wrong: {m['unclear_requirements']}"
assert m["missing_information"] == ["Submission deadline"], f"missing_information wrong: {m['missing_information']}"
print(f"Case 3 PASS: merge captured {len(m['requirements'])} req, "
      f"{len(m['unclear_requirements'])} unclear, "
      f"{len(m['evaluation_criteria'])} criteria, {len(m['deliverables'])} deliverables")

# ── Case 4: deduplication ────────────────────────────────────────────────────
dupe = [
    {"summary": "s", "client": None, "deadline": None, "budget": None,
     "requirements": ["REST API", "99.9% uptime"], "unclear_requirements": [],
     "evaluation_criteria": [], "deliverables": [], "keywords": [],
     "missing_information": [], "extraction_status": "partial",
     "confidence": "medium", "notes": None},
    {"summary": "s", "client": None, "deadline": None, "budget": None,
     "requirements": ["REST API", "OAuth 2.0"],   # REST API is a duplicate
     "unclear_requirements": [{"text": "REST API", "reason": "dup test"}],  # also dup in unclear
     "evaluation_criteria": [], "deliverables": [], "keywords": [],
     "missing_information": [], "extraction_status": "partial",
     "confidence": "medium", "notes": None},
]
md = ext._merge_extractions(dupe)
assert len(md["requirements"]) == 3, f"Expected 3 unique items, got {len(md['requirements'])}"
# "REST API" in unclear_requirements should also be deduplicated
assert len(md["unclear_requirements"]) == 1, f"Expected 1 unique unclear item, got {len(md['unclear_requirements'])}"
print(f"Case 4 PASS: 'REST API' deduplicated in both arrays. "
      f"requirements={md['requirements']}, unclear={md['unclear_requirements']}")

# ── Case 5: _enrich_result — complete result stays complete ──────────────────
complete = ext._enrich_result({
    "summary": "Full RFP for cloud platform.",
    "client": "GovAgency", "deadline": "May 1", "budget": "$1M",
    "requirements": [{"text": "Must use AWS", "category": "mandatory",
                       "reason": "uses 'must'", "type": "technical",
                       "type_reason": "cloud infra"}],
    "unclear_requirements": [],
    "evaluation_criteria": ["Technical merit"], "deliverables": ["System"],
    "keywords": ["cloud"], "missing_information": [],
    "extraction_status": "complete", "confidence": "high", "notes": None,
})
assert complete["extraction_status"] == "complete", f"status should stay complete: {complete['extraction_status']}"
assert complete["confidence"] == "high"
print(f"Case 5 PASS: complete result not downgraded")

# ── Case 6: _enrich_result — empty requirements but has unclear → ambiguous ──
ambiguous = ext._enrich_result({
    "summary": "This document discusses procurement.",
    "client": None, "deadline": None, "budget": None,
    "requirements": [],
    "unclear_requirements": [{"text": "Vendor may need ISO cert", "reason": "no explicit obligation"}],
    "evaluation_criteria": [], "deliverables": [],
    "keywords": ["procurement"],
    "missing_information": ["Submission deadline", "Budget"],
    "extraction_status": "complete",   # LLM wrongly claimed "complete"
    "confidence": "high",              # LLM wrongly claimed "high"
    "notes": None,
})
assert ambiguous["extraction_status"] == "ambiguous", \
    f"status should be corrected to ambiguous: {ambiguous['extraction_status']}"
assert ambiguous["confidence"] == "medium", \
    f"confidence should be downgraded to medium: {ambiguous['confidence']}"
print(f"Case 6 PASS: LLM overclaim corrected → status={ambiguous['extraction_status']}, "
      f"confidence={ambiguous['confidence']}")

# ── Case 7: _enrich_result — nothing at all → failed ────────────────────────
empty = ext._enrich_result({
    "summary": "",
    "client": None, "deadline": None, "budget": None,
    "requirements": [],
    "unclear_requirements": [],
    "evaluation_criteria": [], "deliverables": [], "keywords": [],
    "missing_information": [],
    "extraction_status": "partial",   # LLM claimed partial but there's nothing
    "confidence": "medium",
    "notes": None,
})
assert empty["extraction_status"] == "failed", \
    f"status should be forced to failed: {empty['extraction_status']}"
assert empty["confidence"] == "low", \
    f"confidence should be forced to low: {empty['confidence']}"
assert empty["notes"] is not None, "notes should explain the failure"
print(f"Case 7 PASS: empty result correctly marked failed. notes='{empty['notes'][:60]}...'")

# ── Case 8: _enrich_result — has summary but no items → ambiguous ────────────
summary_only = ext._enrich_result({
    "summary": "This appears to be a pre-solicitation notice.",
    "client": None, "deadline": None, "budget": None,
    "requirements": [],
    "unclear_requirements": [],
    "evaluation_criteria": [], "deliverables": [], "keywords": [],
    "missing_information": ["Full RFP not yet published"],
    "extraction_status": "complete",
    "confidence": "high",
    "notes": None,
})
assert summary_only["extraction_status"] == "ambiguous", \
    f"summary-only should be ambiguous: {summary_only['extraction_status']}"
assert summary_only["notes"] is not None, "notes should explain why"
print(f"Case 8 PASS: summary-only corrected to ambiguous. notes='{summary_only['notes'][:60]}...'")

# ── Case 9: _empty_result has all required new fields ───────────────────────
er = ext._empty_result("test summary")
required_fields = [
    "summary", "client", "deadline", "budget",
    "requirements", "unclear_requirements", "evaluation_criteria",
    "deliverables", "keywords", "missing_information",
    "extraction_status", "confidence", "notes",
]
for field in required_fields:
    assert field in er, f"_empty_result missing field: {field}"
print(f"Case 9 PASS: _empty_result contains all {len(required_fields)} required fields")

# ── Case 10: merge escalates status and lowers confidence ───────────────────
mixed = [
    {"summary": "s", "client": None, "deadline": None, "budget": None,
     "requirements": [{"text": "req1", "category": "mandatory",
                        "reason": "must", "type": "technical", "type_reason": "t"}],
     "unclear_requirements": [], "evaluation_criteria": [], "deliverables": [],
     "keywords": [], "missing_information": [],
     "extraction_status": "complete", "confidence": "high", "notes": None},
    {"summary": "", "client": None, "deadline": None, "budget": None,
     "requirements": [], "unclear_requirements": [],
     "evaluation_criteria": [], "deliverables": [], "keywords": [],
     "missing_information": [], "extraction_status": "failed", "confidence": "low",
     "notes": "Chunk 2 was garbled."},
]
mm = ext._merge_extractions(mixed)
assert mm["extraction_status"] == "failed", \
    f"status should escalate to failed: {mm['extraction_status']}"
assert mm["confidence"] == "low", f"confidence should drop to low: {mm['confidence']}"
assert mm["notes"] and "garbled" in mm["notes"], f"notes should include chunk notes: {mm['notes']}"
print(f"Case 10 PASS: merge escalates status to '{mm['extraction_status']}', "
      f"confidence to '{mm['confidence']}'")

print("\nAll cases passed.")
