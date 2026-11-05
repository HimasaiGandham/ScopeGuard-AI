"""Bounded multipart uploads and read-only access to ingested cases."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from .ingestion import CaseStore, IncomingFile, MAX_BATCH_BYTES, MAX_FILE_BYTES, MAX_FILES, SourceChangedError


def ingestion_router(store: CaseStore) -> APIRouter:
    router = APIRouter(prefix="/api/ingestion/cases")

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
