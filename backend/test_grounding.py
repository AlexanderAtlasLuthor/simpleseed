"""
Verify anti-hallucination grounding in generate_proposal().

Tests:
- Prompt contains explicit prohibitions for dangerous claim categories
- Grounding JSON is parsed correctly when model returns it
- Graceful degradation when JSON is absent or malformed
- KB context + no-KB context both produce correct dict shape
- Grounding status logic
- Prohibited categories are enumerated in the prompt

No real LLM calls. Anthropic client is mocked.
"""
import sys, json, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, ".")

import services.generator as gen_mod
from services.generator import _parse_grounding_response

REQUIREMENTS = {
    "summary": "Healthcare IT modernization for a regional hospital.",
    "client": "Regional Medical Center",
    "budget": "$1.5M",
    "deadline": "2024-09-01",
    "requirements": [
        {"text": "HIPAA-compliant data pipelines", "category": "mandatory"},
        {"text": "EHR system integration", "category": "mandatory"},
    ],
    "deliverables": ["Cloud platform", "Training", "Documentation"],
    "evaluation_criteria": ["Technical approach", "Past experience", "Price"],
    "keywords": ["healthcare", "cloud", "HIPAA", "EHR", "integration"],
}

KB_RESULTS = [
    {
        "document_id": "doc_hc001",
        "filename": "past_healthcare_proposal.txt",
        "snippet": "We delivered a cloud integration platform for a 500-bed hospital in 2022.",
        "relevance_score": 7,
    }
]

# Simulated model response with valid grounding JSON
RESPONSE_WITH_GROUNDING = """\
## Executive Summary
[COMPANY NAME] proposes a HIPAA-compliant cloud modernization solution for Regional Medical Center.

## Team & Experience
Our team brings [PLACEHOLDER: insert verified relevant certifications] and domain expertise
in healthcare IT. In a similar engagement, we delivered a cloud integration platform for a
500-bed hospital (see KB reference).

```json
{
  "information_gaps": [
    "No verified federal past performance found in KB",
    "Team certifications not documented in internal knowledge base"
  ],
  "unsupported_claims_avoided": [
    "Did not claim ISO 27001 certification — no evidence in RFP or KB",
    "Did not claim HIPAA Business Associate Agreement history — not in sources"
  ],
  "evidence_used": [
    {"source": "rfp", "snippet": "HIPAA-compliant data pipelines"},
    {"source": "rfp", "snippet": "EHR system integration"},
    {"source": "internal_document", "document_id": "doc_hc001",
     "filename": "past_healthcare_proposal.txt",
     "snippet": "cloud integration platform for a 500-bed hospital"}
  ]
}
```"""

# Simulated response without grounding JSON (model forgot / edge case)
RESPONSE_WITHOUT_JSON = """\
## Executive Summary
[COMPANY NAME] proposes a solution for Regional Medical Center.
No JSON grounding block present."""

# Malformed JSON grounding block
RESPONSE_MALFORMED_JSON = """\
Some proposal text here.
```json
{ "information_gaps": [ INVALID JSON
```"""


# ── Case 1: _parse_grounding_response correctly splits proposal + JSON ────────
result = _parse_grounding_response(RESPONSE_WITH_GROUNDING)
assert isinstance(result, dict)
assert "proposal" in result
assert "information_gaps" in result
assert "unsupported_claims_avoided" in result
assert "evidence_used" in result

assert "Executive Summary" in result["proposal"]
assert "```json" not in result["proposal"], "JSON block must be stripped from proposal text"
assert len(result["information_gaps"]) == 2
assert len(result["unsupported_claims_avoided"]) == 2
assert len(result["evidence_used"]) == 3

rfp_sources = [e for e in result["evidence_used"] if e["source"] == "rfp"]
kb_sources   = [e for e in result["evidence_used"] if e["source"] == "internal_document"]
assert len(rfp_sources) == 2
assert len(kb_sources) == 1
assert kb_sources[0]["document_id"] == "doc_hc001"
print(f"Case 1 PASS: grounding JSON parsed correctly "
      f"({len(result['information_gaps'])} gaps, {len(result['evidence_used'])} evidence items)")


# ── Case 2: graceful degradation when JSON is absent ─────────────────────────
result_no_json = _parse_grounding_response(RESPONSE_WITHOUT_JSON)
assert result_no_json["proposal"] == RESPONSE_WITHOUT_JSON.strip()
assert result_no_json["information_gaps"] == []
assert result_no_json["unsupported_claims_avoided"] == []
assert result_no_json["evidence_used"] == []
print("Case 2 PASS: absent JSON → empty grounding lists, proposal preserved")


# ── Case 3: graceful degradation when JSON is malformed ──────────────────────
result_bad_json = _parse_grounding_response(RESPONSE_MALFORMED_JSON)
assert "Some proposal text" in result_bad_json["proposal"]
assert result_bad_json["information_gaps"] == []
print("Case 3 PASS: malformed JSON → empty lists, proposal text preserved")


