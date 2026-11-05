import builtins
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf
from PIL import Image

from docforensics.ingestion import CaseStore, IncomingFile, SourceChangedError


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = CaseStore(self.root / "storage")
        with pymupdf.open() as document:
            document.new_page(width=200, height=100)
            document.new_page(width=200, height=100)
            self.pdf = document.tobytes()
        self.png = self.image("PNG", "blue")
        self.jpeg = self.image("JPEG", "red")

    def image(self, format, color):
        stream = io.BytesIO()
        Image.new("RGB", (20, 30), color).save(stream, format=format)
        return stream.getvalue()

    def ingest(self, *items):
        return self.store.ingest(tuple(IncomingFile(name, content) for name, content in items))

    def test_mixed_packet_preserves_bytes_and_assigns_document_and_page_ids(self):
        inputs = (("scan.pdf", self.pdf), ("photo.png", self.png), ("camera.jpeg", self.jpeg))
        original = self.root / "original.pdf"
        original.write_bytes(self.pdf)
        case = self.ingest(*inputs)
        self.assertEqual(case["status"], "ready")
        self.assertEqual([d["page_count"] for d in case["documents"]], [2, 1, 1])
        self.assertEqual([u["status"] for u in case["uploads"]], ["accepted"] * 3)
        for index, (document, (_, content)) in enumerate(zip(case["documents"], inputs), 1):
            self.assertEqual(document["document_id"], f"{case['case_id']}-D{index:02d}")
            self.assertEqual(document["content_sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual(document["pages"][0]["page_id"], document["document_id"] + "-P0001")
            self.assertEqual(self.store.read_original(case["case_id"], document["document_id"])[1], content)
        self.assertEqual(case["documents"][0]["pages"][1]["page_number"], 2)
        self.assertEqual(original.read_bytes(), self.pdf)
        restored = CaseStore(self.store.root).get_case(case["case_id"])
        self.assertEqual(restored, case)
        self.assertEqual(len(self.store.as_case(case["case_id"]).documents), 3)

    def test_duplicate_bytes_appear_once_and_link_to_the_accepted_document(self):
        case = self.ingest(("one.pdf", self.pdf), ("copy.pdf", self.pdf))
        self.assertEqual(len(case["documents"]), 1)
        self.assertEqual(case["uploads"][1]["status"], "duplicate")
        self.assertEqual(case["uploads"][1]["duplicate_of"], case["documents"][0]["document_id"])
        self.assertEqual(len(list((self.store.root / "cases" / case["case_id"] / "originals").iterdir())), 1)

    def test_same_filename_with_different_bytes_does_not_overwrite(self):
        second = self.image("PNG", "green")
        case = self.ingest(("same.png", self.png), ("same.png", second))
        self.assertEqual(len(case["documents"]), 2)
        for document, expected in zip(case["documents"], (self.png, second)):
            self.assertEqual(self.store.read_original(case["case_id"], document["document_id"])[1], expected)
        self.assertNotEqual(*[d["stored_filename"] for d in case["documents"]])

    def test_reupload_creates_a_new_case_and_leaves_the_existing_one_unchanged(self):
        first = self.ingest(("one.pdf", self.pdf))
        saved = self.store.root / "cases" / first["case_id"] / "case.json"
        snapshot = saved.read_bytes()
        second = self.ingest(("one.pdf", self.pdf))
        self.assertNotEqual(first["case_id"], second["case_id"])
        self.assertEqual(saved.read_bytes(), snapshot)
        with patch("docforensics.ingestion.uuid4", return_value=SimpleNamespace(hex=first["case_id"][5:])):
            with self.assertRaises(FileExistsError):
                self.ingest(("one.pdf", self.pdf))
        self.assertEqual(saved.read_bytes(), snapshot)
        self.assertEqual(self.store.get_case(first["case_id"]), first)

    def test_bad_files_do_not_hide_valid_documents_and_are_not_stored(self):
        case = self.ingest(("ok.pdf", self.pdf), ("notes.txt", b"text"), ("bad.pdf", b"broken"),
                           ("empty.png", b""), ("../escape.pdf", self.pdf), ("wrong.png", self.jpeg))
        self.assertEqual(case["status"], "partial")
        self.assertEqual(len(case["documents"]), 1)
        self.assertEqual([u["error"]["code"] for u in case["uploads"][1:]],
                         ["unsupported_format", "unreadable_document", "empty_file", "invalid_filename", "format_mismatch"])
        folder = self.store.root / "cases" / case["case_id"] / "originals"
        self.assertEqual(len(list(folder.iterdir())), 1)
        rejected = self.ingest(("bad.pdf", b"bad"))
        self.assertEqual(rejected["status"], "no_accepted_documents")
        self.assertEqual(self.store.as_case(rejected["case_id"]).documents, ())

    def test_protected_pdf_and_page_file_and_image_limits_are_explicit(self):
        with pymupdf.open(stream=self.pdf, filetype="pdf") as document:
            locked = document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
        self.assertEqual(self.ingest(("locked.pdf", locked))["uploads"][0]["error"]["code"], "password_required")
        with patch("docforensics.ingestion.MAX_PAGES", 1):
            self.assertEqual(self.ingest(("two.pdf", self.pdf))["uploads"][0]["error"]["code"], "page_limit")
        with patch("docforensics.ingestion.MAX_FILE_BYTES", 10):
            self.assertEqual(self.ingest(("large.pdf", self.pdf))["uploads"][0]["error"]["code"], "file_too_large")
        with patch("docforensics.ingestion.MAX_IMAGE_PIXELS", 10):
            self.assertEqual(self.ingest(("large.png", self.png))["uploads"][0]["error"]["code"], "image_too_large")

    def test_empty_excessive_or_oversized_batches_do_not_create_a_case(self):
        with self.assertRaises(ValueError):
            self.store.ingest(())
        with self.assertRaises(ValueError):
            self.store.ingest(tuple(IncomingFile("a.pdf", self.pdf) for _ in range(21)))
        with patch("docforensics.ingestion.MAX_BATCH_BYTES", 10):
            with self.assertRaises(ValueError):
                self.ingest(("a.pdf", self.pdf))
        self.assertEqual(list((self.store.root / "cases").iterdir()), [])

    def test_modified_source_or_page_identity_is_rejected(self):
        case = self.ingest(("a.pdf", self.pdf))
        document = case["documents"][0]
        folder = self.store.root / "cases" / case["case_id"]
        source = folder / "originals" / document["stored_filename"]
        source.write_bytes(self.pdf[:-1] + bytes([self.pdf[-1] ^ 1]))
        with self.assertRaises(SourceChangedError):
            self.store.get_case(case["case_id"])
        source.write_bytes(self.pdf)
        case["documents"][0]["pages"][0]["page_id"] = "wrong"
        (folder / "case.json").write_text(json.dumps(case), encoding="utf-8")
        with self.assertRaises(SourceChangedError):
            self.store.get_case(case["case_id"])

    def test_storage_inside_checkout_and_cross_case_document_access_are_rejected(self):
        with self.assertRaises(ValueError):
            CaseStore(Path(__file__).resolve().parents[1] / "uploads")
        case = self.ingest(("one.pdf", self.pdf))
        with self.assertRaises(FileNotFoundError):
            self.store.read_original(case["case_id"], "another-document")
        with self.assertRaises(FileNotFoundError):
            self.store.get_case("../outside")

    def test_failed_storage_does_not_publish_a_case_record(self):
        original_open = Path.open

        def fail_write(path, *args, **kwargs):
            if path.parent.name == "originals" and args and args[0] == "xb":
                raise OSError("simulated storage failure")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", fail_write):
            with self.assertRaises(OSError):
                self.ingest(("one.pdf", self.pdf))
        self.assertFalse(list(self.store.root.glob("cases/*/case.json")))

    def test_ingestion_does_not_read_evaluation_labels(self):
        original_open = builtins.open

        def guard(file, *args, **kwargs):
            if isinstance(file, (str, os.PathLike)) and Path(file).name == "ground_truth.csv":
                self.fail("runtime ingestion opened evaluation labels")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", guard):
            self.ingest(("one.pdf", self.pdf))


if __name__ == "__main__":
    unittest.main()
