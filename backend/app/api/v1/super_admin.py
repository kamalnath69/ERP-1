"""Super Admin endpoints: manage organizations, view platform-wide health."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_super_admin
from app.models import Organization, OrganizationStatusEnum, Student, Subscription, User
from app.schemas import OrganizationCreate, OrganizationOut, OrganizationUpdate

router = APIRouter(prefix="/super-admin", tags=["super-admin"])


@router.get("/organizations", response_model=list[OrganizationOut])
def list_orgs(user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    return db.execute(select(Organization).order_by(Organization.created_at.desc())).scalars().all()


@router.post("/organizations", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_org(body: OrganizationCreate, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    from app.models import OrganizationTypeEnum
    try:
        ot = OrganizationTypeEnum(body.org_type)
    except ValueError:
        raise HTTPException(400, "Invalid org_type")
    if db.execute(select(Organization).where(Organization.slug == body.slug.lower())).scalar_one_or_none():
        raise HTTPException(409, "Slug exists")
    org = Organization(
        name=body.name,
        slug=body.slug.lower(),
        org_type=ot,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@router.patch("/organizations/{org_id}", response_model=OrganizationOut)
def update_org(org_id: str, body: OrganizationUpdate, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(org, k, v)
    db.commit()
    db.refresh(org)
    return org


@router.post("/organizations/{org_id}/suspend")
def suspend_org(org_id: str, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Not found")
    org.status = OrganizationStatusEnum.suspended
    db.commit()
    return {"ok": True, "status": org.status.value}


@router.post("/organizations/{org_id}/activate")
def activate_org(org_id: str, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Not found")
    org.status = OrganizationStatusEnum.active
    db.commit()
    return {"ok": True, "status": org.status.value}


@router.delete("/organizations/{org_id}")
def delete_org(org_id: str, user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Not found")
    db.delete(org)
    db.commit()
    return {"ok": True}


@router.get("/health")
def platform_health(user: User = Depends(require_super_admin), db: Session = Depends(get_db)):
    total_orgs = db.execute(select(func.count(Organization.id))).scalar()
    active_orgs = db.execute(
        select(func.count(Organization.id)).where(Organization.status == OrganizationStatusEnum.active)
    ).scalar()
    total_users = db.execute(select(func.count(User.id))).scalar()
    total_students = db.execute(select(func.count(Student.id))).scalar()
    plans = db.execute(
        select(Subscription.plan, func.count(Subscription.id)).group_by(Subscription.plan)
    ).all()
    return {
        "total_organizations": total_orgs,
        "active_organizations": active_orgs,
        "total_users": total_users,
        "total_students": total_students,
        "plans": {p: c for p, c in plans},
    }
