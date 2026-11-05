# Foundation evidence tracing

Phase 5 links a case to a finding, a verified document, a page, and a selected region on that page. The example is manually selected and clearly labelled. It demonstrates source tracing rather than automated OCR, alteration detection, or an authenticity decision.

## Upload your own PDF

From the repository folder, run:

```powershell
python -m pip install -r requirements.txt
python -m docforensics.upload_app
```

Open [http://127.0.0.1:8765/](http://127.0.0.1:8765/) in your browser. Keep the server running while using the screen; press Ctrl+C in its PowerShell window to stop a foreground server. If a server is already running on port 8765, open its page instead of starting another copy.

1. Click **Choose File** and select your own PDF.
2. Click **Upload and open PDF**. The screen begins empty and uses the file you choose.
3. Choose a page if the PDF has more than one page. Adjust the page size if needed.
4. Drag a box around the area you want to document.
5. Enter an observation describing that area, then click **Create evidence view**.
6. Click the resulting link to open the highlighted page, crop, source PDF, and trace record.

The screen accepts one unlocked PDF at a time, up to 20 MiB and 200 pages. Each upload creates a separate manual case. Selecting another file clears the previous selection and result; changing pages also clears the selected box. Invalid files show an error.

Uploaded copies, manifests, and traces are stored under `D:\Dataops\output\local-upload-viewer\cases` in this workspace, outside Git. The selected original file is not modified. The saved copy has a sanitized filename; the original chosen filename is retained in `upload.json`. The source bytes are fingerprinted and verified before rendering and serving. The server listens only on this computer and uses no external service.

This is the Phase 5 manual evidence screen. It does not run OCR, automatically identify scribbles, compare several documents, or generate an investigation dossier. Drawing a box records your observation; it does not establish that a document was altered.

## Open the fixed local A01 example

Open `../output/pdf/ocr_assignment_dataset/evidence/A01-D03-144dpi/index.html` relative to the repository root in a browser. The generated folder stays outside Git. Keep all files in the folder together.

1. Inspect the case, finding, document ID, page, and source filename shown at the top.
2. Click **Show the source region**. The source page contains a red rectangle over the manually selected student ID area.
3. Move **Page size** between 50 and 150 percent and resize the window. The image and rectangle share one coordinate system, so they scale together.
4. Compare the selected crop with the same area of the full page.
5. Use **Open original PDF at page 1** to inspect the original PDF, or **View trace record** to see the source hash and coordinate data.

The example finding remains pending human review, and confidence is explicitly unassigned. Selecting a region does not confirm that it is fraudulent or manipulated. The source link depends on the local PDF remaining at its recorded path.

## Create another trace

Install the tested dependencies if needed, then run from the repository folder:

```powershell
python -m pip install -r requirements.txt
python -m docforensics.trace '..\output\pdf\ocr_assignment_dataset\manifests\A01.json' --document-id A01-D03 --page 1 --box 0.31 0.215 0.66 0.245 --output '..\output\pdf\ocr_assignment_dataset\evidence\my-new-trace' --dpi 144 --observation 'Manually selected student ID area for tracing'
```

The output folder must be new. The tool refuses to overwrite an existing bundle or place evidence inside the project checkout or the source PDF folder. It writes the viewer last; if writing is interrupted and no viewer exists, choose a new folder and recreate the bundle rather than treating incomplete files as finished output.

## Coordinate rules and source integrity

Regions use a 1-based page number and normalized coordinates from 0 to 1, starting at the top-left of the displayed page. Rotation and PDF crop settings are already reflected in the rendered page image. Pixel crops round outward to cover the selected region, with right and bottom edges exclusive. A rounding difference of less than one pixel per edge is expected between resolutions.

The viewer uses an SVG with the same proportions as the source image, keeping the selected region aligned at different display sizes. The saved marked page is a separate PNG. The original PDF is opened from bytes and is never saved by the tool.

The manifest is verified first. The bytes actually rendered must match its SHA-256 digest, and the source is checked again after rendering. A source change before or during rendering stops creation. The tool limits resolution to 36–300 dpi and a maximum of 25 million rendered pixels per page. It reads the named manifest and PDF files and never opens the evaluation answer key.

## Bundle contents

| File | Purpose |
| --- | --- |
| `index.html` | Local viewer with source links, region highlight, and size control |
| `trace.json` | Case and manual finding IDs, source document metadata and hash, page, normalized region, rendered dimensions, pixel crop, and audit event |
| `source-page.png` | The rendered source page without an added highlight |
| `marked-page.png` | A separate rendering with the selected region marked |
| `evidence-crop.png` | Unmodified rendered pixels from the selected region |

These files contain source-derived information and stay local until their sharing rights are confirmed. They are not an investigation dossier.

## Verification

Install test dependencies with `python -m pip install -r requirements-dev.txt`, then run `python -m unittest discover -s tests -v`. The 62 tests cover the shared foundation plus upload validation, page rendering, manual trace creation, source hashes, request origin checks, storage boundaries, and changed-source handling. Trace checks also cover crops and marked pixels, page two, rotation, PDF crop settings, multiple resolutions, invalid IDs/pages/resolutions, overwrite prevention, escaped viewer text, and answer-key isolation.

The upload screen was tested in a real headless browser with a chosen dataset PDF: upload, mouse-drawn region, observation, trace creation, and matching served-PDF SHA-256 all passed. A seven-page PDF allowed page two to be selected; changing the file cleared the old selection and result. An invalid PDF showed a friendly error. The run reported zero script errors, and screenshots of the empty screen and selected region were visually inspected.

The A01 example was generated at 72 and 144 dpi. A headless browser checked alignment at 50, 100, and 150 percent in 1280-pixel and 600-pixel windows, verified the source button and local PDF link, and reported zero script errors. Marked-page, crop, desktop, and narrow-window images were also visually inspected. Source verification still reports three unchanged PDFs.
