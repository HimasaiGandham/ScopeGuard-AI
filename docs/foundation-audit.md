# Foundation phases 1–3 audit

Audit date: 1 November 2026 (India Standard Time)

Branch: `feature/foundation`

## Scope and result

This audit reviewed the sample inventory (phase 1), shared case and evidence models (phase 2), and local PDF manifest (phase 3). It inspected the implementation, ran the full test suite and Python compilation, verified the real A01 manifest, and read all 15 sample PDFs without changing them.

The reviewed functions now pass 19 automated tests. The existing A01 manifest verifies three unchanged PDFs. No OCR, visual anomaly detection, or fraud classification is claimed by this audit.

## Phase 1 — sample inventory

- Confirmed 15 PDF files and 15 answer-key rows, with no missing or extra filenames.
- Confirmed five source groups of three PDFs each. The answer key labels five unmodified variants and ten altered variants.
- Opened all 15 PDFs through the manifest builder in memory: all were readable, all had one page, and all had distinct SHA-256 hashes.
- The answer key remains local and is not used as input to the running manifest tool.

These labels describe the prepared dataset. They do not independently establish real-world authenticity.

## Phase 2 — case and evidence models

Reviewed `docforensics/models.py` and the source-reference checks. A case rejects duplicate document IDs, missing evidence documents, and evidence pages beyond a known page count. Source regions use 1-based page numbers and normalized coordinates.

**Issues found and corrected:**

1. A finding could be created with an unsupported category, an unsupported review state, or a blank explanation. These now raise validation errors.
2. Fractional page numbers and page counts were accepted despite the 1-based integer convention. These now raise validation errors.

Tests also cover an audit event pointing to an absent document and a timestamp without a time zone.

## Phase 3 — local manifest

Reviewed `docforensics/manifest.py`, its tests, and the A01 JSON outside the repository.

**Issues and test gaps corrected:**

1. The earlier tamper test changed file size, so it did not prove that SHA-256 detected an equal-size change. The test now covers both cases.
2. A manually changed document ID or duplicated file record could pass some checks. Verification now rejects them.
3. A malformed JSON root could produce an unclear program error. Verification now reports a validation error.
4. A non-serializable manifest could leave a partial output file. Serialization now happens before a new file is opened.
5. A second write to an existing manifest is explicitly tested and leaves the original intact.

The real A01 manifest passed `python -m docforensics.manifest verify` after these changes. Its source PDFs remain outside Git. The generated local manifest was not added to the repository.

## Checks performed

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests -v` | 19 tests passed |
| `python -m compileall -q docforensics tests` | Passed |
| A01 manifest verification | 3 unchanged PDFs |
| Dataset/answer-key inventory | 15 matching files and rows; five groups of three |
| In-memory manifest build across all PDFs | 15 readable, one-page PDFs; 15 distinct hashes |
| `git diff --check` | No whitespace errors |

## Limits and next work

- Manifest verification detects a PDF change **relative to the stored manifest**. The manifest is not digitally signed; someone who changes both a PDF and its JSON record could defeat that comparison. Keep the local manifest and answer key under controlled access.
- The dataset has variants of the same document template. A later demonstration needs related, different document types to establish broader cross-document reasoning.
- At the time of this audit, the application, OCR, visual checks, comparison engine, review interface, and dossier were not implemented, and foundation phases 4–6 remained open. See the work log for subsequent progress.

## Files reviewed or changed

- `docforensics/models.py` and `tests/test_models.py`
- `docforensics/manifest.py` and `tests/test_manifest.py`
- `docs/architecture.md`, `docs/local-manifest.md`, and `docs/work-log.md`
- Local A01 manifest outside Git: `../output/pdf/ocr_assignment_dataset/manifests/A01.json`
