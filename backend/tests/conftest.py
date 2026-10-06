"""
Test fixtures.

WHY A REAL POSTGRES, NOT SQLITE
--------------------------------
The models use Postgres-specific column types (UUID, JSONB — see
app/models/user.py, app/models/submission.py), so the schema cannot be
created against SQLite. Tests run against a real Postgres instance,
configured via TEST_DATABASE_URL (defaults to a `plagiarism_test` database
on the same server docker-compose.yml already brings up). This mirrors how
the rest of the project already assumes Postgres everywhere.

Before running tests, create the test database once:
    docker compose exec db psql -U plagiarism_user -c "CREATE DATABASE plagiarism_test;"
(or, without Docker: `createdb -U plagiarism_user plagiarism_test`)
See docs/README.md > Testing for the full walkthrough.

WHY NO REAL MODEL DOWNLOADS
----------------------------
embed_paragraphs() and the AI-detection classifier both normally download
and run a real ML model (sentence-transformers / transformers). Tests
replace both with small deterministic fakes (autouse fixture below) so the
suite runs in seconds, offline, and reproducibly — while still exercising
every line of the real plagiarism/report-generation/routing logic around
them. This is a standard "mock the boundary, test your own code" split, not
a shortcut around coverage: the *real* embedding/classifier code paths
still get their own narrow unit tests using the real libraries wherever
that's cheap (see test_vector_index.py, which uses real FAISS).
"""
import hashlib
import os
import tempfile

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import re
_raw_db_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or "postgresql+psycopg2://plagiarism_user:plagiarism_pass@localhost:5432/plagiarism_test"
TEST_DATABASE_URL = re.sub(r'/[^/?]+(\?.*)?$', r'/plagiarism_test\1', _raw_db_url)
assert "plagiarism_test" in TEST_DATABASE_URL, f"Safety check: tests must target plagiarism_test, got {TEST_DATABASE_URL}"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("ENV", "test")
# Uploaded test files and the (mocked-save, but still path-checked) FAISS
# index files go under a throwaway temp directory rather than the real
# uploads/ and faiss_data/ folders used by `uvicorn app.main:app --reload`.
_TEST_TMP_DIR = tempfile.mkdtemp(prefix="plagiarism_checker_tests_")
os.environ.setdefault("UPLOAD_DIR", os.path.join(_TEST_TMP_DIR, "uploads"))
os.environ.setdefault("FAISS_INDEX_PATH", os.path.join(_TEST_TMP_DIR, "paragraph_index.faiss"))
os.environ.setdefault("INTERNET_FAISS_INDEX_PATH", os.path.join(_TEST_TMP_DIR, "internet_source_index.faiss"))

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import embedding_pipeline, embeddings, source_ingestion  # noqa: E402
from app.services import vector_index, vector_index_sources  # noqa: E402

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
EMBEDDING_DIM = embeddings.EMBEDDING_DIM

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _fake_embed_paragraphs(paragraphs: list[str]) -> np.ndarray:
    """
    Deterministic, model-free stand-in for embeddings.embed_paragraphs.
    Same input text -> same vector (so duplicate/near-duplicate paragraphs
    still score as a near-perfect match, which is exactly what the real
    plagiarism-detection logic needs to be meaningfully testable).
    Different text -> effectively random, near-orthogonal vectors, so
    unrelated paragraphs reliably score far below any similarity threshold.
    """
    if not paragraphs:
        return np.empty((0, EMBEDDING_DIM), dtype="float32")
    vectors = []
    for text in paragraphs:
        seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "little")
        rng = np.random.default_rng(seed)
        vec = rng.normal(size=EMBEDDING_DIM).astype("float32")
        vec /= np.linalg.norm(vec)
        vectors.append(vec)
    return np.stack(vectors)


class _FakeClassifier:
    """
    Stand-in for the AI-detection transformers pipeline. Flags a paragraph
    as AI-written iff it contains the literal marker text tests opt into
    ("::AI_MARKER::"), so ai_detection tests are deterministic without a
    real model. Mirrors the real pipeline's call signature: callable,
    returns [[{"label": ..., "score": ...}, ...]].
    """

    def __call__(self, text, truncation=True):
        is_ai = "::AI_MARKER::" in text
        return [
            [
                {"label": "Fake", "score": 0.97 if is_ai else 0.03},
                {"label": "Real", "score": 0.03 if is_ai else 0.97},
            ]
        ]


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _mock_ml(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_paragraphs", _fake_embed_paragraphs)
    monkeypatch.setattr(embedding_pipeline, "embed_paragraphs", _fake_embed_paragraphs)
    monkeypatch.setattr(source_ingestion, "embed_paragraphs", _fake_embed_paragraphs)

    import app.services.ai_detection as ai_detection

    monkeypatch.setattr(ai_detection, "_get_classifier", lambda: _FakeClassifier())

    # Each test gets a fresh in-memory FAISS index (both the submission index
    # and the internet-source index) so matches from one test never leak
    # into another — mirrors the DB rollback fixture below.
    vector_index.reset_index_for_testing()
    vector_index_sources.reset_index_for_testing()
    monkeypatch.setattr(vector_index, "save_index", lambda: None)
    monkeypatch.setattr(vector_index_sources, "save_index", lambda: None)
    yield


@pytest.fixture()
def db_session():
    """
    Wraps each test in an outer transaction + a savepoint that's restarted
    after every `db.commit()` the application code performs, then rolls the
    whole thing back at the end. This is the standard SQLAlchemy recipe for
    giving each test a clean slate without recreating the schema every time,
    even though the app under test calls `session.commit()` freely (it has
    no idea it's running inside a test).
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session):
    def _get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Small helpers reused across test modules
# ---------------------------------------------------------------------------

def register_and_login(client: TestClient, role: str, email: str, **extra) -> dict:
    """Registers a user and returns the auth header dict + the raw user JSON."""
    payload = {
        "full_name": extra.pop("full_name", "Test User"),
        "email": email,
        "password": "TestPassword123",
        "role": role,
        **extra,
    }
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    login_resp = client.post("/api/auth/login", json={"email": email, "password": "TestPassword123"})
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "user": login_resp.json()["user"]}


def make_docx_bytes(paragraphs: list[str]) -> bytes:
    """Builds a real, minimal .docx file in memory so upload tests exercise
    the actual python-docx extraction path rather than a mocked one."""
    import io

    from docx import Document

    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
