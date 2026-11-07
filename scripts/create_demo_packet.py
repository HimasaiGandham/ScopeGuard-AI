"""Create synthetic PS2 inputs and a separate evaluation key outside the source tree."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

import pymupdf


PAGE_SIZE = (595, 842)
SOURCE_ROOT = Path(__file__).resolve().parents[1]


def form(title, name, ids, course):
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=PAGE_SIZE[0], height=PAGE_SIZE[1])
        page.insert_text((45, 46), "SCOPEGUARD AI  /  SYNTHETIC TRAINING DOCUMENT", fontsize=10)
        page.insert_text((45, 90), title, fontsize=23)
        rows = [f"Student name {name}", *(f"Student ID {value}" for value in ids),
                f"Course code {course}"]
        for index, row in enumerate(rows):
            page.insert_text((45, 135 + 29 * index), row, fontsize=15)
        page.insert_text((45, 285), "Printed reference: enrollment copy for review", fontsize=15)
        page.insert_text((45, 325), "Fictitious values for the PS2 demonstration.", fontsize=11)
        return pdf.tobytes(no_new_id=True)


def scan(original, ink=None):
    with pymupdf.open(stream=original, filetype="pdf") as source:
        page = source[0]
        if ink:
            points = [(45, 276), (173, 279), (47, 285), (178, 287), (53, 278)]
            page.draw_polyline(points, color=ink, width=2.5)
        pixels = page.get_pixmap(matrix=pymupdf.Matrix(2.2, 2.2), alpha=False)
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=PAGE_SIZE[0], height=PAGE_SIZE[1])
        page.insert_image(page.rect, stream=pixels.tobytes("png"))
        return pdf.tobytes(no_new_id=True, deflate=True)


def create_packet(folder, packet):
    folder = folder.resolve()
    if folder == SOURCE_ROOT or SOURCE_ROOT in folder.parents:
        raise ValueError("Choose an output folder outside the source checkout.")
    if packet == "rehearsal":
        name, primary, secondary = "Mira Example", "REG-2846", "REG-9942"
        first_course, second_course = "DQ-210", "DQ-211"
        ink = (.10, .23, .65)
        categories = {"within_document": 1, "cross_document": 2, "visual": 1}
    else:
        name, primary, secondary = "Leena Example", "REG-8276", None
        first_course, second_course = "DQ-415", "DQ-416"
        ink = (.05, .05, .05)
        categories = {"within_document": 0, "cross_document": 1, "visual": 0}
    ids = [primary, secondary] if secondary else [primary]
    registration = form("Student registration", name, ids, first_course)
    enrollment = form("Enrollment confirmation", name, [primary], second_course)
    inputs = {
        "registration.pdf": registration,
        "enrollment-scan.pdf": scan(enrollment, ink),
    }
    if packet == "rehearsal":
        inputs["damaged.pdf"] = b"Deliberately invalid synthetic PDF for the rejection demo."
    control = scan(enrollment)
    expected = {
        "packet": packet,
        "same_entity": True,
        "accepted": 2,
        "rejected": 1 if packet == "rehearsal" else 0,
        "fields": {
            "registration.pdf": {"student_name": [name], "student_id": ids, "course_code": [first_course]},
            "enrollment-scan.pdf": {
                "student_name": [name], "student_id": [primary], "course_code": [second_course],
            },
        },
        "scan_method": "ocr",
        "finding_categories": categories,
        "visual_region": [42 / 595, 273 / 842, 182 / 595, 290 / 842],
        "altered_visual_signal": "blue ink" if packet == "rehearsal" else "black ink outside detector scope",
        "clean_control_visual_count": 0,
        "sha256": {name: sha256(content).hexdigest() for name, content in
                   {**inputs, "enrollment-clean.pdf": control}.items()},
    }
    folder.mkdir(parents=True, exist_ok=False)
    for name in ("inputs", "controls", "evaluation"):
        (folder / name).mkdir()
    for name, content in inputs.items():
        (folder / "inputs" / name).write_bytes(content)
    (folder / "controls/enrollment-clean.pdf").write_bytes(control)
    (folder / "evaluation/expected.json").write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    print(f"Created {packet} packet. Upload files from {folder / 'inputs'} only.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New folder outside the source checkout")
    parser.add_argument("--packet", choices=("rehearsal", "holdout"), default="rehearsal")
    args = parser.parse_args()
    try:
        create_packet(args.output, args.packet)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
