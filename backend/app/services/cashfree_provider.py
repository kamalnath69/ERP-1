"""Cashfree Payments REST adapter with bounded network behavior."""
from __future__ import annotations

import base64
import hashlib
import hmac
from functools import lru_cache
from typing import Any
from uuid import uuid4

import requests


def cashfree_webhook_signature(payload: bytes, timestamp: str, secret: str) -> str:
    return base64.b64encode(
        hmac.new(secret.encode(), timestamp.encode() + payload, hashlib.sha256).digest()
    ).decode()


def valid_cashfree_webhook_signature(payload: bytes, timestamp: str, signature: str, secret: str) -> bool:
    return bool(signature) and hmac.compare_digest(
        cashfree_webhook_signature(payload, timestamp, secret), signature,
    )


def cashfree_refund_state(provider_status: str | None) -> str:
    """Map Cashfree's refund lifecycle onto the platform refund lifecycle."""
    status = str(provider_status or "").strip().upper()
    if status == "SUCCESS":
        return "processed"
    if status in {"CANCELLED", "FAILED"}:
        return "failed"
    # PENDING and ONHOLD must reserve the refundable balance until a terminal webhook.
    return "approved"


class CashfreeProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        error: dict | None = None,
        request_id: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error = error or {}
        self.request_id = request_id


class CashfreeProvider:
    def __init__(self, app_id: str, secret_key: str, mode: str, api_version: str, *, session=None):
        self.app_id = app_id
        self.secret_key = secret_key
        self.mode = mode
        self.api_version = api_version
        self.session = session or requests.Session()
        self.base_url = "https://sandbox.cashfree.com/pg" if mode == "test" else "https://api.cashfree.com/pg"

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        idempotency_key: str | None = None,
    ) -> dict | list:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Edvatiq-Billing/3.0",
            "x-api-version": self.api_version,
            "x-client-id": self.app_id,
            "x-client-secret": self.secret_key,
            "x-request-id": str(uuid4()),
        }
        if idempotency_key:
            headers["x-idempotency-key"] = idempotency_key
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                json=payload,
                timeout=(5, 20),
                headers=headers,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise CashfreeProviderError(
                "Cashfree could not be reached",
                error={"code": "PROVIDER_CONNECTION_ERROR", "description": str(exc)},
            ) from exc

        try:
            body: Any = response.json() if response.content else {}
        except ValueError:
            body = {}
        if 200 <= response.status_code < 300:
            return body if isinstance(body, (dict, list)) else {}

        error = body if isinstance(body, dict) else {}
        message = str(
            error.get("message")
            or error.get("type")
            or error.get("code")
            or f"Cashfree returned HTTP {response.status_code}"
        )
        raise CashfreeProviderError(
            message,
            status_code=response.status_code,
            error={
                "code": error.get("code") or error.get("type"),
                "description": error.get("message") or message,
            },
            request_id=response.headers.get("x-request-id") or response.headers.get("x-cf-request-id"),
        )

    def create_order(self, payload: dict, *, idempotency_key: str) -> dict:
        result = self._request("POST", "/orders", payload=payload, idempotency_key=idempotency_key)
        return result if isinstance(result, dict) else {}

    def fetch_order(self, order_id: str) -> dict:
        result = self._request("GET", f"/orders/{order_id}")
        return result if isinstance(result, dict) else {}

    def fetch_payments(self, order_id: str) -> list[dict]:
        result = self._request("GET", f"/orders/{order_id}/payments")
        return [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []

    def refund_order(self, order_id: str, payload: dict, *, idempotency_key: str) -> dict:
        result = self._request(
            "POST",
            f"/orders/{order_id}/refunds",
            payload=payload,
            idempotency_key=idempotency_key,
        )
        if isinstance(result, dict):
            return result
        if isinstance(result, list) and result and isinstance(result[0], dict):
            return result[0]
        return {}


@lru_cache(maxsize=6)
def cashfree_provider(app_id: str, secret_key: str, mode: str, api_version: str) -> CashfreeProvider:
    return CashfreeProvider(app_id, secret_key, mode, api_version)
