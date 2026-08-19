"""Validated semantic execution entry point."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.access import AccessEnvelope, AccessViolation
from app.ai.catalog import CatalogError, SemanticCatalog
from app.ai.contracts import AssistantOutcome, AssistantResponse, SemanticQuery
from app.ai.definitions import semantic_definitions
from app.ai.domains.business import execute_business_query
from app.ai.domains.college import execute_college_query
from app.ai.presentation import decorate_response, normalize_student_navigation_refs
from app.models import User


def _interactive_statement_limit(db: Session) -> None:
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(text("SET LOCAL statement_timeout = '2000ms'"))


def execute_semantic_query(
    db: Session,
    user: User,
    query: SemanticQuery,
    catalog: SemanticCatalog,
    envelope: AccessEnvelope,
    *,
    offset: int = 0,
    background: bool = False,
) -> AssistantResponse:
    """Validate and execute one query using the caller's existing DB session."""
    try:
        catalog.validate(query)
        envelope.require_query(catalog, query)
        if not background:
            _interactive_statement_limit(db)
        if envelope.industry == "college":
            response = execute_college_query(
                db, user, query, catalog, envelope,
                semantic_definitions(db, envelope.organization_id),
                offset=offset, background=background,
            )
            response = response.model_copy(update={
                "artifacts": normalize_student_navigation_refs(
                    db, envelope.organization_id, response.artifacts,
                ),
            })
        else:
            response = execute_business_query(
                db, user, query, catalog, envelope, offset=offset,
            )
        return decorate_response(response, query, catalog)
    except AccessViolation as exc:
        return AssistantResponse(
            outcome=exc.outcome, answer=exc.message, scope=envelope.public_scope(),
        )
    except CatalogError:
        return AssistantResponse(
            outcome=AssistantOutcome.UNSUPPORTED,
            answer="That request uses a field or metric that is not registered in the approved assistant catalog.",
            scope=envelope.public_scope(),
        )
