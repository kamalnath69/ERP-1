# Data Exchange

Data Exchange is the shared entry and export workspace for College structure, students, academic evidence, assessment cycles, placement records, and reporting data. It reads the current college hierarchy and effective assessment configuration before showing a method or generating a file.

## Entry methods

Each resource shows only the methods it genuinely supports:

- **Manual entry** for small changes and paged registers.
- **Excel** for guided workbooks with Instructions, Data, Lookups, and hidden Metadata sheets.
- **CSV** for one resource per file. Multi-resource academic structure downloads as an ordered ZIP package.
- **ERP pull** for scheduled, read-only HTTPS synchronization with source mapping.
- **API push** for organization-scoped, idempotent ERP batches.

Academic structure packages follow dependency order: departments, programs, graduation batches and sections, terms, courses, offerings, then assessment patterns. Excel keeps those resources in ordered worksheets and includes live Lookups and hidden Metadata sheets. The CSV package includes ordered resource files, `lookups.csv`, and a manifest.

Assessment files derive their columns from the selected frozen pattern revision; no fixed internal-exam columns are generated. A college with two internals receives two configured metric columns, while a college with three CIAs, assignments, practicals, or custom coding tests receives only those configured fields.

## Create and update templates

A blank create template adds new records only. It never silently updates, deletes, archives, or removes relationships. Natural-key collisions are shown as validation errors.

A prefilled update template includes stable `record_id` and `version` values. Blank update cells leave the existing value unchanged. Enter `__CLEAR__` only for an optional field that the schema marks as clearable. A stale version is rejected so a downloaded file cannot overwrite a newer browser, ERP, or file change.

## Preview and commit

Uploading a file creates a review run. The preview separates creates, updates, unchanged rows, warnings, invalid rows, conflicts, and out-of-scope rows. Nothing from a manual file is committed until the user confirms the valid set.

Invalid rows remain quarantined and can be downloaded as a correction workbook. Valid rows commit transactionally in dependency order. Formula cells, macros, malformed workbooks, unknown assessment metrics, missing parents, duplicate students, scores over configured limits, and unauthorized records are rejected.

## Scope and exports

Templates and exports can use a selected exam cycle, cohort, section, selected record IDs, current filters, or all authorized records. Multi-cohort mark workbooks contain only students and assessment fields in that selected scope.

Readiness, leaderboards, eligibility evidence, interviews, offers, outcomes, and audit history are export-only. Fees, invoices, resume files, private notes, and system-calculated readiness scores cannot be imported. Internship clearance accepts only `cleared`, `pending`, or `needs_review`; it never exchanges fee amounts.

## Limits and background work

The default file limits are 10 MB, 10,000 rows, 20 worksheets, and 200 columns. Imports above 1,000 rows and exports above 5,000 rows run as durable background jobs. The run remains available for status polling, retry-safe artifact download, and audit review.
