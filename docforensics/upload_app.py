"""Local document ingestion and manual PDF evidence selection."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.parse import unquote
from uuid import uuid4

import pymupdf
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .manifest import build_manifest, load_verified_manifest, write_manifest
from .models import SourceRegion
from .trace import _viewer, create_evidence_trace, render_source_page
from .ingestion import CaseStore
from .ingestion_api import ingestion_router
from .context_api import context_router
from .visual_api import visual_router


MAX_UPLOAD_BYTES = 20 * 1024 * 1024
CASE_PATTERN = re.compile(r"UP-[0-9a-f]{16}\Z")
TRACE_PATTERN = re.compile(r"[0-9a-f]{16}\Z")
ASSETS = frozenset(("index.html", "trace.json", "source-page.png", "marked-page.png", "evidence-crop.png"))
DEFAULT_DATA = Path(__file__).resolve().parents[2] / "output" / "local-upload-viewer"


class TraceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(ge=1)
    box: tuple[float, float, float, float]
    observation: str = Field(min_length=1, max_length=1000)


class UploadStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        checkout = Path(__file__).resolve().parents[1]
        if self.root == checkout or checkout in self.root.parents:
            raise ValueError("upload data must be outside the project checkout")
        (self.root / "cases").mkdir(parents=True, exist_ok=True)

    def upload(self, data: bytes, filename: str) -> dict:
        if not data or len(data) > MAX_UPLOAD_BYTES:
            raise ValueError("Choose a nonempty PDF no larger than 20 MB")
        if not filename or len(filename) > 240 or "/" in filename or "\\" in filename or Path(filename).suffix.lower() != ".pdf":
            raise ValueError("Choose a PDF file with a plain filename")
        try:
            with pymupdf.open(stream=data, filetype="pdf") as pdf:
                if not pdf.is_pdf or pdf.needs_pass or not 1 <= pdf.page_count <= 200:
                    raise ValueError("Choose an unlocked PDF containing 1 to 200 pages")
                page_count = pdf.page_count
        except RuntimeError as exc:
            raise ValueError("This file is not a readable PDF") from exc

        case_id = "UP-" + uuid4().hex[:16]
        folder = self.root / "cases" / case_id
        source = folder / "pdfs"
        source.mkdir(parents=True, exist_ok=False)
        safe_stem = re.sub(r"[^A-Za-z0-9._-]", "_", filename[:-4])[:80] or "document"
        stored_name = "source-" + safe_stem + ".pdf"
        with (source / stored_name).open("xb") as stream:
            stream.write(data)
        write_manifest(build_manifest(case_id, source, [stored_name]), folder / "manifest.json")
        metadata = {"case_id": case_id, "document_id": case_id + "-D01", "filename": filename,
                    "pages": page_count, "sha256": hashlib.sha256(data).hexdigest()}
        (folder / "upload.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        return metadata

    def case_folder(self, case_id: str) -> Path:
        if not CASE_PATTERN.fullmatch(case_id):
            raise HTTPException(404, "Upload not found")
        folder = (self.root / "cases" / case_id).resolve()
        if folder.parent != self.root / "cases" or not folder.is_dir():
            raise HTTPException(404, "Upload not found")
        return folder

    def read_source(self, case_id: str):
        folder = self.case_folder(case_id)
        try:
            manifest_path = folder / "manifest.json"
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if Path(payload["source_directory"]).resolve() != folder / "pdfs":
                raise ValueError("source folder mismatch")
            verified = load_verified_manifest(manifest_path)
            if verified.case.case_id != case_id or len(verified.case.documents) != 1:
                raise ValueError("case mismatch")
            document = verified.case.documents[0]
            source_path = verified.source_directory / document.filename
            data = source_path.read_bytes()
            if hashlib.sha256(data).hexdigest() != document.content_sha256:
                raise ValueError("source hash mismatch")
            return folder, document, data
        except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
            raise HTTPException(409, "The stored PDF changed or cannot be read. Upload it again.") from exc

    def page_image(self, case_id: str, page: int) -> bytes:
        _, _, data = self.read_source(case_id)
        image = render_source_page(data, page)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def trace(self, case_id: str, request: TraceRequest) -> dict:
        folder, document, _ = self.read_source(case_id)
        trace_id = uuid4().hex[:16]
        output = folder / "traces" / trace_id
        bundle = create_evidence_trace(folder / "manifest.json", document.document_id,
            SourceRegion(request.page, *request.box), output, observation=request.observation)
        record = json.loads(bundle.record_path.read_text(encoding="utf-8"))
        source_path = folder / "pdfs" / document.filename
        bundle.index_path.write_text(_viewer(record, source_path,
            source_href=f"/api/cases/{case_id}/pdf#page={request.page}", upload_href="/"), encoding="utf-8")
        return {"viewer_url": f"/api/cases/{case_id}/traces/{trace_id}/index.html", "manual_selection": True}

    def asset(self, case_id: str, trace_id: str, filename: str) -> Path:
        folder = self.case_folder(case_id)
        if not TRACE_PATTERN.fullmatch(trace_id) or filename not in ASSETS:
            raise HTTPException(404, "Evidence file not found")
        trace_folder = (folder / "traces" / trace_id).resolve()
        file = (trace_folder / filename).resolve()
        if trace_folder.parent != folder / "traces" or file.parent != trace_folder or not file.is_file():
            raise HTTPException(404, "Evidence file not found")
        return file


def create_app(data_directory: Path = DEFAULT_DATA) -> FastAPI:
    store = UploadStore(data_directory)
    app = FastAPI(title="Local document workspace", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    app.state.case_store = CaseStore(data_directory)
    app.include_router(ingestion_router(app.state.case_store))
    app.include_router(context_router(app.state.case_store))
    app.include_router(visual_router(app.state.case_store))
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        if request.method == "POST":
            origin = request.headers.get("origin")
            if request.headers.get("x-local-upload") != "1" or (origin and origin != str(request.base_url).rstrip("/")):
                return JSONResponse({"detail": "Use the local upload screen"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ValueError)
    async def invalid_input(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/", response_class=HTMLResponse)
    def home():
        return (Path(__file__).with_name("upload_page.html")).read_text(encoding="utf-8")

    @app.get("/ingest", response_class=HTMLResponse)
    def ingestion_home():
        return Path(__file__).with_name("ingestion_page.html").read_text(encoding="utf-8")

    @app.get("/extract", response_class=HTMLResponse)
    def extraction_home():
        return Path(__file__).with_name("extraction_page.html").read_text(encoding="utf-8")

    @app.get('/context', response_class=HTMLResponse)
    def contextual_home():
        return Path(__file__).with_name('context_page.html').read_text(encoding='utf-8')

    @app.get('/visual',response_class=HTMLResponse)
    def visual_home():
        return Path(__file__).with_name('visual_page.html').read_text(encoding='utf-8')

    @app.get("/api/health")
    def health():
        return {"status": "ready", "mode": "manual_evidence", "upload": True}

    @app.post("/api/upload")
    async def upload(request: Request):
        filename = unquote(request.headers.get("x-filename", ""))
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) < 0 or int(content_length) > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Choose a PDF no larger than 20 MB")
            except ValueError as exc:
                raise HTTPException(400, "Invalid upload length") from exc
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "Choose a PDF no larger than 20 MB")
        return await run_in_threadpool(store.upload, bytes(data), filename)

    @app.get("/api/cases/{case_id}/pages/{page}")
    def page_image(case_id: str, page: int):
        return Response(store.page_image(case_id, page), media_type="image/png")

    @app.get("/api/cases/{case_id}/pdf")
    def source_pdf(case_id: str):
        _, document, data = store.read_source(case_id)
        return Response(data, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{document.filename}"'})

    @app.post("/api/cases/{case_id}/trace")
    def trace(case_id: str, payload: TraceRequest):
        return store.trace(case_id, payload)

    @app.get("/api/cases/{case_id}/traces/{trace_id}/{filename}")
    def evidence_asset(case_id: str, trace_id: str, filename: str):
        return FileResponse(store.asset(case_id, trace_id, filename))

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    app = create_app(args.data_dir)
    print(f"Local upload screen: http://127.0.0.1:{args.port}", flush=True)
    print(f"Uploaded copies and manual traces stay in {args.data_dir.resolve()}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, proxy_headers=False, access_log=False)


if __name__ == "__main__":
    main()
