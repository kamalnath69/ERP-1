"""Shared helpers for typed assistant evidence and artifacts."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from app.ai.contracts import ArtifactSecurity, EntityRef, Observation


COLLEGE_DOMAIN_VIEW_PERMISSIONS = {
    "students": "college.students.view",
    "academics": "college.academics.view",
    "assessments": "college.assessments.view",
    "attendance": "college.attendance.view",
    "readiness": "college.readiness.view",
    "coding": "college.coding.view",
    "placements": "college.placements.view",
    "documents": "documents.view",
    "clearance": "college.clearance.view",
}


def identifier(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def security(
    *, permissions=(), domains=(), entity_ids=(), entity_refs=(), scope=None,
) -> ArtifactSecurity:
    domains = tuple(domains)
    required_permissions = set(permissions)
    required_permissions.update(
        COLLEGE_DOMAIN_VIEW_PERMISSIONS[domain]
        for domain in domains
        if domain in COLLEGE_DOMAIN_VIEW_PERMISSIONS
    )
    refs: list[EntityRef] = []
    seen_refs: set[tuple[str, str | None]] = set()
    for item in entity_refs:
        ref = item if isinstance(item, EntityRef) else EntityRef.model_validate(item)
        key = (ref.kind, ref.id)
        if key not in seen_refs:
            refs.append(ref)
            seen_refs.add(key)
        if len(refs) == 500:
            break
    return ArtifactSecurity(
        permissions=sorted(required_permissions),
        domains=sorted(set(domains)),
        entity_ids=list(dict.fromkeys(str(item) for item in entity_ids if item))[:500],
        entity_refs=refs,
        scope=scope or {},
    )


def observation(
    *, kind: str, entity: str, facts: dict, source: str,
    authorized_scope: str, source_timestamp=None, sample_size=None,
    population_size=None, coverage_percent=None, definitions=None,
) -> Observation:
    return Observation(
        id=identifier("obs"), kind=kind, entity=entity,
        facts=json_value(facts), source=source,
        source_timestamp=source_timestamp, sample_size=sample_size,
        population_size=population_size, coverage_percent=coverage_percent,
        definitions=definitions or {}, authorized_scope=authorized_scope,
    )
