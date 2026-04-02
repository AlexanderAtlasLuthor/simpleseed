import json
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


def extract_requirements(text: str) -> dict:
    prompt = f"""Analyze this RFP (Request for Proposal) and extract structured information.

Return a JSON object with exactly these fields:
- "summary": string — 2-3 sentence overview of what is being requested
- "client": string or null — organization name if mentioned
- "deadline": string or null — submission deadline if mentioned
- "budget": string or null — budget range if mentioned
- "requirements": array of strings — key technical and functional requirements
- "evaluation_criteria": array of strings — how proposals will be evaluated
- "deliverables": array of strings — expected deliverables
- "keywords": array of strings — 5-10 important keywords/topics

RFP TEXT:
{text[:8000]}

Return only valid JSON. No markdown, no extra text."""

    message = get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    content = message.content[0].text

    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return json.loads(content)
    except Exception:
        return {
            "summary": content[:500],
            "client": None,
            "deadline": None,
            "budget": None,
            "requirements": [],
            "evaluation_criteria": [],
            "deliverables": [],
            "keywords": [],
        }
