"""Authoritative public legal publication and acceptance helpers."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import LegalAcceptance, LegalDocument, PlatformSetting


LEGAL_TYPES = ("terms", "privacy", "refund")
LEGAL_PROFILE_KEY = "legal_profile"
LEGAL_PROFILE_DEFAULTS = {
    "brand_name": "Edvatiq",
    "legal_name": "",
    "registered_address": "",
    "country": "",
    "state": "",
    "jurisdiction": "",
    "support_email": "sales@edvatiq.com",
    "privacy_email": "",
    "grievance_contact": "",
    "registration_identifiers": "",
}
LEGAL_PROFILE_REQUIRED = (
    "legal_name", "registered_address", "country", "state", "jurisdiction",
    "support_email", "privacy_email", "grievance_contact",
)


STARTER_DOCUMENTS = {
    "terms": {
        "title": "Terms of Service",
        "content": """# Terms of Service

These Terms govern access to Edvatiq, a service operated by {{legal_name}} from {{registered_address}}.

## 1. Accounts and authority

You must provide accurate information and protect account credentials. A person creating a workspace confirms that they are authorized to act for that organization and to invite its users.

## 2. Service use

Edvatiq provides operational software, placement intelligence, and evidence-backed assistance. You remain responsible for source data, business decisions, notices to your users, and verifying outputs before relying on them.

## 3. Acceptable use

Do not misuse the service, attempt unauthorized access, interfere with availability, upload unlawful material, evade limits, or use Edvatiq to make decisions prohibited by applicable law.

## 4. Plans, payments, and taxes

Plan prices, billing intervals, included capacity, and applicable taxes are shown before checkout. Automatic renewal applies only when explicitly selected and supported by the active payment provider. You may cancel future renewal from Plan and billing.

## 5. Integrations and AI

Third-party services and institution systems remain governed by their own terms. AI answers can be incomplete and must not replace professional, clinical, legal, financial, academic, or employment judgment. Protected attributes must not be used for placement ranking or eligibility.

## 6. Data and security

Each organization controls the records it submits and the permissions it grants. We use reasonable safeguards and role-based controls, but no online service can guarantee uninterrupted or error-free operation.

## 7. Suspension and termination

Access may be restricted for non-payment, security risk, unlawful use, or material breach. Ending a subscription does not erase records that must be retained for contractual, tax, audit, or legal obligations.

## 8. Refunds

Refund requests are reviewed case by case under the published Refund and Cancellation Policy. This does not limit rights that cannot be excluded under applicable law.

## 9. Liability

To the extent permitted by law, indirect or consequential losses are excluded. Any aggregate liability is limited to fees paid for the affected service period, except where such a limit is prohibited.

## 10. Governing law and contact

These Terms are governed by applicable law and disputes are subject to {{jurisdiction}}. Contact {{support_email}} for contractual notices or service questions.
""",
    },
    "privacy": {
        "title": "Privacy Policy",
        "content": """# Privacy Policy

This Policy explains how {{legal_name}} handles personal information when providing Edvatiq.

## Information we process

We process account details, organization records, permitted client or student records, usage and audit events, device and security information, support requests, billing references, and content submitted to enabled integrations.

## Why we process it

Information is used to provide and secure the service, enforce permissions, complete payments, synchronize authorized systems, answer support requests, improve reliability, and meet legal obligations.

## Organization-controlled data

Organizations determine which operational, academic, placement, clinical, or customer records they enter and who may access them. Institutions are responsible for providing required notices and establishing a lawful basis for student and staff data.

## AI and service providers

Authorized content may be sent to configured infrastructure, communications, payment, storage, or AI providers only as needed to deliver enabled features. Edvatiq permissions and confirmation rules continue to apply.

## Cookies and security

Edvatiq uses essential session and security cookies. We use access controls, audit records, encryption where configured, and data minimization practices. We do not claim that any system is immune from risk.

## Retention and deletion

Records are retained according to workspace settings, contractual needs, legal obligations, and applicable tax or sector requirements. Some evidence may be archived or pseudonymized instead of immediately deleted.

## Your choices and rights

Depending on applicable law, individuals may request access, correction, restriction, or deletion through their organization or by contacting us. Requests may require identity verification and may be limited by lawful retention duties.

## Contact and grievances

Privacy questions may be sent to {{privacy_email}}. Grievances may be directed to {{grievance_contact}} at {{registered_address}}.
""",
    },
    "refund": {
        "title": "Refund and Cancellation Policy",
        "content": """# Refund and Cancellation Policy

This Policy applies to Edvatiq plans and AI-credit purchases supplied by {{legal_name}}.

## Cancelling future renewal

Where automatic renewal is active, an authorized billing user may cancel renewal from Plan and billing. Access normally continues through the already-paid term unless the workspace is suspended for another valid reason.

## One-time plans and top-ups

One-time plan terms and consumed AI credits do not renew automatically. Unused capacity does not itself guarantee a refund.

## Refund requests

Requests are reviewed case by case, including duplicate charges, confirmed provider errors, failure to provision a paid workspace, or other documented service issues. Contact {{support_email}} with the invoice, payment reference, reason, and supporting information.

## Processing

