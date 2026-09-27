"""
Submission-vs-submission comparison (Phase 5) — backend for the faculty
"comparison page" the spec asks for.

Reuses InternalMatch rows already computed by internal_plagiarism.py
(Phase 4a) rather than re-running any similarity search: a comparison is
just "show me the subset of submission A's already-computed matches that
point at submission B, and vice versa". Both submissions need a generated
report first, since that's what populates InternalMatch — see the
ValueError below.
"""
import uuid

from sqlalchemy.orm import Session

from app.models.paragraph_embedding import ParagraphEmbedding
from app.models.report import InternalMatch, Report
from app.models.submission import Submission


def _paragraphs_with_matches(submission: Submission, other_submission_id: uuid.UUID, db: Session) -> list[dict]:
    report = db.query(Report).filter(Report.submission_id == submission.id).first()
    if report is None:
        raise ValueError(
            f"Submission {submission.id} has no generated report yet. "
            "Generate a report for both submissions before comparing them."
        )

    own_rows = (
        db.query(ParagraphEmbedding)
        .filter(ParagraphEmbedding.submission_id == submission.id)
        .order_by(ParagraphEmbedding.paragraph_index)
        .all()
    )

    matches_by_index = {
        m.source_paragraph_index: m
        for m in db.query(InternalMatch).filter(
            InternalMatch.report_id == report.id,
            InternalMatch.matched_submission_id == other_submission_id,
        )
    }

    paragraphs = []
    for row in own_rows:
        match = matches_by_index.get(row.paragraph_index)
        paragraphs.append(
            {
                "paragraph_index": row.paragraph_index,
                "paragraph_text": row.paragraph_text,
                "matched_paragraph_index": match.matched_paragraph_index if match else None,
                "matched_paragraph_text": match.matched_paragraph_text if match else None,
                "similarity": match.similarity if match else None,
            }
        )
    return paragraphs


def build_comparison(submission_a: Submission, submission_b: Submission, db: Session) -> dict:
    a_paragraphs = _paragraphs_with_matches(submission_a, submission_b.id, db)
    b_paragraphs = _paragraphs_with_matches(submission_b, submission_a.id, db)

    matched_count = sum(1 for p in a_paragraphs if p["similarity"] is not None)
    all_similarities = [p["similarity"] for p in a_paragraphs + b_paragraphs if p["similarity"] is not None]

    return {
        "submission_a_id": submission_a.id,
        "submission_b_id": submission_b.id,
        "a_paragraphs": a_paragraphs,
        "b_paragraphs": b_paragraphs,
        "matched_paragraph_count": matched_count,
        "average_similarity": round(sum(all_similarities) / len(all_similarities), 4) if all_similarities else None,
    }
