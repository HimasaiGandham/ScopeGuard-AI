import tempfile
import unittest
import builtins
import io
import os
from pathlib import Path
from unittest.mock import patch

import pymupdf

from docforensics.manifest import build_manifest, write_manifest
from docforensics.practice import practice_run
from docforensics.processing import Stage, Status


class PracticeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pdf = self.root / "fixture.pdf"
        with pymupdf.open() as document:
            document.new_page()
            document.save(self.pdf)
        self.manifest = self.root / "case.json"
        write_manifest(build_manifest("TEST", self.root, ["fixture.pdf"]), self.manifest)

    def test_practice_scenarios_use_verified_inputs_and_no_analysis_outputs(self):
        for scenario in ("success", "ocr-failure", "awaiting-review"):
            with self.subTest(scenario=scenario):
                run = practice_run(self.manifest, scenario)
                self.assertEqual(run.summary()["mode"], "practice")
                self.assertEqual(run.case.fields, ())
                self.assertEqual(run.case.findings, ())
                self.assertIsNone(run.artifact_path)
                if scenario == "awaiting-review":
                    self.assertEqual(run.steps[-1].status, Status.PENDING)
                if scenario == "ocr-failure":
                    self.assertEqual(next(s.status for s in run.steps if s.stage == Stage.OCR), Status.FAILED)

    def test_modified_source_is_rejected_before_practice_starts(self):
        self.pdf.write_bytes(self.pdf.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "file size changed"):
            practice_run(self.manifest)

    def test_practice_does_not_open_the_answer_key(self):
        (self.root / "ground_truth.csv").write_text("private evaluation labels", encoding="utf-8")

        def guard(opener):
            def guarded(file, *args, **kwargs):
                if isinstance(file, (str, os.PathLike)) and Path(file).name == "ground_truth.csv":
                    self.fail("practice runtime attempted to read evaluation labels")
                return opener(file, *args, **kwargs)
            return guarded

        with patch("builtins.open", guard(builtins.open)), patch("io.open", guard(io.open)):
            for scenario in ("success", "ocr-failure", "awaiting-review"):
                run = practice_run(self.manifest, scenario)
                self.assertEqual(run.summary()["mode"], "practice")


if __name__ == "__main__":
    unittest.main()
