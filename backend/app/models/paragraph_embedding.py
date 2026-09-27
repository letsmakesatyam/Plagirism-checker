"""
One row per paragraph per submission. `id` doubles as the FAISS vector ID
(FAISS's IndexIDMap accepts arbitrary int64 IDs, so we reuse the DB primary key
directly instead of maintaining a separate mapping table).
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class ParagraphEmbedding(Base):
    __tablename__ = "paragraph_embeddings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)  # == FAISS vector id
    submission_id = Column(UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True)
    paragraph_index = Column(Integer, nullable=False)  # position within submission.paragraphs
    paragraph_text = Column(Text, nullable=False)  # kept redundantly for fast match display later

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    submission = relationship("Submission")

    def __repr__(self):
        return f"<ParagraphEmbedding id={self.id} submission={self.submission_id} idx={self.paragraph_index}>"
