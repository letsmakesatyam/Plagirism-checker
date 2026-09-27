"""
Dashboard aggregation (Phase 5).

Every number here is derived from tables Phases 1-4 already populate
(Assignment, Submission, Report, InternalMatch, InternetMatch) — this module
adds no new tables, just read-side queries scoped to the requesting user.
Kept as pure functions (db + user id in, plain dict out) so the route layer
(app/api/routes/dashboard.py) stays a thin wrapper, matching the pattern
already used for report summaries in internal_plagiarism.py /
internet_plagiarism.py.

Deliberately simple, per-row queries rather than a single mega-join: a
dashboard is read occasionally (not a hot path), and readability was
prioritized over minimizing query count — see project ground rules.
"""
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.assignment import Assignment
from app.models.report import InternalMatch, InternetMatch, Report
from app.models.submission import Submission

RECENT_LIMIT = 10
TOP_LIMIT = 5


def _recent_entry(submission: Submission, db: Session) -> dict:
    report = db.query(Report).filter(Report.submission_id == submission.id).first()
    return {
        "submission_id": submission.id,
        "original_filename": submission.original_filename,
        "student_name": submission.student.full_name if submission.student else None,
        "assignment_title": submission.assignment.title if submission.assignment else None,
        "status": submission.status.value,
        "overall_originality_score": report.overall_originality_score if report else None,
        "submitted_at": submission.submitted_at,
    }


def _top_plagiarism_entry(report: Report) -> dict:
    submission = report.submission
    return {
        "submission_id": submission.id,
        "original_filename": submission.original_filename,
        "student_name": submission.student.full_name if submission.student else None,
        "assignment_title": submission.assignment.title if submission.assignment else "",
        "internal_score": report.internal_score,
        "internet_score": report.internet_score,
        "overall_originality_score": report.overall_originality_score,
    }


def _aggregate_sources(rows: list[InternetMatch], limit: int = TOP_LIMIT) -> list[dict]:
    """'Most copied sources' — groups InternetMatch rows by the source document
    they came from, across every one of the faculty's reports."""
    by_source: dict = {}
    for m in rows:
        by_source.setdefault(m.matched_source_id, []).append(m)

    summary = []
    for source_id, group in by_source.items():
        source = group[0].matched_source
        summary.append(
            {
                "matched_source_id": str(source_id),
                "title": source.title,
                "category": source.category.value,
                "times_matched": len(group),
            }
        )
    summary.sort(key=lambda s: s["times_matched"], reverse=True)
    return summary[:limit]


def _aggregate_similar_students(rows: list[InternalMatch], limit: int = TOP_LIMIT) -> list[dict]:
    """'Top similar students' — groups InternalMatch rows by which OTHER
    student's submission was the source of the match, i.e. whose work keeps
    turning up as the thing other submissions are flagged against."""
    by_student: dict = {}
    for m in rows:
        matched_submission = m.matched_submission
        if not matched_submission:
            continue
        by_student.setdefault(matched_submission.student_id, []).append(m)

    summary = []
    for student_id, group in by_student.items():
        student = group[0].matched_submission.student
        summary.append(
            {
                "matched_student_id": str(student_id),
                "matched_student_name": student.full_name if student else None,
                "times_matched": len(group),
            }
        )
    summary.sort(key=lambda s: s["times_matched"], reverse=True)
    return summary[:limit]


def _assignment_analytics(db: Session, faculty_id: uuid.UUID) -> list[dict]:
    assignments = (
        db.query(Assignment).filter(Assignment.faculty_id == faculty_id).order_by(Assignment.created_at.desc()).all()
    )

    results = []
    for assignment in assignments:
        submission_count = (
            db.query(func.count(Submission.id)).filter(Submission.assignment_id == assignment.id).scalar()
        )
        reports = (
            db.query(Report)
            .join(Submission, Report.submission_id == Submission.id)
            .filter(Submission.assignment_id == assignment.id, Report.overall_originality_score.isnot(None))
            .all()
        )
        average_score = (
            round(sum(r.overall_originality_score for r in reports) / len(reports), 2) if reports else None
        )
        results.append(
            {
                "assignment_id": assignment.id,
                "title": assignment.title,
                "submission_count": submission_count,
                "reports_generated": len(reports),
                "average_originality_score": average_score,
            }
        )
    return results


