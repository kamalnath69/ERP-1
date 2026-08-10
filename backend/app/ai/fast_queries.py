"""Zero-credit deterministic answers for common operational questions."""
import re

from fastapi.encoders import jsonable_encoder

from app.ai.contracts import compose_response
from app.ai.local_intent import normalize_language
from app.ai.personalization import AssistantPreferences, style_deterministic_summary
from app.ai.tools import tool_business_records, tool_business_summary


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value.casefold())).strip()


def deterministic_query_plan(
    message: str, location_id: str | None = None,
    context_state: dict | None = None,
) -> dict | None:
    text = _normalized(message)
    language = _language(message, text)
    scoped_follow_up = _scoped_client_follow_up(text, context_state)
    if scoped_follow_up:
        arguments = dict(scoped_follow_up)
        arguments["location_id"] = location_id or arguments.get("location_id")
        return {"tool": "business_records", "language": language, "arguments": arguments}
    padded = f" {text} "
    if len(text.split()) > 12 or any(term in padded for term in (
        " also ", " then ", " plus ", " as well as ", " along with ",
    )) or (" and " in padded and "products and services" not in text):
        return None
    asks_for_list = any(term in text for term in (
        "who are", "who all", "list", "show all", "yaar yaaru", "yaarelaam", "yar yar",
    ))
    asks_for_count = any(term in text for term in (
        "how many", "count", "number of", "evlo", "எத்தனை",
    ))
    purchase_terms = ("who bought", "who purchased", "purchase history", "enna vaang", "enalaam vaang", "enna vang")
    if any(term in text for term in purchase_terms):
        item_query = _purchase_item_query(text)
        return {"tool": "business_records", "language": language, "arguments": {
            "subject": "purchases", "query": item_query, "location_id": location_id, "days": 365,
        }}
    has_clients = bool(re.search(r"\b(?:client|clients|customer|customers)\b", text))
    has_students = bool(re.search(r"\b(?:student|students|learner|learners)\b", text))
    if has_students and (asks_for_list or asks_for_count):
        status = (
            "inactive" if "inactive" in text else
            "active" if "active" in text else
            "all" if "all" in text else "active"
        )
        return {"tool": "business_records", "language": language, "arguments": {
            "subject": "students", "location_id": location_id, "status": status,
        }}
    if has_clients and (asks_for_list or asks_for_count):
        status = (
            "inactive" if "inactive" in text else
            "active" if "active" in text else
            "all" if "all" in text else "active"
        )
        return {"tool": "business_records", "language": language, "arguments": {
            "subject": "clients", "location_id": location_id, "status": status,
        }}
    if any(term in text for term in ("team member", "employees", "staff")) and asks_for_list:
        return {"tool": "business_records", "language": language, "arguments": {
            "subject": "employees", "location_id": location_id,
        }}
    if any(term in text for term in ("catalog", "products", "services")) and asks_for_list:
        return {"tool": "business_records", "language": language, "arguments": {
            "subject": "catalog", "location_id": location_id,
        }}
    summary_terms = (
        "business summary", "business snapshot", "today summary", "today s summary",
        "what needs attention", "active client", "today revenue", "month revenue",
        "appointments today", "low stock", "team members",
    )
    if any(term in text for term in summary_terms):
        return {"tool": "business_summary", "language": language, "arguments": {"location_id": location_id}}
    return None


def _scoped_client_follow_up(text: str, context_state: dict | None) -> dict | None:
    if not any(term in text for term in (
        "who are they", "who are those", "show them", "list them",
        "yaaru yaaru", "yaar yaaru", "yaarelaam", "yar yar",
    )):
        return None
    last_read = (context_state or {}).get("last_read") or {}
    arguments = last_read.get("arguments") or {}
    if last_read.get("tool") != "business_records" or arguments.get("subject") not in {"clients", "students"}:
        return None
    return {
        key: value for key, value in arguments.items()
        if key in {"subject", "query", "location_id", "status", "created_within_days"}
    }


def _purchase_item_query(text: str) -> str | None:
    match = re.fullmatch(r"who\s+(?:has\s+)?(?:bought|purchased)\s+(.+)", text)
    if not match:
        return None
    reference = re.sub(r"^(?:the|a|an)\s+", "", match.group(1)).strip()
    if reference in {"what", "anything", "items", "products", "services"}:
        return None
    return reference or None


