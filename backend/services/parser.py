import pdfplumber

# Minimum printable characters required to consider primary extraction successful.
# Below this threshold the PDF is treated as scanned/image-based and OCR is attempted.
_MIN_TEXT_CHARS = 50


def parse_pdf(file_path: str) -> str:
    """
    Extract text (and structured tables) from a PDF file.

    Strategy:
    1. pdfplumber — detects and extracts tables as markdown, preserves reading
       order, handles complex layouts better than pypdf.
    2. If extracted text is below _MIN_TEXT_CHARS (scanned/image PDF),
       fall back to OCR via pytesseract + pdf2image.

    Returns the best available text, or empty string if both methods fail.
    """
    text = _extract_with_pdfplumber(file_path)
    if len(text.strip()) >= _MIN_TEXT_CHARS:
        return text

    # Fallback: OCR for scanned/image-based PDFs
    return _extract_with_ocr(file_path)


# ---------------------------------------------------------------------------
# Primary extractor: pdfplumber (text + structured tables)
# ---------------------------------------------------------------------------

def _extract_with_pdfplumber(file_path: str) -> str:
    page_contents = []

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            content = _extract_page(page)
            if content.strip():
                page_contents.append(content.strip())

    return "\n\n".join(page_contents)


def _extract_page(page) -> str:
    """
    Extract a single page preserving reading order:
    narrative text above/between/below tables, with tables as markdown.
    """
    tables = page.find_tables()

    if not tables:
        return page.extract_text() or ""

    # Sort tables top-to-bottom (pdfplumber y-axis: 0 = top of page)
    tables_sorted = sorted(tables, key=lambda t: t.bbox[1])

    parts: list[str] = []
    prev_bottom: float = 0.0

    for table in tables_sorted:
        _x0, top, _x1, bottom = table.bbox

        # Text strip above this table
        if top > prev_bottom:
            strip = page.crop((0, prev_bottom, page.width, top))
            strip_text = strip.extract_text() or ""
            if strip_text.strip():
                parts.append(strip_text.strip())

        # Table as markdown
        rows = table.extract()
        if rows:
            md = _table_to_markdown(rows)
            if md:
                parts.append(md)

        prev_bottom = bottom

    # Text strip after the last table
    if prev_bottom < page.height:
        strip = page.crop((0, prev_bottom, page.width, page.height))
        strip_text = strip.extract_text() or ""
        if strip_text.strip():
            parts.append(strip_text.strip())

    return "\n\n".join(parts)


def _table_to_markdown(rows: list[list]) -> str:
    """Convert a list-of-lists table to a markdown table string."""
    if not rows:
        return ""

    # Normalize cells: None → "", strip whitespace, collapse newlines
    cleaned = [
        [str(cell or "").replace("\n", " ").strip() for cell in row]
        for row in rows
    ]

    # Drop rows that are entirely empty
    cleaned = [row for row in cleaned if any(cell for cell in row)]
    if not cleaned:
        return ""

    # Pad all rows to the same column count
    col_count = max(len(row) for row in cleaned)
    cleaned = [row + [""] * (col_count - len(row)) for row in cleaned]

    # First row is the header
    header = cleaned[0]
    separator = ["---" for _ in header]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in cleaned[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# OCR fallback: scanned / image-based PDFs
# ---------------------------------------------------------------------------

def _extract_with_ocr(file_path: str) -> str:
    """
    Convert each PDF page to an image and run Tesseract OCR.
    Requires: tesseract-ocr (system), pytesseract, pdf2image, Pillow (pip).
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        raise RuntimeError(
            "OCR dependencies are not installed. Run:\n"
            "  apt-get install -y tesseract-ocr poppler-utils\n"
            "  pip install pytesseract pdf2image Pillow"
        )

    pages = convert_from_path(file_path, dpi=200)
    texts = []
    for page_img in pages:
        page_text = pytesseract.image_to_string(page_img, lang="eng")
        if page_text.strip():
            texts.append(page_text.strip())

    return "\n\n".join(texts)
