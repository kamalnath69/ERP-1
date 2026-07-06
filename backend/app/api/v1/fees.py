"""Fees module."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import FeeInvoice, FeeStructure, Student, User

router = APIRouter(prefix="/fees", tags=["fees"])


class StructureIn(BaseModel):
    name: str
    amount: float
    level_id: str | None = None
    department_id: str | None = None
    due_date: str | None = None
    description: str | None = None


class InvoiceIn(BaseModel):
    student_id: str
    structure_id: str | None = None
    amount: float
    due_date: str | None = None


class BulkAssignIn(BaseModel):
    structure_id: str
    section_id: str | None = None
    department_id: str | None = None


@router.get("/structures")
def list_structures(user: User = Depends(require_permissions("billing.view")), db: Session = Depends(get_db)):
    rows = db.execute(select(FeeStructure).where(FeeStructure.organization_id == user.organization_id)).scalars().all()
    return [
        {
            "id": s.id, "name": s.name, "amount": s.amount, "level_id": s.level_id,
            "department_id": s.department_id, "due_date": s.due_date, "is_active": s.is_active,
        } for s in rows
    ]


@router.post("/structures", status_code=status.HTTP_201_CREATED)
def create_structure(body: StructureIn, user: User = Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    s = FeeStructure(organization_id=user.organization_id, **body.model_dump())
    db.add(s)
    db.commit()
    return {"id": s.id}


@router.post("/bulk-assign")
def bulk_assign(body: BulkAssignIn, user: User = Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    struct = db.get(FeeStructure, body.structure_id)
    if not struct or struct.organization_id != user.organization_id:
        raise HTTPException(404, "Structure not found")
    stmt = select(Student).where(Student.organization_id == user.organization_id)
    if body.section_id:
        stmt = stmt.where(Student.section_id == body.section_id)
    if body.department_id:
        stmt = stmt.where(Student.department_id == body.department_id)
    students = db.execute(stmt).scalars().all()
    created = 0
    for stu in students:
        inv = FeeInvoice(
            organization_id=user.organization_id,
            student_id=stu.id,
            structure_id=struct.id,
            amount=struct.amount,
            due_date=struct.due_date,
        )
        db.add(inv)
        created += 1
    db.commit()
    return {"ok": True, "invoices_created": created}


@router.get("/invoices")
def list_invoices(
    student_id: str | None = None,
    status: str | None = None,
    user: User = Depends(require_permissions("billing.view")),
    db: Session = Depends(get_db),
):
    stmt = select(FeeInvoice).where(FeeInvoice.organization_id == user.organization_id)
    if student_id:
        stmt = stmt.where(FeeInvoice.student_id == student_id)
    if status:
        stmt = stmt.where(FeeInvoice.status == status)
    rows = db.execute(stmt.order_by(FeeInvoice.created_at.desc()).limit(500)).scalars().all()
    return [
        {
            "id": i.id, "student_id": i.student_id, "amount": i.amount, "amount_paid": i.amount_paid,
            "status": i.status, "due_date": i.due_date, "paid_at": i.paid_at,
        } for i in rows
    ]


@router.post("/invoices", status_code=status.HTTP_201_CREATED)
def create_invoice(body: InvoiceIn, user: User = Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    i = FeeInvoice(organization_id=user.organization_id, **body.model_dump())
    db.add(i)
    db.commit()
    return {"id": i.id}


@router.post("/invoices/{invoice_id}/mark-paid")
def mark_paid(invoice_id: str, user: User = Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    inv = db.get(FeeInvoice, invoice_id)
    if not inv or inv.organization_id != user.organization_id:
        raise HTTPException(404, "Not found")
    inv.status = "paid"
    inv.amount_paid = inv.amount
    inv.paid_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.get("/summary")
def fee_summary(user: User = Depends(require_permissions("billing.view")), db: Session = Depends(get_db)):
    from sqlalchemy import func
    rows = db.execute(
        select(FeeInvoice.status, func.count(FeeInvoice.id), func.sum(FeeInvoice.amount), func.sum(FeeInvoice.amount_paid))
        .where(FeeInvoice.organization_id == user.organization_id)
        .group_by(FeeInvoice.status)
    ).all()
    return {
        "by_status": [
            {"status": s, "count": c, "total": float(t or 0), "collected": float(p or 0)}
            for s, c, t, p in rows
        ]
    }
