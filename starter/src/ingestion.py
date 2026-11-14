"""Read and normalize source data."""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage

log = logging.getLogger(__name__)

# Running footer printed on every spread, e.g. "61 THE WORLD BANK GROUP ANNUAL REPORT 2026".
FOOTER_RE = re.compile(r"(\d{1,3})\s*THE WORLD BANK GROUP ANNUAL REPORT 2026")
SOFT_HYPHEN = "­"


def extract_printed_pages(raw_text: str) -> list[int]:
    """Return printed page numbers found in the running footer (sorted, unique)."""
    return sorted({int(n) for n in FOOTER_RE.findall(raw_text)})


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace while keeping paragraph structure.

    - NFKC: folds ligatures (ﬁ -> fi) and full-width forms.
    - Removes soft hyphens and the running footer (kept separately as printed_pages).
    - Re-joins words hyphenated across a line break ("faith-\\nbased" -> "faith-based").
    - Collapses spaces inside a line; keeps at most one blank line between paragraphs.
    """
    text = unicodedata.normalize("NFKC", text).replace(SOFT_HYPHEN, "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = FOOTER_RE.sub(" ", text)
    text = re.sub(r"(\w)-[ \t]*\n[ \t]*(\w)", r"\1-\2", text)
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Extract each physical PDF page (1-based) with its source and printed page numbers.

    Pages with no extractable text are kept with empty text and flagged in metadata
    (`extraction_status = "empty"`); OCR, when needed, is a separate step.
    Raises if the file cannot be opened — no silent fallback.
    """
    path = Path(path)
    reader = PdfReader(path)
    pages: list[DocumentPage] = []
    for idx, pdf_page in enumerate(reader.pages, start=1):
        status, error = "ok", None
        try:
            raw = pdf_page.extract_text() or ""
        except Exception as exc:  # record and continue; the page stays traceable
            raw, status, error = "", "error", f"{type(exc).__name__}: {exc}"
            log.warning("page %s: extraction failed: %s", idx, error)
        text = normalize_text(raw)
        if status == "ok" and not text:
            status = "empty"
            log.warning("page %s: no extractable text", idx)
        pages.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=idx,
                text=text,
                metadata={
                    "printed_pages": extract_printed_pages(raw),
                    "raw_chars": len(raw),
                    "chars": len(text),
                    "extraction_status": status,
                    "extraction_error": error,
                },
            )
        )
    return pages