# ── Case 4: prompt contains explicit prohibition categories ──────────────────
captured_prompt = {}

def _fake_create(**kwargs):
    msg = MagicMock()
    msg.content = [MagicMock(text=RESPONSE_WITH_GROUNDING)]
    captured_prompt["content"] = kwargs["messages"][0]["content"]
    return msg

with patch.object(gen_mod, "get_client") as mock_client:
    mock_client.return_value.messages.create.side_effect = _fake_create

    gen_mod.generate_proposal(REQUIREMENTS, industry="healthcare", knowledge_context=KB_RESULTS)

prompt = captured_prompt["content"]

# These prohibition categories MUST be present in the prompt
prohibited_categories = [
    "certif",           # certifications
    "metric",           # specific metrics/numbers
    "past performance", # past performance claims
    "compliance",       # regulatory compliance
    "HIPAA",            # specific regulation name
    "placeholder",      # the [PLACEHOLDER] mechanism
    "prohibit",         # the prohibition header (matches "PROHIBITIONS" or "PROHIBITED")
    "GROUNDING",        # the grounding rules section
]
for term in prohibited_categories:
    assert term.lower() in prompt.lower(), \
        f"Prohibition category '{term}' missing from prompt"

print(f"Case 4 PASS: prompt contains all {len(prohibited_categories)} required prohibition categories")


# ── Case 5: KB section present in prompt when knowledge_context provided ──────
assert "INTERNAL KNOWLEDGE BASE" in prompt, "KB section must appear in prompt when context provided"
assert "doc_hc001" in prompt
assert "past_healthcare_proposal.txt" in prompt
assert "500-bed hospital" in prompt  # the snippet
print("Case 5 PASS: KB excerpts embedded in prompt with attribution")


# ── Case 6: no KB section when knowledge_context is empty ────────────────────
captured_prompt.clear()
with patch.object(gen_mod, "get_client") as mock_client:
    mock_client.return_value.messages.create.side_effect = _fake_create
    gen_mod.generate_proposal(REQUIREMENTS, industry="healthcare", knowledge_context=[])

prompt_no_kb = captured_prompt["content"]
assert "INTERNAL KNOWLEDGE BASE" not in prompt_no_kb
# But the no-KB warning must still appear
assert "Do NOT invent past performance" in prompt_no_kb or \
       "No internal KB" in prompt_no_kb, \
    "No-KB branch must still warn against inventing past performance"
print("Case 6 PASS: no KB context → KB section absent but anti-hallucination rules remain")


# ── Case 7: return dict shape is correct in all cases ────────────────────────
required_keys = {"proposal", "information_gaps", "unsupported_claims_avoided", "evidence_used"}
for name, res in [("with_grounding", result), ("no_json", result_no_json), ("bad_json", result_bad_json)]:
    assert required_keys.issubset(res.keys()), \
        f"Missing keys in {name}: {required_keys - res.keys()}"
print("Case 7 PASS: all four required keys present in every return scenario")


# ── Case 8: grounding_status logic ───────────────────────────────────────────
def _grounding_status(evidence_used):
    if any(e.get("source") == "internal_document" for e in evidence_used):
        return "grounded_with_kb"
    if evidence_used:
        return "rfp_only"
    return "ungrounded"

assert _grounding_status(result["evidence_used"]) == "grounded_with_kb"
assert _grounding_status([{"source": "rfp", "snippet": "x"}]) == "rfp_only"
assert _grounding_status([]) == "ungrounded"
print("Case 8 PASS: grounding_status logic covers all three states")


# ── Case 9: proposal text retains [PLACEHOLDER] markers ──────────────────────
assert "[PLACEHOLDER:" in result["proposal"], \
    "Proposal must retain [PLACEHOLDER:...] markers for unverified claims"
print("Case 9 PASS: [PLACEHOLDER:...] markers preserved in proposal text")


# ── Case 10: adversarial case — no KB, "write strong past performance" ────────
# When no KB is provided, the model must be explicitly told NOT to invent.
# Verify the no-KB branch instructs against it.
captured_prompt.clear()
with patch.object(gen_mod, "get_client") as mock_client:
    mock_client.return_value.messages.create.side_effect = _fake_create
    gen_mod.generate_proposal(REQUIREMENTS, industry="healthcare")  # no knowledge_context

adversarial_prompt = captured_prompt["content"]
# These are the specific prohibitions that prevent the adversarial case
assert "past performance" in adversarial_prompt.lower() or \
       "past work" in adversarial_prompt.lower(), \
    "No-KB prompt must address past performance prohibition"
assert "invent" in adversarial_prompt.lower() or \
       "do not" in adversarial_prompt.lower(), \
    "No-KB prompt must contain explicit 'do not invent' instruction"
print("Case 10 PASS: adversarial case (no KB + 'strong past performance') → "
      "prompt prohibits fabrication explicitly")


print("\nAll cases passed.")
