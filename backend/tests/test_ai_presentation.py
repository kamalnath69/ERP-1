import json

from app.ai.catalog import catalog_for
from app.ai.contracts import (
    Artifact, AssistantOutcome, AssistantResponse, QueryGoal, SemanticQuery,
    Suggestion,
)
from app.ai.engine import STRICT_ANSWER_TOOL
from app.ai.presentation import decorate_artifact, decorate_response


INTERNAL_UUID = "f94d1b70-cf8e-42e4-8177-6781a6de3602"
CLIENT_UUID = "7f7d8d24-c151-4dd0-96fa-fbd0bfa70c49"


def _student_query():
    return SemanticQuery(
        goal=QueryGoal.PROFILE,
        entity="student",
        fields=["id", "name", "program", "cgpa"],
    )


def test_presentation_removes_storage_ids_but_preserves_private_navigation_ref():
    artifact = Artifact(
        id="artifact-profile",
        type="profile",
        title="Lokesh Menon",
        data={
            "id": INTERNAL_UUID,
            "name": "Lokesh Menon",
            "program": {
                "id": INTERNAL_UUID,
                "code": "BSC-CS",
                "name": "B.Sc. Computer Science",
            },
            "cgpa": 7.03,
            "profile_ref": {"kind": "client", "id": CLIENT_UUID},
        },
    )

    result = decorate_artifact(artifact, _student_query(), catalog_for("college"))

    assert "id" not in result.data
    assert result.data["program"] == {
        "code": "BSC-CS", "name": "B.Sc. Computer Science",
    }
    assert result.data["profile_ref"] == {"kind": "client", "id": CLIENT_UUID}
    assert result.presentation.layout == "profile"
    assert {field.key for field in result.presentation.fields} == {
        "name", "program", "cgpa",
    }
    assert result.presentation.fields[0].role == "title"


def test_user_visible_answer_and_suggestion_text_never_contains_a_uuid():
    response = AssistantResponse(
        outcome=AssistantOutcome.SUCCESS,
        answer=f"Lokesh has internal ID {INTERNAL_UUID}.",
        artifacts=[Artifact(
            id="artifact-profile", type="profile",
            data={"name": "Lokesh", "department": {"id": INTERNAL_UUID, "name": "CSE"}},
        )],
        suggestions=[Suggestion(
            id="suggestion-1",
            label=f"Open {INTERNAL_UUID}",
            prompt=f"Tell me about {INTERNAL_UUID}",
        )],
    )

    result = decorate_response(response, _student_query(), catalog_for("college"))
    visible = {
        "answer": result.answer,
        "artifact": result.artifacts[0].data,
        "suggestions": [item.model_dump(mode="json") for item in result.suggestions],
    }

    assert INTERNAL_UUID not in json.dumps(visible)


def test_answer_model_cannot_replace_security_labelled_suggestions():
    parameters = STRICT_ANSWER_TOOL["parameters"]

    assert parameters["required"] == ["sections"]
    assert "suggestions" not in parameters["properties"]
    assert parameters["additionalProperties"] is False
