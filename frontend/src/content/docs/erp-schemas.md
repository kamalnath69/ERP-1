# College integration schemas

All push fields use JSON names shown below. Pull integrations may map source field names to these canonical fields.

## Dependency order

Synchronize structure before dependent records:

1. `departments`
2. `programs`
3. `cohorts`
4. `terms` and `courses`
5. `students`
6. exam cycles
7. results, attendance, skills, dynamic assessment marks, and internship clearance

Normal structure and evidence records require `external_id`. Exam cycles and dynamic marks instead use `scheme_code`, `scheme_version`, and `cycle_code`. Exact code collisions with an unlinked local record are quarantined for reviewed linking; Edvatiq never silently claims or overwrites the record. Once linked, ERP updates change only fields that do not have a manual override. When `source_updated_at` is supplied, an older snapshot or changed content with the same timestamp is quarantined instead of replacing newer data. A source record disappearing never archives or deletes its local record.

## Departments

Required: `external_id`, `name`, `code`.

Optional: `description`, `source_updated_at`.

## Programs

Required: `external_id`, `department_code`, `name`, `code`.

Optional: `degree_type`, `duration_semesters`, `source_updated_at`. `department_code` must resolve to an active department.

## Graduation batches and sections

Required: `external_id`, `program_code`, `name`, `code`, `admission_year`, `graduation_year`.

Optional: `current_semester`, `section`, `source_updated_at`. Blank sections are normalized to `GENERAL`. A program, graduation year, and normalized section combination can exist only once.

## Academic years and terms

Required: `external_id`, `name`, `academic_year`, `term_number`, `starts_on`, `ends_on`.

Optional: `status`, `is_current`, `source_updated_at`. Dates use `YYYY-MM-DD`, and the end date must be after the start date.

## Courses

Required: `external_id`, `department_code`, `name`, `code`.

Optional: `credits`, `course_type`, `source_updated_at`. Courses may be synchronized before teaching offerings are configured in Edvatiq.

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

## Legacy placement assessments

Required: `external_id`, `admission_number`, `title`.

Optional: `assessment_type`, `score_percent`, `assessed_on`, `provider`. Percentages must be between 0 and 100.

This compatibility resource is for simple historical placement evidence. New academic, coding, and placement tests should use institution-configured exam cycles and `assessment_marks`.

## Exam cycles

Required: `scheme_code`, `scheme_version`, `cycle_code`, and `cycle_name`.

Academic cycles also require `component_code` and one or more `offering_ids`. Coding and placement cycles require one or more `cohort_ids`. Optional fields include `term_id`, `held_on`, and `due_on`. The referenced pattern revision must already be active and is frozen when the first cycle is committed.

## Dynamic assessment marks

Required: `scheme_code`, `scheme_version`, `cycle_code`, `student`, and `metrics`.

Fetch `GET /api/integrations/v1/college/schemas/assessment_marks?cycle_code=...` for the selected college and cycle. The returned schema is authoritative for metric names, types, maxima, and required fields. If an academic cycle contains more than one assessment for a student's cohort, `academic_scope.assessment_id` or `academic_scope.offering_id` is required. Published marks cannot be silently replaced through ERP push.

## Internship clearance

Required: `external_id`, `admission_number`, `status`.

Optional: `as_of`, `source_updated_at`. Status must be `cleared`, `pending`, or `needs_review`.

```json
{
  "external_id": "clearance-2027-042-2026-08",
  "admission_number": "ADM-2027-042",
  "status": "cleared",
  "as_of": "2026-08-12",
  "source_updated_at": "2026-08-12T09:30:00Z"
}
```

Do not send fee amounts through internship clearance. Placement users receive only status, source time, and freshness.