def faculty_dashboard(db: Session, faculty_id: uuid.UUID) -> dict:
    total_assignments = db.query(func.count(Assignment.id)).filter(Assignment.faculty_id == faculty_id).scalar()

    submissions_q = db.query(Submission).join(Assignment).filter(Assignment.faculty_id == faculty_id)
    total_submissions = submissions_q.count()

    status_counts = (
        db.query(Submission.status, func.count(Submission.id))
        .join(Assignment)
        .filter(Assignment.faculty_id == faculty_id)
        .group_by(Submission.status)
        .all()
    )
    submissions_by_status = {s.value: c for s, c in status_counts}

    recent = submissions_q.order_by(Submission.submitted_at.desc()).limit(RECENT_LIMIT).all()
    recent_submissions = [_recent_entry(s, db) for s in recent]

    top_reports = (
        db.query(Report)
        .join(Submission, Report.submission_id == Submission.id)
        .join(Assignment, Submission.assignment_id == Assignment.id)
        .filter(Assignment.faculty_id == faculty_id, Report.overall_originality_score.isnot(None))
        .order_by(Report.overall_originality_score.asc())
        .limit(TOP_LIMIT)
        .all()
    )
    top_plagiarism = [_top_plagiarism_entry(r) for r in top_reports]

    internet_rows = (
        db.query(InternetMatch)
        .join(Report, InternetMatch.report_id == Report.id)
        .join(Submission, Report.submission_id == Submission.id)
        .join(Assignment, Submission.assignment_id == Assignment.id)
        .filter(Assignment.faculty_id == faculty_id)
        .all()
    )
    most_copied_sources = _aggregate_sources(internet_rows)

    internal_rows = (
        db.query(InternalMatch)
        .join(Report, InternalMatch.report_id == Report.id)
        .join(Submission, Report.submission_id == Submission.id)
        .join(Assignment, Submission.assignment_id == Assignment.id)
        .filter(Assignment.faculty_id == faculty_id)
        .all()
    )
    top_similar_students = _aggregate_similar_students(internal_rows)

    return {
        "total_assignments": total_assignments,
        "total_submissions": total_submissions,
        "submissions_by_status": submissions_by_status,
        "recent_submissions": recent_submissions,
        "top_plagiarism": top_plagiarism,
        "most_copied_sources": most_copied_sources,
        "top_similar_students": top_similar_students,
        "assignment_analytics": _assignment_analytics(db, faculty_id),
    }


def student_dashboard(db: Session, student_id: uuid.UUID) -> dict:
    active_assignments = db.query(Assignment).filter(Assignment.is_active.is_(True)).all()

    my_submissions_q = db.query(Submission).filter(Submission.student_id == student_id)
    my_submissions = my_submissions_q.all()
    total_submissions = len(my_submissions)

    status_counts = (
        db.query(Submission.status, func.count(Submission.id))
        .filter(Submission.student_id == student_id)
        .group_by(Submission.status)
        .all()
    )
    submissions_by_status = {s.value: c for s, c in status_counts}

    recent = my_submissions_q.order_by(Submission.submitted_at.desc()).limit(RECENT_LIMIT).all()
    recent_submissions = [_recent_entry(s, db) for s in recent]

    submitted_assignment_ids = {s.assignment_id for s in my_submissions}
    pending_assignments = [
        {"assignment_id": a.id, "title": a.title, "due_date": a.due_date}
        for a in active_assignments
        if a.id not in submitted_assignment_ids
    ]

    return {
        "total_assignments_available": len(active_assignments),
        "total_submissions": total_submissions,
        "submissions_by_status": submissions_by_status,
        "recent_submissions": recent_submissions,
        "pending_assignments": pending_assignments,
    }
