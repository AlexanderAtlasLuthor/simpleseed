"""
SAM.gov Opportunities API v2 integration.
Docs: https://open.gsa.gov/api/get-opportunities-public-api/

Free API key: https://sam.gov/profile/details (requires account)
Set SAM_GOV_API_KEY in .env
"""
import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

_BASE_URL = "https://api.sam.gov/opportunities/v2/search"
_TIMEOUT = 20


def _api_key() -> str:
    key = os.getenv("SAM_GOV_API_KEY", "")
    if not key:
        raise ValueError("SAM_GOV_API_KEY is not set. Get a free key at https://sam.gov/profile/details")
    return key


async def search_opportunities(
    keywords: str,
    naics_code: str = "",
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Search SAM.gov for open contract opportunities.

    Returns a dict with:
      - totalRecords: int
      - opportunities: list of opportunity dicts
    """
    params: dict[str, Any] = {
        "api_key": _api_key(),
        "q": keywords,
        "limit": min(limit, 25),
        "offset": offset,
        "ptype": "o,p,k,r,s",  # solicitation types
        "status": "active",
        "sortBy": "relevance",
    }
    if naics_code:
        params["naics"] = naics_code

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            response = await client.get(_BASE_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise ValueError("Invalid SAM.gov API key. Check your SAM_GOV_API_KEY.")
            raise ValueError(f"SAM.gov API error: {e.response.status_code}")
        except httpx.RequestError as e:
            raise ValueError(f"Could not reach SAM.gov API: {e}")

    data = response.json()
    raw = data.get("opportunitiesData", [])

    opportunities = [_normalize(o) for o in raw]

    return {
        "totalRecords": data.get("totalRecords", len(opportunities)),
        "opportunities": opportunities,
    }


async def get_opportunity_text(notice_id: str) -> tuple[str, str]:
    """
    Fetch the description of a specific opportunity by noticeId.
    Returns (text, title).
    """
    params = {
        "api_key": _api_key(),
        "noticeid": notice_id,
        "limit": 1,
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(_BASE_URL, params=params)
        response.raise_for_status()

    data = response.json()
    items = data.get("opportunitiesData", [])
    if not items:
        raise ValueError(f"Opportunity {notice_id} not found")

    item = items[0]
    title = item.get("title", notice_id)

    # Build a structured text block from available fields
    lines = [
        f"Title: {title}",
        f"Agency: {item.get('fullParentPathName', item.get('organizationHierarchy', 'N/A'))}",
        f"Type: {item.get('type', 'N/A')}",
        f"NAICS: {item.get('naicsCode', 'N/A')}",
        f"Posted: {item.get('postedDate', 'N/A')}",
        f"Deadline: {item.get('responseDeadLine', 'N/A')}",
        f"Set-Aside: {item.get('typeOfSetAsideDescription', 'N/A')}",
        "",
        "DESCRIPTION:",
        item.get("description", "No description available."),
    ]

    # Append any additional attachments description if present
    attachments = item.get("resourceLinks", [])
    if attachments:
        lines.append(f"\nAttachments: {', '.join(str(a) for a in attachments[:5])}")

    return "\n".join(lines), title


def _normalize(o: dict) -> dict:
    return {
        "noticeId": o.get("noticeId", ""),
        "title": o.get("title", "Untitled"),
        "agency": o.get("fullParentPathName") or o.get("organizationHierarchy", ""),
        "type": o.get("type", ""),
        "naicsCode": o.get("naicsCode", ""),
        "postedDate": o.get("postedDate", ""),
        "responseDeadLine": o.get("responseDeadLine", ""),
        "setAside": o.get("typeOfSetAsideDescription", ""),
        "uiLink": o.get("uiLink", f"https://sam.gov/opp/{o.get('noticeId', '')}/view"),
    }
