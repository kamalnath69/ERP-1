"""Thin role-aware dashboard API."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions
from app.services.business_access import ensure_location, organization_for
from app.services.dashboard import build_dashboard_workspace


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/workspace")
def dashboard_workspace(
    location_id: str | None = None,
    range_days: int = Query(30, alias="range", description="Dashboard period in days"),
    user=Depends(require_permissions("dashboard.view")),
    db: Session = Depends(get_db),
):
    days = range_days if range_days in {7, 30, 90} else 30
    organization = organization_for(db, user)
    if organization.industry.value == "college":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "College workspaces use the placement intelligence dashboard",
        )
    if location_id:
        ensure_location(db, user, location_id)
    return build_dashboard_workspace(db, user, location_id, days)
