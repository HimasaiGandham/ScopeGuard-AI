# Setup and testing

Use Python 3.13, the tested version for this project. In PowerShell, open the repository folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m docforensics.upload_app
```

Using the environment's Python directly avoids changing PowerShell execution policy. Open [the document case screen](http://127.0.0.1:8765/ingest), choose related PDFs or images, and click **Upload files and create case**. Inspect the accepted documents, page IDs, duplicates, and rejection messages. The [manual evidence screen](http://127.0.0.1:8765/) also supports selecting a source region in a single PDF. Keep the server running while using either screen; press Ctrl+C to stop it. If port 8765 is occupied, use a running server with the current code or start on another port with `--port 8766`.

Document cases accept up to 20 PDFs, PNGs, or JPEGs, at most 20 MiB each and 100 MiB combined. PDFs support up to 200 pages, and images up to 25 million pixels. The separate manual evidence screen accepts one PDF per case. Uploaded copies and generated evidence are stored outside the checkout under its parent's `output/local-upload-viewer` folder. Use `--data-dir` to choose another external folder. The original selected files are not modified. Processing is local and requires no API keys.

## Run the checks

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q docforensics tests
.\.venv\Scripts\python.exe -m pip check
```

Tests generate synthetic PDFs and need no private dataset or evaluation answer key. The checkout's parent folder must be writable because test files are created outside the checkout. Direct dependencies are pinned; transitive dependencies are not locked. Read the dependency licenses before distribution, especially PyMuPDF's licensing options. A project-wide license has not yet been selected.

## Supported behavior and contracts

The application supports multi-document acceptance, text/OCR, contextual comparisons, visual ink-overlap checks, and saved human review. Open a saved case and choose **Open reviewer workspace** for the combined flow described in the [reviewer guide](reviewer.md). The [OCR guide](ocr.md) explains the local English model; visual checks do not need it. PDF dossier export and additional visual methods remain future work. Practice commands still simulate the wider coordinator; the reviewer screen invokes real feature processing.

Source regions use 1-based pages and normalized coordinates from 0 to 1, starting at the displayed page's top-left corner. Extracted fields and findings must retain their source references. Analysis findings await human review, and ingestion preserves verified source identity. The synchronous coordinator keeps processing history in memory; persistence, automatic retries, and adapter deadlines require later implementations.

See [ingestion](ingestion.md), [architecture](architecture.md), [processing contracts](processing-contracts.md), [local manifests](local-manifest.md), and [evidence tracing](evidence-tracing.md) for usage and integration details.
