"""Parents CRUD and student linking."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import Parent, Student, StudentParent, User

router = APIRouter(prefix="/parents", tags=["parents"])


class ParentIn(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr | None = None
    phone: str | None = None
    occupation: str | None = None


class ParentLink(BaseModel):
    student_id: str
    parent_id: str
    relationship: str = "guardian"


@router.get("")
def list_parents(user: User = Depends(require_permissions("students.view")), db: Session = Depends(get_db)):
    rows = db.execute(select(Parent).where(Parent.organization_id == user.organization_id)).scalars().all()
    return [
        {
            "id": p.id, "first_name": p.first_name, "last_name": p.last_name,
            "email": p.email, "phone": p.phone, "occupation": p.occupation,
        } for p in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_parent(body: ParentIn, user: User = Depends(require_permissions("students.create")), db: Session = Depends(get_db)):
    payload = body.model_dump()
    if payload.get("email"):
        payload["email"] = str(payload["email"]).lower()
    p = Parent(organization_id=user.organization_id, **payload)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id}


@router.post("/link")
def link_parent(body: ParentLink, user: User = Depends(require_permissions("students.edit")), db: Session = Depends(get_db)):
    student = db.get(Student, body.student_id)
    parent = db.get(Parent, body.parent_id)
    if not student or not parent or student.organization_id != user.organization_id or parent.organization_id != user.organization_id:
        raise HTTPException(404, "Student or parent not found")
    existing = db.execute(
        select(StudentParent).where(StudentParent.student_id == body.student_id, StudentParent.parent_id == body.parent_id)
    ).scalar_one_or_none()
    if existing:
        existing.relationship = body.relationship
    else:
        db.add(StudentParent(student_id=body.student_id, parent_id=body.parent_id, relationship=body.relationship))
    db.commit()
    return {"ok": True}


@router.get("/of-student/{student_id}")
def parents_of_student(student_id: str, user: User = Depends(require_permissions("students.view")), db: Session = Depends(get_db)):
    stmt = (
        select(Parent, StudentParent.relationship)
        .join(StudentParent, StudentParent.parent_id == Parent.id)
        .where(StudentParent.student_id == student_id, Parent.organization_id == user.organization_id)
    )
    rows = db.execute(stmt).all()
    return [{"id": p.id, "name": f"{p.first_name} {p.last_name}", "email": p.email, "phone": p.phone, "relationship": r} for p, r in rows]
