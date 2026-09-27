import uuid
from typing import Optional

from pydantic import BaseModel


class ComparisonParagraph(BaseModel):
    paragraph_index: int
    paragraph_text: str
    matched_paragraph_index: Optional[int] = None
    matched_paragraph_text: Optional[str] = None
    similarity: Optional[float] = None


class ComparisonOut(BaseModel):
    submission_a_id: uuid.UUID
    submission_b_id: uuid.UUID
    a_paragraphs: list[ComparisonParagraph]
    b_paragraphs: list[ComparisonParagraph]
    matched_paragraph_count: int
    average_similarity: Optional[float] = None
