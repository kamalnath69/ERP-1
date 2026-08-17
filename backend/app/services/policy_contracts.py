"""Declared authorization contracts for College-facing HTTP routes."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from fastapi import FastAPI
from fastapi.routing import APIRoute


@dataclass(frozen=True)
class RoutePolicyContract:
    domain: str
    level: str
    capabilities: tuple[str, ...] = ()

    def payload(self) -> dict:
        return asdict(self)


def _contract(domain: str, method: str, *, manage_writes: bool = False, capabilities=()):
    if method == "GET":
        level = "view"
    else:
        level = "manage" if manage_writes else "work"
    return RoutePolicyContract(domain, level, tuple(capabilities))


def college_route_contract(path: str, method: str) -> RoutePolicyContract | None:
    """Resolve explicit policy metadata for a College browser route.

    This deliberately has no catch-all. A newly introduced route must be
    assigned to a domain here or application startup fails.
    """
    path = path.removeprefix("/api")
    method = method.upper()

    if path.startswith("/data-exchange"):
        if path == "/data-exchange/exports":
            return RoutePolicyContract("data", "view", ("college.data.export",))
        capabilities = ()
        return _contract("data", method, capabilities=capabilities)

    if not path.startswith("/college"):
        return None

    if path.startswith("/college/integrations/credentials"):
        return _contract("data", method, manage_writes=True, capabilities=("college.integrations.manage",))
    if path.startswith("/college/integrations") or path.startswith("/college/imports"):
        return _contract("data", method, manage_writes=True, capabilities=("college.integrations.manage",) if path.startswith("/college/integrations") else ())
    if path.startswith("/college/internship-clearance"):
        return _contract("clearance", method)
    if path.startswith("/college/fee-plans"):
        return _contract("clearance", method, manage_writes=True, capabilities=("college.fees.manage",))
    if path.startswith("/college/student-fees"):
        return _contract("clearance", method, capabilities=("college.fees.manage",))

    if path in {"/college/placement-dashboard"}:
        return _contract("reports", method)
    if path.startswith("/college/leaderboards") or path.startswith("/college/student-intelligence"):
        return _contract("readiness", method)
    if path.startswith("/college/readiness-policy"):
        capabilities = ("college.readiness.policy.manage",) if method != "GET" else ()
        return _contract("readiness", method, manage_writes=True, capabilities=capabilities)
    if path.startswith("/college/readiness/"):
        return _contract("readiness", method, manage_writes=True)

    if path in {
        "/college/students/hierarchy",
        "/college/students/summary",
        "/college/students/page",
    }:
        return _contract("students", method)
    if path.startswith("/college/students/"):
        if path.endswith("/intelligence"):
            return _contract("readiness", method)
        if "/coding-" in path:
            return _contract("coding", method)
        if path.endswith("/term-results") or path.endswith("/placement-assessments"):
            return _contract("assessments", method)
        if path.endswith("/attendance-snapshots"):
            return _contract("attendance", method)
        if path.endswith("/resume/extract"):
            return _contract("documents", method, capabilities=("college.documents.sensitive.view",))
        if path.endswith("/career") or path.endswith("/evidence") or path.endswith("/preparation") or path.endswith("/interventions"):
            capabilities = ("college.documents.sensitive.view",) if path.endswith("/evidence") else ()
            return _contract("readiness", method, capabilities=capabilities)
    if path == "/college/students":
        return _contract("students", method, manage_writes=True)
    if path.startswith("/college/interventions"):
        return _contract("readiness", method, capabilities=("college.notes.private.view",))
    if path.startswith("/college/resume-drafts"):
        return _contract("documents", method, capabilities=("college.documents.sensitive.view",))
    if path.startswith("/college/coding/"):
        return _contract("coding", method)

    if path.startswith("/college/pipeline") or path.startswith("/college/companies") or path.startswith("/college/opportunities") or path.startswith("/college/applications"):
        capabilities = ("college.eligibility.override",) if path.endswith("/eligibility-override") else ()
        return _contract("placements", method, manage_writes=path.startswith("/college/pipeline"), capabilities=capabilities)

    if path.startswith("/college/assessment-schemes") or path.startswith("/college/exam-cycles"):
        capabilities = ("college.readiness.policy.manage",) if path.endswith("/readiness-mappings") and method != "GET" else ()
        return _contract("assessments", method, manage_writes=True, capabilities=capabilities)
    if path.startswith("/college/assessments"):
        return _contract("assessments", method)
    if path.startswith("/college/attendance"):
        return _contract("attendance", method)
    if path.startswith("/college/academic-evidence"):
        return _contract("assessments", method)

    academic_roots = (
        "/college/academics/summary", "/college/academic-hierarchy", "/college/departments", "/college/programs",
        "/college/terms", "/college/cohorts", "/college/courses", "/college/offerings",
        "/college/{resource}",
    )
    if path.startswith(academic_roots):
        return _contract("academics", method, manage_writes=True)
    if path == "/college/references":
        return _contract("academics", method)
    if path == "/college/workspace":
        return _contract("students", method)
    return None


def attach_college_policy_contracts(app: FastAPI) -> None:
    """Attach OpenAPI metadata and fail startup for unclassified routes."""
    missing: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not (route.path.startswith("/api/college") or route.path.startswith("/api/data-exchange")):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            contract = college_route_contract(route.path, method)
            if contract is None:
                missing.append(f"{method} {route.path}")
                continue
            payload = contract.payload()
            route.openapi_extra = {**(route.openapi_extra or {}), "x-edvatiq-policy": payload}
            setattr(route.endpoint, "__edvatiq_policy__", payload)
    if missing:
        raise RuntimeError("College routes are missing policy contracts: " + ", ".join(missing))
