"""
Wraps the sentence-transformers model. The model is loaded lazily (on first use,
not at import time) and cached as a module-level singleton so it's only loaded
into memory once per process, regardless of how many requests use it.

Model: all-MiniLM-L6-v2
- What: a distilled transformer trained specifically to produce sentence/paragraph
  embeddings — 384-dimensional vectors where semantically similar text ends up
  close together in vector space (measured by cosine similarity).
- Why this model: it's small (~90MB), fast on CPU (no GPU needed, important for a
  college server), and is one of the most widely validated general-purpose
  sentence embedding models available.
- How embeddings are generated: each paragraph string is tokenized and passed
  through the transformer; the token outputs are mean-pooled into one fixed-size
  vector per paragraph.
- How they are stored: see app/services/vector_index.py — vectors go into a FAISS
  index, with paragraph text/metadata kept in the paragraph_embeddings DB table
  keyed by the same integer ID used as the FAISS vector ID.
- How they are searched: FAISS performs nearest-neighbor search using inner
  product on L2-normalized vectors, which is mathematically equivalent to
  cosine similarity — the standard metric for comparing meaning, not exact wording.
"""
import numpy as np

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # imported lazily: heavy (torch) dependency

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_paragraphs(paragraphs: list[str]) -> np.ndarray:
    """
    Returns an (n, 384) float32 array of L2-normalized embeddings, one row per
    paragraph, in the same order as the input list. Normalizing here means
    downstream FAISS inner-product search is equivalent to cosine similarity.
    """
    if not paragraphs:
        return np.empty((0, EMBEDDING_DIM), dtype="float32")

    model = get_model()
    embeddings = model.encode(paragraphs, normalize_embeddings=True, convert_to_numpy=True)
    return embeddings.astype("float32")
