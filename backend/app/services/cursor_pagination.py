"""Opaque, tenant-bound cursors for stable keyset pagination."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from typing import Any

from fastapi import HTTPException, status

from app.core.config import settings


CURSOR_VERSION = 1
SIGNATURE_BYTES = 16


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _filter_hash(filters: dict | None) -> str:
    normalized = {
        key: value for key, value in (filters or {}).items()
        if value not in (None, "", [], {}, "all")
    }
    return hashlib.sha256(_canonical(normalized).encode("utf-8")).hexdigest()[:20]


def _signature(payload: bytes) -> bytes:
    return hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).digest()[:SIGNATURE_BYTES]


def encode_cursor(
    *,
    scope: str,
    organization_id: str,
    values: dict[str, Any],
    filters: dict | None = None,
) -> str:
    payload = _canonical({
        "v": CURSOR_VERSION,
        "scope": scope,
        "org": organization_id,
        "filters": _filter_hash(filters),
        "values": values,
    }).encode("utf-8")
    token = base64.urlsafe_b64encode(payload + b"." + _signature(payload)).decode("ascii")
    return token.rstrip("=")


def decode_cursor(
    cursor: str | None,
    *,
    scope: str,
    organization_id: str,
    filters: dict | None = None,
) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        separator_at = -(SIGNATURE_BYTES + 1)
        if len(decoded) <= SIGNATURE_BYTES or decoded[separator_at:separator_at + 1] != b".":
            raise ValueError("structure")
        payload = decoded[:separator_at]
        signature = decoded[-SIGNATURE_BYTES:]
        if not hmac.compare_digest(signature, _signature(payload)):
            raise ValueError("signature")
        data = json.loads(payload.decode("utf-8"))
        if data.get("v") != CURSOR_VERSION:
            raise ValueError("version")
        if data.get("scope") != scope or data.get("org") != organization_id:
            raise ValueError("scope")
        if data.get("filters") != _filter_hash(filters):
            raise ValueError("filters")
        values = data.get("values")
        if not isinstance(values, dict):
            raise ValueError("values")
        return values
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "The pagination cursor is invalid or no longer matches these filters",
        ) from exc


def decode_cursor_or_legacy_id(
    cursor: str | None,
    *,
    scope: str,
    organization_id: str,
    filters: dict | None = None,
) -> dict[str, Any] | None:
    """Accept one release of UUID cursors while all clients move to opaque cursors."""
    if not cursor:
        return None
    try:
        return decode_cursor(
            cursor,
            scope=scope,
            organization_id=organization_id,
            filters=filters,
        )
    except HTTPException as cursor_error:
        try:
            return {"id": str(uuid.UUID(cursor)), "legacy": True}
        except (ValueError, TypeError, AttributeError):
            raise cursor_error


def page_size(limit: int, *, default: int = 25, maximum: int = 100) -> int:
    value = limit if limit is not None else default
    return min(max(int(value), 1), maximum)


def page_response(items: list[dict], next_cursor: str | None) -> dict:
    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_more": bool(next_cursor),
    }
