import builtins
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from PIL import Image

from docforensics.manifest import build_manifest, load_verified_manifest, verify_manifest, write_manifest
from docforensics.models import ReviewState, SourceRegion
from docforensics.trace import create_evidence_trace, region_to_pixels


class EvidenceTraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "pdfs"
        self.source.mkdir()
        self.pdf = self.source / "source.pdf"
        with pymupdf.open() as document:
            page = document.new_page(width=200, height=100)
            page.draw_rect(pymupdf.Rect(0, 0, 100, 100), color=None, fill=(1, 0, 0))
            page = document.new_page(width=200, height=100)
            page.draw_rect(page.rect, color=None, fill=(0, 0, 1))
            document.save(self.pdf)
        self.manifest = self.root / "case.json"
        write_manifest(build_manifest("TEST", self.source, ["source.pdf"]), self.manifest)
        self.region = SourceRegion(1, 0.1, 0.1, 0.4, 0.8)

    def trace(self, name="trace", **kwargs):
        return create_evidence_trace(self.manifest, "TEST-D01", kwargs.pop("region", self.region),
                                     self.root / name, **kwargs)

    def test_bundle_links_case_finding_page_pixels_and_source_hash(self):
        original = self.pdf.read_bytes()
        bundle = self.trace(dpi=72)
        record = json.loads(bundle.record_path.read_text(encoding="utf-8"))
        finding = bundle.case.findings[0]
        self.assertEqual(finding.evidence[0].document_id, "TEST-D01")
        self.assertEqual(finding.evidence[0].region, self.region)
        self.assertEqual(finding.review_state, ReviewState.PENDING)
        self.assertTrue(record["demo_only"])
        self.assertEqual(record["selection_method"], "manual")
        self.assertEqual(record["rendered_input_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(record["pixel_box"], [20, 10, 80, 80])
        with Image.open(bundle.index_path.parent / "evidence-crop.png") as crop:
            self.assertEqual(crop.size, (60, 70))
            self.assertEqual(crop.getpixel((30, 30)), (255, 0, 0))
        with Image.open(bundle.index_path.parent / "marked-page.png") as marked:
            self.assertEqual(marked.getpixel((20, 10)), (190, 20, 35))
        self.assertEqual(self.pdf.read_bytes(), original)
        self.assertEqual(len(verify_manifest(self.manifest).documents), 1)
        self.assertIn("#page=1", bundle.index_path.read_text(encoding="utf-8"))

    def test_same_region_scales_with_resolution_and_viewer_coordinates(self):
        records = []
        for dpi in (72, 144):
            bundle = self.trace(f"trace-{dpi}", dpi=dpi)
            record = json.loads(bundle.record_path.read_text(encoding="utf-8"))
            records.append(record)
            html = bundle.index_path.read_text(encoding="utf-8")
            self.assertIn(f'viewBox="0 0 {record["rendered_page"]["width"]} {record["rendered_page"]["height"]}"', html)
            self.assertIn('vector-effect="non-scaling-stroke"', html)
            self.assertIn('id="zoom"', html)
        self.assertEqual(records[1]["pixel_box"], [value * 2 for value in records[0]["pixel_box"]])

    def test_selected_page_two_uses_page_two_pixels(self):
        bundle = self.trace(region=SourceRegion(2, 0.1, 0.1, 0.4, 0.8), dpi=72)
        with Image.open(bundle.index_path.parent / "evidence-crop.png") as crop:
            self.assertEqual(crop.getpixel((30, 30)), (0, 0, 255))
        self.assertIn("#page=2", bundle.index_path.read_text(encoding="utf-8"))

    def test_rotated_and_cropped_page_use_displayed_coordinates(self):
        for rotation, cropbox in ((90, None), (0, pymupdf.Rect(50, 0, 150, 100))):
            with self.subTest(rotation=rotation):
                filename = f"variant-{rotation}.pdf"
                path = self.source / filename
                with pymupdf.open(self.pdf) as document:
                    document[0].set_rotation(rotation)
                    if cropbox:
                        document[0].set_cropbox(cropbox)
                    document.save(path)
                manifest = self.root / f"variant-{rotation}.json"
                write_manifest(build_manifest("VAR", self.source, [filename]), manifest)
                region = SourceRegion(1, 0.1, 0.1, 0.4, 0.4)
                bundle = create_evidence_trace(manifest, "VAR-D01", region, self.root / f"variant-out-{rotation}", dpi=72)
                with Image.open(bundle.index_path.parent / "evidence-crop.png") as crop:
                    self.assertEqual(crop.getpixel((crop.width // 2, crop.height // 2)), (255, 0, 0))

    def test_invalid_document_page_and_resolution_produce_no_bundle(self):
        for document_id, region, dpi in (("missing", self.region, 72),
                                         ("TEST-D01", SourceRegion(3, 0, 0, 1, 1), 72),
                                         ("TEST-D01", self.region, 1000)):
            with self.subTest(document_id=document_id, page=region.page_number, dpi=dpi):
                with self.assertRaises(ValueError):
                    create_evidence_trace(self.manifest, document_id, region, self.root / "invalid", dpi=dpi)
                self.assertFalse((self.root / "invalid").exists())

    def test_outputs_cannot_overwrite_source_project_or_existing_bundle(self):
        project = Path(__file__).resolve().parents[1]
        for output in (self.source / "evidence", project / "tmp" / "evidence"):
            with self.subTest(output=output):
                with self.assertRaises(ValueError):
                    create_evidence_trace(self.manifest, "TEST-D01", self.region, output)
        bundle = self.trace(dpi=72)
        original_record = bundle.record_path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.trace(dpi=144)
        self.assertEqual(bundle.record_path.read_bytes(), original_record)

    def test_source_change_prevents_output(self):
        self.pdf.write_bytes(self.pdf.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "file size changed"):
            self.trace()
        self.assertFalse((self.root / "trace").exists())

    def test_source_change_after_verification_is_also_rejected(self):
        verified = load_verified_manifest(self.manifest)
        self.pdf.write_bytes(self.pdf.read_bytes() + b"changed")
        with patch("docforensics.trace.load_verified_manifest", return_value=verified):
            with self.assertRaisesRegex(ValueError, "source changed after manifest verification"):
                self.trace()
        self.assertFalse((self.root / "trace").exists())

    def test_large_render_is_rejected_before_allocating_page_pixels(self):
        huge = self.source / "huge.pdf"
        with pymupdf.open() as document:
            document.new_page(width=10000, height=10000)
            document.save(huge)
        manifest = self.root / "huge.json"
        write_manifest(build_manifest("HUGE", self.source, ["huge.pdf"]), manifest)
        with self.assertRaisesRegex(ValueError, "too large"):
            create_evidence_trace(manifest, "HUGE-D01", self.region, self.root / "huge-output", dpi=300)
        self.assertFalse((self.root / "huge-output").exists())

    def test_viewer_escapes_manual_text(self):
        text = '<script>alert("fixture")</script>'
        bundle = self.trace(observation=text, dpi=72)
        html = bundle.index_path.read_text(encoding="utf-8")
        self.assertNotIn(text, html)
        self.assertIn("&lt;script&gt;", html)

    def test_answer_key_is_not_opened(self):
        (self.root / "ground_truth.csv").write_text("evaluation only", encoding="utf-8")

        def guard(opener):
            def guarded(file, *args, **kwargs):
                if isinstance(file, (str, os.PathLike)) and Path(file).name == "ground_truth.csv":
                    self.fail("evidence trace tried to read the answer key")
                return opener(file, *args, **kwargs)
            return guarded

        with patch("builtins.open", guard(builtins.open)), patch("io.open", guard(io.open)):
            self.trace(dpi=72)

    def test_full_page_and_subpixel_boxes_stay_inside_image(self):
        self.assertEqual(region_to_pixels(SourceRegion(1, 0, 0, 1, 1), 200, 100), (0, 0, 200, 100))
        box = region_to_pixels(SourceRegion(1, 0.99999, 0.99999, 1, 1), 200, 100)
        self.assertEqual(box, (199, 99, 200, 100))


if __name__ == "__main__":
    unittest.main()
