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
