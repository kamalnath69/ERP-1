# College ERP pull integration

Pull synchronization lets Edvatiq read supported records from a College-controlled HTTPS API on a schedule or manual request.

## Connection requirements

- Use a credential-free public `https://` base URL.
- Authenticate with `Authorization: Bearer` or a configured custom header.
- Configure final endpoints directly; redirects are rejected.
- Resource and pagination URLs must remain on the configured origin.
- Private, loopback, link-local, reserved, and multicast destinations are rejected.

## Resource mapping

Each resource can define a path, JSON root path, source field names, and value maps. Dotted paths address nested objects. An integer path segment can address a list item.

```json
{
  "resources": {
    "students": {
      "path": "/v1/students",
      "root_path": "result.items",
      "fields": {
        "external_id": "student.id",
        "admission_number": "student.admissionNo",
        "first_name": "student.firstName",
        "program_code": "academic.programCode",
        "cohort_code": "academic.batchCode"
      },
      "value_maps": {}
    }
  }
}
```

Dynamic marks can either expose a canonical `metrics` object or map institution-defined metric codes to source paths. Edvatiq validates those keys against the immutable pattern revision identified by `scheme_code`, `scheme_version`, and `cycle_code`; it never invents an exam name or metric.

```json
{
  "resources": {
    "assessment_marks": {
      "path": "/v1/assessment-results",
      "root_path": "result.items",
      "fields": {
        "scheme_code": "exam.patternCode",
        "scheme_version": "exam.patternRevision",
        "cycle_code": "exam.cycleCode",
        "student": "student.admissionNumber",
        "metrics": "scores"
      },
      "metrics": {}
    }
  }
}
```

## Pagination

Cursor state is tracked separately for each configured resource. Cursor mode reads a configured cursor path and sends it with the configured cursor parameter until the resource is exhausted. `updated_since` mode sends the last successful synchronization time. A same-origin next URL can also be configured. A run stops after 100 pages per resource.

## Commit behavior

Every page enters the same staging and validation pipeline as CSV and push ingestion. Valid rows are upserted using connector, resource, and external ID. Missing source records are never interpreted as deletion. Reviewed manual overrides remain authoritative until released.
