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


def generate_proposal(requirements: dict | str, industry: Optional[str] = None) -> str:
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
        f"- Highlight relevant expertise in: {', '.join(ctx['relevant_domains'][:4])}\n"
        if ctx["relevant_domains"] else ""
    )

    prompt = f"""Write a professional proposal draft for this RFP.

VENDOR CONTEXT:
You are writing on behalf of a {ctx['vendor_type']}.
Industry focus: {ctx['focus']}
Tone: {ctx['tone']}

REQUIREMENTS:
{req_text}

Write the proposal with these sections:
1. Executive Summary
2. Understanding of Requirements
3. Proposed Approach & Methodology
4. Team & Experience
5. Timeline
6. Why Choose Us

Guidelines:
- Be professional, concise, and compelling
- Adapt the language and emphasis to the {ctx['label']} industry context
- Use [COMPANY NAME], [SPECIFIC METRIC], [X YEARS] as placeholders for details that need customization
- Focus on value delivered, not just capabilities
- Keep each section tight and purposeful
{domain_line}
Write the full proposal now:"""

    message = get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text
