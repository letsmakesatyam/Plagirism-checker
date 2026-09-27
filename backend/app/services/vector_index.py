"""
FAISS vector index for paragraph-level semantic search.

What FAISS is doing here: it stores every paragraph's embedding vector and lets us
ask "which stored vectors are closest to this query vector?" in roughly constant
time even across a large corpus — far faster than comparing a new paragraph
against every other paragraph in the database one by one.

Index type: IndexIDMap2(IndexFlatIP(EMBEDDING_DIM))
- IndexFlatIP: exact (brute-force) inner-product search. Chosen over an
  approximate index (e.g. IVF/HNSW) because a college-scale corpus (thousands,
  not billions, of paragraphs) is small enough that exact search is still fast,
  and exact search means no risk of missing a real plagiarism match due to
  approximation — accuracy matters more than raw speed here.
- IndexIDMap2: lets us assign our own integer IDs (the paragraph_embeddings DB
  primary key) to each vector instead of relying on FAISS's implicit sequential
  IDs, and supports removing vectors by ID (needed if a submission is deleted).
- Because embeddings are L2-normalized (see embeddings.py), inner product here
  is equivalent to cosine similarity, which is the standard metric for
  comparing meaning rather than exact wording.

Persistence: the index is saved to / loaded from a single file on disk
(settings.FAISS_INDEX_PATH). It is loaded once per process and kept in memory;
`save()` must be called after any add/remove for changes to survive a restart.
"""
import threading
from pathlib import Path
import os

import faiss
import numpy as np

from app.config import settings
from app.services.embeddings import EMBEDDING_DIM

FAISS_INDEX_PATH = Path(settings.FAISS_INDEX_PATH)

_index = None
_lock = threading.Lock()  # FAISS indexes aren't thread-safe for concurrent writes


def _new_empty_index() -> faiss.Index:
    flat = faiss.IndexFlatIP(EMBEDDING_DIM)
    return faiss.IndexIDMap2(flat)


def get_index() -> faiss.Index:
    global _index
    if _index is None:
        with _lock:
            if _index is None:  # re-check inside the lock
                # A zero-byte file can be left behind by an interrupted write
                # from before the atomic-rename fix in save_index() below (or
                # any other process that got killed while creating the file).
                # Treat it the same as "no file yet" rather than handing it to
                # faiss.read_index(), which can hang trying to parse a
                # malformed/empty file instead of raising a clean error.
                if FAISS_INDEX_PATH.exists() and FAISS_INDEX_PATH.stat().st_size > 0:
                    _index = faiss.read_index(str(FAISS_INDEX_PATH))
                else:
                    _index = _new_empty_index()
    return _index


def save_index() -> None:
    # Write to a temp file first, then atomically rename it into place, rather
    # than writing straight to FAISS_INDEX_PATH. faiss.write_index() takes
    # real time on a non-trivial index, and if the process is killed or the
    # container is torn down mid-write (very possible during development —
    # restarts, redeploys, `docker compose down` while a request is still
    # in flight), a direct write leaves a truncated/corrupt file sitting at
    # the real path. faiss.read_index() on a corrupt file doesn't raise a
    # catchable error in all cases — it can hang indefinitely trying to parse
    # a malformed header, which silently wedges every future embedding
    # request with no exception and nothing to log (exactly the bug this
    # comment is here to prevent a repeat of). os.replace() is atomic on both
    # POSIX and Windows, so the real path only ever contains either the
    # previous complete index or a new complete index — never a partial one.
    FAISS_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = FAISS_INDEX_PATH.with_suffix(FAISS_INDEX_PATH.suffix + ".tmp")
    with _lock:
        faiss.write_index(get_index(), str(tmp_path))
        os.replace(tmp_path, FAISS_INDEX_PATH)


def add_vectors(ids: list[int], vectors: np.ndarray) -> None:
    if len(ids) == 0:
        return
    if vectors.shape[0] != len(ids):
        raise ValueError("ids and vectors must have the same length")

    id_array = np.array(ids, dtype="int64")
    with _lock:
        get_index().add_with_ids(vectors.astype("float32"), id_array)


def remove_vectors(ids: list[int]) -> None:
    if len(ids) == 0:
        return
    id_array = np.array(ids, dtype="int64")
    with _lock:
        get_index().remove_ids(id_array)


def search(query_vector: np.ndarray, top_k: int = 5) -> list[tuple[int, float]]:
    """
    Returns up to top_k (id, similarity_score) pairs, ordered highest similarity
    first. similarity_score is a cosine similarity in [-1, 1] (in practice
    [0, 1] for natural-language text) since vectors are L2-normalized.
    """
    index = get_index()
    if index.ntotal == 0:
        return []

    query = query_vector.astype("float32").reshape(1, -1)
    top_k = min(top_k, index.ntotal)
    scores, ids = index.search(query, top_k)

    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx == -1:  # FAISS pads with -1 if fewer than top_k results exist
            continue
        results.append((int(idx), float(score)))
    return results


def reset_index_for_testing() -> None:
    """Only for automated tests — clears the in-memory index without touching disk."""
    global _index
    with _lock:
        _index = _new_empty_index()
