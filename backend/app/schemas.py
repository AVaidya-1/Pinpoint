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
