"""Academic structure endpoints: departments, units, levels, sections, subjects."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import AcademicLevel, AcademicUnit, Department, Section, Subject, User
from app.schemas import (
    AcademicUnitCreate,
    AcademicUnitOut,
    DepartmentCreate,
    DepartmentOut,
    LevelCreate,
    LevelOut,
    SectionCreate,
    SectionOut,
    SubjectCreate,
    SubjectOut,
)

router = APIRouter(prefix="/academic", tags=["academic"])


# ---------- departments ----------
@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(user: User = Depends(require_permissions("academic.view")), db: Session = Depends(get_db)):
    return db.execute(select(Department).where(Department.organization_id == user.organization_id)).scalars().all()


@router.post("/departments", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
def create_department(body: DepartmentCreate, user: User = Depends(require_permissions("departments.manage")), db: Session = Depends(get_db)):
    d = Department(organization_id=user.organization_id, name=body.name, code=body.code, description=body.description)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.delete("/departments/{dept_id}")
def delete_department(dept_id: str, user: User = Depends(require_permissions("departments.manage")), db: Session = Depends(get_db)):
    d = db.get(Department, dept_id)
    if not d or d.organization_id != user.organization_id:
        raise HTTPException(404, "Not found")
    db.delete(d)
    db.commit()
    return {"ok": True}


# ---------- academic units ----------
@router.get("/units", response_model=list[AcademicUnitOut])
def list_units(user: User = Depends(require_permissions("academic.view")), db: Session = Depends(get_db)):
    return db.execute(select(AcademicUnit).where(AcademicUnit.organization_id == user.organization_id)).scalars().all()


@router.post("/units", response_model=AcademicUnitOut, status_code=status.HTTP_201_CREATED)
def create_unit(body: AcademicUnitCreate, user: User = Depends(require_permissions("academic.manage")), db: Session = Depends(get_db)):
    u = AcademicUnit(organization_id=user.organization_id, **body.model_dump())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ---------- levels ----------
@router.get("/levels", response_model=list[LevelOut])
def list_levels(user: User = Depends(require_permissions("academic.view")), db: Session = Depends(get_db), unit_id: str | None = None):
    stmt = select(AcademicLevel).where(AcademicLevel.organization_id == user.organization_id)
    if unit_id:
        stmt = stmt.where(AcademicLevel.unit_id == unit_id)
    return db.execute(stmt.order_by(AcademicLevel.sequence)).scalars().all()


@router.post("/levels", response_model=LevelOut, status_code=status.HTTP_201_CREATED)
def create_level(body: LevelCreate, user: User = Depends(require_permissions("academic.manage")), db: Session = Depends(get_db)):
    lvl = AcademicLevel(organization_id=user.organization_id, **body.model_dump())
    db.add(lvl)
    db.commit()
    db.refresh(lvl)
    return lvl


# ---------- sections ----------
@router.get("/sections", response_model=list[SectionOut])
def list_sections(user: User = Depends(require_permissions("academic.view")), db: Session = Depends(get_db), level_id: str | None = None):
    stmt = select(Section).where(Section.organization_id == user.organization_id)
    if level_id:
        stmt = stmt.where(Section.level_id == level_id)
    return db.execute(stmt).scalars().all()


@router.post("/sections", response_model=SectionOut, status_code=status.HTTP_201_CREATED)
def create_section(body: SectionCreate, user: User = Depends(require_permissions("academic.manage")), db: Session = Depends(get_db)):
    s = Section(organization_id=user.organization_id, **body.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ---------- subjects ----------
@router.get("/subjects", response_model=list[SubjectOut])
def list_subjects(user: User = Depends(require_permissions("academic.view")), db: Session = Depends(get_db)):
    return db.execute(select(Subject).where(Subject.organization_id == user.organization_id).order_by(Subject.name)).scalars().all()


@router.post("/subjects", response_model=SubjectOut, status_code=status.HTTP_201_CREATED)
def create_subject(body: SubjectCreate, user: User = Depends(require_permissions("subjects.manage")), db: Session = Depends(get_db)):
    s = Subject(organization_id=user.organization_id, **body.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s
