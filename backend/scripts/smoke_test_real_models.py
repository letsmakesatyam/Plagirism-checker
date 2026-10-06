"""
End-to-end real CPU model smoke test.
Exercises:
1. Real SentenceTransformer ('all-MiniLM-L6-v2') embeddings on CPU.
2. Real RoBERTa AI-detection classifier on CPU.
3. Cold-start internet source ingestion (starting from _index = None).
4. Cold-start PDF document upload & extraction (starting from _index = None).
5. Real similarity search & report generation against internet sources.
6. Idempotent retry processing with verification of zero duplicates.
7. Post-restart FAISS index persistence and reload verification.
"""
import os
import sys
import tempfile
import uuid
from pathlib import Path

# Set up test environment with isolated paths and database
tmp_dir = tempfile.mkdtemp(prefix="smoke_test_")
os.environ["UPLOAD_DIR"] = os.path.join(tmp_dir, "uploads")
os.environ["FAISS_INDEX_PATH"] = os.path.join(tmp_dir, "smoke_sub.faiss")
os.environ["INTERNET_FAISS_INDEX_PATH"] = os.path.join(tmp_dir, "smoke_sources.faiss")
os.environ["DATABASE_URL"] = "postgresql+psycopg2://plagiarism_user:plagiarism_pass@db:5432/plagiarism_test"
os.environ["ENV"] = "test"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

sys.path.insert(0, "/app")

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.assignment import Assignment
from app.models.internet_source import InternetSource, InternetSourceCategory, InternetSourceParagraph
from app.models.paragraph_embedding import ParagraphEmbedding
from app.models.report import Report
from app.models.submission import Submission, SubmissionStatus
from app.models.user import User, UserRole
from app.services import ai_detection, embeddings, vector_index, vector_index_sources
from app.services.embedding_pipeline import generate_embeddings_for_submission
from app.services.extraction import extract_text
from app.services.report_generation import generate_full_report
from app.services.source_ingestion import ingest_source_from_text


def create_test_pdf(filepath: str, paragraphs: list[str]):
    c = canvas.Canvas(filepath, pagesize=letter)
    y = 750
    for p in paragraphs:
        # Simple text wrapping simulation
        words = p.split()
        line = []
        for word in words:
            line.append(word)
            if len(" ".join(line)) > 70:
                c.drawString(72, y, " ".join(line[:-1]))
                y -= 18
                line = [word]
        if line:
            c.drawString(72, y, " ".join(line))
            y -= 30
    c.save()


