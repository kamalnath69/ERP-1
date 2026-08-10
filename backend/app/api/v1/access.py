"""Atomic RBAC and ABAC configuration with effective-access previews."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.business import serialize
from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import AccessScope, AuditLog, Client, Location, Organization, Permission, Role, RolePermission, User, UserPermissionOverride, UserRole
from app.services.audit import log_action
from app.services.business_access import allowed_client_ids, allowed_location_ids, client_scope_mode, filter_clients
from app.services.entitlements import entitlement_value
from app.services.rbac import get_user_permissions, get_user_roles
from app.services.cursor_pagination import decode_cursor, encode_cursor, page_size

router = APIRouter(prefix="/access", tags=["access-control"])


class LocationAccessBody(BaseModel):
    location_ids: list[str]


class PermissionOverrideBody(BaseModel):
    permission_id: str
    granted: bool


class UserAccessConfiguration(BaseModel):
    role_ids: list[str] = Field(default_factory=list)
    permission_overrides: list[PermissionOverrideBody] = Field(default_factory=list)
    location_mode: str = Field(pattern="^(full|restricted)$")
    location_ids: list[str] = Field(default_factory=list)
    client_mode: str = Field(pattern="^(all|assigned|selected)$")
    client_ids: list[str] = Field(default_factory=list)
    version: int | None = Field(default=None, ge=1)


def target_user(db, actor, user_id):
    row = db.get(User, user_id)
    if not row or row.organization_id != actor.organization_id: raise HTTPException(404, "User not found")
    return row


def _configuration_preview(db: Session, actor: User, target: User, body: UserAccessConfiguration) -> dict:
    valid_roles = db.execute(select(Role).where(
        Role.organization_id == actor.organization_id,
        Role.id.in_(body.role_ids),
        Role.is_active.is_(True),
    )).scalars().all() if body.role_ids else []
    if {row.id for row in valid_roles} != set(body.role_ids):
        raise HTTPException(422, "One or more roles are invalid or inactive")

    actor_permissions = get_user_permissions(db, actor)
    role_permission_rows = db.execute(
        select(Permission.id, Permission.code, Permission.label, Permission.module)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id.in_(body.role_ids))
    ).all() if body.role_ids else []
    role_codes = {row.code for row in role_permission_rows}
    if not role_codes.issubset(actor_permissions):
        raise HTTPException(403, "Cannot assign capabilities you do not have")

    valid_locations = set(db.execute(select(Location.id).where(
        Location.organization_id == actor.organization_id,
        Location.id.in_(body.location_ids),
        Location.is_active.is_(True),
    )).scalars()) if body.location_ids else set()
    if valid_locations != set(body.location_ids):
        raise HTTPException(422, "One or more locations are invalid")
    if body.location_mode == "restricted" and not valid_locations:
        raise HTTPException(422, "Choose at least one location for restricted access")
    actor_locations = allowed_location_ids(db, actor)
    if actor_locations is not None and (body.location_mode == "full" or not valid_locations.issubset(actor_locations)):
        raise HTTPException(403, "Cannot grant locations outside your own access")

    actor_client_mode = client_scope_mode(db, actor)
    actor_clients = allowed_client_ids(db, actor)
    if actor_client_mode != "all" and body.client_mode != "selected":
        raise HTTPException(403, "Scoped administrators can only grant a selected subset of their clients")
    client_stmt = filter_clients(
        select(Client.id).where(Client.organization_id == actor.organization_id, Client.id.in_(body.client_ids)),
        db,
        actor,
    )
    valid_clients = set(db.execute(client_stmt).scalars()) if body.client_ids else set()
    if body.client_mode == "selected" and valid_clients != set(body.client_ids):
        raise HTTPException(422, "One or more selected clients are outside your access")
    if body.client_mode == "selected" and not valid_clients:
        raise HTTPException(422, "Choose at least one client for selected access")
    if actor_clients is not None and body.client_mode == "selected" and not valid_clients.issubset(actor_clients):
        raise HTTPException(403, "Cannot grant clients outside your own access")

    override_ids = [item.permission_id for item in body.permission_overrides]
    if len(override_ids) != len(set(override_ids)):
        raise HTTPException(422, "Each permission may only have one personal adjustment")
    permission_rows = db.execute(select(Permission).where(
        Permission.id.in_(override_ids),
        or_(Permission.organization_id.is_(None), Permission.organization_id == actor.organization_id),
    )).scalars().all() if override_ids else []
    if {row.id for row in permission_rows} != set(override_ids):
        raise HTTPException(422, "One or more permission overrides are invalid")
    permission_by_id = {row.id: row for row in permission_rows}
    for item in body.permission_overrides:
        if item.granted and permission_by_id[item.permission_id].code not in actor_permissions:
            raise HTTPException(403, "Cannot grant a personal capability you do not have")

    effective_codes = set(role_codes)
    for item in body.permission_overrides:
        code = permission_by_id[item.permission_id].code
        if item.granted:
            effective_codes.add(code)
        else:
            effective_codes.discard(code)
    effective_rows = db.execute(select(Permission).where(Permission.code.in_(effective_codes)).order_by(Permission.module, Permission.label)).scalars().all() if effective_codes else []
    warnings = []
    if not body.role_ids:
        warnings.append("No role is selected, so only personal allowances will apply.")
    if "dashboard.view" not in effective_codes:
        warnings.append("This person will not be able to open the business workspace.")
    if "clients.view" not in effective_codes and any(code.startswith("clients.") or code.startswith("gym.") for code in effective_codes):
        warnings.append("Some selected work needs Client access, but Client viewing is blocked.")
    return {
        "roles": [{"id": row.id, "name": row.name, "slug": row.slug} for row in valid_roles],
        "effective_permissions": [{"id": row.id, "code": row.code, "label": row.label, "module": row.module} for row in effective_rows],
        "location_scope": {
            "mode": body.location_mode,
            "count": None if body.location_mode == "full" else len(valid_locations),
        },
        "client_scope": {
            "mode": body.client_mode,
            "count": len(valid_clients) if body.client_mode == "selected" else None,
        },
        "warnings": warnings,
    }


@router.get("/workspace")
def workspace(include_directories: bool = True, actor=Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    actor_permission_codes = get_user_permissions(db, actor)
    permissions = db.execute(select(Permission).where(
        or_(Permission.organization_id.is_(None), Permission.organization_id == actor.organization_id),
        Permission.code.in_(actor_permission_codes),
    ).order_by(Permission.module, Permission.label)).scalars().all()
    roles = db.execute(select(Role).where(Role.organization_id == actor.organization_id).order_by(Role.is_system.desc(), Role.name)).scalars().all()
    role_permissions = db.execute(select(RolePermission.role_id, RolePermission.permission_id).where(
        RolePermission.role_id.in_([row.id for row in roles])
    )).all() if roles else []
    role_users = db.execute(select(UserRole.role_id, func.count(UserRole.user_id)).where(
        UserRole.role_id.in_([row.id for row in roles])
    ).group_by(UserRole.role_id)).all() if roles else []
    permission_ids: dict[str, list[str]] = {row.id: [] for row in roles}
    for role_id, permission_id in role_permissions:
        permission_ids.setdefault(role_id, []).append(permission_id)
    user_counts = dict(role_users)

    users = db.execute(select(User).where(User.organization_id == actor.organization_id).order_by(User.first_name, User.last_name)).scalars().all() if include_directories else []
    user_role_rows = db.execute(select(UserRole.user_id, Role.id, Role.name).join(Role, Role.id == UserRole.role_id).where(
        UserRole.user_id.in_([row.id for row in users])
    )).all() if users else []
    roles_by_user: dict[str, list[dict]] = {row.id: [] for row in users}
    for user_id, role_id, role_name in user_role_rows:
        roles_by_user.setdefault(user_id, []).append({"id": role_id, "name": role_name})

    locations = db.execute(select(Location).where(
        Location.organization_id == actor.organization_id, Location.is_active.is_(True),
    ).order_by(Location.name)).scalars().all()
    clients = db.execute(filter_clients(select(Client).where(
        Client.organization_id == actor.organization_id,
    ).order_by(Client.first_name, Client.last_name).limit(250), db, actor)).scalars().all() if include_directories else []
    return {
        "roles": [{
            **serialize(row),
            "permission_ids": permission_ids.get(row.id, []),
            "user_count": int(user_counts.get(row.id, 0)),
        } for row in roles],
        "permissions": [serialize(row) for row in permissions],
        "users": [{
            "id": row.id, "first_name": row.first_name, "last_name": row.last_name,
            "email": row.email, "is_active": row.is_active, "access_version": row.access_version,
            "roles": roles_by_user.get(row.id, []),
        } for row in users],
        "locations": [serialize(row) for row in locations],
        "clients": [{
            "id": row.id, "first_name": row.first_name, "last_name": row.last_name,
            "phone": row.phone, "client_number": row.client_number,
        } for row in clients],
        "capabilities": {
            "create_custom_roles": bool(entitlement_value(db, db.get(Organization, actor.organization_id), "access.custom_roles", False)),
            "edit_system_roles": False,
            "view_audit": "settings.audit.view" in actor_permission_codes,
        },
    }


@router.get("/users/page")
def access_users_page(
    q: str | None = Query(default=None, max_length=100),
    account_status: str = Query(default="all", alias="status", pattern="^(all|active|inactive)$"),
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    actor=Depends(require_permissions("roles.manage")),
    db: Session = Depends(get_db),
):
    normalized_query = " ".join((q or "").casefold().split())
    filters = {"q": normalized_query, "status": account_status}
    values = decode_cursor(cursor, scope="access.users", organization_id=actor.organization_id, filters=filters)
    statement = select(User).where(User.organization_id == actor.organization_id)
    if account_status != "all":
        statement = statement.where(User.is_active.is_(account_status == "active"))
    if normalized_query:
        term = f"%{normalized_query}%"
        role_match = select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(
            UserRole.user_id == User.id,
            func.lower(Role.name).like(term),
        ).exists()
        statement = statement.where(or_(
            func.lower(User.first_name).like(term),
            func.lower(User.last_name).like(term),
            func.lower(User.email).like(term),
            role_match,
        ))
    first_key = func.lower(User.first_name)
    last_key = func.lower(User.last_name)
    if values:
        first = str(values["first"])
        last = str(values["last"])
        identifier = str(values["id"])
        statement = statement.where(or_(
            first_key > first,
            and_(first_key == first, last_key > last),
            and_(first_key == first, last_key == last, User.id > identifier),
        ))
    size = page_size(limit)
    rows = list(db.execute(statement.order_by(first_key, last_key, User.id).limit(size + 1)).scalars())
    has_more = len(rows) > size
    rows = rows[:size]
    role_rows = db.execute(select(UserRole.user_id, Role.id, Role.name).join(
        Role, Role.id == UserRole.role_id,
    ).where(UserRole.user_id.in_([row.id for row in rows]))).all() if rows else []
    roles_by_user: dict[str, list[dict]] = {row.id: [] for row in rows}
    for user_id, role_id, role_name in role_rows:
        roles_by_user.setdefault(user_id, []).append({"id": role_id, "name": role_name})
    next_cursor = encode_cursor(
        scope="access.users",
        organization_id=actor.organization_id,
        filters=filters,
        values={"first": rows[-1].first_name.casefold(), "last": rows[-1].last_name.casefold(), "id": rows[-1].id},
    ) if has_more and rows else None
    summary = db.execute(select(
        func.count(User.id),
        func.count(User.id).filter(User.is_active.is_(True)),
    ).where(User.organization_id == actor.organization_id)).one()
    return {
        "items": [{
            "id": row.id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "email": row.email,
            "is_active": row.is_active,
            "access_version": row.access_version,
            "roles": roles_by_user.get(row.id, []),
        } for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "summary": {"total": int(summary[0] or 0), "active": int(summary[1] or 0)},
    }


@router.get("/clients/page")
def access_clients_page(
    q: str | None = Query(default=None, max_length=100),
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    actor=Depends(require_permissions("roles.manage")),
    db: Session = Depends(get_db),
):
    normalized_query = " ".join((q or "").casefold().split())
    filters = {"q": normalized_query}
    values = decode_cursor(cursor, scope="access.clients", organization_id=actor.organization_id, filters=filters)
    statement = filter_clients(select(Client).where(Client.organization_id == actor.organization_id), db, actor)
    if normalized_query:
        term = f"%{normalized_query}%"
        statement = statement.where(or_(
            func.lower(Client.first_name).like(term),
            func.lower(Client.last_name).like(term),
            func.lower(func.coalesce(Client.phone, "")).like(term),
            func.lower(Client.client_number).like(term),
        ))
    first_key = func.lower(Client.first_name)
    last_key = func.lower(Client.last_name)
    if values:
        first = str(values["first"])
        last = str(values["last"])
        identifier = str(values["id"])
        statement = statement.where(or_(
            first_key > first,
            and_(first_key == first, last_key > last),
            and_(first_key == first, last_key == last, Client.id > identifier),
        ))
    size = page_size(limit)
    rows = list(db.execute(statement.order_by(first_key, last_key, Client.id).limit(size + 1)).scalars())
    has_more = len(rows) > size
    rows = rows[:size]
    next_cursor = encode_cursor(
        scope="access.clients",
        organization_id=actor.organization_id,
        filters=filters,
        values={"first": rows[-1].first_name.casefold(), "last": rows[-1].last_name.casefold(), "id": rows[-1].id},
    ) if has_more and rows else None
    return {
        "items": [{
            "id": row.id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "phone": row.phone,
            "client_number": row.client_number,
        } for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.get("/audit")
def access_audit(limit: int = 100, actor=Depends(require_permissions("settings.audit.view")), db: Session = Depends(get_db)):
    rows = db.execute(select(AuditLog).where(
        AuditLog.organization_id == actor.organization_id,
        or_(AuditLog.action.like("access.%"), AuditLog.action.like("role.%")),
    ).order_by(AuditLog.created_at.desc()).limit(min(max(limit, 1), 200))).scalars().all()
    user_ids = {row.user_id for row in rows if row.user_id}
    users = {row.id: row for row in db.execute(select(User).where(User.id.in_(user_ids))).scalars()} if user_ids else {}
    return [{
        "id": row.id,
        "action": row.action,
        "actor": f"{users[row.user_id].first_name} {users[row.user_id].last_name}".strip() if row.user_id in users else "System",
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "summary": (row.meta or {}).get("summary"),
        "created_at": row.created_at,
    } for row in rows]


@router.get("/audit/page")
def access_audit_page(
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    actor=Depends(require_permissions("settings.audit.view")),
    db: Session = Depends(get_db),
):
    values = decode_cursor(cursor, scope="access.audit", organization_id=actor.organization_id)
    statement = select(AuditLog).where(
        AuditLog.organization_id == actor.organization_id,
        or_(AuditLog.action.like("access.%"), AuditLog.action.like("role.%")),
    )
    if values:
        pivot_at = datetime.fromisoformat(str(values["at"]))
        statement = statement.where(or_(
            AuditLog.created_at < pivot_at,
            and_(AuditLog.created_at == pivot_at, AuditLog.id < str(values["id"])),
        ))
    size = page_size(limit, default=50)
    rows = list(db.execute(statement.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(size + 1)).scalars())
    has_more = len(rows) > size
    rows = rows[:size]
    user_ids = {row.user_id for row in rows if row.user_id}
    users = {row.id: row for row in db.execute(select(User).where(User.id.in_(user_ids))).scalars()} if user_ids else {}
    next_cursor = encode_cursor(
        scope="access.audit",
        organization_id=actor.organization_id,
        values={"at": rows[-1].created_at.isoformat(), "id": rows[-1].id},
    ) if has_more and rows else None
    return {
        "items": [{
            "id": row.id,
            "action": row.action,
            "actor": f"{users[row.user_id].first_name} {users[row.user_id].last_name}".strip() if row.user_id in users else "System",
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "summary": (row.meta or {}).get("summary"),
            "created_at": row.created_at,
        } for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.get("/catalog")
def catalog(actor=Depends(require_permissions("users.view")), db: Session = Depends(get_db)):
    rows = db.execute(select(Location).where(Location.organization_id == actor.organization_id, Location.is_active.is_(True)).order_by(Location.name)).scalars()
    return {"scope_type": "location", "locations": [serialize(row) for row in rows]}


@router.get("/users/{user_id}")
def get_access(user_id: str, actor=Depends(require_permissions("users.view")), db: Session = Depends(get_db)):
    target = target_user(db, actor, user_id); allowed = allowed_location_ids(db, target)
    locations = db.execute(select(Location).where(Location.organization_id == actor.organization_id, Location.is_active.is_(True))).scalars().all()
    return {
        "mode": "full" if allowed is None else "restricted", "location_ids": [x.id for x in locations] if allowed is None else sorted(allowed),
        "locations": [serialize(x) for x in locations if allowed is None or x.id in allowed],
        "roles": [{"id": x.id, "name": x.name, "slug": x.slug} for x in get_user_roles(db, target)],
        "permissions": sorted(get_user_permissions(db, target)),
    }


@router.put("/users/{user_id}")
def set_access(user_id: str, body: LocationAccessBody, actor=Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    target = target_user(db, actor, user_id)
    if target.id == actor.id: raise HTTPException(409, "Another owner must change your own location boundary")
    valid = set(db.execute(select(Location.id).where(Location.organization_id == actor.organization_id, Location.id.in_(body.location_ids), Location.is_active.is_(True))).scalars())
    if valid != set(body.location_ids): raise HTTPException(422, "One or more locations are invalid")
    actor_allowed = allowed_location_ids(db, actor)
    if actor_allowed is not None and not valid.issubset(actor_allowed): raise HTTPException(403, "Cannot grant a location outside your own access")
    db.execute(delete(AccessScope).where(AccessScope.organization_id == actor.organization_id, AccessScope.user_id == target.id, AccessScope.scope_type == "location"))
    for location_id in valid:
        db.add(AccessScope(organization_id=actor.organization_id, user_id=target.id, scope_type="location", scope_value=location_id, meta={}))
    target.access_version += 1
    log_action(db, organization_id=actor.organization_id, user_id=actor.id, action="access.location_scope_updated", resource_type="user", resource_id=target.id, permission="roles.manage", meta={"summary": f"Location access updated for {target.first_name} {target.last_name}".strip(), "location_count": len(valid)})
    db.commit(); return get_access(user_id, actor, db)


@router.get("/users/{user_id}/configuration")
def get_configuration(user_id: str, actor=Depends(require_permissions("users.view")), db: Session = Depends(get_db)):
    target = target_user(db, actor, user_id)
    roles = get_user_roles(db, target)
    overrides = db.execute(select(UserPermissionOverride).where(UserPermissionOverride.user_id == target.id)).scalars().all()
    location_ids = allowed_location_ids(db, target)
    client_ids = allowed_client_ids(db, target)
    mode = client_scope_mode(db, target)
    selected_client_ids = sorted(client_ids) if client_ids is not None and mode == "selected" else []
    selected_clients = db.execute(filter_clients(select(Client).where(
        Client.organization_id == actor.organization_id,
        Client.id.in_(selected_client_ids),
    ), db, actor)).scalars().all() if selected_client_ids else []
    return {
        "user": {"id": target.id, "first_name": target.first_name, "last_name": target.last_name, "email": target.email},
        "role_ids": [role.id for role in roles],
        "permission_overrides": [{"permission_id": row.permission_id, "granted": row.granted} for row in overrides],
        "location_mode": "full" if location_ids is None else "restricted",
        "location_ids": [] if location_ids is None else sorted(location_ids),
        "client_mode": mode,
        "client_ids": selected_client_ids,
        "selected_clients": [{
            "id": row.id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "phone": row.phone,
            "client_number": row.client_number,
        } for row in selected_clients],
        "effective_permissions": sorted(get_user_permissions(db, target)),
        "version": target.access_version,
    }


@router.post("/users/{user_id}/preview")
def preview_configuration(user_id: str, body: UserAccessConfiguration, actor=Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    target = target_user(db, actor, user_id)
    if target.id == actor.id:
        raise HTTPException(409, "Another owner must review changes to your own effective access")
    return _configuration_preview(db, actor, target, body)


@router.put("/users/{user_id}/configuration")
def save_configuration(user_id: str, body: UserAccessConfiguration, actor=Depends(require_permissions("roles.manage")), db: Session = Depends(get_db)):
    target = target_user(db, actor, user_id)
    if target.id == actor.id:
        raise HTTPException(409, "Another owner must change your own effective access")
    if body.version is not None and body.version != target.access_version:
        raise HTTPException(409, "This person's access changed on another screen. Refresh before saving.")
    preview = _configuration_preview(db, actor, target, body)

    current_owner = any(role.slug == "owner" for role in get_user_roles(db, target))
    next_owner = any(role["slug"] == "owner" for role in preview["roles"])
    if current_owner and not next_owner:
        owner_role = db.execute(select(Role).where(Role.organization_id == actor.organization_id, Role.slug == "owner")).scalar_one_or_none()
        owners = set(db.execute(select(UserRole.user_id).where(UserRole.role_id == owner_role.id)).scalars()) if owner_role else set()
        if len(owners) <= 1:
            raise HTTPException(409, "The final owner cannot be removed")

    db.query(UserRole).filter(UserRole.user_id == target.id).delete()
    for role_id in body.role_ids:
        db.add(UserRole(user_id=target.id, role_id=role_id))
    db.query(UserPermissionOverride).filter(UserPermissionOverride.user_id == target.id).delete()
    for item in body.permission_overrides:
        db.add(UserPermissionOverride(user_id=target.id, permission_id=item.permission_id, granted=item.granted))
    db.execute(delete(AccessScope).where(AccessScope.organization_id == actor.organization_id, AccessScope.user_id == target.id, AccessScope.scope_type.in_(["location", "location_mode", "client", "client_mode"])))
    db.add(AccessScope(organization_id=actor.organization_id, user_id=target.id, scope_type="location_mode", scope_value=body.location_mode, meta={}))
    if body.location_mode == "restricted":
        for location_id in body.location_ids:
            db.add(AccessScope(organization_id=actor.organization_id, user_id=target.id, scope_type="location", scope_value=location_id, meta={}))
    db.add(AccessScope(organization_id=actor.organization_id, user_id=target.id, scope_type="client_mode", scope_value=body.client_mode, meta={}))
    if body.client_mode == "selected":
        for client_id in body.client_ids:
            db.add(AccessScope(organization_id=actor.organization_id, user_id=target.id, scope_type="client", scope_value=client_id, meta={}))
    target.access_version += 1
    log_action(
        db,
        organization_id=actor.organization_id,
        user_id=actor.id,
        action="access.configuration_updated",
        resource_type="user",
        resource_id=target.id,
        permission="roles.manage",
        meta={
            "summary": f"Access updated for {target.first_name} {target.last_name}".strip(),
            "role_count": len(body.role_ids),
            "permission_count": len(preview["effective_permissions"]),
            "location_mode": body.location_mode,
            "client_mode": body.client_mode,
        },
    )
    db.commit()
    return get_configuration(user_id, actor, db)
