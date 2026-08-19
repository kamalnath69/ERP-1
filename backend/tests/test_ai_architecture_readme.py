import re
from pathlib import Path
from typing import get_args

from app.ai.contracts import Artifact, AssistantOutcome, QueryGoal


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE_README = BACKEND_ROOT / "app" / "ai" / "README.md"
AI_API = BACKEND_ROOT / "app" / "api" / "v1" / "ai.py"


def test_ai_architecture_readme_tracks_public_contracts_and_routes():
    documentation = ARCHITECTURE_README.read_text(encoding="utf-8")

    assert "## Maintenance contract" in documentation
    for outcome in AssistantOutcome:
        assert f"`{outcome.value}`" in documentation
    for goal in QueryGoal:
        assert f"`{goal.value}`" in documentation
    for artifact_type in get_args(Artifact.model_fields["type"].annotation):
        assert f"`{artifact_type}`" in documentation

    api_source = AI_API.read_text(encoding="utf-8")
    routes = re.findall(
        r'@router\.(get|post|put|patch|delete)\("([^"]+)"',
        api_source,
    )
    assert routes
    for method, path in routes:
        assert f"`{method.upper()} /api/ai{path}`" in documentation


def test_ai_architecture_readme_names_every_canonical_module():
    documentation = ARCHITECTURE_README.read_text(encoding="utf-8")
    modules = {
        path.name
        for path in (BACKEND_ROOT / "app" / "ai").glob("*.py")
        if path.name != "__init__.py"
    }
    modules.update({"domains/common.py", "domains/business.py", "domains/college.py"})

    for module in modules:
        assert f"`{module}`" in documentation
