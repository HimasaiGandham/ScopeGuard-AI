"""Processing contracts and a small synchronous coordinator for PS2 adapters."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Callable, Mapping
from uuid import uuid4

from .models import AuditEvent, Document, ExtractedField, Finding, FindingCategory, InvestigationCase, ReviewState


class Stage(StrEnum):
    INGESTION = "ingestion"
    OCR = "ocr"
    VISUAL = "visual"
    CONTEXTUAL = "contextual"
    REVIEW = "review"
    DOSSIER = "dossier"


class Status(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ErrorCode(StrEnum):
    MISSING_INPUT = "missing_input"
    UNREADABLE_DOCUMENT = "unreadable_document"
    UNSUPPORTED_DOCUMENT = "unsupported_document"
    SOURCE_CHANGED = "source_changed"
    TIMEOUT = "timeout"
    INVALID_OUTPUT = "invalid_output"
    NOT_IMPLEMENTED = "not_implemented"
    DEPENDENCY_FAILED = "dependency_failed"
    INTERNAL_ERROR = "internal_error"


class WarningCode(StrEnum):
    LOW_CONFIDENCE = "low_confidence"
    PARTIAL_INPUT = "partial_input"
    UNSUPPORTED_LAYOUT = "unsupported_layout"


@dataclass(frozen=True, slots=True)
class ProcessingError:
    code: ErrorCode
    message: str
    retryable: bool = False
    page_number: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, ErrorCode) or not self.message.strip():
            raise ValueError("processing errors require a supported code and message")
        if type(self.retryable) is not bool:
            raise ValueError("retryable must be true or false")
        if self.page_number is not None and (type(self.page_number) is not int or self.page_number < 1):
            raise ValueError("error page numbers must be positive integers")


@dataclass(frozen=True, slots=True)
class ProcessingWarning:
    code: WarningCode
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, WarningCode) or not self.message.strip():
            raise ValueError("processing warnings require a supported code and message")


class StepFailure(Exception):
    """An adapter's expected failure with a safe message for the reviewer."""

    def __init__(self, error: ProcessingError):
        if not isinstance(error, ProcessingError):
            raise ValueError("StepFailure requires ProcessingError")
        self.error = error
        super().__init__(error.message)


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    finding_id: str
    state: ReviewState
    reviewer: str
    note: str

    def __post_init__(self) -> None:
        if not self.finding_id.strip() or not self.reviewer.strip() or not self.note.strip():
            raise ValueError("review decisions require a finding, reviewer, and note")
        if self.state not in (ReviewState.ACCEPTED_FOR_REVIEW, ReviewState.DISMISSED):
            raise ValueError("review decisions must accept a lead or dismiss it")
        if not isinstance(self.state, ReviewState):
            raise ValueError("review state must use ReviewState")


DOCUMENT_STAGES = frozenset((Stage.INGESTION, Stage.OCR, Stage.VISUAL))


@dataclass(frozen=True, slots=True)
class StepRequest:
    stage: Stage
    case: InvestigationCase
    document_ids: tuple[str, ...]
    practice_mode: bool = False
    history: tuple[StepRecord, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.stage, Stage):
            raise ValueError("stage must use Stage")
        if type(self.practice_mode) is not bool:
            raise ValueError("practice_mode must be true or false")
        available = {document.document_id for document in self.case.documents}
        if not self.document_ids or len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("step inputs must list unique document IDs")
        if not set(self.document_ids) <= available:
            raise ValueError("step refers to an unknown input document")
        if self.stage in DOCUMENT_STAGES and len(self.document_ids) != 1:
            raise ValueError("document steps take exactly one document")


@dataclass(frozen=True, slots=True)
class StepOutput:
    documents: tuple[Document, ...] = ()
    fields: tuple[ExtractedField, ...] = ()
    findings: tuple[Finding, ...] = ()
    reviews: tuple[ReviewDecision, ...] = ()
    artifact_path: str | None = None
    warnings: tuple[ProcessingWarning, ...] = ()
    awaiting_review: bool = False

    def __post_init__(self) -> None:
        for collection in (self.documents, self.fields, self.findings, self.reviews, self.warnings):
            if not isinstance(collection, tuple):
                raise ValueError("step output collections must be tuples")
        if type(self.awaiting_review) is not bool:
            raise ValueError("awaiting_review must be true or false")
        if any(not isinstance(warning, ProcessingWarning) for warning in self.warnings):
            raise ValueError("warnings must use ProcessingWarning")
        if any(not isinstance(item, Document) for item in self.documents):
            raise ValueError("documents must use Document")
        if any(not isinstance(item, ExtractedField) for item in self.fields):
            raise ValueError("fields must use ExtractedField")
        if any(not isinstance(item, Finding) for item in self.findings):
            raise ValueError("findings must use Finding")
        if any(not isinstance(item, ReviewDecision) for item in self.reviews):
            raise ValueError("reviews must use ReviewDecision")


