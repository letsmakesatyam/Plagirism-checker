"""
Handles validating and persisting uploaded submission files to disk.
Storage is local disk under settings.UPLOAD_DIR, organized as:
    uploads/submissions/<assignment_id>/<uuid>_<original_filename>
"""
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.config import settings

_EXT_TO_FILETYPE = {".pdf": "pdf", ".docx": "docx"}


def validate_upload(file: UploadFile, file_bytes: bytes) -> str:
    """Returns the normalized file_type ('pdf'/'docx') or raises HTTPException."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}",
        )

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    if len(file_bytes) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    return _EXT_TO_FILETYPE[suffix]


def save_submission_file(file_bytes: bytes, original_filename: str, assignment_id: str) -> tuple[str, str]:
    """
    Saves file_bytes to disk under a unique name.
    Returns (stored_filename, absolute_file_path).
    """
    suffix = Path(original_filename).suffix.lower()
    stored_filename = f"{uuid.uuid4().hex}{suffix}"

    target_dir = Path(settings.UPLOAD_DIR) / assignment_id
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / stored_filename
    target_path.write_bytes(file_bytes)

    return stored_filename, str(target_path)
