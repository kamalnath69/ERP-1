# Integration security

## Secrets

Pull API keys are encrypted server-side. Push credentials are stored only as hashes and the complete secret is displayed once. Rotate a credential if it may have been exposed.

## Network controls

ERP pull accepts credential-free HTTPS URLs, blocks private and reserved destinations, rejects redirects, and keeps pagination on the configured origin.

## Scope and isolation

Every push credential belongs to one organization and contains explicit resource scopes. Run lookup is limited to runs created by that same credential. Tenant and role checks apply independently to the management interface.

## Logs and support

Do not put credentials in connector names, idempotency keys, filenames, or support requests. Audit logs record metadata such as scope, expiry, and action without recording complete secrets.
