# Manual audit — method and status

**Status: reviewed.** An AI assistant (Claude Opus 5.5, `labeler` column) drafted the labels. The student (Nguyễn Lương Nguyên, `reviewed_by` column) then re-checked every row against the PDF. Outcome: all 45 scores were confirmed unchanged. The reasons for pos01 and pos02 (3 rows each) were rewritten to describe the pypdf reading-order errors found during review; the earlier pos02 reason ("continues after an interleaved heading") was wrong. The same person/tool labelled all strategies, so there is a risk of bias, especially because the labeller knew which strategy each chunk came from.

| File | What | Sample (fixed before scoring) |
|---|---|---|
| `coherence_sample.json` | Positions and the chunk that covers each one, per strategy | First 10 counted pages in sorted order (p3, 4, 5, 6, 7, 9, 10, 11, 12, 13). Position = 40-char snippet that starts at the first word boundary after the midpoint of the normalized page text. Chunk = first chunk containing the snippet. |
| `coherence_labels.csv` | 0–2 score + reason per position × strategy | 10 × 3 |
| `grounding_labels.csv` | 0–2 score + reason per test question × strategy (top-3 taken together) | 5 test × 3 |
| `metadata_autocheck.json`, `metadata_audit.csv` | source / page / sections / printed_pages correct? | 5 test × top-3 × 3 = 45 records |

## Scales

- **Coherence:** 0 = the position is cut mid-idea or the subject is missing, so the passage cannot be understood; 1 = understandable, but the chunk starts or ends mid-word/mid-sentence, or loses a referent or list context; 2 = self-contained, with sentence boundaries intact around the position.
- **Grounding (retrieved evidence only, NOT LLM answer accuracy):** 0 = no evidence in the top-3; 1 = evidence present but missing a needed condition or context; 2 = enough to answer every part of the question and trace it to source/page.
- **Metadata:** a record is correct if `source` is the manifest path, the chunk text appears verbatim in the re-extracted text of the stated PDF page, and `sections`/`printed_pages` match the manifest's table-of-contents mapping. This is automated; the student should spot-check a few records in the PDF.

## C vs B

C reuses B's chunks and vectors. Coherence labels are therefore identical, and grounding differs only where a filter changed the top-3. On test, the only filter question (t03) had the same top-3 with and without the filter.
