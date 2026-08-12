# College integration schemas

All push fields use JSON names shown below. Pull integrations may map source field names to these canonical fields.

## Students

Required: `external_id`, `admission_number`, `first_name`, `program_code`, `cohort_code`.

Optional: `last_name`, `email`, `phone`, `current_semester` from 1 to 16.

Programs and cohorts must already exist with matching codes. Student identity is upserted by connector, resource, and external ID.

## Term results

Required: `external_id`, `admission_number`, `semester`.

Optional: `sgpa`, `cgpa`, `active_backlogs`, `total_backlogs`, `credits_earned`, `published_on` in `YYYY-MM-DD` format. GPA values must be between 0 and 10.

## Attendance

Required: `external_id`, `admission_number`.

Optional: `scope`, `classes_held`, `classes_attended`, `attendance_percent`, `as_of`. Attended classes cannot exceed held classes.

## Skills

Required: `external_id`, `admission_number`, `title`.

Optional: `proficiency`, `verified`, `evidence_url`. Verification should reflect an institutional review, not an unreviewed resume extraction.

## Assessments

Required: `external_id`, `admission_number`, `title`.

Optional: `assessment_type`, `score_percent`, `assessed_on`, `provider`. Percentages must be between 0 and 100.

## Internship clearance

Required: `external_id`, `admission_number`, `status`.

Optional: `as_of`, `source_updated_at`. Status must be `cleared`, `pending`, or `needs_review`.

```json
{
  "external_id": "clearance-2027-042-2026-08",
  "admission_number": "CSE-2027-042",
  "status": "cleared",
  "as_of": "2026-08-12",
  "source_updated_at": "2026-08-12T09:30:00Z"
}
```

Do not send fee amounts through internship clearance. Placement users receive only status, source time, and freshness.
