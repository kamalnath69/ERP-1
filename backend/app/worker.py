"""PostgreSQL-backed durable job worker. Run with: python -m app.worker"""
import io
import logging
import time
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, func, or_, select

from app.core.config import ROOT_DIR, settings
from app.core.database import SessionLocal
from app.services.email import send_email
from app.services.communications import queue_whatsapp_template
from app.services.whatsapp import send_whatsapp_message
from app.services.realtime import publish_change
from app.models import (
    AIResultSession, AIUsage, AIWallet, Appointment, ApprovalRequest, ChatConversation, Client, Document, DocumentChunk, Job, Location,
    CollegeCodingAccount, CollegeDataConnector,
    Membership, MembershipPlan, Organization,
    OrganizationDeletionRequest, OrganizationEntitlementOverride, OutboundMessage,
    PaymentEvent, RetentionArchive, Subscription, SubscriptionSchedule, SupportSession,
)

_last_maintenance = None
logger = logging.getLogger("edvatiq.worker")

JOB_CHANGE_PATHS = {
    "send_message": "/notifications",
    "process_document": "/documents",
    "refresh_client_signals": "/client-signals",
    "replay_payment_webhook": "/billing",
    "subscription_transition": "/billing",
    "college_erp_sync": "/college/imports",
    "college_coding_sync": "/college/coding",
    "college_resume_extract": "/college/students",
    "college_readiness_recompute": "/college/placement-dashboard",
    "data_exchange_validate": "/data-exchange/runs",
    "data_exchange_export": "/data-exchange/runs",
}


def run_once() -> bool:
    global _last_maintenance
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        if not _last_maintenance or now - _last_maintenance >= timedelta(minutes=1):
            _maintenance(db, now); db.commit(); _last_maintenance = now
        job = db.execute(select(Job).where(Job.status == "queued", Job.run_at <= now).order_by(Job.run_at).with_for_update(skip_locked=True).limit(1)).scalar_one_or_none()
        if not job: return False
        job.status = "running"; job.locked_at = now; job.attempts += 1; db.commit()
        try:
            if job.kind == "send_message": _send_message(db, job.payload["message_id"])
            elif job.kind == "process_document": _process_document(db, job.payload["document_id"])
            elif job.kind == "refresh_client_signals": _refresh_client_signals(db, job.payload["organization_id"])
            elif job.kind == "replay_payment_webhook": _replay_payment_webhook(db, job.payload["payment_event_id"])
            elif job.kind == "subscription_transition": _subscription_transition(db, job.payload["schedule_id"])
            elif job.kind == "college_erp_sync":
                from app.services.college_jobs import run_erp_sync
                run_erp_sync(db, job.payload)
            elif job.kind == "college_coding_sync":
                from app.services.college_jobs import run_coding_sync
                run_coding_sync(db, job.payload)
            elif job.kind == "college_resume_extract":
                from app.services.college_jobs import run_resume_extract
                run_resume_extract(db, job.payload)
            elif job.kind == "college_readiness_recompute":
                from app.services.college_jobs import run_readiness_recompute
                run_readiness_recompute(db, job.payload)
            elif job.kind == "data_exchange_validate":
                from app.services.data_exchange import process_import_job
                process_import_job(db, job.payload["run_id"])
            elif job.kind == "data_exchange_export":
                from app.services.data_exchange import process_export_job
                process_export_job(db, job.payload["run_id"])
            else: raise ValueError(f"Unknown job kind {job.kind}")
            job.status = "completed"; job.last_error = None
        except Exception as exc:
            job.last_error = str(exc)[:2000]
            if job.attempts >= job.max_attempts: job.status = "failed"
            else: job.status = "queued"; job.run_at = now + timedelta(minutes=min(2 ** job.attempts, 60))
        organization_id = job.organization_id
        changed_path = JOB_CHANGE_PATHS.get(job.kind)
        db.commit()
        if organization_id and changed_path:
            try:
                publish_change(organization_id, changed_path)
            except Exception as exc:
                logger.warning("realtime_publish_failed job=%s error_type=%s", job.kind, type(exc).__name__)
        return True
    finally: db.close()


