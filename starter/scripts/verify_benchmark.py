"""Step 2: verify the benchmark against the normalized corpus BEFORE any retrieval run.

Run from starter/ (after build_manifest):  python -m scripts.verify_benchmark
Checks: split sizes, filter counts, required fields, evidence present on the gold page
(whitespace-insensitive), every other counted page that also contains the evidence,
gold page counted, and filter value present in the gold page's sections.
Writes ../benchmark/verification.json (includes a SHA-256 freeze of questions.json).
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT.parent / "benchmark" / "questions.json"
PAGES = ROOT / "data" / "processed" / "pages.jsonl"
REQUIRED = ["id", "split", "question", "expected_answer", "gold_source_id", "gold_page", "evidence_quote", "filter"]


def squash(s: str) -> str:
    return " ".join(s.split())


def main() -> None:
    data = json.loads(BENCH.read_text(encoding="utf-8"))
    qs = data["questions"]
    pages = {}
    for line in PAGES.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        pages[(row["document_id"], row["page"])] = row

    errors, report = [], []
    ids = [q["id"] for q in qs]
    if len(ids) != len(set(ids)):
        errors.append("duplicate ids")
    for q in qs:
        missing = [k for k in REQUIRED if k not in q]
        if missing:
            errors.append(f"{q.get('id')}: missing {missing}")
            continue
        golds = [{"gold_page": q["gold_page"], "evidence_quote": q["evidence_quote"]}] + q.get("alternative_gold", [])
        checks = []
        for g in golds:
            row = pages.get((q["gold_source_id"], g["gold_page"]))
            if row is None:
                errors.append(f"{q['id']}: page {g['gold_page']} not found")
                continue
            ev = squash(g["evidence_quote"])
            found = ev in squash(row["text"])
            also_on = [p for (doc, p), r in pages.items()
                       if doc == q["gold_source_id"] and p != g["gold_page"] and r["metadata"].get("counted") and ev in squash(r["text"])]
            counted = bool(row["metadata"].get("counted"))
            sections = row["metadata"].get("sections", [])
            filter_ok = None
            if q["filter"]:
                filter_ok = q["filter"]["section"] in sections
                if not filter_ok:
                    errors.append(f"{q['id']}: filter {q['filter']} not in sections {sections} of page {g['gold_page']}")
            if not found:
                errors.append(f"{q['id']}: evidence not found on page {g['gold_page']}")
            if not counted:
                errors.append(f"{q['id']}: page {g['gold_page']} is not a counted content page")
            checks.append({"gold_page": g["gold_page"], "evidence_found": found, "page_counted": counted,
                           "page_sections": sections, "filter_value_on_page": filter_ok,
                           "evidence_also_on_pages": also_on})
        report.append({"id": q["id"], "split": q["split"], "type": q.get("type"), "filter": q["filter"], "checks": checks})

    split = Counter(q["split"] for q in qs)
    filt = Counter(q["split"] for q in qs if q.get("filter"))
    if len(qs) < 20: errors.append("fewer than 20 questions")
    if split["dev"] < 15 or split["test"] < 5: errors.append(f"split too small: {dict(split)}")
    if sum(filt.values()) < 3 or filt["test"] < 1: errors.append(f"filter questions insufficient: {dict(filt)}")

    test_pages = {q["gold_page"] for q in qs if q["split"] == "test"}
    dev_pages = {g for q in qs if q["split"] == "dev"
                 for g in [q["gold_page"]] + [a["gold_page"] for a in q.get("alternative_gold", [])]}
    out = {
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "questions_sha256": hashlib.sha256(BENCH.read_bytes()).hexdigest(),
        "counts": {"total": len(qs), "split": dict(split), "with_filter": dict(filt),
                   "types": dict(Counter(q.get("type") for q in qs))},
        "dev_test_shared_gold_pages": sorted(test_pages & dev_pages),
        "errors": errors,
        "questions": report,
    }
    (BENCH.parent / "verification.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out["counts"], ensure_ascii=False))
    print("shared dev/test gold pages:", out["dev_test_shared_gold_pages"])
    for r in report:
        for c in r["checks"]:
            if c["evidence_also_on_pages"]:
                print(f"{r['id']}: evidence also on pages {c['evidence_also_on_pages']}")
    print("ERRORS:" if errors else "All checks passed.", *errors, sep="\n")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
