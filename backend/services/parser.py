from pypdf import PdfReader

# Minimum printable characters required to consider pypdf extraction successful.
# Below this threshold the PDF is treated as scanned/image-based and OCR is attempted.
_MIN_TEXT_CHARS = 50


def parse_pdf(file_path: str) -> str:
    """
    Extract text from a PDF file.

    Strategy:
    1. Try pypdf (fast, zero extra dependencies) — works for text-based PDFs.
    2. If the extracted text is below _MIN_TEXT_CHARS (scanned/image PDF),
       fall back to OCR via pytesseract + pdf2image.

    Returns the best available text, or empty string if both methods fail.
    """
    text = _extract_with_pypdf(file_path)
    if len(text.strip()) >= _MIN_TEXT_CHARS:
        return text

    # Fallback: OCR
    return _extract_with_ocr(file_path)


def _extract_with_pypdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    pages = []
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            pages.append(extracted)
    return "\n".join(pages).strip()


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
