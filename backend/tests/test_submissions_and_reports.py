import io

from tests.conftest import make_docx_bytes, register_and_login

DUPLICATE_PARAGRAPHS = [
    "The French Revolution began in 1789 and reshaped the political landscape of Europe for a generation.",
    "Industrialization changed how people worked and where they lived across the nineteenth century.",
    "Photosynthesis converts light energy into chemical energy stored in glucose molecules within plant cells.",
]

AI_MARKER_PARAGRAPHS = [
    "::AI_MARKER:: As an AI language model, I have generated this text to illustrate a plausible essay "
    "structure covering the assigned topic in a way that reads as coherent, structured, generic prose. "
    "Machine learning algorithms analyze vast corpora of natural language text to predict subsequent tokens "
    "and synthesize cohesive explanations across various domain areas. Consequently, generative systems "
    "produce structured paragraphs with characteristic sentence lengths and formal transitional phrases "
    "that mimic human scholarly discourse while synthesizing information across distributed training datasets. "
    "This extended prose section ensures that the paragraph fulfills the minimum one hundred word eligibility "
    "threshold required for reliable statistical authorship signal evaluation in academic integrity workflows.",
]


def _create_assignment(client, faculty_headers, title="Test Assignment"):
    resp = client.post("/api/assignments", json={"title": title}, headers=faculty_headers)
    assert resp.status_code == 201
    return resp.json()


