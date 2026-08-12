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

## Pagination

Cursor mode reads a configured cursor path and sends it with the configured cursor parameter. `updated_since` mode sends the last successful synchronization time. A same-origin next URL can also be configured. A run stops after 100 pages.

## Commit behavior

Every page enters the same staging and validation pipeline as CSV and push ingestion. Valid rows are upserted using connector, resource, and external ID. Missing source records are never interpreted as deletion. Reviewed manual overrides remain authoritative until released.
