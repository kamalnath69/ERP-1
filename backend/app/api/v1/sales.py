"""Thin sales and payment API."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions
from app.services.sales import create_sale, invoice_detail, record_payment, sales_workspace, void_invoice


router = APIRouter(prefix="/sales", tags=["sales"])


class InvoiceLineBody(BaseModel):
    item_id: str
    quantity_milli: int = Field(gt=0)
    discount_paise: int = Field(default=0, ge=0)


class InvoiceBody(BaseModel):
    location_id: str
    client_id: str | None = None
    employee_id: str | None = None
    lines: list[InvoiceLineBody] = Field(min_length=1, max_length=100)
    discount_paise: int = Field(default=0, ge=0)
    interstate: bool = False
    notes: str | None = Field(default=None, max_length=2000)
    issue: bool = True
    idempotency_key: str = Field(min_length=8, max_length=120)


class PaymentBody(BaseModel):
    amount_paise: int = Field(gt=0)
    method: str
    reference: str | None = Field(default=None, max_length=120)
    idempotency_key: str = Field(min_length=8, max_length=120)
    version: int | None = Field(default=None, ge=1)


class VoidInvoiceBody(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    version: int | None = Field(default=None, ge=1)


@router.get("/workspace")
def workspace(
    location_id: str | None = None,
    q: str | None = Query(default=None, max_length=120),
    status_filter: str | None = Query(default=None, alias="status"),
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    user=Depends(require_permissions("sales.view")),
    db: Session = Depends(get_db),
):
    return sales_workspace(
        db,
        user,
        location_id=location_id,
        query=q,
        status_filter=status_filter,
        starts_at=starts_at,
        ends_at=ends_at,
        limit=limit,
        cursor=cursor,
    )


@router.get("")
def list_compatibility(
    location_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    user=Depends(require_permissions("sales.view")),
    db: Session = Depends(get_db),
):
    """Compatibility list while callers move to the richer workspace contract."""
    return sales_workspace(
        db,
        user,
        location_id=location_id,
        status_filter=status_filter,
        limit=100,
    )["items"]


@router.get("/{invoice_id}")
def detail(invoice_id: str, user=Depends(require_permissions("sales.view")), db: Session = Depends(get_db)):
    return invoice_detail(db, user, invoice_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create(body: InvoiceBody, user=Depends(require_permissions("sales.manage")), db: Session = Depends(get_db)):
    return create_sale(db, user, body)


@router.post("/{invoice_id}/payments", status_code=status.HTTP_201_CREATED)
def payment(invoice_id: str, body: PaymentBody, user=Depends(require_permissions("payments.record")), db: Session = Depends(get_db)):
    return record_payment(db, user, invoice_id, body)


@router.post("/{invoice_id}/void")
def void(invoice_id: str, body: VoidInvoiceBody, user=Depends(require_permissions("sales.manage")), db: Session = Depends(get_db)):
    return void_invoice(db, user, invoice_id, body)
