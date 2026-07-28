"""Multi-provider LLM orchestrator with tool calling.

Uses the OpenAI and Google Generative AI SDKs directly
so we get real function-calling semantics rather than a text-only chat.
"""
import json
import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.ai.tools import TOOL_SCHEMAS, execute_tool
from app.core.config import settings
from app.models import ChatConversation, ChatMessage, User

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are Athena, the AI assistant inside an Education ERP.

Rules:
- For greetings, thanks, or general questions about yourself, respond conversationally WITHOUT calling any tool.
- For any data question (students, attendance, marks, departments, faculty, KPIs, risks), you MUST call the appropriate tool.
- Never guess data. Never fabricate names, numbers, or IDs. Never bypass a tool result.
- The caller has configurable **access scopes** enforced by the backend. If a tool returns
  a JSON object with `"access_denied": true`, you MUST surface the `message` field to
  the user verbatim (do not paraphrase, do not attempt another tool, and do NOT expose
  any protected data you may have seen in earlier turns).
- When the user references a student by name, ALWAYS call `search_students` first to disambiguate. If multiple students match, ask the user to clarify which one.
- If a tool result includes `scope_summary`, weave it into your reply so the user understands the boundary of their data.
- If the user asks "what can I ask about?", "what's my scope?" or similar, call the
  `my_access_scopes` tool and summarise the result in natural language.
- Once you have the required data, respond in clear, structured Markdown with headings, bullets, and small tables.
- Always speak in the user's language.
- Never expose raw IDs unless the user asks for them; prefer names.

**Tenant terminology** — the current organisation uses these words for hierarchy
entities. In every reply, prefer these words over the generic ones:
{terminology_block}
"""


def _build_system_prompt(db: Session, user: User) -> str:
    """Inject the tenant's terminology map so the LLM uses their words."""
    from app.models import Setting
    from sqlalchemy import select as _select

    terms: dict[str, str] = {
        "organization": "Organization", "campus": "Campus",
        "department": "Department", "academic_unit": "Academic Unit",
        "level": "Level", "section": "Section", "subject": "Subject",
        "student": "Student", "faculty": "Faculty",
        "exam": "Exam", "attendance": "Attendance",
    }
    if user.organization_id:
        row = db.execute(
            _select(Setting).where(
                Setting.organization_id == user.organization_id,
                Setting.key == "terminology",
            )
        ).scalar_one_or_none()
        if row and row.value:
            for k, v in (row.value or {}).items():
                if isinstance(v, str) and v.strip():
                    terms[k] = v.strip()
    block = "\n".join(f"  - {k} → {v}" for k, v in terms.items())
    return SYSTEM_PROMPT_TEMPLATE.replace("{terminology_block}", block)


async def run_chat(
    db: Session,
    user: User,
    conversation: ChatConversation,
    user_message: str,
) -> dict[str, Any]:
    """Run a single user turn with tool calling. Returns dict with assistant content and tool_calls trace."""
    provider = (conversation.provider or "openai").lower()

    # Load prior messages for context
    history_msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    if provider == "gemini":
        return await _run_gemini(db, user, conversation, history_msgs, user_message)
    return await _run_openai(db, user, conversation, history_msgs, user_message)


# ------------------------------------------------------------------- OpenAI
async def _run_openai(db, user, conversation, history_msgs, user_message):
    from openai import AsyncOpenAI

    api_key = settings.AI_API_KEY or os.environ.get("OPENAI_API_KEY", "")
    base_url = settings.OPENAI_BASE_URL or None
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    messages: list[dict] = [{"role": "system", "content": _build_system_prompt(db, user)}]
    for m in history_msgs:
        if m.role in ("user", "assistant") and m.content:
            messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": user_message})

    tool_trace: list[dict] = []

    for _ in range(4):  # max 4 tool-round trips
        resp = await client.chat.completions.create(
            model=conversation.model or "gpt-5.4",
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                result = execute_tool(tc.function.name, db, user, args)
                tool_trace.append({"name": tc.function.name, "arguments": args, "result": result})
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)}
                )
            continue
        # final answer
        return {"content": msg.content or "", "tool_calls": tool_trace}

    return {"content": "I reached my reasoning limit. Please rephrase.", "tool_calls": tool_trace}


# ------------------------------------------------------------------- Gemini
async def _run_gemini(db, user, conversation, history_msgs, user_message):
    """Gemini path - uses google-genai style function calling if available, else falls back to OpenAI."""
    try:
        from openai import AsyncOpenAI
    except Exception:
        return await _run_openai(db, user, conversation, history_msgs, user_message)

    api_key = settings.AI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=settings.GEMINI_BASE_URL or None,
    )

    messages: list[dict] = [{"role": "system", "content": _build_system_prompt(db, user)}]
    for m in history_msgs:
        if m.role in ("user", "assistant") and m.content:
            messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": user_message})

    tool_trace: list[dict] = []
    for _ in range(4):
        try:
            resp = await client.chat.completions.create(
                model=conversation.model or "gemini-3-flash-preview",
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
            )
        except Exception as exc:
            logger.exception("Gemini call failed, falling back to OpenAI: %s", exc)
            return await _run_openai(db, user, conversation, history_msgs, user_message)
        msg = resp.choices[0].message
        if msg.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                result = execute_tool(tc.function.name, db, user, args)
                tool_trace.append({"name": tc.function.name, "arguments": args, "result": result})
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)}
                )
            continue
        return {"content": msg.content or "", "tool_calls": tool_trace}
    return {"content": "I reached my reasoning limit.", "tool_calls": tool_trace}
