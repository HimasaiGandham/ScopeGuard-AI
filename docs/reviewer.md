# Reviewer workspace

## Start a review

Create or reopen a case using the [ingestion screen](ingestion.md), then select **Open reviewer workspace**. The route is `/review?case=<case_id>`. Bookmark it to return to the same case. This screen combines the existing real extraction, contextual, and visual services; older individual screens remain available.

The case section lists accepted files, document IDs, page counts, duplicates, and rejection reasons. Each upload creates a new case. Its upload page runs an initial visual check and links supported suspicious marks to verified crops. The saved visual run is available in the reviewer workspace.

Select the same-student-and-enrollment checkbox only when that relationship is confirmed, then click **Process this case**. Live stage messages show extraction, contextual comparison, and visual inspection. Document/page results show completed, partial, failed, unsupported, or unreadable outcomes. Context is skipped if extraction fails; visual inspection is still attempted. Successful results remain available when another stage fails.

These requests run synchronously while the page stays open; there is no durable job queue or automatic job resumption after refresh. Reloading shows saved results, not a claim that a previous in-flight request finished. Existing per-page worker timeouts still apply.

## Inspect information and evidence

Read the extracted values alongside document/page identity, observed text, type/layout, and uncertainty warnings. Confidence remains unavailable where the engine supplies no score. Each value or finding has an **Inspect** button opening the original page with a normalized red rectangle. Cross-document findings expose both evidence locations. Visual observations also show a verified source crop. Page size scales the image and rectangle together.

Historical extracted values are marked when their source cannot be verified. Changed sources block human review of affected findings. Missing-extracted-field findings use the existing whole-page review anchor and do not assert confirmed document absence. Unknown or failed extraction is visible rather than silently treated as verified information.

Saved-run selectors allow inspection of previous extraction, contextual, and visual results. Contextual results must reference the selected extraction; mismatched selections are cleared with a warning. A failed rerun does not silently substitute an old successful run. Up to the newest 100 saved runs of each type appear in the catalog.

## Record human decisions

Enter your reviewer name and a note for a finding, then choose:

- **Accept lead for further review**: retain it for follow-up; this does not verify the value or confirm fraud.
- **Dismiss lead**: dismiss that lead with your reason; this does not certify the entire document.

Each action creates a new local review event with actor, note, UTC timestamp, decision, finding ID, report kind/run ID, finding-content fingerprint, and shared audit-event data. Decisions are bound to the exact saved run and finding content. They do not carry automatically to a new run, changed finding, or another case. Earlier events and original analysis reports are preserved; the newest matching event is the effective displayed state. Expand **Review history** for prior decisions. Refreshing restores saved decisions.

Reviewer names are self-entered local identifiers, not authenticated or digitally signed identities. Local JSON storage and source manifests are not tamper-proof. This is a local prototype, not a multi-user authorization system.

## Export an investigation dossier

Select matching runs, record a decision for every finding, and acknowledge the limits. Select **Generate PDF dossier** and download the saved report. Earlier exports remain available after refresh. See the [dossier guide](dossier.md) for the PDF contents, evidence links, and storage.

## Local API and storage

- `GET /api/ingestion/cases/{case_id}/workspace`: case inventory, saved runs, review history, and saved PDFs.
- `GET /api/ingestion/cases/{case_id}/review-run/{kind}/{run_id}`: selected report with effective review states and blocked-source notices. Kinds are extraction, context, and visual.
- `POST /api/ingestion/cases/{case_id}/reviews`: kind, run_id, finding_id, state (`accepted_for_review` or `dismissed`), reviewer, and note.
- `POST /api/ingestion/cases/{case_id}/dossiers`: generate a PDF using the selected run IDs, reviewer, and explicit acknowledgment.
- `GET /api/ingestion/cases/{case_id}/dossiers/{dossier_id}`: download a saved PDF.

The existing local host/origin/custom-header checks apply. Invalid states, unrelated findings, absent notes, mismatched processing runs, and unavailable sources are rejected. Reviews are exclusive new files in the external case's `reviews` folder; request files use `dossier-requests`. Originals, earlier runs, and notes are not overwritten. A changed review appends an event rather than editing an earlier note.

## Verification

Use the full test commands in the [setup guide](setup.md). Reviewer tests cover saved decision history, invalid inputs, changed originals, and decisions bound to exact runs and findings. Dossier tests cover matching runs, source links, failure visibility, and the download round trip. Sample files and generated reports remain local.
