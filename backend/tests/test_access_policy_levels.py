"""Pure policy-matrix regressions that do not require a database."""
from types import SimpleNamespace

import app.services.access_policy as access_policy
from app.api.v1.roles import _slug
from app.services.access_policy import (
    COLLEGE_ROLE_LEVEL_SUGGESTIONS,
    POLICY_MANAGED_PERMISSION_CODES,
    ExpandedCollegeScope,
    PolicyContext,
    domain_level_from_permissions,
    permission_codes_for_levels,
)
from app.services.data_exchange import (
    RESOURCES,
    RESOURCE_DOMAINS,
    RESOURCE_VIEW_PERMISSIONS,
    RESOURCE_WRITE_PERMISSIONS,
    resource_catalog,
)


def test_duplicate_permission_bundles_stop_at_the_first_meaningful_level():
    permissions = {"college.coding.view", "college.coding.manage"}
    assert domain_level_from_permissions(permissions, "coding") == "work"
    assert domain_level_from_permissions({"reports.view", "college.placement_reports.view"}, "reports") == "view"
    assert domain_level_from_permissions({"college.clearance.view"}, "clearance") == "view"


def test_explicit_policy_levels_remain_authoritative_over_legacy_bundles():
    context = PolicyContext(
        organization_id="org",
        user_id="user",
        policy_id="policy",
        policy_version=2,
        access_version=3,
        status="active",
        permissions=frozenset({
            "college.assessments.view",
            "college.assessments.record",
            "college.assessments.manage",
        }),
        maximum_scope=ExpandedCollegeScope(unrestricted=True),
        domain_levels={"assessments": "view"},
    )
    assert context.level("assessments") == "view"


def test_policy_level_bundles_do_not_implicitly_grant_sensitive_safeguards():
    permissions = permission_codes_for_levels({
        "students": "work",
        "reports": "view",
        "clearance": "manage",
    })
    assert "clients.manage" in permissions
    assert "college.placement_reports.view" in permissions
    assert "college.clearance.view" in permissions
    assert "college.fees.view" not in permissions
    assert "college.clearance.manage" not in permissions


def test_finance_template_does_not_inherit_placement_reporting():
    suggestion = COLLEGE_ROLE_LEVEL_SUGGESTIONS["finance"]
    assert suggestion == {"students": "view", "clearance": "manage"}


def test_policy_owns_navigation_dependencies_instead_of_role_names():
    assert "college.view" in POLICY_MANAGED_PERMISSION_CODES
    assert "dashboard.view" in POLICY_MANAGED_PERMISSION_CODES


def test_every_exchange_resource_declares_a_domain_and_view_boundary():
    assert set(RESOURCES) == set(RESOURCE_DOMAINS)
    assert set(RESOURCES) == set(RESOURCE_VIEW_PERMISSIONS)
    assert set(RESOURCE_WRITE_PERMISSIONS).issubset(RESOURCES)


def test_data_exchange_separates_view_export_and_write_authority():
    base = {"college.data.view", "college.data.export", "college.students.view"}
    students = next(row for row in resource_catalog(base) if row["key"] == "students")
    assert students["exportable"] is True
    assert students["importable"] is False
    assert students["methods"] == []

    still_read_only = next(row for row in resource_catalog(
        base | {"college.imports.manage"}
    ) if row["key"] == "students")
    assert still_read_only["importable"] is False

    writable = next(row for row in resource_catalog(
        base | {"college.imports.manage", "college.students.manage"}
    ) if row["key"] == "students")
    assert writable["importable"] is True
    assert writable["methods"]


def test_clearance_exchange_never_uses_fee_amount_visibility_as_write_authority():
    permissions = {
        "college.data.view", "college.imports.manage", "college.clearance.view",
    }
    clearance = next(row for row in resource_catalog(permissions) if row["key"] == "internship_clearance")
    assert clearance["importable"] is False
    assert clearance["methods"] == []

    writable = next(row for row in resource_catalog(
        permissions | {"college.clearance.manage"}
    ) if row["key"] == "internship_clearance")
    assert writable["importable"] is True


def test_custom_role_slugs_cannot_impersonate_privileged_system_roles():
    assert _slug("Owner") == "custom-owner"
    assert _slug("Access Admin") == "custom-access-admin"


def test_owner_resolution_requires_the_builtin_role(monkeypatch):
    user = SimpleNamespace(id="user")
    monkeypatch.setattr(
        access_policy,
        "get_user_roles",
        lambda _db, _user: [SimpleNamespace(slug="owner", is_system=False)],
    )
    assert access_policy.is_owner(None, user) is False

    monkeypatch.setattr(
        access_policy,
        "get_user_roles",
        lambda _db, _user: [SimpleNamespace(slug="owner", is_system=True)],
    )
    assert access_policy.is_owner(None, user) is True
