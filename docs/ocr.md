# Local text extraction and supported layouts

## Install the English model

Digital PDF text works without a language model. Scanned PDFs and PNG/JPEG images use the Tesseract engine integrated into PyMuPDF and need its English language data. Download the model from the official Tesseract repository into a folder outside the checkout. For this workspace:

```powershell
New-Item -ItemType Directory -Path 'D:\Dataops\output\ocr-models' -Force
if (-not (Test-Path -LiteralPath 'D:\Dataops\output\ocr-models\eng.traineddata')) {
    Invoke-WebRequest 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/eng.traineddata' -OutFile 'D:\Dataops\output\ocr-models\eng.traineddata'
}
Get-FileHash 'D:\Dataops\output\ocr-models\eng.traineddata' -Algorithm SHA256
$env:OCR_TESSDATA = 'D:\Dataops\output\ocr-models'
```

The tested model hash is `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`. The upstream main branch can change; compare the hash before relying on the measured results below. Keep model files local. Start the server using the [setup guide](setup.md) after setting the variable. The default model folder is the checkout parent's `output/ocr-models`.

## Read and inspect a case

Create a case at `/ingest`, then choose **Read text and inspect extracted fields**. On the extraction screen, click **Read this case**. Results show each document and page status, the text engine used, the detected layout, fields, sections, and supported table counts. Expand **Read page text** for the observed text. Select a field to display its verified source page with a red rectangle around the value; page size controls scale the image and rectangle together.

Each field uses the shared `ExtractedField` format: a stable field ID, label, observed value, optional confidence, document ID, 1-based page, and normalized source rectangle. The original ingestion record and original bytes are not replaced. Each API run saves a new JSON record under the external case folder's `extractions` directory using a unique run ID and exclusive file creation. Use **View saved extraction record** to retrieve it. These snapshots are not a dossier or a resumable job database.

## Supported structure

The supported demo family is the Northfield coursework form, identified from its institution heading and four unique metadata labels. The Data Quality Audit title is also recognized for the controlled test fixture. Assignment titles can vary.

- Fields: Student name, Student ID, Submission date, and Course code.
- Sections: Aim, Method, and Result and reflection, where those headings are readable.
- Tables: the four-row label/value block and the Recorded values table headed Measure and Value. Recorded rows become source-linked fields, retaining units and punctuation as observed.

Other layouts are marked `unsupported_layout` with type `unknown`. Their page text is retained, but semantic fields, sections, and tables are not guessed. This is not a general-purpose invoice, identity document, bank statement, or arbitrary-table parser.

## Confidence and failure behavior

The integrated engine does not expose word-level confidence through this extraction path. Confidence is therefore `null`, and every result displays **review required**. Digital text also has no assigned correctness score. No field is declared verified truth. Missing or unreadable values remain absent; recognition does not fill them from evaluation labels.

Each page runs in a separate worker with a 45-second limit. Oversized rendered pages, missing models, unreadable text, and engine failures are visible. Failed pages or documents do not discard successful results from other inputs. Original fingerprints are checked before and after each document; a source change invalidates that document's output. Image orientation is applied to the displayed page before extraction. Runtime does not read the evaluation answer key.

## Measured demo limits

A local evaluation of the supplied 15 single-page PDFs completed text extraction for all 15, recognized all 15 as the supported coursework layout, and returned 105 fields (four metadata fields and three recorded table values per page). All source hashes remained unchanged.

Only the ten deliberately edited target fields were scored against the separate evaluation labels, after blind extraction completed:

| Target subset | Exact matches |
| --- | --- |
| Digitally printed replacements | 5 of 5 |
| Scribbled replacements | 0 of 5 |
| All edited targets | 5 of 10 |

These are exact-value checks on a small provided dataset, not accuracy claims for all 105 fields or all page text. Scribbles produced extra characters, substitutions, and omissions. Ordinary printed text can also contain errors, such as confusing uppercase I and lowercase l. English printed-text support is implemented; handwriting, multilingual text, arbitrary layouts/tables, robust document classification, and confidence calibration remain unsupported extensions. Always inspect source locations before using a value.

## API and tests

`POST /api/ingestion/cases/{case_id}/extract` runs extraction and returns document/page results plus shared structured fields. It uses the same local POST header/origin rules as ingestion. `GET /api/ingestion/cases/{case_id}/documents/{document_id}/pages/{page}` serves a verified source rendering for inspection. The browser route is `/extract?case=<case_id>`.

`GET /api/ingestion/cases/{case_id}/extractions/{run_id}` returns a saved extraction snapshot after source verification.

Run the full test suite from the setup guide. Digital layout tests check exact values and source rectangles; OCR integration tests run when the local English model is installed. Mixed-packet tests cover a missing model, timeout isolation, source tampering, unsupported layouts, and preservation of readable documents.