def _maintenance(db, now):
    from app.services.audit import log_action
    from app.services.gym import reconcile_membership_rows
    from app.services.wallet import ensure_wallet

    if settings.WHATSAPP_REMINDERS_ENABLED:
        _schedule_whatsapp_reminders(db, now)
    _schedule_college_jobs(db, now)

    db.execute(delete(AIResultSession).where(AIResultSession.expires_at <= now))
    db.execute(delete(ChatConversation).where(ChatConversation.expires_at.is_not(None), ChatConversation.expires_at <= now))

    db.query(SupportSession).filter(SupportSession.status == "active", SupportSession.expires_at <= now).update({SupportSession.status: "expired", SupportSession.ended_at: now})
    db.query(ApprovalRequest).filter(ApprovalRequest.status == "pending", ApprovalRequest.expires_at.is_not(None), ApprovalRequest.expires_at <= now).update({ApprovalRequest.status: "expired"})
    db.query(OrganizationEntitlementOverride).filter(OrganizationEntitlementOverride.is_active.is_(True), OrganizationEntitlementOverride.ends_at <= now).update({OrganizationEntitlementOverride.is_active: False})
    for organization in db.execute(select(Organization).join(AIWallet, AIWallet.organization_id == Organization.id).where(AIWallet.cycle_end <= now)).scalars():
        ensure_wallet(db, organization)
    for organization in db.execute(select(Organization).where(Organization.status.in_(["active", "trial"]))).scalars():
        try:
            local_date = now.astimezone(ZoneInfo(organization.timezone or "Asia/Kolkata")).date()
        except Exception:
            local_date = now.date()
        membership_rows = db.execute(select(Membership).where(
            Membership.organization_id == organization.id,
            or_(
                Membership.status.in_(["active", "frozen", "scheduled"]),
                and_(
                    Membership.status == "renewed",
                    Membership.starts_on <= local_date,
                    Membership.ends_on >= local_date,
                ),
            ),
        ).order_by(Membership.client_id, Membership.starts_on, Membership.id)).scalars().all()
        reconcile_membership_rows(db, membership_rows, local_date)
    for archive in db.execute(select(RetentionArchive).where(RetentionArchive.purged_at.is_(None), RetentionArchive.purge_at <= now)).scalars():
        archive.encrypted_payload = "[purged]"; archive.purged_at = now
    deletions = db.execute(select(OrganizationDeletionRequest).where(OrganizationDeletionRequest.status == "approved", OrganizationDeletionRequest.purge_after <= now)).scalars().all()
    for deletion in deletions:
        organization = db.get(Organization, deletion.organization_id) if deletion.organization_id else None
        if organization:
            log_action(db, organization_id=organization.id, user_id=None, action="platform.organization_purged", resource_type="organization", resource_id=organization.id, meta={"deletion_request_id": deletion.id, "organization_slug": deletion.organization_slug})
            db.flush(); db.delete(organization)
        deletion.status = "completed"; deletion.completed_at = now


