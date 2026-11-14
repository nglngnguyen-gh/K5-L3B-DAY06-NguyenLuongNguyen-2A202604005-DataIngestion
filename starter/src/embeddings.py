"""Gemini embedding adapter. Fails loudly; never falls back to mock vectors."""
from __future__ import annotations

import math
import os
import time
from typing import Protocol

from google import genai
from google.genai import errors, types


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed source chunks."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Embed one question in the same vector space as documents."""
        ...


def _l2_normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    if n == 0:
        raise ValueError("zero-norm embedding returned by provider")
    return [x / n for x in v]


class GeminiEmbedder:
    """gemini-embedding-001 via google-genai.

    Documents use task_type RETRIEVAL_DOCUMENT, queries RETRIEVAL_QUERY. Output is truncated
    (Matryoshka) to `dimensions` and L2-normalized, as recommended for non-default sizes.
    """

    def __init__(self, model_name: str = "gemini-embedding-001", dimensions: int = 768,
                 batch_size: int = 50, max_retries: int = 6) -> None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set (starter/.env)")
        self.client = genai.Client(api_key=key)
        self.model_name = model_name
        self.dimensions = dimensions
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.api_calls = 0
        self.texts_embedded = 0
        self.chars_embedded = 0

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            for attempt in range(self.max_retries):
                try:
                    resp = self.client.models.embed_content(
                        model=self.model_name,
                        contents=batch,
                        config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dimensions),
                    )
                    break
                except errors.APIError as exc:
                    retriable = getattr(exc, "code", None) in (429, 500, 503)
                    if not retriable or attempt == self.max_retries - 1:
                        raise RuntimeError(f"Gemini embedding failed: {exc}") from exc
                    time.sleep(min(60, 2 ** attempt * 2))
            self.api_calls += 1
            vecs = [e.values for e in resp.embeddings]
            if len(vecs) != len(batch) or any(len(v) != self.dimensions for v in vecs):
                raise RuntimeError("Gemini returned unexpected embedding count/dimensions")
            out.extend(_l2_normalize(list(v)) for v in vecs)
            self.texts_embedded += len(batch)
            self.chars_embedded += sum(len(t) for t in batch)
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, question: str) -> list[float]:
        return self._embed([question], "RETRIEVAL_QUERY")[0]
