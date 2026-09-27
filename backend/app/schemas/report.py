import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.report import AILabel, ReportStatus


class InternalMatchOut(BaseModel):
    source_paragraph_index: int
    source_paragraph_text: str
    matched_submission_id: uuid.UUID
    matched_paragraph_index: int
    matched_paragraph_text: str
    similarity: float

    class Config:
        from_attributes = True


class InternetMatchOut(BaseModel):
    source_paragraph_index: int
    source_paragraph_text: str
    matched_source_id: uuid.UUID
    matched_paragraph_index: int
    matched_paragraph_text: str
    similarity: float

    class Config:
        from_attributes = True


class AIResultOut(BaseModel):
    paragraph_index: int
    paragraph_text: str
    ai_probability: float
    label: AILabel

    class Config:
        from_attributes = True


class CopiedFromEntry(BaseModel):
    matched_submission_id: str
    matched_student_name: Optional[str] = None
    matched_original_filename: str
    paragraphs_matched: int
    average_similarity: float


class InternetSourceSummaryEntry(BaseModel):
    matched_source_id: str
    title: str
    url: Optional[str] = None
    category: str
    paragraphs_matched: int
    percentage_of_submission: float
    average_similarity: float


class ReportOut(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    status: ReportStatus
    error: Optional[str] = None
    internal_score: Optional[float] = None
    internet_score: Optional[float] = None
    ai_score: Optional[float] = None
    overall_originality_score: Optional[float] = None
    paragraphs_checked: Optional[int] = None
    paragraphs_flagged_internal: Optional[int] = None
    likely_ai_count: Optional[int] = None
    likely_human_count: Optional[int] = None
    uncertain_count: Optional[int] = None
    generated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ReportDetail(ReportOut):
    internal_matches: list[InternalMatchOut] = []
    internet_matches: list[InternetMatchOut] = []
    ai_results: list[AIResultOut] = []
    copied_from: list[CopiedFromEntry] = []
    internet_sources: list[InternetSourceSummaryEntry] = []
