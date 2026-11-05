# Accepting and identifying documents

The document case screen accepts related files together, preserves their original bytes, and records exactly which documents and pages belong to the case. It identifies file formats; document classification and OCR are later features.

## Create and reopen a case

Start the server using the [setup guide](setup.md), then open `/ingest` on its local address. For the default port this is [the document case screen](http://127.0.0.1:8765/ingest).

1. Choose the related PDFs or images. You can select several files at once.
2. Click **Upload files and create case**.
3. Inspect each file's status, document ID, page count, and rejection or duplicate message.
4. Expand **Show page IDs** or **Show fingerprint** to inspect a document's recorded identity.
5. Use **Download original** to retrieve the exact accepted bytes, or **View case record** to inspect the metadata.
6. Save **Reopen this case** to return to the same case after a refresh or server restart. Keep the same data directory when restarting.

Each submission creates a new case. The application does not append to or replace an earlier case. The single-PDF manual evidence screen remains a separate tool at `/`; this ingestion screen does not yet send a packet through OCR or forensic analysis.

## Supported files and limits

| Limit | Behavior |
| --- | --- |
| Formats | Unlocked PDF, single-frame PNG, and JPEG (`.jpg` or `.jpeg`) |
| File count | 1 to 20 selected files per case |
| File size | At most 20 MiB per file |
| Combined size | At most 100 MiB of selected file bytes; the HTTP body also has a bounded allowance for multipart headers |
| PDF pages | 1 to 200 per PDF |
| Image pixels | At most 25 million per image; each image is one page |

File extensions must match readable content. An unsupported, empty, damaged, oversized, password-protected, or incorrectly named file receives a clear rejection reason while valid files in the same permitted-size batch are retained. A batch that exceeds the file-count or total-size limit is rejected as a whole. No source copy is saved for a rejected item. A case with no accepted documents is explicitly marked `no_accepted_documents`.

## Identity and overwrite protection

A new case receives a generated `CASE-...` ID. Accepted documents receive IDs such as `CASE-...-D01`; their pages receive IDs such as `CASE-...-D01-P0001`, with page numbers beginning at 1. IDs and ordering remain stable when reopening the saved case. The record retains the original filename, detected media type, byte size, page count, and SHA-256 fingerprint.

Identical file bytes selected twice in one packet produce one accepted document and a `duplicate` entry pointing to it. Files with the same filename but different bytes remain separate documents. Selecting the same packet again creates a new case; duplicate handling is within each case.

Originals are stored using generated document IDs rather than user filenames, so same-name uploads do not collide. Case folders, source files, and final JSON records are created exclusively. A rare generated-ID collision fails instead of replacing an earlier case. The case record is written last; a storage failure before that point leaves no published case record. An incomplete or damaged record cannot be reopened as a verified case.

Under the configured external data directory, each case uses `cases/<case-id>/originals/` and `cases/<case-id>/case.json`. Reopening verifies original sizes and hashes; downloading also verifies the selected original. A changed or missing source produces a conflict error. These fingerprints detect changes relative to the local record; the record is not digitally signed.

## Local API and integration

| Request | Purpose |
| --- | --- |
| `POST /api/ingestion/cases` | Multipart form with repeated `files` fields; returns the case, accepted documents, page IDs, and per-upload statuses |
| `GET /api/ingestion/cases/{case_id}` | Reopen the record after verifying accepted originals |
| `GET /api/ingestion/cases/{case_id}/documents/{document_id}/original` | Download the verified original bytes |

POST requests require `X-Local-Upload: 1` and a matching local origin when an Origin header is supplied. The browser screen supplies these automatically. Requests are accepted only for the configured local host names. Invalid requests receive 4xx errors; storage failures receive a safe error rather than a false success.

`CaseStore.ingest(tuple_of_IncomingFile)` provides the same behavior without HTTP. `CaseStore.as_case(case_id)` returns shared `Document` records inside an `InvestigationCase`, preserving original filenames, document IDs, page counts, and fingerprints. Page IDs and media types remain in the saved case record. The existing processing coordinator and evidence models remain unchanged. Runtime ingestion does not read evaluation labels.

Run the full automated suite using the [setup guide](setup.md). A useful manual check is to submit three different PDFs, repeat one file, add a PNG or JPEG, and include an unsupported or damaged file. Verify the statuses and page counts, reopen the case, download an accepted original, and compare its SHA-256 fingerprint with the source file.