def execute_deterministic_query(
    db,
    user,
    conversation_id: str,
    plan: dict,
    preferences: AssistantPreferences | None = None,
) -> dict:
    name = plan["tool"]
    arguments = dict(plan["arguments"])
    if name == "business_summary":
        result = jsonable_encoder(tool_business_summary(db, user, **arguments))
        summary = _summary_text(result, plan.get("language", "en"))
    else:
        result = jsonable_encoder(tool_business_records(
            db, user, conversation_id=conversation_id, **arguments,
        ))
        summary = _records_text(arguments["subject"], result, plan.get("language", "en"))
    summary = style_deterministic_summary(summary, plan.get("language", "en"), preferences)
    trace = [{"name": name, "arguments": arguments, "result": result}]
    response = compose_response(summary, trace)
    return {
        "content": summary,
        "tool_calls": trace,
        "model": "database",
        "route": "business",
        "response": response.model_dump(mode="json"),
        "usage": {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "embedding_tokens": 0,
            "provider_requests": 0,
            "tool_calls": 1,
            "tool_latency_ms": 0,
            "latency_ms": 0,
        },
    }


def _language(message: str, normalized: str) -> str:
    return normalize_language(message)[1]


def _summary_text(result: dict, language: str) -> str:
    if result.get("access_denied"):
        return result.get("message", "You do not have access to this information.")
    if result.get("industry") == "college":
        students = result.get("active_students", result.get("active_clients", 0))
        if language == "tanglish":
            return f"Ippo {students} active students irukaanga; {result.get('employees', 0)} faculty and staff irukaanga."
        if language == "ta":
            return f"உங்களிடம் {students} செயலில் உள்ள மாணவர்களும், {result.get('employees', 0)} ஆசிரியர்கள் மற்றும் பணியாளர்களும் உள்ளனர்."
        return f"You have {students} active students and {result.get('employees', 0)} faculty and staff."
    if language == "tanglish":
        return (
            f"Ippo {result.get('active_clients', 0)} active clients irukaanga, "
            f"innaiku {result.get('appointments_today', 0)} appointments irukku, "
            f"{result.get('low_stock_items', 0)} items low stock-la irukku."
        )
    if language == "ta":
        return (
            f"தற்போது {result.get('active_clients', 0)} செயலில் உள்ள வாடிக்கையாளர்கள், "
            f"இன்று {result.get('appointments_today', 0)} முன்பதிவுகள், "
            f"{result.get('low_stock_items', 0)} குறைந்த இருப்பு பொருட்கள் உள்ளன."
        )
    return (
        f"You have {result.get('active_clients', 0)} active clients, "
        f"{result.get('appointments_today', 0)} appointments today, and "
        f"{result.get('low_stock_items', 0)} low-stock items."
    )


def _records_text(subject: str, result: dict, language: str) -> str:
    if result.get("access_denied"):
        return result.get("message", "You do not have access to this information.")
    count = int(result.get("count", 0))
    labels = {
        "clients": "clients",
        "students": "students",
        "employees": "team members",
        "catalog": "catalog items",
        "purchases": "purchases",
    }
    label = labels.get(subject, subject)
    if language == "tanglish":
        return f"{count} {label} kidaichirukku." if count else f"Matching {label} edhuvum kidaikkala."
    if language == "ta":
        tamil_label = {
            "clients": "வாடிக்கையாளர்கள்",
            "students": "மாணவர்கள்",
            "team members": "குழு உறுப்பினர்கள்",
            "catalog items": "பட்டியல் உருப்படிகள்",
            "purchases": "வாங்கல்கள்",
        }.get(label, label)
        return f"பொருந்தும் {tamil_label} {count} கிடைத்துள்ளன." if count else f"பொருந்தும் {tamil_label} எதுவும் கிடைக்கவில்லை."
    if count == 1:
        label = {"clients": "client", "students": "student", "team members": "team member", "catalog items": "catalog item", "purchases": "purchase"}.get(label, label.rstrip("s"))
    return f"I found {count} {label}." if count else f"No matching {label} were found."
