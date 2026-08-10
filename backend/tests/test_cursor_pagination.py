import uuid

import pytest
from fastapi import HTTPException

from app.services import cursor_pagination
from app.services.cursor_pagination import (
    decode_cursor,
    decode_cursor_or_legacy_id,
    encode_cursor,
    page_response,
    page_size,
)


def test_cursor_round_trip_is_bound_to_scope_tenant_and_filters():
    token = encode_cursor(
        scope="college.students",
        organization_id="org-a",
        filters={"q": "kavya", "cohort_id": "cohort-a"},
        values={"at": "2026-08-10T12:00:00+00:00", "id": "row-a"},
    )

    assert decode_cursor(
        token,
        scope="college.students",
        organization_id="org-a",
        filters={"cohort_id": "cohort-a", "q": "kavya"},
    ) == {"at": "2026-08-10T12:00:00+00:00", "id": "row-a"}

    for overrides in (
        {"scope": "college.applications"},
        {"organization_id": "org-b"},
        {"filters": {"q": "different"}},
    ):
        arguments = {
            "scope": "college.students",
            "organization_id": "org-a",
            "filters": {"q": "kavya", "cohort_id": "cohort-a"},
            **overrides,
        }
        with pytest.raises(HTTPException) as error:
            decode_cursor(token, **arguments)
        assert error.value.status_code == 422


def test_cursor_rejects_tampering_and_malformed_values():
    token = encode_cursor(
        scope="clients.directory",
        organization_id="org-a",
        values={"id": "row-a"},
    )
    replacement = "A" if token[-1] != "A" else "B"

    for value in (token[:-1] + replacement, "not-a-cursor"):
        with pytest.raises(HTTPException) as error:
            decode_cursor(value, scope="clients.directory", organization_id="org-a")
        assert error.value.status_code == 422


def test_cursor_signature_can_safely_contain_the_payload_separator(monkeypatch):
    signature_with_separator = b"safe.signature!!"
    assert len(signature_with_separator) == cursor_pagination.SIGNATURE_BYTES
    monkeypatch.setattr(cursor_pagination, "_signature", lambda _payload: signature_with_separator)

    token = encode_cursor(
        scope="ai.messages:chat-a",
        organization_id="org-a",
        values={"at": "2026-08-10T12:00:00+00:00", "id": "message-a"},
    )

    assert decode_cursor(
        token,
        scope="ai.messages:chat-a",
        organization_id="org-a",
    ) == {"at": "2026-08-10T12:00:00+00:00", "id": "message-a"}


def test_legacy_uuid_cursor_is_temporarily_supported():
    legacy_id = str(uuid.uuid4())
    assert decode_cursor_or_legacy_id(
        legacy_id,
        scope="clients.directory",
        organization_id="org-a",
    ) == {"id": legacy_id, "legacy": True}

    with pytest.raises(HTTPException) as error:
        decode_cursor_or_legacy_id(
            "invalid",
            scope="clients.directory",
            organization_id="org-a",
        )
    assert error.value.status_code == 422


def test_page_helpers_apply_safe_limits_and_explicit_shape():
    assert page_size(0) == 1
    assert page_size(1000) == 100
    assert page_response([{"id": "one"}], "next") == {
        "items": [{"id": "one"}],
        "next_cursor": "next",
        "has_more": True,
    }