@dataclass(frozen=True, slots=True)
class StepRecord:
    stage: Stage
    document_ids: tuple[str, ...]
    status: Status
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: ProcessingError | None = None
    reason: str | None = None
    warnings: tuple[ProcessingWarning, ...] = ()
    output_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProcessingRun:
    case: InvestigationCase
    steps: tuple[StepRecord, ...]
    practice_mode: bool
    artifact_path: str | None = None

    def summary(self) -> dict:
        """Safe progress data without source text, review notes, or file paths."""
        return {
            "case_id": self.case.case_id,
            "mode": "practice" if self.practice_mode else "adapter_run",
            "steps": [
                {
                    "stage": step.stage.value,
                    "document_ids": list(step.document_ids),
                    "status": step.status.value,
                    "started_at": step.started_at.isoformat() if step.started_at else None,
                    "finished_at": step.finished_at.isoformat() if step.finished_at else None,
                    "error": ({"code": step.error.code.value, "message": step.error.message,
                               "retryable": step.error.retryable,
                               "page_number": step.error.page_number} if step.error else None),
                    "reason": step.reason,
                    "warnings": [{"code": warning.code.value, "message": warning.message}
                                 for warning in step.warnings],
                    "output_ids": list(step.output_ids),
                }
                for step in self.steps
            ],
            "field_count": len(self.case.fields),
            "finding_count": len(self.case.findings),
            "audit_event_count": len(self.case.audit_events),
            "has_dossier": self.artifact_path is not None,
        }


Adapter = Callable[[StepRequest], StepOutput]


def run_pipeline(
    case: InvestigationCase, adapters: Mapping[Stage, Adapter], *, practice_mode: bool = False
) -> ProcessingRun:
    """Run registered adapters; keep errors local and never fabricate outputs.

    Contextual analysis only receives document IDs whose OCR completed. Review
    can wait for a person; dossier generation then stays pending. Retry flags
    are descriptive: this coordinator does not automatically retry adapters.
    """
    if not isinstance(case, InvestigationCase):
        raise ValueError("case must use InvestigationCase")
    if not case.documents:
        raise ValueError("processing requires at least one document")
    if case.fields or case.findings:
        raise ValueError("processing requires a fresh case without earlier fields or findings; resume is not supported")
    if type(practice_mode) is not bool:
        raise ValueError("practice_mode must be true or false")
    if any(not isinstance(stage, Stage) or not callable(adapter) for stage, adapter in adapters.items()):
        raise ValueError("adapters must map Stage values to callables")
    coordinator = _Coordinator(case, adapters, practice_mode)
    all_ids = tuple(document.document_id for document in case.documents)
    ocr_ids: list[str] = []
    analysis_ids: set[str] = set()
    for document_id in all_ids:
        ids = (document_id,)
        ingestion = coordinator.execute(Stage.INGESTION, ids)
        if ingestion.status != Status.COMPLETED:
            coordinator.skip(Stage.OCR, ids, "Ingestion did not complete")
            coordinator.skip(Stage.VISUAL, ids, "Ingestion did not complete")
            continue
        ocr = coordinator.execute(Stage.OCR, ids)
        if ocr.status == Status.COMPLETED:
            ocr_ids.append(document_id)
        visual = coordinator.execute(Stage.VISUAL, ids)
        if visual.status == Status.COMPLETED:
            analysis_ids.add(document_id)

    if ocr_ids:
        partial = () if len(ocr_ids) == len(all_ids) else (
            ProcessingWarning(WarningCode.PARTIAL_INPUT, "Some documents have no completed OCR result"),
        )
        contextual = coordinator.execute(Stage.CONTEXTUAL, tuple(ocr_ids), partial)
        if contextual.status == Status.COMPLETED:
            analysis_ids.update(ocr_ids)
    else:
        coordinator.skip(Stage.CONTEXTUAL, all_ids, "No document has a completed OCR result")

    if not analysis_ids:
        coordinator.skip(Stage.REVIEW, all_ids, "No analysis step completed")
        coordinator.skip(Stage.DOSSIER, all_ids, "Human review did not complete")
    else:
        review = coordinator.execute(Stage.REVIEW, all_ids)
        if review.status == Status.PENDING:
            coordinator.wait(Stage.DOSSIER, all_ids, "Waiting for human review")
        elif review.status == Status.COMPLETED:
            coordinator.execute(Stage.DOSSIER, all_ids)
        else:
            coordinator.skip(Stage.DOSSIER, all_ids, "Human review did not complete")
    return ProcessingRun(coordinator.case, tuple(coordinator.steps), practice_mode, coordinator.artifact_path)


