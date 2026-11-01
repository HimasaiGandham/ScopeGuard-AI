"""Shared, framework-independent data models for PS2.

All page regions use normalized coordinates between 0 and 1, with the origin at
the top-left of the displayed page. OCR, image analysis, the review interface,
and the dossier must all preserve this source location convention.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from math import isfinite
from re import fullmatch


class FindingCategory(StrEnum):
    VISUAL = "visual"
    WITHIN_DOCUMENT = "within_document"
    CROSS_DOCUMENT = "cross_document"


class ReviewState(StrEnum):
    PENDING = "pending"
    ACCEPTED_FOR_REVIEW = "accepted_for_review"
    DISMISSED = "dismissed"


@dataclass(frozen=True, slots=True)
class SourceRegion:
    """A rectangle on one page, independent of image or PDF resolution."""

    page_number: int
    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        if type(self.page_number) is not int or self.page_number < 1:
            raise ValueError("page_number must start at 1")
        coordinates = (self.x1, self.y1, self.x2, self.y2)
        if not all(isfinite(value) and 0 <= value <= 1 for value in coordinates):
            raise ValueError("region coordinates must be finite and between 0 and 1")
        if self.x1 >= self.x2 or self.y1 >= self.y2:
            raise ValueError("region must have positive width and height")

    @classmethod
    def from_pixels(
        cls,
        page_number: int,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        page_width: float,
        page_height: float,
    ) -> SourceRegion:
        """Convert an OCR or image bounding box to page-independent coordinates."""

        if page_width <= 0 or page_height <= 0:
            raise ValueError("page dimensions must be positive")
        return cls(
            page_number,
            x1 / page_width,
            y1 / page_height,
            x2 / page_width,
            y2 / page_height,
        )


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    document_id: str
    region: SourceRegion
    excerpt: str | None = None

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("evidence must name a document")
        if not isinstance(self.region, SourceRegion):
            raise ValueError("evidence regions must use SourceRegion")


@dataclass(frozen=True, slots=True)
class Document:
    document_id: str
    filename: str
    document_type: str | None = None
    page_count: int | None = None
    content_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.document_id.strip() or not self.filename.strip():
            raise ValueError("document_id and filename are required")
        if self.page_count is not None and (
            type(self.page_count) is not int or self.page_count < 1
        ):
            raise ValueError("page_count must be positive when known")
        if self.content_sha256 is not None and not fullmatch(
            r"[0-9a-fA-F]{64}", self.content_sha256
        ):
            raise ValueError("content_sha256 must be a SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class ExtractedField:
    field_id: str
    name: str
    value: str
    source: EvidenceRef
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.field_id.strip() or not self.name.strip():
            raise ValueError("field_id and name are required")
        if not isinstance(self.source, EvidenceRef):
            raise ValueError("field sources must use EvidenceRef")
        _check_confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class Finding:
    """An evidence-backed lead; review state does not assert fraud."""

    finding_id: str
    category: FindingCategory
    observation: str
    explanation: str
    evidence: tuple[EvidenceRef, ...]
    confidence: float | None = None
    review_state: ReviewState = ReviewState.PENDING

    def __post_init__(self) -> None:
        if not self.finding_id.strip() or not self.observation.strip() or not self.explanation.strip():
            raise ValueError("finding_id, observation, and explanation are required")
        if not isinstance(self.category, FindingCategory):
            raise ValueError("finding category is not supported")
        if not isinstance(self.review_state, ReviewState):
            raise ValueError("review state is not supported")
        if not isinstance(self.evidence, tuple):
            raise ValueError("finding evidence must be a tuple")
        if not self.evidence:
            raise ValueError("a finding must have at least one evidence reference")
        if any(not isinstance(item, EvidenceRef) for item in self.evidence):
            raise ValueError("finding evidence must use EvidenceRef")
        _check_confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    occurred_at: datetime
    action: str
    document_id: str | None = None
    details: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.action.strip():
            raise ValueError("event_id and action are required")
        if self.occurred_at.tzinfo is None:
            raise ValueError("audit timestamps must include a time zone")


@dataclass(frozen=True, slots=True)
class InvestigationCase:
    case_id: str
    documents: tuple[Document, ...]
    fields: tuple[ExtractedField, ...] = field(default_factory=tuple)
    findings: tuple[Finding, ...] = field(default_factory=tuple)
    audit_events: tuple[AuditEvent, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id is required")
        for items, item_type in (
            (self.documents, Document), (self.fields, ExtractedField),
            (self.findings, Finding), (self.audit_events, AuditEvent),
        ):
            if not isinstance(items, tuple):
                raise ValueError("case collections must be tuples")
            if any(not isinstance(item, item_type) for item in items):
                raise ValueError(f"case collection items must use {item_type.__name__}")
        _check_unique((document.document_id for document in self.documents), "document")
        _check_unique((item.field_id for item in self.fields), "field")
        _check_unique((item.finding_id for item in self.findings), "finding")
        _check_unique((event.event_id for event in self.audit_events), "audit event")

        documents = {document.document_id: document for document in self.documents}
        for item in self.fields:
            _check_evidence(item.source, documents)
        for finding in self.findings:
            for evidence in finding.evidence:
                _check_evidence(evidence, documents)
        for event in self.audit_events:
            if event.document_id is not None and event.document_id not in documents:
                raise ValueError(f"audit event refers to unknown document: {event.document_id}")


def _check_confidence(value: float | None) -> None:
    if value is not None and (not isfinite(value) or not 0 <= value <= 1):
        raise ValueError("confidence must be between 0 and 1 when known")


def _check_unique(identifiers: Iterable[str], label: str) -> None:
    seen: set[str] = set()
    for identifier in identifiers:
        if identifier in seen:
            raise ValueError(f"duplicate {label} id: {identifier}")
        seen.add(identifier)


def _check_evidence(evidence: EvidenceRef, documents: dict[str, Document]) -> None:
    document = documents.get(evidence.document_id)
    if document is None:
        raise ValueError(f"evidence refers to unknown document: {evidence.document_id}")
    if document.page_count is not None and evidence.region.page_number > document.page_count:
        raise ValueError(
            f"evidence page {evidence.region.page_number} exceeds "
            f"{document.document_id}'s {document.page_count} pages"
        )
