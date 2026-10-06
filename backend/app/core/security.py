"""
Password hashing (versioned bcrypt with pre-hashing) and JWT encode/decode helpers.

Versioned scheme:
- $v2$: SHA-256 pre-hashed password followed by bcrypt hashing. Eliminates bcrypt's
  hard 72-byte input truncation limit for any Unicode length while maintaining
  high entropy and constant-size input.
- Legacy ($2a$, $2b$, $2y$): Historical direct bcrypt hashing with 72-byte truncation.
  Supported for backward compatibility, automatically upgraded upon successful login.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import logging

import bcrypt
from jose import jwt, JWTError

from app.config import settings

logger = logging.getLogger(__name__)

_BCRYPT_MAX_BYTES = 72  # bcrypt's legacy hard input limit
_V2_PREFIX = "$v2$"


def _prehash_v2(plain_password: str) -> bytes:
    """Pre-hashes arbitrary-length UTF-8 password to fixed 32-byte digest before bcrypt."""
    return hashlib.sha256(plain_password.encode("utf-8")).digest()


def hash_password(plain_password: str) -> str:
    """
    Hashes a password using the current versioned scheme ($v2$).
    Uses SHA-256 pre-hash followed by bcrypt, completely avoiding silent truncation.
    """
    prehashed = _prehash_v2(plain_password)
    hashed = bcrypt.hashpw(prehashed, bcrypt.gensalt()).decode("utf-8")
    return f"{_V2_PREFIX}{hashed}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain password against a stored hash safely.
    Supports $v2$ (versioned) and legacy bcrypt ($2a$, $2b$, $2y$).
    Handles malformed or unsupported stored hashes safely without throwing 500 exceptions.
    """
    if not plain_password or not hashed_password:
        return False

    try:
        if hashed_password.startswith(_V2_PREFIX):
            raw_hash = hashed_password[len(_V2_PREFIX):]
            prehashed = _prehash_v2(plain_password)
            return bcrypt.checkpw(prehashed, raw_hash.encode("utf-8"))

        if hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
            # Legacy bcrypt scheme (truncate to 72 bytes)
            password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
            return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))

        # Unknown or unsupported hash scheme
        logger.warning("auth_unsupported_hash_scheme", extra={"prefix": hashed_password[:7]})
        return False
    except (ValueError, TypeError) as exc:
        logger.warning("auth_malformed_hash_encountered", extra={"error": str(exc)})
        return False
    except Exception as exc:
        logger.error("auth_password_verification_error", extra={"error": str(exc)})
        return False


def needs_upgrade(hashed_password: str) -> bool:
    """Checks if the stored hash belongs to an older scheme and should be upgraded."""
    if not hashed_password:
        return False
    return not hashed_password.startswith(_V2_PREFIX)


def create_access_token(data: dict, expires_minutes: int | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
