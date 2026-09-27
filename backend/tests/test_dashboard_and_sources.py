import io

from tests.conftest import make_docx_bytes, register_and_login

WIKI_PARAGRAPH = (
    "Mount Everest is Earth's highest mountain above sea level, located in the Mahalangur Himal "
    "sub-range of the Himalayas, straddling the border between Nepal and the Tibet Autonomous Region."
)


def _create_assignment(client, faculty_headers, title="Geography Assignment"):
    resp = client.post("/api/assignments", json={"title": title}, headers=faculty_headers)
    assert resp.status_code == 201
    return resp.json()


def _upload(client, student_headers, assignment_id, paragraphs, filename="essay.docx"):
    file_bytes = make_docx_bytes(paragraphs)
    resp = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        headers=student_headers,
        files={"file": (filename, io.BytesIO(file_bytes), "application/octet-stream")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_faculty_can_add_source_from_text(client):
    faculty = register_and_login(client, "faculty", "src_fac@example.com")
    resp = client.post(
        "/api/internet-sources",
        json={"title": "Mount Everest — Wikipedia", "category": "wikipedia", "text": WIKI_PARAGRAPH * 3},
        headers=faculty["headers"],
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["paragraph_count"] >= 1


def test_student_cannot_manage_sources(client):
    student = register_and_login(client, "student", "src_stu@example.com")
    resp = client.post(
        "/api/internet-sources",
        json={"title": "X", "category": "wikipedia", "text": WIKI_PARAGRAPH * 3},
        headers=student["headers"],
    )
    assert resp.status_code == 403


def test_internet_plagiarism_flags_matching_source(client):
    faculty = register_and_login(client, "faculty", "isrc_fac@example.com")
    student = register_and_login(client, "student", "isrc_stu@example.com")

    # Passed as the exact same single paragraph the submission below will
    # contain — the fake embedding fixture (conftest.py) hashes text to a
    # vector, so identical text is required to produce a matching score.
    src_resp = client.post(
        "/api/internet-sources",
        json={"title": "Everest Facts", "category": "wikipedia", "text": WIKI_PARAGRAPH},
        headers=faculty["headers"],
    )
    assert src_resp.status_code == 201

    assignment = _create_assignment(client, faculty["headers"])
    submission = _upload(client, student["headers"], assignment["id"], [WIKI_PARAGRAPH], "everest.docx")

    report_resp = client.post(f"/api/submissions/{submission['id']}/generate-report", headers=student["headers"])
    assert report_resp.status_code == 200
    report = report_resp.json()
    assert report["internet_score"] == 100.0
    assert len(report["internet_sources"]) == 1
    assert report["internet_sources"][0]["title"] == "Everest Facts"


def test_faculty_dashboard_reflects_activity(client):
    faculty = register_and_login(client, "faculty", "dash_fac@example.com")
    student = register_and_login(client, "student", "dash_stu@example.com")
    assignment = _create_assignment(client, faculty["headers"])
    _upload(client, student["headers"], assignment["id"], ["An original sentence about volcanic rock formation."])

    resp = client.get("/api/faculty/dashboard", headers=faculty["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_assignments"] >= 1
    assert data["total_submissions"] >= 1


def test_student_dashboard_reflects_activity(client):
    faculty = register_and_login(client, "faculty", "dash_fac2@example.com")
    student = register_and_login(client, "student", "dash_stu2@example.com")
    assignment = _create_assignment(client, faculty["headers"])
    _upload(client, student["headers"], assignment["id"], ["Another wholly original sentence about sand dunes."])

    resp = client.get("/api/students/dashboard", headers=student["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_submissions"] >= 1


def test_comparison_requires_both_reports_generated(client):
    faculty = register_and_login(client, "faculty", "cmp_fac@example.com")
    student = register_and_login(client, "student", "cmp_stu@example.com")
    assignment = _create_assignment(client, faculty["headers"])
    sub_a = _upload(client, student["headers"], assignment["id"], ["Paragraph one about tectonic plates."], "a.docx")
    sub_b = _upload(client, student["headers"], assignment["id"], ["Paragraph one about tectonic plates."], "b.docx")

    # Neither has a report yet -> comparison should fail with a clear error, not a 500.
    resp = client.get(
        f"/api/submissions/{sub_a['id']}/compare/{sub_b['id']}", headers=faculty["headers"]
    )
    assert resp.status_code == 409

    client.post(f"/api/submissions/{sub_a['id']}/generate-report", headers=student["headers"])
    client.post(f"/api/submissions/{sub_b['id']}/generate-report", headers=student["headers"])

    resp = client.get(
        f"/api/submissions/{sub_a['id']}/compare/{sub_b['id']}", headers=faculty["headers"]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched_paragraph_count"] >= 1


def test_student_cannot_use_comparison_endpoint(client):
    faculty = register_and_login(client, "faculty", "cmp2_fac@example.com")
    student = register_and_login(client, "student", "cmp2_stu@example.com")
    assignment = _create_assignment(client, faculty["headers"])
    sub_a = _upload(client, student["headers"], assignment["id"], ["Text A"], "a.docx")
    sub_b = _upload(client, student["headers"], assignment["id"], ["Text B"], "b.docx")

    resp = client.get(f"/api/submissions/{sub_a['id']}/compare/{sub_b['id']}", headers=student["headers"])
    assert resp.status_code == 403
