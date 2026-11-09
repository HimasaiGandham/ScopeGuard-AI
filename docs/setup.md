# Setup and testing

Use Python 3.13, the tested version for this project. In PowerShell, open the repository folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For scanned PDFs or images, [download and verify the English OCR model](ocr.md#install-the-english-model). In the same PowerShell session, start the app:

```powershell
.\.venv\Scripts\python.exe -m docforensics.upload_app
```

Using the environment's Python directly avoids changing PowerShell execution policy. Open [the document case screen](http://127.0.0.1:8765/ingest), drop or choose related PDFs or images, and click **Upload & check**. Inspect the saved documents, duplicate and rejection messages, and alteration check. The [manual evidence screen](http://127.0.0.1:8765/) supports selecting a source region in a single PDF. Keep the server running while using either screen. Press Ctrl+C to stop it. If port 8765 is occupied, use a running server with the current code or start on another port with `--port 8766`.

Document cases accept up to 20 PDFs, PNGs, or JPEGs, at most 20 MiB each and 100 MiB combined. PDFs support up to 200 pages, and images up to 25 million pixels. The separate manual evidence screen accepts one PDF per case. Uploaded copies and generated evidence are stored outside the checkout under its parent's `output/local-upload-viewer` folder. Use `--data-dir` to choose another external folder. The original selected files are not modified. Processing is local and requires no API keys.

## Run the checks

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q docforensics tests
.\.venv\Scripts\python.exe -m pip check
```

Tests generate synthetic PDFs and need no private dataset or evaluation answer key. The checkout's parent folder must be writable because test files are created outside the checkout. Direct dependencies are pinned and transitive dependencies are resolved at install time. See [dependency terms](third-party.md) before distribution.

## Host a judge demo on Render

In the [Render dashboard](https://dashboard.render.com/), choose **New → Blueprint** and connect the repository branch that contains `render.yaml`. The Blueprint builds a Docker web service with the verified English OCR model and generates a `DEMO_PASSWORD`. When the service is live, open its HTTPS URL with `/ingest` appended. Sign in as `reviewer` using the password from the service's **Environment** page. Share the password separately with authorized reviewers.

Use the synthetic packet from the [demo walkthrough](demo.md). The hosted demo uses a shared reviewer login and stores cases on the free instance's temporary filesystem. Upload only synthetic documents and download the dossier during the same session. Restart, redeployment, or idle shutdown can clear saved cases.

## Supported behavior and contracts

The application supports multi-document acceptance, text/OCR, contextual comparisons, visual ink-overlap checks, saved human review, and PDF dossiers. Open a saved case and choose **Open reviewer workspace** for the [reviewer flow](reviewer.md) and [PDF export](dossier.md). The [OCR guide](ocr.md) explains the local English model. Practice commands simulate the wider coordinator. The reviewer screen invokes real feature processing.

Source regions use 1-based pages and normalized coordinates from 0 to 1, starting at the displayed page's top-left corner. Extracted fields and findings retain their source references. The local workspace saves results and review history, and the extraction and visual workers enforce per-page deadlines. The practice coordinator keeps its simulated step history in memory. The workspace provides manual reruns.

See [ingestion](ingestion.md), [architecture](architecture.md), [processing contracts](processing-contracts.md), [local manifests](local-manifest.md), and [evidence tracing](evidence-tracing.md) for usage and integration details.
