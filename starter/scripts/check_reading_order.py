"""Detect reading-order inversions in pypdf extraction (stream order vs. visual position).

Run from starter/:  python -m scripts.check_reading_order
For each counted page, text segments (>= MIN_LEN chars) are taken in pypdf's stream order with
their (x, y). An event is flagged when, inside the same half of a 2-page spread, the next segment
- sits in the same column (|dx| <= COL_TOL) but clearly HIGHER on the page (dy > JUMP), or
- moves to a column further LEFT while also moving up,
or when the stream moves from the right-hand page back to the left-hand page.
Normal reading (down a column, then to the top of the next column to the right) is not flagged.
Running footers ("NN THE WORLD BANK GROUP ANNUAL REPORT 2026") are ignored: they are removed in normalization.
Output: results/reading_order_check.json
"""
from __future__ import annotations

import json
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
MIN_LEN, COL_TOL, JUMP = 25, 40, 30


def segments(page):
    segs = []

    def visit(text, cm, tm, fd, fs):
        t = " ".join(text.split())
        if len(t) >= MIN_LEN and "ANNUAL REPORT 2026" not in t:
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            segs.append((x, y, t))

    page.extract_text(visitor_text=visit)
    return segs


def main() -> None:
    manifest = json.loads((ROOT.parent / "data" / "manifest.json").read_text(encoding="utf-8"))
    src = manifest["sources"][0]
    reader = PdfReader(ROOT.parent / src["source_path_or_url"])
    report = []
    for pno in src["counted_pdf_pages"]:
        page = reader.pages[pno - 1]
        mid = float(page.mediabox.width) / 2
        segs = segments(page)
        events = []
        for (x0, y0, t0), (x1, y1, t1) in zip(segs, segs[1:]):
            h0, h1 = x0 >= mid, x1 >= mid
            kind = None
            if h0 and not h1:
                kind = "right_page_to_left_page"
            elif h0 == h1:
                if abs(x1 - x0) <= COL_TOL and y1 - y0 > JUMP:
                    kind = "jump_up_same_column"
                elif x1 < x0 - COL_TOL and y1 - y0 > JUMP:
                    kind = "back_to_left_column"
            if kind:
                events.append({"kind": kind, "from": {"x": round(x0), "y": round(y0), "text": t0[:90]},
                               "to": {"x": round(x1), "y": round(y1), "text": t1[:90]}})
        report.append({"pdf_page": pno, "segments": len(segs), "events": events})
    out = ROOT / "results" / "reading_order_check.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    flagged = [r for r in report if r["events"]]
    print(f"pages checked: {len(report)} | pages with events: {len(flagged)}")
    for r in flagged:
        kinds = {}
        for e in r["events"]:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        print(f"p{r['pdf_page']}: {kinds}")


if __name__ == "__main__":
    main()