def _schedule_college_jobs(db, now):
    def queue(kind, organization_id, payload, key):
        exists = db.execute(select(Job.id).where(
            Job.organization_id == organization_id,
            Job.idempotency_key == key,
        )).first()
        if not exists:
            db.add(Job(
                organization_id=organization_id,
                kind=kind,
                payload=payload,
                status="queued",
                run_at=now,
                max_attempts=5,
                idempotency_key=key,
            ))

    due_connectors = db.execute(select(CollegeDataConnector).where(
        CollegeDataConnector.is_active.is_(True),
        CollegeDataConnector.encrypted_api_key.is_not(None),
        or_(CollegeDataConnector.next_sync_at.is_(None), CollegeDataConnector.next_sync_at <= now),
        CollegeDataConnector.status.notin_(("queued", "syncing")),
    )).scalars()
    for connector in due_connectors:
        bucket = now.strftime("%Y%m%d%H")
        mapping = connector.mapping or {}
        resource_configs = mapping.get("resources", mapping)
        resource_types = sorted(resource_configs) if resource_configs else [
            "students", "term_results", "attendance", "skills",
        ]
        queue(
            "college_erp_sync", connector.organization_id,
            {"connector_id": connector.id, "resource_types": resource_types},
            f"college-erp-scheduled:{connector.id}:{bucket}"[:120],
        )
        connector.status = "queued"

    stale_accounts = db.execute(select(CollegeCodingAccount).where(
        CollegeCodingAccount.is_active.is_(True),
        CollegeCodingAccount.consent_status == "granted",
        or_(CollegeCodingAccount.last_success_at.is_(None), CollegeCodingAccount.last_success_at <= now - timedelta(hours=24)),
        CollegeCodingAccount.sync_status.notin_(("queued", "syncing")),
    ).limit(250)).scalars()
    for account in stale_accounts:
        bucket = now.strftime("%Y%m%d")
        queue(
            "college_coding_sync", account.organization_id,
            {"account_id": account.id},
            f"college-coding-daily:{account.id}:{bucket}"[:120],
        )
        account.sync_status = "queued"

    college_orgs = db.execute(select(Organization).where(
        Organization.status.in_(("active", "trial")),
        Organization.industry == "college",
    )).scalars()
    for organization in college_orgs:
        bucket = now.strftime("%Y%m%d")
        queue(
            "college_readiness_recompute", organization.id,
            {"organization_id": organization.id},
            f"college-readiness-daily:{bucket}"[:120],
        )


def _subscription_transition(db, schedule_id):
    from app.services.billing import activate_subscription_schedule, provider_error
    from app.services.payment_gateways import gateway_config

    schedule = db.get(SubscriptionSchedule, schedule_id)
    if not schedule or schedule.status != "scheduled":
        return
    subscription = db.get(Subscription, schedule.subscription_id)
    if not subscription:
        schedule.status = "failed"
        return
    config = gateway_config(subscription.provider, subscription.provider_mode)
    if config.mode == "mock" or not subscription.razorpay_subscription_id:
        activate_subscription_schedule(db, subscription)
        return
    try:
        from app.services.razorpay_provider import razorpay_provider
        provider = razorpay_provider(config.client_id, config.secret).fetch_subscription(subscription.razorpay_subscription_id)
    except Exception as exc:
        provider_error(exc, "subscription_reconciliation")
        raise RuntimeError("Payment provider has not confirmed the subscription transition") from exc
    if schedule.action == "cancel":
        if provider.get("status") not in {"cancelled", "completed"}:
            raise RuntimeError("Cancellation is awaiting payment-provider confirmation")
        activate_subscription_schedule(db, subscription)
        return
    if provider.get("status") != "active" or provider.get("plan_id") != schedule.provider_reference:
        raise RuntimeError("Plan change is awaiting payment-provider confirmation")
    start = datetime.fromtimestamp(provider["current_start"], timezone.utc) if provider.get("current_start") else None
    end = datetime.fromtimestamp(provider["current_end"], timezone.utc) if provider.get("current_end") else None
    activate_subscription_schedule(db, subscription, period_start=start, period_end=end)


