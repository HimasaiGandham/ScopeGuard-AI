# Contextual comparison

Compare observed fields inside one document and across a related packet. Every result is a lead for human review, with original values and source locations. A discrepancy does not establish manipulation, and zero leads does not establish authenticity or completeness.

## Use the screen

1. Start the application using the [setup guide](setup.md), upload a packet at `/ingest`, and run extraction.
2. Choose **Check contextual consistency** from the extraction results.
3. Leave the relationship checkbox unchecked for internal checks only. Check it only when the packet concerns the same student **and enrollment**, where identity and course fields are intended to agree.
4. Click **Check consistency**. Each lead shows the rule, original values, normalized comparison values, uncertainty, and evidence buttons.
5. Inspect both cited locations for a conflict. The source image and rectangle scale together. Missing extracted fields use a clearly labelled whole-page review anchor, rather than an invented value location.
6. Expand **All original and normalized values**, or open **View saved analysis record** for the structured result.

Each analysis creates a separate JSON snapshot under the external case folder's `analyses` directory. Earlier analyses, extraction runs, case metadata, and original files are not replaced. A saved extraction is required; analysis does not accept arbitrary client-supplied fields. Sources are verified before analysis and again before saving.

## Supported normalization

| Kind | Supported comparison rule |
| --- | --- |
| Names and ordinary text | Unicode NFKC, collapsed whitespace, and case folding; original text retained. No fuzzy matching, token reordering, or I/l correction. |
| IDs and course codes | Whitespace normalization and uppercase; punctuation, internal spaces, and leading zeros are preserved. |
| Dates | ISO year-month-day, day plus full English month plus year, and day plus abbreviated English month plus year. Ambiguous numeric slash dates are left incomparable with a review warning. |
| Supported numeric fields | Exact decimal comparison for amount, total, fixed/variable/optional costs. Valid comma thousands separators are removed; supported currency symbols/codes remain part of the comparison. No rounding or currency conversion. Units or unsupported formats request review. |

Submission dates are not compared across different documents because different forms can legitimately have different submission dates. Cross-document checks are limited to student_name, student_id, course_code, and date_of_birth, after explicit relationship confirmation. Names are observations, not entity-resolution proof.

## Internal checks and uncertainty

Repeated occurrences of the same field within a document produce either an `internal_conflict` when comparable values differ or a `repeated_field` lead when equivalent values repeat. Repetition can be intentional. Cross-document differences produce `cross_document_conflict` with at least two original source references.

For a successfully extracted supported layout, expected but absent/empty fields produce `missing_extracted_field`. This means **not extracted**, not confirmed absent from the original. Unknown layouts or incomplete extractions do not establish missing document content. They produce coverage warnings instead. A format that cannot be normalized is retained with a warning and excluded from conflict decisions.

Expected fields are name/ID/course for registration and confirmation forms, plus submission date for coursework. Date of birth is optional. Confidence remains unknown when the OCR engine supplies no score. Unknown or below-0.7 extraction confidence is disclosed in conflict explanations, and all findings retain pending review with no invented finding confidence. The rules never label a person or document fraudulent.

## Different-document demo packet

The supported controlled templates use an exact heading on its own line and labelled rows, for example:

```text
Student registration
Student name Alice Example
Student ID NF-100
Course code ST-112
```

```text
Enrollment confirmation
Student name Alice Example
Student ID NF-100
Course code CS-999
```

For the same confirmed enrollment, this pair produces a course-code conflict citing both values. Add a second `Student ID NF-999` row to the registration to demonstrate an internal contradiction. Make both forms use ST-112 and omit the extra ID row for a clean control. These are narrow demo templates, not generic parsers for all registration/confirmation documents.

Automated and local acceptance checks generated real PDFs of these two document types and ran extraction before comparison. Four controlled packets produced:

| Packet | Expected and observed leads | Missed leads | Unexpected leads |
| --- | --- | --- | --- |
| Matching control | 0 | 0 | 0 |
| Contradictory ID plus different course | 1 internal and 2 cross-document conflicts | 0 | 0 |
| Repeated equivalent ID | 1 benign-repetition review lead | 0 | 0 |
| Unextracted course row | 1 missing-extracted-field review lead | 0 | 0 |

These are five expected review leads on four controlled packets, not a population accuracy estimate or proof of robustness on noisy OCR. Existing scribbled samples remain unreliable text inputs. All generated sources remained unchanged. Demo PDFs, raw results, labels, screenshots, and internal work records stay local. Runtime analysis reads only the selected saved extraction and verified case; it never opens `ground_truth.csv`. Evaluation expectations are compared after blind analysis in a separate test/evaluation process.

## API and boundaries

`POST /api/ingestion/cases/{case_id}/context` takes JSON `extraction_run_id` and boolean `same_entity` (default false). `same_entity: true` represents reviewer confirmation of the same student and enrollment. The normal local POST header/origin rules apply. Extra request fields, malformed run IDs, and non-boolean relationship values are rejected. `GET /api/ingestion/cases/{case_id}/analyses/{analysis_id}` retrieves a saved analysis after source verification.

The pure `analyze(InvestigationCase, same_entity=...)` function uses the shared field/finding/evidence models. The API reconstructs and validates those models from the saved extraction. Comparison supports up to 500 fields and returns at most 200 leads, with an explicit partial-results warning at the lead limit. It uses deterministic rules; learned entity resolution, fuzzy names, arbitrary document types, semantic reasoning over paragraphs, temporal version reconciliation, anomaly verification, and consequential human decisions are outside this implementation.
