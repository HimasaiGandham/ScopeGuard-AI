"""Make a local manual evidence-link demonstration from a verified PDF."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from html import escape
from math import ceil, floor
from pathlib import Path
from uuid import uuid4

import pymupdf
from PIL import Image, ImageDraw

from .manifest import load_verified_manifest
from .models import AuditEvent, EvidenceRef, Finding, FindingCategory, InvestigationCase, SourceRegion


MAX_RENDER_PIXELS = 25_000_000


@dataclass(frozen=True, slots=True)
class TraceBundle:
    case: InvestigationCase
    index_path: Path
    record_path: Path


def region_to_pixels(region: SourceRegion, width: int, height: int) -> tuple[int, int, int, int]:
    """Return a covering crop box with exclusive right and bottom edges."""
    if type(width) is not int or type(height) is not int or width < 1 or height < 1:
        raise ValueError("image dimensions must be positive integers")
    if not isinstance(region, SourceRegion):
        raise ValueError("region must use SourceRegion")
    left, top = min(width - 1, floor(region.x1 * width)), min(height - 1, floor(region.y1 * height))
    return (left, top, min(width, max(left + 1, ceil(region.x2 * width))),
            min(height, max(top + 1, ceil(region.y2 * height))))


def render_source_page(source_bytes: bytes, page_number: int, dpi: int = 144) -> Image.Image:
    """Render the displayed PDF page, with bounded memory use."""
    if type(dpi) is not int or not 36 <= dpi <= 300:
        raise ValueError("dpi must be an integer between 36 and 300")
    if type(page_number) is not int or page_number < 1:
        raise ValueError("page must be a positive integer")
    with pymupdf.open(stream=source_bytes, filetype="pdf") as pdf:
        if not pdf.is_pdf or pdf.needs_pass:
            raise ValueError("PDF cannot be read without a password")
        if page_number > pdf.page_count:
            raise ValueError("page is beyond the source document")
        page = pdf[page_number - 1]
        if ceil(page.rect.width * dpi / 72) * ceil(page.rect.height * dpi / 72) > MAX_RENDER_PIXELS:
            raise ValueError("page is too large at this dpi; choose a lower resolution")
        pixmap = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def create_evidence_trace(
    manifest_path: Path,
    document_id: str,
    region: SourceRegion,
    output_directory: Path,
    *,
    observation: str = "Manually selected page region for the evidence tracing demonstration",
    dpi: int = 144,
) -> TraceBundle:
    """Connect a manual finding to source pixels without making a forensic claim.

    Coordinates describe the displayed page, including its rotation and crop.
    The answer key is never opened. Source PDFs are never saved or overwritten.
    """
    if not isinstance(region, SourceRegion):
        raise ValueError("region must use SourceRegion")
    if type(dpi) is not int or not 36 <= dpi <= 300:
        raise ValueError("dpi must be an integer between 36 and 300")
    if not isinstance(observation, str) or not observation.strip():
        raise ValueError("a manual observation is required")

    verified = load_verified_manifest(manifest_path)
    document = next((d for d in verified.case.documents if d.document_id == document_id), None)
    if document is None:
        raise ValueError("document ID is not present in this case")
    if region.page_number > document.page_count:
        raise ValueError("evidence page is beyond the source document")

    output_directory = output_directory.resolve()
    checkout = Path(__file__).resolve().parents[1]
    if output_directory == checkout or checkout in output_directory.parents:
        raise ValueError("evidence output must be outside the project checkout")
    if output_directory == verified.source_directory or verified.source_directory in output_directory.parents:
        raise ValueError("evidence output must be outside the source PDF folder")
    if output_directory.exists():
        raise FileExistsError("evidence output folder already exists; choose a new folder")

    source_path = (verified.source_directory / document.filename).resolve(strict=True)
    if source_path.parent != verified.source_directory:
        raise ValueError("source path is outside the verified PDF folder")
    source_bytes = source_path.read_bytes()
    rendered_hash = hashlib.sha256(source_bytes).hexdigest()
    if rendered_hash != document.content_sha256.lower():
        raise ValueError("source changed after manifest verification")

    image = render_source_page(source_bytes, region.page_number, dpi)

    box = region_to_pixels(region, image.width, image.height)
    crop = image.crop(box)
    marked = image.copy()
    ImageDraw.Draw(marked).rectangle(
        (box[0], box[1], box[2] - 1, box[3] - 1), outline=(190, 20, 35), width=max(2, round(dpi / 48)))
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != rendered_hash:
        raise ValueError("source changed while rendering; no evidence bundle was written")

    finding = Finding(
        finding_id=f"manual-{document_id}-p{region.page_number}",
        category=FindingCategory.VISUAL,
        observation=observation.strip(),
        explanation="A person selected this region to test source tracing. No automated anomaly or authenticity conclusion was made.",
        evidence=(EvidenceRef(document_id, region),),
        confidence=None,
    )
    event = AuditEvent(str(uuid4()), datetime.now(timezone.utc), "evidence.manual_link", document_id,
                       "Manual region selected for a source tracing demonstration")
    case = replace(verified.case, findings=(finding,), audit_events=verified.case.audit_events + (event,))
    record = {
        "trace_version": 1,
        "demo_only": True,
        "selection_method": "manual",
        "case_id": case.case_id,
        "case_document_ids": [d.document_id for d in case.documents],
        "finding": asdict(finding),
        "source_document": asdict(document),
        "source_path": str(source_path),
        "rendered_input_sha256": rendered_hash,
        "rendered_page": {"width": image.width, "height": image.height, "dpi": dpi},
        "pixel_box": list(box),
        "coordinate_convention": "displayed page top left origin; normalized x1 y1 x2 y2; pixel right and bottom exclusive",
        "audit": {"event_id": event.event_id, "occurred_at": event.occurred_at.isoformat(), "action": event.action},
        "assets": {"page": "source-page.png", "marked": "marked-page.png", "crop": "evidence-crop.png"},
    }

    output_directory.mkdir(parents=True, exist_ok=False)
    image.save(output_directory / "source-page.png", dpi=(dpi, dpi))
    marked.save(output_directory / "marked-page.png", dpi=(dpi, dpi))
    crop.save(output_directory / "evidence-crop.png", dpi=(dpi, dpi))
    record_path = output_directory / "trace.json"
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    index_path = output_directory / "index.html"
    index_path.write_text(_viewer(record, source_path), encoding="utf-8")
    return TraceBundle(case, index_path, record_path)


def _viewer(record: dict, source_path: Path, *, source_href: str | None = None,
            upload_href: str | None = None) -> str:
    finding = record["finding"]
    source = record["source_document"]
    region = finding["evidence"][0]["region"]
    size = record["rendered_page"]
    x, y = region["x1"] * size["width"], region["y1"] * size["height"]
    width = (region["x2"] - region["x1"]) * size["width"]
    height = (region["y2"] - region["y1"]) * size["height"]
    source_uri = escape(source_href or (source_path.as_uri() + f"#page={region['page_number']}"), quote=True)
    upload_link = f'<p><a href="{escape(upload_href, quote=True)}">Upload another PDF</a></p>' if upload_href else ""
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Manual evidence tracing demonstration</title>
<style>
body{{font:16px/1.5 system-ui,sans-serif;margin:0;background:#f5f7fa;color:#172433}}
main{{max-width:1100px;margin:auto;padding:28px}}h1{{font-size:28px;line-height:1.2}}h2{{font-size:21px}}
section{{background:white;border:1px solid #cdd5df;border-radius:8px;padding:20px;margin:18px 0}}
a{{color:#164ba0}}button{{background:#173f76;color:white;padding:10px 16px;border:0;border-radius:5px;cursor:pointer}}
.banner{{font-weight:600}}.meta{{overflow-wrap:anywhere}}.canvas{{overflow:auto;border:1px solid #cdd5df;background:#e5e9ee}}
#page{{display:block;width:100%;height:auto}}input{{vertical-align:middle}}.crop{{max-width:100%;border:1px solid #cdd5df}}
.detail{{font-size:14px;color:#41536a}}:focus-visible{{outline:3px solid #e8a012;outline-offset:3px}}
</style></head><body><main>
<h1>Manual evidence tracing demonstration</h1>
{upload_link}
<p class="banner">This is a manually selected source region. No automated alteration detection or authenticity decision was performed.</p>
<section aria-labelledby="finding-title"><h2 id="finding-title">Finding to inspect</h2>
<p>{escape(finding['observation'])}</p><p>{escape(finding['explanation'])}</p>
<p class="meta">Case <strong>{escape(record['case_id'])}</strong> → Finding <strong>{escape(finding['finding_id'])}</strong> → Document <strong>{escape(source['document_id'])}</strong> → Page <strong>{region['page_number']}</strong></p>
<p>File {escape(source['filename'])} · Review pending · Confidence not assigned</p>
<button type="button" id="show-source">Show the source region</button>
<p><a href="{source_uri}">Open original PDF at page {region['page_number']}</a> · <a href="trace.json">View trace record</a> · <a href="marked-page.png">Open marked page image</a></p>
</section>
<section id="source" aria-labelledby="source-title"><h2 id="source-title" tabindex="-1">Original page with selected region</h2>
<p><label for="zoom">Page size</label> <input id="zoom" type="range" min="50" max="150" step="10" value="100"> <output id="zoom-value" for="zoom">100%</output></p>
<div class="canvas"><svg id="page" viewBox="0 0 {size['width']} {size['height']}" role="img" aria-label="Source page with a red rectangle marking the manually selected evidence">
<image href="source-page.png" width="{size['width']}" height="{size['height']}"/>
<rect id="evidence-region" x="{x:.6f}" y="{y:.6f}" width="{width:.6f}" height="{height:.6f}" fill="none" stroke="#be1423" stroke-width="3" vector-effect="non-scaling-stroke"/>
</svg></div></section>
<section><h2>Selected source crop</h2><img class="crop" src="evidence-crop.png" alt="Unmodified pixels cropped from the selected source region">
<p class="detail meta">SHA-256 of rendered input {escape(record['rendered_input_sha256'])}<br>Rendered page {size['width']} by {size['height']} pixels at {size['dpi']} dpi. Coordinates follow the displayed page, including rotation.</p></section>
</main><script>
document.getElementById('show-source').addEventListener('click',()=>{{document.getElementById('source').scrollIntoView({{behavior:'smooth'}});document.getElementById('source-title').focus({{preventScroll:true}});}});
document.getElementById('zoom').addEventListener('input',event=>{{const value=event.target.value;document.getElementById('page').style.width=value+'%';document.getElementById('zoom-value').value=value+'%';}});
</script></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--page", type=int, required=True)
    parser.add_argument("--box", type=float, nargs=4, metavar=("X1", "Y1", "X2", "Y2"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=144)
    parser.add_argument("--observation", default="Manually selected page region for the evidence tracing demonstration")
    args = parser.parse_args()
    try:
        bundle = create_evidence_trace(args.manifest, args.document_id, SourceRegion(args.page, *args.box),
                                       args.output, observation=args.observation, dpi=args.dpi)
    except (OSError, ValueError, KeyError, RuntimeError, TypeError) as exc:
        parser.exit(1, f"Evidence trace error: {exc}\n")
    print("MANUAL DEMONSTRATION: source tracing only; no automated forensic conclusion.")
    print(f"Open {bundle.index_path}")
    print(f"Trace record {bundle.record_path}")


if __name__ == "__main__":
    main()
