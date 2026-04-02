import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def generate_proposal(requirements: dict | str) -> str:
    if isinstance(requirements, dict):
        req_text = f"""Summary: {requirements.get('summary', 'N/A')}
Client: {requirements.get('client', 'N/A')}
Budget: {requirements.get('budget', 'N/A')}
Deadline: {requirements.get('deadline', 'N/A')}

Key Requirements:
{chr(10).join(f'- {r}' for r in requirements.get('requirements', []))}

Deliverables:
{chr(10).join(f'- {d}' for d in requirements.get('deliverables', []))}

Evaluation Criteria:
{chr(10).join(f'- {c}' for c in requirements.get('evaluation_criteria', []))}"""
    else:
        req_text = str(requirements)

    prompt = f"""Write a professional proposal draft for this RFP.

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
- Use [COMPANY NAME], [SPECIFIC METRIC], [X YEARS] as placeholders for details that need customization
- Focus on value delivered, not just capabilities
- Keep each section tight and purposeful

Write the full proposal now:"""

    message = get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text
