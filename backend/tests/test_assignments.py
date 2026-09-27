from tests.conftest import register_and_login


def _make_assignment(client, faculty_headers, title="Essay on Federalism", **extra):
    resp = client.post("/api/assignments", json={"title": title, **extra}, headers=faculty_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_faculty_can_create_and_list_assignment(client):
    faculty = register_and_login(client, "faculty", "fac1@example.com")
    created = _make_assignment(client, faculty["headers"])
    assert created["title"] == "Essay on Federalism"
    assert created["is_active"] is True

    listed = client.get("/api/assignments", headers=faculty["headers"])
    assert listed.status_code == 200
    assert any(a["id"] == created["id"] for a in listed.json())


def test_student_cannot_create_assignment(client):
    student = register_and_login(client, "student", "stu1@example.com")
    resp = client.post("/api/assignments", json={"title": "Should Fail"}, headers=student["headers"])
    assert resp.status_code == 403


def test_student_sees_only_active_assignments(client):
    faculty = register_and_login(client, "faculty", "fac2@example.com")
    active = _make_assignment(client, faculty["headers"], title="Active One")
    inactive = _make_assignment(client, faculty["headers"], title="Inactive One")
    client.put(f"/api/assignments/{inactive['id']}", json={"is_active": False}, headers=faculty["headers"])

    student = register_and_login(client, "student", "stu2@example.com")
    listed = client.get("/api/assignments", headers=student["headers"])
    ids = [a["id"] for a in listed.json()]
    assert active["id"] in ids
    assert inactive["id"] not in ids


def test_faculty_cannot_edit_others_assignment(client):
    faculty_a = register_and_login(client, "faculty", "faca@example.com")
    faculty_b = register_and_login(client, "faculty", "facb@example.com")
    assignment = _make_assignment(client, faculty_a["headers"])

    resp = client.put(
        f"/api/assignments/{assignment['id']}", json={"title": "Hijacked"}, headers=faculty_b["headers"]
    )
    assert resp.status_code == 403


def test_assignment_search_matches_title(client):
    faculty = register_and_login(client, "faculty", "facsearch@example.com")
    _make_assignment(client, faculty["headers"], title="Photosynthesis Report")
    _make_assignment(client, faculty["headers"], title="Cold War Essay")

    resp = client.get("/api/assignments", params={"search": "photosynthesis"}, headers=faculty["headers"])
    titles = [a["title"] for a in resp.json()]
    assert titles == ["Photosynthesis Report"]


def test_delete_assignment(client):
    faculty = register_and_login(client, "faculty", "facdel@example.com")
    assignment = _make_assignment(client, faculty["headers"])
    resp = client.delete(f"/api/assignments/{assignment['id']}", headers=faculty["headers"])
    assert resp.status_code == 204
    resp = client.get(f"/api/assignments/{assignment['id']}", headers=faculty["headers"])
    assert resp.status_code == 404
