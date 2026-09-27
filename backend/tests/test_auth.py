from tests.conftest import register_and_login


def test_register_and_login_faculty(client):
    auth = register_and_login(client, "faculty", "prof@example.com", department="CS")
    assert auth["user"]["role"] == "faculty"
    assert auth["user"]["department"] == "CS"


def test_register_and_login_student(client):
    auth = register_and_login(client, "student", "student@example.com", roll_number="21CS001")
    assert auth["user"]["role"] == "student"
    assert auth["user"]["roll_number"] == "21CS001"


def test_duplicate_email_rejected(client):
    payload = {"full_name": "Ann Duplicate", "email": "dup@example.com", "password": "TestPassword123", "role": "student"}
    first = client.post("/api/auth/register", json=payload)
    assert first.status_code == 201
    second = client.post("/api/auth/register", json=payload)
    assert second.status_code == 409


def test_wrong_password_rejected(client):
    register_and_login(client, "student", "wrongpass@example.com")
    resp = client.post("/api/auth/login", json={"email": "wrongpass@example.com", "password": "NotTheRightOne1"})
    assert resp.status_code == 401


def test_me_requires_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_returns_current_user(client):
    auth = register_and_login(client, "faculty", "me@example.com")
    resp = client.get("/api/auth/me", headers=auth["headers"])
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"


def test_short_password_rejected_by_validation(client):
    resp = client.post(
        "/api/auth/register",
        json={"full_name": "A", "email": "short@example.com", "password": "short", "role": "student"},
    )
    assert resp.status_code == 422
