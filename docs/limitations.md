# Measured results and limits

The integrated runtime at main commit `a86baca` was checked on 7 November 2026 in a fresh Windows checkout using Python 3.13 and the documented English model. The 112 automated tests, compilation, and dependency checks passed. A browser rehearsal ran upload, OCR, contextual and visual checks, source inspection, review, and PDF export. The separate evaluation keys were opened after processing.

| Controlled case | Observed result |
| --- | --- |
| Rehearsal packet | Two files accepted and the damaged PDF rejected. Seven expected fields matched exactly, including three from the scan. One internal conflict, two cross-document conflicts, and one blue ink region matched the expected observations. |
| Unmarked scan control | Zero visual leads on one clean scan. |
| Reserved packet | Six expected fields matched exactly, including three from the scan. One course-code mismatch was found. The deliberately black ink mark produced zero visual leads. |
| Rehearsal dossier | Five pages with all six sections. Three distinct original page or crop links opened. Source fingerprints and review event IDs matched the stored case. |

The observed processing times were 1.84 s for the rehearsal and 2.05 s for the reserved packet, measured from the browser's process action to displayed results on one machine. These small-case measurements exclude upload and human review time.

An earlier local evaluation on the supplied 15 PDFs provides another limited comparison. Exact OCR matches for edited targets were 5 of 5 printed edits and 0 of 5 scribbled edits. The visual method localized 5 of 5 blue scribbles, flagged 0 of 5 unmodified controls, and missed all 5 digital edits. The original evaluation materials are kept separate from the synthetic handover. See the [OCR evaluation](ocr.md) and [visual evaluation](visual.md).

| Area | Supported behavior and limits |
| --- | --- |
| Extraction | Printed English in supported coursework and related-form layouts. Numeric OCR confidence is unavailable. Handwriting, arbitrary layout extraction, multilingual OCR, and calibrated scores remain open. Poor scan quality can change the observed value. |
| Contextual checks | Selected normalized fields and explicit same-enrollment grouping. Missing extracted fields can reflect OCR failure. Repetition may be intentional. Grouping unrelated records can introduce false leads. |
| Visual checks | Blue ink near dark print on a rendered page. Authorized marks, stamps, and scan artifacts may trigger observations. Black ink, grayscale, digital substitutions, fonts, and signature verification are outside the demonstrated scope. |
| Traceability | Originals and evidence use file fingerprints and normalized source coordinates. A changed source blocks export. Local files and review identities are unsigned. |
| Dossier | Snapshot of the selected results and recorded decisions. Page and region references travel with the PDF. Live evidence links require the matching local case and server. |
| Deployment | Loopback prototype with local storage and manual review. Multi-user identity, durable background jobs, and production deployment are outside scope. |

These results describe the named cases and cannot establish real-world sensitivity, specificity, or authenticity. ISO/IEC 27037, 27041, 27042, NIST SP 800-86, and OWASP ML security references in PS2 are background reading. The project makes no certification or formal compliance claim.
