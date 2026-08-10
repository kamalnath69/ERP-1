"""Small Razorpay REST adapter with bounded, operation-aware recovery."""
from __future__ import annotations

import time
from functools import lru_cache
from typing import Any

import requests


TRANSIENT_STATUSES = {429, 500, 502, 503, 504}


class RazorpayProviderError(Exception):
    def __init__(self, message: str, *, status_code: int = 0, error: dict | None = None, request_id: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error = error or {}
        self.request_id = request_id


class RazorpayProvider:
    def __init__(self, key_id: str, key_secret: str, *, session=None, sleep=time.sleep):
        self.auth = (key_id, key_secret)
        self.session = session or requests.Session()
        self.sleep = sleep
        self.base_url = "https://api.razorpay.com/v1"

    def _request(self, method: str, path: str, *, payload: dict | None = None, params: dict | None = None) -> dict:
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                auth=self.auth,
                json=payload,
                params=params,
                timeout=(5, 20),
                headers={"Accept": "application/json", "User-Agent": "Edvatiq-Billing/2.0"},
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise RazorpayProviderError(
                "Razorpay could not be reached",
                error={"code": "PROVIDER_CONNECTION_ERROR", "description": str(exc)},
            ) from exc

        try:
            body: Any = response.json() if response.content else {}
        except ValueError:
            body = {}
        if 200 <= response.status_code < 300:
            return body if isinstance(body, dict) else {}

        error = body.get("error", {}) if isinstance(body, dict) else {}
        if not isinstance(error, dict):
            error = {"description": str(error)}
        message = str(error.get("description") or f"Razorpay returned HTTP {response.status_code}")
        raise RazorpayProviderError(
            message,
            status_code=response.status_code,
            error=error,
            request_id=response.headers.get("X-Razorpay-Request-Id") or response.headers.get("x-request-id"),
        )

    def create_order(self, payload: dict) -> dict:
        return self._request("POST", "/orders", payload=payload)

    def create_plan(self, payload: dict) -> dict:
        try:
            return self._request("POST", "/plans", payload=payload)
        except RazorpayProviderError as exc:
            if exc.status_code not in TRANSIENT_STATUSES:
                raise
            # Plan creation does not move money. Recover an accepted-but-lost
            # response before making one bounded retry.
            self.sleep(0.5)
            existing = self._find_plan(payload)
            if existing:
                return existing
            self.sleep(0.5)
            return self._request("POST", "/plans", payload=payload)

    def _find_plan(self, expected: dict) -> dict | None:
        try:
            response = self._request("GET", "/plans", params={"count": 100})
        except RazorpayProviderError:
            return None
        expected_item = expected.get("item") or {}
        expected_notes = expected.get("notes") or {}
        for plan in response.get("items", []):
            item = plan.get("item") or {}
            notes = plan.get("notes") or {}
            if (
                plan.get("period") == expected.get("period")
                and int(plan.get("interval") or 0) == int(expected.get("interval") or 0)
                and int(item.get("amount") or 0) == int(expected_item.get("amount") or 0)
                and item.get("currency") == expected_item.get("currency")
                and notes.get("plan_version_id") == expected_notes.get("plan_version_id")
                and notes.get("mode") == expected_notes.get("mode")
            ):
                return plan
        return None

    def create_subscription(self, payload: dict) -> dict:
        return self._request("POST", "/subscriptions", payload=payload)

    def update_subscription(self, subscription_id: str, payload: dict) -> dict:
        return self._request("PATCH", f"/subscriptions/{subscription_id}", payload=payload)

    def cancel_subscription(self, subscription_id: str, payload: dict) -> dict:
        return self._request("POST", f"/subscriptions/{subscription_id}/cancel", payload=payload)

    def fetch_subscription(self, subscription_id: str) -> dict:
        return self._request("GET", f"/subscriptions/{subscription_id}")

    def fetch_payment(self, payment_id: str) -> dict:
        return self._request("GET", f"/payments/{payment_id}")

    def refund_payment(self, payment_id: str, payload: dict) -> dict:
        return self._request("POST", f"/payments/{payment_id}/refund", payload=payload)

    def capture_payment(self, payment_id: str, amount: int, currency: str) -> dict:
        return self._request("POST", f"/payments/{payment_id}/capture", payload={"amount": amount, "currency": currency})


@lru_cache(maxsize=4)
def razorpay_provider(key_id: str, key_secret: str) -> RazorpayProvider:
    return RazorpayProvider(key_id, key_secret)
