"""
Tests for document viewer endpoints:
- GET /api/submissions/{id}/document-view
- GET /api/submissions/{id}/pages/{page}/image
- GET /api/submissions/{id}/annotated-file
"""
import io
import fitz
from tests.conftest import register_and_login


def make_sample_pdf_bytes() -> bytes:
    """Create a minimal 2-page PDF for test uploads."""
    doc = fitz.open()
    page1 = doc.new_page(width=595, height=842)
    page1.insert_text((50, 100), "First paragraph of student submission text for testing.", fontsize=12)
    page1.insert_text((50, 200), "Second paragraph of the assignment document here.", fontsize=12)

    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((50, 100), "Third paragraph on the second page of this document.", fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_document_viewer_flow(client):
    # 1. Register faculty and student
    faculty_headers = register_and_login(client, "faculty", "faculty_doc@example.com")["headers"]
    student_headers = register_and_login(client, "student", "student_doc@example.com")["headers"]
    other_student_headers = register_and_login(client, "student", "student_other@example.com")["headers"]

    # 2. Create assignment
    res = client.post(
        "/api/assignments",
        json={"title": "Doc Viewer Test Assignment", "description": "Testing in-doc highlighting"},
        headers=faculty_headers,
    )
    assert res.status_code == 201, res.text
    assignment_id = res.json()["id"]

    # 3. Upload submission
    pdf_content = make_sample_pdf_bytes()
    upload_res = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        files={"file": ("test_doc.pdf", io.BytesIO(pdf_content), "application/pdf")},
        headers=student_headers,
    )
    assert upload_res.status_code == 201, upload_res.text
    submission_id = upload_res.json()["id"]

    # 4. Generate report
    rep_res = client.post(
        f"/api/submissions/{submission_id}/generate-report",
        headers=student_headers,
    )
    assert rep_res.status_code == 200, rep_res.text

    # 5. Test GET /document-view (as student owner)
    dv_res = client.get(
        f"/api/submissions/{submission_id}/document-view",
        headers=student_headers,
    )
    assert dv_res.status_code == 200, dv_res.text
    dv_data = dv_res.json()
    assert dv_data["page_count"] == 2
    assert len(dv_data["pages"]) == 2
    assert "highlights" in dv_data["pages"][0]
    assert "summary" in dv_data

    # 6. Test GET /document-view (as owning faculty)
    dv_fac_res = client.get(
        f"/api/submissions/{submission_id}/document-view",
        headers=faculty_headers,
    )
    assert dv_fac_res.status_code == 200

    # 7. Test GET /document-view unauthorized (other student) -> 403
    dv_other_res = client.get(
        f"/api/submissions/{submission_id}/document-view",
        headers=other_student_headers,
    )
    assert dv_other_res.status_code == 403

    # 8. Test GET page image
    img_res = client.get(
        f"/api/submissions/{submission_id}/pages/1/image?annotated=true",
        headers=student_headers,
    )
    assert img_res.status_code == 200
    assert img_res.headers["content-type"] == "image/png"
    assert len(img_res.content) > 1000

    # 9. Test GET page image via query token
    raw_token = student_headers["Authorization"].split("Bearer ")[1]
    img_token_res = client.get(
        f"/api/submissions/{submission_id}/pages/1/image?annotated=true&token={raw_token}",
    )
    assert img_token_res.status_code == 200
    assert img_token_res.headers["content-type"] == "image/png"

    # 10. Test GET annotated PDF file
    pdf_res = client.get(
        f"/api/submissions/{submission_id}/annotated-file",
        headers=student_headers,
    )
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert len(pdf_res.content) > 1000
