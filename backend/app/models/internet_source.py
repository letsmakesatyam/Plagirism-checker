"""
Internet plagiarism corpus (Phase 4b).

This system checks "internet plagiarism" against a locally indexed knowledge
base rather than live-crawling the web on every check, for three reasons:
1. Speed — a FAISS lookup against a pre-built index is milliseconds; crawling
   search engines per-paragraph per-submission would be slow and rate-limited.
2. Determinism — reports are reproducible and don't depend on a third-party
   API being up.
3. It's the same architecture real plagiarism checkers use in practice
   (Turnitin etc. maintain their own indexed corpus rather than searching the
   live web per check).

`InternetSource` is one indexed document (a Wikipedia article, a paper, a
book chapter, a blog post, ...). `InternetSourceCategory` covers the six
categories the spec asks for. `InternetSourceParagraph` is one paragraph of
that document — the actual unit that gets embedded and searched, exactly
mirroring how `ParagraphEmbedding` works for submissions (see
paragraph_embedding.py). Its `id` doubles as the internet FAISS index's
vector id, same pattern.

New sources are added via `app/services/source_ingestion.py`, either from
raw pasted/seeded text or (with real internet access) fetched from a URL.
See `scripts/seed_internet_sources.py` for the demo corpus this ships with.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class InternetSourceCategory(str, enum.Enum):
    WIKIPEDIA = "wikipedia"
    RESEARCH_PAPER = "research_paper"
    BOOK = "book"
    EDUCATIONAL_WEBSITE = "educational_website"
    BLOG = "blog"
    GOVERNMENT = "government"


class InternetSource(Base):
    __tablename__ = "internet_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(300), nullable=False)
    url = Column(String(1000), nullable=True)
    category = Column(Enum(InternetSourceCategory), nullable=False, index=True)

    full_text = Column(Text, nullable=False)
    paragraph_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    paragraphs = relationship("InternetSourceParagraph", back_populates="source", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<InternetSource {self.title!r} ({self.category.value})>"


class InternetSourceParagraph(Base):
    __tablename__ = "internet_source_paragraphs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)  # == internet FAISS vector id
    source_id = Column(UUID(as_uuid=True), ForeignKey("internet_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    paragraph_index = Column(Integer, nullable=False)
    paragraph_text = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    source = relationship("InternetSource", back_populates="paragraphs")

    def __repr__(self):
        return f"<InternetSourceParagraph id={self.id} source={self.source_id} idx={self.paragraph_index}>"
