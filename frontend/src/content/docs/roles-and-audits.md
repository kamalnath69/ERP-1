# Roles, permissions, and audits

The interface may hide unavailable actions, but the API independently enforces every permission and tenant boundary.

## Least privilege

Use a role that contains only the capabilities needed for the person's job. Owners can review permissions from Access. College roles can also be restricted by department, program, batch, cohort, and assigned students.

## Sensitive actions

Payments, refunds, membership lifecycle changes, placement eligibility overrides, application stage changes, communications, and AI-assisted mutations may require confirmation, a reason, or an optimistic version.

## Audit history

Audit entries identify the action, responsible user, time, affected record, and safe metadata. Secrets, passwords, complete integration tokens, and custom instruction contents are not written to audit logs.

## Support access

Platform support access is time-limited and separately audited. Limited support sessions cannot perform permanently restricted financial, access, export, deletion, or signing operations.
