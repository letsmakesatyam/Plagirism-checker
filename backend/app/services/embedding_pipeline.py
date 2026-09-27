"""
Runs after text extraction succeeds. For a submission's stored paragraphs:
1. Create a ParagraphEmbedding DB row per paragraph (to get a stable integer id).
2. Generate embeddings for all paragraphs in one batch call (batching is far
   faster than one-paragraph-at-a-time since the model amortizes overhead).
3. Add the vectors to the FAISS index, keyed by the DB row ids from step 1.
4. Persist the FAISS index to disk so it survives a restart.
"""
from sqlalchemy.orm import Session

from app.models.paragraph_embedding import ParagraphEmbedding
from app.models.submission import Submission
from app.services.embeddings import embed_paragraphs
from app.services.vector_index import add_vectors, save_index


def generate_embeddings_for_submission(submission: Submission, db: Session) -> None:
    paragraphs = submission.paragraphs or []
    if not paragraphs:
        return

    # Step 1: create DB rows first so we have stable ids to hand to FAISS.
    rows = []
    for idx, paragraph_text in enumerate(paragraphs):
        row = ParagraphEmbedding(
            submission_id=submission.id,
            paragraph_index=idx,
            paragraph_text=paragraph_text,
        )
        db.add(row)
        rows.append(row)
    db.flush()  # assigns primary keys without committing yet

    # Step 2: batch-embed all paragraphs together.
    vectors = embed_paragraphs(paragraphs)

    # Step 3 & 4: index and persist.
    ids = [row.id for row in rows]
    add_vectors(ids, vectors)
    save_index()

    db.commit()
