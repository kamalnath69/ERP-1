"""Catalog-governed assistant presentation and internal-ID redaction."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.catalog import CatalogError, SemanticCatalog
from app.ai.contracts import (
    Artifact, ArtifactPresentation, AssistantResponse, PresentationField,
    SemanticQuery,
)
from app.models import CollegeStudentProfile


UUID_PATTERN = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
)

CONTROL_OBJECT_KEYS = {
    "profile_ref", "selection_ref", "entity", "query", "query_spec",
}
CONTROL_VALUE_KEYS = {
    "action_id", "clarification_id", "confirmation_token", "job_id",
    "result_session_id", "undo_token",
}
STRUCTURAL_KEYS = {
    "avatar_url", "columns", "count_is_exact", "fields", "group", "groups",
    "has_more", "items", "metrics", "next_cursor", "population",
    "profile_ref", "query", "query_spec", "rank", "scope_label", "total",
    "values",
}
LAYOUTS = {
    "profile": "profile", "records": "cards", "ranking": "ranking",
    "comparison": "comparison", "metric": "metrics", "chart": "chart",
    "sources": "sources", "notice": "notice", "clarification": "clarification",
    "action": "action", "processing": "processing",
}


def redact_internal_identifiers(text: str) -> str:
    """Ensure accidental database UUIDs never reach user-visible prose."""
    return UUID_PATTERN.sub("record", str(text or ""))


def _internal_key(key: str) -> bool:
    normalized = str(key or "").casefold()
    return (
        normalized == "id"
        or normalized.endswith("_id")
        or normalized.startswith("_")
    )


def sanitize_display_data(value: Any, *, preserve_controls: bool = True) -> Any:
    """Remove storage identifiers while retaining non-rendered interaction metadata."""
    if isinstance(value, dict):
        cleaned = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if preserve_controls and key in CONTROL_OBJECT_KEYS:
                cleaned[key] = item
                continue
            if preserve_controls and key in CONTROL_VALUE_KEYS:
                cleaned[key] = item
                continue
            if _internal_key(key):
                continue
            cleaned[key] = sanitize_display_data(
                item, preserve_controls=preserve_controls,
            )
        return cleaned
    if isinstance(value, (list, tuple)):
        return [
            sanitize_display_data(item, preserve_controls=preserve_controls)
            for item in value
        ]
    return value


def _student_profile_ids(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        ref = value.get("profile_ref")
        if isinstance(ref, dict) and ref.get("kind") == "student" and ref.get("id"):
            result.add(str(ref["id"]))
        for item in value.values():
            result.update(_student_profile_ids(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            result.update(_student_profile_ids(item))
    return result


def _replace_student_profile_refs(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key == "profile_ref" and isinstance(item, dict) and item.get("kind") == "student":
                client_id = mapping.get(str(item.get("id") or ""))
                if client_id:
                    cleaned[key] = {"kind": "client", "id": client_id}
                continue
            cleaned[key] = _replace_student_profile_refs(item, mapping)
        return cleaned
    if isinstance(value, list):
        return [_replace_student_profile_refs(item, mapping) for item in value]
    if isinstance(value, tuple):
        return [_replace_student_profile_refs(item, mapping) for item in value]
    return value


def normalize_student_navigation_refs(
    db: Session,
    organization_id: str,
    artifacts: list[Artifact],
) -> list[Artifact]:
    """Translate private academic IDs into tenant-scoped client navigation refs."""
    student_ids: set[str] = set()
    for artifact in artifacts:
        student_ids.update(_student_profile_ids(artifact.data))
    if not student_ids:
        return artifacts
    mapping = dict(db.execute(select(
        CollegeStudentProfile.id,
        CollegeStudentProfile.client_id,
    ).where(
        CollegeStudentProfile.organization_id == organization_id,
        CollegeStudentProfile.id.in_(student_ids),
    )).all())
    return [artifact.model_copy(update={
        "data": _replace_student_profile_refs(artifact.data, mapping),
    }) for artifact in artifacts]


def _artifact_keys(artifact: Artifact) -> set[str]:
    data = artifact.data or {}
    keys = set(data)
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        keys.update(item)
        if isinstance(item.get("values"), dict):
            keys.update(item["values"])
    for item in data.get("groups") or []:
        if not isinstance(item, dict):
            continue
        keys.update(item)
        if isinstance(item.get("values"), dict):
            keys.update(item["values"])
    keys.update(key for key in data.get("fields") or [] if isinstance(key, str))
    keys.update(key for key in data.get("metrics") or [] if isinstance(key, str))
    return keys


def _field_spec(catalog: SemanticCatalog, entity: str, key: str) -> PresentationField | None:
    candidates = [entity]
    if catalog.industry == "college" and entity in {"department", "cohort"}:
        candidates.append("student")
    candidates.extend(
        candidate for candidate in catalog.entities
        if candidate not in candidates
    )
    for candidate in candidates:
        try:
            definition = catalog.field(candidate, key)
        except CatalogError:
            continue
        if definition.visibility != "display" or not definition.projectable:
            return None
        return PresentationField(
            key=key, label=definition.label, format=definition.display_format,
            group=definition.display_group, role=definition.display_role,
            priority=definition.display_priority,
        )
    return None


def _metric_specs(
    catalog: SemanticCatalog, query: SemanticQuery, keys: set[str],
) -> list[PresentationField]:
    result = []
    for metric_key in query.metrics:
        try:
            metric = catalog.metric(metric_key)
        except CatalogError:
            continue
        data_key = metric_key
        if metric_key == "revenue" and "revenue_paise" in keys:
            data_key = "revenue_paise"
        result.append(PresentationField(
            key=data_key, label=metric.label, format=metric.display_format,
            group="Analysis", role="metric", priority=metric.display_priority,
        ))
    return result


def build_presentation(
    artifact: Artifact, query: SemanticQuery, catalog: SemanticCatalog,
) -> ArtifactPresentation:
    keys = _artifact_keys(artifact)
    fields: list[PresentationField] = []
    seen = set()
    for key in keys:
        if key in STRUCTURAL_KEYS or _internal_key(key):
            continue
        spec = _field_spec(catalog, query.entity, key)
        if spec:
            fields.append(spec)
            seen.add(spec.key)
    if artifact.type == "comparison" and isinstance(artifact.data.get("metrics"), list):
        for key in query.fields:
            if key in seen or _internal_key(key):
                continue
            spec = _field_spec(catalog, query.entity, key)
            if spec:
                fields.append(spec)
                seen.add(spec.key)
    if "group" in keys:
        label = "Group"
        if query.group_by:
            try:
                label = catalog.field(query.entity, query.group_by[0]).label
            except CatalogError:
                pass
        fields.append(PresentationField(
            key="group", label=label, format="text", group="Comparison",
            role="title", priority=0,
        ))
        seen.add("group")
    for spec in _metric_specs(catalog, query, keys):
        if spec.key not in seen:
            fields.append(spec)
            seen.add(spec.key)
    fields.sort(key=lambda item: (
        0 if item.role == "title" else 1 if item.role == "subtitle" else 2,
        item.priority, item.label.casefold(),
    ))
    return ArtifactPresentation(
        layout=LAYOUTS[artifact.type], entity=query.entity,
        fields=fields,
        preview_limit=4 if artifact.type in {"records", "ranking"} else None,
    )


def decorate_artifact(
    artifact: Artifact, query: SemanticQuery, catalog: SemanticCatalog,
) -> Artifact:
    sanitized = sanitize_display_data(artifact.data)
    current = artifact.model_copy(update={
        "title": redact_internal_identifiers(artifact.title or "") or None,
        "data": sanitized,
    })
    return current.model_copy(update={
        "presentation": build_presentation(current, query, catalog),
    })


def decorate_response(
    response: AssistantResponse, query: SemanticQuery, catalog: SemanticCatalog,
) -> AssistantResponse:
    """Apply the display allowlist before synthesis, storage, or transport."""
    artifacts = [decorate_artifact(item, query, catalog) for item in response.artifacts]
    observations = [item.model_copy(update={
        "facts": sanitize_display_data(item.facts, preserve_controls=False),
    }) for item in response.observations]
    suggestions = [item.model_copy(update={
        "label": redact_internal_identifiers(item.label),
        "prompt": redact_internal_identifiers(item.prompt),
    }) for item in response.suggestions]
    return response.model_copy(update={
        "answer": redact_internal_identifiers(response.answer),
        "artifacts": artifacts,
        "observations": observations,
        "suggestions": suggestions,
    })
