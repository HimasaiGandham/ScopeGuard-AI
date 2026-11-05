"""Local text extraction with bounded worker processes and explicit layout support."""
from __future__ import annotations

import io
import json
import re
from pathlib import Path
import subprocess
import sys
from dataclasses import asdict

import pymupdf
from PIL import Image, ImageOps

from .models import EvidenceRef, ExtractedField, SourceRegion
from .related_layouts import recognize_related

LABELS = {"student name": "student_name", "student id": "student_id",
          "submission date": "submission_date", "course code": "course_code"}


def read_page(content: bytes, suffix: str, number: int, tessdata: str | None) -> dict:
    if suffix != ".pdf":
        with Image.open(io.BytesIO(content)) as image:
            stream = io.BytesIO()
            ImageOps.exif_transpose(image).convert("RGB").save(stream, format="PNG")
        with pymupdf.open(stream=stream.getvalue(), filetype="png") as image_pdf:
            content = image_pdf.convert_to_pdf()
    with pymupdf.open(stream=content, filetype="pdf") as pdf:
        page = pdf[number - 1]
        if page.rect.width * page.rect.height * (150 / 72) ** 2 > 25_000_000:
            raise ValueError("Page exceeds the rendering limit")
        textpage = page.get_textpage()
        method = "digital"
        if not page.get_text(textpage=textpage).strip():
            method = "ocr"
            if not tessdata or not (Path(tessdata) / "eng.traineddata").is_file():
                raise ValueError("English OCR model unavailable")
            textpage = page.get_textpage_ocr(language="eng", dpi=150, full=True, tessdata=tessdata)
        words = []
        for word in page.get_text("words", textpage=textpage)[:50000]:
            rect = pymupdf.Rect(word[:4]) * page.rotation_matrix
            rect &= page.rect
            if rect.is_empty:
                continue
            words.append({"text": word[4], "box": [rect.x0/page.rect.width, rect.y0/page.rect.height,
                         rect.x1/page.rect.width, rect.y1/page.rect.height]})
        return {"method": method, "words": words, "confidence": None,
                "review_required": True, "warning": "Confidence unavailable; compare with the original page."}


def recognize(page: dict, document_id: str, page_number: int) -> dict:
    # Group displayed words into lines, including labels and values in separate PDF text blocks.
    lines = []
    for word in sorted(page["words"], key=lambda w: (w["box"][1], w["box"][0])):
        center = (word["box"][1] + word["box"][3]) / 2
        line = next((line for line in lines if abs(line["center"] - center) < .006), None)
        if line is None:
            line = {"center": center, "words": []}
            lines.append(line)
        line["words"].append(word)
    for line in lines:
        line["words"].sort(key=lambda w: w["box"][0])
        line["text"] = " ".join(w["text"] for w in line["words"])
    text = "\n".join(line["text"] for line in lines)
    related = recognize_related(lines, document_id, page_number)
    if related is not None:
        return related
    normalized = " ".join(text.lower().split())
    supported = ("northfield learning institute" in normalized or "data quality audit" in normalized) and all(
        sum(line["text"].lower().strip().startswith(label) for line in lines) == 1 for label in LABELS)
    fields, sections, rows = [], [], []
    if supported:
        for line in lines:
            lower = line["text"].lower().strip()
            for label, name in LABELS.items():
                if lower.startswith(label):
                    count = len(label.split())
                    value_words = line["words"][count:]
                    # Only the supported left-label/right-value block is interpreted.
                    value_words = [w for w in value_words if w["text"].strip(":")]
                    if not value_words:
                        continue
                    region = SourceRegion(page_number, min(w["box"][0] for w in value_words),
                        min(w["box"][1] for w in value_words), max(w["box"][2] for w in value_words),
                        max(w["box"][3] for w in value_words))
                    value = " ".join(w["text"] for w in value_words)
                    field = ExtractedField(f"{document_id}-p{page_number}-{name}", name, value,
                                            EvidenceRef(document_id, region, value), None)
                    fields.append(asdict(field))
                    rows.append({"label": label, "field_id": field.field_id})
            if lower.startswith(("1. aim", "2. method", "3. result")):
                sections.append(line["text"])
    tables = [{"kind": "label_value_block", "rows": rows}] if rows else []
    if supported:
        header = next((i for i,line in enumerate(lines) if line['text'].lower().strip() == 'measure value'), None)
        if header is not None:
            boundary = lines[header]['words'][-1]['box'][0] - .01
            measured = []
            for line in lines[header+1:]:
                if 'coursework submission' in line['text'].lower(): break
                left = [w for w in line['words'] if w['box'][0] < boundary]
                right = [w for w in line['words'] if w['box'][0] >= boundary]
                if not left or not right: continue
                label = ' '.join(w['text'] for w in left)
                value = ' '.join(w['text'] for w in right)
                region = SourceRegion(page_number,min(w['box'][0] for w in right),min(w['box'][1] for w in right),max(w['box'][2] for w in right),max(w['box'][3] for w in right))
                name = re.sub(r'[^a-z0-9]+','_',label.lower()).strip('_') or 'recorded_value'
                field = ExtractedField(f'{document_id}-p{page_number}-table-{len(measured)+1}',name,value,EvidenceRef(document_id,region,value),None)
                fields.append(asdict(field));measured.append({'label':label,'value':value,'field_id':field.field_id})
            tables.append({'kind':'recorded_values','columns':['Measure','Value'],'rows':measured})
    return {"layout": "northfield_coursework" if supported else "unsupported_layout",
            "document_type": "coursework_submission" if supported else "unknown",
            "text": text, "fields": fields, "sections": sections,
            "tables": tables,
            "layout_warning": None if supported else "Unsupported layout: text is retained, but no field labels are inferred."}


