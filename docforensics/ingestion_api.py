"""Bounded multipart uploads and read-only access to ingested cases."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
import io
import os
import json
import re
from uuid import uuid4
from pathlib import Path
from PIL import Image, ImageOps
from .extraction import extract_case
from .trace import render_source_page

from .ingestion import CaseStore, IncomingFile, MAX_BATCH_BYTES, MAX_FILE_BYTES, MAX_FILES, SourceChangedError


def ingestion_router(store: CaseStore) -> APIRouter:
    router = APIRouter(prefix="/api/ingestion/cases")

    @router.post("/{case_id}/extract")
    def extract(case_id: str):
        try:
            model = os.environ.get("OCR_TESSDATA", str(Path(__file__).resolve().parents[2] / "output" / "ocr-models"))
            result = extract_case(store, case_id, tessdata=model)
            run_id = uuid4().hex
            result['run_id'] = run_id
            directory = store.root / 'cases' / case_id / 'extractions'
            directory.mkdir(exist_ok=True)
            with (directory / (run_id + '.json')).open('x', encoding='utf-8') as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
            return result
        except FileNotFoundError as exc:
            raise HTTPException(404, "Case not found") from exc
        except SourceChangedError as exc:
            raise HTTPException(409, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(500, 'Extraction result could not be saved; originals are preserved.') from exc

    @router.get('/{case_id}/extractions/{run_id}')
    def extraction_record(case_id: str, run_id: str):
        if not re.fullmatch(r'[0-9a-f]{32}', run_id):
            raise HTTPException(404, 'Extraction not found')
        try:
            store.get_case(case_id)
            return json.loads((store.root/'cases'/case_id/'extractions'/(run_id+'.json')).read_text(encoding='utf-8'))
        except FileNotFoundError as exc:
            raise HTTPException(404, 'Extraction not found') from exc
        except (SourceChangedError, ValueError) as exc:
            raise HTTPException(409, 'Saved result or source cannot be verified') from exc

    @router.get("/{case_id}/documents/{document_id}/pages/{page}")
    def page_image(case_id: str, document_id: str, page: int):
        try:
            metadata, content = store.read_original(case_id, document_id)
            if not 1 <= page <= metadata["page_count"]:
                raise HTTPException(422, "Invalid page")
            if metadata["media_type"] == "application/pdf":
                image = render_source_page(content, page)
            else:
                with Image.open(io.BytesIO(content)) as original:
                    image = ImageOps.exif_transpose(original).convert("RGB")
            output = io.BytesIO()
            image.save(output, format="PNG")
            return Response(output.getvalue(), media_type="image/png")
        except FileNotFoundError as exc:
            raise HTTPException(404, "Source not found") from exc
        except SourceChangedError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("")
    async def create_case(request: Request):
        # Reserve space for multipart headers/boundaries in addition to file bytes.
        limit = MAX_BATCH_BYTES + 1024 * 1024
        length = request.headers.get("content-length")
        if length is not None:
            try:
                size = int(length)
            except ValueError as exc:
                raise HTTPException(400, "Invalid upload length.") from exc
            if size < 0 or size > limit:
                raise HTTPException(413, "The combined upload is too large.")
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "multipart/form-data":
            raise HTTPException(415, "Use the multiple-file upload form.")
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await request.receive()
            received += len(message.get("body", b""))
            if received > limit:
                raise HTTPException(413, "The combined upload is too large.")
            return message

        bounded = Request(request.scope, receive=bounded_receive)
        async with bounded.form(max_files=MAX_FILES, max_fields=0) as form:
            items = form.multi_items()
            if not items or any(key != "files" or not isinstance(file, UploadFile) for key, file in items):
                raise HTTPException(422, "Select files using the files field.")
            files = []
            for _, file in items:
                content = await file.read(MAX_FILE_BYTES + 1)
                files.append(IncomingFile(file.filename or "", content))
            try:
                return await run_in_threadpool(store.ingest, tuple(files))
            except OSError as exc:
                raise HTTPException(500, "The case could not be saved. Check the local storage and retry as a new case.") from exc

    @router.get("/{case_id}")
    def get_case(case_id: str):
        try:
            return store.get_case(case_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except SourceChangedError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/{case_id}/documents/{document_id}/original")
    def original(case_id: str, document_id: str):
        try:
            document, content = store.read_original(case_id, document_id)
            return Response(content, media_type=document["media_type"], headers={
                "Content-Disposition": f'attachment; filename="{document["stored_filename"]}"'})
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except SourceChangedError as exc:
            raise HTTPException(409, str(exc)) from exc

    return router
