import json
import tempfile
import unittest
from pathlib import Path

import pymupdf

from docforensics.manifest import build_manifest, verify_manifest, write_manifest


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        # Use the checkout's parent: the manifest is intentionally forbidden
        # inside a Git checkout, and this also works in restricted sandboxes.
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "pdfs"
        self.source.mkdir()
        self.pdf_path = self.source / "sample_001.pdf"
        with pymupdf.open() as pdf:
            pdf.new_page()
            pdf.save(self.pdf_path)

    def test_manifest_identifies_unchanged_pdf_and_detects_tampering(self) -> None:
        before = self.pdf_path.read_bytes()
        manifest = build_manifest("A01", self.source, ["sample_001.pdf"])
        self.assertEqual(self.pdf_path.read_bytes(), before)
        self.assertEqual(manifest["documents"][0]["document_id"], "A01-D01")
        self.assertEqual(manifest["documents"][0]["page_count"], 1)

        output = self.root / "manifests" / "A01.json"
        write_manifest(manifest, output)
        case = verify_manifest(output)
        self.assertEqual(case.documents[0].content_sha256, manifest["documents"][0]["content_sha256"])

        self.pdf_path.write_bytes(before + b"changed")
        with self.assertRaisesRegex(ValueError, "file size changed"):
            verify_manifest(output)

        # A size-only check would miss this change; the digest must catch it.
        changed = bytearray(before)
        changed[-1] ^= 1
        self.pdf_path.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "file hash changed"):
            verify_manifest(output)

    def test_existing_manifest_is_not_replaced(self) -> None:
        manifest = build_manifest("A01", self.source, ["sample_001.pdf"])
        output = self.root / "A01.json"
        write_manifest(manifest, output)
        original = output.read_bytes()
        with self.assertRaises(FileExistsError):
            write_manifest(manifest, output)
        self.assertEqual(output.read_bytes(), original)

    def test_unserializable_manifest_does_not_leave_partial_file(self) -> None:
        output = self.root / "A01.json"
        with self.assertRaises(TypeError):
            write_manifest({"unsupported": object()}, output)
        self.assertFalse(output.exists())

    def test_changed_document_id_is_rejected(self) -> None:
        manifest = build_manifest("A01", self.source, ["sample_001.pdf"])
        manifest["documents"][0]["document_id"] = "wrong-id"
        output = self.root / "A01.json"
        write_manifest(manifest, output)
        with self.assertRaisesRegex(ValueError, "document ID"):
            verify_manifest(output)

    def test_duplicate_file_record_is_rejected(self) -> None:
        manifest = build_manifest("A01", self.source, ["sample_001.pdf"])
        duplicate = dict(manifest["documents"][0], document_id="A01-D02")
        manifest["documents"].append(duplicate)
        output = self.root / "A01.json"
        write_manifest(manifest, output)
        with self.assertRaisesRegex(ValueError, "listed more than once"):
            verify_manifest(output)

    def test_malformed_manifest_is_rejected_cleanly(self) -> None:
        output = self.root / "malformed.json"
        output.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "JSON object"):
            verify_manifest(output)

    def test_answer_key_is_not_read_or_embedded(self) -> None:
        (self.root / "ground_truth.csv").write_text("secret,label\nA01,altered\n", encoding="utf-8")
        manifest = build_manifest("A01", self.source, ["sample_001.pdf"])
        serialized = json.dumps(manifest)
        self.assertNotIn("altered", serialized)
        self.assertNotIn("ground_truth", serialized)

    def test_refuses_to_write_manifest_inside_git_checkout(self) -> None:
        manifest = build_manifest("A01", self.source, ["sample_001.pdf"])
        checkout = Path(__file__).resolve().parents[1]
        with self.assertRaisesRegex(ValueError, "outside the project checkout"):
            write_manifest(manifest, checkout / "tmp" / "A01.json")

    def test_refuses_to_read_source_pdf_inside_project_checkout(self) -> None:
        checkout = Path(__file__).resolve().parents[1]
        with self.assertRaisesRegex(ValueError, "outside the project checkout"):
            build_manifest("A01", checkout, ["README.md"])

    def test_rejects_file_path_outside_source_folder(self) -> None:
        with self.assertRaisesRegex(ValueError, "PDF filename"):
            build_manifest("A01", self.source, ["../sample_001.pdf"])


if __name__ == "__main__":
    unittest.main()
