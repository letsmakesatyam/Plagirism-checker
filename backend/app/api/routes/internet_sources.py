"""
Internet-source corpus management (Phase 4b). Faculty-only: this is
knowledge-base administration, not part of the student submission flow.

POST /api/internet-sources          -> add a source from pasted/uploaded text
POST /api/internet-sources/from-url -> add a source by fetching a URL (needs
                                        real internet access — see README)
GET  /api/internet-sources          -> list indexed sources (for a faculty
                                        admin screen to see what's been indexed)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_role
from app.database import get_db
from app.models.internet_source import InternetSource
from app.models.user import User, UserRole
from app.schemas.internet_source import InternetSourceCreateFromText, InternetSourceCreateFromUrl, InternetSourceOut
from app.services.source_ingestion import ingest_source_from_text, ingest_source_from_url

router = APIRouter(prefix="/api/internet-sources", tags=["internet-sources"])


@router.post("", response_model=InternetSourceOut, status_code=status.HTTP_201_CREATED)
def add_source_from_text(
    payload: InternetSourceCreateFromText,
    db: Session = Depends(get_db),
    _faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    try:
        return ingest_source_from_text(
            title=payload.title, category=payload.category, text=payload.text, db=db, url=payload.url
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/from-url", response_model=InternetSourceOut, status_code=status.HTTP_201_CREATED)
def add_source_from_url(
    payload: InternetSourceCreateFromUrl,
    db: Session = Depends(get_db),
    _faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    try:
        return ingest_source_from_url(title=payload.title, category=payload.category, url=payload.url, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — network/HTTP errors from httpx
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not fetch URL: {exc}")


@router.get("", response_model=list[InternetSourceOut])
def list_sources(
    db: Session = Depends(get_db),
    _faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    return db.query(InternetSource).order_by(InternetSource.created_at.desc()).all()
