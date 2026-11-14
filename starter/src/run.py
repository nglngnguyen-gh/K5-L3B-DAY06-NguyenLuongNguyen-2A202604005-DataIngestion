"""Day 06 pipeline entry point (run from starter/).

  python -m src.run ingest                     # chunk A/B, embed (Gemini), upsert A/B/C into pgvector
  python -m src.run search "question" [--strategy B] [--section IFC]   # ad-hoc top-3 check
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import GeminiEmbedder
from .ingestion import load_corpus
from .store import PgVectorStore, text_hash

STARTER = Path(__file__).resolve().parents[1]
REPO = STARTER.parent
RESULTS = STARTER / "results"
MANIFEST = REPO / "data" / "manifest.json"

EMBEDDING_DIMS = 768
STRATEGIES = {
    "A": {"chunking": "fixed_size", "size": 800, "overlap": 100, "use_filter": False,
          "hypothesis": "Baseline: fixed windows ignore sentence/heading boundaries; more evidence cut mid-sentence."},
    "B": {"chunking": "by_paragraph", "max_size": 800, "min_size": 200, "use_filter": False,
          "hypothesis": "Same size budget as A but paragraph/heading boundaries -> more coherent chunks, higher Hit@1."},
    "C": {"chunking": "by_paragraph", "max_size": 800, "min_size": 200, "use_filter": True,
          "hypothesis": "B + section filter (only for questions that provide one) removes cross-institution confusions."},
}


def build_chunks(pages, cfg):
    if cfg["chunking"] == "fixed_size":
        return [c for p in pages for c in fixed_size(p, cfg["size"], cfg["overlap"])]
    return [c for p in pages for c in by_paragraph(p, cfg["max_size"], cfg["min_size"])]


def length_stats(chunks):
    L = [len(c.text) for c in chunks]
    q = statistics.quantiles(L, n=10)
    return {"chunks": len(L), "total_chars": sum(L), "approx_tokens": round(sum(L) / 4),
            "min": min(L), "p10": round(q[0]), "median": statistics.median(L), "mean": round(statistics.mean(L)),
            "p90": round(q[-1]), "max": max(L)}


def embed_with_cache(store, embedder, texts):
    """Return vectors for texts; only texts missing from the DB cache are sent to the API."""
    cached = store.cached_embeddings(embedder.model_name, "RETRIEVAL_DOCUMENT", texts)
    missing = list(dict.fromkeys(t for t in texts if text_hash(t) not in cached))
    if missing:
        vecs = embedder.embed_documents(missing)
        store.put_cache(embedder.model_name, "RETRIEVAL_DOCUMENT", missing, vecs)
        cached.update({text_hash(t): v for t, v in zip(missing, vecs)})
    return [cached[text_hash(t)] for t in texts], len(missing)


def cmd_ingest(_args) -> None:
    model = os.environ.get("EMBEDDING_MODEL") or "gemini-embedding-001"
    store = PgVectorStore(os.environ["DATABASE_URL"], EMBEDDING_DIMS)
    store.create_schema()
    embedder = GeminiEmbedder(model, EMBEDDING_DIMS)

    t0 = time.perf_counter()
    pages = load_corpus(MANIFEST, REPO)
    load_s = time.perf_counter() - t0

    run = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "embedding_model": model,
           "dimensions": EMBEDDING_DIMS, "pages": len(pages), "load_seconds": round(load_s, 2), "strategies": {}}
    chunk_cache = {}
    for name, cfg in STRATEGIES.items():
        key = json.dumps({k: v for k, v in cfg.items() if k not in ("use_filter", "hypothesis")}, sort_keys=True)
        t = time.perf_counter()
        chunks = chunk_cache.setdefault(key, build_chunks(pages, cfg))
        chunk_s = time.perf_counter() - t
        t = time.perf_counter()
        calls_before = embedder.api_calls
        vectors, newly_embedded = embed_with_cache(store, embedder, [c.text for c in chunks])
        embed_s = time.perf_counter() - t
        t = time.perf_counter()
        upsert = store.upsert(name, chunks, vectors, model)
        db_s = time.perf_counter() - t
        run["strategies"][name] = {
            "config": cfg, **length_stats(chunks),
            "texts_sent_to_api": newly_embedded, "api_calls": embedder.api_calls - calls_before,
            "seconds": {"chunk": round(chunk_s, 3), "embed": round(embed_s, 2), "db": round(db_s, 2)},
            "upsert": upsert, "rows_in_db": store.count(name),
        }
        print(f"{name}: {len(chunks)} chunks | sent to API {newly_embedded} | upsert {upsert} | rows {store.count(name)}")

    run["api_totals"] = {"calls": embedder.api_calls, "texts": embedder.texts_embedded, "chars": embedder.chars_embedded,
                         "approx_tokens": round(embedder.chars_embedded / 4)}
    RESULTS.mkdir(exist_ok=True)
    with (RESULTS / "ingest_runs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(run, ensure_ascii=False) + "\n")
    (RESULTS / "strategies.json").write_text(json.dumps(
        {"embedding": {"provider": "Google Gemini API (google-genai)", "model": model, "dimensions": EMBEDDING_DIMS,
                       "document_task_type": "RETRIEVAL_DOCUMENT", "query_task_type": "RETRIEVAL_QUERY",
                       "normalization": "L2 after truncation"},
         "vector_store": {"engine": "PostgreSQL 16 + pgvector 0.8.7", "table": "chunks", "metric": "cosine (<=>)",
                          "search": "exact (sequential scan, no ANN index)"},
         "strategies": STRATEGIES}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("API totals:", run["api_totals"])


def cmd_search(args) -> None:
    model = os.environ.get("EMBEDDING_MODEL") or "gemini-embedding-001"
    store = PgVectorStore(os.environ["DATABASE_URL"], EMBEDDING_DIMS)
    embedder = GeminiEmbedder(model, EMBEDDING_DIMS)
    filters = {"section": args.section} if args.section else None
    for hit in store.search(args.strategy, embedder.embed_query(args.query), 3, filters):
        print(f"{hit['score']:.4f} {hit['chunk_id']} p{hit['page']} {hit['sections']}\n   {hit['text'][:200]!r}")


def main() -> None:
    load_dotenv(STARTER / ".env")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest")
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--strategy", default="B")
    s.add_argument("--section")
    args = ap.parse_args()
    {"ingest": cmd_ingest, "search": cmd_search}[args.cmd](args)


if __name__ == "__main__":
    main()
