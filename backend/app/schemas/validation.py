"""Reusable validation primitives for browser-facing request contracts."""
from __future__ import annotations

import re
from types import NoneType
from typing import Annotated, Any, get_args

from pydantic import BaseModel, BeforeValidator, ConfigDict, ValidationInfo, field_validator


def _strip_text(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _blank_to_none(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    return normalized or None


TrimmedStr = Annotated[str, BeforeValidator(_strip_text)]
OptionalTrimmedStr = Annotated[str | None, BeforeValidator(_blank_to_none)]


class RequestModel(BaseModel):
    """Strict base for JSON bodies controlled by the Edvatiq browser client."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before", check_fields=False)
    @classmethod
    def normalize_ordinary_fields(cls, value: Any, info: ValidationInfo) -> Any:
        field_name = info.field_name or ""
        sensitive = any(marker in field_name for marker in (
            "password", "token", "secret", "signature", "mfa_code", "api_key",
        ))
        if sensitive or not isinstance(value, str):
            return value

        normalized = value.strip()
        field = cls.model_fields.get(field_name)
        if field and not normalized:
            allows_none = field.annotation is NoneType or NoneType in get_args(field.annotation)
            if allows_none:
                return None
            if field.is_required():
                label = field_name.replace("_", " ").capitalize()
                raise ValueError(f"{label} is required")
        if len(normalized) > 20_000:
            raise ValueError("Value must be 20000 characters or fewer")
        return normalized


def valid_phone(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    digits = re.sub(r"\D", "", normalized)
    if not 7 <= len(digits) <= 15 or not re.fullmatch(r"[+\d()\-.\s]+", normalized):
        raise ValueError("Enter a valid phone number")
    return normalized


def non_blank(value: str, label: str = "Value") -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized
