"""
Internet plagiarism detection (Phase 4b).

Mirrors internal_plagiarism.py exactly, except paragraphs are matched
against the internet-source FAISS index (app/services/vector_index_sources.py)
built from InternetSource / InternetSourceParagraph rows (see
app/services/source_ingestion.py) instead of against other submissions.

Uses INTERNET_SIMILARITY_THRESHOLD (0.78, lower than the internal 0.85) —
see app/config.py for why: web sources are more often paraphrased than
copied verbatim by the time they land in a submission.

`run_internet_check` writes results onto the given Report / adds
InternetMatch rows, following the same "no commit, no status change" contract
as run_internal_check — see report_generation.py for orchestration.
"""
from sqlalchemy.orm import Session

from app.config import settings
from app.models.internet_source import InternetSourceParagraph
from app.models.paragraph_embedding import ParagraphEmbedding
from app.models.report import InternetMatch, Report
from app.models.submission import Submission
from app.schemas.report import InternetSourceSummaryEntry
from app.services.vector_index_sources import search as faiss_search_sources


def run_internet_check(submission: Submission, report: Report, db: Session) -> None:
    own_rows = (
        db.query(ParagraphEmbedding)
        .filter(ParagraphEmbedding.submission_id == submission.id)
        .order_by(ParagraphEmbedding.paragraph_index)
        .all()
    )
    if not own_rows:
        raise ValueError(
            "Submission has no indexed paragraphs; cannot run internet plagiarism check."
        )

    threshold = settings.INTERNET_SIMILARITY_THRESHOLD

    db.query(InternetMatch).filter(InternetMatch.report_id == report.id).delete()

    from app.services.embeddings import embed_paragraphs  # local import: avoid loading model unless needed

    query_vectors = embed_paragraphs([row.paragraph_text for row in own_rows])

    best_by_paragraph: dict[int, tuple] = {}
    matched_ids_to_lookup: set[int] = set()
    for row, query_vector in zip(own_rows, query_vectors):
        raw_matches = faiss_search_sources(query_vector, top_k=5)
        filtered = [(fid, score) for fid, score in raw_matches if score >= threshold]
        if not filtered:
            continue
        best_id, best_score = max(filtered, key=lambda pair: pair[1])
        best_by_paragraph[row.paragraph_index] = (row, best_id, best_score)
        matched_ids_to_lookup.add(best_id)

    matched_rows = {}
    if matched_ids_to_lookup:
        matched_rows = {
            r.id: r
            for r in db.query(InternetSourceParagraph).filter(InternetSourceParagraph.id.in_(matched_ids_to_lookup))
        }

    flagged_count = 0
    new_matches: list[InternetMatch] = []
    for paragraph_index, (row, best_id, best_score) in best_by_paragraph.items():
        match_row = matched_rows.get(best_id)
        if not match_row:
            continue
        flagged_count += 1
        new_matches.append(
            InternetMatch(
                report_id=report.id,
                source_paragraph_index=paragraph_index,
                source_paragraph_text=row.paragraph_text,
                matched_source_id=match_row.source_id,
                matched_paragraph_index=match_row.paragraph_index,
                matched_paragraph_text=match_row.paragraph_text,
                similarity=round(best_score, 4),
            )
        )
    db.add_all(new_matches)

    total_paragraphs = len(own_rows)
    report.internet_score = round((flagged_count / total_paragraphs) * 100, 2) if total_paragraphs else 0.0


def internet_sources_summary(report: Report, db: Session) -> list["InternetSourceSummaryEntry"]:
    """
    'Source-wise percentage' the spec asks for: groups InternetMatch rows by
    the source document they came from, with each source's category, title,
    URL, how many paragraphs matched, and what share of the submission's
    total paragraphs that represents.
    """
    matches = report.internet_matches
    if not matches:
        return []

    total_paragraphs = report.paragraphs_checked or 1
    by_source: dict = {}
    for m in matches:
        by_source.setdefault(m.matched_source_id, []).append(m)

    summary = []
    for source_id, group in by_source.items():
        source = group[0].matched_source
        summary.append(
            InternetSourceSummaryEntry(
                matched_source_id=str(source_id),
                title=source.title,
                url=source.url,
                category=source.category.value,
                paragraphs_matched=len(group),
                percentage_of_submission=round((len(group) / total_paragraphs) * 100, 2),
                average_similarity=round(sum(m.similarity for m in group) / len(group), 4),
            )
        )
    summary.sort(key=lambda s: s.paragraphs_matched, reverse=True)
    return summary
