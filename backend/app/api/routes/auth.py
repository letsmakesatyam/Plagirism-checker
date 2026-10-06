"""
Authentication endpoints.

POST /api/auth/register  -> create a Faculty or Student account
POST /api/auth/login     -> obtain a JWT access token
GET  /api/auth/me        -> current authenticated user's profile
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, needs_upgrade, verify_password
from app.database import get_db
from app.models.user import User
from app.schemas.user import Token, UserLogin, UserOut, UserRegister

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    normalized_email = payload.email.strip().lower()

    existing = db.query(User).filter(func.lower(func.trim(User.email)) == normalized_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered. Please sign in or use account recovery.",
        )

    user = User(
        full_name=payload.full_name.strip(),
        email=normalized_email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        roll_number=payload.roll_number.strip() if payload.roll_number else None,
        division=payload.division.strip() if payload.division else None,
        batch=payload.batch.strip() if payload.batch else None,
        department=payload.department.strip() if payload.department else None,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered. Please sign in or use account recovery.",
        )
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    normalized_email = payload.email.strip().lower()

    user = db.query(User).filter(func.lower(func.trim(User.email)) == normalized_email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    # Seamlessly upgrade legacy bcrypt hashes to versioned $v2$ format upon successful authentication
    if needs_upgrade(user.hashed_password):
        try:
            user.hashed_password = hash_password(payload.password)
            db.commit()
            logger.info("auth_upgraded_password_hash", extra={"user_id": str(user.id)})
        except Exception as exc:
            logger.warning("auth_failed_to_upgrade_hash", extra={"error": str(exc)})
            db.rollback()

    token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    return Token(access_token=token, user=user)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
