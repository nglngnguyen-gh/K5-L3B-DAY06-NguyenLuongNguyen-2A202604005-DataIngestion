"""Step 1: read the corpus, decide which pages count as content, and write the manifest.

Run from starter/:  python -m scripts.build_manifest
Outputs:
  ../data/manifest.json             source, license, page list, counting rule, per-page stats
  data/processed/pages.jsonl        normalized page text + metadata (regenerable, not committed)
  results/ingestion_log.json        empty/error/excluded pages and footer checks
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # starter/
sys.path.insert(0, str(ROOT))

from src.ingestion import load_pdf  # noqa: E402

PDF_PATH = ROOT / "data" / "The World Bank Group Annual Report 2026.pdf"
DOCUMENT_ID = "wbg-ar-2026"
MIN_CONTENT_CHARS = 500  # below this a page is a cover/divider/photo page

# Table of contents printed on PDF page 2 (printed page -> section title), copied verbatim.
CONTENTS = [
    (2, "About Us"),
    (4, "Letter from the Executive Directors"),
    (6, "Letter from the President"),
    (8, "Reforms and Results"),
    (10, "Jobs Strategy"),
    (26, "World Bank Group Scorecard"),
    (28, "Target Map"),
    (30, "Financial Summary"),
    (32, "One World Bank Group"),
    (49, "World Bank (IBRD/IDA)"),
    (61, "IFC"),
    (72, "MIGA"),
    (80, "ICSID"),
]

# Pages excluded by inspection (reason must be checkable in the PDF).
MANUAL_EXCLUSIONS = {
    2: "table of contents + report preface",
    45: "back matter: financial statements by reference, legal disclaimer, rights, credits",
}


def expected_printed_pages(pdf_page: int) -> list[int]:
    """Layout: PDF p1 = cover, p2 = printed p1, then each PDF page is a 2-page spread."""
    if pdf_page == 1:
        return []
    if pdf_page == 2:
        return [1]
    return [2 * pdf_page - 4, 2 * pdf_page - 3]


def sections_for(printed: list[int]) -> list[str]:
    out: list[str] = []
    for n in printed:
        title = None
        for start, name in CONTENTS:
            if n >= start:
                title = name
        if title and title not in out:
            out.append(title)
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    if not PDF_PATH.exists():
        raise FileNotFoundError(PDF_PATH)
    source = PDF_PATH.relative_to(ROOT.parent).as_posix()
    pages = load_pdf(PDF_PATH, DOCUMENT_ID, source)

    page_rows, log_rows = [], []
    for p in pages:
        meta = p.metadata
        expected = expected_printed_pages(p.page)
        found = meta["printed_pages"]
        if found and found != expected:
            log_rows.append({"page": p.page, "issue": "footer_mismatch", "found": found, "expected": expected})
        printed = expected
        sections = sections_for(printed)

        if meta["extraction_status"] != "ok":
            counted, reason = False, f"extraction {meta['extraction_status']}"
        elif p.page in MANUAL_EXCLUSIONS:
            counted, reason = False, MANUAL_EXCLUSIONS[p.page]
        elif meta["chars"] < MIN_CONTENT_CHARS:
            counted, reason = False, f"cover/divider page (< {MIN_CONTENT_CHARS} chars)"
        else:
            counted, reason = True, None
        if not counted:
            log_rows.append({"page": p.page, "issue": "excluded", "reason": reason, "chars": meta["chars"]})

        p.metadata.update({"printed_pages": printed, "sections": sections, "counted": counted})
        page_rows.append({
            "pdf_page": p.page,
            "printed_pages": printed,
            "sections": sections,
            "chars": meta["chars"],
            "counted": counted,
            "exclusion_reason": reason,
        })

    counted_pages = [r["pdf_page"] for r in page_rows if r["counted"]]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": [{
            "source_id": DOCUMENT_ID,
            "title": "The World Bank Group Annual Report 2026: Investing in People, Investing in Prosperity",
            "author": "World Bank Group",
            "year": 2026,
            "reporting_period": "July 1, 2025 – June 30, 2026 (fiscal 2026)",
            "source_path_or_url": source,
            "original_url": "https://www.worldbank.org/en/about/annual-report",
            "doi": "10.1596/AR2026",
            "license_or_permission": "CC BY-NC-ND 3.0 IGO (stated on PDF page 45, 'Rights and Permissions')",
            "attribution": "World Bank Group. 2026. The World Bank Group Annual Report 2026. Washington, DC: World Bank. License: Creative Commons Attribution-NonCommercial-NoDerivatives (CC BY-NC-ND 3.0 IGO).",
            "usage_note": "Non-commercial course lab. PDF kept unmodified; text extraction/chunks/embeddings are used only for retrieval experiments and are not redistributed as an adapted work. Third-party content (photos, figures) is not claimed.",
            "accessed_at": "2026-11-14",
            "accessed_at_note": "date the PDF was added to the lab repo (file creation time); download date not separately recorded",
            "snapshot": {"pdf_creation_date": "2026-10-14", "producer": "Adobe InDesign 21.6", "sha256": sha256(PDF_PATH), "bytes": PDF_PATH.stat().st_size},
            "physical_pdf_pages": len(pages),
            "printed_pages_total": max(max(r["printed_pages"]) for r in page_rows if r["printed_pages"]),
            "counted_pdf_pages": counted_pages,
            "counted_page_count": len(counted_pages),
            "counted_chars": sum(r["chars"] for r in page_rows if r["counted"]),
        }],
        "page_counting_rule": (
            "Unit = one physical PDF page (most PDF pages are 2-page spreads, so this is conservative). "
            f"Counted if text extraction succeeded, the page has >= {MIN_CONTENT_CHARS} normalized characters, "
            "and it is not table of contents or legal/credits back matter. Excluded: cover, contents, "
            "section divider, back matter, back cover."
        ),
        "section_rule": "section = title(s) from the printed table of contents (PDF p2) covering the page's printed page numbers; a spread on a boundary gets both titles.",
        "extraction": {"library": "pypdf", "normalization": "NFKC, soft-hyphen removal, footer removal, line-break hyphen rejoin, whitespace collapse", "ocr": "not needed (all pages have a text layer)"},
        "pages": page_rows,
    }

    (ROOT.parent / "data" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    out_dir = ROOT / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "pages.jsonl").open("w", encoding="utf-8") as f:
        for p in pages:
            f.write(json.dumps({"document_id": p.document_id, "source": p.source, "page": p.page, "text": p.text, "metadata": p.metadata}, ensure_ascii=False) + "\n")
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "ingestion_log.json").write_text(json.dumps(log_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"PDF pages: {len(pages)} | counted content pages: {len(counted_pages)} | counted chars: {manifest['sources'][0]['counted_chars']}")
    for row in log_rows:
        print("LOG", row)
    if len(counted_pages) < 30:
        raise SystemExit("Corpus has fewer than 30 content pages")


if __name__ == "__main__":
    main()
