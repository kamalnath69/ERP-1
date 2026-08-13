"""Support-session boundaries that must remain fail closed."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core import deps


class _UserDb:
    def __init__(self, user):
        self.user = user

    def get(self, _model, _identifier):
        return self.user


def _user(*, super_admin=False, organization_id="org"):
    return SimpleNamespace(
        id="user",
        is_active=True,
        is_super_admin=super_admin,
        organization_id=organization_id,
        session_version=1,
        access_version=1,
    )


def test_tenant_user_cannot_use_a_support_header_to_skip_normal_checks(monkeypatch):
    user = _user()
    monkeypatch.setattr(deps, "decode_token", lambda _token: {
        "type": "access", "sub": user.id, "sv": 1, "av": 1,
    })
    request = SimpleNamespace(
        headers={"x-support-session": "not-a-platform-session"},
        cookies={},
        method="GET",
        url=SimpleNamespace(path="/api/college/placement-dashboard"),
        state=SimpleNamespace(),
    )

    with pytest.raises(HTTPException) as error:
        deps.get_current_user(
            request,
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
            _UserDb(user),
        )
    assert error.value.status_code == 403
    assert "platform administrator" in str(error.value.detail)


def test_platform_admin_cannot_enter_tenant_permission_dependency_without_support_session():
    platform_admin = _user(super_admin=True, organization_id=None)
    check = deps.require_permissions("college.students.view")

    with pytest.raises(HTTPException) as error:
        check(platform_admin, None)
    assert error.value.status_code == 403
    assert "audited support session" in str(error.value.detail)
