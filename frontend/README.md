# Edvatiq Frontend

The frontend is a React 19 application built with Vite.

## Development

```powershell
yarn install
yarn dev
```

The development server runs at `http://localhost:3000`. `yarn start` is retained as an alias for environments that already use it.

## Environment

Set `VITE_BACKEND_URL` to the backend origin. The existing `REACT_APP_BACKEND_URL` name remains supported during deployment migration.

Set `ENABLE_HEALTH_CHECK=true` to expose `/health`, `/health/simple`, `/health/ready`, `/health/live`, `/health/errors`, and `/health/stats` on the development server.

## Verification

```powershell
yarn test
yarn build
yarn preview
```

Production output is written to `build/` to preserve the existing deployment contract.

## Vercel

Create one Vercel project for the frontend and set its **Root Directory** to `frontend`. The checked-in `vercel.json` selects Vite, builds to `build/`, supports React Router deep links, and proxies `/api/*` to the separately hosted backend.

Do not set `VITE_BACKEND_URL`, `REACT_APP_BACKEND_URL`, or `EDVATIQ_API_ORIGIN` in Vercel. Browser requests use the same-origin `/api` proxy defined in `vercel.json`, which preserves authentication and CSRF cookies.

Configure the external backend for the deployed frontend URL:

```dotenv
APP_URL=https://app.example.com
CORS_ORIGINS=https://app.example.com
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=lax
AUTH_COOKIE_DOMAIN=
```

Use the custom frontend domain for `APP_URL`. Preview deployments can safely use the same proxy configuration because their cookies remain scoped to the preview hostname.
