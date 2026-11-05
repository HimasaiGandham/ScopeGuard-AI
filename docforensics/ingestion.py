"""Accept a document packet while preserving its original file identities."""

from __future__ import annotations

import hashlib
import io
import json
import re
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pymupdf
from PIL import Image

from .models import Document, InvestigationCase


MAX_FILES = 20
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_BATCH_BYTES = 100 * 1024 * 1024
MAX_PAGES = 200
MAX_IMAGE_PIXELS = 25_000_000
CASE_ID = re.compile(r"CASE-[0-9a-f]{32}\Z")
FORMATS = {".pdf": "application/pdf", ".png": "image/png",
           ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


@dataclass(frozen=True, slots=True)
class IncomingFile:
    filename: str
    content: bytes


class SourceChangedError(ValueError):
    """A stored case or original can no longer be verified."""


class FileRejected(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _inspect(item: IncomingFile) -> tuple[str, int]:
    filename, content = item.filename, item.content
    if (not filename or len(filename) > 240 or filename[-1:] in (" ", ".")
            or any(ord(c) < 32 or c in '/\\:<>"|?*' for c in filename)):
        raise FileRejected("invalid_filename", "Choose a file with a plain filename, without a folder path.")
    suffix = Path(filename).suffix.lower()
    if suffix not in FORMATS:
        raise FileRejected("unsupported_format", "Supported files are PDF, PNG, and JPEG.")
    if not content:
        raise FileRejected("empty_file", "This file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise FileRejected("file_too_large", "Each file must be no larger than 20 MiB.")
    try:
        if suffix == ".pdf":
            with pymupdf.open(stream=content, filetype="pdf") as pdf:
                if not pdf.is_pdf:
                    raise FileRejected("format_mismatch", "The file contents do not match the PDF extension.")
                if pdf.needs_pass:
                    raise FileRejected("password_required", "Upload an unlocked PDF.")
                if not 1 <= pdf.page_count <= MAX_PAGES:
                    raise FileRejected("page_limit", "A PDF must contain 1 to 200 pages.")
                return FORMATS[suffix], pdf.page_count
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                expected = "PNG" if suffix == ".png" else "JPEG"
                if image.format != expected:
                    raise FileRejected("format_mismatch", "The image contents do not match its extension.")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise FileRejected("image_too_large", "An image must contain no more than 25 million pixels.")
                if getattr(image, "n_frames", 1) != 1:
                    raise FileRejected("unsupported_image", "Upload a single-frame PNG or JPEG.")
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                image.load()
        return FORMATS[suffix], 1
    except FileRejected:
        raise
    except (RuntimeError, OSError, ValueError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise FileRejected("unreadable_document", "This file is damaged or cannot be read as its selected format.") from exc


class CaseStore:
    """Write new immutable cases, with exclusive files and a final case record."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        checkout = Path(__file__).resolve().parents[1]
        if self.root == checkout or checkout in self.root.parents:
            raise ValueError("case storage must be outside the project checkout")
        (self.root / "cases").mkdir(parents=True, exist_ok=True)

    def ingest(self, files: tuple[IncomingFile, ...]) -> dict:
        if not isinstance(files, tuple) or not 1 <= len(files) <= MAX_FILES:
            raise ValueError("Select between 1 and 20 files for one case.")
        if any(not isinstance(item, IncomingFile) or not isinstance(item.filename, str)
               or not isinstance(item.content, bytes) for item in files):
            raise ValueError("Uploads must contain filenames and bytes.")
        if sum(len(item.content) for item in files) > MAX_BATCH_BYTES:
            raise ValueError("The combined file size must not exceed 100 MiB.")

        case_id = "CASE-" + uuid4().hex
        documents, uploads, originals, hashes = [], [], [], {}
        for index, item in enumerate(files, start=1):
            result = {"input_index": index, "filename": item.filename}
            try:
                media_type, pages = _inspect(item)
            except FileRejected as exc:
                uploads.append(dict(result, status="rejected", error={"code": exc.code, "message": str(exc)}))
                continue
            digest = hashlib.sha256(item.content).hexdigest()
            if digest in hashes:
                uploads.append(dict(result, status="duplicate", duplicate_of=hashes[digest],
                                    message="Identical file bytes are already included in this case."))
                continue
            document_id = f"{case_id}-D{len(documents) + 1:02d}"
            stored_name = document_id + Path(item.filename).suffix.lower()
            documents.append({"document_id": document_id, "filename": item.filename,
                              "stored_filename": stored_name, "media_type": media_type,
                              "size_bytes": len(item.content), "content_sha256": digest, "page_count": pages,
                              "pages": [{"page_id": f"{document_id}-P{page:04d}", "page_number": page}
                                        for page in range(1, pages + 1)]})
            uploads.append(dict(result, status="accepted", document_id=document_id))
            hashes[digest] = document_id
            originals.append((stored_name, item.content))

        record = {"case_version": 1, "case_id": case_id,
                  "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "status": ("no_accepted_documents" if not documents else
                             "partial" if any(u["status"] == "rejected" for u in uploads) else "ready"),
                  "documents": documents, "uploads": uploads}
        self._as_case(record)
        folder = self.root / "cases" / case_id
        folder.mkdir(exist_ok=False)
        source = folder / "originals"
        source.mkdir(exist_ok=False)
        for filename, content in originals:
            with (source / filename).open("xb") as stream:
                stream.write(content)
        # Publish the record last. An interrupted folder without case.json is not a completed case.
        with (folder / "case.json").open("x", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        return record

    def _folder(self, case_id: str) -> Path:
        if not CASE_ID.fullmatch(case_id):
            raise FileNotFoundError("Case not found.")
        folder = (self.root / "cases" / case_id).resolve()
        if folder.parent != self.root / "cases" or not (folder / "case.json").is_file():
            raise FileNotFoundError("Case not found.")
        return folder

    @staticmethod
    def _as_case(record: dict) -> InvestigationCase:
        documents = []
        if record["case_version"] != 1 or not isinstance(record["uploads"], list):
            raise ValueError("unsupported case record")
        for index, document in enumerate(record["documents"], start=1):
            identifier = f"{record['case_id']}-D{index:02d}"
            suffix = Path(document["filename"]).suffix.lower()
            if (document["document_id"] != identifier or suffix not in FORMATS
                    or document["stored_filename"] != identifier + suffix
                    or document["media_type"] != FORMATS[suffix]
                    or type(document["size_bytes"]) is not int or document["size_bytes"] < 1
                    or type(document["page_count"]) is not int or not 1 <= document["page_count"] <= MAX_PAGES):
                raise ValueError("invalid document identity")
            expected = [{"page_id": f"{identifier}-P{page:04d}", "page_number": page}
                        for page in range(1, document["page_count"] + 1)]
            if document["pages"] != expected:
                raise ValueError("invalid page identity")
            documents.append(Document(identifier, document["filename"], page_count=document["page_count"],
                                      content_sha256=document["content_sha256"]))
        return InvestigationCase(record["case_id"], tuple(documents))

    def get_case(self, case_id: str, *, verify_sources: bool = True) -> dict:
        folder = self._folder(case_id)
        try:
            record = json.loads((folder / "case.json").read_text(encoding="utf-8"))
            if record["case_id"] != case_id:
                raise ValueError("case identity changed")
            self._as_case(record)
            if verify_sources:
                for document in record["documents"]:
                    self._read_original(folder, document)
            return record
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise SourceChangedError("The stored case or original changed or cannot be read. Create a new case.") from exc

    def as_case(self, case_id: str) -> InvestigationCase:
        return self._as_case(self.get_case(case_id))

    @staticmethod
    def _read_original(folder: Path, document: dict) -> bytes:
        source = (folder / "originals" / document["stored_filename"]).resolve(strict=True)
        if source.parent != folder / "originals":
            raise ValueError("original path changed")
        content = source.read_bytes()
        if len(content) != document["size_bytes"] or hashlib.sha256(content).hexdigest() != document["content_sha256"]:
            raise ValueError("original fingerprint changed")
        return content

    def read_original(self, case_id: str, document_id: str) -> tuple[dict, bytes]:
        record = self.get_case(case_id, verify_sources=False)
        document = next((d for d in record["documents"] if d["document_id"] == document_id), None)
        if document is None:
            raise FileNotFoundError("Document not found in this case.")
        try:
            return document, self._read_original(self._folder(case_id), document)
        except (OSError, ValueError) as exc:
            raise SourceChangedError("The stored original changed or cannot be read. Create a new case.") from exc
