"""
Internal plagiarism detection (Phase 4a).

"Internal" means: compare this submission's paragraphs against every other
paragraph already embedded in FAISS — which, by construction, covers every
other submission ever uploaded (any assignment, any student), since
embedding_pipeline.py indexes every submission the moment it's embedded.
This naturally satisfies the spec's "compare against current assignment +
previous submissions": both are just "other rows in the same FAISS index".

Algorithm, per paragraph of the checked submission:
1. Embed the paragraph and query FAISS for its nearest neighbours.
2. Drop any neighbour that belongs to this same submission (self-matches are
   not plagiarism) and any neighbour below INTERNAL_SIMILARITY_THRESHOLD.
3. Keep the single best remaining match, if any, as evidence for that
   paragraph. A paragraph counts as "flagged" if it has one.

Overall internal_score = (flagged paragraphs / total paragraphs) * 100.
This is intentionally a paragraph-coverage metric (how much of the document
appears elsewhere) rather than an average similarity — it is what "X% of
this submission matches other sources" actually means to a human reader.

`run_internal_check` writes its results directly onto the given `Report`
row and adds `InternalMatch` rows to the session, but does not commit or
touch `report.status` — see app/services/report_generation.py, which calls
this alongside `internet_plagiarism.run_internet_check` and owns the
overall status/commit lifecycle so that one check's failure never rolls
back the other's already-computed results.
"""
from sqlalchemy.orm import Session

from app.config import settings
from app.models.paragraph_embedding import ParagraphEmbedding
from app.models.report import InternalMatch, Report
from app.models.submission import Submission
from app.schemas.report import CopiedFromEntry
from app.services.vector_index import search as faiss_search


def run_internal_check(submission: Submission, report: Report, db: Session) -> None:
    own_rows = (
        db.query(ParagraphEmbedding)
        .filter(ParagraphEmbedding.submission_id == submission.id)
        .order_by(ParagraphEmbedding.paragraph_index)
        .all()
    )
    if not own_rows:
        raise ValueError(
            "Submission has no indexed paragraphs; cannot run internal plagiarism check."
        )

    own_ids = {row.id for row in own_rows}
    threshold = settings.INTERNAL_SIMILARITY_THRESHOLD

    # Wipe any previous run's matches before recomputing (report can be regenerated).
    db.query(InternalMatch).filter(InternalMatch.report_id == report.id).delete()

    from app.services.embeddings import embed_paragraphs  # local import: avoid loading model unless needed

    query_vectors = embed_paragraphs([row.paragraph_text for row in own_rows])

    best_by_paragraph: dict[int, tuple] = {}
    matched_ids_to_lookup: set[int] = set()
    for row, query_vector in zip(own_rows, query_vectors):
        raw_matches = faiss_search(query_vector, top_k=10 + len(own_ids))
        filtered = [(fid, score) for fid, score in raw_matches if fid not in own_ids and score >= threshold]
        if not filtered:
            continue
        best_id, best_score = max(filtered, key=lambda pair: pair[1])
        best_by_paragraph[row.paragraph_index] = (row, best_id, best_score)
        matched_ids_to_lookup.add(best_id)

    matched_rows = {}
    if matched_ids_to_lookup:
        matched_rows = {
            r.id: r for r in db.query(ParagraphEmbedding).filter(ParagraphEmbedding.id.in_(matched_ids_to_lookup))
        }

    flagged_count = 0
    new_matches: list[InternalMatch] = []
    for paragraph_index, (row, best_id, best_score) in best_by_paragraph.items():
        match_row = matched_rows.get(best_id)
        if not match_row:
            continue
        flagged_count += 1
        new_matches.append(
            InternalMatch(
                report_id=report.id,
                source_paragraph_index=paragraph_index,
                source_paragraph_text=row.paragraph_text,
                matched_submission_id=match_row.submission_id,
                matched_paragraph_index=match_row.paragraph_index,
                matched_paragraph_text=match_row.paragraph_text,
                similarity=round(best_score, 4),
            )
        )
    db.add_all(new_matches)

    total_paragraphs = len(own_rows)
    report.internal_score = round((flagged_count / total_paragraphs) * 100, 2) if total_paragraphs else 0.0
    report.paragraphs_checked = total_paragraphs
    report.paragraphs_flagged_internal = flagged_count


def copied_from_summary(report: Report, db: Session) -> list["CopiedFromEntry"]:
    """
    Aggregates InternalMatch rows into a per-source-submission summary:
    "X% of this submission's flagged paragraphs came from submission Y".
    This is the "copied from" list the spec asks for.
    """
    matches = report.internal_matches
    if not matches:
        return []

    by_submission: dict = {}
    for m in matches:
        by_submission.setdefault(m.matched_submission_id, []).append(m)

    summary = []
    for submission_id, group in by_submission.items():
        matched_submission = group[0].matched_submission
        summary.append(
            CopiedFromEntry(
                matched_submission_id=str(submission_id),
                matched_student_name=matched_submission.student.full_name if matched_submission.student else None,
                matched_original_filename=matched_submission.original_filename,
                paragraphs_matched=len(group),
                average_similarity=round(sum(m.similarity for m in group) / len(group), 4),
            )
        )
    summary.sort(key=lambda s: s.paragraphs_matched, reverse=True)
    return summary
