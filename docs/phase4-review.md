# Phase 4 requirements review

Reviewed 1 November 2026 on `feature/foundation` against the tracked `docs/ps2-requirements.md`, its identical untracked root copy, and the agreed Phase 4 processing plan.

## Scope and completion

Phase 4 supplies the contracts and practice coordinator that later features will use. Its scoped work is complete: stage inputs and outputs, five statuses, errors and warnings, failure isolation, audit events, human-review waiting, and a repeatable practice flow are implemented and tested. This does not complete the full PS2 prototype; the mandatory feature checkboxes in the requirements file remain open.

## Phase 4 acceptance checks

| Planned Phase 4 work | Implementation and verification |
| --- | --- |
| Define the processing steps and their inputs and outputs | Six stages, `StepRequest`, `StepOutput`, document classification, shared fields and findings, review decisions, report reference; record exchange tested through a complete fixture run |
| Define pending running completed failed and skipped | Status records and UTC audit events; tests cover completion, failures, dependent skips, and pending human review |
| Define clear errors and partial results | Typed errors, retry guidance, optional page location, warnings, unavailable-adapter handling, and safe unexpected-error messages |
| Keep failed inputs from misleading later analysis | Per-document failures are isolated; contextual IDs include only completed OCR; stale processed input is rejected; failed outputs are not applied |
| Preserve human oversight and evidence references | New findings must await review; evidence scope and page references are validated; pending review prevents dossier execution |
| Exercise a practice flow with A01 | Success, OCR timeout, and waiting review scenarios verify the manifest before running and explicitly identify simulation mode |
| Record work and how to test it | Processing guide, work log, regression tests, and local JSON snapshots document the behaviour |

## Bugs reproduced and fixed

1. **Stale analysis on a repeated run:** A case containing earlier fields or findings was accepted, which could mix old results with a newly failed step. The coordinator now requires a fresh case. Tests cover both stale fields and stale findings.
2. **Mutable records:** Lists could be stored in frozen case records or finding evidence, permitting changes after validation. Those collections now require tuples and the expected record types. Source regions and field evidence are also type-checked.
3. **Incorrect finding scope:** A finding labelled within-document could cite multiple documents. It is now rejected; the separate cross-document rule still requires at least two sources.
4. **Empty report accepted:** An existing zero-byte file could be treated as a completed dossier. Actual adapter runs now require a nonempty file. Report semantics remain the dossier feature's responsibility.
5. **Warning lost on a skipped step:** A partial-input warning disappeared when contextual analysis had no adapter. Skipped and waiting paths now preserve the warnings supplied to them.

The new regression cases were run before the fixes and reproduced the failures, then passed after the changes.

## Full PS2 requirement mapping

| Mandatory prototype requirement | Phase 4 contribution | Remaining implementation |
| --- | --- | --- |
| Multiple authorized documents with IDs and source references | Case and manifest identities carried through requests; source identity cannot be changed by classification | Upload and full ingestion in `feature/ingestion-ocr` |
| OCR structured fields with location and confidence | Shared field outputs, scope checks, warnings for empty or uncertain results | Actual OCR and layout extraction in `feature/ingestion-ocr` |
| Review interface | Review-decision records and waiting behaviour | Screens, user interaction, and persistent decisions in `feature/review-interface` |
| Suspicious visual regions | Typed visual findings and validated evidence scope | Actual detectors and highlights in `feature/visual-forensics` and the interface |
| Inconsistencies within a document | Within-document finding contract constrained to one source document | Comparison logic in `feature/contextual-analysis` |
| Conflicts across related documents | Cross-document finding contract needs two source documents; failed OCR inputs are excluded | Entity matching and comparison in `feature/contextual-analysis` |
| Explained findings with source evidence and uncertainty | Observation, explanation, evidence, confidence, warnings, and mandatory review state | Evidence-backed analysis, UI presentation, and Phase 5 page-region demonstration |
| Structured investigation dossier | Report step receives case records and prior processing limitations; review must complete first | Six required report sections and download in `feature/investigation-dossier` |

## Deliverables still to finish

The working application, full architecture covering the selected models and tools, sample generated dossier, complete setup and licensing documentation, authorized demonstration dataset, full methodology documentation, live evidence-traceability demonstration, and final limitations report are not all complete. They are assigned to the remaining foundation phases and feature branches. The current architecture, source repository, processing guide, and local sample inventory are partial supporting deliverables.

The audit trail is currently held in memory, with processing snapshots exportable as JSON. Persistent investigation history and authenticated review UI are later implementation work. Adapters will enforce actual service time limits; this phase defines the timeout error and safe propagation. The practice adapters perform no OCR, real forensic analysis, or real human review and generate no dossier.

## Verification results

- Full suite: 42 tests pass after the fixes.
- Python compilation succeeds.
- A01 source manifest verifies three unchanged PDFs.
- All three A01 practice scenarios retain explicit practice mode and no generated dossier.
- A guarded integration test rejects any attempted access to `ground_truth.csv` while exercising all three practice scenarios.
- Staged whitespace checks pass before commit.

No finite test suite proves the absence of all possible bugs. The checks above cover the Phase 4 contracts and the reproduced failure cases; the real OCR, analysis, interface, and dossier behaviours require their own later verification.
