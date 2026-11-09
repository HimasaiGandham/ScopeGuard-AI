import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from fastapi.testclient import TestClient
from PIL import Image

from docforensics.upload_app import UploadStore, create_app


class UploadAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = create_app(self.root / "uploads")
        self.client = TestClient(self.app, base_url="http://127.0.0.1:8765")
        self.addCleanup(self.client.close)
        with pymupdf.open() as document:
            document.new_page(width=200, height=100)
            page = document.new_page(width=200, height=100)
            page.draw_rect(page.rect, color=None, fill=(0, 0, 1))
            self.pdf = document.tobytes()
        self.headers = {"X-Local-Upload": "1", "Origin": "http://127.0.0.1:8765"}

    def upload(self, data=None, filename="my-own-document.pdf"):
        return self.client.post("/api/upload", content=self.pdf if data is None else data,
            headers=dict(self.headers, **{"X-Filename": filename, "Content-Type": "application/pdf"}))

    def test_home_has_file_picker_and_no_fixed_sample(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('type="file"', response.text)
        self.assertIn("Upload and open PDF", response.text)
        self.assertNotIn("sample_003.pdf", response.text)
        self.assertEqual(self.client.get("/api/health").json()["mode"], "manual_evidence")

    def test_own_pdf_upload_pages_and_manual_trace_round_trip(self):
        upload = self.upload()
        self.assertEqual(upload.status_code, 200)
        item = upload.json()
        self.assertEqual(item["filename"], "my-own-document.pdf")
        self.assertEqual(item["pages"], 2)
        self.assertEqual(item["sha256"], hashlib.sha256(self.pdf).hexdigest())
        case = item["case_id"]
        image = self.client.get(f"/api/cases/{case}/pages/2")
        self.assertEqual(image.status_code, 200)
        with Image.open(io.BytesIO(image.content)) as page:
            self.assertEqual(page.getpixel((50, 50)), (0, 0, 255))
        trace = self.client.post(f"/api/cases/{case}/trace", headers=self.headers,
            json={"page": 2, "box": [0.1, 0.1, 0.5, 0.5], "observation": "My selected area"})
        self.assertEqual(trace.status_code, 200)
        viewer_url = trace.json()["viewer_url"]
        viewer = self.client.get(viewer_url)
        self.assertEqual(viewer.status_code, 200)
        self.assertIn(f'/api/cases/{case}/pdf#page=2', viewer.text)
        self.assertIn('href="/">Upload another PDF', viewer.text)
        record = self.client.get(viewer_url.replace("index.html", "trace.json")).json()
        self.assertTrue(record["demo_only"])
        self.assertEqual(record["finding"]["evidence"][0]["region"]["page_number"], 2)
        self.assertEqual(record["rendered_input_sha256"], item["sha256"])
        self.assertEqual(self.client.get(f"/api/cases/{case}/pdf").content, self.pdf)

    def test_invalid_pdf_filename_and_locked_pdf_are_rejected_before_storage(self):
        self.assertEqual(self.upload(b"not a PDF").status_code, 422)
        self.assertEqual(self.upload(filename="../../private.pdf").status_code, 422)
        self.assertEqual(self.upload(filename="wrong.txt").status_code, 422)
        with pymupdf.open(stream=self.pdf, filetype="pdf") as document:
            locked = document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="test")
        self.assertEqual(self.upload(locked).status_code, 422)
        self.assertEqual(list((self.app.state.store.root / "cases").iterdir()), [])

    def test_origin_custom_header_and_host_are_checked(self):
        response = self.client.post("/api/upload", content=self.pdf, headers={"X-Filename": "file.pdf"})
        self.assertEqual(response.status_code, 403)
        response = self.client.post("/api/upload", content=self.pdf,
            headers={"X-Filename": "file.pdf", "X-Local-Upload": "1", "Origin": "https://elsewhere.example"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/", headers={"Host": "elsewhere.example"}).status_code, 400)

    def test_hosted_demo_requires_credentials_and_preserves_https_uploads(self):
        app = create_app(self.root / "hosted", hosted_access=("demo.example", "test-password"))
        with TestClient(app, base_url="http://demo.example") as client:
            auth = ("reviewer", "test-password")
            self.assertEqual(client.get("/api/health").status_code, 200)
            self.assertEqual(client.get("/api/health", headers={"Host": "elsewhere.example"}).status_code, 400)
            self.assertEqual(client.get("/ingest").status_code, 401)
            self.assertEqual(client.get("/ingest", auth=("reviewer", "wrong")).status_code, 401)
            page = client.get("/ingest", auth=auth)
            self.assertEqual(page.status_code, 200)
            self.assertIn("Upload only synthetic examples", page.text)
            self.assertNotIn("Your files stay on this computer", page.text)

            headers = {"X-Local-Upload": "1", "X-Filename": "synthetic.pdf",
                       "Origin": "https://demo.example", "Content-Type": "application/pdf"}
            self.assertEqual(client.post("/api/upload", content=self.pdf, headers=headers).status_code, 401)
            wrong_origin = dict(headers, Origin="https://elsewhere.example")
            self.assertEqual(client.post("/api/upload", content=self.pdf, headers=wrong_origin, auth=auth).status_code, 403)
            result = client.post("/api/upload", content=self.pdf, headers=headers, auth=auth)
            self.assertEqual(result.status_code, 200)
            source = f"/api/cases/{result.json()['case_id']}/pdf"
            self.assertEqual(client.get(source).status_code, 401)
            self.assertEqual(client.get(source, auth=auth).content, self.pdf)

    def test_upload_size_limit_applies_to_headers_and_stream(self):
        with patch("docforensics.upload_app.MAX_UPLOAD_BYTES", 10):
            self.assertEqual(self.upload().status_code, 413)
            response = self.client.post("/api/upload", content=self.pdf,
                headers=dict(self.headers, **{"X-Filename": "file.pdf", "Content-Length": "1"}))
            self.assertEqual(response.status_code, 413)

    def test_invalid_page_region_case_and_asset_are_rejected(self):
        case = self.upload().json()["case_id"]
        self.assertEqual(self.client.get(f"/api/cases/{case}/pages/3").status_code, 422)
        self.assertEqual(self.client.get("/api/cases/not-a-case/pages/1").status_code, 404)
        response = self.client.post(f"/api/cases/{case}/trace", headers=self.headers,
            json={"page": 1, "box": [-1, 0, 1, 1], "observation": "Invalid"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get(f"/api/cases/{case}/traces/invalid/index.html").status_code, 404)

    def test_changed_uploaded_copy_is_not_served_as_verified(self):
        case = self.upload().json()["case_id"]
        path = next((self.app.state.store.root / "cases" / case / "pdfs").glob("*.pdf"))
        path.write_bytes(path.read_bytes() + b"changed")
        self.assertEqual(self.client.get(f"/api/cases/{case}/pages/1").status_code, 409)
        self.assertEqual(self.client.get(f"/api/cases/{case}/pdf").status_code, 409)

    def test_upload_storage_cannot_be_inside_repository(self):
        with self.assertRaisesRegex(ValueError, "outside the project"):
            UploadStore(Path(__file__).resolve().parents[1] / "tmp" / "uploads")


if __name__ == "__main__":
    unittest.main()
