"""
Report endpoints (Phase 4 complete + Phase 5 additions).

POST /api/submissions/{id}/generate-report -> run/re-run plagiarism checks, return report
GET  /api/submissions/{id}/report          -> fetch existing report (404 if never generated)
GET  /api/submissions/{id}/report/pdf      -> download the report as a PDF (Phase 5)
GET  /api/reports                          -> faculty-only search/filter across their reports (Phase 5)
GET  /api/submissions/{a}/compare/{b}      -> faculty-only paragraph-level comparison (Phase 5)
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_role
from app.database import get_db
from app.models.assignment import Assignment
from app.models.report import Report, ReportStatus
from app.models.submission import Submission, SubmissionStatus
from app.models.user import User, UserRole
from app.schemas.comparison import ComparisonOut
from app.schemas.report import ReportDetail, ReportOut
from app.services.comparison import build_comparison
from app.services.internal_plagiarism import copied_from_summary
from app.services.internet_plagiarism import internet_sources_summary
from app.services.report_generation import generate_full_report
from app.services.report_pdf import generate_report_pdf

router = APIRouter(tags=["reports"])


def _authorize(submission: Submission, current_user: User) -> None:
    is_owner_student = current_user.role == UserRole.STUDENT and submission.student_id == current_user.id
    is_owner_faculty = current_user.role == UserRole.FACULTY and submission.assignment.faculty_id == current_user.id
    if not (is_owner_student or is_owner_faculty):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this submission")


def _to_detail(report: Report, db: Session) -> ReportDetail:
    detail = ReportDetail.model_validate(report)
    detail.copied_from = copied_from_summary(report, db)
    detail.internet_sources = internet_sources_summary(report, db)
    return detail


@router.post("/api/submissions/{submission_id}/generate-report", response_model=ReportDetail)
def generate_report(
    submission_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    _authorize(submission, current_user)

    if submission.status != SubmissionStatus.EMBEDDED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Submission is not ready for plagiarism checking (status={submission.status.value}). "
                "It must finish text extraction and embedding first."
            ),
        )

    if not submission.paragraphs or len(submission.paragraphs) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate plagiarism report: No readable text paragraphs were extracted from this submission.",
        )

    report = generate_full_report(submission, db)
    return _to_detail(report, db)


@router.get("/api/submissions/{submission_id}/report", response_model=ReportDetail)
def get_report(
    submission_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    _authorize(submission, current_user)

    report = db.query(Report).filter(Report.submission_id == submission_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No report generated yet for this submission. POST to /generate-report first.",
        )
    return _to_detail(report, db)


@router.get("/api/submissions/{submission_id}/report/pdf")
def download_report_pdf(
    submission_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Phase 5. Owner student or owning faculty only, same as GET .../report.
    Renders via app/services/report_pdf.py (reportlab — pure Python, no
    system dependencies needed beyond the pip package).
    """
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    _authorize(submission, current_user)

    report = db.query(Report).filter(Report.submission_id == submission_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No report generated yet for this submission. POST to /generate-report first.",
        )

    pdf_bytes = generate_report_pdf(report, submission)
    base_name = submission.original_filename.rsplit(".", 1)[0]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="plagiarism-report-{base_name}.pdf"'},
    )


@router.get("/api/reports", response_model=list[ReportOut])
def list_reports(
    status_filter: Optional[ReportStatus] = None,
    min_originality: Optional[float] = None,
    max_originality: Optional[float] = None,
    assignment_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    """
    Phase 5. Faculty-only report search/filter — covers the spec's "Filter
    reports" and "Search submissions" faculty features, scoped to reports
    generated for the faculty's own assignments. `search` matches the
    submission's original filename or the submitting student's name.
    """
    query = (
        db.query(Report)
        .join(Submission, Report.submission_id == Submission.id)
        .join(Assignment, Submission.assignment_id == Assignment.id)
        .join(User, Submission.student_id == User.id)
        .filter(Assignment.faculty_id == faculty.id)
    )
    if status_filter is not None:
        query = query.filter(Report.status == status_filter)
    if min_originality is not None:
        query = query.filter(Report.overall_originality_score >= min_originality)
    if max_originality is not None:
        query = query.filter(Report.overall_originality_score <= max_originality)
    if assignment_id is not None:
        query = query.filter(Assignment.id == assignment_id)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(Submission.original_filename.ilike(like), User.full_name.ilike(like)))

    return query.order_by(Report.generated_at.desc()).all()


@router.get("/api/submissions/{submission_id}/compare/{other_submission_id}", response_model=ComparisonOut)
def compare_submissions(
    submission_id: uuid.UUID,
    other_submission_id: uuid.UUID,
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    """
    Phase 5. Backend for the faculty "comparison page" — faculty-only per the
    spec. Faculty must own the assignment of `submission_id` (the primary
    submission being inspected); `other_submission_id` can belong to any
    assignment, since cross-assignment copying is exactly the kind of thing
    a comparison page should be able to surface.
    """
    submission_a = db.query(Submission).filter(Submission.id == submission_id).first()
    submission_b = db.query(Submission).filter(Submission.id == other_submission_id).first()
    if not submission_a or not submission_b:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    if submission_a.assignment.faculty_id != faculty.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this submission's assignment"
        )

    try:
        return build_comparison(submission_a, submission_b, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
