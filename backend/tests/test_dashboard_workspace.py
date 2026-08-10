from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Organization, User
from app.services.dashboard import build_dashboard_workspace
from app.services.rbac import get_user_permissions


def _dashboard_owner(db):
    organization = db.execute(select(Organization).where(
        Organization.slug == "pulse-fitness",
    )).scalar_one()
    users = db.execute(select(User).where(
        User.organization_id == organization.id,
        User.is_active.is_(True),
    )).scalars().all()
    return next(user for user in users if {
        "dashboard.view", "sales.view", "clients.view",
    }.issubset(get_user_permissions(db, user)))


def test_dashboard_includes_scoped_chart_variety():
    with SessionLocal() as db:
        user = _dashboard_owner(db)
        workspace = build_dashboard_workspace(db, user, None, 30)

    widgets = {widget["id"]: widget for widget in workspace["widgets"]}
    assert widgets["collections_trend"]["kind"] == "line_chart"
    assert widgets["sales_status_mix"]["kind"] == "donut_chart"
    assert widgets["sales_status_mix"]["x_key"] == "label"
    assert widgets["sales_status_mix"]["data"]
    assert widgets["client_growth"]["kind"] == "bar_chart"
    assert len(widgets["client_growth"]["data"]) == 30
    assert sum(point["value"] for point in widgets["client_growth"]["data"]) > 0
    assert any(item["id"] == "sales_status_mix" for item in workspace["breakdowns"])
    assert any(item["id"] == "client_growth" and item["type"] == "bar" for item in workspace["series"])
