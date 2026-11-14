"""Chunking strategies. Both work per page so every chunk maps to exactly one PDF page."""
from __future__ import annotations

import re

from .models import Chunk, DocumentPage

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9$€“\"(•])")
TERMINAL = re.compile(r"[.!?:;”\"]$")
NUMERIC_TOKEN = re.compile(r"^\(?[-$€]?\d[\d,.]*%?\)?[a-z]?$")


def _squash(text: str) -> str:
    return " ".join(text.split())


def _base_meta(page: DocumentPage) -> dict:
    return {k: page.metadata[k] for k in ("sections", "printed_pages") if k in page.metadata}


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Fixed character windows over the whitespace-collapsed page text (no boundary snapping)."""
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("require size > 0 and 0 <= overlap < size")
    text = _squash(page.text)
    step = size - overlap
    chunks: list[Chunk] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        piece = text[start:end].strip()
        if piece:
            idx = len(chunks)
            chunks.append(Chunk(
                chunk_id=f"{page.document_id}:p{page.page:03d}:f{idx:03d}",
                document_id=page.document_id, source=page.source, page=page.page, text=piece,
                metadata={**_base_meta(page), "chunk_index": idx, "char_start": start, "char_end": end, "heading": None},
            ))
        if end == len(text):
            break
        start += step
    return chunks


def _is_heading(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    if line.startswith(("TABLE ", "FIGURE ")):
        return True
    if len(letters) < 4 or len(line) > 120:
        return False
    return sum(c.isupper() for c in letters) / len(letters) >= 0.8


def _is_table_row(line: str) -> bool:
    toks = line.split()
    numeric = sum(bool(NUMERIC_TOKEN.match(t)) for t in toks)
    last = toks[-1]
    return numeric >= 2 and numeric / len(toks) >= 0.3 and bool(NUMERIC_TOKEN.match(last)) and not last.endswith(",")


def _blocks(text: str) -> list[tuple[str | None, str]]:
    """Rebuild (heading, paragraph) blocks from column-wrapped PDF lines."""
    lines = [ln.strip() for ln in text.split("\n")]
    blocks: list[tuple[str | None, str]] = []
    heading: str | None = None
    para: list[str] = []
    pending_heading: list[str] = []

    def flush_para() -> None:
        if para:
            blocks.append((heading, " ".join(para)))
            para.clear()

    for i, line in enumerate(lines):
        if not line:
            flush_para()
            continue
        if _is_heading(line):
            flush_para()
            pending_heading.append(line)
            continue
        if pending_heading:
            heading = " ".join(pending_heading)
            blocks.append((heading, heading))  # heading text stays in the chunk where it occurs
            pending_heading.clear()
        if line.startswith("•"):
            flush_para()
        para.append(line)
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if _is_table_row(line) or (TERMINAL.search(line) and (not nxt or nxt[:1].isupper() or nxt[:1].isdigit() or nxt.startswith("•"))):
            flush_para()
    flush_para()
    if pending_heading:
        heading = " ".join(pending_heading)
        blocks.append((heading, heading))
    return blocks


def _split_oversized(text: str, max_size: int) -> list[str]:
    parts: list[str] = []
    cur = ""
    for sent in SENTENCE_SPLIT.split(text):
        while len(sent) > max_size:  # a single sentence longer than the limit: hard split
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(sent[:max_size])
            sent = sent[max_size:]
        if cur and len(cur) + 1 + len(sent) > max_size:
            parts.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        parts.append(cur)
    return parts


def _merge_small(groups: list[tuple[str | None, str]], min_size: int, max_size: int) -> list[tuple[str | None, str]]:
    """Merge chunks shorter than min_size with a neighbour on the same page if the result fits max_size.
    (Typical case: infographic call-outs such as '33,000' + 'JOBS IN JORDAN ...'.)"""
    out: list[tuple[str | None, str]] = []
    for heading, text in groups:
        if out:
            prev_h, prev_t = out[-1]
            fits = len(prev_t) + 1 + len(text) <= max_size
            if fits and (len(prev_t) < min_size or len(text) < min_size):
                out[-1] = (prev_h if len(prev_t) >= len(text) else heading, f"{prev_t}\n{text}")
                continue
        out.append((heading, text))
    return out


def by_paragraph(page: DocumentPage, max_size: int, min_size: int = 200) -> list[Chunk]:
    """Group reconstructed paragraphs under the same heading up to max_size characters.

    A new heading starts a new chunk; paragraphs longer than max_size are split at sentence
    boundaries (hard character split only for a single over-long sentence). Chunks shorter
    than min_size are then merged with a neighbour on the same page when the result fits.
    """
    groups: list[tuple[str | None, str]] = []
    cur: list[str] = []
    cur_heading: str | None = None

    def emit() -> None:
        if cur:
            groups.append((cur_heading, "\n".join(cur)))
            cur.clear()

    for heading, para in _blocks(page.text):
        if heading != cur_heading:
            emit()
            cur_heading = heading
        for piece in (_split_oversized(para, max_size) if len(para) > max_size else [para]):
            if cur and sum(len(c) + 1 for c in cur) + len(piece) > max_size:
                emit()
            cur.append(piece)
    emit()

    return [
        Chunk(
            chunk_id=f"{page.document_id}:p{page.page:03d}:b{idx:03d}",
            document_id=page.document_id, source=page.source, page=page.page, text=text,
            metadata={**_base_meta(page), "chunk_index": idx, "heading": heading},
        )
        for idx, (heading, text) in enumerate(_merge_small(groups, min_size, max_size))
    ]
