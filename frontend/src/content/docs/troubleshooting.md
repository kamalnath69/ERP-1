# Troubleshooting

## I cannot sign in

Verify the work email, password, and Workspace ID when the email belongs to more than one organization. If authenticator security is required, complete enrollment from the security page after sign-in.

## The browser reports a session error

Confirm the frontend and API use HTTPS in production, allowed CORS origins contain the exact frontend origin, cookies use `SameSite=None` and `Secure` for cross-site deployments, and `AUTH_COOKIE_DOMAIN` is empty when frontend and API do not share a parent domain.

## An ERP pull failed

Check that the final URL is public HTTPS, does not redirect, remains on one origin, and returns a list at the configured root path. Review the masked connector status and run errors without pasting API secrets into support messages.

## A push batch partially committed

Read the run result, correct only invalid source rows, and send a new idempotency key. Do not reuse the original key with changed content.

## Counts do not match

Check active filters, location or academic scope, record status, and source freshness. Counts and lists should use the same scope. Contact support with record IDs and filter details, not passwords or access tokens.
