# Dependencies and acknowledgments

The [setup guide](setup.md) installs the pinned direct packages from `requirements.txt`. The project runs locally and uses the following components:

| Component | Role | Upstream terms and source |
| --- | --- | --- |
| PyMuPDF and MuPDF | PDF text, page rendering, integrated Tesseract OCR | [Artifex license information](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright). The package declares AGPL-3.0 or an Artifex commercial license. |
| Tesseract English tessdata_fast | Local language model for scanned printed text | [Pinned model source](https://github.com/tesseract-ocr/tessdata_fast/tree/87416418657359cb625c412a48b6e1d6d41c29bd) and [Apache 2.0 license](https://github.com/tesseract-ocr/tessdata_fast/blob/87416418657359cb625c412a48b6e1d6d41c29bd/LICENSE). |
| Pillow | Image validation and processing | [Pillow license](https://github.com/python-pillow/Pillow/blob/main/LICENSE). Installed package declares MIT-CMU. |
| FastAPI and Uvicorn | Local API and HTTP server | [FastAPI MIT license](https://github.com/fastapi/fastapi/blob/master/LICENSE) and [Uvicorn BSD-3-Clause license](https://github.com/Kludex/uvicorn/blob/main/LICENSE.md). |
| python-multipart | Multipart upload parsing | [Apache 2.0 license](https://github.com/Kludex/python-multipart/blob/master/LICENSE.txt). |
| ReportLab and Bitstream Vera | PDF layout and embedded report typeface | [ReportLab package and BSD terms](https://pypi.org/project/reportlab/4.4.9/). The installed package includes its license and the Bitstream Vera font notice. |
| HTTPX | Development API test client | [HTTPX BSD-3-Clause license](https://github.com/encode/httpx/blob/master/LICENSE.md). |

The project source has no selected project-wide license. This notice identifies dependencies and their terms and grants no additional permissions. Confirm the project's distribution terms before broader release, especially the PyMuPDF/MuPDF terms. The handover does not bundle dependency wheels, installed packages, model weights, organizer documents, or private cases.

The reproducible dataset uses original synthetic forms and invented identities. The team may use those fixtures for the hackathon demonstration. The supplied 15-PDF dataset was used in local evaluation and is excluded from the handover because its redistribution rights have not been established here.

Codex assisted with implementation, tests, and documentation. The runtime performs local OCR and deterministic comparisons, rendering, visual checks, and reporting. It does not call Codex or a hosted language model. Describe the actual AI assistance and external components during evaluation if requested.