def extract_case(store, case_id: str, *, tessdata: str | None = None, timeout: float = 45) -> dict:
    record = store.get_case(case_id, verify_sources=False)
    documents, all_fields = [], []
    for document in record["documents"]:
        result = {"document_id": document["document_id"], "filename": document["filename"], "pages": []}
        try:
            _, content = store.read_original(case_id, document["document_id"])
        except (OSError, ValueError):
            result.update(status="failed", error="Source missing or changed; extraction was not attempted.")
            documents.append(result)
            continue
        for number in range(1, document["page_count"] + 1):
            page = {"page_number": number, "page_id": document["pages"][number-1]["page_id"]}
            try:
                command = [sys.executable, "-m", "docforensics.extraction", "--worker",
                           Path(document["filename"]).suffix.lower(), str(number), tessdata or ""]
                completed = subprocess.run(command, input=content, capture_output=True, timeout=timeout)
                if completed.returncode:
                    raise ValueError("Text engine could not read this page; check the OCR model and page readability.")
                observed = json.loads(completed.stdout)
                layout = recognize(observed, document["document_id"], number)
                page.update(observed, **layout, status="completed" if observed["words"] else "unreadable")
                all_fields.extend(layout["fields"])
            except subprocess.TimeoutExpired:
                page.update(status="failed", error="Page extraction timed out; other pages continue.")
            except (OSError, ValueError, KeyError, TypeError):
                page.update(status="failed", error="Text engine could not read this page; check the English OCR model and original.")
            result["pages"].append(page)
        # Recheck after processing, so changes during extraction invalidate the document output.
        try:
            store.read_original(case_id, document["document_id"])
        except (OSError, ValueError):
            all_fields = [f for f in all_fields if f["source"]["document_id"] != document["document_id"]]
            result.update(pages=[], status="failed", error="Source changed during extraction.")
        else:
            states = [p["status"] for p in result["pages"]]
            result["status"] = "completed" if all(s == "completed" for s in states) else "partial" if "completed" in states else "failed"
        documents.append(result)
    return {"case_id": case_id, "documents": documents, "fields": all_fields, "uploads": record["uploads"],
            "limits": "English printed text; one supported demo layout; handwriting and other layouts need human review."}


if __name__ == "__main__":
    try:
        output = read_page(sys.stdin.buffer.read(), sys.argv[2], int(sys.argv[3]), sys.argv[4] or None)
        sys.stdout.write(json.dumps(output))
    except Exception:
        sys.exit(1)
