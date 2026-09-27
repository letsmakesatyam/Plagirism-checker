import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.internet_source import InternetSourceCategory


class InternetSourceCreateFromText(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    category: InternetSourceCategory
    text: str = Field(min_length=50)
    url: Optional[str] = None


class InternetSourceCreateFromUrl(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    category: InternetSourceCategory
    url: str = Field(min_length=5)


class InternetSourceOut(BaseModel):
    id: uuid.UUID
    title: str
    url: Optional[str] = None
    category: InternetSourceCategory
    paragraph_count: int
    created_at: datetime

    class Config:
        from_attributes = True
