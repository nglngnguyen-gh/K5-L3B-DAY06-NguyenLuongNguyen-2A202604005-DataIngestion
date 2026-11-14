"""Evaluate retrieved evidence and keep per-query traces."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

PARTIAL_MIN_CHARS = 30


def _squash(s: str) -> str:
    return " ".join(s.split())


def gold_list(question: dict[str, Any]) -> list[dict[str, Any]]:
    golds = [{"gold_page": question["gold_page"], "evidence_quote": question["evidence_quote"]}]
    golds += question.get("alternative_gold", [])
    return [{**g, "gold_source_id": question["gold_source_id"]} for g in golds]


def _partial(evidence: str, text: str) -> bool:
    """True if the chunk holds a >=30-char prefix or suffix of the evidence (evidence cut by a boundary)."""
    for n in range(len(evidence) - 1, PARTIAL_MIN_CHARS - 1, -1):
        if evidence[:n] in text or evidence[-n:] in text:
            return True
    return False


def label_hit(hit: dict[str, Any], golds: list[dict[str, Any]]) -> dict[str, Any]:
    text = _squash(hit["text"])
    on_gold_page = full = partial = False
    for g in golds:
        if hit["document_id"] == g["gold_source_id"] and hit["page"] == g["gold_page"]:
            on_gold_page = True
            ev = _squash(g["evidence_quote"])
            if ev in text:
                full = True
            elif _partial(ev, text):
                partial = True
    return {"on_gold_page": on_gold_page, "evidence_full": full, "evidence_partial": partial and not full}


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """A hit = chunk from a gold source/page that contains the full gold evidence.

    Hit@1: rank-1 chunk is a hit. Evidence Hit@3: any of the top-3 is a hit.
    Also records page-only matches, partial evidence (boundary cut) and filter compliance.
    """
    golds = gold_list(question)
    labels = [label_hit(h, golds) for h in hits[:3]]
    hit_ranks = [i + 1 for i, lab in enumerate(labels) if lab["evidence_full"]]
    flt = question.get("filter")
    compliance = None
    if flt:
        compliance = all(flt["section"] in h["sections"] for h in hits[:3]) and len(hits) > 0
    return {
        "hit_at_1": bool(labels and labels[0]["evidence_full"]),
        "hit_at_3": bool(hit_ranks),
        "first_hit_rank": hit_ranks[0] if hit_ranks else None,
        "page_hit_at_3": any(lab["on_gold_page"] for lab in labels),
        "evidence_split_in_top3": any(lab["evidence_partial"] for lab in labels) and not hit_ranks,
        "filter_compliant": compliance,
        "hit_labels": labels,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate by strategy and split; report numerator/denominator, not only rates."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for t in traces:
        groups[(t["strategy"], t["split"])].append(t)
    out: dict[str, Any] = {}
    for (strategy, split), rows in sorted(groups.items()):
        n = len(rows)
        ev = [r["eval"] for r in rows]
        # Questions that carry a filter: for C it is applied; for A/B we still measure whether the
        # unfiltered top-3 happens to stay inside the requested section (for the B-C comparison).
        filt = [r for r in rows if r.get("filter")]

        def frac(k: int, d: int) -> str:
            return f"{k}/{d}" if d else "N/A"

        out.setdefault(strategy, {})[split] = {
            "n": n,
            "hit_at_1": frac(sum(e["hit_at_1"] for e in ev), n),
            "hit_at_3": frac(sum(e["hit_at_3"] for e in ev), n),
            "page_hit_at_3": frac(sum(e["page_hit_at_3"] for e in ev), n),
            "evidence_split_misses": [r["id"] for r in rows if r["eval"]["evidence_split_in_top3"]],
            "misses_at_3": [r["id"] for r in rows if not r["eval"]["hit_at_3"]],
            "filter_questions": [r["id"] for r in rows if r.get("filter")],
            "filter_compliance": frac(sum(bool(r["eval"]["filter_compliant"]) for r in filt), len(filt)),
            "filter_question_hit_at_3": frac(sum(r["eval"]["hit_at_3"] for r in rows if r.get("filter")),
                                             sum(1 for r in rows if r.get("filter"))),
        }
    return out
