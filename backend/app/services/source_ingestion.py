"""
Adds one document to the internet-source knowledge base: creates the
InternetSource row, splits it into paragraphs, embeds them, and indexes them
in the internet FAISS index — the mirror of embedding_pipeline.py for
submissions.

Two entry points:
- `ingest_source_from_text`: used by the seed script and by faculty/admin
  tooling to add a source you already have the text for (pasted, uploaded,
  scraped elsewhere). Fully functional offline.
- `ingest_source_from_url`: fetches a page with `httpx` and strips HTML tags
  before ingesting. Requires outbound internet access — see README section 11
  for why this couldn't be exercised in the build sandbox, and test this one
  first on your machine.
"""
import re

from sqlalchemy.orm import Session

from app.models.internet_source import InternetSource, InternetSourceCategory, InternetSourceParagraph
from app.services.embeddings import embed_paragraphs
from app.services.extraction import clean_text, split_into_paragraphs
from app.services.vector_index_sources import add_vectors, save_index


def _strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&amp;|&quot;|&#39;|&lt;|&gt;", " ", text)
    return text


def ingest_source_from_text(
    title: str,
    category: InternetSourceCategory,
    text: str,
    db: Session,
    url: str | None = None,
) -> InternetSource:
    cleaned = clean_text(text)
    paragraphs = [p for p in split_into_paragraphs(cleaned) if len(p.split()) >= 8]
    if not paragraphs:
        raise ValueError("Source text produced no usable paragraphs (need at least 8 words each)")

    source = InternetSource(title=title, url=url, category=category, full_text=cleaned, paragraph_count=len(paragraphs))
    db.add(source)
    db.flush()

    rows = []
    for idx, paragraph_text in enumerate(paragraphs):
        row = InternetSourceParagraph(source_id=source.id, paragraph_index=idx, paragraph_text=paragraph_text)
        db.add(row)
        rows.append(row)
    db.flush()

    vectors = embed_paragraphs(paragraphs)
    ids = [row.id for row in rows]
    add_vectors(ids, vectors)
    save_index()

    db.commit()
    db.refresh(source)
    return source


def ingest_source_from_url(
    title: str,
    category: InternetSourceCategory,
    url: str,
    db: Session,
) -> InternetSource:
    import httpx

    response = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "PlagiarismChecker/1.0"})
    response.raise_for_status()
    text = _strip_html(response.text)
    return ingest_source_from_text(title=title, category=category, text=text, db=db, url=url)
