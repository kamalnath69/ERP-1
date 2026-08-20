from app.core.config import settings
from app.services.email import send_auth_code_email
from app.services.email_templates import render_auth_email
from app.services.whatsapp import normalize_phone, send_whatsapp_message


def test_security_email_template_is_branded_and_inbox_safe():
    subject, text, html = render_auth_email(
        code="123456",
        purpose="email_verification",
        first_name="Kamal",
        app_url="https://app.edvatiq.com",
        expires_minutes=10,
    )

    assert subject == "Verify your email for Edvatiq"
    assert "123456" in text and "expires in 10 minutes" in text
    assert "Edvatiq" in html and "YOUR ONE-TIME CODE" in html
    assert "Valid for 10 minutes" in html
    assert "https://app.edvatiq.com/verify-email" in html
    assert "<img" not in html


def test_resend_auth_email_uses_a_bounded_client_and_idempotency(monkeypatch):
    captured = {}

    def fake_send(payload, options):
        captured.update(payload=payload, options=options)
        return {"id": "email-test-123"}

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "EMAIL_SEND_TIMEOUT_SECONDS", 8)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(settings, "RESEND_FROM_EMAIL", "Edvatiq <no-reply@edvatiq.app>")
    monkeypatch.setattr("app.services.email.resend.Emails.send", fake_send)

    sent = send_auth_code_email(
        "owner@example.com",
        "123456",
        "email_verification",
        idempotency_key="signup-email-challenge-1",
    )

    assert sent is True
    assert captured["payload"]["to"] == ["owner@example.com"]
    assert captured["options"] == {"idempotency_key": "signup-email-challenge-1"}


def test_resend_auth_email_does_not_write_logs_in_serverless(monkeypatch):
    def fail_if_mkdir_is_called(*_args, **_kwargs):
        raise AssertionError("serverless email logging must not touch the application filesystem")

    monkeypatch.setattr(settings, "SERVERLESS_RUNTIME", True)
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(settings, "RESEND_FROM_EMAIL", "Edvatiq <no-reply@edvatiq.app>")
    monkeypatch.setattr("app.services.email.Path.mkdir", fail_if_mkdir_is_called)
    monkeypatch.setattr(
        "app.services.email.resend.Emails.send",
        lambda _payload, _options: {"id": "email-serverless-123"},
    )

    sent = send_auth_code_email(
        "owner@example.com",
        "123456",
        "email_verification",
        idempotency_key="signup-email-serverless",
    )

    assert sent is True


def test_whatsapp_template_payload_is_normalized_and_tracked(monkeypatch):
    captured = {}

    class Response:
        ok = True
        status_code = 200
        content = b"response"

        @staticmethod
        def json():
            return {"messages": [{"id": "wamid.test-123"}]}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, payload=json, timeout=timeout)
        return Response()

    monkeypatch.setattr(settings, "WHATSAPP_TOKEN", "test-token")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "12345")
    monkeypatch.setattr(settings, "WHATSAPP_GRAPH_VERSION", "v23.0")
    monkeypatch.setattr(settings, "WHATSAPP_DEFAULT_COUNTRY_CODE", "91")
    monkeypatch.setattr("app.services.whatsapp.requests.post", fake_post)

    message_id = send_whatsapp_message(
        "98765 43210",
        template_name="appointment_reminder",
        template_language="en",
        template_variables=["Asha", "Edvatiq Fitness", "02 Aug 2026", "09:00 AM", "Main Location"],
    )

    assert normalize_phone("98765 43210") == "919876543210"
    assert message_id == "wamid.test-123"
    assert captured["payload"] == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "919876543210",
        "type": "template",
        "template": {
            "name": "appointment_reminder",
            "language": {"code": "en"},
            "components": [{"type": "body", "parameters": [
                {"type": "text", "text": "Asha"},
                {"type": "text", "text": "Edvatiq Fitness"},
                {"type": "text", "text": "02 Aug 2026"},
                {"type": "text", "text": "09:00 AM"},
                {"type": "text", "text": "Main Location"},
            ]}],
        },
    }
