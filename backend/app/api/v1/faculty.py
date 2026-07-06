"""Faculty CRUD — creating a faculty also creates a linked user account."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions
from app.core.security import hash_password
from app.models import Faculty, Role, User, UserRole
from app.schemas import FacultyCreate, FacultyOut

router = APIRouter(prefix="/faculty", tags=["faculty"])


@router.get("", response_model=list[FacultyOut])
def list_faculty(user: User = Depends(require_permissions("faculty.view")), db: Session = Depends(get_db)):
    return db.execute(select(Faculty).where(Faculty.organization_id == user.organization_id)).scalars().all()


@router.post("", response_model=FacultyOut, status_code=status.HTTP_201_CREATED)
def create_faculty(body: FacultyCreate, user: User = Depends(require_permissions("faculty.create")), db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    u = User(
        organization_id=user.organization_id,
        email=email,
        hashed_password=hash_password(body.password),
        first_name=body.first_name,
        last_name=body.last_name,
        is_active=True,
    )
    db.add(u)
    db.flush()

    faculty_role = db.execute(
        select(Role).where(Role.organization_id == user.organization_id, Role.slug == "faculty")
    ).scalar_one_or_none()
    if faculty_role:
        db.add(UserRole(user_id=u.id, role_id=faculty_role.id))

    f = Faculty(
        organization_id=user.organization_id,
        user_id=u.id,
        employee_number=body.employee_number,
        designation=body.designation,
        department_id=body.department_id,
        qualification=body.qualification,
        experience_years=body.experience_years,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


@router.get("/{faculty_id}", response_model=FacultyOut)
def get_faculty(faculty_id: str, user: User = Depends(require_permissions("faculty.view")), db: Session = Depends(get_db)):
    f = db.get(Faculty, faculty_id)
    if not f or f.organization_id != user.organization_id:
        raise HTTPException(404, "Not found")
    return f
