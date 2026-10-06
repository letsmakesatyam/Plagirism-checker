"""
Orchestrates every plagiarism check (internal, internet, and AI-text detection)
into a single Report row per submission.

Each check function (run_internal_check, run_internet_check, run_ai_check) is a
pure worker: it writes its own score fields and match/result rows onto the
Report/session and either succeeds or raises. This module is the only place that:
- creates/reuses the Report row,
- decides overall status (COMPLETE only if every check succeeded; FAILED with
  a combined error message if any check raised — but a failed check does NOT
  discard a different check's results, since each writes independent columns),
- computes `overall_originality_score` from whichever scores are available,
- commits.

Why `ai_score` is NOT folded into `overall_originality_score`: internal/internet
scores measure copying (text that exists elsewhere), which is what "originality"
means academically. AI-generated text can be entirely un-copied — original in
that sense — while still raising a different, separate concern the spec asks to
surface on its own (`report.ai_score`, paragraph-wise, "never claim certainty").
Conflating the two into one number would misrepresent both.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.report import Report, ReportStatus
from app.models.submission import Submission
from app.services.ai_detection import run_ai_check
from app.services.internal_plagiarism import run_internal_check
from app.services.internet_plagiarism import run_internet_check

logger = logging.getLogger(__name__)


def _get_or_create_report(submission: Submission, db: Session) -> Report:
    report = db.query(Report).filter(Report.submission_id == submission.id).first()
    if report is None:
        report = Report(submission_id=submission.id)
        db.add(report)
        db.flush()
    return report


def generate_full_report(submission: Submission, db: Session) -> Report:
    report = _get_or_create_report(submission, db)
    report.status = ReportStatus.GENERATING
    db.commit()

    errors: list[str] = []
    log_extra = {"submission_id": str(submission.id), "report_id": str(report.id)}
    logger.info("report_generation_started", extra=log_extra)

    try:
        run_internal_check(submission, report, db)
    except Exception as exc:  # noqa: BLE001 — collected, not fatal to the whole report
        logger.warning("internal_check_failed", extra=log_extra, exc_info=exc)
        errors.append(f"internal check failed: {exc}")

    try:
        run_internet_check(submission, report, db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("internet_check_failed", extra=log_extra, exc_info=exc)
        errors.append(f"internet check failed: {exc}")

    try:
        run_ai_check(submission, report, db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ai_check_failed", extra=log_extra, exc_info=exc)
        report.ai_status = "unavailable"
        report.ai_signal_strength = "unavailable"
        report.ai_score = None
        # Note: AI check failure is recorded as unavailable, but does not block
        # the report from completing or invalidate plagiarism findings.

    # overall_originality_score: 100 minus whichever plagiarism signal is
    # strongest. Using max() rather than averaging is deliberate — a
    # paragraph flagged by only one check is still a real originality
    # problem, so the worse of the two scores should drive the headline
    # number rather than being diluted by the other.
    scored_values = [s for s in (report.internal_score, report.internet_score) if s is not None]
    report.overall_originality_score = round(100 - max(scored_values), 2) if scored_values else None

    report.status = ReportStatus.FAILED if errors else ReportStatus.COMPLETE
    report.error = "; ".join(errors) if errors else None
    report.generated_at = datetime.utcnow()

    db.commit()
    db.refresh(report)
    logger.info(
        "report_generation_finished",
        extra={**log_extra, "status": report.status.value, "error_count": len(errors)},
    )
    return report
