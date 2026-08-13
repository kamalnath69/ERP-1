# Institution-configured assessment patterns

Edvatiq does not assume how many internals, practicals, assignments, coding tests, or placement assessments a college conducts. Academic administrators define the institution's terminology and rules once, and every register, template, ERP schema, and report follows that configuration.

## Configure a pattern

Open **College > Academic evidence > Academic structure > Assessment patterns**. A pattern contains:

- A stable code, name, domain, and final score scale.
- Ordered components or custom metrics.
- A value type such as number, percentage, integer, count, rank, boolean, grade, or short text.
- Maximum values, weightage, pass thresholds, and required or optional status.
- A deterministic calculation: weighted sum, average, or best N of M.
- An optional minimum number of completed components before a final result is available.

For example, one institution can configure two internals. Another can configure three continuous assessments with the best two counted, a practical, and a semester examination. These examples are college data, never product constants.

## Assign effective scopes

Activate a pattern, then assign it to a scope. Edvatiq resolves one effective pattern using this order:

1. Graduation batch or section and term.
2. Program and term.
3. Graduation batch or section.
4. Program.
5. Institution default.

Two patterns cannot own the same exact scope. Assigning a newer revision of the same pattern upgrades that scope without changing historical cycles.

## Versions and history

Creating the first exam cycle freezes its pattern revision. Components, limits, and calculations can no longer be edited in place. Use **New version** for future cycles. Existing marks, exports, calculations, and ERP payloads remain attached to the original revision.

## Exam cycles and marks

An academic cycle instantiates one configured component across selected course offerings. Edvatiq aggregates component cycles for the same student, course offering, and pattern revision before calculating average, weighted, or best-N results.

Coding and placement cycles can target one or more cohorts and collect all configured metrics in one register. Manual forms, Excel, CSV, ERP pull, and API push validate against the same frozen metric schema.

Published corrections require the assessment-correction permission, an explanation, the current record version, and an audit entry containing before and after values.

## Readiness mapping

Assessment values do not influence placement readiness automatically. An authorized readiness administrator must map a numeric metric or the calculated pattern result to academics, coding, assessment, profile, attendance, or training. Disabling a mapping stops future recomputations from consuming it without deleting source marks or historical readiness snapshots.

