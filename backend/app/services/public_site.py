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
    "contact_phone": "+919787867648",
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


VERSION_TWO_DOCUMENTS = {
    "terms": {
        "title": "Terms of Service",
        "content": """# Terms of Service

These Terms of Service govern access to Edvatiq and form an agreement between the organization accepting them and {{legal_name}}, operating from {{registered_address}}. Please read them together with the current Privacy Policy, Refund and Cancellation Policy, plan description, and any signed order or enterprise agreement.

## 1. Scope and order of documents

Edvatiq provides hosted organization software, operational workflows, placement intelligence, integrations, reporting, and permission-aware AI assistance. These Terms apply to trial, paid, promotional, and administrator-created workspaces.

If a signed order or enterprise agreement expressly conflicts with these Terms, that signed document controls only for the conflicting subject. Product descriptions, support material, and documentation explain features but do not override this agreement unless expressly incorporated.

## 2. Eligibility and organizational authority

The person creating or purchasing a workspace confirms that they are legally capable of entering this agreement and authorized to act for the named organization. The organization is responsible for its administrators, invited users, contractors, and anyone using credentials issued under its workspace.

You must provide accurate account, billing, tax, and organization information and keep it current. Edvatiq may request reasonable evidence of authority, identity, payment authorization, or organization ownership where needed to protect users or meet legal obligations.

## 3. Accounts, roles, and security

Each user must use an individual account unless a documented integration credential is specifically provided. You must protect passwords, recovery codes, API credentials, and authenticated devices; shared passwords and attempts to bypass role restrictions are prohibited.

Workspace administrators control invitations, roles, locations, academic scope, and enabled modules. They must grant the minimum access reasonably required and remove access promptly when a user's role ends. Notify {{support_email}} without delay if you suspect unauthorized access, credential disclosure, or account misuse.

Edvatiq may require email verification, multi-factor authentication, session revalidation, or additional confirmation for sensitive actions.

## 4. Service and feature availability

Available features depend on the selected plan, organization type, permissions, configuration, region, and third-party availability. Beta, preview, or evaluation features may change, be limited, or be withdrawn and should not be used as the sole system of record for critical decisions.

Edvatiq may improve or replace features while preserving the material purpose of a paid service. Planned maintenance and urgent security work may temporarily affect availability. Unless a signed agreement states otherwise, no specific uptime or response-time commitment is created by these Terms.

## 5. Organization responsibilities

The organization is responsible for:

- determining whether Edvatiq is suitable for its workflows and legal obligations;
- the accuracy, quality, authority, and lawful collection of records submitted to the service;
- giving required notices and obtaining required permissions or consents from staff, clients, patients, students, guardians, candidates, and other individuals;
- configuring roles, retention, integrations, communications, eligibility policies, and approval workflows correctly;
- reviewing outputs, reports, calculations, imported records, and AI-assisted suggestions before acting on them; and
- maintaining independent procedures for emergencies, clinical care, statutory reporting, examinations, financial controls, and other activities that cannot safely depend on one online service.

## 6. Acceptable use

You must not use Edvatiq to break the law, violate another person's rights, discriminate unlawfully, misrepresent evidence, or process information you are not authorized to use. You must not:

- probe, scan, disrupt, overload, reverse engineer, or bypass security or usage controls except where applicable law expressly permits;
- upload malware, unlawful content, stolen credentials, payment authentication data, or unnecessary highly sensitive information;
- scrape the service, resell access without written authorization, impersonate another person, or conceal the origin of automated traffic;
- use AI or placement features to make prohibited decisions or rank people using protected attributes;
- send unsolicited or deceptive communications; or
- use Edvatiq to develop a competing model or service through unauthorized bulk extraction.

Reasonable integration and accessibility testing must use documented interfaces and agreed environments.

## 7. Plans, orders, and taxes

The checkout or order identifies the plan, billing interval, included limits, price, and applicable taxes. Prices may differ by plan, term, currency, or negotiated order. Taxes shown at checkout are based on the information available at that time, and the organization remains responsible for accurate tax details and any taxes it is legally required to pay.

Paid access begins after payment confirmation or another expressly approved billing arrangement. A failed, reversed, disputed, or fraudulent payment may delay activation or restrict access. Invoices and provider references are electronic records and should be reviewed promptly.

## 8. Renewal, cancellation, and plan changes

Automatic renewal applies only when it is clearly selected, supported by the payment provider, and shown in the billing experience or order. An authorized billing user may cancel a future renewal before the next charge. Cancellation normally takes effect at the end of the paid term unless the service states otherwise.

Changing plans may alter limits, features, charges, or the next renewal amount. Downgrades can make some features unavailable but do not authorize deletion of records that must be retained. Refund eligibility and cancellation processing are governed by the current Refund and Cancellation Policy and any non-excludable legal rights.

## 9. AI credits and usage limits

AI credits and other metered capacity are consumed according to the action shown in the product. Estimates may be displayed before a request, but complex actions can use different capacity where disclosed. Credits may have an expiry period stated at purchase and are not money, stored value, or transferable currency.

Edvatiq may enforce fair-use, rate, storage, record, and integration limits to protect reliability. Attempts to evade limits may result in throttling or suspension.

## 10. Organization data and service data

As between the parties, the organization retains its rights in records, documents, instructions, and content it lawfully submits. The organization grants Edvatiq the limited rights needed to host, copy, transform, transmit, index, secure, back up, and otherwise process that content to provide and support the service.

Edvatiq may generate service telemetry, security events, usage measurements, and aggregated or de-identified operational information. Such information must not be used to re-identify individuals and may be used to secure, operate, support, and improve the service as permitted by law and the Privacy Policy.

## 11. Privacy and regulated information

The Privacy Policy explains how personal information is handled. Depending on the workflow, the organization may determine the purpose and means of processing while Edvatiq processes records on its documented instructions. The organization remains responsible for sector-specific duties applying to education, employment, health, consumer, or financial records.

Do not enter card PINs, CVVs, one-time payment passwords, account passwords, or authentication secrets into notes, documents, prompts, or support requests.

## 12. Integrations and imported data

Third-party systems, ERP connectors, coding platforms, communications providers, storage providers, and payment gateways are governed by their own terms and availability. The organization authorizes Edvatiq to exchange the configured information with those providers.

You are responsible for connector credentials, mapping rules, source-system authority, and reviewing import results. Edvatiq does not infer deletion merely because a source stops returning a record unless a documented workflow expressly says otherwise. Third-party changes, outages, rate limits, or inaccurate source data may affect synchronization.

## 13. AI-assisted features

AI features can summarize authorized records, draft text, explain evidence, and suggest next actions. Their output may be incomplete, outdated, or incorrect. AI output is not legal, medical, financial, employment, academic, or other professional advice and must not replace qualified judgment.

The current user's permissions, organization scope, confirmation rules, and source boundaries continue to apply. Users must verify material facts and supporting records before relying on an answer. Edvatiq may block instructions that seek unauthorized data, unsafe actions, or circumvention of controls.

## 14. Intellectual property and feedback

Edvatiq and its licensors retain rights in the software, interface, documentation, trademarks, templates, and service technology. Except for the limited right to use the service during an authorized term, no ownership is transferred.

If you provide product feedback, you permit Edvatiq to use it without restriction or payment, provided that this does not grant rights in your confidential records or identify individuals publicly without permission.

## 15. Confidentiality

Each party must use reasonable care to protect non-public information received from the other and use it only for the agreement. This duty does not cover information that is public without breach, independently developed, already lawfully known, or lawfully received from another source.

A party may disclose information when legally required after giving notice where permitted and limiting disclosure to what is required.

## 16. Suspension and protective action

Edvatiq may temporarily restrict access where reasonably necessary to address a security threat, unlawful use, material breach, payment failure, risk to another customer, or a binding legal request. Where practical, Edvatiq will provide notice and an opportunity to remedy the issue.

Emergency restrictions may be immediate. Suspension does not remove payment obligations already incurred or erase evidence that must be retained.

## 17. Termination and data handling

Either party may end the service as permitted by the selected plan, order, or these Terms. Material breach may justify termination if it is not remedied within a reasonable notice period, unless immediate action is required for security or law.

After termination, access may end and records may be deleted, archived, anonymized, or retained according to workspace settings, backup cycles, contractual requirements, disputes, tax duties, audit needs, and applicable law. The organization should export needed information before access ends. Recovery after deletion is not guaranteed.

## 18. Disclaimers

To the extent permitted by law, the service is provided on an as-available basis. Edvatiq does not warrant that every feature will be uninterrupted, that every third-party source will remain available, or that all imported, calculated, or AI-generated information will be error-free.

Nothing in these Terms excludes warranties, remedies, or obligations that cannot lawfully be excluded.

## 19. Limitation of liability

To the extent permitted by law, neither party is liable for indirect, incidental, special, punitive, or consequential loss, or for lost profits, revenue, goodwill, or anticipated savings arising from the service. Edvatiq's aggregate liability for claims relating to the affected service is limited to fees paid for that service during the twelve months before the event giving rise to the claim.

These limitations do not apply where prohibited by law and do not limit liability that cannot legally be limited.

## 20. Changes to these Terms

Edvatiq may publish a new version to reflect product, legal, security, or business changes. The effective date and version will be displayed. Where a change materially affects an active paid service, reasonable notice will be provided through the service, email, or another appropriate channel when required.

Continued use after the effective date constitutes acceptance only to the extent permitted by law and the applicable agreement. Historical versions remain available for accepted-version evidence.

## 21. Governing law, notices, and contact

These Terms are governed by applicable law, and disputes are subject to {{jurisdiction}}, except where mandatory law provides another forum or remedy. Electronic acceptance and notices may be retained as electronic records.

Contractual notices and service questions may be sent to {{support_email}}. Notices to the organization may be sent to its registered workspace owner or billing contact. The operator is {{legal_name}}, {{registered_address}}.
""",
    },
    "privacy": {
        "title": "Privacy Policy",
        "content": """# Privacy Policy

This Privacy Policy explains how {{legal_name}}, operating Edvatiq from {{registered_address}}, handles personal information in the public website, account services, organization workspaces, integrations, support, and AI-assisted features.

## 1. Who this Policy applies to

This Policy applies to visitors, account holders, workspace administrators, staff users, demo-request contacts, and individuals whose information is processed through an Edvatiq workspace. An organization may provide additional notices for its employees, clients, patients, students, candidates, members, or other individuals.

Edvatiq can act in different roles. For account, security, billing-reference, public-site, and service-administration information, {{legal_name}} determines why and how information is processed. For many records entered by an organization, the organization determines the purpose and authorized users, and Edvatiq processes those records to provide the configured service.

## 2. Information we collect

Depending on use, we may process:

- account and identity details such as name, work email, phone number, profile image, designation, verification state, and organization association;
- organization information such as legal and trading names, locations, industry, tax identifiers, settings, roles, and subscription details;
- operational records such as clients, members, appointments, attendance, inventory, sales references, invoices, payments, tasks, notes, documents, and communications;
- academic and placement records such as student identifiers, batches, attendance, results, assessments, coding profiles, resumes, skills, applications, interviews, offers, readiness evidence, and internship-clearance status;
- clinic or wellness workflow information entered into enabled modules, which may include sensitive or sector-regulated records where the organization is authorized to process them;
- integration information such as connector configuration, external identifiers, synchronization status, mapped fields, import errors, and provider responses;
- AI interactions such as prompts, authorized source references, generated answers, feedback, and action confirmations;
- billing and transaction references such as plan, amount, tax, invoice status, payment-provider order ID, and settlement or refund status, while payment authentication data is handled by the payment provider;
- device, network, and security information such as IP address, browser, session, cookie, login attempt, audit event, and diagnostic data; and
- information submitted through demo, support, grievance, security, or other contact channels.

## 3. Sources of information

Information may come directly from you, your organization, an authorized administrator, an integrated ERP or other system, uploaded files, configured third-party services, payment and communication providers, or automatically from use of the service.

Organizations must ensure that they have authority to provide information and that source records are accurate. Imported records can retain source identifiers, freshness times, ownership markers, and audit evidence so authorized users can understand their origin.

## 4. Why we process information

We process information as reasonably necessary to:

- create, verify, administer, and secure accounts and workspaces;
- provide configured operational, academic, placement, reporting, billing, document, and AI features;
- enforce permissions, organization boundaries, role scope, confirmations, and usage limits;
- synchronize authorized systems, validate imports, preserve manual overrides, and report errors;
- process subscriptions, invoices, payment status, refunds, tax records, and fraud checks;
- deliver service messages, requested communications, reminders, and support;
- detect misuse, investigate incidents, maintain audit evidence, and protect users and infrastructure;
- monitor reliability, diagnose faults, and improve service performance and usability;
- comply with contractual, tax, accounting, security, and legal obligations; and
- establish, exercise, or defend legal claims.

Where applicable law requires consent for a particular activity, that activity should use a clear request and an available withdrawal method. Other processing may be necessary to perform a contract, comply with law, protect legitimate interests, or act on the organization's documented instructions, depending on context and jurisdiction.

## 5. Organization-controlled records

Workspace administrators decide which modules to enable, which records to add or import, who can access them, and how long they are operationally needed. Requests concerning organization-controlled records should usually be directed first to that organization because it can identify the record, authority, and appropriate response.

Edvatiq does not authorize an organization to collect information unlawfully. Organizations are responsible for required notices, permissions, guardian involvement where applicable, sector rules, and fair use of attendance, academic, employment, health, financial, or placement evidence.

## 6. Students, minors, and education records

College features are designed for authorized institutional staff and placement workflows. Institutions must determine whether a student is a child or otherwise requires guardian authorization under applicable law and configure collection and access accordingly.

Protected characteristics must not be used in Edvatiq readiness scores, placement ranking, or candidate recommendations. Fee information is minimized in normal placement workflows to an internship-clearance state unless a finance-authorized user has lawful access to additional detail.

## 7. AI-assisted processing

When a user invokes an AI feature, Edvatiq may process the prompt, conversation context, relevant authorized records, tool results, and feedback to produce the requested response. Only information needed for the request should be supplied to configured AI infrastructure.

Permissions and record scope continue to apply. AI output can be inaccurate and should be reviewed against linked evidence. Sensitive actions require confirmation where the product provides that control. Users should not place passwords, payment authentication data, or unrelated sensitive records in prompts.

Saved assistant preferences affect presentation and tone but do not expand data access or override safety and business rules.

## 8. Integrations and service providers

Edvatiq uses service providers for infrastructure, storage, communications, payments, monitoring, support, and AI where configured. These providers receive information only as reasonably needed for their role and are subject to contractual, technical, or legal controls appropriate to that service.

Organizations can also connect their own ERP, coding profile, or other provider. Those providers operate under their own privacy practices. Connector credentials are protected according to their purpose; secrets are not intentionally returned after one-time display where the integration is designed that way.

## 9. Payments

Payment gateways process card, UPI, banking, wallet, or other payment authentication information under their own terms. Edvatiq ordinarily receives transaction references, status, method category, amount, and limited payer or billing details rather than full payment credentials.

Never submit a card PIN, CVV, UPI PIN, one-time password, banking password, or payment recovery code to Edvatiq support, notes, documents, or AI prompts.

## 10. Cookies and similar technology

Edvatiq uses essential cookies or browser storage for authentication, security, CSRF protection, preferences, draft preservation, and reliable navigation. These technologies are necessary for requested service functions.

If optional analytics or other non-essential technologies are introduced, their use and available choices should be disclosed through an appropriate notice or control before they are used where required.

## 11. Disclosure of information

Information may be disclosed:

- to authorized users within the relevant organization and scope;
- to service providers and connected systems needed to deliver configured features;
- to payment, banking, tax, or professional advisers as needed for transactions and compliance;
- during a merger, financing, reorganization, or transfer, subject to appropriate confidentiality and notice obligations;
- to authorities, courts, or other parties when reasonably required by law, legal process, safety, fraud prevention, or protection of rights; or
- with the individual's or organization's direction where legally valid.

Edvatiq does not make workspace permissions public. A valid disclosure request is reviewed for authority and scope, and disclosure should be limited where legally permitted.

## 12. International and regional processing

Infrastructure or service providers may process information in more than one region. Where cross-border safeguards or transfer restrictions apply, Edvatiq and the organization must use an appropriate legal and contractual mechanism and respect applicable government restrictions.

The location of an organization, individual, provider, and configured deployment can affect which rules apply.

## 13. Retention

Retention depends on record type, workspace configuration, contractual needs, source-system authority, backup cycles, dispute or fraud evidence, tax and accounting duties, sector requirements, and applicable law.

Account and workspace records are kept while needed to provide the service. Security and audit records may be retained for investigation and accountability. Transaction and invoice evidence may be retained for statutory periods. Deleted information can remain in restricted backups until normal rotation, and some records may be anonymized or archived instead of erased where lawful retention is required.

Organizations should not keep personal information longer than necessary and should maintain their own retention instructions for organization-controlled records.

## 14. Security

Edvatiq uses measures designed to protect information, including organization isolation, permission checks, session controls, password hashing, CSRF protection, audit events, provider-secret handling, and encryption where configured. Access to production systems and sensitive actions should be limited to authorized roles.

No online service can guarantee absolute security. Users must protect credentials, devices, exports, and integration keys and promptly report suspected incidents to {{support_email}}. Do not include unnecessary personal records in an initial security report.

## 15. Individual choices and rights

Depending on applicable law and context, an individual may have rights to receive information about processing, access personal data, request correction or erasure, withdraw consent, nominate another person, restrict or object to certain processing, or raise a grievance.

Rights are not absolute and may be limited by identity verification, another person's rights, source-system authority, contractual necessity, security, legal claims, or mandatory retention. For organization-controlled records, Edvatiq may refer the request to the organization and assist it as required.

Requests should identify the relevant organization and record without sending passwords or excessive sensitive information. Privacy requests may be sent to {{privacy_email}}.

## 16. Communications

Service and security messages may be necessary for account verification, payment status, incidents, policy changes, and requested workflows. Where optional promotional communications are offered, they should provide an appropriate opt-out mechanism.

Unsubscribing from promotional messages does not stop essential service, security, transaction, or legal notices.

## 17. Grievances and complaints

Privacy concerns should first be sent to {{privacy_email}} with enough information to identify the account or organization. Grievances may be directed to {{grievance_contact}}. We may request identity or authority verification before disclosing or changing records.

This process does not limit a right to approach an applicable regulator, board, court, or other authority.

## 18. Changes to this Policy

This Policy may be updated for service, provider, security, or legal changes. Each publication displays a version and effective date, and historical versions are retained for acceptance evidence. Material changes will be communicated through an appropriate channel where required.

## 19. Contact

The operator is {{legal_name}}, {{registered_address}}. Privacy questions may be sent to {{privacy_email}}, service questions to {{support_email}}, and grievances to {{grievance_contact}}.
""",
    },
    "refund": {
        "title": "Refund and Cancellation Policy",
        "content": """# Refund and Cancellation Policy

This Refund and Cancellation Policy explains how subscription cancellations, failed or duplicate payments, AI-credit purchases, and refund requests are handled for Edvatiq services supplied by {{legal_name}}. It should be read with the plan details, invoice, checkout information, and Terms of Service.

## 1. Scope

This Policy applies to self-serve Edvatiq plans, renewals, and AI-credit or capacity purchases. A signed enterprise order may contain different commercial terms; where it expressly conflicts with this Policy, the signed order controls for that purchase.

Nothing in this Policy restricts a refund, cancellation, charge correction, or other remedy that cannot lawfully be excluded.

## 2. Before completing payment

Checkout shows the selected plan or pack, billing interval, price, applicable tax, and whether the purchase is recurring or one-time. Review the organization, plan, quantity, currency, and payer details before authorizing payment.

Payment gateways may present their own authentication and processing notices. Do not share a card PIN, CVV, UPI PIN, one-time password, banking password, or payment recovery code with Edvatiq.

## 3. Cancelling future renewal

Where automatic renewal is enabled, an authorized billing user may cancel the next renewal from Plan and billing or through the supported contact channel. Cancellation should be requested before the next payment is initiated.

Cancelling renewal normally prevents future renewal charges but does not reverse the current paid term. Workspace access ordinarily continues until the end of that term unless access is separately suspended for security, unlawful use, non-payment, or another valid reason.

If the interface does not show a cancellation control, contact {{support_email}} from an authorized workspace email and identify the organization and subscription. Do not send payment credentials.

## 4. One-time plans and AI-credit packs

One-time terms and top-up packs do not renew automatically unless checkout expressly states otherwise. AI credits or other capacity can expire on the date shown at purchase or in Plan and billing.

Used credits, completed AI actions, consumed capacity, and elapsed service time are generally not reversible. An unused balance alone does not guarantee a cash refund, but documented service or billing problems will be reviewed under this Policy and applicable law.

## 5. Trial and promotional access

Ending a free trial or promotional period does not create a refund because no plan fee was paid. If payment details were used for a clearly disclosed conversion to a paid term, the renewal and cancellation information shown during enrollment applies.

Promotional credits, discounts, and non-cash benefits have no cash value unless the applicable offer expressly states otherwise.

## 6. Requests that may qualify for review

Refund or correction requests are reviewed on their evidence and circumstances. Examples that may qualify include:

- the same Edvatiq purchase was charged more than once;
- the payment provider confirmed capture but the paid workspace or credit pack was not provisioned;
- the amount or plan charged differs from the confirmed checkout because of an Edvatiq or provider error;
- a material paid service was not supplied as described and the issue was not reasonably corrected;
- an unauthorized transaction is confirmed through the provider's investigation; or
- applicable law requires a refund, cancellation, replacement, or other remedy.

Listing a circumstance does not guarantee approval. Edvatiq may first correct provisioning, restore credits, extend access, or reverse an incorrect invoice where that fully resolves the issue and is legally appropriate.

## 7. Requests that are generally not refundable

Subject to applicable law and the facts of the request, refunds are generally not provided for:

- a change of mind after paid access was provisioned and used;
- unused time in a billing period after cancellation of future renewal;
- used AI credits, completed actions, or capacity consumed by authorized users;
- failure to use available features, incomplete onboarding, or organization configuration choices;
- inability caused solely by the organization's device, network, source system, credentials, mapping, or unsupported third-party service;
- access restricted because of a material breach, unlawful use, fraud risk, or security threat; or
- promotional, bonus, or complimentary credits.

This list does not override remedies for a deficient, incorrectly described, duplicate, unauthorized, or legally refundable transaction.

## 8. Failed, pending, and reversed payments

A failed or pending payment is not treated as a completed purchase until the provider confirms success. Banks and payment providers can temporarily reserve or display amounts during processing even when Edvatiq has not received a successful status.

If a payment remains pending, avoid repeated attempts until its status is clear. A provider-confirmed failed payment should normally be released or reversed by the provider or bank according to its process. Send the payment reference to {{support_email}} if the status remains inconsistent after the provider's stated processing period.

## 9. Duplicate payments

If two successful charges relate to the same intended order, report both payment references and the invoice or checkout ID. After verification, Edvatiq may refund the duplicate transaction or, with authorization, apply it to a valid future purchase.

Do not submit full card numbers, bank passwords, PINs, CVVs, or one-time passwords as evidence.

## 10. How to request a review

Send the request to {{support_email}} from the workspace owner, billing contact, or payer email where possible. Include:

- organization and workspace identifier;
- invoice, checkout, or order reference;
- payment-provider reference;
- payment date and amount;
- a clear reason for the request; and
- relevant screenshots or provider confirmation with sensitive credentials removed.

Requests should be made promptly after discovering the issue and within any period required by applicable law, provider rules, or the signed order. Edvatiq may request reasonable proof of identity, authority, and payment ownership.

## 11. Review process

Edvatiq will compare the request with invoices, payment-provider status, provisioning events, usage records, service incidents, and prior corrections. Complex or provider-dependent cases can require additional time or information.

The outcome may be approval, partial approval where legally and technically appropriate, denial with a reason, restoration of the purchased service, correction of an invoice, replacement of credits, or referral to the payment provider. Fraud, abuse, or conflicting ownership claims may be escalated for additional verification.

## 12. Approved refunds

Approved refunds are normally initiated through the original payment method and provider. If that method cannot receive the refund, another lawful method may be considered after identity and ownership checks.

The provider and receiving bank control final posting time after initiation. Taxes, discounts, credits, and partial adjustments will be handled according to the original invoice, provider capability, and applicable law. Edvatiq will retain the refund reference and corresponding accounting record.

## 13. Plan changes and partial periods

Upgrades, downgrades, and plan replacements may change features, limits, and future charges. Any proration, credit, or immediate charge will be shown before confirmation where supported.

Cancellation during a paid term does not automatically create a refund for unused days. A signed order, displayed checkout term, documented service failure, or mandatory legal right can provide a different result.

## 14. Chargebacks and payment disputes

Before raising a payment dispute, contact {{support_email}} so the transaction can be identified and a correction attempted. A chargeback or bank dispute can temporarily restrict the related workspace while ownership, fraud, and payment status are investigated.

This does not prevent a payer from using rights available through a bank, payment provider, regulator, or law. Providing accurate references helps avoid duplicate refunds or conflicting outcomes.

## 15. Suspension and termination

Cancellation of future renewal is different from suspension or termination for breach. A workspace restricted for security, unlawful use, payment reversal, or material violation is not automatically entitled to a refund.

Edvatiq will consider the cause, service supplied, evidence, and applicable rights when reviewing any related request. Records may remain retained for payment, tax, audit, fraud, dispute, or legal obligations.

## 16. Statutory and consumer rights

Nothing in this Policy excludes or limits rights concerning deficient services, incorrectly described services, unauthorized or duplicate charges, or other remedies that cannot legally be excluded. If a provision conflicts with mandatory law, the mandatory rule applies to the extent of the conflict.

## 17. Changes to this Policy

New versions may be published for product, provider, commercial, or legal changes. The version accepted for a purchase remains available as historical evidence. The current version and effective date are displayed on this page.

## 18. Contact and grievance channel

Refund and cancellation requests may be sent to {{support_email}}. Formal grievances may be directed to {{grievance_contact}}. The operator is {{legal_name}}, {{registered_address}}, and disputes are subject to the jurisdiction stated in the Terms of Service, except where mandatory law provides another remedy or forum.
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
