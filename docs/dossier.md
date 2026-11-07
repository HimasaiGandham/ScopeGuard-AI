# Investigation dossier

The reviewer workspace exports the selected extraction, contextual, and visual results as a PDF. Each export captures the effective decisions for those runs at the time of generation.

## Generate and download

1. Open a saved case in the [reviewer workspace](reviewer.md) and choose **Process this case** or select existing runs. Confirm the related-document grouping only when the documents concern the same student and enrollment.
2. Inspect the original evidence and record a decision with a note for every finding. Enter your reviewer name and acknowledge that the results may be incomplete or uncertain.
3. Select **Generate PDF dossier**, then **Download PDF dossier**. Reopening the case shows its latest saved PDFs.

The six sections cover document overview, extracted information, contextual analysis, visual forensic findings, evidence and traceability, and investigation summary. The PDF identifies the selected runs and their record fingerprints. It includes file fingerprints, page failures and unsupported layouts, extracted values, source locations, uncertainty, and decisions with their event IDs, reviewer names, and notes.

Evidence IDs in the report point to document and page IDs and exact normalized regions. Page and visual crop links open through the local server at the address used for export. The receiving viewer can use the printed references to locate the sources in a matching case when the local links are unavailable. The PDF uses references and links so it can remain small without embedding every page image.

## Snapshot and limits

Export requires matching extraction and contextual runs, reviewed findings bound to the exact saved content, and original files that still match their fingerprints. A changed or missing original blocks new exports. A new review or export leaves earlier PDFs as historical snapshots. Save the corresponding authorized sources separately if the report needs to remain traceable after handover.

The PDF retains failed and incomplete results and shows unavailable confidence explicitly. The report summarizes supported observations and reviewer decisions. The visual detector covers blue ink near dark printed content, and the contextual checks cover selected fields and supported layouts. Findings indicate items for follow-up. The workflow leaves authenticity unverified.

Export is limited to 2,000 combined report entries and one million text characters. Split a packet and rerun the checks if it exceeds the limit. The report font renders supported characters directly and shows other characters as Unicode escapes.

## Local API

- `POST /api/ingestion/cases/{case_id}/dossiers` accepts extraction, context, and visual run IDs, a reviewer name, and `acknowledge: true`. A successful response returns the new ID and download path.
- `GET /api/ingestion/cases/{case_id}/dossiers/{dossier_id}` downloads the saved PDF. The workspace response lists up to 50 recent exports.

The case's external data directory stores generated PDFs under `dossiers/`. The export runs locally with ReportLab and uses saved records. It requires neither a model service nor an answer key. The previous request endpoint remains available for historical integrations and saves request metadata only.

Run the [test suite](setup.md) for the PDF round trip, data and evidence fidelity, immutable exports, rejection of invalid selections, changed originals, and failed writes.
