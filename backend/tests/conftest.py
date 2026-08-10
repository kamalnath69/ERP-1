import pytest


@pytest.fixture(autouse=True)
def prevent_external_email(monkeypatch):
    """Tests must never consume configured email or AI provider quotas."""
    delivered = lambda *_args, **_kwargs: True
    monkeypatch.setattr("app.api.v1.auth.send_auth_code_email", delivered)
    monkeypatch.setattr("app.api.v1.users.send_auth_code_email", delivered)
    monkeypatch.setattr("app.ai.orchestrator.provider", lambda: None)
