"""Student CRUD."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import Student, User
from app.schemas import StudentCreate, StudentOut, StudentUpdate

router = APIRouter(prefix="/students", tags=["students"])


@router.get("", response_model=list[StudentOut])
def list_students(
    q: str | None = None,
    section_id: str | None = None,
    department_id: str | None = None,
    user: User = Depends(require_permissions("students.view")),
    db: Session = Depends(get_db),
):
    stmt = select(Student).where(Student.organization_id == user.organization_id)
    if section_id:
        stmt = stmt.where(Student.section_id == section_id)
    if department_id:
        stmt = stmt.where(Student.department_id == department_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Student.first_name).like(like),
                func.lower(Student.last_name).like(like),
                func.lower(Student.admission_number).like(like),
                func.lower(Student.email).like(like),
                func.lower(Student.roll_number).like(like),
            )
        )
    stmt = stmt.order_by(Student.created_at.desc()).limit(500)
    return db.execute(stmt).scalars().all()


@router.post("", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def create_student(body: StudentCreate, user: User = Depends(require_permissions("students.create")), db: Session = Depends(get_db)):
    exists = db.execute(
        select(Student).where(
            Student.organization_id == user.organization_id,
            Student.admission_number == body.admission_number,
        )
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Admission number already exists")

    payload = body.model_dump()
    if payload.get("email"):
        payload["email"] = str(payload["email"]).lower()
    s = Student(organization_id=user.organization_id, **payload)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.get("/{student_id}", response_model=StudentOut)
def get_student(student_id: str, user: User = Depends(require_permissions("students.view")), db: Session = Depends(get_db)):
    s = db.get(Student, student_id)
    if not s or s.organization_id != user.organization_id:
        raise HTTPException(404, "Not found")
    return s


@router.patch("/{student_id}", response_model=StudentOut)
def update_student(student_id: str, body: StudentUpdate, user: User = Depends(require_permissions("students.edit")), db: Session = Depends(get_db)):
    s = db.get(Student, student_id)
    if not s or s.organization_id != user.organization_id:
        raise HTTPException(404, "Not found")
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "email" and v:
            v = str(v).lower()
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/{student_id}")
def delete_student(student_id: str, user: User = Depends(require_permissions("students.delete")), db: Session = Depends(get_db)):
    s = db.get(Student, student_id)
    if not s or s.organization_id != user.organization_id:
        raise HTTPException(404, "Not found")
    db.delete(s)
    db.commit()
    return {"ok": True}
