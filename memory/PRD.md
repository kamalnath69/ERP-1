# Athena Education ERP — PRD

## Original problem statement
Build a production-grade AI-powered Education ERP SaaS platform that serves both
Schools and Colleges from a single codebase. Enterprise, multi-tenant, AI-first,
with dynamic RBAC/ABAC, ChatGPT-style assistant with tool calling, analytics,
reports, and a superadmin console.

## Architecture (delivered)
- **Backend**: FastAPI + SQLAlchemy 2.0 + PostgreSQL (15) + Alembic-ready. Clean
  layering: `core/`, `models/`, `schemas/`, `services/`, `api/v1/`, `ai/`, `db/`.
- **Frontend**: React 19 + TailwindCSS + shadcn/ui + Recharts + React Router + Sonner.
- **Auth**: JWT access + refresh tokens (argon2 password hashing, refresh rotation).
- **Multi-tenancy**: every business table carries `organization_id`; enforced at API layer.
- **RBAC + ABAC**: dynamic roles + per-user permission overrides + scope table.
- **AI**: multi-provider (OpenAI GPT-5.4 default + Gemini 3 Flash) via the Emergent proxy,
  OpenAI-compatible tool calling, tools authorized via authenticated user.
- **Billing**: Razorpay orders + webhook + mock-pay dev endpoint.
- **Audit log**: every mutation and AI query written to `audit_logs`.
- **Feature flags**: per-org toggles for modules.

## User personas
- **Super Admin** — platform ops, creates/suspends/activates organizations.
- **Principal / Administrator** — full tenant admin.
- **HOD / Class Advisor / Faculty** — role-scoped teaching workflows.
- **Student / Parent** — read-only self-views.

## Phase 1 — DELIVERED (2026-02)
- [x] Multi-tenant registration with slug + admin bootstrap
- [x] JWT + refresh flow, /auth/me
- [x] Dynamic Role & Permission editor (matrix by module)
- [x] Users, Faculty, Students CRUD
- [x] Academic structure (Departments, Units, Levels, Sections, Subjects)
- [x] Attendance marking (grid) + summary aggregation
- [x] Exams + Marks entry + publish workflow
- [x] Athena AI Chat with 9 registered tools (search, profile, attendance,
      marks, dept summary, faculty, risk prediction, analytics KPIs)
- [x] Analytics dashboard (attendance trend, dept distribution, KPIs)
- [x] Super Admin console (orgs, health, suspend/activate)
- [x] Billing page (plans, invoices, Razorpay order + mock-pay)
- [x] Audit log viewer
- [x] Feature flags UI
- [x] Landing page (Bento grid, hero, pricing) + Login + Register

## Backlog (P1)
- [ ] Parent portal + Parent-Student linking flow in UI
- [ ] Access Scope editor (ABAC) — table exists, UI not built
- [ ] Faculty assignments UI (subject × section)
- [ ] Timetable & Academic calendar
- [ ] Fees module (Razorpay recurring subscriptions)
- [ ] Reports export (PDF/Excel) endpoints
- [ ] Notifications sending + email delivery (SendGrid/Resend)
- [ ] Alembic migrations wired in (currently `create_all`)

## Backlog (P2)
- [ ] RAG over policy docs, curriculum
- [ ] Sentiment analysis on feedback
- [ ] Placement, Library, Transport, Hostel modules
- [ ] NBA / NAAC compliance workflows
- [ ] Celery + Redis for scheduled jobs (webhook retries, notifications)

## Known limitations
- **AI credits** — Emergent Universal Key needs balance top-up (Profile → Universal Key → Add Balance). Otherwise `/api/ai/chat` returns budget-exceeded errors. Everything else works without it.
- Razorpay uses placeholder keys → `/billing/orders/{id}/mock-pay` demo endpoint is what powers the upgrade flow until real keys are added to `.env`.
- Alembic migrations are set up structurally but the app currently uses `Base.metadata.create_all` for schema bootstrap.
EOF
