import json
import os
from typing import Optional
import anthropic
from dotenv import load_dotenv

load_dotenv()

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def _req_text(r) -> str:
    """Extract plain text from a requirement — handles both string and classified dict."""
    return r["text"] if isinstance(r, dict) else str(r)


def generate_proposal(
    requirements: dict | str,
    industry: Optional[str] = None,
    knowledge_context: list | None = None,
) -> dict:
    """
    Generate a grounded proposal draft.

    The model is constrained to assert only facts present in the RFP or KB.
    It is explicitly prohibited from inventing: certifications, metrics,
    past performance, regulatory compliance, or team credentials.

    Returns:
        {
            "proposal": str,                    — the proposal text
            "information_gaps": list[str],      — items the model could not substantiate
            "unsupported_claims_avoided": list[str],  — claims explicitly withheld
            "evidence_used": list[dict]         — rfp/kb sources referenced
        }
    """
    from services.industry import get_industry_context
    ctx = get_industry_context(industry)

    if isinstance(requirements, dict):
        req_text = f"""Summary: {requirements.get('summary', 'N/A')}
Client: {requirements.get('client', 'N/A')}
Budget: {requirements.get('budget', 'N/A')}
Deadline: {requirements.get('deadline', 'N/A')}

Key Requirements:
{chr(10).join(f'- {_req_text(r)}' for r in requirements.get('requirements', []))}

Deliverables:
{chr(10).join(f'- {d}' for d in requirements.get('deliverables', []))}

Evaluation Criteria:
{chr(10).join(f'- {c}' for c in requirements.get('evaluation_criteria', []))}"""
    else:
        req_text = str(requirements)

    domain_line = (
        f"- Relevant domains to address: {', '.join(ctx['relevant_domains'][:4])}\n"
        if ctx["relevant_domains"] else ""
    )

    # KB section: structured excerpts with attribution
    if knowledge_context:
        doc_blocks = []
        for i, doc in enumerate(knowledge_context, start=1):
            doc_blocks.append(
                f"[KB-{i}] filename={doc['filename']}  id={doc['document_id']}"
                f"  keyword_overlap={doc['relevance_score']}\n"
                f"  Excerpt: \"{doc['snippet'][:400]}\""
            )
        kb_section = (
            "\n\nINTERNAL KNOWLEDGE BASE — VERIFIED PAST WORK:\n"
            "(Retrieved by keyword matching. Use only what is explicitly stated below.)\n\n"
            + "\n\n".join(doc_blocks)
        )
        kb_note = (
            "The KB excerpts above are your ONLY permitted source for past performance claims. "
            "Reference them by excerpt content — do not embellish or extend what they say."
        )
    else:
        kb_section = ""
        kb_note = (
            "No internal KB documents were found for this RFP. "
            "Do NOT invent past performance, case studies, or client names. "
            "Write the 'Team & Experience' section in general terms only."
        )

    prompt = f"""You are a proposal writer. Write a professional proposal draft for the RFP below.

════════════════════════════════════════════════════════════
GROUNDING RULES — READ BEFORE WRITING (NON-NEGOTIABLE)
════════════════════════════════════════════════════════════
PERMITTED SOURCES OF TRUTH:
  1. The RFP requirements listed below
  2. KB excerpts listed below (if any)

HARD PROHIBITIONS — DO NOT CLAIM:
  ✗ Past performance, client names, or project outcomes NOT in the KB
  ✗ Certifications (ISO 27001, SOC 2 Type II, FedRAMP, CMMC, PCI-DSS, HITRUST, etc.)
    unless explicitly mentioned in the RFP requirements or KB
  ✗ Specific metrics or numbers ([X]% uptime, $Y saved, Z% faster, N years experience)
    unless drawn verbatim from a KB excerpt or RFP requirement
  ✗ Regulatory compliance status (HIPAA-compliant, FISMA-authorized, NIST 800-53 certified,
    GDPR-ready, etc.) unless stated in RFP or KB
  ✗ Named individuals, team credentials, or educational backgrounds not in the KB

WHEN EVIDENCE IS MISSING:
  → Insert [PLACEHOLDER: describe what verified evidence would go here]
  → Do NOT silently substitute plausible-sounding data
  → Correct:  "Our team brings [PLACEHOLDER: insert verified relevant certifications]"
  → Incorrect: "Our team holds ISO 27001 and SOC 2 Type II certifications"

{kb_note}
════════════════════════════════════════════════════════════

VENDOR CONTEXT:
Vendor type: {ctx['vendor_type']}
Industry focus: {ctx['focus']}
Tone: {ctx['tone']}

RFP REQUIREMENTS:
{req_text}{kb_section}

Write the proposal with these sections:
1. Executive Summary
2. Understanding of Requirements
3. Proposed Approach & Methodology
4. Team & Experience
5. Timeline
6. Why Choose Us

Additional guidelines:
- Use [COMPANY NAME] as placeholder for your organization's name
- Use [PLACEHOLDER: ...] for any specific claim you cannot support with the sources above
- Be concise and purposeful in each section
{domain_line}
═══════════════════════════════════════════════════════════
AFTER the proposal text, output this JSON block (fenced with ```json ... ```).
Be honest — this is used to audit proposal quality.
```json
{{
  "information_gaps": [
    "list each topic you could not substantiate from the RFP or KB"
  ],
  "unsupported_claims_avoided": [
    "list each category of claim you deliberately withheld due to missing evidence"
  ],
  "evidence_used": [
    {{"source": "rfp", "snippet": "exact phrase or requirement you referenced"}},
    {{"source": "internal_document", "document_id": "...", "filename": "...", "snippet": "excerpt you used"}}
  ]
}}
```
═══════════════════════════════════════════════════════════

Write the full proposal now, followed by the grounding JSON:"""

    message = get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3500,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_grounding_response(message.content[0].text)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_grounding_response(response_text: str) -> dict:
    """
    Split the model's output into proposal text + grounding JSON.

    Expected format:
        <proposal prose>

        ```json
        { "information_gaps": [...], "unsupported_claims_avoided": [...], "evidence_used": [...] }
        ```

    Gracefully degrades: if JSON is absent or malformed, returns empty lists.
    The proposal text is never lost.
    """
    proposal_text = response_text.strip()
    grounding: dict = {
        "information_gaps": [],
        "unsupported_claims_avoided": [],
        "evidence_used": [],
    }

    if "```json" in response_text:
        parts = response_text.split("```json", 1)
        proposal_text = parts[0].strip()
        json_str = parts[1].split("```")[0].strip()
        try:
            parsed = json.loads(json_str)
            grounding["information_gaps"] = parsed.get("information_gaps") or []
            grounding["unsupported_claims_avoided"] = parsed.get("unsupported_claims_avoided") or []
            grounding["evidence_used"] = parsed.get("evidence_used") or []
        except Exception:
            # JSON parse failed — keep empty lists, preserve proposal text
            pass

    return {
        "proposal": proposal_text,
        **grounding,
    }
