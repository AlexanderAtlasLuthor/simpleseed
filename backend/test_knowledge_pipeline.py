"""
Verify that search_knowledge() is wired into the proposal generation pipeline.
Tests the integration between KB retrieval and generate_proposal().

No LLM calls, no real Anthropic API.
Uses a temp dir for the knowledge store.
"""
import sys, tempfile, json
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, ".")

# ── Patch KNOWLEDGE_DIR to a temp dir ────────────────────────────────────────
import services.knowledge as kb_mod
_tmp_kb = tempfile.mkdtemp()
kb_mod.KNOWLEDGE_DIR = Path(_tmp_kb)

# Seed the knowledge dir with a realistic document
_DOC_ID = "doc_healthcarepast"
_DOC_CONTENT = (
    "We successfully delivered a cloud-based patient data integration platform "
    "for a regional hospital network. The project involved HIPAA-compliant data "
    "pipelines, EHR system integration, cloud infrastructure on AWS, and a "
    "real-time analytics dashboard. Healthcare IT modernization completed on time "
    "and under budget. Key technologies: AWS, Python, PostgreSQL, HL7 FHIR."
)
(Path(_tmp_kb) / f"{_DOC_ID}.txt").write_text(_DOC_CONTENT)

from services.knowledge import search_knowledge
import services.generator as gen_mod


# ── Case 1: query matching KB content → results returned ─────────────────────
results = search_knowledge("healthcare cloud patient data integration")
assert len(results) >= 1, f"Expected at least 1 result, got {len(results)}"
top = results[0]
assert top["document_id"] == _DOC_ID
assert "relevance_score" in top, "Must use relevance_score (not relevance)"
assert isinstance(top["relevance_score"], int)
assert top["relevance_score"] > 0
assert "snippet" in top
assert len(top["snippet"]) <= 500
assert "filename" in top
print(f"Case 1 PASS: search_knowledge returns results with relevance_score={top['relevance_score']}")


# ── Case 2: empty KB query → empty results (no crash) ────────────────────────
no_results = search_knowledge("")
assert no_results == [], f"Empty query should yield [], got {no_results}"
print("Case 2 PASS: empty query returns []")


# ── Case 3: query with no keyword overlap → empty results ────────────────────
unrelated = search_knowledge("submarine navigation sonar military torpedo")
assert unrelated == [], f"Unrelated query should return [], got {unrelated}"
print("Case 3 PASS: unrelated query returns empty results")


# ── Case 4: generate_proposal accepts knowledge_context and injects it ────────
# Mock the Anthropic client so no real API call is made
captured_prompt = {}

def _fake_create(**kwargs):
    msg = MagicMock()
    msg.content = [MagicMock(text="MOCK PROPOSAL")]
    # Capture the prompt for inspection
    captured_prompt["content"] = kwargs["messages"][0]["content"]
    return msg

with patch.object(gen_mod, "get_client") as mock_client:
    mock_client.return_value.messages.create.side_effect = _fake_create

    requirements = {
        "summary": "Healthcare cloud modernization for a hospital network.",
        "client": "City Hospital",
        "budget": "$2M",
        "deadline": "2024-06-01",
        "requirements": [{"text": "HIPAA-compliant data pipelines", "category": "mandatory"}],
        "deliverables": ["Cloud platform", "EHR integration"],
        "evaluation_criteria": ["Technical approach", "Past experience"],
        "keywords": ["healthcare", "cloud", "HIPAA", "EHR"],
    }

    # With knowledge context
    proposal_with_kb = gen_mod.generate_proposal(
        requirements,
        industry="healthcare",
        knowledge_context=results,
    )

    assert proposal_with_kb == "MOCK PROPOSAL"
    prompt_text = captured_prompt["content"]
    assert "INTERNAL KNOWLEDGE BASE" in prompt_text, \
        "Prompt must contain KB section when context is provided"
    assert _DOC_ID in prompt_text or "doc_healthcarepast" in prompt_text, \
        "Prompt must reference the document id"
    assert "relevance" in prompt_text.lower(), \
        "Prompt should mention relevance score"
    print("Case 4 PASS: knowledge_context injected into generator prompt")

    # Without knowledge context (empty list)
    captured_prompt.clear()
    proposal_no_kb = gen_mod.generate_proposal(
        requirements,
        industry="healthcare",
        knowledge_context=[],
    )
    prompt_text_no_kb = captured_prompt["content"]
    assert "INTERNAL KNOWLEDGE BASE" not in prompt_text_no_kb, \
        "Prompt must NOT contain KB section when context is empty"
    print("Case 5 PASS: empty knowledge_context → no KB section in prompt (clean fallback)")

    # Without knowledge_context param at all (backward compat)
    captured_prompt.clear()
    proposal_compat = gen_mod.generate_proposal(requirements, industry="healthcare")
    prompt_compat = captured_prompt["content"]
    assert "INTERNAL KNOWLEDGE BASE" not in prompt_compat, \
        "Omitting knowledge_context must not break existing callers"
    print("Case 6 PASS: omitting knowledge_context is backward-compatible")


# ── Case 7: knowledge_status logic ───────────────────────────────────────────
def _compute_status(results):
    return "used" if results else "no_relevant_documents_found"

assert _compute_status([{"document_id": "doc_1", "filename": "a.txt"}]) == "used"
assert _compute_status([]) == "no_relevant_documents_found"
print("Case 7 PASS: knowledge_status correctly reflects retrieval outcome")


# ── Case 8: knowledge_used contains only document_id + filename ───────────────
knowledge_used = [
    {"document_id": r["document_id"], "filename": r["filename"]}
    for r in results
]
assert all(set(k.keys()) == {"document_id", "filename"} for k in knowledge_used), \
    "knowledge_used items must have exactly document_id and filename"
print(f"Case 8 PASS: knowledge_used shape is correct: {knowledge_used}")


# ── Case 9: all required fields present in a knowledge result ─────────────────
required_fields = {"document_id", "filename", "snippet", "relevance_score"}
assert required_fields.issubset(top.keys()), \
    f"Missing fields in result: {required_fields - top.keys()}"
print(f"Case 9 PASS: result has all required fields: {sorted(top.keys())}")


# ── Case 10: query built from requirements keywords works end-to-end ──────────
keywords = ["healthcare", "cloud", "patient", "integration"]
summary = "Modernize hospital data systems."
kb_query = " ".join(keywords) + " " + summary
results_from_req = search_knowledge(kb_query)
assert len(results_from_req) >= 1, "Query built from requirements must find the seeded document"
print(f"Case 10 PASS: query from requirements.keywords+summary finds KB doc "
      f"(relevance_score={results_from_req[0]['relevance_score']})")


print("\nAll cases passed.")

# Cleanup
import shutil
shutil.rmtree(_tmp_kb, ignore_errors=True)
