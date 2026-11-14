"""PostgreSQL + pgvector store: chunks per strategy, embedding cache, cosine search with SQL filter."""
from __future__ import annotations

import hashlib
import json
from typing import Any

import psycopg

from .models import Chunk


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in v) + "]"


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.database_url = database_url
        self.dimensions = dimensions
        self.conn = psycopg.connect(database_url, autocommit=True)

    def create_schema(self) -> None:
        d = self.dimensions
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS chunks (
                    strategy        text        NOT NULL,
                    chunk_id        text        NOT NULL,
                    document_id     text        NOT NULL,
                    source          text        NOT NULL,
                    page            int         NOT NULL,
                    printed_pages   int[]       NOT NULL DEFAULT '{{}}',
                    sections        text[]      NOT NULL DEFAULT '{{}}',
                    heading         text,
                    chunk_index     int         NOT NULL,
                    text            text        NOT NULL,
                    n_chars         int         NOT NULL,
                    content_hash    text        NOT NULL,
                    embedding_model text        NOT NULL,
                    embedding       vector({d}) NOT NULL,
                    metadata        jsonb       NOT NULL DEFAULT '{{}}',
                    updated_at      timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (strategy, chunk_id)
                )""")
            cur.execute("CREATE INDEX IF NOT EXISTS chunks_sections_gin ON chunks USING gin (sections)")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS embedding_cache (
                    model      text NOT NULL,
                    dims       int  NOT NULL,
                    task_type  text NOT NULL,
                    text_hash  text NOT NULL,
                    embedding  vector({d}) NOT NULL,
                    PRIMARY KEY (model, dims, task_type, text_hash)
                )""")
            # Check the existing column matches the model dimension.
            cur.execute("""SELECT format_type(atttypid, atttypmod) FROM pg_attribute
                           WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'""")
            col = cur.fetchone()[0]
            if col != f"vector({d})":
                raise RuntimeError(f"chunks.embedding is {col}, expected vector({d}); migrate or use another table")

    # ---- embedding cache (avoids paying twice for identical text) ----
    def cached_embeddings(self, model: str, task_type: str, texts: list[str]) -> dict[str, list[float]]:
        hashes = list({text_hash(t) for t in texts})
        if not hashes:
            return {}
        with self.conn.cursor() as cur:
            cur.execute("""SELECT text_hash, embedding::text FROM embedding_cache
                           WHERE model=%s AND dims=%s AND task_type=%s AND text_hash = ANY(%s)""",
                        (model, self.dimensions, task_type, hashes))
            return {h: json.loads(v) for h, v in cur.fetchall()}

    def put_cache(self, model: str, task_type: str, texts: list[str], vectors: list[list[float]]) -> None:
        with self.conn.cursor() as cur:
            cur.executemany("""INSERT INTO embedding_cache (model, dims, task_type, text_hash, embedding)
                               VALUES (%s, %s, %s, %s, %s::vector) ON CONFLICT DO NOTHING""",
                            [(model, self.dimensions, task_type, text_hash(t), _vec(v)) for t, v in zip(texts, vectors)])

    # ---- chunks ----
    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]], model: str) -> dict[str, int]:
        """Idempotent write: stable IDs, update only changed content, delete stale chunks of re-ingested docs."""
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors length mismatch")
        if any(len(v) != self.dimensions for v in vectors):
            raise ValueError("vector dimension mismatch")
        ids = [c.chunk_id for c in chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate chunk ids in input")
        stats = {"inserted": 0, "updated": 0, "unchanged": 0, "deleted": 0}
        with self.conn.transaction(), self.conn.cursor() as cur:
            for c, v in zip(chunks, vectors):
                h = text_hash(c.text)
                extra = {k: v2 for k, v2 in c.metadata.items() if k not in ("sections", "printed_pages", "heading", "chunk_index")}
                cur.execute("""
                    INSERT INTO chunks (strategy, chunk_id, document_id, source, page, printed_pages, sections, heading,
                                        chunk_index, text, n_chars, content_hash, embedding_model, embedding, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector,%s)
                    ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                        document_id=EXCLUDED.document_id, source=EXCLUDED.source, page=EXCLUDED.page,
                        printed_pages=EXCLUDED.printed_pages, sections=EXCLUDED.sections, heading=EXCLUDED.heading,
                        chunk_index=EXCLUDED.chunk_index, text=EXCLUDED.text, n_chars=EXCLUDED.n_chars,
                        content_hash=EXCLUDED.content_hash, embedding_model=EXCLUDED.embedding_model,
                        embedding=EXCLUDED.embedding, metadata=EXCLUDED.metadata, updated_at=now()
                    WHERE chunks.content_hash IS DISTINCT FROM EXCLUDED.content_hash
                       OR chunks.embedding_model IS DISTINCT FROM EXCLUDED.embedding_model
                       OR chunks.sections IS DISTINCT FROM EXCLUDED.sections
                    RETURNING (xmax = 0) AS inserted""",
                    (strategy, c.chunk_id, c.document_id, c.source, c.page, c.metadata.get("printed_pages", []),
                     c.metadata.get("sections", []), c.metadata.get("heading"), c.metadata.get("chunk_index", 0),
                     c.text, len(c.text), h, model, _vec(v), json.dumps(extra)))
                row = cur.fetchone()
                if row is None:
                    stats["unchanged"] += 1
                elif row[0]:
                    stats["inserted"] += 1
                else:
                    stats["updated"] += 1
            docs = sorted({c.document_id for c in chunks})
            cur.execute("""DELETE FROM chunks WHERE strategy=%s AND document_id = ANY(%s) AND NOT (chunk_id = ANY(%s))""",
                        (strategy, docs, ids))
            stats["deleted"] = cur.rowcount
        return stats

    def count(self, strategy: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM chunks WHERE strategy=%s", (strategy,))
            return cur.fetchone()[0]

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Exact cosine search (no ANN index), filter applied in SQL before ranking.

        Supported filters: {"section": "<value>"} (matches if value in sections), {"page": int}.
        """
        if len(query_vector) != self.dimensions:
            raise ValueError("query vector dimension mismatch")
        where, params = ["strategy = %s"], [strategy]
        for key, value in (filters or {}).items():
            if key == "section":
                where.append("%s = ANY(sections)")
            elif key == "page":
                where.append("page = %s")
            else:
                raise ValueError(f"unsupported filter: {key}")
            params.append(value)
        q = _vec(query_vector)
        sql = f"""SELECT chunk_id, document_id, source, page, printed_pages, sections, heading, chunk_index, text,
                         1 - (embedding <=> %s::vector) AS score
                  FROM chunks WHERE {' AND '.join(where)}
                  ORDER BY embedding <=> %s::vector, chunk_id LIMIT %s"""
        with self.conn.cursor() as cur:
            cur.execute(sql, [q, *params, q, top_k])
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
