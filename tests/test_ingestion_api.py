import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from fastapi.testclient import TestClient
from PIL import Image

from docforensics.upload_app import create_app


class IngestionAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        self.app = create_app(Path(self.temp.name) / "storage")
        self.client = TestClient(self.app, base_url="http://127.0.0.1:8765")
        self.addCleanup(self.client.close)
        self.headers = {"X-Local-Upload": "1", "Origin": "http://127.0.0.1:8765"}
        with pymupdf.open() as document:
            document.new_page()
            self.pdf = document.tobytes()
        output = io.BytesIO()
        Image.new("RGB", (15, 20), "blue").save(output, format="PNG")
        self.png = output.getvalue()

    def upload(self, files=None, **kwargs):
        return self.client.post("/api/ingestion/cases", headers=self.headers,
            files=files or [("files", ("one.pdf", self.pdf, "application/pdf")),
                            ("files", ("scan.png", self.png, "image/png"))], **kwargs)

    def test_screen_and_mixed_upload_reopen_and_original_download(self):
        self.assertIn('href="/ingest"', self.client.get("/").text)
        self.assertIn('multiple accept=', self.client.get("/ingest").text)
        response = self.upload()
        self.assertEqual(response.status_code, 200)
        case = response.json()
        self.assertEqual(len(case["documents"]), 2)
        self.assertEqual(self.client.get(f"/api/ingestion/cases/{case['case_id']}").json(), case)
        for document, expected in zip(case["documents"], (self.pdf, self.png)):
            source = self.client.get(f"/api/ingestion/cases/{case['case_id']}/documents/{document['document_id']}/original")
            self.assertEqual(source.status_code, 200)
            self.assertEqual(source.content, expected)
            self.assertEqual(source.headers["content-type"], document["media_type"])
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_duplicate_and_rejected_files_have_individual_statuses(self):
        case = self.upload([("files", ("one.pdf", self.pdf)), ("files", ("copy.pdf", self.pdf)),
                            ("files", ("bad.pdf", b"broken")), ("files", ("notes.txt", b"text"))]).json()
        self.assertEqual([u["status"] for u in case["uploads"]], ["accepted", "duplicate", "rejected", "rejected"])
        self.assertEqual(case["status"], "partial")

    def test_foreign_origin_and_missing_header_cannot_create_cases(self):
        for headers in ({}, {"X-Local-Upload": "1", "Origin": "https://elsewhere.example"}):
            response = self.client.post("/api/ingestion/cases", files=[("files", ("one.pdf", self.pdf))], headers=headers)
            self.assertEqual(response.status_code, 403)
        self.assertEqual(list((self.app.state.case_store.root / "cases").iterdir()), [])

    def test_invalid_forms_count_and_content_type_are_rejected(self):
        self.assertEqual(self.client.post("/api/ingestion/cases", headers=self.headers, content=b"raw").status_code, 415)
        self.assertEqual(self.upload([("wrong", ("one.pdf", self.pdf))]).status_code, 422)
        self.assertEqual(self.upload([("files", ("one.pdf", self.pdf))], data={"extra": "field"}).status_code, 400)
        self.assertEqual(self.upload([("files", (f"{i}.pdf", self.pdf)) for i in range(21)]).status_code, 400)
        self.assertEqual(list((self.app.state.case_store.root / "cases").iterdir()), [])

    def test_upload_body_is_bounded_even_with_an_inaccurate_length_header(self):
        with patch("docforensics.ingestion_api.MAX_BATCH_BYTES", 0):
            headers = dict(self.headers, **{"Content-Length": str(2 * 1024 * 1024)})
            self.assertEqual(self.client.post("/api/ingestion/cases", content=b"x", headers=headers).status_code, 413)
            request = self.client.build_request("POST", "/api/ingestion/cases", headers=self.headers,
                files=[("files", ("large.pdf", b"x" * (1024 * 1024 + 1)))])
            request.headers["Content-Length"] = "1"
            self.assertEqual(self.client.send(request).status_code, 413)
        self.assertEqual(list((self.app.state.case_store.root / "cases").iterdir()), [])

    def test_changed_source_and_unknown_case_or_document_are_not_served(self):
        case = self.upload().json()
        document = case["documents"][0]
        prefix = f"/api/ingestion/cases/{case['case_id']}"
        self.assertEqual(self.client.get(prefix + "/documents/wrong/original").status_code, 404)
        self.assertEqual(self.client.get("/api/ingestion/cases/not-a-case").status_code, 404)
        original = self.app.state.case_store.root / "cases" / case["case_id"] / "originals" / document["stored_filename"]
        original.write_bytes(original.read_bytes() + b"changed")
        self.assertEqual(self.client.get(prefix).status_code, 409)
        self.assertEqual(self.client.get(prefix + f"/documents/{document['document_id']}/original").status_code, 409)

    def test_storage_failure_reports_safe_error_without_claiming_a_saved_case(self):
        with patch.object(self.app.state.case_store, "ingest", side_effect=OSError("private storage path")):
            response = self.upload()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private storage path", response.text)


if __name__ == "__main__":
    unittest.main()
