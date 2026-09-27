import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.submission import FileType, SubmissionStatus


class SubmissionOut(BaseModel):
    id: uuid.UUID
    assignment_id: uuid.UUID
    student_id: uuid.UUID
    original_filename: str
    file_type: FileType
    file_size_bytes: int
    status: SubmissionStatus
    extraction_error: Optional[str] = None
    embedding_error: Optional[str] = None
    was_ocr_used: Optional[bool] = None
    page_count: Optional[int] = None
    word_count: Optional[int] = None
    submitted_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubmissionDetail(SubmissionOut):
    extracted_text: Optional[str] = None
    paragraphs: Optional[list[str]] = None
