"""
FAISS vector index for the internet-source knowledge base (Phase 4b).

Deliberately a separate index/file from app/services/vector_index.py (which
indexes submission paragraphs), rather than sharing one index with a "type"
filter, because:
- The two corpora grow independently (sources are seeded/ingested rarely;
  submissions arrive constantly) and never need to be searched together —
  internal and internet checks are always separate queries.
- Keeping them physically separate means a bug or corruption in one index
  can never affect the other, and each can be rebuilt independently.

Same index type and reasoning as vector_index.py — see that file's docstring
for why IndexIDMap2(IndexFlatIP) was chosen. Kept as a near-duplicate module
rather than a shared parameterized class so Phase 3's already-tested
submission-index code path is never touched by Phase 4b changes (see project
rule: never break previously built modules).
"""
import os
import threading
from pathlib import Path

import faiss
import numpy as np

from app.config import settings
from app.services.embeddings import EMBEDDING_DIM

INTERNET_FAISS_INDEX_PATH = Path(settings.INTERNET_FAISS_INDEX_PATH)

_index = None
_lock = threading.Lock()


def _new_empty_index() -> faiss.Index:
    flat = faiss.IndexFlatIP(EMBEDDING_DIM)
    return faiss.IndexIDMap2(flat)


def get_index() -> faiss.Index:
    global _index
    if _index is None:
        with _lock:
            if _index is None:
                # See app/services/vector_index.py's get_index() for why the
                # size check and the atomic-rename in save_index() below both
                # matter — same reasoning, duplicated here since this is a
                # deliberately separate module (see file docstring).
                if INTERNET_FAISS_INDEX_PATH.exists() and INTERNET_FAISS_INDEX_PATH.stat().st_size > 0:
                    _index = faiss.read_index(str(INTERNET_FAISS_INDEX_PATH))
                else:
                    _index = _new_empty_index()
    return _index


def save_index() -> None:
    INTERNET_FAISS_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = INTERNET_FAISS_INDEX_PATH.with_suffix(INTERNET_FAISS_INDEX_PATH.suffix + ".tmp")
    with _lock:
        faiss.write_index(get_index(), str(tmp_path))
        os.replace(tmp_path, INTERNET_FAISS_INDEX_PATH)


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
    index = get_index()
    if index.ntotal == 0:
        return []

    query = query_vector.astype("float32").reshape(1, -1)
    top_k = min(top_k, index.ntotal)
    scores, ids = index.search(query, top_k)

    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx == -1:
            continue
        results.append((int(idx), float(score)))
    return results


def reset_index_for_testing() -> None:
    global _index
    with _lock:
        _index = _new_empty_index()
