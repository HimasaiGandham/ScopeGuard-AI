# 🔎 Document Forensics Assistant

### DataOps Innovation Hackathon — Problem Statement 2

This project aims to help a person review a group of documents and spot details that may need a closer look. It will read information from the documents, compare related details, point to unusual areas, and explain what it found.

## 💡 Why this matters

Imagine reviewing an application form, an identity document, and a supporting letter. A name or date may differ between them. A number may appear to have been changed. Checking every page by hand takes time, and a simple text reader may miss the connection between documents.

Our goal is to bring those clues together so a reviewer can investigate them more easily.

## 🧭 How the planned system will work

1. **Add documents.** A reviewer uploads several permitted sample documents for one case.
2. **Read the information.** The system reads printed text, including text in scanned pages or images, and organizes useful details such as names, dates, and amounts.
3. **Compare the details.** It looks for missing or conflicting information within a document and across the group.
4. **Look at the pages.** It highlights areas that appear visually unusual, such as a field with different spacing or alignment.
5. **Show the evidence.** Each finding points back to the document and location that supports it.
6. **Create a report.** The system produces an investigation summary with the findings, evidence, possible explanations, and items that need human review.

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

This first screen uses your manual selection. Automatic text reading, discrepancy detection, comparison across documents, and the investigation report are still to be built.

## 📤 Try your own documents

Open PowerShell in the project folder and run:

```powershell
python -m pip install -r requirements.txt
python -m docforensics.upload_app
```

Open [the document case screen](http://127.0.0.1:8765/ingest). Choose related PDFs or images and click **Upload files and create case**. The table shows accepted files, skipped duplicates, and rejected files with clear reasons. Expand **Show page IDs** or **Show fingerprint** to inspect a file's identity. Use **Reopen this case** to return to the saved case. Keep PowerShell running while using the screen.

The originals are copied unchanged outside the repository. See the [ingestion guide](docs/ingestion.md) for limits, identity rules, storage, and API usage. The [manual evidence screen](http://127.0.0.1:8765/) remains available for selecting a region in a single PDF.

## 📚 More detail

The [requirements checklist](docs/ps2-requirements.md) records the full prototype, demo, and submission expectations from the hackathon problem statement.

The [foundation architecture](docs/architecture.md) explains how documents, findings, and source evidence will connect.

The [processing guide](docs/processing-contracts.md) defines processing inputs, outputs, statuses, errors, and practice commands.

The [evidence tracing guide](docs/evidence-tracing.md) explains how to upload your own PDF, select a region, and verify its source link.

The [setup guide](docs/setup.md) gives isolated installation, execution, and test instructions.
