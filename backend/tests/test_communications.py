from app.core.config import settings
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
