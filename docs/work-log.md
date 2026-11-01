# Project work record

Last updated: 1 November 2026 (India Standard Time)

This is the running record for the DataOps Innovation Hackathon PS2 project. It records completed work, decisions, checks, limitations, and the next phase. Update it whenever a phase changes or a material implementation decision is made. Detailed reports for the team can be prepared from this record, the repository history, and the resulting artifacts.

## Current snapshot

| Item | State |
| --- | --- |
| Selected challenge | PS2: AI-Powered Document Forensics and Contextual Intelligence System |
| Active branch | `feature/foundation` |
| Branch history | See `git log` for the current commit and phase history |
| Foundation phase 1: sample inventory | Complete |
| Foundation phase 2: shared data format | Complete |
| Foundation phase 3: safe local file tracking | Complete |
| Foundation phase 4: processing contracts | Complete |
| Foundation phase 5: evidence tracing demonstration | Next |
| Application, OCR, visual analysis, reviewer interface, and dossier | Not implemented yet |
| Public dataset upload | None |
| Merge into `main` | Not started |

## Foundation phase 1 — understand the sample set

**Completed:** Inventoried the local dataset. It contains 15 one-page PDF files, each containing a page image without selectable text. A separate local `ground_truth.csv` provides five groups of three: one labelled unmodified variant and two altered variants per group. Group A01, consisting of `sample_001.pdf` through `sample_003.pdf`, was selected as the first development example.

**Decision:** Keep the PDFs and answer key outside Git. The detection pipeline must not read the answer key. Labels are for evaluation only, after the system produces findings.

**Limit:** Each group consists of variants of one document template. This is useful for OCR and alteration checks, but a later demonstration needs related, different document types to show broader cross-document contextual reasoning.

## Foundation phase 2 — define the shared data format

**Completed:** Added framework-independent Python models in `docforensics/models.py` for:

- An investigation case and its documents.
- Extracted fields with optional confidence and source evidence.
- Findings with categories, observations, explanations, evidence, confidence, and review state.
- Audit events for processing and reviewer activity.
- A source region with a 1-based page number and normalized page coordinates.

**Validation:** Case creation rejects duplicate IDs, evidence pointing to an absent document, and evidence pointing beyond a known page count. Findings require at least one evidence reference. Regions reject invalid coordinates. A helper converts pixel bounding boxes into normalized page coordinates.

**Design choice:** A finding is a lead for human review. Its review state does not declare fraud or document authenticity. OCR results and AI explanations must remain tied to observed source evidence.

**Checks run:** `python -m unittest discover -s tests -v` passed five tests. `git diff --check` reported no whitespace errors. The foundation code and architecture were pushed to `feature/foundation` as commit `d9a7433`.

**Documentation:** `docs/architecture.md` contains the intended processing flow, shared records, coordinate convention, and local data handling approach. The README accurately says that the application itself is not built yet.

## Foundation phase 3 — track sample files safely

**Completed:** Added `docforensics/manifest.py`, a reusable command to create and verify a local case manifest. Created an A01 manifest outside Git for `sample_001.pdf`, `sample_002.pdf`, and `sample_003.pdf`. The three stable IDs are `A01-D01`, `A01-D02`, and `A01-D03`. Each entry records the original filename, one-page count, byte size, and SHA-256 digest. The source folder is also recorded so the case can locate the exact input files.

**Integrity check:** Recorded SHA-256 values for the three PDFs before running the tool and compared them afterward; all were unchanged. The `verify` command independently rechecked all three files against the local manifest and succeeded.

**Separation check:** The tool accepts an explicit list of PDF filenames and does not read `ground_truth.csv`. The answer key and PDFs remain outside Git. The manifest writer rejects an output path inside this project checkout and refuses to overwrite an existing manifest. The source directory must also be outside the checkout.

**Checks run:** `python -m unittest discover -s tests -v` passed the model and manifest checks. The manifest tests cover unchanged-file verification, a changed-file failure, separation from the answer key, and path safeguards. The tested PDF dependency is recorded in `requirements.txt`.

