"""Control-plane security, entitlement, wallet, and API coverage."""
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.models import Organization, User
from app.services.entitlements import resolve_entitlements
from app.services.platform_security import platform_permissions
from app.services.wallet import release_reservation, reserve_credits
from server import app


client = TestClient(app, raise_server_exceptions=True)


def platform_headers():
    with SessionLocal() as db:
        admin = db.execute(select(User).where(User.organization_id.is_(None), User.is_super_admin.is_(True), User.is_active.is_(True)).order_by(User.created_at)).scalars().first()
        return {"Authorization": f"Bearer {create_access_token(admin.id, None, {'sv': admin.session_version})}"}


def test_platform_owner_permissions_are_database_backed():
    with SessionLocal() as db:
        admin = db.execute(select(User).where(User.organization_id.is_(None), User.is_super_admin.is_(True)).order_by(User.created_at)).scalars().first()
        granted = platform_permissions(db, admin)
        assert {"organizations.manage", "plans.publish", "billing.refund", "support.start", "settings.manage"}.issubset(granted)


def test_existing_organizations_have_versioned_entitlements_and_wallets():
    with SessionLocal() as db:
        organization = db.execute(select(Organization).order_by(Organization.created_at)).scalars().first()
        resolved = resolve_entitlements(db, organization)
        assert resolved["plan"]["version_id"]
        assert resolved["values"]["module.clients"] is True
        assert resolved["values"]["limits.clients"] > 0


def test_wallet_reservation_releases_without_negative_balance():
    with SessionLocal() as db:
        organization = db.execute(select(Organization).order_by(Organization.created_at)).scalars().first()
        reservation = reserve_credits(db, organization, 1, f"test-wallet-{uuid4()}")
        wallet = release_reservation(db, reservation)
        assert wallet.balance_credits >= 0
        assert wallet.reserved_credits >= 0
        assert reservation.status == "released"
        db.rollback()


def test_control_center_sections_are_available_to_platform_owner():
    headers = platform_headers()
    for section in ("me", "overview", "organizations", "plans", "billing", "wallets", "platform-team", "support-sessions", "operations", "audit", "settings"):
        response = client.get(f"/api/super-admin/{section}", headers=headers)
        assert response.status_code == 200, (section, response.text)
