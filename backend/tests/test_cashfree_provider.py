"""Cashfree adapter and payment verification contracts."""
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services.billing import create_provider_order, verify_provider_payment
from app.services.cashfree_provider import (
    CashfreeProvider, CashfreeProviderError, cashfree_refund_state, cashfree_webhook_signature,
    valid_cashfree_webhook_signature,
)
from app.services.payment_gateways import GatewayConfig


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.content = b"{}"

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def test_cashfree_create_order_uses_sandbox_headers_and_idempotency():
    session = FakeSession([FakeResponse(body={"order_id": "edv_order", "payment_session_id": "session"})])
    provider = CashfreeProvider("test-app", "test-secret", "test", "2025-01-01", session=session)

    result = provider.create_order({"order_id": "edv_order"}, idempotency_key="checkout-key")

    assert result["payment_session_id"] == "session"
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url == "https://sandbox.cashfree.com/pg/orders"
    assert kwargs["headers"]["x-client-id"] == "test-app"
    assert kwargs["headers"]["x-client-secret"] == "test-secret"
    assert kwargs["headers"]["x-api-version"] == "2025-01-01"
    assert kwargs["headers"]["x-idempotency-key"] == "checkout-key"
    assert kwargs["timeout"] == (5, 20)


def test_cashfree_provider_surfaces_sanitized_api_error():
    session = FakeSession([FakeResponse(
        status_code=401,
        body={"type": "authentication_error", "message": "Invalid API credentials"},
        headers={"x-request-id": "request-1"},
    )])
    provider = CashfreeProvider("bad-app", "bad-secret", "live", "2025-01-01", session=session)

    with pytest.raises(CashfreeProviderError) as error:
        provider.fetch_order("order-1")

    assert error.value.status_code == 401
    assert error.value.request_id == "request-1"
    assert error.value.error["code"] == "authentication_error"


def test_cashfree_webhook_signature_uses_timestamp_and_untouched_body():
    payload = b'{"data":{"order":{"order_id":"edv_1"}}}'
    signature = cashfree_webhook_signature(payload, "1786543200000", "secret-key")

    assert valid_cashfree_webhook_signature(payload, "1786543200000", signature, "secret-key")
    assert not valid_cashfree_webhook_signature(payload + b" ", "1786543200000", signature, "secret-key")


@pytest.mark.parametrize(
    ("provider_status", "platform_status"),
    [
        ("SUCCESS", "processed"),
        ("PENDING", "approved"),
        ("ONHOLD", "approved"),
        ("FAILED", "failed"),
        ("CANCELLED", "failed"),
    ],
)
def test_cashfree_refund_states_reserve_non_terminal_refunds(provider_status, platform_status):
    assert cashfree_refund_state(provider_status) == platform_status


def test_cashfree_order_requires_a_checkout_session(monkeypatch):
    class Provider:
        def create_order(self, _payload, *, idempotency_key):
            assert idempotency_key == "checkout-key"
            return {"order_id": "edv_order"}

    monkeypatch.setattr("app.services.billing.cashfree_provider", lambda *_args: Provider())
    config = GatewayConfig(
        provider="cashfree",
        mode="test",
        client_id="test-app",
        secret="test-secret",
        webhook_secret="test-secret",
        configured=True,
        webhook_configured=True,
        recurring_supported=False,
    )

    with pytest.raises(HTTPException) as error:
        create_provider_order(
            config,
            reference_id="invoice-id",
            amount_paise=49900,
            currency="INR",
            customer={"id": "customer", "phone": "9876543210"},
            notes={"description": "Test checkout"},
            idempotency_key="checkout-key",
        )

    assert error.value.status_code == 502
    assert error.value.detail == "Cashfree did not return a checkout session"


def test_cashfree_verification_requires_paid_order_and_successful_payment(monkeypatch):
    monkeypatch.setattr(settings, "CASHFREE_MODE", "test")
    monkeypatch.setattr(settings, "CASHFREE_TEST_APP_ID", "test-app")
    monkeypatch.setattr(settings, "CASHFREE_TEST_SECRET_KEY", "test-secret")

    class Provider:
        def fetch_order(self, order_id):
            return {"order_id": order_id, "order_amount": 499, "order_currency": "INR", "order_status": "PAID"}

        def fetch_payments(self, _order_id):
            return [{"cf_payment_id": 12345, "payment_status": "SUCCESS", "payment_amount": 499, "payment_group": "upi"}]

    monkeypatch.setattr("app.services.billing.cashfree_provider", lambda *_args: Provider())
    result = verify_provider_payment(
        provider="cashfree",
        mode="test",
        order_id="edv_order",
        amount_paise=49900,
        currency="INR",
    )

    assert result == {"status": "paid", "payment_id": "12345", "method": "upi"}


def test_cashfree_verification_does_not_trust_mismatched_amount(monkeypatch):
    monkeypatch.setattr(settings, "CASHFREE_MODE", "test")
    monkeypatch.setattr(settings, "CASHFREE_TEST_APP_ID", "test-app")
    monkeypatch.setattr(settings, "CASHFREE_TEST_SECRET_KEY", "test-secret")

    class Provider:
        def fetch_order(self, order_id):
            return {"order_id": order_id, "order_amount": 1, "order_currency": "INR", "order_status": "PAID"}

    monkeypatch.setattr("app.services.billing.cashfree_provider", lambda *_args: Provider())
    with pytest.raises(HTTPException) as error:
        verify_provider_payment(
            provider="cashfree",
            mode="test",
            order_id="edv_order",
            amount_paise=49900,
            currency="INR",
        )

    assert error.value.status_code == 409
