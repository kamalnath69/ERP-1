import logging

from resend.exceptions import ResendError

from app.core.config import settings
from app.services.email import send_email


def test_resend_provider_sends_and_returns_message_id(monkeypatch):
    captured = {}

    def fake_send(payload):
        captured.update(payload)
        return {"id": "email_test_123"}

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(settings, "RESEND_FROM_EMAIL", "Edvatiq <hello@example.com>")
    monkeypatch.setattr("app.services.email.resend.Emails.send", fake_send)

    message_id = send_email(
        "owner@example.com",
        "Verify your email",
        "Plain text",
        "<p>Plain text</p>",
        "email_verification",
    )

    assert message_id == "email_test_123"
    assert captured == {
        "from": "Edvatiq <hello@example.com>",
        "to": ["owner@example.com"],
        "subject": "Verify your email",
        "text": "Plain text",
        "html": "<p>Plain text</p>",
    }


def test_resend_test_sender_restriction_has_actionable_log(monkeypatch, caplog):
    def rejected(_payload):
        raise ResendError(
            403,
            "validation_error",
            "You can only send testing emails to your own email address.",
            "Verify a domain.",
        )

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(settings, "RESEND_FROM_EMAIL", "Edvatiq <onboarding@resend.dev>")
    monkeypatch.setattr("app.services.email.resend.Emails.send", rejected)

    with caplog.at_level(logging.INFO, logger="edvatiq.email"):
        result = send_email("client@example.org", "Verify", "Code", "<p>Code</p>", "email_verification")

    assert result is None
    assert "reason=test_sender_recipient_restricted status_code=403" in caplog.text
