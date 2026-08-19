"""Integration coverage for shared, gym, and clinic workflows."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import object_session

from app.core.database import SessionLocal
from app.core.config import settings
from app.models import (
    AIUsage, AIWallet, AuditLog, ChatConversation, ChatMessage, ChatTurn, Client,
    LegalDocument, Organization, Permission, PlanDefinition, PlanVersion, Role, RolePermission,
    Subscription, User, UserPermissionOverride, UserRole, WalletReservation,
)
from app.services.rbac import get_user_permissions
from conftest import delete_signup_challenge, verified_signup_body
from server import app


client = TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def organizations():
    created = []
    yield created
    if created:
        with SessionLocal() as db:
            db.execute(delete(Organization).where(Organization.id.in_(created)))
            db.commit()


def register(created, industry):
    unique = uuid4().hex[:10]
    body, challenge_id = verified_signup_body(client, {
        "organization_name": f"Test {industry.title()} {unique}",
        "organization_slug": f"test-{industry}-{unique}",
        "industry": industry,
        "admin_email": f"owner-{unique}@example.com",
        "admin_password": "Testing@123",
        "admin_first_name": "Test",
        "admin_last_name": "Owner",
        "location_name": "Main Location",
        "city": "Chennai",
    })
    try:
        response = client.post("/api/auth/register", json=body)
    finally:
        delete_signup_challenge(challenge_id)
    assert response.status_code == 201, response.text
    login = client.post("/api/auth/login", json={
        "email": f"owner-{unique}@example.com", "password": "Testing@123",
        "org_slug": f"test-{industry}-{unique}",
    })
    assert login.status_code == 200, login.text
    access = login.cookies.get(settings.ACCESS_COOKIE_NAME)
    headers = {"Authorization": f"Bearer {access}"}
    context_response = client.get("/api/organization/context", headers=headers)
    assert context_response.status_code == 200, context_response.text
    context = context_response.json()
    created.append(context["organization"]["id"])
    return headers, context


def post(path, headers, payload, expected=201):
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code == expected, response.text
    return response.json()


def create_client(headers, location_id, name="Asha"):
    return post("/api/clients", headers, {
        "first_name": name,
        "phone": f"90000{uuid4().int % 100000:05d}",
        "home_location_id": location_id,
        "whatsapp_consent": True,
    })


class TestSecureAuthentication:
    def test_business_id_availability_and_password_policy(self):
        candidate = f"available-{uuid4().hex[:10]}"
        available = client.get("/api/auth/organization-id/availability", params={"value": candidate})
        assert available.status_code == 200
        assert available.json() == {
            "value": candidate,
            "available": True,
            "valid": True,
            "message": "Available",
            "suggestions": [],
        }

        invalid = client.get("/api/auth/organization-id/availability", params={"value": "Invalid--ID"})
        assert invalid.status_code == 200
        assert invalid.json()["valid"] is False

        with SessionLocal() as db:
            existing_slug = db.execute(select(Organization.slug).order_by(Organization.created_at)).scalars().first()
        taken = client.get("/api/auth/organization-id/availability", params={"value": existing_slug})
        assert taken.status_code == 200
        assert taken.json()["available"] is False
        assert taken.json()["suggestions"]

        weak_body, challenge_id = verified_signup_body(client, {
            "organization_name": "Weak Password Test",
            "organization_slug": candidate,
            "industry": "gym",
            "admin_email": f"weak-{uuid4().hex[:8]}@example.com",
            "admin_password": "password123",
            "admin_first_name": "Test",
            "admin_last_name": "Owner",
            "location_name": "Main Location",
            "city": "Chennai",
        })
        try:
            weak_password = client.post("/api/auth/register", json=weak_body)
        finally:
            delete_signup_challenge(challenge_id)
        assert weak_password.status_code == 422
        assert "admin_password" in weak_password.json()["error"]["field_errors"]

    def test_owner_email_is_single_workspace_but_staff_email_can_be_reused(self, organizations):
        owner_headers, context = register(organizations, "gym")
        organization_id = context["organization"]["id"]
        location_id = context["locations"][0]["id"]
        roles = client.get("/api/roles", headers=owner_headers).json()
        manager_role = next(role for role in roles if role["slug"] == "manager")
        staff_email = f"shared-staff-{uuid4().hex[:8]}@example.com"
        staff = post("/api/users", owner_headers, {
            "email": staff_email,
            "first_name": "Shared",
            "last_name": "Staff",
            "password": "Testing@123",
            "role_ids": [manager_role["id"]],
            "location_ids": [location_id],
        })
        with SessionLocal() as db:
            db.get(User, staff["id"]).email_verified = True
            owner_email = db.execute(
                select(User.email)
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .where(
                    User.organization_id == organization_id,
                    Role.is_system.is_(True),
                    Role.system_key == "owner",
                )
            ).scalar_one()
            db.commit()

        challenge_ids = []
        try:
            owner_requested = client.post(
                "/api/auth/registration/email/challenges",
                json={"email": owner_email},
            )
            assert owner_requested.status_code == 201, owner_requested.text
            owner_challenge = owner_requested.json()
            challenge_ids.append(owner_challenge["challenge_id"])
            blocked = client.post(
                f"/api/auth/registration/email/challenges/{owner_challenge['challenge_id']}/verify",
                json={
                    "challenge_token": owner_challenge["challenge_token"],
                    "code": owner_challenge["test_code"],
                },
            )
            assert blocked.status_code == 409, blocked.text
            assert "already owns another business" in blocked.json()["detail"]

            staff_requested = client.post(
                "/api/auth/registration/email/challenges",
                json={"email": staff_email},
            )
            assert staff_requested.status_code == 201, staff_requested.text
            staff_challenge = staff_requested.json()
            challenge_ids.append(staff_challenge["challenge_id"])
            allowed = client.post(
                f"/api/auth/registration/email/challenges/{staff_challenge['challenge_id']}/verify",
                json={
                    "challenge_token": staff_challenge["challenge_token"],
                    "code": staff_challenge["test_code"],
                },
            )
            assert allowed.status_code == 200, allowed.text

            second_slug = f"shared-owner-{uuid4().hex[:10]}"
            with SessionLocal() as db:
                legal = {
                    row.document_type: row.id
                    for row in db.execute(select(LegalDocument).where(
                        LegalDocument.status == "published",
                    )).scalars()
                }
            client.cookies.clear()
            second_registration = client.post("/api/auth/register", json={
                "organization_name": "Shared Email Workspace",
                "organization_slug": second_slug,
                "industry": "gym",
                "admin_email": staff_email,
                "admin_password": "Testing@123",
                "admin_first_name": "Shared",
                "admin_last_name": "Owner",
                "location_name": "Main Location",
                "city": "Chennai",
                "legal_acceptance": {
                    "accepted": True,
                    "terms_document_id": legal["terms"],
                    "privacy_document_id": legal["privacy"],
                    "refund_document_id": legal["refund"],
                },
                "email_verification": {
                    "challenge_id": allowed.json()["challenge_id"],
                    "proof": allowed.json()["verification_proof"],
                },
            })
            assert second_registration.status_code == 201, second_registration.text
            with SessionLocal() as db:
                second_organization_id = db.execute(select(Organization.id).where(
                    Organization.slug == second_slug,
                )).scalar_one()
            organizations.append(second_organization_id)

            ambiguous = client.post("/api/auth/login", json={
                "email": staff_email,
                "password": "Testing@123",
            })
            assert ambiguous.status_code == 400, ambiguous.text
            assert "Business ID is required" in ambiguous.json()["detail"]
            assert client.post("/api/auth/login", json={
                "email": staff_email,
                "password": "Testing@123",
                "org_slug": context["organization"]["slug"],
            }).status_code == 200
            assert client.post("/api/auth/login", json={
                "email": staff_email,
                "password": "Testing@123",
                "org_slug": second_slug,
            }).status_code == 200
        finally:
            for challenge_id in challenge_ids:
                delete_signup_challenge(challenge_id)
            client.cookies.clear()

    def test_verification_cookie_csrf_refresh_and_recovery(self, organizations, monkeypatch):
        delivered = {}
        delivery_counts = {}

        def capture_email(recipient, code, purpose, first_name="", **_kwargs):
            delivered[purpose] = {"recipient": recipient, "code": code}
            delivery_counts[purpose] = delivery_counts.get(purpose, 0) + 1
            return True

        monkeypatch.setattr("app.api.v1.auth.send_auth_code_email", capture_email)
        unique = uuid4().hex[:10]
        slug = f"secure-auth-{unique}"
        email = f"secure-{unique}@example.com"
        body, challenge_id = verified_signup_body(client, {
            "organization_name": "Secure Auth Test", "organization_slug": slug,
            "industry": "gym", "admin_email": email, "admin_password": "Testing@123",
            "admin_first_name": "Secure", "admin_last_name": "Owner",
            "location_name": "Main Location", "city": "Chennai",
        })
        try:
            registered = client.post("/api/auth/register", json=body)
        finally:
            delete_signup_challenge(challenge_id)
        assert registered.status_code == 201, registered.text
        assert "access_token" not in registered.json()
        assert registered.json()["user"]["email_verified"] is True
        assert delivered["email_verification"]["recipient"] == email
        assert delivery_counts["email_verification"] == 1
        with SessionLocal() as db:
            org = db.execute(select(Organization).where(Organization.slug == slug)).scalar_one()
            organizations.append(org.id)
            assert db.execute(select(User).where(User.organization_id == org.id)).scalar_one().email_verified is True

        set_cookies = "; ".join(registered.headers.get_list("set-cookie"))
        assert f"{settings.ACCESS_COOKIE_NAME}=" in set_cookies and "HttpOnly" in set_cookies
        assert "SameSite=lax" in set_cookies
        assert client.get("/api/auth/me").status_code == 200
        issued_access = client.cookies.get(settings.ACCESS_COOKIE_NAME)

        rejected_csrf = client.patch("/api/users/me/profile", json={"first_name": "Blocked"})
        assert rejected_csrf.status_code == 403
        csrf = client.cookies.get(settings.CSRF_COOKIE_NAME)
        accepted_csrf = client.patch("/api/users/me/profile", headers={"X-CSRF-Token": csrf}, json={"first_name": "Verified"})
        assert accepted_csrf.status_code == 200, accepted_csrf.text

        old_refresh = client.cookies.get(settings.REFRESH_COOKIE_NAME)
        refreshed = client.post("/api/auth/refresh", headers={"X-CSRF-Token": csrf})
        assert refreshed.status_code == 200, refreshed.text
        assert client.cookies.get(settings.REFRESH_COOKIE_NAME) != old_refresh
        replay = TestClient(app, raise_server_exceptions=True)
        replay.cookies.set(settings.REFRESH_COOKIE_NAME, old_refresh, path="/api/auth")
        replay.cookies.set(settings.CSRF_COOKIE_NAME, client.cookies.get(settings.CSRF_COOKIE_NAME), path="/")
        reused = replay.post("/api/auth/refresh", headers={"X-CSRF-Token": client.cookies.get(settings.CSRF_COOKIE_NAME)})
        assert reused.status_code == 401
        assert "reuse" in reused.json()["detail"].lower()

        forgot = client.post("/api/auth/password/forgot", json={"email": email, "org_slug": slug})
        assert forgot.status_code == 200 and forgot.json()["message"] == "If the account exists, a code has been sent"
        unknown = client.post("/api/auth/password/forgot", json={"email": f"unknown-{unique}@example.com", "org_slug": slug})
        assert unknown.status_code == 200 and unknown.json()["message"] == forgot.json()["message"]
        reset = client.post("/api/auth/password/reset", json={
            "email": email, "org_slug": slug, "code": delivered["password_reset"]["code"],
            "new_password": "NewTesting@456",
        })
        assert reset.status_code == 200, reset.text
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {issued_access}"}).status_code == 401
        assert client.post("/api/auth/login", json={"email": email, "password": "Testing@123", "org_slug": slug}).status_code == 401
        assert client.post("/api/auth/login", json={"email": email, "password": "NewTesting@456", "org_slug": slug}).status_code == 200


class TestSharedPlatform:
    def test_owner_permissions_are_runtime_invariant_and_tenant_isolated(self, organizations):
        _headers_a, context_a = register(organizations, "gym")
        _headers_b, context_b = register(organizations, "salon")
        organization_a = context_a["organization"]["id"]
        organization_b = context_b["organization"]["id"]

        with SessionLocal() as db:
            owner_a = db.execute(select(User).where(User.organization_id == organization_a)).scalar_one()
            owner_b = db.execute(select(User).where(User.organization_id == organization_b)).scalar_one()
            owner_role = db.execute(
                select(Role)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == owner_a.id, Role.system_key == "owner")
            ).scalar_one()
            assert owner_role.is_system is True
            assert {"ai.use", "ai.actions", "clients.media.view"}.issubset(
                get_user_permissions(db, owner_a)
            )

            owner_role.name = "Workspace Principal"
            owner_role.slug = f"workspace-principal-{uuid4().hex[:6]}"
            permission = Permission(
                code=f"future.sensitive.{uuid4().hex}",
                label="Future sensitive capability",
                module="future",
                organization_id=organization_a,
            )
            db.add(permission)
            db.flush()
            assert db.execute(select(RolePermission).where(
                RolePermission.role_id == owner_role.id,
                RolePermission.permission_id == permission.id,
            )).scalar_one_or_none() is None
            db.add(UserPermissionOverride(
                user_id=owner_a.id,
                permission_id=permission.id,
                granted=False,
            ))
            db.flush()

            assert permission.code in get_user_permissions(db, owner_a)
            assert permission.code not in get_user_permissions(db, owner_b)

    def test_owner_billing_and_module_limits_are_not_authorization_errors(
        self, organizations, monkeypatch,
    ):
        headers, context = register(organizations, "gym")
        organization_id = context["organization"]["id"]
        monkeypatch.setattr(settings, "AI_API_KEY", "test-key")

        with SessionLocal() as db:
            wallet = db.execute(select(AIWallet).where(
                AIWallet.organization_id == organization_id,
            )).scalar_one()
            wallet.balance_credits = 0
            wallet.reserved_credits = 0
            wallet.cycle_grant_credits = 0
            wallet.cycle_end = datetime.now(timezone.utc) + timedelta(days=1)
            db.commit()

        exhausted = client.post("/api/ai/chat", headers=headers, json={
            "message": "Analyze current client activity",
            "idempotency_key": f"owner-quota-{uuid4().hex}",
        })
        assert exhausted.status_code == 200, exhausted.text
        assert exhausted.json()["message"]["outcome"] == "quota_exhausted"
        assert exhausted.json()["message"]["scope"]["owner"] is True

        with SessionLocal() as db:
            organization = db.get(Organization, organization_id)
            organization.enabled_modules = [
                module for module in organization.enabled_modules if module != "ai"
            ]
            db.commit()

        unavailable = client.post("/api/ai/chat", headers=headers, json={
            "message": "Analyze current client activity",
            "idempotency_key": f"owner-entitlement-{uuid4().hex}",
        })
        assert unavailable.status_code == 200, unavailable.text
        assert unavailable.json()["message"]["outcome"] == "entitlement_required"

    def test_owner_ai_actions_require_confirmation_and_are_idempotent(self, organizations):
        headers, context = register(organizations, "gym")
        organization_id = context["organization"]["id"]
        with SessionLocal() as db:
            organization = db.get(Organization, organization_id)
            action_plan = db.execute(
                select(PlanVersion).join(PlanDefinition, PlanDefinition.id == PlanVersion.plan_id)
                .where(PlanDefinition.slug == "business", PlanVersion.status == "published")
                .order_by(PlanVersion.version.desc())
            ).scalars().first()
            subscription = db.execute(select(Subscription).where(
                Subscription.organization_id == organization_id,
            )).scalars().first()
            organization.plan = "business"
            subscription.plan = "business"
            subscription.plan_version_id = action_plan.id
            db.commit()
        key = f"owner-action-{uuid4().hex}"
        body = {
            "action_type": "create_task",
            "payload": {"title": "Review placement readiness evidence"},
            "idempotency_key": key,
        }

        prepared = client.post("/api/ai/actions/prepare", headers=headers, json=body)
        assert prepared.status_code == 200, prepared.text
        first = prepared.json()
        assert first["status"] == "pending_confirmation"
        assert first["preview"]["requires_confirmation"] is True

        replay = client.post("/api/ai/actions/prepare", headers=headers, json=body)
        assert replay.status_code == 200, replay.text
        refreshed = replay.json()
        assert refreshed["action_id"] == first["action_id"]
        assert refreshed["confirmation_token"] != first["confirmation_token"]

        stale = client.post(
            f"/api/ai/actions/{first['action_id']}/confirm", headers=headers,
            json={"confirmation_token": first["confirmation_token"]},
        )
        assert stale.status_code == 403

        confirmed = client.post(
            f"/api/ai/actions/{first['action_id']}/confirm", headers=headers,
            json={"confirmation_token": refreshed["confirmation_token"]},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "completed"

        confirmation_replay = client.post(
            f"/api/ai/actions/{first['action_id']}/confirm", headers=headers,
            json={"confirmation_token": refreshed["confirmation_token"]},
        )
        assert confirmation_replay.status_code == 200
        assert confirmation_replay.json()["status"] == "completed"

        undone = client.post(
            f"/api/ai/actions/{first['action_id']}/undo", headers=headers,
        )
        assert undone.status_code == 200, undone.text
        assert undone.json()["status"] == "undone"
        assert client.post(
            f"/api/ai/actions/{first['action_id']}/undo", headers=headers,
        ).status_code == 409

        with SessionLocal() as db:
            assert db.execute(select(AuditLog.id).where(
                AuditLog.organization_id == organization_id,
                AuditLog.action == "ai_action.create_task",
            )).scalar_one_or_none()
            assert db.execute(select(AuditLog.id).where(
                AuditLog.organization_id == organization_id,
                AuditLog.action == "ai_action.undo.create_task",
            )).scalar_one_or_none()

    def test_catalog_and_inventory_use_filter_bound_cursor_pages(self, organizations):
        headers, context = register(organizations, "gym")
        location_id = context["locations"][0]["id"]
        marker = f"Paged {uuid4().hex[:7]}"
        products = []
        for index in range(4):
            product = post("/api/catalog", headers, {
                "name": f"{marker} Item {index + 1}",
                "sku": f"PAGE-{uuid4().hex[:8]}",
                "item_type": "product",
                "price_paise": 10000 + index,
                "cost_paise": 5000,
                "unit": "unit",
                "track_stock": True,
            })
            products.append(product)
            post("/api/inventory/adjust", headers, {
                "location_id": location_id,
                "item_id": product["id"],
                "quantity_delta_milli": (index + 1) * 1000,
                "reason": f"{marker} receipt",
                "batch_number": f"B-{index + 1}" if index < 2 else "",
                "reorder_level_milli": 500,
            })

        first_catalog = client.get("/api/catalog/page", headers=headers, params={"q": marker, "limit": 2})
        assert first_catalog.status_code == 200, first_catalog.text
        first_catalog_page = first_catalog.json()
        assert len(first_catalog_page["items"]) == 2
        assert first_catalog_page["has_more"] is True
        assert first_catalog_page["next_cursor"]
        second_catalog = client.get("/api/catalog/page", headers=headers, params={
            "q": marker,
            "limit": 2,
            "cursor": first_catalog_page["next_cursor"],
        })
        assert second_catalog.status_code == 200, second_catalog.text
        catalog_ids = [row["id"] for row in first_catalog_page["items"] + second_catalog.json()["items"]]
        assert len(catalog_ids) == len(set(catalog_ids)) == 4
        mismatched_catalog = client.get("/api/catalog/page", headers=headers, params={
            "q": f"{marker} changed",
            "cursor": first_catalog_page["next_cursor"],
        })
        assert mismatched_catalog.status_code == 422

        first_levels = client.get("/api/inventory/levels/page", headers=headers, params={
            "location_id": location_id,
            "q": marker,
            "limit": 2,
        })
        assert first_levels.status_code == 200, first_levels.text
        first_level_page = first_levels.json()
        assert len(first_level_page["items"]) == 2
        assert first_level_page["summary"]["stocked_items"] >= 4
        second_levels = client.get("/api/inventory/levels/page", headers=headers, params={
            "location_id": location_id,
            "q": marker,
            "limit": 2,
            "cursor": first_level_page["next_cursor"],
        })
        assert second_levels.status_code == 200, second_levels.text
        level_ids = [row["id"] for row in first_level_page["items"] + second_levels.json()["items"]]
        assert len(level_ids) == len(set(level_ids)) == 4

        batches = client.get("/api/inventory/levels/page", headers=headers, params={
            "location_id": location_id,
            "q": marker,
            "batches_only": True,
        })
        assert batches.status_code == 200, batches.text
        assert {row["batch_number"] for row in batches.json()["items"]} == {"B-1", "B-2"}

        movements = client.get("/api/inventory/movements/page", headers=headers, params={
            "location_id": location_id,
            "q": marker,
            "limit": 2,
        })
        assert movements.status_code == 200, movements.text
        movement_page = movements.json()
        assert len(movement_page["items"]) == 2
        assert movement_page["has_more"] is True
        next_movements = client.get("/api/inventory/movements/page", headers=headers, params={
            "location_id": location_id,
            "q": marker,
            "limit": 2,
            "cursor": movement_page["next_cursor"],
        })
        assert next_movements.status_code == 200, next_movements.text
        movement_ids = [row["id"] for row in movement_page["items"] + next_movements.json()["items"]]
        assert len(movement_ids) == len(set(movement_ids)) == 4

    def test_access_directories_use_scoped_cursor_pages(self, organizations):
        headers, context = register(organizations, "gym")
        organization_id = context["organization"]["id"]
        location_id = context["locations"][0]["id"]
        with SessionLocal() as db:
            db.add_all([
                User(
                    organization_id=organization_id,
                    email=f"access-{index}-{uuid4().hex[:8]}@example.com",
                    hashed_password="not-used",
                    first_name=name,
                    last_name="Pagination",
                    is_active=index != 2,
                    email_verified=True,
                )
                for index, name in enumerate(("Alpha", "Beta", "Gamma"))
            ])
            db.commit()
        for name in ("Access Asha", "Access Bala", "Access Chitra"):
            create_client(headers, location_id, name)

        compact_workspace = client.get(
            "/api/access/workspace",
            headers=headers,
            params={"include_directories": False},
        )
        assert compact_workspace.status_code == 200, compact_workspace.text
        assert compact_workspace.json()["users"] == []
        assert compact_workspace.json()["clients"] == []

        users = client.get("/api/access/users/page", headers=headers, params={"limit": 2})
        assert users.status_code == 200, users.text
        user_page = users.json()
        assert len(user_page["items"]) == 2
        assert user_page["summary"] == {"total": 4, "active": 3}
        assert user_page["has_more"] is True
        more_users = client.get("/api/access/users/page", headers=headers, params={
            "limit": 2,
            "cursor": user_page["next_cursor"],
        })
        assert more_users.status_code == 200, more_users.text
        user_ids = [row["id"] for row in user_page["items"] + more_users.json()["items"]]
        assert len(user_ids) == len(set(user_ids)) == 4
        changed_user_filter = client.get("/api/access/users/page", headers=headers, params={
            "status": "active",
            "cursor": user_page["next_cursor"],
        })
        assert changed_user_filter.status_code == 422

        students = client.get("/api/access/clients/page", headers=headers, params={
            "q": "Access",
            "limit": 2,
        })
        assert students.status_code == 200, students.text
        student_page = students.json()
        assert len(student_page["items"]) == 2
        assert student_page["has_more"] is True
        more_students = client.get("/api/access/clients/page", headers=headers, params={
            "q": "Access",
            "limit": 2,
            "cursor": student_page["next_cursor"],
        })
        assert more_students.status_code == 200, more_students.text
        student_ids = [row["id"] for row in student_page["items"] + more_students.json()["items"]]
        assert len(student_ids) == len(set(student_ids)) == 3

    def test_cancelled_ai_turn_removes_transient_messages(self, organizations, monkeypatch):
        from app.api.v1.ai import _process_chat
        from app.schemas import ChatRequest

        headers, context = register(organizations, "gym")
        organization_id = context["organization"]["id"]
        request_key = f"cancel:{uuid4()}"

        async def cancel_response(*_args, **_kwargs):
            raise asyncio.CancelledError()

        monkeypatch.setattr("app.api.v1.ai.run_assistant_turn", cancel_response)

        with SessionLocal() as db:
            owner = db.execute(select(User).where(User.organization_id == organization_id)).scalar_one()
            body = ChatRequest(
                message="Explain a cross-functional customer retention strategy",
                idempotency_key=request_key,
            )
            with pytest.raises(asyncio.CancelledError):
                asyncio.run(_process_chat(body, owner, db))

        with SessionLocal() as db:
            turn = db.execute(select(ChatTurn).where(
                ChatTurn.organization_id == organization_id,
                ChatTurn.request_key == request_key,
            )).scalar_one()
            assert turn.status == "cancelled"
            assert turn.error_code == "cancelled"
            assert db.scalar(select(func.count(ChatMessage.id)).where(ChatMessage.turn_id == turn.id)) == 1

    def test_ai_stream_owns_session_and_attaches_user(self, organizations, monkeypatch):
        headers, _context = register(organizations, "gym")
        observed = {}

        async def streamed_response(_body, stream_user, stream_db, emit=None):
            observed["attached"] = object_session(stream_user) is stream_db
            if emit:
                await emit("answer_delta", {"text": "Ready"})
            return {
                "conversation_id": "stream-session-test",
                "conversation": {"id": "stream-session-test"},
                "message": {"artifacts": [], "suggestions": [], "evidence": []},
                "credits_used": 0,
                "ai_wallet": {},
            }

        monkeypatch.setattr("app.api.v1.ai._process_chat", streamed_response)
        response = client.post(
            "/api/ai/chat/stream",
            headers=headers,
            json={"message": "Check stream session ownership"},
        )

        assert response.status_code == 200, response.text
        assert observed["attached"] is True
        assert "event: complete" in response.text

    def test_ai_chat_management_personalization_and_feedback(self, organizations):
        headers, context = register(organizations, "gym")
        organization_id = context["organization"]["id"]
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=30)
        with SessionLocal() as db:
            owner = db.execute(select(User).where(User.organization_id == organization_id)).scalar_one()
            recent = ChatConversation(
                organization_id=organization_id, user_id=owner.id,
                title="Recent operations", expires_at=expires_at,
            )
            pinned = ChatConversation(
                organization_id=organization_id, user_id=owner.id,
                title="Pinned renewals", expires_at=expires_at, pinned_at=now,
            )
            archived = ChatConversation(
                organization_id=organization_id, user_id=owner.id,
                title="Closed billing review", expires_at=expires_at, archived_at=now,
            )
            expired = ChatConversation(
                organization_id=organization_id, user_id=owner.id,
                title="Expired private chat", expires_at=now - timedelta(days=1),
            )
            processing = ChatConversation(
                organization_id=organization_id, user_id=owner.id,
                title="Answer in progress", expires_at=expires_at,
            )
            db.add_all([recent, pinned, archived, expired, processing])
            db.flush()
            completed_turn = ChatTurn(
                organization_id=organization_id, conversation_id=archived.id,
                user_id=owner.id, request_key=f"test:{uuid4()}",
                status="completed", completed_at=now,
            )
            processing_turn = ChatTurn(
                organization_id=organization_id, conversation_id=processing.id,
                user_id=owner.id, request_key=f"test:{uuid4()}", status="processing",
            )
            db.add_all([completed_turn, processing_turn])
            db.flush()
            db.add(ChatMessage(
                organization_id=organization_id, conversation_id=archived.id,
                turn_id=completed_turn.id, role="user",
                content="Find the Acme renewal invoice",
            ))
            assistant = ChatMessage(
                organization_id=organization_id, conversation_id=archived.id,
                turn_id=completed_turn.id, role="assistant",
                content="The renewal invoice is ready.",
            )
            db.add(assistant)
            db.commit()
            ids = {
                "recent": recent.id, "pinned": pinned.id, "archived": archived.id,
                "expired": expired.id, "processing": processing.id,
                "assistant": assistant.id,
            }

        active = client.get("/api/ai/conversations", headers=headers)
        assert active.status_code == 200, active.text
        active_ids = [item["id"] for item in active.json()]
        assert active_ids[0] == ids["pinned"]
        assert ids["archived"] not in active_ids
        assert ids["expired"] not in active_ids
        active_page_response = client.get(
            "/api/ai/conversations/page", headers=headers, params={"limit": 2},
        )
        assert active_page_response.status_code == 200, active_page_response.text
        active_page = active_page_response.json()
        assert active_page["items"][0]["id"] == ids["pinned"]
        assert active_page["has_more"] is True
        next_active_response = client.get("/api/ai/conversations/page", headers=headers, params={
            "limit": 2,
            "cursor": active_page["next_cursor"],
        })
        assert next_active_response.status_code == 200, next_active_response.text
        paged_ids = [row["id"] for row in active_page["items"] + next_active_response.json()["items"]]
        assert len(paged_ids) == len(set(paged_ids)) == 3
        changed_conversation_filter = client.get("/api/ai/conversations/page", headers=headers, params={
            "scope": "all",
            "cursor": active_page["next_cursor"],
        })
        assert changed_conversation_filter.status_code == 422
        expired_detail = client.get(
            f"/api/ai/conversations/{ids['expired']}", headers=headers,
        )
        assert expired_detail.status_code == 410

        search = client.get(
            "/api/ai/conversations",
            headers=headers,
            params={"scope": "all", "q": "ACME RENEWAL"},
        )
        assert search.status_code == 200, search.text
        assert [item["id"] for item in search.json()] == [ids["archived"]]

        pinned_response = client.patch(
            f"/api/ai/conversations/{ids['recent']}",
            headers=headers,
            json={"pinned": True},
        )
        assert pinned_response.status_code == 200, pinned_response.text
        assert pinned_response.json()["pinned_at"]
        with SessionLocal() as db:
            assert db.get(ChatConversation, ids["recent"]).expires_at == expires_at

        archived_response = client.patch(
            f"/api/ai/conversations/{ids['recent']}",
            headers=headers,
            json={"archived": True},
        )
        assert archived_response.status_code == 200, archived_response.text
        assert archived_response.json()["archived_at"]
        assert archived_response.json()["pinned_at"] is None
        with SessionLocal() as db:
            assert db.get(ChatConversation, ids["recent"]).expires_at == expires_at

        blocked_stream = client.patch(
            f"/api/ai/conversations/{ids['processing']}",
            headers=headers,
            json={"archived": True},
        )
        assert blocked_stream.status_code == 409

        archived_chat = client.post("/api/ai/chat", headers=headers, json={
            "conversation_id": ids["recent"],
            "message": "Continue this chat",
            "idempotency_key": f"test:{uuid4()}",
        })
        assert archived_chat.status_code == 409
        assert "Restore" in archived_chat.json()["detail"]

        invalid_title = client.patch(
            f"/api/ai/conversations/{ids['archived']}", headers=headers, json={"title": "   "},
        )
        assert invalid_title.status_code == 422
        renamed = client.patch(
            f"/api/ai/conversations/{ids['archived']}", headers=headers,
            json={"title": "  Renewal   decisions  "},
        )
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "Renewal decisions"

        feedback = client.post(
            f"/api/ai/messages/{ids['assistant']}/feedback", headers=headers,
            json={"rating": "not_helpful", "reason": "The linked customer was missing."},
        )
        assert feedback.status_code == 200, feedback.text
        messages = client.get(
            f"/api/ai/conversations/{ids['archived']}/messages", headers=headers,
        )
        assistant_message = next(item for item in messages.json() if item["id"] == ids["assistant"])
        assert assistant_message["feedback_rating"] == "not_helpful"
        latest_message_response = client.get(
            f"/api/ai/conversations/{ids['archived']}/messages/page",
            headers=headers,
            params={"limit": 1},
        )
        assert latest_message_response.status_code == 200, latest_message_response.text
        latest_message_page = latest_message_response.json()
        assert latest_message_page["has_more"] is True
        earlier_message_response = client.get(
            f"/api/ai/conversations/{ids['archived']}/messages/page",
            headers=headers,
            params={"limit": 1, "cursor": latest_message_page["next_cursor"]},
        )
        assert earlier_message_response.status_code == 200, earlier_message_response.text
        message_ids = [
            row["id"]
            for row in latest_message_page["items"] + earlier_message_response.json()["items"]
        ]
        assert len(message_ids) == len(set(message_ids)) == 2
        assert ids["assistant"] in message_ids

        preference = client.put("/api/users/me/preferences/assistant", headers=headers, json={
            "value": {
                "preferred_name": "Kamal", "tone": "direct", "detail": "balanced",
                "formatting": "paragraphs", "custom_instructions": "Lead with the action.",
            },
        })
        assert preference.status_code == 200, preference.text
        version = preference.json()["version"]
        updated = client.put("/api/users/me/preferences/assistant", headers=headers, json={
            "version": version,
            "value": {**preference.json()["value"], "tone": "friendly"},
        })
        assert updated.status_code == 200, updated.text
        conflict = client.put("/api/users/me/preferences/assistant", headers=headers, json={
            "version": version,
            "value": {**preference.json()["value"], "tone": "professional"},
        })
        assert conflict.status_code == 409
        invalid_preference = client.put("/api/users/me/preferences/assistant", headers=headers, json={
            "value": {**preference.json()["value"], "custom_instructions": "x" * 1501},
        })
        assert invalid_preference.status_code == 422

        other_headers, _ = register(organizations, "salon")
        isolated = client.get(
            f"/api/ai/conversations/{ids['archived']}/messages", headers=other_headers,
        )
        assert isolated.status_code == 404
        other_search = client.get(
            "/api/ai/conversations", headers=other_headers,
            params={"scope": "all", "q": "Renewal decisions"},
        )
        assert other_search.status_code == 200
        assert other_search.json() == []

        with SessionLocal() as db:
            relevant_logs = db.execute(select(AuditLog).where(
                AuditLog.organization_id == organization_id,
                AuditLog.action.in_(["ai.conversation.update", "user.preference.update"]),
            )).scalars().all()
            logged_meta = " ".join(str(row.meta) for row in relevant_logs)
            assert "Renewal decisions" not in logged_meta
            assert "Lead with the action" not in logged_meta

    def test_settings_audit_filters_operations_and_logs_location_creation(self, organizations):
        headers, context = register(organizations, "gym")
        organization_id = context["organization"]["id"]
        with SessionLocal() as db:
            organization = db.get(Organization, organization_id)
            owner = db.execute(select(User).where(User.organization_id == organization_id)).scalar_one()
            growth = db.execute(
                select(PlanVersion).join(PlanDefinition, PlanDefinition.id == PlanVersion.plan_id)
                .where(PlanDefinition.slug == "growth", PlanVersion.status == "published")
                .order_by(PlanVersion.version.desc())
            ).scalars().first()
            subscription = db.execute(select(Subscription).where(Subscription.organization_id == organization_id)).scalars().first()
            organization.plan = "growth"
            subscription.plan = "growth"
            subscription.plan_version_id = growth.id
            db.add(AuditLog(
                organization_id=organization_id,
                user_id=owner.id,
                action="sale.create",
                resource_type="sale_invoice",
                resource_id=str(uuid4()),
            ))
            db.commit()

        branch = post("/api/locations", headers, {
            "name": "Settings Audit Branch",
            "code": f"SA{uuid4().hex[:4].upper()}",
            "city": "Chennai",
        })
        workspace = client.get("/api/settings/workspace", headers=headers)

        assert workspace.status_code == 200, workspace.text
        events = workspace.json()["audit"]
        actions = {event["action"] for event in events}
        assert "location.create" in actions
        assert "sale.create" not in actions
        assert any(event["resource_type"] == "location" for event in events if event["action"] == "location.create")
        assert branch["name"] == "Settings Audit Branch"

    def test_ai_active_client_list_matches_summary_count(self, organizations):
        from app.ai.access import resolve_access_envelope
        from app.ai.catalog import catalog_for
        from app.ai.contracts import FilterOperator, QueryFilter, QueryGoal, SemanticQuery
        from app.ai.execution import execute_semantic_query

        headers, context = register(organizations, "gym")
        location_id = context["locations"][0]["id"]
        created = [create_client(headers, location_id, f"Client {index}") for index in range(7)]
        other_headers, other_context = register(organizations, "gym")
        other_location_id = other_context["locations"][0]["id"]
        for index in range(3):
            create_client(other_headers, other_location_id, f"Other Tenant {index}")

        with SessionLocal() as db:
            inactive = db.get(Client, created[-1]["id"])
            inactive.status = "inactive"
            db.commit()
            owner = db.execute(select(User).where(User.organization_id == context["organization"]["id"])).scalar_one()

            envelope = resolve_access_envelope(db, owner)
            catalog = catalog_for(envelope.industry)
            active_query = SemanticQuery(
                goal=QueryGoal.LIST, entity="client",
                fields=["id", "name", "status"],
                filters=[QueryFilter(field="status", operator=FilterOperator.EQ, value="active")],
                limit=5,
            )
            all_query = active_query.model_copy(update={"filters": [], "limit": 25})
            records = execute_semantic_query(db, owner, active_query, catalog, envelope)
            all_records = execute_semantic_query(db, owner, all_query, catalog, envelope)

        active_artifact = records.artifacts[0]
        all_artifact = all_records.artifacts[0]
        assert active_artifact.data["total"] == 6
        assert len(active_artifact.data["items"]) == 5
        assert active_artifact.data["has_more"] is True
        assert all_artifact.data["total"] == 7

    def test_entity_resolution_handles_spacing_phone_and_ambiguity(self, organizations):
        from app.services.entity_resolution import resolve_entities

        headers, context = register(organizations, "gym")
        location_id = context["locations"][0]["id"]
        first = create_client(headers, location_id, "Kavinraj")
        create_client(headers, location_id, "Kavinraj")

        with SessionLocal() as db:
            owner = db.execute(select(User).where(User.organization_id == context["organization"]["id"])).scalar_one()
            by_name = resolve_entities(db, owner, "Kavin Raj", ["client"])
            by_phone = resolve_entities(db, owner, f"+91 {first['phone'][:5]} {first['phone'][5:]}", ["client"])

        assert by_name["resolution"] == "ambiguous"
        assert len(by_name["items"]) == 2
        assert by_phone["resolution"] == "unique"
        assert by_phone["selected"]["id"] == first["id"]
        assert by_phone["selected"]["selection_ref"] == {"kind": "client", "id": first["id"]}

    def test_catalog_and_inventory_resolve_as_one_location_scoped_product(self, organizations):
        from app.models import Location, StockLevel
        from app.services.entity_resolution import resolve_entities

        headers, context = register(organizations, "gym")
        location_id = context["locations"][0]["id"]
        product = post("/api/catalog", headers, {
            "name": "Whey Protein 1 kg", "sku": f"WHEY-{uuid4().hex[:6]}",
            "item_type": "product", "price_paise": 249900, "unit": "kg", "track_stock": True,
        })
        post("/api/inventory/adjust", headers, {
            "location_id": location_id, "item_id": product["id"], "quantity_delta_milli": 5000,
            "reason": "Opening stock", "batch_number": "MAIN", "reorder_level_milli": 2000,
        })

        with SessionLocal() as db:
            second = Location(
                organization_id=context["organization"]["id"], name="Warehouse", code=f"WH-{uuid4().hex[:6]}",
                city="Chennai", state="Tamil Nadu", is_primary=False,
            )
            db.add(second); db.flush()
            db.add(StockLevel(
                organization_id=context["organization"]["id"], location_id=second.id, item_id=product["id"],
                quantity_milli=7000, reorder_level_milli=1000, batch_number="WAREHOUSE",
            ))
            db.commit()
            owner = db.execute(select(User).where(User.organization_id == context["organization"]["id"])).scalar_one()
            resolved = resolve_entities(db, owner, "Whey Protein 1 kg", ["catalog", "inventory"])

        assert resolved["resolution"] == "unique"
        assert resolved["count"] == 1
        assert resolved["selected"]["kind"] == "catalog"
        assert resolved["selected"]["profile_ref"] == {"kind": "catalog", "id": product["id"]}
        assert resolved["selected"]["snapshot"]["stock"]["level_count"] == 2
        assert resolved["selected"]["snapshot"]["stock"]["total_quantity_milli"] == 12000

        selected = client.get(f"/api/catalog/{product['id']}/profile", headers=headers, params={"location_id": location_id})
        all_locations = client.get(f"/api/catalog/{product['id']}/profile", headers=headers)
        assert selected.status_code == 200, selected.text
        assert selected.json()["metrics"]["stock_milli"] == 5000
        assert selected.json()["scope"]["location"]["id"] == location_id
        assert all_locations.json()["metrics"]["stock_milli"] == 12000

    def test_ranked_search_ignores_name_spacing(self, organizations):
        headers, context = register(organizations, "gym")
        location_id = context["locations"][0]["id"]
        expected = create_client(headers, location_id, "Kavinraj")
        create_client(headers, location_id, "Unrelated Client")

        response = client.get("/api/search", headers=headers, params={"q": "Kavin Raj"})

        assert response.status_code == 200, response.text
        results = response.json()["clients"]
        assert results and results[0]["id"] == expected["id"]
        assert results[0]["display_name"] == "Kavinraj"
        assert "notes" not in results[0]

        typo_response = client.get("/api/search", headers=headers, params={"q": "Kavinrj"})
        assert typo_response.status_code == 200, typo_response.text
        assert typo_response.json()["clients"][0]["id"] == expected["id"]

    def test_ai_client_numbers_and_tool_failures_keep_transactions_healthy(self, organizations, monkeypatch):
        from app.ai.access import resolve_access_envelope
        from app.ai.catalog import catalog_for
        from app.ai.contracts import EntityRef, QueryGoal, SemanticQuery
        from app.ai.execution import execute_semantic_query

        headers, context = register(organizations, "gym")
        location_id = context["locations"][0]["id"]
        expected = create_client(headers, location_id, "Kavinraj")

        with SessionLocal() as db:
            owner = db.execute(select(User).where(User.organization_id == context["organization"]["id"])).scalar_one()
            envelope = resolve_access_envelope(db, owner)
            query = SemanticQuery(
                goal=QueryGoal.PROFILE, entity="client",
                fields=["id", "name", "client_number"],
                entities=[EntityRef(kind="client", label=expected["client_number"])],
            )
            result = execute_semantic_query(db, owner, query, catalog_for(envelope.industry), envelope)

            assert "id" not in result.artifacts[0].data
            assert result.artifacts[0].data["profile_ref"] == {
                "kind": "client", "id": expected["id"],
            }
            assert all(
                field.key != "id"
                for field in result.artifacts[0].presentation.fields
            )
            assert db.scalar(select(func.count()).select_from(User).where(User.organization_id == owner.organization_id)) >= 1

    def test_simple_greeting_skips_provider_wallet_and_usage(self, organizations, monkeypatch):
        headers, context = register(organizations, "gym")
        organization_id = context["organization"]["id"]
        with SessionLocal() as db:
            reservations_before = db.scalar(select(func.count()).select_from(WalletReservation).where(WalletReservation.organization_id == organization_id))
            usage_before = db.scalar(select(func.count()).select_from(AIUsage).where(AIUsage.organization_id == organization_id))

        class ProviderMustNotRun:
            async def respond(self, **_kwargs):
                raise AssertionError("Simple greetings must not call the AI provider")

        monkeypatch.setattr("app.ai.engine.configured_provider", lambda: ProviderMustNotRun())
        response = client.post("/api/ai/chat", headers=headers, json={
            "message": "Vanakkam!", "idempotency_key": f"greeting-{uuid4().hex}",
        })

        assert response.status_code == 200, response.text
        assert response.json()["credits_used"] == 0
        assert response.json()["message"]["content"].startswith("Vanakkam")
        conversation_id = response.json()["conversation_id"]
        messages = client.get(f"/api/ai/conversations/{conversation_id}/messages", headers=headers)
        assert messages.status_code == 200
        assert [message["role"] for message in messages.json()] == ["user", "assistant"]
        assert messages.json()[0]["turn_id"] == messages.json()[1]["turn_id"]
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(WalletReservation).where(WalletReservation.organization_id == organization_id)) == reservations_before
            assert db.scalar(select(func.count()).select_from(AIUsage).where(AIUsage.organization_id == organization_id)) == usage_before
            assistant = db.execute(select(ChatMessage).where(ChatMessage.conversation_id == conversation_id, ChatMessage.role == "assistant")).scalar_one()
            assert assistant.outcome == "success"
            turn_id = assistant.turn_id
            assert db.get(ChatTurn, turn_id).status == "completed"

        deleted = client.delete(f"/api/ai/conversations/{conversation_id}/turns/{turn_id}", headers=headers)
        assert deleted.status_code == 200, deleted.text
        assert client.get(f"/api/ai/conversations/{conversation_id}/messages", headers=headers).json() == []

    def test_tenant_location_abac_and_ai_language(self, organizations):
        owner, context = register(organizations, "gym")
        main = context["locations"][0]["id"]
        with SessionLocal() as db:
            organization = db.get(Organization, context["organization"]["id"])
            growth = db.execute(
                select(PlanVersion).join(PlanDefinition, PlanDefinition.id == PlanVersion.plan_id)
                .where(PlanDefinition.slug == "growth", PlanVersion.status == "published")
                .order_by(PlanVersion.version.desc())
            ).scalars().first()
            subscription = db.execute(select(Subscription).where(Subscription.organization_id == organization.id)).scalars().first()
            organization.plan = "growth"; subscription.plan = "growth"; subscription.plan_version_id = growth.id
            db.commit()
        branch = post("/api/locations", owner, {
            "name": "Second Branch", "code": f"B{uuid4().hex[:4].upper()}", "city": "Madurai",
        })
        visible_client = create_client(owner, main, "Main Client")
        hidden_client = create_client(owner, branch["id"], "Hidden Client")

        roles_response = client.get("/api/roles", headers=owner)
        assert roles_response.status_code == 200, roles_response.text
        staff_role = next(role for role in roles_response.json() if role["slug"] == "staff")
        staff_email = f"staff-{uuid4().hex[:8]}@example.com"
        staff = post("/api/users", owner, {
            "email": staff_email,
            "first_name": "Restricted",
            "password": "Testing@123",
            "role_ids": [staff_role["id"]],
            "location_ids": [main],
        })
        with SessionLocal() as db:
            row = db.get(User, staff["id"]); row.email_verified = True; db.commit()
        effective = client.get(f"/api/access/users/{staff['id']}", headers=owner)
        assert effective.status_code == 200
        assert effective.json()["location_ids"] == [main]

        login = client.post("/api/auth/login", json={
            "email": staff_email,
            "password": "Testing@123",
            "org_slug": context["organization"]["slug"],
        })
        assert login.status_code == 200, login.text
        restricted = {"Authorization": f"Bearer {login.cookies.get(settings.ACCESS_COOKIE_NAME)}"}
        listed = client.get("/api/clients", headers=restricted)
        assert listed.status_code == 200
        assert {row["id"] for row in listed.json()["items"]} == {visible_client["id"]}
        assert client.get(f"/api/clients/{hidden_client['id']}", headers=restricted).status_code == 403
        from app.services.entity_resolution import resolve_entities
        with SessionLocal() as db:
            restricted_user = db.get(User, staff["id"])
            assert resolve_entities(db, restricted_user, "Second Branch", ["location"])["resolution"] == "none"
            hidden_resolution = resolve_entities(db, restricted_user, "Hidden Client", ["client"])
            assert hidden_client["id"] not in {item["id"] for item in hidden_resolution["items"]}

        other_tenant, _ = register(organizations, "gym")
        assert client.get(f"/api/clients/{visible_client['id']}", headers=other_tenant).status_code == 404

        ai = client.post("/api/ai/chat", headers=owner, json={
            "message": "Innaiku collection evlo?",
            "context": {"location_id": main},
        })
        assert ai.status_code == 200, ai.text
        assert "INR" in ai.json()["message"]["content"]
        assert ai.json()["message"]["artifacts"][0]["type"] == "metric"

    def test_atomic_gst_sale_and_appointment_conflict(self, organizations):
        headers, context = register(organizations, "salon")
        location_id = context["locations"][0]["id"]
        buyer = create_client(headers, location_id)
        employees = client.get("/api/employees", headers=headers)
        assert employees.status_code == 200
        employee_id = employees.json()["items"][0]["id"]
        product = post("/api/catalog", headers, {
            "name": "Hair Serum", "sku": f"SER-{uuid4().hex[:6]}", "item_type": "product",
            "price_paise": 10000, "cost_paise": 5000, "tax_rate_bps": 1800,
            "tax_inclusive": False, "unit": "bottle", "track_stock": True,
        })
        service = post("/api/catalog", headers, {
            "name": "Premium Haircut", "sku": f"CUT-{uuid4().hex[:6]}", "item_type": "service",
            "price_paise": 75000, "duration_minutes": 60,
        })
        post("/api/inventory/adjust", headers, {
            "location_id": location_id, "item_id": product["id"], "quantity_delta_milli": 5000,
            "reason": "Opening stock",
        })
        sale_body = {
            "location_id": location_id,
            "client_id": buyer["id"],
            "lines": [{"item_id": product["id"], "quantity_milli": 2000}],
            "issue": True,
            "idempotency_key": f"sale-{uuid4().hex}",
        }
        invoice = post("/api/sales", headers, sale_body)
        assert (invoice["subtotal_paise"], invoice["cgst_paise"], invoice["sgst_paise"], invoice["total_paise"]) == (20000, 1800, 1800, 23600)
        assert post("/api/sales", headers, sale_body)["id"] == invoice["id"]
        inventory = client.get(f"/api/inventory?location_id={location_id}", headers=headers).json()
        assert inventory[0]["quantity_milli"] == 3000
        transferable = client.get("/api/inventory/levels/page", headers=headers, params={
            "location_id": location_id,
            "q": "Hair Serum",
            "state": "in_stock",
        })
        assert transferable.status_code == 200, transferable.text
        assert [row["item"]["id"] for row in transferable.json()["items"]] == [product["id"]]
        post(f"/api/sales/{invoice['id']}/payments", headers, {
            "amount_paise": 23600, "method": "upi", "idempotency_key": f"payment-{uuid4().hex}",
        })
        paid = next(row for row in client.get("/api/sales", headers=headers).json() if row["id"] == invoice["id"])
        assert paid["status"] == "paid"

        ai = client.post("/api/ai/chat", headers=headers, json={
            "message": "Innaiku collection evlo?",
            "context": {"location_id": location_id},
        })
        assert ai.status_code == 200, ai.text
        assert ai.json()["credits_used"] == 0
        assert "236.00" in ai.json()["message"]["content"]
        assert ai.json()["message"]["artifacts"][0]["data"]["revenue_paise"] == 23600

        client_profile = client.get(f"/api/clients/{buyer['id']}/profile", headers=headers)
        assert client_profile.status_code == 200, client_profile.text
        assert client_profile.json()["metrics"]["lifetime_value_paise"] == 23600
        employee_profile = client.get(f"/api/employees/{employee_id}/profile", headers=headers)
        assert employee_profile.status_code == 200, employee_profile.text
        assert "hashed_password" not in (employee_profile.json()["account"] or {})
        item_profile = client.get(f"/api/catalog/{product['id']}/profile", headers=headers)
        assert item_profile.status_code == 200, item_profile.text
        assert item_profile.json()["metrics"]["units_sold_milli"] == 2000
        notification_summary = client.get("/api/notifications/summary", headers=headers)
        assert notification_summary.status_code == 200
        assert notification_summary.json()["unread"] >= 1
        mark_all = client.post("/api/notifications/read-all", headers=headers)
        assert mark_all.status_code == 200
        assert client.get("/api/notifications/summary", headers=headers).json()["unread"] == 0

        starts = datetime.now(timezone.utc) + timedelta(days=2)
        booking = {
            "location_id": location_id, "client_id": buyer["id"], "employee_id": employee_id,
            "service_id": service["id"], "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=1)).isoformat(),
        }
        post("/api/appointments", headers, booking)
        assert client.post("/api/appointments", headers=headers, json=booking).status_code == 409
        appointment_rows = client.get("/api/appointments", headers=headers, params={
            "location_id": location_id,
            "start": (starts - timedelta(minutes=1)).isoformat(),
            "end": (starts + timedelta(hours=2)).isoformat(),
        })
        assert appointment_rows.status_code == 200, appointment_rows.text
        appointment = appointment_rows.json()[0]
        assert appointment["client"]["id"] == buyer["id"]
        assert appointment["client"]["first_name"] == buyer["first_name"]
        assert appointment["employee"]["id"] == employee_id
        assert appointment["service"] == {
            "id": service["id"],
            "name": "Premium Haircut",
            "duration_minutes": 60,
        }
        timeline_response = client.get(f"/api/clients/{buyer['id']}/timeline", headers=headers, params={"limit": 2})
        assert timeline_response.status_code == 200, timeline_response.text
        timeline_page = timeline_response.json()
        assert timeline_page["has_more"] is True
        assert timeline_page["next_cursor"]
        older_timeline_response = client.get(f"/api/clients/{buyer['id']}/timeline", headers=headers, params={
            "limit": 2,
            "cursor": timeline_page["next_cursor"],
        })
        assert older_timeline_response.status_code == 200, older_timeline_response.text
        timeline_ids = [row["id"] for row in timeline_page["items"] + older_timeline_response.json()["items"]]
        assert len(timeline_ids) == len(set(timeline_ids))
        assert {row.split(":", 1)[0] for row in timeline_ids}.issuperset({"appointment", "invoice", "payment"})
        changed_timeline_filter = client.get(f"/api/clients/{buyer['id']}/timeline", headers=headers, params={
            "event_type": "invoice",
            "cursor": timeline_page["next_cursor"],
        })
        assert changed_timeline_filter.status_code == 422

    def test_employee_profile_hides_compensation_without_permission(self, organizations):
        owner, context = register(organizations, "gym")
        location_id = context["locations"][0]["id"]
        roles = client.get("/api/roles", headers=owner).json()
        manager_role = next(role for role in roles if role["slug"] == "manager")
        employee = client.get("/api/employees", headers=owner).json()["items"][0]
        email = f"manager-{uuid4().hex[:8]}@example.com"
        manager = post("/api/users", owner, {
            "email": email, "first_name": "Profile", "last_name": "Manager",
            "password": "Testing@123", "role_ids": [manager_role["id"]],
            "location_ids": [location_id],
        })
        with SessionLocal() as db:
            row = db.get(User, manager["id"]); row.email_verified = True; db.commit()
        login = client.post("/api/auth/login", json={
            "email": email, "password": "Testing@123", "org_slug": context["organization"]["slug"],
        })
        headers = {"Authorization": f"Bearer {login.cookies.get(settings.ACCESS_COOKIE_NAME)}"}

        profile = client.get(f"/api/employees/{employee['id']}/profile", headers=headers)
        assert profile.status_code == 200, profile.text
        assert profile.json()["capabilities"]["view_compensation"] is False
        assert "salary_paise" not in profile.json()["employee"]


class TestGymWorkflow:
    def test_membership_checkin_freeze_and_renewal(self, organizations):
        headers, context = register(organizations, "gym")
        location_id = context["locations"][0]["id"]
        member = create_client(headers, location_id, "Gym Member")
        plan = post("/api/gym/plans", headers, {
            "name": "Quarterly", "duration_days": 90, "price_paise": 900000, "joining_fee_paise": 50000,
        })
        membership = post("/api/gym/memberships", headers, {
            "location_id": location_id, "client_id": member["id"], "plan_id": plan["id"],
            "starts_on": date.today().isoformat(),
        })
        assert membership["amount_paise"] == 950000
        checkin = post("/api/gym/check-ins", headers, {
            "location_id": location_id, "membership_id": membership["id"], "method": "staff",
        })
        assert client.post("/api/gym/check-ins", headers=headers, json={
            "location_id": location_id, "membership_id": membership["id"],
        }).status_code == 409
        assert client.post(f"/api/gym/check-ins/{checkin['id']}/checkout", headers=headers).status_code == 200

        tomorrow = date.today() + timedelta(days=1)
        frozen = client.post(f"/api/gym/memberships/{membership['id']}/freeze", headers=headers, json={
            "frozen_from": tomorrow.isoformat(),
            "frozen_until": (tomorrow + timedelta(days=7)).isoformat(),
            "version": membership["version"],
        })
        assert frozen.status_code == 200, frozen.text
        assert client.post(f"/api/gym/memberships/{membership['id']}/resume", headers=headers).status_code == 200
        renewed = client.post(f"/api/gym/memberships/{membership['id']}/renew", headers=headers)
        assert renewed.status_code == 201, renewed.text
        cancelled = client.post(f"/api/gym/memberships/{renewed.json()['id']}/cancel", headers=headers, json={
            "reason": "Member requested cancellation", "version": renewed.json()["version"],
        })
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["cancellation_reason"] == "Member requested cancellation"
        summary = client.get("/api/gym/summary", headers=headers)
        assert summary.status_code == 200, summary.text
        assert summary.json()["check_ins_today"] == 1

    def test_client_intelligence_workspace_media_and_profile_actions(self, organizations):
        headers, context = register(organizations, "gym")
        location_id = context["locations"][0]["id"]
        member = create_client(headers, location_id, "Client Intelligence")
        plan = post("/api/gym/plans", headers, {
            "name": "One Week", "duration_days": 6, "price_paise": 100000,
        })
        membership = post("/api/gym/memberships", headers, {
            "location_id": location_id, "client_id": member["id"], "plan_id": plan["id"],
            "starts_on": date.today().isoformat(),
        })
        assert membership["invoice"]["status"] == "issued"
        assert membership["invoice"]["items_preview"] == ["One Week membership"]
        memory = post(f"/api/clients/{member['id']}/memory", headers, {
            "category": "preference", "label": "Training preference",
            "value": "Prefers quiet morning strength sessions", "visibility": "team",
        })
        assert memory["version"] == 1
        post(f"/api/clients/{member['id']}/commitments", headers, {
            "title": "Share the revised workout plan",
            "due_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        })
        post(f"/api/gym/members/{member['id']}/goals", headers, {
            "metric_key": "weight_kg", "label": "Reach target weight", "baseline_value": 82,
            "target_value": 76, "current_value": 80, "unit": "kg",
            "starts_on": date.today().isoformat(), "target_on": (date.today() + timedelta(days=60)).isoformat(),
        })
        checkin = post(f"/api/gym/members/{member['id']}/check-in", headers, {
            "location_id": location_id, "notes": "Profile quick action",
        })
        assert checkin["recorded_by_user_id"]
        assert checkin["source"] == "client_workspace"
        checkout = client.post(f"/api/gym/members/{member['id']}/check-out", headers=headers)
        assert checkout.status_code == 200, checkout.text

        upload = client.post(
            f"/api/clients/{member['id']}/media", headers=headers,
            data={"media_kind": "profile_photo", "visibility": "team"},
            files={"file": ("profile.png", b"\x89PNG\r\n\x1a\nclient-photo", "image/png")},
        )
        assert upload.status_code == 201, upload.text
        assert client.get(f"/api/clients/{member['id']}/photo", headers=headers).status_code == 200

        assessment = post("/api/catalog", headers, {
            "name": "Progress Assessment", "sku": f"ASSESS-{uuid4().hex[:6]}",
            "item_type": "service", "price_paise": 40000, "duration_minutes": 30,
        })
        post("/api/sales", headers, {
            "location_id": location_id, "client_id": member["id"],
            "lines": [{"item_id": assessment["id"], "quantity_milli": 1000}],
            "issue": True, "idempotency_key": f"signal-balance-{uuid4().hex}",
        })

        workspace = client.get(f"/api/clients/{member['id']}/workspace?range=30d", headers=headers)
        assert workspace.status_code == 200, workspace.text
        data = workspace.json()
        assert data["profile_photo_url"]
        assert data["industry"] == "gym"
        assert data["industry_data"]["attendance"]["checkins"] == 1
        assert any(item["label"] == "Training preference" for item in data["memory"])
        assert data["pulse"]["state"] == "action_needed"
        assert data["sales"][0]["items"][0]["name"] == "Progress Assessment"
        assert any(item["signal_type"] == "membership_expiry" for item in data["signals"])
        assert any(item["signal_type"] == "overdue_commitment" for item in data["signals"])
        balance_signal = next(item for item in data["signals"] if item["signal_type"] == "outstanding_balance")
        assert balance_signal["evidence"][0]["value"] == 140000
        assert isinstance(balance_signal["evidence"][0]["value"], int)
        attention = client.get("/api/clients/attention", headers=headers)
        assert attention.status_code == 200, attention.text
        assert any(row["client"]["id"] == member["id"] for row in attention.json())

    def test_membership_checkout_renewal_and_invoice_resolution(self, organizations):
        headers, context = register(organizations, "gym")
        location_id = context["locations"][0]["id"]
        with SessionLocal() as db:
            organization = db.get(Organization, context["organization"]["id"])
            organization.tax_settings = {"prices_include_tax": False, "default_tax_rate_bps": 1800}
            db.commit()
        plan = post("/api/gym/plans", headers, {
            "name": "Billing Plan", "duration_days": 30,
            "price_paise": 100000, "joining_fee_paise": 20000,
        })

        partial_client = create_client(headers, location_id, "Partial Payment")
        quote = client.get(
            "/api/gym/membership-quote",
            headers=headers,
            params={"plan_id": plan["id"], "client_id": partial_client["id"], "kind": "activation"},
        )
        assert quote.status_code == 200, quote.text
        assert quote.json()["total_paise"] == 141600
        activation_key = f"membership-partial-{uuid4().hex}"
        partial = post("/api/gym/memberships", headers, {
            "location_id": location_id, "client_id": partial_client["id"], "plan_id": plan["id"],
            "starts_on": date.today().isoformat(), "payment_option": "partial",
            "partial_payment_paise": 30000, "payment_method": "upi",
            "idempotency_key": activation_key,
        })
        assert partial["invoice"]["total_paise"] == 141600
        assert partial["invoice"]["paid_paise"] == 30000
        assert partial["invoice"]["status"] == "partially_paid"
        assert partial["invoice"]["tax_snapshot"]["rate_bps"] == 1800
        assert partial["payment"]["amount_paise"] == 30000
        repeated = post("/api/gym/memberships", headers, {
            "location_id": location_id, "client_id": partial_client["id"], "plan_id": plan["id"],
            "starts_on": date.today().isoformat(), "payment_option": "partial",
            "partial_payment_paise": 30000, "payment_method": "upi",
            "idempotency_key": activation_key,
        })
        assert repeated["id"] == partial["id"]
        blocked_void = client.post(
            f"/api/sales/{partial['invoice']['id']}/void",
            headers=headers,
            json={"reason": "Incorrect charge", "version": partial["invoice"]["version"]},
        )
        assert blocked_void.status_code == 409
        post(f"/api/sales/{partial['invoice']['id']}/payments", headers, {
            "amount_paise": 111600, "method": "bank",
            "idempotency_key": f"payment-{uuid4().hex}", "version": partial["invoice"]["version"],
        })
        workspace = client.get(f"/api/clients/{partial_client['id']}/workspace", headers=headers).json()
        assert workspace["billing"]["summary"]["outstanding_paise"] == 0

        full_client = create_client(headers, location_id, "Full Payment")
        full = post("/api/gym/memberships", headers, {
            "location_id": location_id, "client_id": full_client["id"], "plan_id": plan["id"],
            "starts_on": date.today().isoformat(), "payment_option": "full",
            "payment_method": "cash", "idempotency_key": f"membership-full-{uuid4().hex}",
        })
        assert full["invoice"]["status"] == "paid"
        assert full["payment"]["amount_paise"] == 141600

        deferred_client = create_client(headers, location_id, "Deferred Payment")
        deferred = post("/api/gym/memberships", headers, {
            "location_id": location_id, "client_id": deferred_client["id"], "plan_id": plan["id"],
            "starts_on": date.today().isoformat(), "payment_option": "later",
            "idempotency_key": f"membership-later-{uuid4().hex}",
        })
        deferred_workspace = client.get(f"/api/clients/{deferred_client['id']}/workspace", headers=headers).json()
        open_invoice = deferred_workspace["billing"]["open_invoices"][0]
        assert open_invoice["id"] == deferred["invoice"]["id"]
        assert open_invoice["item_names"] == ["Billing Plan membership", "Joining fee"]
        assert deferred_workspace["billing"]["summary"]["outstanding_paise"] == 141600
        voided = post(f"/api/sales/{deferred['invoice']['id']}/void", headers, {
            "reason": "Duplicate membership charge", "version": deferred["invoice"]["version"],
        }, expected=200)
        assert voided["status"] == "void"
        assert voided["void_reason"] == "Duplicate membership charge"
        assert client.get(f"/api/clients/{deferred_client['id']}/workspace", headers=headers).json()["billing"]["summary"]["outstanding_paise"] == 0

        renewal = post(f"/api/gym/memberships/{partial['id']}/renew", headers, {
            "payment_option": "later", "idempotency_key": f"renewal-{uuid4().hex}",
        })
        assert renewal["status"] == "scheduled"
        assert renewal["previous_membership_id"] == partial["id"]
        assert renewal["invoice"]["total_paise"] == 118000
        assert all(item["item_name"] != "Joining fee" for item in renewal["invoice"]["lines"])
        memberships = client.get("/api/gym/memberships", headers=headers).json()
        assert next(item for item in memberships if item["id"] == partial["id"])["status"] == "active"
        cancelled = post(f"/api/gym/memberships/{renewal['id']}/cancel", headers, {
            "reason": "Renewal no longer required", "version": renewal["version"],
            "timing": "now", "cancel_scheduled_renewal": True,
        }, expected=200)
        assert cancelled["status"] == "cancelled"
        assert cancelled["invoice"]["status"] == "void"

    def test_selected_client_scope_applies_to_profiles(self, organizations):
        owner, context = register(organizations, "gym")
        location_id = context["locations"][0]["id"]
        visible = create_client(owner, location_id, "Selected Client")
        hidden = create_client(owner, location_id, "Hidden Client")
        roles = client.get("/api/roles", headers=owner).json()
        staff_role = next(role for role in roles if role["slug"] == "staff")
        email = f"selected-{uuid4().hex[:8]}@example.com"
        staff = post("/api/users", owner, {
            "email": email, "first_name": "Selected", "password": "Testing@123",
            "role_ids": [staff_role["id"]], "location_ids": [location_id],
        })
        with SessionLocal() as db:
            row = db.get(User, staff["id"]); row.email_verified = True; db.commit()
        configured = client.put(f"/api/access/users/{staff['id']}/configuration", headers=owner, json={
            "role_ids": [staff_role["id"]], "permission_overrides": [],
            "location_mode": "restricted", "location_ids": [location_id],
            "client_mode": "selected", "client_ids": [visible["id"]],
        })
        assert configured.status_code == 200, configured.text
        login = client.post("/api/auth/login", json={
            "email": email, "password": "Testing@123", "org_slug": context["organization"]["slug"],
        })
        scoped = {"Authorization": f"Bearer {login.cookies.get(settings.ACCESS_COOKIE_NAME)}"}
        listed = client.get("/api/clients", headers=scoped)
        assert {row["id"] for row in listed.json()["items"]} == {visible["id"]}
        assert client.get(f"/api/clients/{visible['id']}/workspace", headers=scoped).status_code == 200
        assert client.get(f"/api/clients/{hidden['id']}/workspace", headers=scoped).status_code == 403


class TestClinicWorkflow:
    def test_signed_records_labs_and_dispensing(self, organizations):
        headers, context = register(organizations, "clinic")
        location_id = context["locations"][0]["id"]
        person = create_client(headers, location_id, "Clinic Patient")
        patient = post("/api/clinic/patients", headers, {
            "client_id": person["id"], "blood_group": "O+", "consent": {"treatment": True},
        })
        practitioner = client.get("/api/employees", headers=headers).json()["items"][0]
        encounter = post("/api/clinic/encounters", headers, {
            "location_id": location_id, "patient_id": patient["id"],
            "practitioner_employee_id": practitioner["id"], "chief_complaint": "Fever",
        })
        post(f"/api/clinic/encounters/{encounter['id']}/vitals", headers, {"values": {"temperature_c": 38.1}})
        post(f"/api/clinic/encounters/{encounter['id']}/diagnoses", headers, {
            "description": "Viral fever", "is_primary": True,
        })
        medicine = post("/api/catalog", headers, {
            "name": "Paracetamol 500mg", "sku": f"MED-{uuid4().hex[:6]}", "item_type": "medicine",
            "price_paise": 200, "tax_rate_bps": 500, "unit": "tablet", "track_stock": True,
        })
        post("/api/inventory/adjust", headers, {
            "location_id": location_id, "item_id": medicine["id"], "quantity_delta_milli": 10000,
            "reason": "Pharmacy receipt", "batch_number": "PCM-001",
            "expires_on": (date.today() + timedelta(days=365)).isoformat(),
        })
        prescription = post("/api/clinic/prescriptions", headers, {
            "encounter_id": encounter["id"], "items": [{
                "medicine_item_id": medicine["id"], "medicine_name": "Paracetamol 500mg",
                "dosage": "1 tablet", "frequency": "Twice daily", "duration": "3 days",
            }],
        })
        lab_test = post("/api/clinic/lab/tests", headers, {
            "name": "Complete Blood Count", "code": f"CBC-{uuid4().hex[:4]}", "price_paise": 50000,
        })
        lab_order = post("/api/clinic/lab/orders", headers, {
            "encounter_id": encounter["id"], "test_id": lab_test["id"],
        })

        signed = client.post(f"/api/clinic/encounters/{encounter['id']}/sign", headers=headers)
        assert signed.status_code == 200, signed.text
        immutable = client.patch(f"/api/clinic/encounters/{encounter['id']}", headers=headers, json={
            "clinical_notes": "Should not change", "version": signed.json()["version"],
        })
        assert immutable.status_code == 423
        assert client.post(f"/api/clinic/prescriptions/{prescription['id']}/sign", headers=headers).status_code == 200
        rx = next(row for row in client.get("/api/clinic/prescriptions", headers=headers).json() if row["id"] == prescription["id"])
        dispense = post("/api/clinic/dispenses", headers, {
            "location_id": location_id, "prescription_id": prescription["id"],
            "items": [{"prescription_item_id": rx["items"][0]["id"], "quantity_milli": 3000, "batch_number": "PCM-001"}],
        })
        assert dispense["items"][0]["quantity_milli"] == 3000

        assert client.post(f"/api/clinic/lab/orders/{lab_order['id']}/sign", headers=headers).status_code == 200
        result = client.put(f"/api/clinic/lab/orders/{lab_order['id']}/result", headers=headers, json={
            "values": {"hemoglobin": 13.5}, "interpretation": "Within range",
        })
        assert result.status_code == 200, result.text
        assert client.post(f"/api/clinic/lab/orders/{lab_order['id']}/verify", headers=headers).status_code == 200
        inventory = client.get(f"/api/inventory?location_id={location_id}", headers=headers).json()
        assert next(row for row in inventory if row["item_id"] == medicine["id"])["quantity_milli"] == 7000
