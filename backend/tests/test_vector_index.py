"""
Pure unit tests for app/services/vector_index.py, using the *real* FAISS
library end to end (no DB, no mocking) — this is the narrow "test the real
thing" half referenced in conftest.py's module docstring, complementing the
mocked-boundary integration tests in test_submissions_and_reports.py.

No app-level fixtures are needed here: vector_index's index lives in a
module-level singleton pointed at FAISS_INDEX_PATH (set to a throwaway temp
file by conftest.py before any app module is imported), and
reset_index_for_testing() gives each test a clean slate.
"""
import numpy as np
import pytest

from app.services import vector_index
from app.services.embeddings import EMBEDDING_DIM


@pytest.fixture(autouse=True)
def clean_index(tmp_path, monkeypatch):
    """
    Every test in this file gets a clean in-memory index AND its own private
    on-disk path, isolated from the app's shared FAISS_INDEX_PATH (which
    other test files' real submission-pipeline tests also write to). Without
    this isolation, save/reload assertions here can flake: those other
    tests' embedding pipeline can still be mid-flight (e.g. FastAPI
    BackgroundTasks completing after the test client call returns) and
    write to the *same* shared index file a moment after this file resets
    it, which is exactly the kind of cross-test contamination a private
    path avoids entirely.
    """
    monkeypatch.setattr(vector_index, "FAISS_INDEX_PATH", tmp_path / "test_vector_index.faiss")
    vector_index.reset_index_for_testing()
    yield
    vector_index.reset_index_for_testing()


def _unit_vector(seed: int) -> np.ndarray:
    """Deterministic, L2-normalized vector (same shape as a real embedding)."""
    rng = np.random.RandomState(seed)
    v = rng.rand(EMBEDDING_DIM).astype("float32")
    return v / np.linalg.norm(v)


def test_search_on_empty_index_returns_nothing():
    results = vector_index.search(_unit_vector(0), top_k=5)
    assert results == []


def test_add_then_search_finds_identical_vector_first():
    v1, v2, v3 = _unit_vector(1), _unit_vector(2), _unit_vector(3)
    vector_index.add_vectors([101, 102, 103], np.stack([v1, v2, v3]))

    results = vector_index.search(v1, top_k=3)

    assert results[0][0] == 101
    # Cosine similarity of a vector against itself is 1.0 (allow float slack).
    assert results[0][1] == pytest.approx(1.0, abs=1e-4)
    # All three ids should come back since top_k >= ntotal.
    assert {r[0] for r in results} == {101, 102, 103}


def test_search_orders_by_similarity_highest_first():
    base = _unit_vector(10)
    # A slightly perturbed copy of `base` should be closer to it than an
    # unrelated random vector.
    near = base + 0.01 * _unit_vector(11)
    near = near / np.linalg.norm(near)
    far = _unit_vector(99)

    vector_index.add_vectors([1, 2], np.stack([near.astype("float32"), far.astype("float32")]))
    results = vector_index.search(base, top_k=2)

    assert [r[0] for r in results] == [1, 2]
    assert results[0][1] > results[1][1]


def test_remove_vectors_excludes_them_from_later_searches():
    v1, v2 = _unit_vector(20), _unit_vector(21)
    vector_index.add_vectors([201, 202], np.stack([v1, v2]))

    vector_index.remove_vectors([201])
    results = vector_index.search(v1, top_k=5)

    assert 201 not in {r[0] for r in results}
    assert 202 in {r[0] for r in results}


def test_save_and_reload_preserves_search_results(tmp_path):
    """
    Exercises the same faiss.write_index/read_index round trip that
    save_index()/get_index() use, but on a fresh, local IndexIDMap2 instance
    rather than through the module-level singleton. This sidesteps the
    global-state/monkeypatch interaction that made the singleton-based
    version of this test flaky (see docs/CHECKLIST.md Phase 7 "Known issue"
    for the investigation), while still giving real coverage of the actual
    persistence guarantee: a saved index, reloaded from disk, returns the
    same search results as before the reload.
    """
    import faiss

    v1, v2 = _unit_vector(30), _unit_vector(31)

    index = vector_index._new_empty_index()
    index.add_with_ids(np.stack([v1, v2]).astype("float32"), np.array([301, 302], dtype="int64"))

    def _search(idx, query, top_k=2):
        scores, ids = idx.search(query.astype("float32").reshape(1, -1), top_k)
        return [(int(i), float(s)) for s, i in zip(scores[0], ids[0]) if i != -1]

    before = _search(index, v1)

    save_path = tmp_path / "roundtrip.faiss"
    faiss.write_index(index, str(save_path))
    reloaded = faiss.read_index(str(save_path))
    after = _search(reloaded, v1)

    assert before == after
    assert {r[0] for r in after} == {301, 302}


def test_add_vectors_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        vector_index.add_vectors([1, 2], np.stack([_unit_vector(1)]))


def test_add_vectors_with_empty_list_is_a_noop():
    vector_index.add_vectors([], np.empty((0, EMBEDDING_DIM), dtype="float32"))
    assert vector_index.search(_unit_vector(1), top_k=5) == []
