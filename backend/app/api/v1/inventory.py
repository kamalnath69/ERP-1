"""Focused inventory API."""
from fastapi import APIRouter, Depends, Query, status
from pydantic import Field, model_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.validation import RequestModel
from app.core.deps import require_permissions
from app.services.inventory import inventory_levels_page, inventory_movements_page, inventory_workspace, transfer_stock


router = APIRouter(prefix="/inventory", tags=["inventory"])


class TransferBody(RequestModel):
    item_id: str
    source_location_id: str
    destination_location_id: str
    quantity_milli: int = Field(gt=0)
    batch_number: str = Field(default="", max_length=120)
    reason: str = Field(min_length=3, max_length=300)

    @model_validator(mode="after")
    def different_locations(self):
        if self.source_location_id == self.destination_location_id:
            raise ValueError("Destination location must differ from the source")
        return self


@router.get("/workspace")
def workspace(
    location_id: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    state: str | None = Query(default=None, pattern="^(low|out|expiring|available|in_stock)$"),
    user=Depends(require_permissions("inventory.view")),
    db: Session = Depends(get_db),
):
    return inventory_workspace(db, user, location_id, q, state)


@router.get("/levels/page")
def levels_page(
    location_id: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    state: str | None = Query(default=None, pattern="^(low|out|expiring|available|in_stock)$"),
    batches_only: bool = False,
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    user=Depends(require_permissions("inventory.view")),
    db: Session = Depends(get_db),
):
    return inventory_levels_page(db, user, location_id, q, state, batches_only, cursor, limit)


@router.get("/movements/page")
def movements_page(
    location_id: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    movement_type: str | None = Query(default=None, max_length=30),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    user=Depends(require_permissions("inventory.view")),
    db: Session = Depends(get_db),
):
    return inventory_movements_page(db, user, location_id, q, movement_type, cursor, limit)


@router.post("/transfer", status_code=status.HTTP_201_CREATED)
def transfer(body: TransferBody, user=Depends(require_permissions("inventory.adjust")), db: Session = Depends(get_db)):
    return transfer_stock(db, user, **body.model_dump())
