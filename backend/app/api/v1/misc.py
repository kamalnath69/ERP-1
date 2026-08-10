"""Feature flag and lightweight system routes."""
import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from jwt import ExpiredSignatureError, InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.deps import require_permissions
from app.core.security import decode_token
from app.models import FeatureFlag, Organization, User
from app.services.realtime import hub

router = APIRouter(tags=["misc"])


def event_tenant(request: Request) -> str:
    """Authenticate SSE without retaining a request-scoped DB session."""
    authorization = request.headers.get("authorization", "")
    bearer_token = authorization[7:] if authorization.lower().startswith("bearer ") else None
    raw_token = bearer_token or request.cookies.get(settings.ACCESS_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Missing authentication session")
    try:
        payload = decode_token(raw_token)
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Wrong token type")

    with SessionLocal() as db:
        user = db.get(User, payload.get("sub"))
        if not user or not user.is_active or payload.get("sv") != user.session_version:
            raise HTTPException(status_code=401, detail="Session is no longer active")
        if not user.organization_id:
            raise HTTPException(status_code=400, detail="No organization context")
        organization = db.get(Organization, user.organization_id)
        if not organization or organization.status.value in {"suspended", "cancelled"}:
            raise HTTPException(status_code=403, detail="Organization is not active")
        return str(user.organization_id)


@router.get("/events")
async def tenant_events(request: Request, tenant_id: Annotated[str, Depends(event_tenant)]):
    async def stream():
        queue = hub.subscribe(tenant_id)
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: invalidate\ndata: {json.dumps({'path': payload['path']})}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            hub.unsubscribe(tenant_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
    })


@router.get("/feature-flags")
def feature_flags(user: User = Depends(require_permissions("settings.manage")), db: Session = Depends(get_db)):
    stmt = select(FeatureFlag).where(FeatureFlag.organization_id == user.organization_id)
    return [{"id": f.id, "flag": f.flag, "enabled": f.enabled} for f in db.execute(stmt).scalars().all()]


@router.post("/feature-flags/{flag_id}/toggle")
def toggle_flag(flag_id: str, user: User = Depends(require_permissions("settings.manage")), db: Session = Depends(get_db)):
    f = db.get(FeatureFlag, flag_id)
    if f and f.organization_id == user.organization_id:
        f.enabled = not f.enabled
        db.commit()
    return {"ok": True, "enabled": f.enabled if f else False}
