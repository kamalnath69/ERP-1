# Edvatiq Business Manager

Edvatiq is a multi-tenant, multi-location SaaS operations platform for Indian gyms, salons, outpatient clinics, and colleges. It combines relationship records, scheduling, finance, inventory, staff access, vertical workflows, multilingual AI, documents, notifications, reporting, and subscription enforcement.

## Stack

- React 19, Tailwind CSS, shadcn/ui, React Router
- FastAPI, SQLAlchemy 2, Alembic
- PostgreSQL
- OpenAI Responses API with tenant-scoped tools
- S3-compatible storage, SMTP, Meta WhatsApp Cloud, Razorpay

## Development

Backend configuration lives in `backend/.env`.

```powershell
cd backend
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn server:app --reload
```

```powershell
cd frontend
npm install
npm start
```

The seeded Gym demo uses `owner@pulse-fitness.edvatiq.com` / `Owner@123`; the College demo uses `owner@crescent-college.edvatiq.com` / `Owner@123`. Provider integrations run in mock mode by default.

## Supabase PostgreSQL

Edvatiq uses Supabase as a standard PostgreSQL server through SQLAlchemy and Alembic. Keep database credentials on the backend only; the React application must never receive the Postgres connection string.

The supplied direct project endpoint requires IPv6. Use it for a persistent backend with IPv6 connectivity. This project's IPv4 Session pooler is the default in the setup script, so local Windows setup is:

```powershell
cd backend
.\scripts\configure_supabase.ps1
python -m alembic upgrade head
```

On an IPv6-capable backend, explicitly select the direct endpoint:

```powershell
cd backend
.\scripts\configure_supabase.ps1 -HostName "db.fyebyevqueurgubyiyir.supabase.co" -UserName "postgres"
python -m alembic upgrade head
```

The script requests the database password through a hidden prompt, safely encodes it, enables SSL, and does not print it. Edvatiq migrations enable the `vector` and `pg_trgm` extensions required by document knowledge and typo-tolerant search. See Supabase's [connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres) and [extension guide](https://supabase.com/docs/guides/database/extensions).

## Authentication and Resend Email

Browser sessions use short-lived HttpOnly access cookies, rotating HttpOnly refresh cookies, signed CSRF tokens, and immediate session revocation after password reset. JWTs are never stored in browser storage or returned by login endpoints.

For verification, password-reset, invitations, and queued email, create a Resend API key and configure `backend/.env`:

```dotenv
EMAIL_PROVIDER=resend
RESEND_API_KEY=re_your_api_key
RESEND_FROM_EMAIL=Edvatiq <hello@your-verified-domain.com>
```

Resend's `onboarding@resend.dev` sender may be used during setup, subject to Resend's testing-recipient restrictions. Set `EMAIL_PROVIDER=smtp` only when intentionally using the legacy SMTP fallback.

## WhatsApp customer updates

Email is reserved for account verification, password recovery, and secure invitations. Consented customer service updates and reminders use Meta WhatsApp Cloud API templates through the PostgreSQL worker.

```dotenv
WHATSAPP_TOKEN=your-permanent-system-user-token
WHATSAPP_PHONE_NUMBER_ID=your-phone-number-id
WHATSAPP_GRAPH_VERSION=v23.0
WHATSAPP_DEFAULT_COUNTRY_CODE=91
WHATSAPP_TEMPLATE_LANGUAGE=en
WHATSAPP_REMINDERS_ENABLED=true
```

Create and approve these Utility templates in WhatsApp Manager with the matching body-variable order:

- `appointment_confirmation`: customer name, business name, date, time, location.
- `appointment_reminder`: customer name, business name, date, time, location.
- `appointment_status_update`: customer name, business name, status, date, time.
- `membership_update`: customer name, plan name, business name, status, valid-until date.
- `membership_expiry_reminder`: customer name, plan name, expiry date, days remaining, business name.
- `customer_update`: customer name, update text, business name.

Keep `WHATSAPP_REMINDERS_ENABLED=false` until credentials and templates are approved. Customers must explicitly consent and have a valid phone number before any message is queued. Provider calls remain mocked while `PROVIDER_MOCK_MODE=true`.

Production HTTPS deployments must also use explicit origins and Secure cookies:

```dotenv
APP_URL=https://app.example.com
CORS_ORIGINS=https://app.example.com
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=lax
AUTH_COOKIE_DOMAIN=
```

Keep `AUTH_COOKIE_SECURE=false` only for local `http://localhost` development. Restart the API after changing environment values.

## Razorpay Test and Live Payments

Payment mode is selected on the server. Test and live credentials are stored separately so they cannot be mixed accidentally.

```dotenv
RAZORPAY_MODE=test
RAZORPAY_TEST_KEY_ID=rzp_test_your_key_id
RAZORPAY_TEST_KEY_SECRET=your_test_key_secret
RAZORPAY_TEST_WEBHOOK_SECRET=your_test_webhook_secret

RAZORPAY_LIVE_KEY_ID=
RAZORPAY_LIVE_KEY_SECRET=
RAZORPAY_LIVE_WEBHOOK_SECRET=
```

Use `RAZORPAY_MODE=mock` for local payments without Razorpay, `test` for Razorpay's simulated payment flow, and `live` only after live credentials and the live webhook are configured. Existing `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET` values remain supported when their key prefix matches the selected mode.

Configure the active Razorpay dashboard webhook as:

```text
https://your-api-domain.example/api/billing/webhook
```

Subscribe to `payment.captured`, `payment.failed`, and `order.paid`. Razorpay requires a public HTTPS URL and does not deliver webhooks to localhost.

Run the durable document and notification worker separately:

```powershell
cd backend
python -m app.worker
```

## Vercel frontend deployment

Deploy only the `frontend` directory to Vercel and keep FastAPI, PostgreSQL, and workers on persistent infrastructure. In the Vercel project:

1. Set **Root Directory** to `frontend`.
2. Add `EDVATIQ_API_ORIGIN=https://your-api-domain.example` to Production and Preview.
3. Leave `VITE_BACKEND_URL` unset so `/api/*` uses the authenticated same-origin proxy.
4. Add the final frontend URL to the backend `APP_URL` and `CORS_ORIGINS`, enable secure cookies, then redeploy both services.

The frontend Vercel configuration preserves React Router deep links, proxies API and streaming requests, and applies immutable caching only to hashed static assets.
