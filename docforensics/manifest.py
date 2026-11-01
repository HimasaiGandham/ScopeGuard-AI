"""Create and verify a local case manifest without reading evaluation labels."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pymupdf

from .models import Document, InvestigationCase


MANIFEST_VERSION = 1


def build_manifest(
    case_id: str, source_directory: Path, filenames: list[str]
) -> dict[str, Any]:
    """Record the exact PDFs used by one case, without copying or editing them."""

    if not case_id or not all(char.isalnum() or char in "-_" for char in case_id):
        raise ValueError("case_id must contain only letters, numbers, '-' or '_'")
    if not filenames or len(filenames) != len(set(filenames)):
        raise ValueError("provide a non-empty list of unique PDF filenames")

    source_directory = source_directory.resolve(strict=True)
    if not source_directory.is_dir():
        raise ValueError("source_directory must be a folder")
    _require_outside_git(source_directory)

    records: list[dict[str, Any]] = []
    documents: list[Document] = []
    for index, filename in enumerate(sorted(filenames), start=1):
        pdf_path = _pdf_path(source_directory, filename)
        digest_before = _sha256(pdf_path)
        with pymupdf.open(pdf_path) as pdf:
            if not pdf.is_pdf or pdf.needs_pass or pdf.page_count < 1:
                raise ValueError(f"PDF cannot be inspected: {filename}")
            page_count = pdf.page_count
        digest_after = _sha256(pdf_path)
        if digest_before != digest_after:
            raise RuntimeError(f"source file changed while inspecting it: {filename}")

        record = {
            "document_id": f"{case_id}-D{index:02d}",
            "filename": filename,
            "page_count": page_count,
            "size_bytes": pdf_path.stat().st_size,
            "content_sha256": digest_after,
        }
        records.append(record)
        documents.append(
            Document(
                document_id=record["document_id"],
                filename=filename,
                page_count=page_count,
                content_sha256=digest_after,
            )
        )

    InvestigationCase(case_id=case_id, documents=tuple(documents))
    return {
        "manifest_version": MANIFEST_VERSION,
        "case_id": case_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_directory": str(source_directory),
        "documents": records,
    }


def write_manifest(manifest: dict[str, Any], output_path: Path) -> None:
    """Write a new manifest outside this project checkout; never replace one."""

    output_path = output_path.resolve()
    _require_outside_git(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def verify_manifest(manifest_path: Path) -> InvestigationCase:
    """Recheck the exact files recorded by a local manifest."""

    with manifest_path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ValueError("unsupported manifest version")

    source_directory = Path(manifest["source_directory"]).resolve(strict=True)
    if not source_directory.is_dir():
        raise ValueError("source_directory is no longer a folder")
    _require_outside_git(source_directory)
    records = manifest["documents"]
    if not isinstance(records, list) or not records:
        raise ValueError("manifest must list at least one document")

    documents: list[Document] = []
    for record in records:
        pdf_path = _pdf_path(source_directory, record["filename"])
        if pdf_path.stat().st_size != record["size_bytes"]:
            raise ValueError(f"file size changed: {record['filename']}")
        if _sha256(pdf_path) != record["content_sha256"]:
            raise ValueError(f"file hash changed: {record['filename']}")
        with pymupdf.open(pdf_path) as pdf:
            if not pdf.is_pdf or pdf.needs_pass or pdf.page_count != record["page_count"]:
                raise ValueError(f"PDF page count or readability changed: {record['filename']}")
        documents.append(
            Document(
                document_id=record["document_id"],
                filename=record["filename"],
                page_count=record["page_count"],
                content_sha256=record["content_sha256"],
            )
        )

    return InvestigationCase(case_id=manifest["case_id"], documents=tuple(documents))


def _pdf_path(source_directory: Path, filename: str) -> Path:
    if Path(filename).name != filename or Path(filename).suffix.lower() != ".pdf":
        raise ValueError(f"expected a PDF filename without a directory: {filename}")
    pdf_path = (source_directory / filename).resolve(strict=True)
    if pdf_path.parent != source_directory or not pdf_path.is_file():
        raise ValueError(f"PDF must be a file in the source directory: {filename}")
    return pdf_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_outside_git(path: Path) -> None:
    checkout_root = Path(__file__).resolve().parents[1]
    if path == checkout_root or checkout_root in path.parents:
        raise ValueError("manifest output must be outside the project checkout")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="write a new local case manifest")
    create.add_argument("--case-id", required=True)
    create.add_argument("--source-dir", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("files", nargs="+")
    verify = commands.add_parser("verify", help="recheck files in an existing manifest")
    verify.add_argument("manifest", type=Path)
    args = parser.parse_args()

    try:
        if args.command == "create":
            manifest = build_manifest(args.case_id, args.source_dir, args.files)
            write_manifest(manifest, args.output)
            print(f"Created {args.output} with {len(manifest['documents'])} documents")
        else:
            case = verify_manifest(args.manifest)
            print(f"Verified {case.case_id}: {len(case.documents)} unchanged PDFs")
    except (FileExistsError, FileNotFoundError, KeyError, OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"Manifest error: {exc}\n")


if __name__ == "__main__":
    main()
