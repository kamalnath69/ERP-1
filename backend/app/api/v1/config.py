"""Config API — custom permissions, terminology, and academic engine (exam types,
attendance statuses, grade bands). Everything here is tenant-driven metadata.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permissions
from app.models import (
    AttendanceStatusConfig,
    ExamType,
    GradeBand,
    Permission,
    Setting,
    User,
)

router = APIRouter(prefix="", tags=["config"])


# ========================================================================== #
# 1) CUSTOM PERMISSIONS — Principal can create tenant-scoped permission codes.
# ========================================================================== #

class PermissionCreate(BaseModel):
    code: str = Field(min_length=2, max_length=120)
    label: str = Field(min_length=1, max_length=200)
    module: str = Field(min_length=1, max_length=80)
    description: str | None = None


class PermissionUpdate(BaseModel):
    label: str | None = None
    module: str | None = None
    description: str | None = None


@router.post("/permissions", status_code=status.HTTP_201_CREATED)
def create_permission(
    body: PermissionCreate,
    user: User = Depends(require_permissions("roles.manage")),
    db: Session = Depends(get_db),
):
    if not user.organization_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No organization context")
    code = body.code.strip().lower()
    dup = db.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Permission code '{code}' already exists")
    p = Permission(
        code=code,
        label=body.label.strip(),
        module=body.module.strip(),
        description=body.description,
        organization_id=user.organization_id,  # tenant-scoped
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "code": p.code, "label": p.label, "module": p.module,
            "description": p.description, "organization_id": p.organization_id}


@router.patch("/permissions/{perm_id}")
def update_permission(
    perm_id: str,
    body: PermissionUpdate,
    user: User = Depends(require_permissions("roles.manage")),
    db: Session = Depends(get_db),
):
    p = db.get(Permission, perm_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Permission not found")
    if p.organization_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform permissions are read-only")
    if not user.is_super_admin and p.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant modification blocked")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "code": p.code, "label": p.label, "module": p.module,
            "description": p.description, "organization_id": p.organization_id}


@router.delete("/permissions/{perm_id}")
def delete_permission(
    perm_id: str,
    user: User = Depends(require_permissions("roles.manage")),
    db: Session = Depends(get_db),
):
    p = db.get(Permission, perm_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Permission not found")
    if p.organization_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform permissions cannot be deleted")
    if not user.is_super_admin and p.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant modification blocked")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ========================================================================== #
# 2) TERMINOLOGY — rename hierarchy labels per tenant.
# ========================================================================== #

DEFAULT_TERMINOLOGY = {
    "organization": "Organization",
    "campus": "Campus",
    "department": "Department",
    "academic_unit": "Academic Unit",
    "level": "Level",
    "section": "Section",
    "subject": "Subject",
    "student": "Student",
    "faculty": "Faculty",
    "exam": "Exam",
    "attendance": "Attendance",
}


class TerminologyIn(BaseModel):
    terms: dict[str, str]


@router.get("/settings/terminology")
def get_terminology(user: CurrentUser, db: Session = Depends(get_db)):
    if not user.organization_id:
        return {"terms": DEFAULT_TERMINOLOGY, "defaults": DEFAULT_TERMINOLOGY}
    row = db.execute(
        select(Setting).where(
            Setting.organization_id == user.organization_id,
            Setting.key == "terminology",
        )
    ).scalar_one_or_none()
    terms = dict(DEFAULT_TERMINOLOGY)
    if row and row.value:
        terms.update({k: v for k, v in (row.value or {}).items() if isinstance(v, str) and v.strip()})
    return {"terms": terms, "defaults": DEFAULT_TERMINOLOGY}


@router.put("/settings/terminology")
def put_terminology(
    body: TerminologyIn,
    user: User = Depends(require_permissions("settings.manage")),
    db: Session = Depends(get_db),
):
    if not user.organization_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No organization context")
    row = db.execute(
        select(Setting).where(
            Setting.organization_id == user.organization_id,
            Setting.key == "terminology",
        )
    ).scalar_one_or_none()
    # Filter to only known keys — new keys are still stored but with best-effort.
    cleaned = {k: v.strip() for k, v in body.terms.items() if isinstance(v, str) and v.strip()}
    if row:
        row.value = cleaned
    else:
        db.add(Setting(
            organization_id=user.organization_id,
            key="terminology",
            value=cleaned,
        ))
    db.commit()
    merged = dict(DEFAULT_TERMINOLOGY)
    merged.update(cleaned)
    return {"terms": merged, "defaults": DEFAULT_TERMINOLOGY}


# ========================================================================== #
# 3) ACADEMIC ENGINE — exam types, attendance statuses, grade bands.
# ========================================================================== #

# ---- Exam Types ---- #

class ExamTypeIn(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    weightage_default: float = 0.0
    max_marks_default: float = 100.0
    is_final: bool = False
    description: str | None = None
    display_order: int = 0
    is_active: bool = True


@router.get("/config/exam-types")
def list_exam_types(user: CurrentUser, db: Session = Depends(get_db)):
    if not user.organization_id:
        return []
    rows = db.execute(
        select(ExamType).where(ExamType.organization_id == user.organization_id).order_by(ExamType.display_order, ExamType.code)
    ).scalars().all()
    return [_serialize_exam_type(r) for r in rows]


@router.post("/config/exam-types", status_code=status.HTTP_201_CREATED)
def create_exam_type(
    body: ExamTypeIn,
    user: User = Depends(require_permissions("academic.manage")),
    db: Session = Depends(get_db),
):
    row = ExamType(organization_id=user.organization_id, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_exam_type(row)


@router.patch("/config/exam-types/{row_id}")
def update_exam_type(
    row_id: str,
    body: ExamTypeIn,
    user: User = Depends(require_permissions("academic.manage")),
    db: Session = Depends(get_db),
):
    row = db.get(ExamType, row_id)
    if not row or (not user.is_super_admin and row.organization_id != user.organization_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _serialize_exam_type(row)


@router.delete("/config/exam-types/{row_id}")
def delete_exam_type(
    row_id: str,
    user: User = Depends(require_permissions("academic.manage")),
    db: Session = Depends(get_db),
):
    row = db.get(ExamType, row_id)
    if not row or (not user.is_super_admin and row.organization_id != user.organization_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


def _serialize_exam_type(r: ExamType) -> dict:
    return {
        "id": r.id, "code": r.code, "name": r.name,
        "weightage_default": r.weightage_default, "max_marks_default": r.max_marks_default,
        "is_final": r.is_final, "description": r.description,
        "display_order": r.display_order, "is_active": r.is_active,
    }


# ---- Attendance Statuses ---- #

class AttendanceStatusIn(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    label: str = Field(min_length=1, max_length=80)
    counts_as_present: bool = False
    is_leave: bool = False
    color: str | None = None
    display_order: int = 0
    is_active: bool = True


@router.get("/config/attendance-statuses")
def list_att_statuses(user: CurrentUser, db: Session = Depends(get_db)):
    if not user.organization_id:
        return []
    rows = db.execute(
        select(AttendanceStatusConfig).where(AttendanceStatusConfig.organization_id == user.organization_id).order_by(AttendanceStatusConfig.display_order, AttendanceStatusConfig.code)
    ).scalars().all()
    return [_serialize_att_status(r) for r in rows]


@router.post("/config/attendance-statuses", status_code=status.HTTP_201_CREATED)
def create_att_status(
    body: AttendanceStatusIn,
    user: User = Depends(require_permissions("academic.manage")),
    db: Session = Depends(get_db),
):
    row = AttendanceStatusConfig(organization_id=user.organization_id, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_att_status(row)


@router.patch("/config/attendance-statuses/{row_id}")
def update_att_status(
    row_id: str,
    body: AttendanceStatusIn,
    user: User = Depends(require_permissions("academic.manage")),
    db: Session = Depends(get_db),
):
    row = db.get(AttendanceStatusConfig, row_id)
    if not row or (not user.is_super_admin and row.organization_id != user.organization_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _serialize_att_status(row)


@router.delete("/config/attendance-statuses/{row_id}")
def delete_att_status(
    row_id: str,
    user: User = Depends(require_permissions("academic.manage")),
    db: Session = Depends(get_db),
):
    row = db.get(AttendanceStatusConfig, row_id)
    if not row or (not user.is_super_admin and row.organization_id != user.organization_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


def _serialize_att_status(r: AttendanceStatusConfig) -> dict:
    return {
        "id": r.id, "code": r.code, "label": r.label,
        "counts_as_present": r.counts_as_present, "is_leave": r.is_leave,
        "color": r.color, "display_order": r.display_order, "is_active": r.is_active,
    }


# ---- Grade Bands ---- #

class GradeBandIn(BaseModel):
    min_percent: float = Field(ge=0, le=100)
    max_percent: float = Field(ge=0, le=100)
    grade: str = Field(min_length=1, max_length=10)
    grade_point: float = 0.0
    description: str | None = None
    display_order: int = 0
    is_active: bool = True


@router.get("/config/grade-bands")
def list_grade_bands(user: CurrentUser, db: Session = Depends(get_db)):
    if not user.organization_id:
        return []
    rows = db.execute(
        select(GradeBand).where(GradeBand.organization_id == user.organization_id).order_by(GradeBand.min_percent.desc())
    ).scalars().all()
    return [_serialize_grade(r) for r in rows]


@router.post("/config/grade-bands", status_code=status.HTTP_201_CREATED)
def create_grade_band(
    body: GradeBandIn,
    user: User = Depends(require_permissions("academic.manage")),
    db: Session = Depends(get_db),
):
    if body.max_percent < body.min_percent:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "max_percent must be >= min_percent")
    row = GradeBand(organization_id=user.organization_id, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_grade(row)


@router.patch("/config/grade-bands/{row_id}")
def update_grade_band(
    row_id: str,
    body: GradeBandIn,
    user: User = Depends(require_permissions("academic.manage")),
    db: Session = Depends(get_db),
):
    row = db.get(GradeBand, row_id)
    if not row or (not user.is_super_admin and row.organization_id != user.organization_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _serialize_grade(row)


@router.delete("/config/grade-bands/{row_id}")
def delete_grade_band(
    row_id: str,
    user: User = Depends(require_permissions("academic.manage")),
    db: Session = Depends(get_db),
):
    row = db.get(GradeBand, row_id)
    if not row or (not user.is_super_admin and row.organization_id != user.organization_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


def _serialize_grade(r: GradeBand) -> dict:
    return {
        "id": r.id, "min_percent": r.min_percent, "max_percent": r.max_percent,
        "grade": r.grade, "grade_point": r.grade_point, "description": r.description,
        "display_order": r.display_order, "is_active": r.is_active,
    }
