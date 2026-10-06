"""
Report model (Phase 4). One row per submission, created/updated once plagiarism
checks run. Holds only the aggregate scores + status; per-paragraph evidence
lives in InternalMatch, InternetMatch, and (Phase 4c) AIResult (all this file).

Score fields are nullable because the three checks (internal / internet / AI)
run independently and may finish at different times — a report is "complete"
once every requested check has a non-null score, but partial reports are
valid and viewable (e.g. internal_score ready while internet_score is still
being computed).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class ReportStatus(str, enum.Enum):
    PENDING = "pending"        # not yet generated
    GENERATING = "generating"  # checks currently running
    COMPLETE = "complete"      # all requested checks finished
    FAILED = "failed"


class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(
        UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    status = Column(Enum(ReportStatus), default=ReportStatus.PENDING, nullable=False, index=True)
    error = Column(Text, nullable=True)

    # Aggregate scores, 0-100. internet_score and ai_score are populated by
    # later phases (4b/4c) and are nullable until then.
    internal_score = Column(Float, nullable=True)
    internet_score = Column(Float, nullable=True)
    ai_score = Column(Float, nullable=True)
    overall_originality_score = Column(Float, nullable=True)  # 100 - max(internal, internet); see service docstring

    paragraphs_checked = Column(Integer, nullable=True)
    paragraphs_flagged_internal = Column(Integer, nullable=True)

    # Phase 4c: AI-text-detection paragraph counts. Kept as three independent
    # buckets (not just a flagged/not-flagged pair) because the AI check
    # deliberately reports "uncertain" for paragraphs it can't confidently
    # call either way — see app/services/ai_detection.py.
    likely_ai_count = Column(Integer, nullable=True)
    likely_human_count = Column(Integer, nullable=True)
    uncertain_count = Column(Integer, nullable=True)

    # Auditable AI metadata and signal presentation
    ai_status = Column(String(50), nullable=True)  # completed, insufficient_text, unreliable_ocr, unavailable, legacy
    ai_model_name = Column(String(150), nullable=True)
    ai_method_version = Column(String(50), nullable=True)
    ai_word_coverage_pct = Column(Float, nullable=True)
    ai_evaluated_words = Column(Integer, nullable=True)
    ai_skipped_words = Column(Integer, nullable=True)
    ai_signal_strength = Column(String(50), nullable=True)  # low, moderate, elevated, uncertain, unavailable

    generated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    submission = relationship("Submission")
    internal_matches = relationship("InternalMatch", back_populates="report", cascade="all, delete-orphan")
    internet_matches = relationship("InternetMatch", back_populates="report", cascade="all, delete-orphan")
    ai_results = relationship("AIResult", back_populates="report", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Report submission={self.submission_id} status={self.status}>"


class InternalMatch(Base):
    """
    One row per matched paragraph pair found during internal plagiarism
    scoring: paragraph #`source_paragraph_index` of the checked submission
    is semantically similar (>= threshold) to a paragraph found in some other
    submission already indexed in FAISS.
    """

    __tablename__ = "internal_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id = Column(UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)

    source_paragraph_index = Column(Integer, nullable=False)
    source_paragraph_text = Column(Text, nullable=False)

    matched_submission_id = Column(UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False)
    matched_paragraph_index = Column(Integer, nullable=False)
    matched_paragraph_text = Column(Text, nullable=False)

    similarity = Column(Float, nullable=False)  # cosine similarity, 0-1

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    report = relationship("Report", back_populates="internal_matches")
    matched_submission = relationship("Submission", foreign_keys=[matched_submission_id])

    def __repr__(self):
        return f"<InternalMatch report={self.report_id} sim={self.similarity:.2f}>"


class InternetMatch(Base):
    """
    Mirrors InternalMatch, but the matched paragraph comes from the internet
    knowledge base (InternetSourceParagraph) instead of another submission.
    """

    __tablename__ = "internet_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id = Column(UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)

    source_paragraph_index = Column(Integer, nullable=False)
    source_paragraph_text = Column(Text, nullable=False)

    matched_source_id = Column(UUID(as_uuid=True), ForeignKey("internet_sources.id", ondelete="CASCADE"), nullable=False)
    matched_paragraph_index = Column(Integer, nullable=False)
    matched_paragraph_text = Column(Text, nullable=False)

    similarity = Column(Float, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    report = relationship("Report", back_populates="internet_matches")
    matched_source = relationship("InternetSource", foreign_keys=[matched_source_id])

    def __repr__(self):
        return f"<InternetMatch report={self.report_id} sim={self.similarity:.2f}>"


class AILabel(str, enum.Enum):
    LIKELY_HUMAN = "likely_human"
    UNCERTAIN = "uncertain"
    LIKELY_AI = "likely_ai"


class AIResult(Base):
    """
    One row per evaluated paragraph from the AI-text-detection check (Phase 4c).
    Unlike InternalMatch/InternetMatch there's no "matched" counterpart — this
    is a classifier score against the paragraph itself, not a similarity match.
    Very short paragraphs are skipped entirely at check time (not enough text
    for the classifier to say anything meaningful) rather than stored with a
    forced label — see app/services/ai_detection.py.
    """

    __tablename__ = "ai_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id = Column(UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)

    paragraph_index = Column(Integer, nullable=False)
    paragraph_text = Column(Text, nullable=False)

    # Probability (0-1) the classifier assigns to "machine-generated". Stored
    # even for uncertain/human-labeled paragraphs so the frontend (Phase 6)
    # can render a confidence gradient rather than just three fixed buckets.
    ai_probability = Column(Float, nullable=False)
    label = Column(Enum(AILabel), nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    report = relationship("Report", back_populates="ai_results")

    def __repr__(self):
        return f"<AIResult report={self.report_id} label={self.label} p={self.ai_probability:.2f}>"
