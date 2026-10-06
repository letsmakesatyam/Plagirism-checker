import io
from app.core.security import hash_password, verify_password, _prehash_v2, needs_upgrade
from app.models.user import User, UserRole
from app.database import SessionLocal
import bcrypt


def test_password_schemes_and_boundary(client, db_session):
    # 1. Test legacy bcrypt ($2b$) compatibility
    plain_legacy = "LegacyPassword123"
    legacy_hash = bcrypt.hashpw(plain_legacy.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")
    assert legacy_hash.startswith("$2b$")
    assert needs_upgrade(legacy_hash) is True
    assert verify_password(plain_legacy, legacy_hash) is True
    assert verify_password("WrongPassword", legacy_hash) is False

    # 2. Test versioned $v2$ password scheme
    new_pass = "ModernSecurePassword123"
    v2_hash = hash_password(new_pass)
    assert v2_hash.startswith("$v2$")
    assert needs_upgrade(v2_hash) is False
    assert verify_password(new_pass, v2_hash) is True
    assert verify_password("WrongPassword", v2_hash) is False

    # 3. Test >72 bytes password and UTF-8 boundary
    long_pass = "VeryLongPassword_With_Unicode_Characters_öäü_and_symbols_1234567890_More_And_More_Long_Text"
    assert len(long_pass.encode("utf-8")) > 72
    long_hash = hash_password(long_pass)
    assert verify_password(long_pass, long_hash) is True
    # If truncated to 72 bytes, slightly different end would match; with v2 prehash it will NOT match:
    tampered_end = long_pass[:-1] + "X"
    assert verify_password(tampered_end, long_hash) is False

    # 4. Test malformed hash does not raise 500/exception
    assert verify_password("AnyPass", "not_a_valid_hash") is False
    assert verify_password("AnyPass", "$2b$invalid_salt") is False
    assert verify_password("AnyPass", "") is False


def test_mixed_case_and_whitespace_login(client, db_session):
    # Register with mixed case and trailing space
    reg_payload = {
        "full_name": "Case Sensitive User",
        "email": "CaseTest@Example.Com ",
        "password": "Password123!",
        "role": "student",
    }
    resp = client.post("/api/auth/register", json=reg_payload)
    assert resp.status_code == 201
    created_email = resp.json()["email"]
    assert created_email == "casetest@example.com"

    # Login with all uppercase
    resp_login = client.post("/api/auth/login", json={"email": "CASETEST@EXAMPLE.COM", "password": "Password123!"})
    assert resp_login.status_code == 200
    assert resp_login.json()["user"]["email"] == "casetest@example.com"

    # Duplicate registration with different case returns 409
    dup_resp = client.post("/api/auth/register", json={
        "full_name": "Dup User",
        "email": "casetest@example.com",
        "password": "DifferentPassword123",
        "role": "student",
    })
    assert dup_resp.status_code == 409


def test_legacy_hash_upgrade_on_login(client, db_session):
    # Manually insert user with legacy $2b$ hash
    plain_pass = "MyLegacySecretPass1"
    legacy_hash = bcrypt.hashpw(plain_pass.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")

    user = User(
        full_name="Legacy User",
        email="legacy_user@example.com",
        hashed_password=legacy_hash,
        role=UserRole.STUDENT,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.hashed_password.startswith("$2b$")

    # Login
    resp = client.post("/api/auth/login", json={"email": "legacy_user@example.com", "password": plain_pass})
    assert resp.status_code == 200

    # Verify that in database, the hash was upgraded to $v2$
    db_session.expire_all()
    reloaded = db_session.query(User).filter(User.id == user.id).first()
    assert reloaded.hashed_password.startswith("$v2$")


def test_disabled_account_login(client, db_session):
    user = User(
        full_name="Disabled User",
        email="disabled@example.com",
        hashed_password=hash_password("Pass1234567"),
        role=UserRole.STUDENT,
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()

    resp = client.post("/api/auth/login", json={"email": "disabled@example.com", "password": "Pass1234567"})
    assert resp.status_code == 403
    assert "Account is disabled" in resp.json()["detail"]
