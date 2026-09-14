"""Pydantic models for API requests and responses (P0 slice)."""

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    mime_type: str
    page_count: int
    sha256: str
    size_bytes: int


class DocumentCommit(BaseModel):
    upload_id: str
    pages: list[int] = Field(description="1-based physical page numbers to import")


class DocumentEnqueued(BaseModel):
    document_id: str
    job_id: str
    status: str


class PageInfo(BaseModel):
    id: str
    physical_page_number: int


class DocumentInfo(BaseModel):
    id: str
    filename: str
    mime_type: str
    status: str
    page_count: int
    pages: list[PageInfo]
    original_path: str


class CapacityInfo(BaseModel):
    total_pages: int
    max_pages: int
    remaining: int
    document_count: int
    max_documents: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]
    capacity: CapacityInfo


class HealthResponse(BaseModel):
    status: str
    model: str
    key_present: bool
    db_ok: bool


class ErrorResponse(BaseModel):
    code: str
    message: str


class SearchRequest(BaseModel):
    question: str
    document_ids: list[str]
    force_refresh: bool = False


class SearchCreated(BaseModel):
    search_id: str
    job_id: str


class CoverageInfo(BaseModel):
    checked_pages: int
    total_pages: int


class EvidenceItem(BaseModel):
    id: str
    document_id: str
    filename: str
    page_id: str
    physical_page_number: int
    kind: str
    scope: str
    boxes: list[list[float]]
    image_url: str


class SearchResponse(BaseModel):
    id: str
    state: str
    outcome: str
    coverage: CoverageInfo
    evidence: list[EvidenceItem]
    model_id: str
    errors: list[dict] = Field(default_factory=list)


class JobResponse(BaseModel):
    id: str
    kind: str
    state: str
    completed_units: int
    total_units: int
    error_code: str | None = None
    cancel_requested: bool = False
