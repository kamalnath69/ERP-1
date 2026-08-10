"""Thin Client directory API."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import User
from app.services.clients import client_directory

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("/directory")
def directory(
    q: str | None = None,
    segment: str = "all",
    location_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    user: User = Depends(require_permissions("clients.view")),
    db: Session = Depends(get_db),
):
    return client_directory(
        db,
        user,
        location_id=location_id,
        query=q,
        segment=segment,
        limit=limit,
        cursor=cursor,
    )
