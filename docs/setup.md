# Setup and testing

Use Python 3.13, the tested version for this project. In PowerShell, open the repository folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m docforensics.upload_app
```

Using the environment's Python directly avoids changing PowerShell execution policy. Open [the upload screen](http://127.0.0.1:8765/), choose an unlocked PDF, upload it, select a page, draw a box, enter an observation, and create the evidence view. Keep the server running while using the screen; press Ctrl+C to stop it. If port 8765 is occupied, use the existing server or start on another port with `--port 8766`.

The screen accepts one PDF per manual case, up to 20 MiB and 200 pages. Uploaded copies and generated evidence are stored outside the checkout under its parent's `output/local-upload-viewer` folder. Use `--data-dir` to choose another external folder. The original selected file is not modified. Processing is local and requires no API keys.

## Run the checks

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q docforensics tests
.\.venv\Scripts\python.exe -m pip check
```

Tests generate synthetic PDFs and need no private dataset or evaluation answer key. The checkout's parent folder must be writable because test files are created outside the checkout. Direct dependencies are pinned; transitive dependencies are not locked. Read the dependency licenses before distribution, especially PyMuPDF's licensing options. A project-wide license has not yet been selected.

## Supported behavior and contracts

The current application supports PDF upload and manually selected source evidence. Automatic OCR, visual and contextual detection, multi-document review, and dossier generation are future work. Practice commands simulate processing adapters; they do not produce actual analysis.

Source regions use 1-based pages and normalized coordinates from 0 to 1, starting at the displayed page's top-left corner. Extracted fields and findings must retain their source references. Analysis findings await human review, and ingestion preserves verified source identity. The synchronous coordinator keeps processing history in memory; persistence, automatic retries, and adapter deadlines require later implementations.

See [architecture](architecture.md), [processing contracts](processing-contracts.md), [local manifests](local-manifest.md), and [evidence tracing](evidence-tracing.md) for usage and integration details.
