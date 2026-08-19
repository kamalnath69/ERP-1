"""Shared business-industry semantic execution."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from app.ai.access import AccessEnvelope
from app.ai.catalog import SemanticCatalog
from app.ai.contracts import (
    Artifact, AssistantOutcome, AssistantResponse, FilterOperator, QueryGoal,
    SemanticQuery, Suggestion,
)
from app.ai.domains.common import identifier, json_value, observation, security
from app.models import Appointment, Client, Location, Organization, SaleInvoice, User
from app.services.business_access import filter_clients
from app.services.entity_resolution import resolve_entities, validate_entity_ref


def _apply(statement, expression, operator: FilterOperator, value):
    if operator == FilterOperator.EQ:
        return statement.where(expression == value)
    if operator == FilterOperator.NE:
        return statement.where(expression != value)
    if operator == FilterOperator.GT:
        return statement.where(expression > value)
    if operator == FilterOperator.GTE:
        return statement.where(expression >= value)
    if operator == FilterOperator.LT:
        return statement.where(expression < value)
    if operator == FilterOperator.LTE:
        return statement.where(expression <= value)
    if operator == FilterOperator.CONTAINS:
        return statement.where(func.lower(func.coalesce(expression, "")).contains(str(value).casefold()))
    if operator == FilterOperator.IN:
        return statement.where(expression.in_(value if isinstance(value, list) else [value]))
    if operator == FilterOperator.NOT_IN:
        return statement.where(expression.notin_(value if isinstance(value, list) else [value]))
    if operator == FilterOperator.IS_NULL:
        return statement.where(expression.is_(None) if value is not False else expression.is_not(None))
    return statement


def _client_profile(
    db: Session, user: User, query: SemanticQuery, fields: list[str], unavailable: list[str],
    envelope: AccessEnvelope,
) -> AssistantResponse:
    ref = query.entities[0] if query.entities else None
    selected = None
    if ref and ref.id:
        selected = validate_entity_ref(db, user, "client", ref.id)
    elif ref and ref.label:
        result = resolve_entities(db, user, ref.label, ["client"], 8, include_media=False)
        if result.get("resolution") == "ambiguous":
            clarification_id = identifier("clarify")
            options = result.get("items", [])
            return AssistantResponse(
                outcome=AssistantOutcome.CLARIFICATION,
                answer="I found more than one authorized client. Choose one and I'll continue the original question.",
                artifacts=[Artifact(
                    id=identifier("artifact"), type="clarification", title="Which client did you mean?",
                    data={
                        "clarification_id": clarification_id,
                        "entity_kind": "client",
                        "options": [{
                            "entity": {"kind": "client", "id": item["id"], "label": item["display_name"]},
                            "label": item["display_name"], "meta": item.get("display_meta"),
                        } for item in options],
                    },
                    security=security(
                        permissions=("clients.view",), entity_ids=(item["id"] for item in options),
                    ),
                )], scope=envelope.public_scope(),
            )
        selected = result.get("selected")
    if not selected:
        return AssistantResponse(
            outcome=AssistantOutcome.NOT_FOUND,
            answer="I couldn't find that client in your authorized scope.",
            scope=envelope.public_scope(),
        )
    row = db.get(Client, selected["id"])
    if not row or row.organization_id != envelope.organization_id:
        return AssistantResponse(
            outcome=AssistantOutcome.NOT_FOUND,
            answer="I couldn't find that client in your authorized scope.",
            scope=envelope.public_scope(),
        )
    values = {
        "id": row.id, "name": f"{row.first_name} {row.last_name}".strip(),
        "status": row.status, "client_number": row.client_number,
        "last_visit_at": row.last_visit_at, "email": row.email, "phone": row.phone,
    }
    visible = {key: json_value(value) for key, value in values.items() if key in set(fields) | {"name"}}
    visible["profile_ref"] = {"kind": "client", "id": row.id}
    obs = observation(
        kind="client_profile", entity="client", facts=visible,
        source="Edvatiq client records", source_timestamp=row.updated_at,
        sample_size=1, population_size=1, authorized_scope=envelope.scope_label(1),
    )
    answer = f"{values['name']} is currently marked {row.status} in the client record."
    if row.client_number:
        answer += f" Their approved client number is {row.client_number}."
    if row.last_visit_at and "last_visit_at" in fields:
        answer += f" Their last recorded visit was {row.last_visit_at.date().isoformat()}."
    if unavailable:
        answer += " Fields outside your current access were omitted."
    return AssistantResponse(
        outcome=AssistantOutcome.PARTIAL if unavailable else AssistantOutcome.SUCCESS,
        answer=answer,
        artifacts=[Artifact(
            id=identifier("artifact"), type="profile", title=values["name"],
            data=visible, evidence_ids=[obs.id],
            security=security(permissions=("clients.view",), entity_ids=(row.id,)),
        )],
        suggestions=[Suggestion(
            id=identifier("suggestion"), label="Upcoming appointments",
            prompt="Show this client's upcoming appointments",
            entity_refs=[{"kind": "client", "id": row.id, "label": values["name"]}],
            security=security(
                permissions=("clients.view", "appointments.view"),
                entity_refs=({"kind": "client", "id": row.id, "label": values["name"]},),
            ),
        )] if "appointments.view" in envelope.permissions else [],
        observations=[obs], scope=envelope.public_scope(),
    )


def _client_list(
    db: Session, user: User, query: SemanticQuery, fields: list[str], unavailable: list[str], envelope: AccessEnvelope,
    *, offset: int = 0,
) -> AssistantResponse:
    name = func.trim(Client.first_name + literal(" ") + Client.last_name)
    expressions = {
        "id": Client.id, "name": name, "status": Client.status,
        "client_number": Client.client_number, "last_visit_at": Client.last_visit_at,
    }
    statement = filter_clients(select(
        Client.id.label("id"), name.label("name"), Client.status.label("status"),
        Client.client_number.label("client_number"), Client.last_visit_at.label("last_visit_at"),
        Client.updated_at.label("source_updated_at"),
    ).where(Client.organization_id == envelope.organization_id), db, user, Client)
    for item in query.filters:
        if item.field in expressions:
            statement = _apply(statement, expressions[item.field], item.operator, item.value)
    total = int(db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0)
    order = []
    for item in query.sort:
        expression = expressions.get(item.field)
        if expression is not None:
            order.append((expression.desc() if item.direction == "desc" else expression.asc()).nullslast())
    rows = [{key: json_value(value) for key, value in dict(row._mapping).items()} for row in db.execute(
        statement.order_by(*(order or [func.lower(name), Client.id])).offset(max(offset, 0)).limit(query.limit)
    ).all()]
    if not rows:
        return AssistantResponse(
            outcome=AssistantOutcome.EMPTY, answer="I found no matching clients in your authorized scope.",
            scope=envelope.public_scope(),
        )
    items = []
    for row in rows:
        item = {key: row.get(key) for key in set(fields) | {"name"} if key in row}
        item["profile_ref"] = {"kind": "client", "id": row["id"]}
        items.append(item)
    obs = observation(
        kind="client_records", entity="client", facts={"items": items, "total": total},
        source="Edvatiq client records", sample_size=len(items), population_size=total,
        authorized_scope=envelope.scope_label(total),
    )
    answer = f"I found {total} matching client{'s' if total != 1 else ''} in {envelope.scope_label(total)}."
    if unavailable:
        answer += " Fields outside your current access were omitted."
    return AssistantResponse(
        outcome=AssistantOutcome.PARTIAL if unavailable else AssistantOutcome.SUCCESS,
        answer=answer,
        artifacts=[Artifact(
            id=identifier("artifact"), type="records", title="Clients",
            data={
                "items": items, "total": total,
                "has_more": total > offset + len(items),
                "query": query.model_dump(mode="json"),
            },
            evidence_ids=[obs.id],
            security=security(
                permissions=("clients.view",), entity_ids=(row["id"] for row in rows),
                scope={"population": total},
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _appointments(db: Session, query: SemanticQuery, fields: list[str], envelope: AccessEnvelope, *, offset: int = 0) -> AssistantResponse:
    statement = (
        select(
            Appointment.id.label("id"), Appointment.status.label("status"),
            Appointment.starts_at.label("starts_at"),
            func.trim(Client.first_name + literal(" ") + Client.last_name).label("client"),
            Location.name.label("location"), Appointment.updated_at.label("source_updated_at"),
            Appointment.location_id.label("_location_id"),
            Appointment.client_id.label("_client_id"),
        )
        .join(Client, Client.id == Appointment.client_id)
        .join(Location, Location.id == Appointment.location_id)
        .where(Appointment.organization_id == envelope.organization_id)
    )
    if envelope.location_ids is not None:
        statement = statement.where(Appointment.location_id.in_(envelope.location_ids))
    if envelope.client_ids is not None:
        statement = statement.where(Appointment.client_id.in_(envelope.client_ids))
    expressions = {"id": Appointment.id, "status": Appointment.status, "starts_at": Appointment.starts_at, "client": Client.first_name, "location": Location.name}
    for item in query.filters:
        if item.field in expressions:
            statement = _apply(statement, expressions[item.field], item.operator, item.value)
    total = int(db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0)
    rows = [{key: json_value(value) for key, value in dict(row._mapping).items()} for row in db.execute(
        statement.order_by(Appointment.starts_at.desc()).offset(max(offset, 0)).limit(query.limit)
    ).all()]
    if not rows:
        return AssistantResponse(outcome=AssistantOutcome.EMPTY, answer="I found no matching appointments in your authorized scope.", scope=envelope.public_scope())
    items = []
    for row in rows:
        item = {key: row.get(key) for key in set(fields) if key in row}
        if row.get("_client_id"):
            item["profile_ref"] = {"kind": "client", "id": row["_client_id"]}
        items.append(item)
    obs = observation(kind="appointment_records", entity="appointment", facts={"items": items, "total": total}, source="Edvatiq appointments", sample_size=len(items), population_size=total, authorized_scope=envelope.scope_label(total))
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS,
        answer=f"I found {total} matching appointment{'s' if total != 1 else ''} in {envelope.scope_label(total)}.",
        artifacts=[Artifact(
            id=identifier("artifact"), type="records", title="Appointments",
            data={"items": items, "total": total, "has_more": total > offset + len(items)}, evidence_ids=[obs.id],
            security=security(
                permissions=("appointments.view",), entity_ids=(row["id"] for row in rows),
                scope={
                    "population": total,
                    "location_ids": list(dict.fromkeys(row["_location_id"] for row in rows)),
                    "client_ids": list(dict.fromkeys(row["_client_id"] for row in rows)),
                },
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def _sales(db: Session, query: SemanticQuery, fields: list[str], envelope: AccessEnvelope, *, offset: int = 0) -> AssistantResponse:
    statement = select(
        SaleInvoice.id.label("id"), SaleInvoice.invoice_number.label("invoice_number"),
        SaleInvoice.status.label("status"), SaleInvoice.total_paise.label("total_paise"),
        SaleInvoice.paid_paise.label("paid_paise"), SaleInvoice.issued_at.label("issued_at"),
        Location.name.label("location"), SaleInvoice.updated_at.label("source_updated_at"),
        SaleInvoice.location_id.label("_location_id"),
        SaleInvoice.client_id.label("_client_id"),
    ).join(Location, Location.id == SaleInvoice.location_id).where(
        SaleInvoice.organization_id == envelope.organization_id,
    )
    if envelope.location_ids is not None:
        statement = statement.where(SaleInvoice.location_id.in_(envelope.location_ids))
    if envelope.client_ids is not None:
        statement = statement.where(SaleInvoice.client_id.in_(envelope.client_ids))
    expressions = {
        "id": SaleInvoice.id,
        "invoice_number": SaleInvoice.invoice_number,
        "status": SaleInvoice.status,
        "total_paise": SaleInvoice.total_paise,
        "paid_paise": SaleInvoice.paid_paise,
        "issued_at": SaleInvoice.issued_at,
        "location": Location.name,
        "location_id": SaleInvoice.location_id,
    }
    for item in query.filters:
        if item.field in expressions:
            statement = _apply(statement, expressions[item.field], item.operator, item.value)
    if query.time_window and query.time_window.preset == "current":
        organization = db.get(Organization, envelope.organization_id)
        zone = ZoneInfo(organization.timezone or "Asia/Kolkata")
        local_today = datetime.now(timezone.utc).astimezone(zone).date()
        start = datetime.combine(local_today, time.min, tzinfo=zone).astimezone(timezone.utc)
        end = (datetime.combine(local_today, time.min, tzinfo=zone) + timedelta(days=1)).astimezone(timezone.utc)
        statement = statement.where(SaleInvoice.issued_at >= start, SaleInvoice.issued_at < end)
    total = int(db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0)
    revenue_rows = statement.where(SaleInvoice.status.notin_(("draft", "void"))).order_by(None).subquery()
    revenue = int(db.scalar(select(func.coalesce(func.sum(revenue_rows.c.total_paise), 0))) or 0)
    rows = [{key: json_value(value) for key, value in dict(row._mapping).items()} for row in db.execute(
        statement.order_by(SaleInvoice.issued_at.desc().nullslast()).offset(max(offset, 0)).limit(query.limit)
    ).all()]
    items = []
    for row in rows:
        item = {key: row.get(key) for key in set(fields) if key in row}
        item["profile_ref"] = {"kind": "invoice", "id": row["id"]}
        items.append(item)
    obs = observation(
        kind="sales_summary", entity="sale", facts={"revenue_paise": revenue, "items": items, "total": total},
        source="Edvatiq finalized invoices", sample_size=total, population_size=total,
        definitions={"revenue": "sum of non-draft, non-void invoice totals in the authorized location scope"},
        authorized_scope=envelope.scope_label(total),
    )
    return AssistantResponse(
        outcome=AssistantOutcome.SUCCESS,
        answer=f"Recorded revenue is INR {revenue / 100:,.2f} across {envelope.scope_label(total)}.",
        artifacts=[Artifact(
            id=identifier("artifact"), type="metric", title="Revenue",
            data={
                "revenue_paise": revenue, "items": items, "total": total,
                "has_more": total > offset + len(items),
            }, evidence_ids=[obs.id],
            security=security(
                permissions=("sales.view",), entity_ids=(row["id"] for row in rows),
                scope={
                    "population": total,
                    "location_ids": list(dict.fromkeys(row["_location_id"] for row in rows)),
                    "client_ids": list(dict.fromkeys(row["_client_id"] for row in rows if row["_client_id"])),
                },
            ),
        )], observations=[obs], scope=envelope.public_scope(),
    )


def execute_business_query(
    db: Session, user: User, query: SemanticQuery, catalog: SemanticCatalog,
    envelope: AccessEnvelope,
    *, offset: int = 0,
) -> AssistantResponse:
    envelope.require_query(catalog, query)
    fields, unavailable = envelope.projectable_fields(catalog, query)
    if query.entity == "client":
        if query.goal == QueryGoal.PROFILE:
            return _client_profile(db, user, query, fields, unavailable, envelope)
        return _client_list(db, user, query, fields, unavailable, envelope, offset=offset)
    if query.entity == "appointment":
        return _appointments(db, query, fields, envelope, offset=offset)
    if query.entity == "sale":
        return _sales(db, query, fields, envelope, offset=offset)
    return AssistantResponse(
        outcome=AssistantOutcome.UNSUPPORTED,
        answer="That entity is not registered for this workspace.", scope=envelope.public_scope(),
    )
