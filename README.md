# 🔎 Document Forensics Assistant

### DataOps Innovation Hackathon — Problem Statement 2

This project aims to help a person review a group of documents and spot details that may need a closer look. It will read information from the documents, compare related details, point to unusual areas, and explain what it found.

## 💡 Why this matters

Imagine reviewing an application form, an identity document, and a supporting letter. A name or date may differ between them. A number may appear to have been changed. Checking every page by hand takes time, and a simple text reader may miss the connection between documents.

Our goal is to bring those clues together so a reviewer can investigate them more easily.

## 🧭 How the system works

1. **Add documents.** A reviewer uploads several permitted sample documents for one case.
2. **Read the information.** The system reads printed text, including text in scanned pages or images, and organizes useful details such as names, dates, and amounts.
3. **Compare the details.** It looks for missing or conflicting information within a document and across the group.
4. **Look at the pages.** It highlights supported visual clues, such as blue ink crossing a printed field.
5. **Show the evidence.** Each finding points back to the document and location that supports it.
6. **Review findings and download a report.** A reviewer records decisions and generates a PDF dossier with findings, evidence references, and follow-up items.

### 📝 A simple example

If an application form and a supporting document show different dates of birth, the system should display both values, show where each appears, and explain the mismatch. **A mismatch is a reason to check; it is not proof of fraud.**

## 👀 What the hackathon demo should show

- Uploading and reviewing more than one sample document.
- Reading and organizing information from those documents.
- Finding visual clues and differences within or across documents.
- Clicking a finding to see its source on the original page.
- Creating a clear investigation report.

## 🚧 Current status

**Multi-document case creation is available:** upload related PDFs, PNGs, and JPEGs together, see each file's acceptance status, and inspect its document ID, page IDs, and fingerprint. A separate manual PDF screen lets you draw an evidence region and open its source-linked view. Shared records, source verification, and processing contracts support these tools.

The prototype supports the workflow from document upload through PDF dossier export. English printed text extraction returns source-linked fields for supported layouts. Contextual checks compare observed values within documents and across reviewer-confirmed related documents. The upload screen checks for blue ink near dark printed content and links suspected regions to the original. The reviewer workspace saves decisions and exports the selected case results to PDF. Numeric OCR and visual confidence are unavailable. The final demo and submission are Priority 7.

## 📤 Try your own documents

Open PowerShell in the project folder and run:

```powershell
python -m pip install -r requirements.txt
python -m docforensics.upload_app
```

Open [the document case screen](http://127.0.0.1:8765/ingest). Choose related PDFs or images and click **Upload files and check for visual marks**. The table shows saved files, skipped identical copies, and rejection reasons. Check **Alteration check** for suspicious regions and select **Open reviewer workspace** for the full processing and review flow. Expand **Show page IDs** or **Show fingerprint** to inspect file identity. Use **Reopen this case** to return to the saved case. Keep PowerShell running while using the screen.

The originals are copied unchanged outside the repository. See the [ingestion guide](docs/ingestion.md) for limits, identity rules, storage, and API usage. The [manual evidence screen](http://127.0.0.1:8765/) remains available for selecting a region in a single PDF.

## 📚 More detail

The [requirements checklist](docs/ps2-requirements.md) records the full prototype, demo, and submission expectations from the hackathon problem statement.

The [architecture guide](docs/architecture.md) shows how documents, findings, source evidence, and review decisions connect.

The [processing guide](docs/processing-contracts.md) defines processing inputs, outputs, statuses, errors, and practice commands.

The [evidence tracing guide](docs/evidence-tracing.md) explains how to upload your own PDF, select a region, and verify its source link.

The [setup guide](docs/setup.md) gives isolated installation, execution, and test instructions.

The [OCR guide](docs/ocr.md) explains local model setup, supported layouts, source highlights, measured extraction results, and limitations.

The [contextual comparison guide](docs/contextual.md) explains supported comparisons, same-student/enrollment grouping, uncertainty, and evidence inspection.

The [visual inspection guide](docs/visual.md) explains the supported ink-overlap signal, evidence, measured misses, and false-alarm limitations.

The [reviewer workspace guide](docs/reviewer.md) covers processing, evidence inspection, and saved decisions. The [dossier guide](docs/dossier.md) explains PDF generation, download, and evidence links.