**User verification (1 November 2026, India Standard Time):** The user ran the test command in PowerShell and reported `Ran 10 tests` followed by `OK`. They also ran the manifest verification command and received `Verified A01: 3 unchanged PDFs`, then inspected the generated JSON containing the three document IDs, filenames, page counts, sizes, and hashes.

**Documentation:** `docs/local-manifest.md` contains the exact create and verify commands and explains the manifest fields. The local generated file is `../output/pdf/ocr_assignment_dataset/manifests/A01.json` relative to the repository root; it is not committed.

**Limit:** This phase identifies and preserves the sample inputs. It does not extract text or decide which PDF is altered.

## Foundation phases 1–3 audit

On 1 November 2026, reviewed the completed work and corrected model validation and manifest verification gaps. The expanded suite passed 19 tests; compilation and the real A01 verification also passed. The dataset inventory matched all 15 PDFs to 15 answer-key rows and five groups of three. The findings, fixes, test results, and remaining limits are recorded in [the detailed audit](foundation-audit.md). At that audit, foundation phase 4 was next.

## Foundation phase 4 — define processing contracts

**Completed on 1 November 2026:** Added `docforensics/processing.py` with six steps, five progress states, shared request/output records, typed errors and warnings, human-review decisions, and a synchronous coordinator. Adapters receive the current case, eligible document IDs, and earlier step records. Outputs use the existing document, field, finding, and source-reference models. Classification can update the document type while preserving verified source identity.

**Failure behaviour:** Ingestion failures skip only the affected document's OCR and visual steps. OCR failures leave visual checks available, and contextual comparison receives only documents whose OCR completed. Partial analysis produces a warning. Missing or waiting human review leaves the dossier pending. Invalid outputs are rejected before being added to the case. Known errors carry safe codes, messages, retry flags, and optional page locations; unexpected exception text is not exposed.

**Practice command:** Added `docforensics/practice.py`. Its simulated adapters first verify the local source manifest, then exercise success, a single-document OCR timeout, or waiting human review. Every console run and JSON snapshot identifies practice mode. No source values, findings, actual human decisions, or dossiers are fabricated by the practice adapters, and the answer key is not read.

**Checks:** The full suite passed 36 tests and Python compilation passed. Actual A01 practice runs verified the twelve-step success path with 24 audit events; a timeout on A01-D02 with contextual scope limited to A01-D01 and A01-D03; and pending review/dossier states without starting the dossier. A separate guard rejects analysis outputs that attempt to mark their own findings as human-reviewed. The normal manifest verification remains the input prerequisite.

**Local output:** Progress snapshots for all three scenarios were saved outside Git in `../output/pdf/ocr_assignment_dataset/practice/phase4_success.json`, `phase4_ocr-failure.json`, and `phase4_awaiting-review.json`. Each snapshot explicitly records practice mode and no generated dossier. The A01 manifest verification still reports three unchanged PDFs after the runs.

**Documentation:** [Processing contracts and test commands](processing-contracts.md) describes the stage inputs and outputs, statuses, errors, warnings, review handling, history, and manual checks.

**Limits:** The coordinator stores history in memory and runs synchronously. Background jobs, automatic retry, persistent storage, and actual time limits are not implemented here; feature adapters must enforce their I/O time limits. The practice flow checks the coordination contracts rather than performing OCR or forensic analysis.

## Remaining foundation phases

### Phase 5 — prove evidence tracing

- Use an A01 example to link a case to a finding and then to a marked region on its original page.
- Check page-coordinate conversion against the source image dimensions.
- Confirm that the example does not use the answer key to generate a finding.

### Phase 6 — hand off the foundation

- Update setup and architecture instructions.
- Re-run the foundation checks and inspect the files that would be submitted.
- Prepare the branch for review and eventual merge into `main`.

## Reporting convention

For each later phase, add the date, branch, objective, files changed, decisions, checks and results, limitations, and next step. Keep planned work visibly separate from completed work. Do not include sensitive documents, private data, or the evaluation answer key in a public report without confirmed sharing rights.

## Workspace note

An untracked root-level `ps2-requirements.md` is an exact duplicate of the tracked `docs/ps2-requirements.md`. It was left untouched and is not part of the foundation commit.
