"""Structured user-correctable API validation errors."""
from __future__ import annotations

from collections.abc import Mapping


class ValidationProblem(Exception):
    def __init__(
        self,
        *,
        field_errors: Mapping[str, str | list[str]] | None = None,
        form_errors: list[str] | None = None,
        message: str = "Please correct the highlighted fields.",
        status_code: int = 422,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.field_errors = {
            str(path): [str(item) for item in (messages if isinstance(messages, list) else [messages])]
            for path, messages in (field_errors or {}).items()
        }
        self.form_errors = [str(item) for item in (form_errors or [])]


def validation_problem(field: str, message: str) -> ValidationProblem:
    return ValidationProblem(field_errors={field: [message]})