def _upload(client, student_headers, assignment_id, paragraphs, filename="essay.docx"):
    file_bytes = make_docx_bytes(paragraphs)
    resp = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        headers=student_headers,
        files={"file": (filename, io.BytesIO(file_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_upload_extracts_and_embeds_successfully(client):
    faculty = register_and_login(client, "faculty", "up_fac@example.com")
    student = register_and_login(client, "student", "up_stu@example.com")
    assignment = _create_assignment(client, faculty["headers"])

    submission = _upload(client, student["headers"], assignment["id"], DUPLICATE_PARAGRAPHS)
    assert submission["status"] == "embedded"
    assert submission["word_count"] > 0
    assert submission["extraction_error"] is None
    assert submission["embedding_error"] is None


def test_upload_rejects_wrong_extension(client):
    faculty = register_and_login(client, "faculty", "ext_fac@example.com")
    student = register_and_login(client, "student", "ext_stu@example.com")
    assignment = _create_assignment(client, faculty["headers"])

    resp = client.post(
        f"/api/assignments/{assignment['id']}/submissions",
        headers=student["headers"],
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 400


def test_faculty_cannot_upload_submission(client):
    faculty = register_and_login(client, "faculty", "noupload_fac@example.com")
    assignment = _create_assignment(client, faculty["headers"])
    resp = client.post(
        f"/api/assignments/{assignment['id']}/submissions",
        headers=faculty["headers"],
        files={"file": ("essay.docx", io.BytesIO(make_docx_bytes(["hi"])), "application/octet-stream")},
    )
    assert resp.status_code == 403


def test_internal_plagiarism_flags_duplicate_submission(client):
    """Two different students submit near-identical text to the same
    assignment; the second submission's report should flag it against the
    first (this exercises the real internal_plagiarism.py logic end to end,
    only the embedding vectors themselves are faked)."""
    faculty = register_and_login(client, "faculty", "dup_fac@example.com")
    student_a = register_and_login(client, "student", "dup_stu_a@example.com")
    student_b = register_and_login(client, "student", "dup_stu_b@example.com")
    assignment = _create_assignment(client, faculty["headers"])

    _upload(client, student_a["headers"], assignment["id"], DUPLICATE_PARAGRAPHS, "original.docx")
    submission_b = _upload(client, student_b["headers"], assignment["id"], DUPLICATE_PARAGRAPHS, "copy.docx")

    resp = client.post(
        f"/api/submissions/{submission_b['id']}/generate-report", headers=student_b["headers"]
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert report["internal_score"] == 100.0
    assert report["paragraphs_flagged_internal"] == len(DUPLICATE_PARAGRAPHS)
    assert len(report["copied_from"]) == 1
    assert report["copied_from"][0]["matched_original_filename"] == "original.docx"


def test_unrelated_submission_is_not_flagged(client):
    faculty = register_and_login(client, "faculty", "clean_fac@example.com")
    student = register_and_login(client, "student", "clean_stu@example.com")
    assignment = _create_assignment(client, faculty["headers"])

    submission = _upload(
        client, student["headers"], assignment["id"],
        ["A wholly original paragraph about the migration patterns of Arctic terns across two hemispheres."],
        "unique.docx",
    )
    resp = client.post(f"/api/submissions/{submission['id']}/generate-report", headers=student["headers"])
    assert resp.status_code == 200
    report = resp.json()
    assert report["internal_score"] == 0.0
    assert report["paragraphs_flagged_internal"] == 0


def test_ai_detection_flags_marked_paragraph(client):
    faculty = register_and_login(client, "faculty", "ai_fac@example.com")
    student = register_and_login(client, "student", "ai_stu@example.com")
    assignment = _create_assignment(client, faculty["headers"])

    submission = _upload(client, student["headers"], assignment["id"], AI_MARKER_PARAGRAPHS, "ai.docx")
    resp = client.post(f"/api/submissions/{submission['id']}/generate-report", headers=student["headers"])
    assert resp.status_code == 200
    report = resp.json()
    assert report["likely_ai_count"] == 1
    assert report["ai_score"] == 100.0


def test_upload_rejects_empty_file(client):
    faculty = register_and_login(client, "faculty", "empty_fac@example.com")
    student = register_and_login(client, "student", "empty_stu@example.com")
    assignment = _create_assignment(client, faculty["headers"])

    resp = client.post(
        f"/api/assignments/{assignment['id']}/submissions",
        headers=student["headers"],
        files={"file": ("empty.docx", io.BytesIO(b""), "application/octet-stream")},
    )
    assert resp.status_code == 400  # file_storage rejects the empty file outright


def test_report_requires_embedded_status(client):
    """A .docx extension containing bytes that aren't a real docx fails
    extraction gracefully (status=failed, extraction_error set), and
    generate-report on a non-embedded submission must be rejected (409),
    not silently produce a meaningless report."""
    faculty = register_and_login(client, "faculty", "notready_fac@example.com")
    student = register_and_login(client, "student", "notready_stu@example.com")
    assignment = _create_assignment(client, faculty["headers"])

    resp = client.post(
        f"/api/assignments/{assignment['id']}/submissions",
        headers=student["headers"],
        files={"file": ("corrupt.docx", io.BytesIO(b"this is not a real docx file"), "application/octet-stream")},
    )
    assert resp.status_code == 201
    submission = resp.json()
    assert submission["status"] == "failed"
    assert submission["extraction_error"] is not None

    report_resp = client.post(f"/api/submissions/{submission['id']}/generate-report", headers=student["headers"])
    assert report_resp.status_code == 409


def test_pdf_report_download(client):
    faculty = register_and_login(client, "faculty", "pdf_fac@example.com")
    student = register_and_login(client, "student", "pdf_stu@example.com")
    assignment = _create_assignment(client, faculty["headers"])
    submission = _upload(client, student["headers"], assignment["id"], DUPLICATE_PARAGRAPHS, "pdftest.docx")
    client.post(f"/api/submissions/{submission['id']}/generate-report", headers=student["headers"])

    resp = client.get(f"/api/submissions/{submission['id']}/report/pdf", headers=student["headers"])
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_other_student_cannot_view_submission(client):
    faculty = register_and_login(client, "faculty", "priv_fac@example.com")
    owner = register_and_login(client, "student", "priv_owner@example.com")
    intruder = register_and_login(client, "student", "priv_intruder@example.com")
    assignment = _create_assignment(client, faculty["headers"])
    submission = _upload(client, owner["headers"], assignment["id"], DUPLICATE_PARAGRAPHS)

    resp = client.get(f"/api/submissions/{submission['id']}", headers=intruder["headers"])
    assert resp.status_code == 403


def test_faculty_reports_search_and_filter(client):
    faculty = register_and_login(client, "faculty", "search_fac@example.com")
    student = register_and_login(client, "student", "search_stu@example.com")
    assignment = _create_assignment(client, faculty["headers"])
    submission = _upload(client, student["headers"], assignment["id"], DUPLICATE_PARAGRAPHS, "searchable.docx")
    client.post(f"/api/submissions/{submission['id']}/generate-report", headers=student["headers"])

    resp = client.get("/api/reports", params={"search": "searchable"}, headers=faculty["headers"])
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp_min = client.get("/api/reports", params={"min_originality": 101}, headers=faculty["headers"])
    assert resp_min.json() == []