class _Coordinator:
    def __init__(self, case: InvestigationCase, adapters: Mapping[Stage, Adapter], practice_mode: bool):
        self.case = case
        self.adapters = adapters
        self.practice_mode = practice_mode
        self.steps: list[StepRecord] = []
        self.artifact_path: str | None = None

    def event(self, stage: Stage, status: Status, ids: tuple[str, ...], details: str) -> None:
        event = AuditEvent(str(uuid4()), datetime.now(timezone.utc), f"{stage.value}.{status.value}",
                           ids[0] if len(ids) == 1 else None, details)
        self.case = replace(self.case, audit_events=self.case.audit_events + (event,))

    def skip(self, stage: Stage, ids: tuple[str, ...], reason: str,
             code: ErrorCode = ErrorCode.DEPENDENCY_FAILED,
             warnings: tuple[ProcessingWarning, ...] = ()) -> StepRecord:
        record = StepRecord(stage, ids, Status.SKIPPED, finished_at=datetime.now(timezone.utc),
                            error=ProcessingError(code, reason), reason=reason, warnings=warnings)
        self.steps.append(record)
        self.event(stage, Status.SKIPPED, ids, reason)
        return record

    def wait(self, stage: Stage, ids: tuple[str, ...], reason: str,
             warnings: tuple[ProcessingWarning, ...] = ()) -> StepRecord:
        record = StepRecord(stage, ids, Status.PENDING, reason=reason, warnings=warnings)
        self.steps.append(record)
        self.event(stage, Status.PENDING, ids, reason)
        return record

    def execute(self, stage: Stage, ids: tuple[str, ...],
                warnings: tuple[ProcessingWarning, ...] = ()) -> StepRecord:
        adapter = self.adapters.get(stage)
        if adapter is None:
            if stage == Stage.REVIEW:
                return self.wait(stage, ids, "Waiting for a human review adapter", warnings)
            return self.skip(stage, ids, "No adapter is implemented for this step", ErrorCode.NOT_IMPLEMENTED, warnings)
        started = datetime.now(timezone.utc)
        self.event(stage, Status.RUNNING, ids, "Practice adapter started" if self.practice_mode else "Adapter started")
        try:
            request = StepRequest(stage, self.case, ids, self.practice_mode, tuple(self.steps))
            try:
                output = adapter(request)
            except StepFailure:
                raise
            except Exception as exc:
                raise StepFailure(ProcessingError(ErrorCode.INTERNAL_ERROR, "Adapter failed unexpectedly")) from exc
            if not isinstance(output, StepOutput):
                raise ValueError("adapter must return StepOutput")
            if output.awaiting_review:
                if stage != Stage.REVIEW or output.documents or output.fields or output.findings or output.reviews or output.artifact_path:
                    raise ValueError("only review may wait, without adding outputs")
                record = StepRecord(stage, ids, Status.PENDING, started_at=started,
                                    reason="Waiting for a human decision", warnings=warnings + output.warnings)
            else:
                candidate, output_ids = self.apply(request, output)
                self.case = candidate
                if output.artifact_path:
                    self.artifact_path = output.artifact_path
                record = StepRecord(stage, ids, Status.COMPLETED, started, datetime.now(timezone.utc),
                                    warnings=warnings + output.warnings, output_ids=output_ids)
                for decision in output.reviews:
                    self.event(stage, Status.COMPLETED, ids,
                               f"{decision.finding_id}: {decision.state.value}; reviewer={decision.reviewer}; note={decision.note}")
        except StepFailure as exc:
            error = exc.error
            if error.page_number is not None:
                document = next((d for d in self.case.documents if d.document_id == ids[0]), None)
                if len(ids) != 1 or (document.page_count is not None and error.page_number > document.page_count):
                    error = ProcessingError(ErrorCode.INVALID_OUTPUT, "Error refers to an invalid document page")
            record = StepRecord(stage, ids, Status.FAILED, started, datetime.now(timezone.utc), error=error,
                                warnings=warnings)
        except (ValueError, TypeError, AttributeError) as exc:
            record = StepRecord(stage, ids, Status.FAILED, started, datetime.now(timezone.utc),
                                error=ProcessingError(ErrorCode.INVALID_OUTPUT,
                                    str(exc) if isinstance(exc, ValueError) else "Adapter output failed validation"),
                                warnings=warnings)
        except Exception:
            record = StepRecord(stage, ids, Status.FAILED, started, datetime.now(timezone.utc),
                                error=ProcessingError(ErrorCode.INTERNAL_ERROR, "Adapter failed unexpectedly"),
                                warnings=warnings)
        self.steps.append(record)
        self.event(stage, record.status, ids, record.error.message if record.error else (record.reason or "Step completed"))
        return record

    def apply(self, request: StepRequest, output: StepOutput) -> tuple[InvestigationCase, tuple[str, ...]]:
        stage = request.stage
        if output.documents and stage != Stage.INGESTION:
            raise ValueError("only ingestion returns document classifications")
        updates = {document.document_id: document for document in output.documents}
        if len(updates) != len(output.documents) or not set(updates) <= set(request.document_ids):
            raise ValueError("document updates must name unique input documents")
        for document in self.case.documents:
            if document.document_id in updates and replace(updates[document.document_id], document_type=document.document_type) != document:
                raise ValueError("ingestion cannot change verified source identity")
        if output.fields and stage != Stage.OCR:
            raise ValueError("only OCR returns extracted fields")
        if output.findings and stage not in (Stage.VISUAL, Stage.CONTEXTUAL):
            raise ValueError("only analysis steps return findings")
        if output.reviews and stage != Stage.REVIEW:
            raise ValueError("only review returns decisions")
        if output.artifact_path and stage != Stage.DOSSIER:
            raise ValueError("only dossier returns an artifact")
        for item in output.fields:
            if item.source.document_id not in request.document_ids:
                raise ValueError("field evidence is outside this step's input")
        if stage == Stage.OCR and not self.practice_mode and not output.fields and not output.warnings:
            raise ValueError("empty OCR results require an explanatory warning")
        for finding in output.findings:
            if finding.review_state != ReviewState.PENDING:
                raise ValueError("new analysis findings must await human review")
            if any(evidence.document_id not in request.document_ids for evidence in finding.evidence):
                raise ValueError("finding evidence is outside this step's input")
            if stage == Stage.VISUAL and finding.category != FindingCategory.VISUAL:
                raise ValueError("visual analysis must return visual findings")
            if stage == Stage.CONTEXTUAL and finding.category == FindingCategory.VISUAL:
                raise ValueError("contextual analysis cannot return visual findings")
            if finding.category == FindingCategory.CROSS_DOCUMENT and len({e.document_id for e in finding.evidence}) < 2:
                raise ValueError("cross-document findings require evidence from two documents")
            if finding.category == FindingCategory.WITHIN_DOCUMENT and len({e.document_id for e in finding.evidence}) != 1:
                raise ValueError("within-document findings must reference exactly one document")
        decisions = {decision.finding_id: decision for decision in output.reviews}
        if len(decisions) != len(output.reviews) or not set(decisions) <= {f.finding_id for f in self.case.findings}:
            raise ValueError("review decisions must name unique existing findings")
        findings = tuple(replace(finding, review_state=decisions[finding.finding_id].state)
                         if finding.finding_id in decisions else finding for finding in self.case.findings)
        if stage == Stage.REVIEW and any(f.review_state == ReviewState.PENDING for f in findings):
            raise ValueError("unreviewed findings must wait for a human decision")
        if stage == Stage.DOSSIER and not self.practice_mode:
            if not output.artifact_path or not Path(output.artifact_path).is_file() or Path(output.artifact_path).stat().st_size == 0:
                raise ValueError("dossier must return an existing nonempty file")
        documents = tuple(updates.get(document.document_id, document) for document in self.case.documents)
        candidate = replace(self.case, documents=documents, fields=self.case.fields + output.fields,
                            findings=findings + output.findings)
        output_ids = tuple(updates) + tuple(item.field_id for item in output.fields) + tuple(f.finding_id for f in output.findings)
        return candidate, output_ids
