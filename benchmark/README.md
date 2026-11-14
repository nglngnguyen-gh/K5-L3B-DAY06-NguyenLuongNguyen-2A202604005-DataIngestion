# Benchmark — WBG Annual Report 2026 (`wbg-ar-2026-v1`)

Questions were written and the dev/test split fixed **before any chunking, embedding or retrieval run**. The SHA-256 of `questions.json` at verification time is stored in `verification.json`; any later change to the test set must be logged here.

## Files

| File | Content |
|---|---|
| `questions.json` | 20 questions with `id, split, type, question, expected_answer, gold_source_id, gold_page, evidence_quote, filter` (+ `alternative_gold` when several pages are valid) |
| `verification.json` | Output of `python -m scripts.verify_benchmark` (run from `starter/`): evidence found on gold page, other pages containing it, filter value check, counts, hash |

## Design

- **Split:** 15 dev / 5 test, fixed in advance. Test questions come from pages 9, 24, 27, 39, 43 and cover all 4 question types.
- **Types:** direct 8, paraphrase 5, conditional/exception 3, metadata_filter 4.
- **Filter questions (4):** d11 (World Bank (IBRD/IDA)), d12 (IFC), d14 (MIGA), t03 (ICSID, test). Each one is a question whose figure is **ambiguous across institutions** (bonds, commitments, guarantees, "cases"). The filter value is a **user-context input assumed given before retrieval** ("user is reading chapter X"), not derived from the gold answer. Values come from the printed table of contents (`section` metadata).
- **Gold pages** are physical PDF pages (1-based), matching `data/manifest.json`. Evidence is compared after the same normalization as ingestion, ignoring whitespace differences.
- **Several valid sources:** d14 (p38 or p39), t02 (p27, p29 or p30). Any listed page counts as a hit if the chunk contains that page's evidence.

## Selection rule (declared before test)

Highest dev Evidence Hit@3 → ties broken by dev Hit@1 → mean grounding on dev spot-checks → fewer chunks / lower ingest time. Test is run once, after the configuration is fixed.

## Known risks / limitations

- **Leakage:** dev and test share no primary gold page, but d14's alternative gold page 39 is also t04's gold page (different facts: new guarantees vs. reinsurance). Chapter-level overlap exists (MIGA: d14/t04; ICSID: d15/t03; World Bank: d11/t02) because the corpus is a single report.
- **Single author:** questions, gold and later manual labels are written by the student (with AI drafting help, then checked against the PDF) — risk of bias toward phrasing found in the text.
- **Extraction order:** some spreads interleave sidebar text with body text (e.g. p43, p23); evidence was chosen from contiguous sentences, but chunks may still split them.
- Several evidence quotes are long (d04, d07, t02) and may be split by fixed-size chunking; this is intentional to expose chunk-boundary errors.
- Small sample (5 test questions): results illustrate this corpus only, not a general ranking of strategies.
