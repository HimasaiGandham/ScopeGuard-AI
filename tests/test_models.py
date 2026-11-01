import unittest

from docforensics.models import (
    Document,
    EvidenceRef,
    ExtractedField,
    Finding,
    FindingCategory,
    InvestigationCase,
    SourceRegion,
)


class FoundationModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = Document("doc-1", "sample.pdf", page_count=1)
        self.region = SourceRegion(1, 0.2, 0.3, 0.6, 0.4)
        self.evidence = EvidenceRef("doc-1", self.region, "Example value")

    def test_case_keeps_source_link_for_fields_and_findings(self) -> None:
        case = InvestigationCase(
            "case-1",
            documents=(self.document,),
            fields=(ExtractedField("field-1", "name", "Example value", self.evidence, 0.9),),
            findings=(
                Finding(
                    "finding-1",
                    FindingCategory.VISUAL,
                    "A field appears visually inconsistent",
                    "A reviewer should inspect the marked region",
                    (self.evidence,),
                    0.7,
                ),
            ),
        )
        self.assertEqual(case.findings[0].evidence[0].document_id, "doc-1")
        self.assertEqual(case.findings[0].evidence[0].region.page_number, 1)

    def test_case_rejects_evidence_on_unknown_document(self) -> None:
        other = EvidenceRef("missing-document", self.region)
        with self.assertRaisesRegex(ValueError, "unknown document"):
            InvestigationCase(
                "case-1",
                documents=(self.document,),
                findings=(
                    Finding("finding-1", FindingCategory.VISUAL, "A mark", "Inspect it", (other,)),
                ),
            )

    def test_case_rejects_evidence_beyond_page_count(self) -> None:
        other = EvidenceRef("doc-1", SourceRegion(2, 0.2, 0.3, 0.6, 0.4))
        with self.assertRaisesRegex(ValueError, "exceeds"):
            InvestigationCase(
                "case-1",
                documents=(self.document,),
                fields=(ExtractedField("field-1", "name", "Example", other),),
            )

    def test_region_rejects_invalid_coordinates(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            SourceRegion(1, 0.2, 0.3, 1.2, 0.4)

    def test_pixel_box_converts_to_page_independent_region(self) -> None:
        region = SourceRegion.from_pixels(1, 416, 294, 1035, 347, 1275, 1650)
        self.assertAlmostEqual(region.x1, 416 / 1275)
        self.assertAlmostEqual(region.y2, 347 / 1650)


if __name__ == "__main__":
    unittest.main()