def _replay_payment_webhook(db, event_id):
    from app.services.billing import fulfill_invoice, rupees_to_paise
    from app.models import Invoice

    event = db.get(PaymentEvent, event_id)
    if not event: return
    data = event.payload or {}
    if event.provider == "cashfree":
        envelope = data.get("data") if isinstance(data.get("data"), dict) else {}
        payment = envelope.get("payment") if isinstance(envelope.get("payment"), dict) else {}
        order = envelope.get("order") if isinstance(envelope.get("order"), dict) else {}
        order_id = order.get("order_id")
        invoice = db.execute(select(Invoice).where(
            Invoice.provider == "cashfree", Invoice.provider_order_id == order_id,
        )).scalar_one_or_none() if order_id else None
        if invoice and event.event_type == "PAYMENT_SUCCESS_WEBHOOK" and payment.get("payment_status") == "SUCCESS":
            received = rupees_to_paise(payment.get("payment_amount"))
            currency = payment.get("payment_currency") or order.get("order_currency")
            if received == invoice.amount_paise and currency == invoice.currency:
                fulfill_invoice(db, invoice, str(payment.get("cf_payment_id") or ""))
    else:
        payment = data.get("payload", {}).get("payment", {}).get("entity", {})
        order = data.get("payload", {}).get("order", {}).get("entity", {})
        order_id = payment.get("order_id") or order.get("id")
        invoice = db.execute(select(Invoice).where(
            Invoice.provider == "razorpay",
            or_(Invoice.provider_order_id == order_id, Invoice.razorpay_order_id == order_id),
        )).scalar_one_or_none() if order_id else None
        if invoice and event.event_type in {"payment.captured", "order.paid"}:
            received = int(payment.get("amount") or order.get("amount_paid") or 0)
            currency = payment.get("currency") or order.get("currency")
            if received == invoice.amount_paise and currency == invoice.currency:
                fulfill_invoice(db, invoice, payment.get("id"))
        elif invoice and event.event_type == "payment.failed" and invoice.status != "paid": invoice.status = "failed"
    event.status = "replayed"; event.processed_at = datetime.now(timezone.utc); event.error = None


def _send_message(db, message_id):
    row = db.get(OutboundMessage, message_id)
    if not row or row.status == "sent": return
    if settings.PROVIDER_MOCK_MODE:
        row.provider_message_id = f"mock-{row.id}"; row.status = "sent"; row.sent_at = datetime.now(timezone.utc); row.attempts += 1; return
    if row.channel == "email":
        message_id = send_email(row.recipient, row.subject or "Message from Edvatiq", row.body, f"<p>{escape(row.body)}</p>", "notification")
        if not message_id: raise RuntimeError("Email provider rejected the message")
        row.provider_message_id = message_id
    elif row.channel == "whatsapp":
        provider_id = send_whatsapp_message(
            row.recipient, body=row.body, template_name=row.template,
            template_language=row.template_language,
            template_variables=row.template_variables,
        )
        if not provider_id: raise RuntimeError("WhatsApp provider rejected the message")
        row.provider_message_id = provider_id
    row.status = "sent"; row.sent_at = datetime.now(timezone.utc); row.attempts += 1