Approved refunds are returned through the original payment provider where possible. Provider processing times and bank settlement times are outside Edvatiq's direct control.

## Statutory rights

Nothing in this Policy excludes rights or remedies that cannot be excluded under applicable law. Disputes are handled under the jurisdiction stated in the Terms of Service.
""",
    },
}


def legal_profile(db: Session) -> tuple[dict, PlatformSetting | None]:
    setting = db.execute(
        select(PlatformSetting).where(PlatformSetting.key == LEGAL_PROFILE_KEY)
    ).scalar_one_or_none()
    return {**LEGAL_PROFILE_DEFAULTS, **(setting.value if setting else {})}, setting


def missing_legal_profile_fields(profile: dict) -> list[str]:
    return [field for field in LEGAL_PROFILE_REQUIRED if not str(profile.get(field) or "").strip()]


def materialize_legal_content(content: str, profile: dict) -> str:
    output = content
    for key, value in profile.items():
        output = output.replace("{{" + key + "}}", str(value or "").strip())
    return output.strip()


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def current_legal_documents(db: Session) -> dict[str, LegalDocument]:
    rows = db.execute(select(LegalDocument).where(
        LegalDocument.status == "published",
        LegalDocument.document_type.in_(LEGAL_TYPES),
    )).scalars()
    return {row.document_type: row for row in rows}


def legal_document_payload(row: LegalDocument, *, include_content: bool = True) -> dict:
    payload = {
        "id": row.id,
        "type": row.document_type,
        "version": row.version,
        "title": row.title,
        "status": row.status,
        "version_lock": row.version_lock,
        "content_hash": row.content_hash,
        "effective_at": row.effective_at,
        "published_at": row.published_at,
        "updated_at": row.updated_at,
    }
    if include_content:
        payload["content_markdown"] = row.content_markdown
    return payload


def public_legal_payload(db: Session, *, include_content: bool = True) -> dict:
    profile, setting = legal_profile(db)
    documents = current_legal_documents(db)
    missing = missing_legal_profile_fields(profile)
    ready = not missing and all(kind in documents for kind in LEGAL_TYPES)
    return {
        "ready": ready,
        "operator": profile,
        "profile_version": setting.version if setting else 0,
        "documents": {
            kind: legal_document_payload(documents[kind], include_content=include_content)
            if kind in documents else None
            for kind in LEGAL_TYPES
        },
    }


def validate_legal_acceptance(db: Session, acceptance) -> dict[str, LegalDocument]:
    current = current_legal_documents(db)
    profile, _ = legal_profile(db)
    if missing_legal_profile_fields(profile) or any(kind not in current for kind in LEGAL_TYPES):
        raise HTTPException(503, "Registration is temporarily unavailable while legal documents are being published")
    if not acceptance or not acceptance.accepted:
        raise HTTPException(422, "You must agree to the Terms and acknowledge the Privacy and Refund Policies")
    submitted = {
        "terms": acceptance.terms_document_id,
        "privacy": acceptance.privacy_document_id,
        "refund": acceptance.refund_document_id,
    }
    if any(current[kind].id != submitted[kind] for kind in LEGAL_TYPES):
        raise HTTPException(409, "Legal documents changed. Review the current versions and try again")
    return current


def create_legal_acceptance(
    db: Session,
    *,
    documents: dict[str, LegalDocument],
    subject_email: str,
    source: str,
    organization_id: str | None = None,
    user_id: str | None = None,
    signup_checkout_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> LegalAcceptance:
    now = datetime.now(timezone.utc)
    row = LegalAcceptance(
        organization_id=organization_id,
        user_id=user_id,
        signup_checkout_id=signup_checkout_id,
        subject_email=subject_email.strip().lower(),
        terms_document_id=documents["terms"].id,
        privacy_document_id=documents["privacy"].id,
        refund_document_id=documents["refund"].id,
        document_snapshot={
            kind: {
                "id": documents[kind].id,
                "version": documents[kind].version,
                "hash": documents[kind].content_hash,
                "title": documents[kind].title,
            }
            for kind in LEGAL_TYPES
        },
        accepted_at=now,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:300] or None,
        source=source,
    )
    db.add(row)
    db.flush()
    return row


def attach_checkout_acceptance(db: Session, checkout_id: str, organization_id: str, user_id: str) -> None:
    row = db.execute(select(LegalAcceptance).where(
        LegalAcceptance.signup_checkout_id == checkout_id,
    ).with_for_update()).scalar_one_or_none()
    if row:
        row.organization_id = organization_id
        row.user_id = user_id


def seed_legal_drafts(db: Session) -> None:
    _, setting = legal_profile(db)
    if not setting:
        db.add(PlatformSetting(key=LEGAL_PROFILE_KEY, value=dict(LEGAL_PROFILE_DEFAULTS), version=1))
    for kind, spec in STARTER_DOCUMENTS.items():
        exists = db.scalar(select(func.count(LegalDocument.id)).where(
            LegalDocument.document_type == kind,
        ))
        if not exists:
            body = spec["content"].strip()
            db.add(LegalDocument(
                document_type=kind,
                version=1,
                title=spec["title"],
                content_markdown=body,
                content_hash=content_hash(body),
                status="draft",
            ))
    db.flush()
