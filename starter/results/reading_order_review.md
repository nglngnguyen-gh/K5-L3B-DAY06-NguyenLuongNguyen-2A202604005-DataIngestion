# Reading-order review of pypdf extraction

Found while auditing coherence pos01 (PDF p3). This review was run **after** the test run. It changes nothing in the pipeline or in the reported metrics; it only documents an extraction limitation.

**Method.** `python -m scripts.check_reading_order` (run from `starter/`) walks pypdf's text segments (≥ 25 chars, running footers excluded) in stream order with their (x, y). It flags a jump to a higher position in the same column, a jump back to a column on the left, and a jump from the right-hand page of a spread back to the left-hand page. The script reports every flag in `reading_order_check.json`. Each flag below was then checked by hand against the normalized text.

**Result.** 19 of 41 counted pages have at least one flag. By hand they fall into three types.

## Type 1: a sentence is cut, and its second half appears elsewhere (content damage). 8 pages, 11 breaks

Found in two passes. Pass 1 used the position flags. Pass 2 searched every counted page for a line that starts in lower case right after a finished sentence or an ALL-CAPS heading, then excluded footnote letters, wrapped URLs and infographic labels by hand. Pass 2 found the p4, p5, p23 (second), p27 and p43 breaks: the position scan had put p4 under Type 2 and had not flagged p27 at all.

| PDF page | Broken text in the normalized output | Where the continuation appears |
|---|---|---|
| 4 | "In line with the parallel consolidation of the Environmental and Social \| LETTER FROM THE EXECUTIVE DIRECTORS Seated (left to right)…" | "function, this critical milestone strengthens institutional accountability…" about 2,000 chars later, after the letter's opening paragraph |
| 5 | "…LETTER FROM THE PRESIDENT \| provided electricity to 59 million people…" | the start of this sentence is in another text frame |
| 21 | "…engagement platforms for civil society, faith-based, and think tank \| Partnerships are essential…" | "partners, including a monthly storytelling initiative…" later on the page |
| 21 | "…Two projects are being \| The World Bank's ESF applies…" | later on the page |
| 23 | "People affected by … these projects can raise their \| problem-solving approach." | "concerns with CAO, which reports directly…" about 1,000 chars later |
| 23 | "…the institutions' clients using a neutral, collaborative, \| investigation of the Requests for Inspection…" | elsewhere on the page |
| 23 | "Executive Directors consider and decide on IBRD loans, IDA \| For more information, visit … directors." | "credits and grants, IFC investments, MIGA guarantees…" right after the sidebar URL |
| 24 | "GIA continued to advance its Country Assurance and Advisory Program, \| For more information…" | "notably through engagements in Afghanistan and Sierra Leone" about 7,000 chars later |
| 27 | "…it provides loans, guarantees, risk-management products, and advisory \| TABLE 3: IBRD NET COMMITMENTS BY REGION…" | "services to middle-income and creditworthy low-income countries…" after Table 3 and its footnotes (about 1,000 chars) |
| 32 | "…harmonize our procurement policies and systems, and \| For more information…" | "to date, we have signed Procurement Mutual Reliance Frameworks…" at the end of the page |
| 43 | "…UNCITRAL toolkits. BUILDING CAPACITY IN MEDIATION AND AMICABLE SETTLEMENT \| as a flexible and efficient approach…" | the start of this sentence is in another text frame |

Cause: text frames that flow across columns or around sidebars and boxes are stored in the content stream out of visual order. Chunks covering these spots join unrelated sentences. Every strategy is affected, because all of them chunk the same extracted text.

## Type 2: whole blocks out of order, sentences intact. Pages 3, 4, 5, 7, 15, 16, 17, 35, 37 (p4 and p5 also have Type 1 breaks)

Examples: p3, where the institutions list comes before the mission statement, so "To achieve this" loses its referent; p4, where the opening "Against a backdrop of repeated shocks…" of the Executive Directors' letter appears after the list of directors' names; p5, where the President's letter title appears after the signature; p16 and p17, where infographic labels and numbers are separated. Meaning inside each block is preserved, but chunks can mix neighbouring blocks.

## Type 3: heading extracted after its body. Pages 7, 19, 22, 23, 30, 39, 42, 43

This affects B and C, because `by_paragraph` attaches a heading to the text that **follows** it:
- p43: chunk `b002` gets the heading "BUILDING CAPACITY IN MEDIATION AND AMICABLE SETTLEMENT", but its text is the Paris-office passage. Chunks `b000` and `b001`, which really belong under that heading, have no heading.
- p42: "MEMBERSHIP UPDATES AND BENEFITS" is extracted after the membership text and merged with the next heading ("REACHING FURTHER, WORKING CLOSER"). The membership chunks (`b004`, `b005`) carry only "ICSID".

So the `heading` metadata is unreliable on these pages. It is not used for filtering; the filter uses `sections`, which comes from page numbers and is not affected.

## Impact on reported results

- The benchmark evidence for all 20 questions was verified verbatim, and none of it sits inside a Type 1 break. Hit@1 and Hit@3 are therefore not directly affected. The benchmark is blind to this error class, because no question targets a broken passage.
- Gold pages with flags: 7 (d03, d04), 19 (d10), 24 (t05), 27 (t02), 30 (t02 alt), 32 (d12), 39 (d14 alt, t04), 42 (d15), 43 (t03). All were still hits at rank ≤ 3 for every strategy.
- Coherence sample: pos01 (p3) is Type 2, and pos02 (p4) ends exactly at a Type 1 break, so no chunk can hold the full sentence. Both are annotated in `audit/coherence_labels.csv`. The other 8 sampled chunks do not overlap any flagged spot. pos03 is on p5, but its chunk (chars ~2100–2950) lies outside both p5 issues.

## Possible fix (not applied)

Extract in visual order with a layout-aware reader, for example PyMuPDF text blocks sorted by column, or pdfplumber with column detection. Then check the result per page with this script. Applying the fix now would change the corpus after the test run, so it would have to be reported as a post-hoc experiment, not as a held-out result.