def _schedule_whatsapp_reminders(db, now):
    from app.services.entitlements import entitlement_value

    for organization in db.execute(select(Organization).where(Organization.status.in_(["active", "trial"]))).scalars():
        if not entitlement_value(db, organization, "communications.automations", False):
            continue
        try:
            local_zone = ZoneInfo(organization.timezone)
        except Exception:
            local_zone = timezone.utc

        appointments = db.execute(
            select(Appointment, Client, Location)
            .join(Client, Client.id == Appointment.client_id)
            .join(Location, Location.id == Appointment.location_id)
            .where(
                Appointment.organization_id == organization.id,
                Appointment.status.in_(["scheduled", "confirmed"]),
                Appointment.starts_at > now,
                Appointment.starts_at <= now + timedelta(hours=24),
                Client.whatsapp_consent.is_(True),
                Client.phone.is_not(None),
            )
        ).all()
        for appointment, client, location in appointments:
            local_start = appointment.starts_at.astimezone(local_zone)
            queue_whatsapp_template(
                db, organization=organization, client=client, location_id=location.id,
                template=settings.WHATSAPP_TEMPLATE_APPOINTMENT_REMINDER,
                variables=[
                    client.first_name,
                    organization.name,
                    local_start.strftime("%d %b %Y"),
                    local_start.strftime("%I:%M %p"),
                    location.name,
                ],
                body=f"Appointment reminder for {local_start.strftime('%d %b %Y at %I:%M %p')} at {location.name}",
                idempotency_key=f"wa-appointment:{appointment.id}:24h", run_at=now,
            )

        local_today = now.astimezone(local_zone).date()
        memberships = db.execute(
            select(Membership, Client, MembershipPlan)
            .join(Client, Client.id == Membership.client_id)
            .join(MembershipPlan, MembershipPlan.id == Membership.plan_id)
            .where(
                Membership.organization_id == organization.id,
                Membership.status == "active",
                Membership.ends_on >= local_today,
                Membership.ends_on <= local_today + timedelta(days=7),
                Client.whatsapp_consent.is_(True),
                Client.phone.is_not(None),
            )
        ).all()
        for membership, client, plan in memberships:
            days_remaining = (membership.ends_on - local_today).days
            if days_remaining not in {1, 7}:
                continue
            queue_whatsapp_template(
                db, organization=organization, client=client, location_id=membership.location_id,
                template=settings.WHATSAPP_TEMPLATE_MEMBERSHIP_EXPIRY,
                variables=[
                    client.first_name, plan.name,
                    membership.ends_on.strftime("%d %b %Y"),
                    str(days_remaining), organization.name,
                ],
                body=f"Membership reminder: {plan.name} expires on {membership.ends_on.strftime('%d %b %Y')}",
                idempotency_key=f"wa-membership:{membership.id}:{days_remaining}d", run_at=now,
            )


