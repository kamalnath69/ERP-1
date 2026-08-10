"""Payment mode isolation tests."""
import pytest
from fastapi import HTTPException

from app.api.v1.billing import _payment_config
from app.core.config import settings


def set_credentials(monkeypatch, *, mode: str, test: tuple[str, str, str] = ("", "", ""), live: tuple[str, str, str] = ("", "", "")):
    monkeypatch.setattr(settings, "RAZORPAY_MODE", mode)
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "")
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    monkeypatch.setattr(settings, "RAZORPAY_TEST_KEY_ID", test[0])
    monkeypatch.setattr(settings, "RAZORPAY_TEST_KEY_SECRET", test[1])
    monkeypatch.setattr(settings, "RAZORPAY_TEST_WEBHOOK_SECRET", test[2])
    monkeypatch.setattr(settings, "RAZORPAY_LIVE_KEY_ID", live[0])
    monkeypatch.setattr(settings, "RAZORPAY_LIVE_KEY_SECRET", live[1])
    monkeypatch.setattr(settings, "RAZORPAY_LIVE_WEBHOOK_SECRET", live[2])


def test_test_mode_uses_only_test_credentials(monkeypatch):
    set_credentials(
        monkeypatch,
        mode="test",
        test=("rzp_test_example", "test-secret", "test-webhook"),
        live=("rzp_live_example", "live-secret", "live-webhook"),
    )
    assert _payment_config() == ("test", "rzp_test_example", "test-secret", "test-webhook")


def test_live_mode_uses_only_live_credentials(monkeypatch):
    set_credentials(
        monkeypatch,
        mode="live",
        test=("rzp_test_example", "test-secret", "test-webhook"),
        live=("rzp_live_example", "live-secret", "live-webhook"),
    )
    assert _payment_config() == ("live", "rzp_live_example", "live-secret", "live-webhook")


def test_mode_rejects_mismatched_key(monkeypatch):
    set_credentials(monkeypatch, mode="live", live=("rzp_test_wrong", "secret", "webhook"))
    with pytest.raises(HTTPException) as error:
        _payment_config()
    assert error.value.status_code == 503


def test_webhook_secret_is_required(monkeypatch):
    set_credentials(monkeypatch, mode="test", test=("rzp_test_example", "secret", ""))
    with pytest.raises(HTTPException) as error:
        _payment_config(require_webhook=True)
    assert error.value.status_code == 503


def test_mock_mode_never_loads_credentials(monkeypatch):
    set_credentials(
        monkeypatch,
        mode="mock",
        test=("rzp_test_example", "test-secret", "test-webhook"),
        live=("rzp_live_example", "live-secret", "live-webhook"),
    )
    assert _payment_config() == ("mock", "", "", "")
