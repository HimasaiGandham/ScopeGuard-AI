# Project work record

Last updated: 1 November 2026 (India Standard Time)

This is the running record for the DataOps Innovation Hackathon PS2 project. It records completed work, decisions, checks, limitations, and the next phase. Update it whenever a phase changes or a material implementation decision is made. Detailed reports for the team can be prepared from this record, the repository history, and the resulting artifacts.

## Current snapshot

| Item | State |
| --- | --- |
| Selected challenge | PS2: AI-Powered Document Forensics and Contextual Intelligence System |
| Active branch | `feature/foundation` |
| Latest implementation commit before this record | `d9a7433` — Establish PS2 evidence and case models |
| Foundation phase 1: sample inventory | Complete |
| Foundation phase 2: shared data format | Complete |
| Foundation phase 3: safe local file tracking | Next |
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

## Remaining foundation phases

### Phase 3 — track sample files safely

- Build a local A01 case manifest containing stable document IDs, filenames, page counts, and SHA-256 hashes.
- Keep source PDFs unchanged and outside Git.
- Keep the answer key separate from runtime input.
- Verify that a case can identify exactly which files it used.

### Phase 4 — define processing contracts

- Specify common inputs, outputs, statuses, and errors for ingestion, OCR, visual analysis, contextual comparison, and dossier generation.
- Record processing and review activity as audit events.
- Check that the planned modules can exchange the shared case, field, finding, and evidence records.

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