def _process_document(db, document_id):
    row = db.get(Document, document_id)
    if not row or row.status == "ready": return
    row.status = "processing"; db.flush()
    reservation = None
    provider_usage = {
        "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
        "embedding_tokens": 0, "provider_requests": 0,
    }
    try:
        if settings.AI_API_KEY:
            from app.services.ai_metering import route_credit_limit
            from app.services.wallet import reserve_credit_budget
            reservation = reserve_credit_budget(
                db, db.get(Organization, row.organization_id), route_credit_limit(db, "knowledge"),
                f"document-ai:{row.id}:v{row.embedding_version}",
            )
        content = _document_bytes(row); pages = []
        if row.content_type == "application/pdf":
            from pypdf import PdfReader
            pages = [(index + 1, page.extract_text() or "") for index, page in enumerate(PdfReader(io.BytesIO(content)).pages)]
        elif row.content_type.endswith("wordprocessingml.document"):
            from docx import Document as WordDocument
            text = "\n".join(paragraph.text for paragraph in WordDocument(io.BytesIO(content)).paragraphs); pages = [(None, text)]
        elif row.content_type == "text/plain": pages = [(None, content.decode("utf-8", errors="replace"))]
        else: pages = [(None, "")]
        text = "\n".join(item[1] for item in pages)
        if len(text.strip()) < max(80, len(pages) * 30) and settings.AI_API_KEY:
            from app.ai.provider import provider
            extracted = provider().extract_file_text(content, row.content_type)
            pages = [(None, extracted.text)]
            text = extracted.text
            provider_usage.update({
                "input_tokens": extracted.input_tokens,
                "cached_input_tokens": extracted.cached_input_tokens,
                "output_tokens": extracted.output_tokens,
                "provider_requests": extracted.provider_requests,
            })
        if not text.strip(): raise ValueError("No readable text was found in this document")
        row.extracted_text = text[:2_000_000]; chunks = []
        for page_number, page_text in pages:
            for start in range(0, len(page_text), 1000):
                chunk = page_text[start:start + 1200].strip()
                if chunk: chunks.append((page_number, chunk))
                if len(chunks) >= 200: break
            if len(chunks) >= 200: break
        embedding = _embed([item[1] for item in chunks])
        vectors = embedding.vectors if embedding else None
        if embedding:
            provider_usage["embedding_tokens"] = embedding.input_tokens
            provider_usage["provider_requests"] += embedding.provider_requests
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == row.id))
        for index, (page_number, chunk) in enumerate(chunks):
            vector = vectors[index] if vectors else None
            db.add(DocumentChunk(organization_id=row.organization_id, document_id=row.id, chunk_index=index,
                content=chunk, embedding=vector, embedding_vector=vector,
                search_vector=func.to_tsvector("simple", chunk), page_number=page_number,
                token_count=max(1, len(chunk) // 4), meta={"name": row.name}))
        row.embedding_model = settings.AI_EMBEDDING_MODEL if vectors else None
        row.embedding_version = (row.embedding_version or 0) + 1; row.status = "ready"; row.error = None
        if reservation:
            from app.services.ai_metering import calculate_charge
            from app.services.wallet import settle_reservation
            charge = calculate_charge(db, settings.AI_MODEL_BASIC, provider_usage)
            credits = min(reservation.credits, charge.credits)
            settle_reservation(db, reservation, charge.credits)
            db.add(AIUsage(organization_id=row.organization_id, user_id=row.uploaded_by_user_id,
                           model=settings.AI_EMBEDDING_MODEL,
                           input_tokens=provider_usage["input_tokens"],
                           cached_input_tokens=provider_usage["cached_input_tokens"],
                           output_tokens=provider_usage["output_tokens"],
                           embedding_tokens=provider_usage["embedding_tokens"],
                           provider_requests=provider_usage["provider_requests"],
                           tool_calls=0, route="document", status="completed", credits_used=credits,
                           provider_cost_paise=charge.provider_cost_paise, rate_version=charge.rate_version))
    except Exception as exc:
        row.status = "failed"; row.error = str(exc)[:1000]
        if reservation:
            from app.services.wallet import release_reservation
            release_reservation(db, reservation)
        raise


def _document_bytes(row):
    if settings.S3_ENDPOINT_URL and not settings.PROVIDER_MOCK_MODE:
        import boto3
        client = boto3.client("s3", endpoint_url=settings.S3_ENDPOINT_URL,
                              aws_access_key_id=settings.S3_ACCESS_KEY_ID,
                              aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY)
        return client.get_object(Bucket=settings.S3_BUCKET, Key=row.object_key)["Body"].read()
    path = ROOT_DIR / "storage" / row.object_key
    if not path.exists(): raise FileNotFoundError("Local document is unavailable to the worker")
    return path.read_bytes()


def _refresh_client_signals(db, organization_id):
    from app.api.v1.client_intelligence import _refresh_signals
    from app.models import Client, Organization, Role, User, UserRole

    org = db.get(Organization, organization_id)
    if not org:
        return
    owner = db.execute(
        select(User).join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
        .where(
            User.organization_id == organization_id,
            Role.slug == "owner",
            Role.is_system.is_(True),
            User.is_active.is_(True),
        )
        .limit(1)
    ).scalar_one_or_none()
    if not owner:
        return
    clients = db.execute(select(Client).where(Client.organization_id == organization_id, Client.status == "active")).scalars().all()
    for client in clients:
        _refresh_signals(db, owner, client, org.industry.value)
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    db.add(Job(
        organization_id=organization_id, kind="refresh_client_signals",
        payload={"organization_id": organization_id}, run_at=tomorrow,
        idempotency_key=f"client-signals-scheduled-{tomorrow.isoformat()}",
    ))


def _embed(chunks):
    if not chunks or not settings.AI_API_KEY: return None
    from app.ai.provider import provider
    return provider().embed(chunks)


if __name__ == "__main__":
    while True:
        if not run_once(): time.sleep(2)
