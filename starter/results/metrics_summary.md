# Results summary — five dimensions

Corpus: `wbg-ar-2026` (41 counted PDF pages). Embedding: `gemini-embedding-001`, 768d. Store: PostgreSQL 16 + pgvector 0.8.7, exact cosine search. Benchmark: 15 dev / 5 test (`benchmark/questions.json`, sha256 in `benchmark/verification.json`). The strategy was selected on dev and locked in `results/selection.json` (2026-11-14T03:54:16Z, commit 547b93a) **before** the single test run.

Manual labels are **AI drafts pending student review** (see `audit/README.md`).

## 1. Retrieval accuracy (strict: chunk on a gold page containing the full evidence quote)

| Strategy | Dev Hit@1 | Dev Evidence Hit@3 | Test Hit@1 | Test Evidence Hit@3 |
|---|---|---|---|---|
| A fixed 800/100 | **14/15** | 14/15 | 4/5 | 5/5 |
| B paragraph ≤800 | 13/15 | 14/15 | **5/5** | 5/5 |
| C = B + section filter | 13/15 | 14/15 | **5/5** | 5/5 |

- **d02 (all strategies miss):** the gold sentence ($25 billion in guarantees, p6) is never retrieved. Retrieval returns p4 ("surpassed its goal of $20 billion … four years ahead"), which has no $25 billion figure, and p17, where the infographic number is separated from its label by text extraction. This is a genuine miss; p4 would score grounding 1.
- **d01 (B/C rank-1 is not a hit):** p5 ("shortened average project preparation and approval times from 19 months to nine") is equivalent for the main fact but lacks the "low-risk projects in as little as 60 days" condition. Under the strict definition the gold chunk is at rank 2. Lesson: the gold set did not list equivalent statements on other pages, and `verify_benchmark.py` checks only verbatim matches.
- **A t03 Hit@1 miss:** the gold paragraph is rank 3. Ranks 1–2 are other ICSID "case" figures (60 registered cases, 256 sessions).
- The dev and test Hit@1 rankings disagree (A > B on dev by 1 question; B > A on test by 1 question). With n = 15 and n = 5, a one-question difference is within noise.
- No evidence was split across chunk boundaries in any strategy's top-3 (`evidence_split_misses` is empty). A's 100-character overlap was enough for these quotes.

## 2. Chunk coherence (10 fixed positions, 0–2)

| Strategy | Sum | Mean /2 | Distribution |
|---|---|---|---|
| A | 10/20 | 1.0 | 0×0, 10×1, 0×2 |
| B | 18/20 | 1.8 | 0×0, 2×1, 8×2 |
| C | 18/20 | 1.8 | same chunks as B |

A always starts or ends mid-word, but the 100-character overlap meant no sampled position was cut in its own sentence (no 0s). B's two 1s come from a pypdf reading-order break (pos02: the sentence's continuation is extracted about 2,000 characters later, so no chunking can keep it whole) and a three-item list that is split (pos05). pos01 is also on a page whose two text blocks are extracted in reverse visual order. See `reading_order_review.md`: 8 of 41 pages have sentences cut by extraction order, which affects every strategy equally.

## 3. Metadata usefulness

- **Complete and correct:** 45/45 test top-3 records (15 per strategy). `source`, `page`, `sections` and `printed_pages` match the PDF and the manifest.
- **Filter compliance** (questions that provide a filter; for A/B we check whether the unfiltered top-3 happens to stay in the section):

| Strategy | Dev | Test |
|---|---|---|
| A | 1/3 | 1/1 |
| B | 1/3 | 1/1 |
| C | **3/3** | 1/1 |

- **Useful:** `page` + `printed_pages` let every hit be traced to the PDF page and the printed page. With the `section` filter in C, d11 (World Bank) and d12 (IFC) keep the top-3 inside the requested chapter. Without it, B's top-3 included p19 (IBRD/IFC bond figures) for d11, and p5 and p18 (Group-wide private capital) for d12, which are plausible distractors.
- **Limitation:** sections are assigned per page from the table of contents, so boundary spreads carry two sections. Example: p32 is tagged both `World Bank (IBRD/IDA)` and `IFC`, so a World Bank procurement chunk on p32 passes an IFC filter. On this benchmark, the filter never changed whether a question was a hit (filter-question Hit@3 is 3/3 and 1/1 for every strategy). It only cleaned up ranks 2–3.

## 4. Grounding quality (5 test questions, top-3 taken together, 0–2)

| Strategy | 0 | 1 | 2 | Mean /2 |
|---|---|---|---|---|
| A | 0 | 0 | 5 | 2.0 |
| B | 0 | 0 | 5 | 2.0 |
| C | 0 | 0 | 5 | 2.0 |

This is a ceiling effect: the test questions turned out easy for every strategy, so grounding does not separate them. Difference in quality: in A t03 the answer is at rank 3 behind two same-topic distractors, while in B/C it is at rank 1 in a chunk containing exactly the Figure 5 paragraph.

## 5. Data strategy impact and resources

| | A | B | C |
|---|---|---|---|
| Chunks | 276 | 331 | 331 |
| Length min / median / mean / p90 / max (chars) | 102 / 800 / 749 / 800 / 800 | 80 / 578 / 553 / 766 / 800 | same as B |
| Total chars embedded (≈ tokens at 4 chars/token) | 206,659 (≈51.7k) | 182,923 (≈45.7k) | 0 new (vectors reused from B) |
| Document embed API calls / wall time | 6 / 9.5 s | 7 / 10.0 s | 0 / 0.1 s |
| DB upsert | 0.66 s | 0.66 s | 0.78 s |
| Median search latency (dev) | 4.6 ms | 4.5 ms | 4.5 ms |

Query embeddings: 20 calls in total (15 dev + 5 test), cached in `embedding_cache`. A re-ingest made 0 API calls and changed 0 rows (`ingest_runs.jsonl`, run 2). Billing depends on the student's Gemini tier and is to be filled in from Google AI Studio.

- **A → B (chunk boundaries only, same 800-char budget):** coherence improves clearly (1.0 → 1.8). B embeds 12% fewer characters (no overlap) but produces 20% more, shorter chunks. Retrieval accuracy is unchanged within noise (Hit@3 equal; Hit@1 −1 on dev, +1 on test). Trade-off: B's shorter chunks rank precisely (t03), but a paragraph with the wrong scope can outrank the gold one (d01, p5).
- **B → C (filter only):** no change in Hit@1/Hit@3 on this benchmark. Filter compliance on dev rises from 1/3 to 3/3 at no extra cost. C's value is in removing cross-institution distractors from ranks 2–3, which matters most when a downstream LLM reads all three chunks. Its correctness depends on page-level section labels (see p32).
- **Selection:** by the pre-declared rule, A was selected (dev Hit@3 tie → dev Hit@1 14 vs 13). Given the test reversal, the coherence gap, and filter compliance, the evidence does not show that A is better at retrieval. For an LLM consumer, C would be the practical choice, but that judgement was made after seeing test, so it is not a held-out result.
- **Limits:** a single report; 20 questions; one author for questions and labels, with AI drafting; numbers apply only to this corpus.
