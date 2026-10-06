"""
Submission endpoints.

POST /api/assignments/{assignment_id}/submissions  -> student uploads a file
GET  /api/submissions/mine                          -> student's own submissions
                                                        supports ?status_filter= & ?search= (Phase 5)
GET  /api/submissions/{id}                          -> submission detail (owner student or owning faculty)
GET  /api/assignments/{assignment_id}/submissions    -> faculty views all submissions for their assignment
                                                        supports ?status_filter= & ?search= (Phase 5)
"""
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_role
from app.database import get_db
from app.models.assignment import Assignment
from app.models.paragraph_embedding import ParagraphEmbedding
from app.models.report import Report
from app.models.submission import Submission, SubmissionStatus
from app.models.user import User, UserRole
from app.schemas.submission import SubmissionDetail, SubmissionOut
from app.services import document_viewer, file_storage
from app.services.embedding_pipeline import generate_embeddings_for_submission
from app.services.extraction import extract_text
from app.services.vector_index import search as faiss_search

router = APIRouter(tags=["submissions"])
logger = logging.getLogger(__name__)


@router.post(
    "/api/assignments/{assignment_id}/submissions",
    response_model=SubmissionDetail,
    status_code=status.HTTP_201_CREATED,
)
def upload_submission(
    assignment_id: uuid.UUID,
    file: UploadFile,
    db: Session = Depends(get_db),
    student: User = Depends(require_role(UserRole.STUDENT)),
):
    # NOTE: this is a plain `def`, not `async def`, on purpose. Everything below
    # (text extraction, OCR, and especially the embedding model) is blocking,
    # CPU-bound, synchronous code. FastAPI automatically runs a sync path
    # operation function in a worker thread pool, which keeps the main asyncio
    # event loop free to keep serving every *other* request (auth/me, other
    # users' pages, etc.) while one upload is being processed. Declaring this
    # `async def` while calling blocking code directly inside it would instead
    # block that single shared event loop for the entire server until this
    # function returns — which is what caused uploads to appear stuck and,
    # at the same time, made unrelated requests (like the session check on
    # page refresh) hang too.
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id, Assignment.is_active.is_(True)).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    existing = (
        db.query(Submission)
        .filter(Submission.assignment_id == assignment_id, Submission.student_id == student.id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already submitted for this assignment. Only one submission per assignment is allowed.",
        )

    # file.file is the underlying SpooledTemporaryFile — its .read() is a plain
    # synchronous call, unlike UploadFile.read() which is a coroutine and can
    # only be awaited from an async def function.
    file_bytes = file.file.read()
    file_type = file_storage.validate_upload(file, file_bytes)
    stored_filename, file_path = file_storage.save_submission_file(file_bytes, file.filename, str(assignment_id))

    submission = Submission(
        assignment_id=assignment_id,
        student_id=student.id,
        original_filename=file.filename,
        stored_filename=stored_filename,
        file_path=file_path,
        file_type=file_type,
        file_size_bytes=len(file_bytes),
        status=SubmissionStatus.EXTRACTING,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    logger.info(
        "submission_uploaded",
        extra={"submission_id": str(submission.id), "assignment_id": str(assignment_id), "file_type": file_type},
    )

    # Extraction runs synchronously for now (Phase 2). Phase 3+ can move this to a
    # background task / queue once embeddings are chained onto the same pipeline.
    result = extract_text(file_path, file_type)
    if result.error or not result.paragraphs or result.word_count == 0:
        error_msg = result.error or "No readable text or paragraphs could be extracted from this file."
        submission.status = SubmissionStatus.FAILED
        submission.extraction_error = error_msg
        submission.was_ocr_used = result.was_ocr_used
        submission.page_count = result.page_count
        db.commit()
        db.refresh(submission)
        logger.warning(
            "extraction_failed",
            extra={"submission_id": str(submission.id), "error": error_msg},
        )
        return submission

    submission.status = SubmissionStatus.EXTRACTED
    submission.extracted_text = result.text
    submission.paragraphs = result.paragraphs
    submission.page_count = result.page_count
    submission.word_count = result.word_count
    submission.was_ocr_used = result.was_ocr_used
    db.commit()
    db.refresh(submission)

    # Phase 3: generate embeddings and index them in FAISS for semantic comparison.
    submission.status = SubmissionStatus.EMBEDDING
    db.commit()
    try:
        generate_embeddings_for_submission(submission, db)
        submission.status = SubmissionStatus.EMBEDDED
    except Exception as exc:  # noqa: BLE001 — surfaced via embedding_error, not a 500
        submission.status = SubmissionStatus.FAILED
        submission.embedding_error = str(exc)
        logger.warning("embedding_failed", extra={"submission_id": str(submission.id)}, exc_info=exc)

    db.commit()
    db.refresh(submission)
    logger.info(
        "submission_pipeline_finished",
        extra={"submission_id": str(submission.id), "status": submission.status.value},
    )
    return submission


@router.get("/api/submissions/mine", response_model=list[SubmissionOut])
def list_my_submissions(
    status_filter: Optional[SubmissionStatus] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    student: User = Depends(require_role(UserRole.STUDENT)),
):
    query = db.query(Submission).filter(Submission.student_id == student.id)
    if status_filter is not None:
        query = query.filter(Submission.status == status_filter)
    if search:
        query = query.filter(Submission.original_filename.ilike(f"%{search}%"))
    return query.order_by(Submission.submitted_at.desc()).all()


@router.get("/api/submissions/{submission_id}", response_model=SubmissionDetail)
def get_submission(
    submission_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    is_owner_student = current_user.role == UserRole.STUDENT and submission.student_id == current_user.id
    is_owner_faculty = (
        current_user.role == UserRole.FACULTY and submission.assignment.faculty_id == current_user.id
    )
    if not (is_owner_student or is_owner_faculty):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this submission")

    return submission


@router.get("/api/assignments/{assignment_id}/submissions", response_model=list[SubmissionOut])
def list_assignment_submissions(
    assignment_id: uuid.UUID,
    status_filter: Optional[SubmissionStatus] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    if assignment.faculty_id != faculty.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this assignment")

    query = db.query(Submission).filter(Submission.assignment_id == assignment_id)
    if status_filter is not None:
        query = query.filter(Submission.status == status_filter)
    if search:
        # Phase 5: search matches either the uploaded filename or the submitting
        # student's name (the "Search submissions" faculty feature from the spec).
        query = query.join(User, Submission.student_id == User.id).filter(
            or_(Submission.original_filename.ilike(f"%{search}%"), User.full_name.ilike(f"%{search}%"))
        )
    return query.order_by(Submission.submitted_at.desc()).all()


@router.get("/api/submissions/{submission_id}/file")
def download_submission_file(
    submission_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    Phase 6. Serves the original uploaded file (PDF/DOCX) so the frontend can
    render an inline preview (e.g. the report page's PDF viewer). Same
    owner-student-or-owning-faculty authorization as every other submission
    endpoint — this is the raw file, so it's not opened up any wider than that.
    """
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    is_owner_student = current_user.role == UserRole.STUDENT and submission.student_id == current_user.id
    is_owner_faculty = (
        current_user.role == UserRole.FACULTY and submission.assignment.faculty_id == current_user.id
    )
    if not (is_owner_student or is_owner_faculty):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this submission")

    file_path = Path(submission.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file is missing on disk")

    media_type = "application/pdf" if submission.file_type.value == "pdf" else (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(path=file_path, media_type=media_type, filename=submission.original_filename)


@router.get("/api/submissions/{submission_id}/document-view")
def get_submission_document_view(
    submission_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns page metadata and highlight bounding box coordinates for this submission.
    Available to the owner student or owning faculty. Works before or after report generation.
    """
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    is_owner_student = current_user.role == UserRole.STUDENT and submission.student_id == current_user.id
    is_owner_faculty = (
        current_user.role == UserRole.FACULTY and submission.assignment.faculty_id == current_user.id
    )
    if not (is_owner_student or is_owner_faculty):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this submission")

    file_path = Path(submission.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file is missing on disk")

    report = db.query(Report).filter(Report.submission_id == submission_id).first()
    try:
        return document_viewer.get_submission_document_pages(submission, report, db)
    except Exception as exc:
        logger.error(f"Error computing document view: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate document view: {exc}")


@router.get("/api/submissions/{submission_id}/pages/{page}/image")
def get_submission_page_image(
    submission_id: uuid.UUID,
    page: int,
    annotated: bool = False,
    dpi: int = 150,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Renders high-resolution image of a page from the authentic document.
    Default annotated=False returns the clean original page image for interactive overlays.
    """
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    is_owner_student = current_user.role == UserRole.STUDENT and submission.student_id == current_user.id
    is_owner_faculty = (
        current_user.role == UserRole.FACULTY and submission.assignment.faculty_id == current_user.id
    )
    if not (is_owner_student or is_owner_faculty):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this submission")

    file_path = Path(submission.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file is missing on disk")

    report = db.query(Report).filter(Report.submission_id == submission_id).first()
    try:
        img_bytes = document_viewer.render_page_image_bytes(submission, report, db, page_number=page, annotated=annotated, dpi=dpi)
        return Response(content=img_bytes, media_type="image/png")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        logger.error(f"Error rendering page image: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to render page image")


@router.get("/api/submissions/{submission_id}/annotated-file")
def download_annotated_file(
    submission_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generates and downloads an annotated PDF copy of the document with highlights embedded.
    """
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    is_owner_student = current_user.role == UserRole.STUDENT and submission.student_id == current_user.id
    is_owner_faculty = (
        current_user.role == UserRole.FACULTY and submission.assignment.faculty_id == current_user.id
    )
    if not (is_owner_student or is_owner_faculty):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this submission")

    file_path = Path(submission.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file is missing on disk")

    report = db.query(Report).filter(Report.submission_id == submission_id).first()
    try:
        pdf_bytes = document_viewer.generate_annotated_document_pdf(submission, report, db)
        stem = Path(submission.original_filename).stem
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="annotated-{stem}.pdf"'},
        )
    except Exception as exc:
        logger.error(f"Error generating annotated file: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate annotated PDF")



@router.get("/api/submissions/{submission_id}/similar-paragraphs")
def get_similar_paragraphs(
    submission_id: uuid.UUID,
    top_k: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Phase 3 preview / diagnostic: for each paragraph in this submission, returns
    the most semantically similar paragraphs found anywhere in the FAISS index
    (across all submissions, including this one — self-matches are excluded).

    This is the raw building block Phase 4's internal-plagiarism report will be
    built on top of (percentage scoring, source attribution, highlighting, etc.
    are not implemented yet — this endpoint just proves the retrieval works).
    """
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    is_owner_student = current_user.role == UserRole.STUDENT and submission.student_id == current_user.id
    is_owner_faculty = (
        current_user.role == UserRole.FACULTY and submission.assignment.faculty_id == current_user.id
    )
    if not (is_owner_student or is_owner_faculty):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this submission")

    own_paragraph_rows = (
        db.query(ParagraphEmbedding)
        .filter(ParagraphEmbedding.submission_id == submission_id)
        .order_by(ParagraphEmbedding.paragraph_index)
        .all()
    )
    if not own_paragraph_rows:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No embeddings available yet for this submission (status={submission.status.value})",
        )

    own_ids = {row.id for row in own_paragraph_rows}
    from app.services.embeddings import embed_paragraphs  # local import: avoid loading the model unless needed

    query_vectors = embed_paragraphs([row.paragraph_text for row in own_paragraph_rows])

    results = []
    for row, query_vector in zip(own_paragraph_rows, query_vectors):
        raw_matches = faiss_search(query_vector, top_k=top_k + len(own_ids))
        matches = [(faiss_id, score) for faiss_id, score in raw_matches if faiss_id not in own_ids][:top_k]

        match_details = []
        if matches:
            match_ids = [m[0] for m in matches]
            match_rows = {r.id: r for r in db.query(ParagraphEmbedding).filter(ParagraphEmbedding.id.in_(match_ids))}
            for faiss_id, score in matches:
                match_row = match_rows.get(faiss_id)
                if match_row:
                    match_details.append(
                        {
                            "similarity": round(score, 4),
                            "matched_submission_id": str(match_row.submission_id),
                            "matched_paragraph_text": match_row.paragraph_text,
                        }
                    )

        results.append(
            {
                "paragraph_index": row.paragraph_index,
                "paragraph_text": row.paragraph_text,
                "matches": match_details,
            }
        )

    return {"submission_id": str(submission_id), "paragraph_results": results}
