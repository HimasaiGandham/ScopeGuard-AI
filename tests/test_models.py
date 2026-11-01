import unittest
from datetime import datetime, timezone

from docforensics.models import (
    AuditEvent,
    Document,
    EvidenceRef,
    ExtractedField,
    Finding,
    FindingCategory,
    InvestigationCase,
    ReviewState,
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

    def test_finding_rejects_invalid_category_state_and_missing_explanation(self) -> None:
        arguments = ("finding-1", FindingCategory.VISUAL, "A visible mark", "Inspect it", (self.evidence,))
        with self.assertRaisesRegex(ValueError, "category"):
            Finding("finding-1", "unknown", "A visible mark", "Inspect it", (self.evidence,))
        with self.assertRaisesRegex(ValueError, "review state"):
            Finding(*arguments, review_state="unknown")
        with self.assertRaisesRegex(ValueError, "explanation"):
            Finding("finding-1", FindingCategory.VISUAL, "A visible mark", "", (self.evidence,))
        self.assertEqual(Finding(*arguments, review_state=ReviewState.PENDING).review_state, ReviewState.PENDING)

    def test_page_numbers_and_counts_must_be_integers(self) -> None:
        with self.assertRaisesRegex(ValueError, "page_number"):
            SourceRegion(1.5, 0.2, 0.3, 0.6, 0.4)
        with self.assertRaisesRegex(ValueError, "page_count"):
            Document("doc-2", "sample.pdf", page_count=1.5)

    def test_case_rejects_duplicate_documents_and_dangling_audit_event(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate document"):
            InvestigationCase("case-1", documents=(self.document, self.document))
        event = AuditEvent("event-1", datetime.now(timezone.utc), "review", "missing-document")
        with self.assertRaisesRegex(ValueError, "unknown document"):
            InvestigationCase("case-1", documents=(self.document,), audit_events=(event,))

    def test_audit_event_requires_time_zone(self) -> None:
        with self.assertRaisesRegex(ValueError, "time zone"):
            AuditEvent("event-1", datetime(2026, 11, 1, 10, 0), "review")


if __name__ == "__main__":
    unittest.main()
