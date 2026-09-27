import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AssignmentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: Optional[str] = None
    due_date: Optional[datetime] = None


class AssignmentUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    is_active: Optional[bool] = None


class AssignmentOut(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str] = None
    faculty_id: uuid.UUID
    due_date: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AssignmentWithStats(AssignmentOut):
    submission_count: int = 0
    # Populated only for students: their own submission for this assignment,
    # if one exists. None means they haven't submitted yet. The frontend uses
    # this to disable/hide the upload control and link to the existing
    # submission instead of allowing a second upload.
    my_submission_id: Optional[uuid.UUID] = None
    my_submission_status: Optional[str] = None
