"""
Submission model. A Student's uploaded file against an Assignment, plus the
results of the text-extraction pipeline (Phase 2). Plagiarism/AI-detection
scores are added as separate columns/tables in Phase 3-4.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum, Integer, Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class SubmissionStatus(str, enum.Enum):
    UPLOADED = "uploaded"          # file saved, extraction not yet run
    EXTRACTING = "extracting"      # extraction in progress
    EXTRACTED = "extracted"        # text extraction succeeded, embedding not yet run
    EMBEDDING = "embedding"        # embedding generation in progress
    EMBEDDED = "embedded"          # embeddings generated & indexed in FAISS — ready for comparison
    FAILED = "failed"              # extraction or embedding failed (see extraction_error/embedding_error)


class FileType(str, enum.Enum):
    PDF = "pdf"
    DOCX = "docx"


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        # One submission per student per assignment — re-submitting is not
        # supported (see docs/CHECKLIST.md). Enforced here, not just in the
        # API route, so it holds even under concurrent requests.
        UniqueConstraint("assignment_id", "student_id", name="uq_submissions_assignment_student"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False, unique=True)
    file_path = Column(String(500), nullable=False)
    file_type = Column(Enum(FileType), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)

    status = Column(Enum(SubmissionStatus), default=SubmissionStatus.UPLOADED, nullable=False, index=True)
    extraction_error = Column(Text, nullable=True)
    embedding_error = Column(Text, nullable=True)

    was_ocr_used = Column(Boolean, nullable=True)  # set after extraction; see services/extraction.py
    extracted_text = Column(Text, nullable=True)
    paragraphs = Column(JSONB, nullable=True)  # list[str], populated after extraction; embeddings use this in Phase 3
    page_count = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)

    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    assignment = relationship("Assignment", back_populates="submissions")
    student = relationship("User", foreign_keys=[student_id])

    def __repr__(self):
        return f"<Submission {self.original_filename} by {self.student_id}>"
