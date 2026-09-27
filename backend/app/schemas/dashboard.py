import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RecentSubmissionEntry(BaseModel):
    submission_id: uuid.UUID
    original_filename: str
    student_name: Optional[str] = None
    assignment_title: Optional[str] = None
    status: str
    overall_originality_score: Optional[float] = None
    submitted_at: datetime


class TopPlagiarismEntry(BaseModel):
    submission_id: uuid.UUID
    original_filename: str
    student_name: Optional[str] = None
    assignment_title: str
    internal_score: Optional[float] = None
    internet_score: Optional[float] = None
    overall_originality_score: Optional[float] = None


class MostCopiedSourceEntry(BaseModel):
    matched_source_id: str
    title: str
    category: str
    times_matched: int


class TopSimilarStudentEntry(BaseModel):
    matched_student_id: str
    matched_student_name: Optional[str] = None
    times_matched: int


class AssignmentAnalyticsEntry(BaseModel):
    assignment_id: uuid.UUID
    title: str
    submission_count: int
    reports_generated: int
    average_originality_score: Optional[float] = None


class FacultyDashboardOut(BaseModel):
    total_assignments: int
    total_submissions: int
    submissions_by_status: dict[str, int]
    recent_submissions: list[RecentSubmissionEntry]
    top_plagiarism: list[TopPlagiarismEntry]
    most_copied_sources: list[MostCopiedSourceEntry]
    top_similar_students: list[TopSimilarStudentEntry]
    assignment_analytics: list[AssignmentAnalyticsEntry]


class PendingAssignmentEntry(BaseModel):
    assignment_id: uuid.UUID
    title: str
    due_date: Optional[datetime] = None


class StudentDashboardOut(BaseModel):
    total_assignments_available: int
    total_submissions: int
    submissions_by_status: dict[str, int]
    recent_submissions: list[RecentSubmissionEntry]
    pending_assignments: list[PendingAssignmentEntry]
