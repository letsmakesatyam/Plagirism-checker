"""
Dashboard endpoints (Phase 5). Aggregation-only — see
app/services/dashboard.py for the queries. No new tables.

GET /api/faculty/dashboard  -> faculty's own assignments/submissions/reports, aggregated
GET /api/students/dashboard -> student's own assignments/submissions, aggregated
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_role
from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.dashboard import FacultyDashboardOut, StudentDashboardOut
from app.services.dashboard import faculty_dashboard, student_dashboard

router = APIRouter(tags=["dashboard"])


@router.get("/api/faculty/dashboard", response_model=FacultyDashboardOut)
def get_faculty_dashboard(
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    return faculty_dashboard(db, faculty.id)


@router.get("/api/students/dashboard", response_model=StudentDashboardOut)
def get_student_dashboard(
    db: Session = Depends(get_db),
    student: User = Depends(require_role(UserRole.STUDENT)),
):
    return student_dashboard(db, student.id)
