"""Regression coverage for declared College authorization boundaries."""
from fastapi.routing import APIRoute

from app.services.policy_contracts import college_route_contract
from server import app


def test_every_college_browser_route_declares_policy_metadata():
    routes = [
        route for route in app.routes
        if isinstance(route, APIRoute)
        and (route.path.startswith("/api/college") or route.path.startswith("/api/data-exchange"))
    ]
    assert routes
    for route in routes:
        for method in route.methods - {"HEAD", "OPTIONS"}:
            contract = college_route_contract(route.path, method)
            assert contract is not None, f"Missing policy contract: {method} {route.path}"
            assert route.openapi_extra["x-edvatiq-policy"] == contract.payload()
            assert route.endpoint.__edvatiq_policy__ == contract.payload()


def test_unknown_college_route_fails_closed():
    assert college_route_contract("/api/college/new-unguarded-area", "GET") is None


def test_sensitive_exports_require_view_plus_explicit_export_capability():
    contract = college_route_contract("/api/data-exchange/exports", "POST")
    assert contract is not None
    assert contract.domain == "data"
    assert contract.level == "view"
    assert contract.capabilities == ("college.data.export",)


def test_college_home_uses_the_scoped_reports_domain():
    contract = college_route_contract("/api/college/placement-dashboard", "GET")
    assert contract is not None
    assert contract.domain == "reports"
    assert contract.level == "view"