def main():
    print("=" * 60)
    print("STARTING REAL-MODEL CPU SMOKE TEST")
    print("=" * 60)

    engine = create_engine(os.environ["DATABASE_URL"])
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # 1. Verify Real Model Load & Dimension
    print("\n[Step 1] Loading real SentenceTransformer model on CPU...")
    test_text = ["Academic integrity requires that all scholarly work acknowledges previous sources appropriately."]
    vecs = embeddings.embed_paragraphs(test_text)
    assert vecs.shape == (1, 384), f"Unexpected embedding shape: {vecs.shape}"
    print(f"✓ Real SentenceTransformer loaded successfully: output shape {vecs.shape}")

    print("\n[Step 2] Loading real RoBERTa AI-detection classifier on CPU...")
    clf = ai_detection._get_classifier()
    res = clf(test_text)
    fake_prob = ai_detection._ai_probability(res[0])
    print(f"✓ Real RoBERTa detector loaded successfully: P(AI) = {fake_prob:.4f}")

    # 2. Cold-start Source Ingestion
    print("\n[Step 3] Cold-start source ingestion with _index = None...")
    vector_index_sources.clear_index_for_testing()
    assert vector_index_sources._index is None

    source_text = (
        "Distributed consensus algorithms ensure that multiple nodes in a network agree on a single data value. "
        "The Raft consensus algorithm achieves this through leader election, log replication, and safety guarantees.\n\n"
        "By decomposing consensus into distinct sub-problems, Raft enhances understandability without sacrificing formal guarantees."
    )
    source = ingest_source_from_text(
        title="Raft Consensus Overview",
        category=InternetSourceCategory.RESEARCH_PAPER,
        text=source_text,
        db=db,
    )
    assert source.id is not None
    assert vector_index_sources._index is not None
    source_vectors_count = len(vector_index_sources.get_indexed_ids())
    assert source_vectors_count == 2
    print(f"✓ Source ingested successfully on cold start: source_id={source.id}, indexed_paragraphs={source_vectors_count}")

    # 3. Create Users & Assignment
    uid = uuid.uuid4().hex[:8]
    fac = User(email=f"smoke_fac_{uid}@example.com", full_name="Smoke Faculty", hashed_password="pw", role=UserRole.FACULTY)
    stu = User(email=f"smoke_stu_{uid}@example.com", full_name="Smoke Student", hashed_password="pw", role=UserRole.STUDENT)
    db.add_all([fac, stu])
    db.commit()

    assign = Assignment(title="Distributed Systems Paper", faculty_id=fac.id)
    db.add(assign)
    db.commit()

    # 4. Cold-start PDF Upload & Extraction
    print("\n[Step 4] Cold-start PDF document upload & extraction with _index = None...")
    vector_index.clear_index_for_testing()
    assert vector_index._index is None

    pdf_paragraphs = [
        "Distributed consensus algorithms ensure that multiple nodes in a network agree on a single data value. "
        "The Raft consensus algorithm achieves this through leader election, log replication, and safety guarantees.",
        "In contrast, Paxos is widely considered significantly harder to understand and implement in production environments.",
    ]
    pdf_path = os.path.join(tmp_dir, "student_submission.pdf")
    create_test_pdf(pdf_path, pdf_paragraphs)

    extracted = extract_text(pdf_path, "pdf")
    assert not extracted.error
    assert len(extracted.paragraphs) >= 2
    print(f"✓ PDF extracted: {extracted.page_count} page(s), {extracted.word_count} words, {len(extracted.paragraphs)} paragraphs")

    stored_name = f"smoke_submission_{uuid.uuid4().hex}.pdf"
    submission = Submission(
        assignment_id=assign.id,
        student_id=stu.id,
        original_filename="student_submission.pdf",
        stored_filename=stored_name,
        file_path=pdf_path,
        file_type="pdf",
        file_size_bytes=os.path.getsize(pdf_path),
        status=SubmissionStatus.EXTRACTED,
        extracted_text=extracted.text,
        paragraphs=extracted.paragraphs,
        page_count=extracted.page_count,
        word_count=extracted.word_count,
    )
    db.add(submission)
    db.commit()

    # Real embedding pipeline execution
    generate_embeddings_for_submission(submission, db)
    submission.status = SubmissionStatus.EMBEDDED
    db.commit()
    assert vector_index._index is not None
    sub_vectors_count = len(vector_index.get_indexed_ids())
    print(f"✓ Submission embedded with real SentenceTransformer: {sub_vectors_count} vectors indexed in FAISS")

    # 5. Real Report Generation & Similarity Matching
    print("\n[Step 5] Real report generation & semantic matching...")
    report = generate_full_report(submission, db)
    assert report is not None
    print(f"✓ Report generated: overall_originality_score = {report.overall_originality_score}%")
    print(f"  Internet score: {report.internet_score}%")
    print(f"  Internet matches found: {len(report.internet_matches)}")
    print(f"  AI score: {report.ai_score}%")
    assert len(report.internet_matches) > 0, "Expected at least 1 match against the ingested Raft source!"
    best_match = report.internet_matches[0]
    print(f"  Top match: similarity = {best_match.similarity:.4f}, source = '{best_match.matched_source.title}'")
    assert best_match.similarity > 0.85, f"Expected high similarity match, got {best_match.similarity}"

    # 6. Retry Processing & Idempotency Check
    print("\n[Step 6] Testing retry processing idempotency...")
    # Simulate a retry on the submission
    generate_embeddings_for_submission(submission, db)
    p_rows = db.query(ParagraphEmbedding).filter(ParagraphEmbedding.submission_id == submission.id).all()
    assert len(p_rows) == len(submission.paragraphs)
    assert len(vector_index.get_indexed_ids()) == len(submission.paragraphs)
    print(f"✓ Retry verified: exactly {len(p_rows)} paragraph rows and FAISS vectors exist (zero duplicates)")

    # 7. Persistence & Reload Verification after Simulated Restart
    print("\n[Step 7] Testing FAISS index persistence across restart...")
    # Simulate server restart where in-memory index is None
    vector_index.clear_index_for_testing()
    vector_index_sources.clear_index_for_testing()
    assert vector_index._index is None
    assert vector_index_sources._index is None

    # Search should trigger automatic lazy load from disk
    query_vec = embeddings.embed_paragraphs([pdf_paragraphs[0]])
    results = vector_index.search(query_vec, top_k=3)
    assert len(results) > 0
    assert results[0][0] in [r.id for r in p_rows]
    print(f"✓ Submission index successfully reloaded from disk after restart: top match score = {results[0][1]:.4f}")

    source_results = vector_index_sources.search(query_vec, top_k=3)
    assert len(source_results) > 0
    print(f"✓ Source index successfully reloaded from disk after restart: top match score = {source_results[0][1]:.4f}")

    # Cleanup
    db.query(Report).filter(Report.submission_id == submission.id).delete()
    db.query(ParagraphEmbedding).filter(ParagraphEmbedding.submission_id == submission.id).delete()
    db.query(Submission).filter(Submission.id == submission.id).delete()
    db.query(Assignment).filter(Assignment.id == assign.id).delete()
    db.query(User).filter(User.id.in_([stu.id, fac.id])).delete()
    db.query(InternetSourceParagraph).filter(InternetSourceParagraph.source_id == source.id).delete()
    db.query(InternetSource).filter(InternetSource.id == source.id).delete()
    db.commit()
    db.close()

    print("\n" + "=" * 60)
    print("ALL REAL-MODEL CPU SMOKE TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    main()
