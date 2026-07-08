"""Exams and marks endpoints."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import Exam, Mark, User
from app.schemas import ExamCreate, ExamOut, MarksBulkCreate

router = APIRouter(prefix="/marks", tags=["marks"])


@router.get("/exams", response_model=list[ExamOut])
def list_exams(
    subject_id: str | None = None,
    section_id: str | None = None,
    user: User = Depends(require_permissions("marks.view")),
    db: Session = Depends(get_db),
):
    stmt = select(Exam).where(Exam.organization_id == user.organization_id)
    if subject_id:
        stmt = stmt.where(Exam.subject_id == subject_id)
    if section_id:
        stmt = stmt.where(Exam.section_id == section_id)
    return db.execute(stmt.order_by(Exam.created_at.desc())).scalars().all()


@router.post("/exams", response_model=ExamOut, status_code=status.HTTP_201_CREATED)
def create_exam(body: ExamCreate, user: User = Depends(require_permissions("marks.enter")), db: Session = Depends(get_db)):
    payload = body.model_dump()
    if payload.get("exam_date"):
        try:
            payload["exam_date"] = date.fromisoformat(payload["exam_date"])
        except ValueError:
            payload["exam_date"] = None

    # If the tenant has configured an exam_types catalogue, enforce membership.
    from app.models import ExamType
    catalogue = db.execute(
        select(ExamType.code).where(ExamType.organization_id == user.organization_id, ExamType.is_active.is_(True))
    ).scalars().all()
    if catalogue and payload.get("exam_type") not in catalogue:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"exam_type '{payload.get('exam_type')}' is not in this organisation's catalogue: {sorted(catalogue)}. "
            "Add it under Academic Config → Exam Types first.",
        )

    e = Exam(organization_id=user.organization_id, **payload)
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


@router.post("/exams/{exam_id}/publish")
def publish_exam(exam_id: str, user: User = Depends(require_permissions("marks.publish")), db: Session = Depends(get_db)):
    e = db.get(Exam, exam_id)
    if not e or e.organization_id != user.organization_id:
        raise HTTPException(404, "Not found")
    e.is_published = True
    db.commit()
    return {"ok": True}


@router.post("/bulk")
def bulk_marks(body: MarksBulkCreate, user: User = Depends(require_permissions("marks.enter")), db: Session = Depends(get_db)):
    exam = db.get(Exam, body.exam_id)
    if not exam or exam.organization_id != user.organization_id:
        raise HTTPException(404, "Exam not found")

    for entry in body.marks:
        existing = db.execute(
            select(Mark).where(Mark.exam_id == exam.id, Mark.student_id == entry.student_id)
        ).scalar_one_or_none()
        if existing:
            existing.obtained = entry.obtained
            existing.grade = entry.grade
            existing.remarks = entry.remarks
            existing.entered_by_user_id = user.id
        else:
            db.add(
                Mark(
                    organization_id=user.organization_id,
                    exam_id=exam.id,
                    student_id=entry.student_id,
                    obtained=entry.obtained,
                    grade=entry.grade,
                    remarks=entry.remarks,
                    entered_by_user_id=user.id,
                )
            )
    db.commit()
    return {"ok": True, "count": len(body.marks)}


@router.get("/exams/{exam_id}/marks")
def get_exam_marks(exam_id: str, user: User = Depends(require_permissions("marks.view")), db: Session = Depends(get_db)):
    exam = db.get(Exam, exam_id)
    if not exam or exam.organization_id != user.organization_id:
        raise HTTPException(404, "Not found")
    marks = db.execute(select(Mark).where(Mark.exam_id == exam_id)).scalars().all()
    return {
        "exam": ExamOut.model_validate(exam).model_dump(),
        "marks": [
            {
                "id": m.id,
                "student_id": m.student_id,
                "obtained": m.obtained,
                "grade": m.grade,
                "remarks": m.remarks,
            }
            for m in marks
        ],
    }
