"""
Fetch RFP content from a URL.
Handles HTML pages and direct PDF links.
No scraping of authenticated portals — user provides the direct URL.
"""
import io
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from services.parser import parse_pdf

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SimpleSeed/1.0; RFP analysis tool)",
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
}

_TIMEOUT = 30  # seconds
_MAX_BYTES = 20 * 1024 * 1024  # 20 MB


async def fetch_url_text(url: str) -> tuple[str, str]:
    """
    Fetch text from a URL.
    Returns (text, source_name) where source_name is a readable identifier.
    Raises ValueError with a user-friendly message on failure.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://")

    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.TimeoutException:
        raise ValueError("Request timed out. The server took too long to respond.")
    except httpx.HTTPStatusError as e:
        raise ValueError(f"Server returned {e.response.status_code}. Check that the URL is publicly accessible.")
    except httpx.RequestError as e:
        raise ValueError(f"Could not reach URL: {e}")

    content_type = response.headers.get("content-type", "").lower()
    source_name = parsed.hostname or url

    # PDF response
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        text = _extract_pdf_bytes(response.content)
        if not text.strip():
            raise ValueError("PDF downloaded but contains no extractable text (may be scanned/image-based).")
        return text, source_name

    # HTML response
    if "html" in content_type or "text" in content_type:
        text = _extract_html_text(response.text)
        if not text.strip():
            raise ValueError("Page fetched but no readable text could be extracted.")
        return text, source_name

    raise ValueError(f"Unsupported content type: {content_type}. Only HTML pages and PDF files are supported.")


def _extract_pdf_bytes(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        tmp_path = f.name
    try:
        return parse_pdf(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _extract_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Remove boilerplate elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    # Prefer <main> or <article> if available
    main = soup.find("main") or soup.find("article") or soup.find(id="content")
    root = main if main else soup.body or soup

    lines = []
    for element in root.descendants:
        if element.name in ("h1", "h2", "h3", "h4"):
            text = element.get_text(strip=True)
            if text:
                lines.append(f"\n{text}\n")
        elif element.name in ("p", "li", "td", "th"):
            text = element.get_text(strip=True)
            if text:
                lines.append(text)

    return "\n".join(lines)
