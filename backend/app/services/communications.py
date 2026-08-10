"""Durable, consent-aware client communication queuing."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.models import Job, OutboundMessage


def queue_whatsapp_template(
    db,
    *,
    organization,
    client,
    location_id: str | None,
    template: str,
    variables: list[str],
    body: str,
    idempotency_key: str,
    run_at: datetime | None = None,
) -> OutboundMessage | None:
    if not client.whatsapp_consent or not client.phone:
        return None
    existing = db.execute(select(OutboundMessage).where(
        OutboundMessage.organization_id == organization.id,
        OutboundMessage.idempotency_key == idempotency_key,
    )).scalar_one_or_none()
    if existing:
        return existing
    now = run_at or datetime.now(timezone.utc)
    message = OutboundMessage(
        organization_id=organization.id, location_id=location_id, client_id=client.id,
        channel="whatsapp", recipient=client.phone, template=template,
        template_language=settings.WHATSAPP_TEMPLATE_LANGUAGE,
        template_variables=[str(value) for value in variables], body=body,
        scheduled_for=now, idempotency_key=idempotency_key,
    )
    db.add(message)
    db.flush()
    db.add(Job(
        organization_id=organization.id, kind="send_message", payload={"message_id": message.id},
        run_at=now, idempotency_key=f"send-{message.id}",
    ))
    return message
