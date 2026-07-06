"""Faculty assignments (faculty × subject × section)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import FacultyAssignment, User

router = APIRouter(prefix="/assignments", tags=["assignments"])


class AssignmentIn(BaseModel):
    faculty_user_id: str
    subject_id: str
    section_id: str
    role: str = "teacher"
    academic_year_id: str | None = None


@router.get("")
def list_assignments(
    section_id: str | None = None,
    faculty_user_id: str | None = None,
    user: User = Depends(require_permissions("academic.view")),
    db: Session = Depends(get_db),
):
    stmt = select(FacultyAssignment).where(FacultyAssignment.organization_id == user.organization_id)
    if section_id:
        stmt = stmt.where(FacultyAssignment.section_id == section_id)
    if faculty_user_id:
        stmt = stmt.where(FacultyAssignment.faculty_user_id == faculty_user_id)
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": a.id, "faculty_user_id": a.faculty_user_id, "subject_id": a.subject_id,
            "section_id": a.section_id, "role": a.role,
        } for a in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_assignment(body: AssignmentIn, user: User = Depends(require_permissions("academic.manage")), db: Session = Depends(get_db)):
    a = FacultyAssignment(organization_id=user.organization_id, **body.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"id": a.id}


@router.delete("/{assignment_id}")
def delete_assignment(assignment_id: str, user: User = Depends(require_permissions("academic.manage")), db: Session = Depends(get_db)):
    a = db.get(FacultyAssignment, assignment_id)
    if not a or a.organization_id != user.organization_id:
        raise HTTPException(404, "Not found")
    db.delete(a)
    db.commit()
    return {"ok": True}
