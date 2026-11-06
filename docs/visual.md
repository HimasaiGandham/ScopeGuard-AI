# Visual ink-overlap inspection

## Run the check

Start the server using the [setup guide](setup.md). Upload a packet at `/ingest`, then choose **Inspect visual marks** and click **Inspect this case**. OCR is not a prerequisite. The screen lists document/page statuses, errors, observation counts, and review leads. A page with zero observations is not declared authentic or unaltered.

Select **Inspect highlighted source and crop** to see the original page, red source rectangle, and original pixels cropped from that region. Use the page-size slider to inspect the alignment. The case/document ID, 1-based page, normalized region, source SHA-256, method, and raw signal counts are retained in the saved report. **View saved visual report** opens the result record.

## Supported signal

Method `blue_ink_near_dark_content_v1` detects sufficiently large blue-ink components near dark content. It is a deterministic color/geometry heuristic, not a trained forgery classifier.

1. PDF pages render in their displayed orientation at 144 dpi; image EXIF orientation is applied. Rendering is capped at 25 million pixels.
2. Analysis scales down, without upscaling, to fit 1200 by 1700 pixels while preserving aspect ratio. Original/display coordinates are linked through normalized rectangles.
3. Blue candidates satisfy B−R > 35, B−G > 20, B > 90, R < 180, and G < 180. Dark pixels have all channels below 110.
4. A five-pixel dilation groups nearby blue pixels. Candidate bounds are then reduced to the actual blue pixels.
5. A candidate needs a long side of at least 25 pixels, short side of at least seven pixels, at least 40 blue pixels, density of at least 0.015, and at least eight dark pixels within its three-pixel blue neighborhood.

These thresholds refer to the analysis image. They suppress thin isolated underlines and blue writing separated from dark content in the tested controls. They can still flag authorized corrections, stamps, annotations, overlapping colored print, or scan artifacts. Pixel counts describe the observed signal; they are not probabilities.

## Evidence and uncertainty

Each observation uses the shared visual Finding/EvidenceRef/SourceRegion models and remains pending human review. Finding confidence is `null`, with an explicit uncalibrated-confidence note and possible benign explanations. It makes no determination about authenticity, alteration, intent, or fraud.

Normalized coordinates refer to the displayed page after PDF rotation/crop or image orientation. Page rendering and cropping use the same orientation. Evidence assets are rendered on demand from verified original bytes; size/hash checks and the report's source fingerprint must match. Changed or missing originals block evidence display instead of showing another source. Page highlights and crops are derived assets; originals are never saved by the renderer.

## Measured coverage and misses

Blind inspection of the supplied 15 PDFs completed before a separate local evaluator read labels. All original hashes were unchanged. A localized detection means the predicted region center fell inside the labelled edited field; this is not a pixel-perfect segmentation metric.

| Supplied subset | Pages | Pages with a localized observation | Misses / false alarms |
| --- | --- | --- | --- |
| Blue scribbled alterations | 5 | 5 | 0 localized misses |
| Digital edits | 5 | 0 | 5 misses; outside the signal's demonstrated coverage |
| Unmodified controls | 5 | 0 observations | 0 observed false alarms |

The five scribbled pages each produced one observation in the affected field. These small, controlled results do not establish real-world sensitivity or specificity. The algorithm was scoped to blue-overprinted marks; it was not fitted using runtime labels or expected regions. Ordinary isolated blue text/underlines and clean generated controls also produced no observations in tests. Authorized blue marks that overlap print may still trigger a lead.

Black-ink changes, invisible digital substitutions, grayscale documents, fonts, spacing, signatures, image compositing, arbitrary colors, and determining whether a correction is authorized are unsupported. Existing contextual comparisons can help expose readable value discrepancies, but do not turn this visual heuristic into a complete alteration detector. Low-resolution scans, compression/color artifacts, and unusual lighting may cause misses or false leads.

## Processing and storage

Each page runs in a separate worker with a 30-second timeout. Failures are recorded, and other documents continue. Each run inspects at most 100 pages; remaining pages receive explicit failures. Each page returns at most 50 observations with a potential-truncation warning at the cap. Original identities are checked before and after each document; results from a changed document are discarded. Rejected uploads remain visible.

Saved reports use new run IDs and exclusive writes under the external case folder's `visual` directory. Case records, earlier runs, and original documents are not replaced. A saved report is a historical observation; source evidence is reverified when requested. Records and manifests are not digitally signed. No answer key, filename label, or known edit coordinates enter the detector.

## Local API and checks

- `POST /api/ingestion/cases/{case_id}/visual` runs inspection under the normal local POST header/origin controls.
- `GET /api/ingestion/cases/{case_id}/visual/{run_id}` retrieves a saved report.
- `GET /api/ingestion/cases/{case_id}/visual/{run_id}/evidence/{finding_id}/page` returns its verified source rendering; replace `page` with `crop` for the original-pixel crop.

The screen route is `/visual?case=<case_id>`. Run the full test suite from the setup guide. Tests cover localized overprint, clean and ordinary-mark controls, unsupported black edits, rotated PDF coordinates, timeout/missing-source isolation, request authorization, exclusive reports, crop rendering, changed-source rejection, and answer-key isolation. Browser checks verify source/crop display and highlight alignment across page sizes and narrow/wide windows. Generated reports, sample PDFs, screenshots, evaluation labels, and internal work records remain local.
