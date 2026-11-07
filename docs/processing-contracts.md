# Foundation processing contracts

The processing layer defines the records passed between features and a synchronous coordinator that records their progress. A feature implementation plugs into the coordinator as an adapter: a function receiving `StepRequest` and returning `StepOutput`. The practice command uses clearly labelled simulated adapters.

## Step inputs and outputs

Every request includes the current case, the document IDs eligible for that step, the earlier step records, and a practice flag. Earlier records carry warnings, failures, and partial inputs so the review screen and dossier can disclose limitations.

| Step | Scope and prerequisites | Accepted output |
| --- | --- | --- |
| Ingestion | One verified document | Optional document classification; original ID, filename, page count, and fingerprint remain fixed |
| OCR | One document whose ingestion completed | Structured fields with confidence and source locations; an empty real result needs an explanatory warning |
| Visual | One document whose ingestion completed | Visual findings supported by regions in that document |
| Contextual | Only documents whose OCR completed | Findings about inconsistencies within or across those documents; cross-document findings need evidence from at least two documents |
| Review | The case, findings, and prior step records | Human decisions with finding ID, state, reviewer, and note, or an explicit waiting result |
| Dossier | The case after review completes, plus prior step records | A path to an existing generated file in an actual adapter run |

OCR and visual work continue independently after ingestion. An OCR failure does not prevent a visual check of the same document. A failed ingestion skips both. Contextual comparison proceeds on available OCR results with a partial-input warning when appropriate. The case retains the original document records so failed documents remain visible.

Output is validated before being added to the case. Duplicate IDs, invalid source regions, output for a different document, and data returned by the wrong step are rejected without adding that output. A within-document finding must reference exactly one document; a cross-document finding must reference at least two. Ingestion may classify a document but cannot change its verified source identity. A real dossier output must be an existing nonempty file; its actual report content is checked in the future dossier branch.

Runs require a fresh case with no previous extracted fields or findings. Reusing an earlier processed case is rejected so a failed OCR step cannot leave stale values in the new comparison. Case collections and finding evidence use immutable tuples. Resume and retry workflows must be designed explicitly before accepting prior analysis records as inputs.

## Status meanings

| Status | Meaning |
| --- | --- |
| `pending` | Waiting for a human review or for that review to finish |
| `running` | The adapter has started; recorded in the audit history |
| `completed` | The adapter returned valid output for this step |
| `failed` | The step ran and encountered an error or invalid output |
| `skipped` | The step did not run because an adapter is unavailable or a prerequisite failed |

Executed steps record a running event, then a completed, failed, or waiting event. Skipped steps have no start time. A waiting review has no finish time, and the dossier remains pending without being invoked. The coordinator is synchronous; live background monitoring, pause/resume, automatic retries, and durable job storage are future work. A `retryable` error flag describes whether a retry may be useful; it does not trigger one.

## Errors and warnings

Errors carry a code, a safe message, a retryable flag, and an optional 1-based page number. The step record provides the affected document IDs. Page-specific errors must refer to a valid page in a single document.

| Error code | Meaning |
| --- | --- |
| `missing_input` | A required input is unavailable |
| `unreadable_document` | A document or page cannot be read |
| `unsupported_document` | The implementation does not support the input |
| `source_changed` | A source no longer matches its verified identity |
| `timeout` | An adapter reports that its time limit expired |
| `invalid_output` | Returned data violates the shared contracts |
| `not_implemented` | No adapter has been registered for the step |
| `dependency_failed` | A prerequisite did not complete |
| `internal_error` | An unexpected adapter exception occurred |

Adapters implement their own actual I/O deadlines and raise `StepFailure(ProcessingError(...))` for expected failures. Unexpected exceptions receive a generic public message; their raw text is not copied into progress summaries or audit events. Expected error messages should be written for the reviewer and must not contain secrets or unnecessary source text.

Warnings use `low_confidence`, `partial_input`, or `unsupported_layout`. A low-confidence value may still be returned with its confidence and evidence; the warning does not automatically fail the entire step. Warnings remain in the progress records.

## Human review and audit history

A review decision accepts a lead for further review or dismisses it. Neither state proves authenticity or fraud. New analysis findings must be pending; an analysis adapter cannot mark its own findings as human-reviewed. Pending findings cannot be silently marked as reviewed. Review notes and reviewer identifiers are retained in the case audit history. The compact JSON progress summary includes IDs, statuses, timestamps, errors, warnings, and output IDs; it omits source text, review notes, report paths, and document paths.

The coordinator records history in memory. The `--json` option exports a progress snapshot when requested; it is not a persistent job database or a resume file. Adapters should use request document IDs as their analysis scope and return the shared models rather than changing the case in place.

## Run processing practice on A01

From the repository folder, run:

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m docforensics.practice '..\output\pdf\ocr_assignment_dataset\manifests\A01.json' --scenario success
python -m docforensics.practice '..\output\pdf\ocr_assignment_dataset\manifests\A01.json' --scenario ocr-failure
python -m docforensics.practice '..\output\pdf\ocr_assignment_dataset\manifests\A01.json' --scenario awaiting-review
```

Each practice run first verifies the source manifest and prints `PRACTICE ONLY`. The adapters do not perform OCR, analyze alterations, read the answer key, record a real human decision, or create a dossier. Simulated `completed` statuses prove the coordination path only.

- **Success:** Twelve simulated steps complete for the three-document case, with 24 audit events and no generated fields, findings, or dossier.
- **OCR failure:** A01-D02 has a simulated retryable timeout. Its visual step still runs. Contextual comparison receives A01-D01 and A01-D03 and displays a partial-input warning.
- **Awaiting review:** Review and dossier remain pending. The dossier adapter is not started.

Add `--json` to print the structured progress summary. The runtime reads the named manifest and its PDFs; `ground_truth.csv` remains separate. A practice command exits successfully when its selected simulation runs, including the intentionally injected failure scenario; inspect the printed statuses or JSON for that simulated failure.

## Verification evidence

The tests exercise shared field and finding exchange, document classification without identity changes, valid review decisions, input-scope checks, per-document failure isolation, partial inputs, waiting review, unavailable adapters, safe unexpected-error messages, low-confidence warnings, report-file validation, invalid page references, and manifest-to-practice integration. Original synthetic test cases remain unchanged when output validation fails.

The [evidence tracing guide](evidence-tracing.md) demonstrates a page-region link using the A01 sources. The [reviewer workspace](reviewer.md) runs the implemented extraction, contextual, and visual services on saved cases. The practice commands above exercise the simulated coordinator.
