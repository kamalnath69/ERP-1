"""Active payment-gateway selection without exposing provider credentials."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import PlatformSetting


SUPPORTED_GATEWAYS = {"razorpay", "cashfree"}


@dataclass(frozen=True)
class GatewayConfig:
    provider: str
    mode: str
    client_id: str
    secret: str
    webhook_secret: str
    configured: bool
    webhook_configured: bool
    recurring_supported: bool

    @property
    def checkout_mode(self) -> str:
        if self.provider == "cashfree":
            return "sandbox" if self.mode == "test" else "production"
        return self.mode

    def public_payload(self, *, active: bool = False) -> dict:
        return {
            "provider": self.provider,
            "mode": self.mode,
            "checkout_mode": self.checkout_mode,
            "configured": self.configured,
            "webhook_configured": self.webhook_configured,
            "recurring_supported": self.recurring_supported,
            "active": active,
        }


def gateway_config(provider: str, mode: str | None = None, *, require_configured: bool = True, require_webhook: bool = False) -> GatewayConfig:
    normalized = str(provider or "").strip().lower()
    if normalized not in SUPPORTED_GATEWAYS:
        raise HTTPException(400, "Unsupported payment gateway")
    selected_mode = mode or (settings.RAZORPAY_MODE if normalized == "razorpay" else settings.CASHFREE_MODE)
    if selected_mode not in {"mock", "test", "live"}:
        raise HTTPException(503, "The payment gateway mode is invalid")
    if normalized == "razorpay":
        client_id, secret, webhook_secret = settings.razorpay_credentials(selected_mode)
        credentials_valid = bool(client_id and secret and client_id.startswith(f"rzp_{selected_mode}_"))
        recurring_supported = True
    else:
        client_id, secret, webhook_secret = settings.cashfree_credentials(selected_mode)
        credentials_valid = bool(client_id and secret)
        recurring_supported = False
    configured = (selected_mode == "mock" and settings.ENVIRONMENT != "production") or credentials_valid
    webhook_configured = (selected_mode == "mock" and settings.ENVIRONMENT != "production") or bool(webhook_secret)
    config = GatewayConfig(
        provider=normalized,
        mode=selected_mode,
        client_id=client_id,
        secret=secret,
        webhook_secret=webhook_secret,
        configured=configured,
        webhook_configured=webhook_configured,
        recurring_supported=recurring_supported,
    )
    if require_configured and not configured:
        raise HTTPException(503, f"{normalized.title()} {selected_mode} payments are not configured")
    if require_webhook and not webhook_configured:
        raise HTTPException(503, f"The {normalized.title()} {selected_mode} webhook is not configured")
    return config


def selected_gateway_provider(db: Session) -> str:
    row = db.execute(select(PlatformSetting).where(PlatformSetting.key == "payment_gateway")).scalar_one_or_none()
    provider = str((row.value if row else {}).get("provider") or settings.PAYMENT_GATEWAY).strip().lower()
    return provider if provider in SUPPORTED_GATEWAYS else settings.PAYMENT_GATEWAY


def active_gateway(db: Session, *, require_configured: bool = True, require_webhook: bool = False) -> GatewayConfig:
    return gateway_config(
        selected_gateway_provider(db),
        require_configured=require_configured,
        require_webhook=require_webhook,
    )


def gateway_inventory(db: Session) -> dict:
    active = selected_gateway_provider(db)
    providers = [
        gateway_config(provider, require_configured=False).public_payload(active=provider == active)
        for provider in sorted(SUPPORTED_GATEWAYS)
    ]
    current = next(item for item in providers if item["provider"] == active)
    return {**current, "providers": providers}
