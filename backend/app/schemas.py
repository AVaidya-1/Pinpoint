from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DocStatus(str, Enum):
    importing = "importing"
    ready = "ready"
    failed = "failed"


class JobState(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    interrupted = "interrupted"


class SearchOutcome(str, Enum):
    found = "found"
    no_evidence = "no_evidence"
    uncertain = "uncertain"
    incomplete = "incomplete"


class InspectionStatus(str, Enum):
    found = "found"
    not_found = "not_found"
    uncertain = "uncertain"


class EvidenceKind(str, Enum):
    text = "text"
    table = "table"
    diagram = "diagram"
    chart = "chart"
    photo = "photo"


class EvidenceScope(str, Enum):
    region = "region"
    page = "page"


class CheckStatus(str, Enum):
    accepted = "accepted"
    rejected = "rejected"
    uncertain = "uncertain"


class InspectionResponse(BaseModel):
    status: InspectionStatus
    kind: Optional[EvidenceKind] = None
    boxes_2d: list[list[int]] = Field(default_factory=list)
    scope: Optional[EvidenceScope] = None


class CheckResponse(BaseModel):
    verdict: CheckStatus


class DocumentOut(BaseModel):
    id: str
    original_filename: str
    mime_type: str
    page_count: int
    selected_pages: list[int]
    status: str
    created_at: str


class PageOut(BaseModel):
    id: str
    document_id: str
    physical_page_number: int
    width_px: int
    height_px: int


class EvidenceOut(BaseModel):
    id: str
    document_id: str
    filename: str
    page_id: str
    physical_page_number: int
    kind: str
    scope: str
    boxes: list[list[float]]
    image_url: str


class SearchOut(BaseModel):
    id: str
    state: str
    outcome: Optional[str] = None
    question: str
    checked_pages: int
    total_pages: int
    evidence: list[EvidenceOut] = Field(default_factory=list)
    model_id: str
    created_at: str


class JobOut(BaseModel):
    id: str
    kind: str
    state: str
    completed_units: int
    total_units: int
    created_at: str


class HealthOut(BaseModel):
    status: str
    model: str
    key_present: bool
    total_pages: int
    max_pages: int
