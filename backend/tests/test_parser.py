"""
Unit tests for services/parser.py

All pdfplumber and OCR calls are mocked — no real PDF files needed.
Tests cover:
  - _table_to_markdown: normal, None cells, empty input, single-row
  - parse_pdf: happy path (pdfplumber), OCR fallback threshold, multi-page
"""
from unittest.mock import MagicMock, patch

import pytest

from services.parser import _table_to_markdown, parse_pdf


# ── _table_to_markdown ─────────────────────────────────────────────────────

def test_table_to_markdown_basic_two_rows():
    rows = [["Name", "Value"], ["Alpha", "42"]]
    result = _table_to_markdown(rows)
    assert "| Name | Value |" in result
    assert "| --- | --- |" in result
    assert "| Alpha | 42 |" in result


def test_table_to_markdown_none_cells_become_empty_string():
    rows = [["Col1", None], ["val", "v2"]]
    result = _table_to_markdown(rows)
    assert "Col1" in result
    # None cell → empty string, so the separator still appears
    assert "| --- |" in result


def test_table_to_markdown_empty_input_returns_empty_string():
    assert _table_to_markdown([]) == ""


def test_table_to_markdown_all_empty_cells_returns_empty_string():
    assert _table_to_markdown([[None, None], [None, ""]]) == ""


def test_table_to_markdown_single_header_row():
    rows = [["Only Header"]]
    result = _table_to_markdown(rows)
    assert "| Only Header |" in result
    assert "| --- |" in result


def test_table_to_markdown_ragged_rows_padded():
    # Second row has fewer columns — should be padded
    rows = [["A", "B", "C"], ["x"]]
    result = _table_to_markdown(rows)
    assert "A" in result
    assert "x" in result


# ── parse_pdf ──────────────────────────────────────────────────────────────

def _make_mock_pdf(page_text: str, tables=None):
    """Build a pdfplumber PDF mock with one page."""
    page = MagicMock()
    page.extract_text.return_value = page_text
    page.find_tables.return_value = tables or []
    page.extract_tables.return_value = tables or []

    pdf = MagicMock()
    pdf.pages = [page]
    pdf.__enter__ = MagicMock(return_value=pdf)
    pdf.__exit__ = MagicMock(return_value=False)
    return pdf


def test_parse_pdf_returns_text_from_pdfplumber():
    long_text = "This is the content of an IT services RFP document. " * 5  # > 50 chars
    mock_pdf = _make_mock_pdf(long_text)

    with patch("pdfplumber.open", return_value=mock_pdf):
        result = parse_pdf("fake_rfp.pdf")

    assert "IT services RFP document" in result


def test_parse_pdf_triggers_ocr_when_pdfplumber_text_too_short():
    short_text = "Hi"  # < 50 chars → OCR threshold
    mock_pdf = _make_mock_pdf(short_text)
    ocr_result = "Full scanned document text extracted via OCR with lots of content here."

    with patch("pdfplumber.open", return_value=mock_pdf), \
         patch("services.parser._extract_with_ocr", return_value=ocr_result) as mock_ocr:
        result = parse_pdf("scanned.pdf")

    mock_ocr.assert_called_once_with("scanned.pdf")
    assert result == ocr_result


def test_parse_pdf_returns_empty_string_when_both_fail():
    mock_pdf = _make_mock_pdf("")
    with patch("pdfplumber.open", return_value=mock_pdf), \
         patch("services.parser._extract_with_ocr", return_value=""):
        result = parse_pdf("empty.pdf")

    assert result == ""


def test_parse_pdf_multi_page_joins_with_double_newline():
    page1 = MagicMock()
    page1.extract_text.return_value = "Page one content with enough characters to exceed threshold"
    page1.find_tables.return_value = []

    page2 = MagicMock()
    page2.extract_text.return_value = "Page two content with enough characters as well"
    page2.find_tables.return_value = []

    pdf = MagicMock()
    pdf.pages = [page1, page2]
    pdf.__enter__ = MagicMock(return_value=pdf)
    pdf.__exit__ = MagicMock(return_value=False)

    with patch("pdfplumber.open", return_value=pdf):
        result = parse_pdf("multipage.pdf")

    assert "Page one" in result
    assert "Page two" in result
    assert "\n\n" in result


def test_parse_pdf_uses_pdfplumber_not_ocr_when_text_sufficient():
    sufficient_text = "A" * 60  # > 50 chars
    mock_pdf = _make_mock_pdf(sufficient_text)

    with patch("pdfplumber.open", return_value=mock_pdf), \
         patch("services.parser._extract_with_ocr") as mock_ocr:
        parse_pdf("normal.pdf")

    mock_ocr.assert_not_called()
