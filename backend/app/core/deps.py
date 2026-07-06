"""FastAPI dependencies: DB session, auth, tenant, permissions."""
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models import User

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        payload = decode_token(creds.credentials)
    except ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")

    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    request.state.user = user
    request.state.tenant_id = user.organization_id
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_super_admin(user: CurrentUser) -> User:
    if not user.is_super_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Super admin required")
    return user


def require_tenant(user: CurrentUser) -> User:
    if not user.organization_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No organization context")
    return user


def require_permissions(*codes: str):
    """Dependency factory that ensures user has ALL required permission codes."""
    from app.services.rbac import user_has_permissions

    def _check(
        user: CurrentUser,
        db: Annotated[Session, Depends(get_db)],
    ) -> User:
        if user.is_super_admin:
            return user
        if not user_has_permissions(db, user, list(codes)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {', '.join(codes)}")
        return user

    return _check
