# Foundation handoff

Prepared 6 November 2026 for `feature/foundation`. This branch supplies shared records, verified local inputs, processing contracts, and manual evidence tracing. The full PS2 prototype remains in development.

## Set up a fresh checkout

Use Python 3.13, the version tested for this foundation. In PowerShell, open the checkout folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m docforensics.upload_app
```

Using the environment's Python directly avoids needing to change PowerShell execution policy. For running the screen without tests, install `requirements.txt` instead. The declared versions pin direct dependencies; transitive dependencies are not locked. Read the dependency licenses before distributing the prototype, especially PyMuPDF's licensing options; no project-wide licensing decision has been made.

Open [the upload screen](http://127.0.0.1:8765/), choose an unlocked PDF, click **Upload and open PDF**, select a page, draw an evidence box, add an observation, and create the evidence view. Stop a foreground server with Ctrl+C. If the port is occupied, open the existing server or choose another port with `--port 8766` and open that port's URL.

The automated tests generate their own synthetic PDFs. They do not require the private dataset, a manifest from another computer, API keys, or an answer key. The checkout's parent folder must be writable because test data is deliberately created outside the checkout. Uploaded copies and generated evidence also stay outside the checkout; use `--data-dir` to choose another external folder if needed.

## Verify the local A01 case separately

These checks use this workspace's existing local data; they are optional on a fresh computer without that data:

```powershell
python -m docforensics.manifest verify 'D:\Dataops\output\pdf\ocr_assignment_dataset\manifests\A01.json'
python -m docforensics.practice 'D:\Dataops\output\pdf\ocr_assignment_dataset\manifests\A01.json' --scenario success
python -m docforensics.practice 'D:\Dataops\output\pdf\ocr_assignment_dataset\manifests\A01.json' --scenario ocr-failure
python -m docforensics.practice 'D:\Dataops\output\pdf\ocr_assignment_dataset\manifests\A01.json' --scenario awaiting-review
```

Expect three unchanged PDFs. The practice runs must label themselves as simulations. The injected OCR failure affects A01-D02 while visual processing remains available; waiting review leaves the dossier pending. These commands do not perform actual OCR or generate a report.

## What later branches should reuse

| Component | Contract to preserve |
| --- | --- |
| `models.py` | Cases, documents, fields, findings, review states, audit events, and source references |
| `manifest.py` | Stable document identity, page counts, SHA-256 verification, and source-folder linkage |
| `processing.py` | `StepRequest` to `StepOutput`, scoped document IDs, validated results, statuses, warnings, and safe failures |
| `trace.py` | Verified rendering and evidence bundles with normalized coordinates and source fingerprints |
| `upload_app.py` | A local manual PDF screen demonstrating the tracing contract; not a multi-document processing adapter |

Page numbers begin at 1. Regions use normalized coordinates from 0 to 1, with the origin at the top-left of the displayed page. OCR or image coordinates must be converted into this convention. Every extracted field and finding must retain its supporting document, page, and region. Ingestion must preserve source identity. Analysis findings begin pending human review.

See [architecture](architecture.md), [processing contracts](processing-contracts.md), [local manifests](local-manifest.md), and [evidence tracing](evidence-tracing.md) for the full rules.

## Next branch: ingestion and OCR

After foundation review and merge, bring `feature/ingestion-ocr` up to date with the merged foundation before implementation. Its first phase should accept multiple permitted PDFs or images into one case and preserve their identities. Later phases add supported document classification, text extraction, structured fields with source locations and confidence, and failure isolation. Select and evaluate an actual OCR engine there; this foundation does not select one.

Keep the evaluation answer key separate from runtime input. The five sample groups are variants of one template; use additional related document types later to demonstrate broader contextual reasoning.

## Boundaries and review checklist

The local upload screen accepts one PDF per manual case, up to 20 MiB and 200 pages. Rendering is bounded to avoid oversized page images. OCR, automatic visual or contextual findings, multi-document review, persistent processing jobs, and dossier generation remain future work. The current in-memory coordinator does not supply retries, job persistence, or actual adapter deadlines.

Before merge, inspect the staged files and confirm that the source PDFs, answer key, generated bundles, personal branch plan, and local Phase 4 review are absent. Run the automated checks and inspect the upload flow. Keep the full [PS2 checklist](ps2-requirements.md) open until its working prototype and deliverables are actually demonstrated. This handoff prepares the foundation for review; it does not merge the branch or declare the hackathon submission complete.
