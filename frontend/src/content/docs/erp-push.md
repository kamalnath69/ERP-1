# College ERP push API

The push API accepts supported College evidence from an external ERP using an organization-scoped credential.

## Credential lifecycle

Create a push credential from College > Data > ERP synchronization. Select only the required resource scopes and an expiry. The complete secret is shown once. Rotation immediately invalidates the old secret; revocation is permanent and audited.

```http
Authorization: Bearer edv_college_<prefix>_<secret>
Idempotency-Key: erp-export-2026-08-12-students-001
Content-Type: application/json
```

## Send a batch

```http
POST /api/integrations/v1/college/students
```

```json
{
  "records": [
    {
      "external_id": "erp-student-1042",
      "admission_number": "ADM-2027-042",
      "first_name": "Asha",
      "last_name": "Raman",
      "email": "asha@example.edu",
      "program_code": "BTECH-AIML",
      "cohort_code": "AIML-2027-A",
      "current_semester": 6
    }
  ],
  "sent_at": "2026-08-12T12:00:00Z"
}
```

The request accepts at most 500 records and 2 MB. Normal resources require a stable `external_id`. Dynamic `exam_cycles` and `assessment_marks` use their immutable pattern and cycle identifiers instead. A credential is limited to 60 requests per minute.

## Dynamic assessment data

Read the current cycle schema before sending marks:

```http
GET /api/integrations/v1/college/schemas/assessment_marks?cycle_code=PLACEMENT_DIAGNOSTIC_2027
```

The response contains the college's actual component codes, value types, limits, pattern revision, and academic-scope requirements. Send those fields inside `metrics`; unknown fields are quarantined rather than guessed.

```json
{
  "records": [{
    "scheme_code": "PLACEMENT_DIAGNOSTIC",
    "scheme_version": 3,
    "cycle_code": "PLACEMENT_DIAGNOSTIC_2027",
    "student": { "admission_number": "ADM-2027-042" },
    "academic_scope": { "assessment_id": "c8606b26-2bbb-4fcb-b48d-cfae3e6a3032" },
    "metrics": { "CODING_SCORE": 78, "SQL": 42, "TEST_CASES": 18 }
  }]
}
```

## Idempotency

Replay the same `Idempotency-Key` with identical content to receive the original run result. Reusing that key with changed content returns `409 Conflict`.

## Partial results

Valid rows commit automatically. Invalid rows are quarantined in the run result with row numbers and sanitized errors. Source values do not overwrite fields held by a reviewed manual override.

```json
{
  "run_id": "7b7fcb3d-7f4f-4d4f-a76c-d32fd52d4ab4",
  "resource": "students",
  "status": "partial",
  "received_count": 2,
  "committed_count": 1,
  "failed_count": 1,
  "errors": [{ "row": 2, "errors": ["program_code is required"] }],
  "replayed": false
}
```

## Run status and OpenAPI

Read a run created by the same credential at `GET /api/integrations/v1/college/runs/{run_id}`.

The filtered public contract is available at [integration OpenAPI](/api/integrations/v1/openapi.json). It does not contain browser, Super Admin, or cookie-authenticated endpoints.
