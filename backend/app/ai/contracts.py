"""Versioned, validated response blocks for the AI business interface."""
from typing import Any, Literal

from pydantic import BaseModel, Field


class ResponseBlock(BaseModel):
    id: str
    type: Literal["text", "kpi_grid", "chart", "entity_cards", "table", "timeline", "alert", "action", "empty"]
    title: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    document_id: str
    document: str
    excerpt: str
    page: int | None = None
    section: str | None = None
    href: str


class AIResponseV1(BaseModel):
    schema_version: Literal[1] = 1
    summary: str
    blocks: list[ResponseBlock] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    result_session_id: str | None = None


KPI_LABELS = {
    "today_revenue_paise": "Today revenue",
    "month_revenue_paise": "Month revenue",
    "active_clients": "Active clients",
    "appointments_today": "Appointments today",
    "low_stock_items": "Low stock",
    "employees": "Team members",
}


def compose_response(summary: str, trace: list[dict]) -> AIResponseV1:
    """Convert trusted tool output to a small, deterministic UI schema."""
    blocks: list[ResponseBlock] = []
    citations: list[Citation] = []
    actions: list[dict] = []
    result_session_id = None

    for index, item in enumerate(trace):
        result = item.get("result") or {}
        if result.get("access_denied") or result.get("error"):
            continue
        name = item.get("name")
        presentation = result.get("presentation") or {}
        if name == "business_summary":
            values = []
            for key, label in KPI_LABELS.items():
                if key in result:
                    values.append({"label": label, "value": result[key], "format": "money" if key.endswith("_paise") else "number"})
            blocks.append(ResponseBlock(id=f"kpi-{index}", type="kpi_grid", title="Business snapshot", data={"items": values}))
        elif presentation.get("type") == "chart":
            blocks.append(ResponseBlock(id=f"chart-{index}", type="chart", title=presentation.get("title"), data={
                "chart_type": presentation.get("chart_type", "line"),
                "x_key": "label", "series": presentation.get("series", []),
                "rows": result.get("rows", [])[:100],
            }))
        elif result.get("items") is not None:
            items = result.get("items", [])[:5]
            block_type = "entity_cards" if presentation.get("display") == "cards" else "table"
            exact_count = bool(result.get("count_is_exact", result.get("count") is not None))
            blocks.append(ResponseBlock(id=f"records-{index}", type=block_type, title=presentation.get("title") or "Results", data={
                "items": items, "columns": presentation.get("columns", []),
                "total": result.get("count") if exact_count else None,
                "count_is_exact": exact_count, "has_more": bool(result.get("has_more")),
                "result_session_id": result.get("result_session_id"), "query_spec": result.get("query_spec"),
                "entity_kind": presentation.get("entity_kind"),
            }))
            result_session_id = result.get("result_session_id") or result_session_id
        if result.get("citations"):
            citations.extend(Citation.model_validate(row) for row in result["citations"])
        if result.get("action_id"):
            safe_action = {key: result.get(key) for key in [
                "action_id", "status", "risk_level", "preview", "confirmation_token", "result", "undo_expires_at"
            ] if result.get(key) is not None}
            actions.append(safe_action)
            blocks.append(ResponseBlock(id=f"action-{index}", type="action", title=result.get("preview", {}).get("title"), data=safe_action))

    if not blocks:
        blocks.append(ResponseBlock(id="summary", type="text", data={"text": summary}))
    return AIResponseV1(summary=summary, blocks=blocks, citations=citations, actions=actions, result_session_id=result_session_id)
