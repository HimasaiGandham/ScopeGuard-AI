import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from docforensics.models import (
    Document, EvidenceRef, ExtractedField, Finding, FindingCategory,
    InvestigationCase, ReviewState, SourceRegion,
)
from docforensics.processing import (
    ErrorCode, ProcessingError, ProcessingWarning, ReviewDecision, Stage, Status,
    StepFailure, StepOutput, WarningCode, run_pipeline,
)


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        self.case = InvestigationCase("test", (
            Document("d1", "one.pdf", page_count=1),
            Document("d2", "two.pdf", page_count=1),
        ))
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        self.report = Path(self.temp.name) / "contract-test.txt"
        self.report.write_text("Contract fixture only, not a generated dossier", encoding="utf-8")

    def evidence(self, document_id):
        return EvidenceRef(document_id, SourceRegion(1, 0.1, 0.1, 0.5, 0.2))

    def field(self, document_id):
        return ExtractedField(f"field-{document_id}", "test", f"fixture-{document_id}", self.evidence(document_id), 0.8)

    def adapter(self, request):
        if request.stage == Stage.OCR:
            return StepOutput(fields=(self.field(request.document_ids[0]),))
        if request.stage == Stage.VISUAL:
            document_id = request.document_ids[0]
            finding = Finding(f"visual-{document_id}", FindingCategory.VISUAL,
                              "Fixture observation", "Fixture explanation", (self.evidence(document_id),))
            return StepOutput(findings=(finding,))
        if request.stage == Stage.CONTEXTUAL and len(request.document_ids) >= 2:
            return StepOutput(findings=(Finding("cross-fixture", FindingCategory.CROSS_DOCUMENT,
                "Fixture values differ", "Compare the fixture source regions",
                tuple(self.evidence(document_id) for document_id in request.document_ids)),))
        if request.stage == Stage.REVIEW:
            return StepOutput(reviews=tuple(
                ReviewDecision(f.finding_id, ReviewState.ACCEPTED_FOR_REVIEW, "test-reviewer", "Fixture review")
                for f in request.case.findings
            ))
        if request.stage == Stage.DOSSIER:
            return StepOutput(artifact_path=str(self.report))
        return StepOutput()

    def adapters(self, **overrides):
        mapping = {stage: self.adapter for stage in Stage}
        mapping.update({Stage(name): adapter for name, adapter in overrides.items()})
        return mapping

    def step(self, run, stage, ids=None):
        return next(step for step in run.steps if step.stage == stage and (ids is None or step.document_ids == ids))

    def test_success_exchanges_records_and_preserves_original_case(self):
        observed_history = []

        def dossier(request):
            observed_history.extend(request.history)
            return self.adapter(request)

        run = run_pipeline(self.case, self.adapters(dossier=dossier))
        self.assertEqual(len(run.steps), 9)
        self.assertTrue(all(step.status == Status.COMPLETED for step in run.steps))
        self.assertEqual(len(run.case.fields), 2)
        self.assertEqual(len(run.case.findings), 3)
        self.assertTrue(all(f.review_state == ReviewState.ACCEPTED_FOR_REVIEW for f in run.case.findings))
        self.assertEqual(len(observed_history), 8)
        self.assertTrue(all(step.started_at and step.finished_at >= step.started_at for step in run.steps))
        self.assertEqual(self.case.fields, ())
        self.assertEqual(self.case.audit_events, ())
        self.assertEqual(run.case.documents, self.case.documents)
        self.assertTrue(run.summary()["has_dossier"])
        self.assertEqual(sum(e.action.endswith(".running") for e in run.case.audit_events), len(run.steps))
        self.assertEqual(len({e.event_id for e in run.case.audit_events}), len(run.case.audit_events))
        self.assertTrue(all(e.occurred_at.utcoffset() is not None for e in run.case.audit_events))
        self.assertTrue(any("reviewer=test-reviewer; note=Fixture review" in (e.details or "")
                            for e in run.case.audit_events))
        self.assertNotIn("Fixture review", str(run.summary()))

    def test_ocr_failure_keeps_other_document_and_limits_context_input(self):
        context_inputs = []

        def ocr(request):
            if request.document_ids == ("d1",):
                raise StepFailure(ProcessingError(ErrorCode.TIMEOUT, "OCR timed out", retryable=True))
            return self.adapter(request)

        def contextual(request):
            context_inputs.extend(request.document_ids)
            return StepOutput()

        run = run_pipeline(self.case, self.adapters(ocr=ocr, contextual=contextual))
        failed = self.step(run, Stage.OCR, ("d1",))
        self.assertEqual(failed.status, Status.FAILED)
        self.assertTrue(failed.error.retryable)
        self.assertEqual(context_inputs, ["d2"])
        self.assertEqual([f.source.document_id for f in run.case.fields], ["d2"])
        self.assertEqual(self.step(run, Stage.VISUAL, ("d1",)).status, Status.COMPLETED)
        self.assertEqual(self.step(run, Stage.CONTEXTUAL).warnings[0].code, WarningCode.PARTIAL_INPUT)
        self.assertEqual(self.step(run, Stage.DOSSIER).status, Status.COMPLETED)

    def test_ingestion_failure_skips_only_its_dependants(self):
        def ingestion(request):
            if request.document_ids == ("d1",):
                raise StepFailure(ProcessingError(ErrorCode.UNREADABLE_DOCUMENT, "Cannot read document"))
            return StepOutput()

        run = run_pipeline(self.case, self.adapters(ingestion=ingestion))
        self.assertEqual(self.step(run, Stage.OCR, ("d1",)).status, Status.SKIPPED)
        self.assertEqual(self.step(run, Stage.VISUAL, ("d1",)).error.code, ErrorCode.DEPENDENCY_FAILED)
        self.assertEqual(self.step(run, Stage.OCR, ("d2",)).status, Status.COMPLETED)

    def test_unimplemented_adapters_never_claim_completion(self):
        run = run_pipeline(self.case, {})
        self.assertTrue(all(step.status == Status.SKIPPED for step in run.steps))
        self.assertEqual(self.step(run, Stage.INGESTION, ("d1",)).error.code, ErrorCode.NOT_IMPLEMENTED)

    def test_missing_or_waiting_review_keeps_dossier_pending(self):
        for adapter in (None, lambda request: StepOutput(awaiting_review=True)):
            with self.subTest(adapter=adapter):
                mapping = self.adapters()
                if adapter is None:
                    mapping.pop(Stage.REVIEW)
                else:
                    mapping[Stage.REVIEW] = adapter
                run = run_pipeline(self.case, mapping)
                self.assertEqual(self.step(run, Stage.REVIEW).status, Status.PENDING)
                self.assertEqual(self.step(run, Stage.DOSSIER).status, Status.PENDING)
                self.assertIsNone(self.step(run, Stage.DOSSIER).started_at)
                self.assertFalse(run.summary()["has_dossier"])

    def test_out_of_scope_output_fails_atomically(self):
        def ocr(request):
            return StepOutput(fields=(self.field("d2"),)) if request.document_ids == ("d1",) else self.adapter(request)

        run = run_pipeline(self.case, self.adapters(ocr=ocr))
        self.assertEqual(self.step(run, Stage.OCR, ("d1",)).error.code, ErrorCode.INVALID_OUTPUT)
        self.assertEqual([f.field_id for f in run.case.fields], ["field-d2"])

    def test_unexpected_adapter_exception_does_not_leak_its_message(self):
        def ocr(request):
            raise ValueError("private token SECRET")

        run = run_pipeline(self.case, self.adapters(ocr=ocr))
        self.assertEqual(self.step(run, Stage.OCR, ("d1",)).error.code, ErrorCode.INTERNAL_ERROR)
        self.assertNotIn("SECRET", str(run.summary()))
        self.assertNotIn("SECRET", str(run.case.audit_events))

    def test_low_confidence_is_a_warning_not_a_failed_step(self):
        def ocr(request):
            return StepOutput(fields=(self.field(request.document_ids[0]),), warnings=(
                ProcessingWarning(WarningCode.LOW_CONFIDENCE, "A field needs review"),))

        run = run_pipeline(self.case, self.adapters(ocr=ocr))
        self.assertEqual(self.step(run, Stage.OCR, ("d1",)).status, Status.COMPLETED)
        self.assertEqual(self.step(run, Stage.OCR, ("d1",)).warnings[0].code, WarningCode.LOW_CONFIDENCE)

    def test_real_empty_ocr_and_missing_dossier_are_rejected(self):
        run = run_pipeline(self.case, self.adapters(ocr=lambda request: StepOutput(),
                                                   dossier=lambda request: StepOutput()))
        self.assertEqual(self.step(run, Stage.OCR, ("d1",)).error.code, ErrorCode.INVALID_OUTPUT)
        self.assertEqual(self.step(run, Stage.DOSSIER).error.code, ErrorCode.INVALID_OUTPUT)

    def test_cross_document_finding_needs_two_source_documents(self):
        def contextual(request):
            return StepOutput(findings=(Finding("cross", FindingCategory.CROSS_DOCUMENT,
                "Fixture conflict", "Fixture explanation", (self.evidence("d1"),)),))

        run = run_pipeline(self.case, self.adapters(contextual=contextual))
        self.assertEqual(self.step(run, Stage.CONTEXTUAL).error.code, ErrorCode.INVALID_OUTPUT)
        self.assertNotIn("cross", [f.finding_id for f in run.case.findings])

    def test_unreviewed_findings_cannot_be_marked_review_complete(self):
        run = run_pipeline(self.case, self.adapters(review=lambda request: StepOutput()))
        self.assertEqual(self.step(run, Stage.REVIEW).status, Status.FAILED)
        self.assertEqual(self.step(run, Stage.DOSSIER).status, Status.SKIPPED)

    def test_analysis_cannot_mark_its_own_finding_as_reviewed(self):
        def visual(request):
            return StepOutput(findings=(Finding("bypass-" + request.document_ids[0], FindingCategory.VISUAL,
                "Fixture observation", "Fixture explanation", (self.evidence(request.document_ids[0]),),
                review_state=ReviewState.ACCEPTED_FOR_REVIEW),))

        run = run_pipeline(self.case, self.adapters(visual=visual))
        self.assertEqual(self.step(run, Stage.VISUAL, ("d1",)).error.code, ErrorCode.INVALID_OUTPUT)
        self.assertFalse(any(f.finding_id.startswith("bypass-") for f in run.case.findings))

    def test_practice_empty_steps_are_explicitly_labelled(self):
        run = run_pipeline(self.case, {stage: lambda request: StepOutput() for stage in Stage}, practice_mode=True)
        self.assertEqual(run.summary()["mode"], "practice")
        self.assertTrue(all(step.status == Status.COMPLETED for step in run.steps))
        self.assertFalse(run.summary()["has_dossier"])
        self.assertEqual(run.case.fields, ())
        self.assertEqual(run.case.findings, ())

    def test_ingestion_can_classify_but_cannot_change_source_identity(self):
        def classify(request):
            document = next(d for d in request.case.documents if d.document_id == request.document_ids[0])
            return StepOutput(documents=(replace(document, document_type="fixture form"),))

        run = run_pipeline(self.case, self.adapters(ingestion=classify))
        self.assertTrue(all(d.document_type == "fixture form" for d in run.case.documents))

        def corrupt(request):
            document = next(d for d in request.case.documents if d.document_id == request.document_ids[0])
            return StepOutput(documents=(replace(document, filename="different.pdf"),))

        failed = run_pipeline(self.case, self.adapters(ingestion=corrupt))
        self.assertEqual(failed.case.documents, self.case.documents)
        self.assertEqual(self.step(failed, Stage.INGESTION, ("d1",)).error.code, ErrorCode.INVALID_OUTPUT)

    def test_errors_cannot_point_beyond_a_document_page_count(self):
        def fail(request):
            raise StepFailure(ProcessingError(ErrorCode.UNREADABLE_DOCUMENT, "Cannot read page", page_number=2))

        run = run_pipeline(self.case, self.adapters(ocr=fail))
        self.assertEqual(self.step(run, Stage.OCR, ("d1",)).error.code, ErrorCode.INVALID_OUTPUT)

    def test_previously_processed_case_cannot_reuse_stale_fields_or_findings(self):
        stale_finding = Finding("old", FindingCategory.VISUAL, "Old observation", "Old explanation",
                                (self.evidence("d1"),))
        for case in (replace(self.case, fields=(self.field("d1"),)),
                     replace(self.case, findings=(stale_finding,))):
            with self.subTest(case=case):
                with self.assertRaisesRegex(ValueError, "fresh case"):
                    run_pipeline(case, self.adapters())

    def test_within_document_finding_cannot_span_multiple_documents(self):
        def contextual(request):
            return StepOutput(findings=(Finding("wrong-scope", FindingCategory.WITHIN_DOCUMENT,
                "Fixture mismatch", "Fixture explanation", (self.evidence("d1"), self.evidence("d2"))),))

        run = run_pipeline(self.case, self.adapters(contextual=contextual))
        self.assertEqual(self.step(run, Stage.CONTEXTUAL).status, Status.FAILED)
        self.assertEqual(self.step(run, Stage.CONTEXTUAL).error.code, ErrorCode.INVALID_OUTPUT)

    def test_empty_dossier_file_is_rejected(self):
        self.report.write_bytes(b"")
        run = run_pipeline(self.case, self.adapters())
        self.assertEqual(self.step(run, Stage.DOSSIER).status, Status.FAILED)
        self.assertFalse(run.summary()["has_dossier"])

    def test_skipped_context_retains_partial_input_warning(self):
        def ocr(request):
            if request.document_ids == ("d1",):
                raise StepFailure(ProcessingError(ErrorCode.UNREADABLE_DOCUMENT, "Cannot read document"))
            return self.adapter(request)

        mapping = self.adapters(ocr=ocr)
        del mapping[Stage.CONTEXTUAL]
        run = run_pipeline(self.case, mapping)
        self.assertEqual(self.step(run, Stage.CONTEXTUAL).status, Status.SKIPPED)
        self.assertEqual(self.step(run, Stage.CONTEXTUAL).warnings[0].code, WarningCode.PARTIAL_INPUT)


if __name__ == "__main__":
    unittest.main()
