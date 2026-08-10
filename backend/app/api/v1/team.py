"""Focused Team directory API."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions
from app.services.team import build_team_directory


router = APIRouter(prefix="/employees", tags=["team"])


@router.get("/directory")
def team_directory(
    location_id: str | None = None,
    q: str | None = None,
    status: str | None = Query(default=None, pattern="^(active|inactive|on_leave)$"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    user=Depends(require_permissions("employees.view")),
    db: Session = Depends(get_db),
):
    return build_team_directory(db, user, location_id=location_id, query=q, status=status, limit=limit, cursor=cursor)
