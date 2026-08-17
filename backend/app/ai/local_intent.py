"""Conservative multilingual intent and entity compiler for live business reads."""
import re
import unicodedata
from datetime import datetime, time, timedelta, timezone
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.ai.local_contracts import (
    BusinessQueryV1, DateWindow, IntentMatch, QueryClarification, ResolvedEntity,
)
from app.models import Organization, User
from app.services.entity_resolution import resolve_entities


ENGINE_VERSION = "local-intent-v2"
LANGUAGE_CLASSIFIER_VERSION = "turn-language-v2"
LOCAL_THRESHOLD = 0.94
MAX_LOCAL_TOKENS = 16

SUBJECT_ALIASES = {
    "clients": {
        "client", "clients", "customer", "customers", "member", "members",
        "clientu", "customeru", "vaadikkaiyalar", "vaadikkaiyalargal",
        "வாடிக்கையாளர்", "வாடிக்கையாளர்கள்",
    },
    "employees": {"employee", "employees", "staff", "team", "team member", "trainer", "trainers", "stylist", "practitioner", "doctor", "ஊழியர்"},
    "catalog": {"product", "products", "service", "services", "item", "items", "catalog", "menu", "பொருள்", "சேவை"},
    "inventory": {"inventory", "stock", "stocks", "batch", "batches", "expiry", "இருப்பு"},
    "stock_movements": {"stock movement", "stock movements", "inventory history", "stock history"},
    "appointments": {"appointment", "appointments", "booking", "bookings", "walk in", "walk-ins", "schedule", "முன்பதிவு"},
    "invoices": {"invoice", "invoices", "bill", "bills", "receipt", "receipts", "sale", "sales"},
    "payments": {"payment", "payments", "collection", "collections", "upi", "cash", "card"},
    "purchases": {"purchase", "purchases", "bought", "purchased", "ordered", "buyer", "buyers", "வாங்க"},
    "tasks": {"task", "tasks", "work item", "reminder", "reminders", "follow up", "follow-up"},
    "memberships": {"membership", "memberships", "renewal", "renewals", "plan expiry", "உறுப்பினர்"},
    "checkins": {"check in", "check-ins", "checkin", "attendance", "visit", "visits", "வருகை"},
    "classes": {"class", "classes", "sessions"},
    "equipment": {"equipment", "machine", "machines", "maintenance", "asset", "assets"},
    "measurements": {"measurement", "measurements", "weight", "body fat", "bmi", "progress"},
    "goals": {"goal", "goals", "target", "targets"},
    "workouts": {"workout", "workouts", "exercise", "exercises", "training session"},
    "diets": {"diet", "diets", "meal plan", "nutrition"},
    "coaching": {"coaching", "coaching note", "trainer note"},
    "signals": {"attention", "risk", "risks", "signal", "signals", "follow-up due"},
    "commitments": {"commitment", "commitments", "promise", "promises"},
    "salon_profiles": {"preference", "preferences", "formula", "formulas", "sensitivity", "sensitivities", "preferred stylist"},
    "patients": {"patient", "patients", "abha"},
    "encounters": {"encounter", "encounters", "consultation", "consultations", "follow up visit"},
    "prescriptions": {"prescription", "prescriptions", "medicine order"},
    "lab_orders": {"lab", "lab order", "lab orders", "test order", "test orders", "pending test"},
    "communications": {"message", "messages", "whatsapp", "email delivery", "communication", "communications"},
    "notifications": {"notification", "notifications", "alerts"},
    "locations": {"location", "locations", "branch", "branches"},
}
SUBJECT_ALIASES["checkins"].add("check-in")
SUBJECT_ALIASES["checkins"].update({"occupancy", "currently inside"})
SUBJECT_ALIASES.update({
    "class_bookings": {"class booking", "class bookings", "class reservation", "class reservations"},
    "memories": {"client memory", "client memories", "relationship memory", "client preference"},
    "vitals": {"vital", "vitals", "blood pressure", "temperature", "spo2"},
    "allergies": {"allergy", "allergies"},
    "diagnoses": {"diagnosis", "diagnoses"},
    "lab_results": {"lab result", "lab results", "test result", "test results"},
    "dispenses": {"dispense", "dispenses", "pharmacy dispensing", "dispensing history"},
})

SUBJECT_DOMAIN = {
    **{key: "shared" for key in ["clients", "employees", "catalog", "inventory", "stock_movements", "appointments", "invoices", "payments", "purchases", "tasks", "communications", "notifications", "locations"]},
    **{key: "gym" for key in ["memberships", "checkins", "classes", "equipment", "measurements", "goals", "workouts", "diets", "coaching"]},
    "signals": "client_intelligence", "commitments": "client_intelligence", "salon_profiles": "salon",
    **{key: "clinic" for key in ["patients", "encounters", "prescriptions", "lab_orders"]},
}
SUBJECT_DOMAIN.update({
    "class_bookings": "gym", "memories": "client_intelligence", "vitals": "clinic",
    "allergies": "clinic", "diagnoses": "clinic", "lab_results": "clinic", "dispenses": "clinic",
})

ENTITY_KIND = {
    "clients": "client", "employees": "employee", "catalog": "catalog", "inventory": "catalog",
    "appointments": "client", "invoices": "invoice", "payments": "payment", "purchases": "catalog",
    "memberships": "client", "checkins": "client", "classes": "class", "equipment": "equipment",
    "measurements": "client", "goals": "client", "workouts": "client", "diets": "client",
    "coaching": "client", "signals": "client", "commitments": "client", "salon_profiles": "client",
    "patients": "patient", "encounters": "encounter", "prescriptions": "prescription", "lab_orders": "lab_order",
    "locations": "location",
}
ENTITY_KIND.update({
    "class_bookings": "client", "memories": "client", "vitals": "patient",
    "allergies": "patient", "diagnoses": "encounter", "lab_results": "lab_order",
    "dispenses": "prescription",
})

AI_ONLY_TERMS = {
    "why", "explain", "suggest", "recommend", "prediction", "predict", "forecast", "draft",
    "summarize document", "policy", "manual", "pdf", "what should", "how can i improve",
}
WRITE_PREFIXES = {
    "create", "add", "send", "book", "schedule", "assign", "cancel", "renew", "freeze", "resume",
    "adjust", "update", "change", "delete", "remove", "refund", "pay", "mark", "record", "sign",
}
TANGLISH_TOKENS = {
    "antha", "andha", "intha", "indha", "ena", "enna", "edhu", "ethu",
    "yaaru", "yaar", "evlo", "evalo", "irukku", "irukaanga", "irukanga",
    "vaanguna", "vanguna", "vaangirkaan", "vaangirkaru", "vangirkaan",
    "vangirkaru", "kadaisiya", "kadisiya", "ivar", "avar", "ivanga",
    "avanga", "innaiku", "nethu", "kaatu", "sollu", "venum", "venuma",
    "dhaan", "illa", "illai", "seri", "aama", "vanakkam",
    "vanakam", "nandri", "kidaichirukku", "irukken", "pesu",
}


def normalize_language(message: str) -> tuple[str, str]:
    normalized = unicodedata.normalize("NFKC", message).casefold()
    normalized = re.sub(r"[^\w@+.-]+", " ", normalized, flags=re.UNICODE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    explicit_english = bool(re.search(r"\b(?:reply|respond|speak|answer|continue)\s+(?:only\s+)?in\s+english\b", normalized))
    explicit_tanglish = bool(re.search(r"\b(?:tanglish|tamil\s+in\s+english|tamil\s+using\s+english)\b", normalized))
    explicit_tamil = bool(re.search(r"\b(?:reply|respond|speak|answer)\s+(?:only\s+)?in\s+tamil\b", normalized))
    if explicit_english:
        language = "en"
    elif explicit_tanglish:
        language = "tanglish"
    elif explicit_tamil or any("\u0b80" <= char <= "\u0bff" for char in message):
        language = "ta"
    else:
        tokens = normalized.split()
        signals = [token for token in tokens if _is_tanglish_token(token)]
        strong = {
            "antha", "andha", "intha", "indha", "yaaru", "evlo", "irukku", "irukaanga",
            "innaiku", "nethu", "venum", "venuma", "pesu", "sollu", "kaatu", "vanakkam",
        }
        language = "tanglish" if len(signals) >= 2 or (
            len(signals) == 1 and (signals[0] in strong or len(tokens) <= 4)
        ) else "en"
    return normalized, language


def _is_tanglish_token(token: str) -> bool:
    if token in TANGLISH_TOKENS:
        return True
    return bool(re.fullmatch(
        r"(?:a(?:th|dh)u+|i(?:th|dh)u+|yaa+r+u+|iru(?:k+u|ka+nga)|"
        r"vaa?ng\w*|kadai?si\w*|sollu\w*|kaatu\w*)",
        token,
    ))


def interpret_business_query(
    db: Session, user: User, message: str, location_id: str | None = None,
    context_state: dict | None = None,
) -> IntentMatch:
    text, language = normalize_language(message)
    if not text:
        return IntentMatch(outcome="fallback", confidence=0, reason="empty")
    if _requires_ai(text):
        return IntentMatch(outcome="fallback", confidence=1, reason="ai_required")

    org = db.get(Organization, user.organization_id)
    industry = getattr(org.industry, "value", org.industry) if org else None
    if industry == "college":
        return IntentMatch(
            outcome="fallback",
            confidence=1,
            reason="college_structure_requires_college_router",
        )
    date_range, comparison = parse_date_ranges(text, org.timezone if org else "Asia/Kolkata")
    previous = _previous_query(context_state)
    if previous and _is_follow_up(text) and _follow_up_matches_scope(previous, text):
        compiled = _compile_follow_up(
            previous, text, language, date_range, comparison, location_id,
            context_state or {},
        )
        if isinstance(compiled, QueryClarification):
            return IntentMatch(
                outcome="clarify", confidence=0.95, clarification=compiled,
            )
        if compiled:
            return IntentMatch(
                outcome="local", confidence=compiled.confidence, query=compiled,
            )
        return IntentMatch(
            outcome="fallback", confidence=0.5, reason="ambiguous_follow_up",
        )

    subject, subject_score = _subject(text)
    operation, operation_score = _operation(text, subject)
    if operation == "relationship":
        subject, subject_score = "clients", 0.98
    if (not subject or subject_score < LOCAL_THRESHOLD) and operation in {"detail", "reverse_lookup"}:
        subject, subject_score = "clients", 0.95
    if not subject or not operation:
        return IntentMatch(outcome="fallback", confidence=max(subject_score, operation_score), reason="unsupported")
    unsafe_reason = _unsafe_local_reason(
        text, subject, operation, subject_score, operation_score,
    )
    if unsafe_reason:
        return IntentMatch(
            outcome="fallback", confidence=min(subject_score, operation_score),
            reason=unsafe_reason,
        )
    if subject == "purchases" and operation not in {"buyers", "rank", "history", "find"}:
        return IntentMatch(outcome="fallback", confidence=min(subject_score, operation_score), reason="unsupported_purchase_query")

    if operation == "rank" and subject not in {"purchases", "catalog", "clients"}:
        return IntentMatch(outcome="fallback", confidence=min(subject_score, operation_score), reason="unsupported_ranking")
    if operation == "group" and subject in {
        "employees", "catalog", "patients", "measurements", "goals", "diets", "coaching",
        "salon_profiles", "prescriptions", "lab_orders", "class_bookings", "memories",
        "vitals", "allergies", "diagnoses", "lab_results",
    }:
        return IntentMatch(outcome="fallback", confidence=min(subject_score, operation_score), reason="unsupported_grouping")
    status = _status(text, subject)
    if operation == "attention" and subject == "signals":
        status = "open"
    metric = _metric(text, subject)
    if metric == "average":
        return IntentMatch(outcome="fallback", confidence=min(subject_score, operation_score), reason="unsupported_average")
    reference = _entity_reference(text, operation, subject)
    entities: list[ResolvedEntity] = []
    if reference:
        kinds = _resolution_kinds(subject, operation)
        resolution = resolve_entities(db, user, reference, kinds, 8)
        selected = _safe_selection(resolution, kinds[0] if len(kinds) == 1 else "person")
        if selected:
            subject = _subject_for_resolved_entity(subject, operation, selected["kind"])
            entities.append(_resolved(selected))
        elif resolution.get("items"):
            return IntentMatch(
                outcome="clarify", confidence=min(subject_score, operation_score),
                clarification=QueryClarification(
                    reason="ambiguous_entity",
                    message=_clarification_message(language),
                    candidates=resolution["items"],
                ),
            )
        elif operation in {"detail", "reverse_lookup", "relationship", "history", "status", "buyers"}:
            return IntentMatch(outcome="fallback", confidence=min(subject_score, operation_score), reason="entity_not_found")

    confidence = round(min(subject_score, operation_score), 3)
    if confidence < LOCAL_THRESHOLD:
        return IntentMatch(outcome="fallback", confidence=confidence, reason="low_confidence")
    min_amount, max_amount = _amount_filters(text)
    query = BusinessQueryV1(
        intent=f"{subject}.{operation}", domain=SUBJECT_DOMAIN[subject], operation=operation,
        subject=subject, metric=metric, language=language, query_text=reference if not entities else None,
        status=status, min_amount_paise=min_amount, max_amount_paise=max_amount,
        location_id=location_id, date_range=date_range, comparison_range=comparison,
        entities=entities, group_by="location" if operation == "group" else None,
        granularity="week" if "weekly" in text else "month" if "monthly" in text else "day",
        sort="value" if operation == "rank" else "latest_invoice" if subject == "purchases" and operation == "history" and any(term in text for term in ("last", "latest", "kadaisi", "kadisi")) else None,
        direction="asc" if any(term in text for term in ("lowest", "least sold", "smallest")) else "desc",
        confidence=confidence,
    )
    return IntentMatch(outcome="local", confidence=confidence, query=query)


def parse_date_ranges(text: str, timezone_name: str) -> tuple[DateWindow | None, DateWindow | None]:
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        try:
            zone = ZoneInfo("Asia/Kolkata")
        except Exception:
            zone = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
    now = datetime.now(timezone.utc).astimezone(zone)
    today = now.date()

    def window(start_date, end_date, label):
        start = datetime.combine(start_date, time.min, zone).astimezone(timezone.utc)
        end = datetime.combine(end_date, time.min, zone).astimezone(timezone.utc)
        return DateWindow(start=start, end=end, label=label)

    primary = comparison = None
    explicit = re.search(r"(\d{4})-(\d{2})-(\d{2})\s+(?:to|through|until)\s+(\d{4})-(\d{2})-(\d{2})", text)
    days = re.search(r"(?:last|past)\s+(\d{1,3})\s+days?", text)
    month_names = {name: index for index, name in enumerate((
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    ), 1)}
    named_month = next(((name, number) for name, number in month_names.items() if re.search(rf"\b{name}\b", text)), None)
    if explicit:
        try:
            start_date = datetime(*map(int, explicit.groups()[:3])).date()
            end_date = datetime(*map(int, explicit.groups()[3:])).date() + timedelta(days=1)
            if start_date >= end_date:
                return None, None
            primary = window(start_date, end_date, f"{start_date.isoformat()} to {(end_date - timedelta(days=1)).isoformat()}")
        except ValueError:
            return None, None
    elif days:
        count = min(max(int(days.group(1)), 1), 365)
        primary = window(today - timedelta(days=count - 1), today + timedelta(days=1), f"last {count} days")
    elif any(term in text for term in ("today", "innaiku", "இன்று")):
        primary = window(today, today + timedelta(days=1), "today")
    elif any(term in text for term in ("yesterday", "nethu", "நேற்று")):
        primary = window(today - timedelta(days=1), today, "yesterday")
    elif "last week" in text:
        start = today - timedelta(days=today.weekday() + 7)
        primary = window(start, start + timedelta(days=7), "last week")
    elif "this week" in text:
        start = today - timedelta(days=today.weekday())
        primary = window(start, start + timedelta(days=7), "this week")
    elif "last month" in text:
        first = today.replace(day=1)
        previous_end = first
        previous_start = (first - timedelta(days=1)).replace(day=1)
        primary = window(previous_start, previous_end, "last month")
    elif "this month" in text or "month revenue" in text:
        first = today.replace(day=1)
        next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        primary = window(first, next_month, "this month")
    elif "this year" in text:
        primary = window(today.replace(month=1, day=1), today.replace(year=today.year + 1, month=1, day=1), "this year")
    elif named_month:
        name, month = named_month
        year_match = re.search(rf"\b{name}\s+(20\d{{2}})\b", text)
        year = int(year_match.group(1)) if year_match else today.year
        start = today.replace(year=year, month=month, day=1)
        end = start.replace(year=year + 1, month=1) if month == 12 else start.replace(month=month + 1)
        primary = window(start, end, f"{name.title()} {year}")

    if any(term in text for term in ("compare", "versus", " vs ")):
        if primary and primary.label == "this month":
            end = primary.start.astimezone(zone).date()
            start = (end - timedelta(days=1)).replace(day=1)
            comparison = window(start, end, "last month")
        elif primary and primary.label == "this week":
            end = primary.start.astimezone(zone).date()
            comparison = window(end - timedelta(days=7), end, "last week")
        elif not primary:
            first = today.replace(day=1)
            next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
            primary = window(first, next_month, "this month")
            comparison = window((first - timedelta(days=1)).replace(day=1), first, "last month")
    return primary, comparison


def _requires_ai(text: str) -> bool:
    if any(term in text for term in AI_ONLY_TERMS):
        return True
    first = text.split()[0]
    return first in WRITE_PREFIXES


def _subject(text: str) -> tuple[str | None, float]:
    if any(term in text for term in ("revenue", "turnover", "collection amount", "sales amount")):
        return "payments", 0.99
    if any(_has_phrase(text, term) for term in (
        "partially paid", "partial payment", "invoice", "invoices", "bill",
        "bills", "receipt", "receipts", "sale", "sales",
    )):
        return "invoices", 0.99
    if any(term in text for term in (
        "who bought", "who purchased", "buyers", "bought by", "purchased by",
        "clients bought", "clients purchased", "vaanguna", "vanguna", "vaangirukaanga",
    )):
        return "purchases", 0.99
    if re.search(r"\b(?:vaang|vang)\w*\b", text):
        return "purchases", 0.98

    best = (None, 0.0)
    best_alias_length = 0
    for subject, aliases in SUBJECT_ALIASES.items():
        for alias in aliases:
            if _has_phrase(text, alias):
                score = 0.98
            elif len(text.split()) <= 5 and " " not in alias:
                similarity = max(
                    (SequenceMatcher(None, token, alias).ratio() for token in text.split()),
                    default=0,
                )
                score = 0.94 if similarity >= 0.96 else 0.0
            else:
                score = 0.0
            if score > best[1] or (score == best[1] and len(alias) > best_alias_length):
                best = (subject, score)
                best_alias_length = len(alias)
    return best


def _operation(text: str, subject: str | None) -> tuple[str | None, float]:
    purchase_word = bool(re.search(r"\b(?:buy|bought|purchase|purchased|vaang|vang)\w*\b", text))
    latest_word = any(term in text for term in ("last", "latest", "recent", "kadaisi", "kadisi"))
    if subject == "purchases" and purchase_word and latest_word:
        return "history", 0.99
    if any(phrase in text for phrase in (
        "who bought", "who purchased", "buyers of", "bought by", "purchased by",
        "clients bought", "clients purchased", "vaanguna", "vanguna", "vaangirukaanga",
    )):
        return "buyers", 0.99
    if re.search(r"(?:'s|s'|\bs\b)\s+(?:trainer|stylist|practitioner|coach)", text) or "assigned to whom" in text:
        return "relationship", 0.98
    if any(phrase in text for phrase in ("phone number is this", "email is this")):
        return "reverse_lookup", 0.98
    rules = [
        ("buyers", ("who bought", "who purchased", "buyers", "vaanguna", "vanguna", "யார் வாங்க")),
        ("reverse_lookup", ("whose phone", "whose email", "who owns", "number belongs")),
        ("compare", ("compare", "comparison", "versus", " vs ")),
        ("group", ("group by", "by location", "by branch", "location wise", "branch wise")),
        ("trend", ("trend", "over time", "daily", "weekly", "monthly pattern")),
        ("rank", ("top ", "most sold", "sold the most", "best selling", "highest", "lowest", "least sold")),
        ("attention", ("needs attention", "need attention", "follow up today", "follow-up today")),
        ("exceptions", ("partially paid", "partial payment", "overdue", "low stock", "out of stock", "expiring", "expired", "failed", "pending", "unpaid", "no show")),
        ("count", ("how many", "count", "number of", "evlo", "எத்தனை")),
        ("detail", ("tell me about", "details of", "detail of", "profile of", "information about")),
        ("history", ("history", "recent", "last visit", "previous", "past appointments")),
        ("status", ("status of", "is invoice", "is membership", "is payment")),
        ("aggregate", ("revenue", "total", "average", "collection", "sales amount", "turnover")),
        ("find", ("show", "list", "find", "which", "who are", "give me", "new ", "kaatu", "காட்டு")),
    ]
    for operation, phrases in rules:
        if any(_has_phrase(text, phrase) for phrase in phrases):
            return operation, 0.98
    if subject and _is_narrow_subject_read(text, subject):
        return "find", 0.96
    return None, 0.0


def _has_phrase(text: str, phrase: str) -> bool:
    if re.fullmatch(r"[\w-]+", phrase, flags=re.UNICODE):
        return bool(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, flags=re.UNICODE))
    return phrase in text


def _is_narrow_subject_read(text: str, subject: str) -> bool:
    value = re.sub(r"^(?:all|the|active|inactive|current|new)\s+", "", text).strip()
    if value in {"item", "product", "service", "sale", "invoice", "customer", "client"}:
        return False
    return any(value == alias for alias in SUBJECT_ALIASES.get(subject, set()))


def _matched_subjects(text: str) -> set[str]:
    return {
        subject
        for subject, aliases in SUBJECT_ALIASES.items()
        if any(_has_phrase(text, alias) for alias in aliases)
    }


def _unsafe_local_reason(
    text: str, subject: str, operation: str,
    subject_score: float, operation_score: float,
) -> str | None:
    tokens = text.split()
    if subject_score < LOCAL_THRESHOLD or operation_score < LOCAL_THRESHOLD:
        return "low_confidence"
    if len(tokens) > MAX_LOCAL_TOKENS:
        return "complex_query"

    subjects = _matched_subjects(text)
    allowed_combinations = (
        operation == "buyers" and subjects <= {"clients", "purchases", "catalog", "invoices"}
    ) or (
        operation == "rank" and subjects <= {"clients", "purchases", "catalog", "invoices"}
    ) or (
        operation == "group" and "locations" in subjects and len(subjects) == 2
    ) or subjects <= {"inventory", "stock_movements"}
    if len(subjects) > 1 and not allowed_combinations:
        return "multiple_subjects"

    has_count = any(_has_phrase(text, phrase) for phrase in (
        "how many", "count", "number of", "evlo", "எத்தனை",
    ))
    has_list = any(_has_phrase(text, phrase) for phrase in (
        "show", "list", "find", "who are", "give me", "kaatu", "காட்டு",
    ))
    compound_connector = any(_has_phrase(text, phrase) for phrase in (
        "also", "then", "plus", "as well as", "along with",
    )) or (" and " in f" {text} " and "between" not in text)
    if compound_connector and (len(subjects) > 1 or (has_count and has_list)):
        return "compound_query"
    return None


def _status(text: str, subject: str, default_clients: bool = True) -> str | None:
    aliases = {
        "partially_paid": ("partially paid", "partial payment", "part payment"),
        "inactive": ("inactive",), "active": ("active",), "overdue": ("overdue", "unpaid"),
        "pending": ("pending", "queued"), "failed": ("failed",), "completed": ("completed", "done"),
        "cancelled": ("cancelled", "canceled"), "expired": ("expired",), "expiring": ("expiring",),
        "paid": ("paid",), "frozen": ("frozen",), "open": ("open",),
        "scheduled": ("scheduled", "upcoming"), "booked": ("booked",),
        "current": ("current occupancy", "currently inside"),
        "low": ("low stock",), "out": ("out of stock",), "no_show": ("no show",),
    }
    for status, words in aliases.items():
        if any(word in text for word in words):
            if subject == "lab_orders" and status == "pending":
                return "ordered"
            return status
    return "active" if default_clients and subject == "clients" and "all" not in text else None


def _metric(text: str, subject: str) -> str | None:
    if any(term in text for term in ("revenue", "turnover", "collection", "sales amount")):
        return "revenue"
    if "average" in text:
        return "average"
    if subject == "checkins": return "checkins"
    if subject == "appointments": return "appointments"
    if subject == "memberships": return "memberships"
    if subject == "clients": return "clients"
    if subject == "purchases": return "top_products"
    return None


def _amount_filters(text: str) -> tuple[int | None, int | None]:
    def paise(value: str) -> int:
        return int(round(float(value.replace(",", "")) * 100))

    between = re.search(r"(?:between|from)\s+(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d{1,2})?)\s+(?:and|to)\s+(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d{1,2})?)", text)
    if between:
        first, second = paise(between.group(1)), paise(between.group(2))
        return min(first, second), max(first, second)
    single = re.search(r"(?:above|over|more than|at least|below|under|less than|at most)\s+(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d{1,2})?)", text)
    if not single:
        return None, None
    value = paise(single.group(1))
    return (value, None) if any(term in text for term in ("above", "over", "more than", "at least")) else (None, value)


def _entity_reference(text: str, operation: str, subject: str) -> str | None:
    patterns = {
        "buyers": r"(?:who (?:has )?(?:bought|purchased)|buyers of|clients? (?:who )?(?:bought|purchased))\s+(?:the\s+)?(.+)",
        "detail": r"(?:tell me about|details? of|profile of|information about)\s+(.+)",
        "reverse_lookup": r"(?:whose (?:phone(?: number)?|email) is|who owns|(?:phone number|email) is this)\s*[:=-]?\s*(.+)",
        "relationship": r"(?:who is\s+)?(.+?)(?:'s|s'|\bs\b)\s+(?:trainer|stylist|practitioner|coach)",
        "status": r"(?:status of|is)\s+(.+?)(?:\s+(?:paid|active|pending|cancelled|expired))?$",
    }
    pattern = patterns.get(operation)
    if pattern:
        match = re.search(pattern, text)
        if match:
            return _clean_reference(match.group(1))
    if operation == "history":
        if subject == "purchases":
            match = re.search(r"^(.+?)\s+(?:last|latest|recent|kadaisi\w*|kadisi\w*)\s+", text)
            if match:
                return _clean_reference(match.group(1))
        match = re.search(r"(?:show\s+)?(.+?)(?:'s|s')\s+(?:recent|appointment|visit|purchase|membership|check in|workout)", text)
        if match: return _clean_reference(match.group(1))
    return None


def _clean_reference(reference: str) -> str | None:
    value = re.sub(r"\b(today|yesterday|this week|last week|this month|last month|last \d+ days)\b", "", reference)
    value = re.sub(r"^(?:the|a|an)\s+", "", value).strip(" .?-")
    if value in {"what", "anything", "items", "products", "services", "all"}:
        return None
    return value or None


def _safe_selection(resolution: dict, kind: str) -> dict | None:
    if resolution.get("resolution") == "unique":
        return resolution.get("selected")
    items = resolution.get("items") or []
    if kind not in {"catalog", "inventory", "equipment", "class", "location", "lab_test"} or not items:
        return None
    first = items[0]
    second_score = items[1].get("confidence", 0) if len(items) > 1 else 0
    if first.get("confidence", 0) >= 88 and first.get("confidence", 0) - second_score >= 10:
        return first
    return None


def _resolution_kinds(subject: str, operation: str) -> list[str]:
    if operation == "reverse_lookup":
        return ["client", "employee", "patient"]
    if operation == "detail" and subject == "clients":
        return ["client", "employee", "catalog"]
    if subject == "purchases" and operation == "history":
        return ["client"]
    kind = ENTITY_KIND.get(subject)
    return [kind] if kind else []


def _subject_for_resolved_entity(subject: str, operation: str, kind: str) -> str:
    if operation not in {"detail", "reverse_lookup"}:
        return subject
    return {
        "client": "clients", "employee": "employees", "catalog": "catalog",
        "patient": "patients", "invoice": "invoices",
    }.get(kind, subject)


def _resolved(item: dict) -> ResolvedEntity:
    return ResolvedEntity(
        kind=item["kind"], id=item["id"], display_name=item["display_name"],
        confidence=float(item.get("confidence", 100)) / 100, profile_ref=item.get("profile_ref"),
    )


def _previous_query(context_state: dict | None) -> BusinessQueryV1 | None:
    state = context_state or {}
    raw = state.get("local_query")
    if raw:
        try:
            return BusinessQueryV1.model_validate(raw)
        except Exception:
            pass

    last_read = state.get("last_read") or {}
    if last_read.get("tool") != "business_records":
        return None
    spec = last_read.get("arguments") or {}
    subject = {"sales": "invoices"}.get(spec.get("subject"), spec.get("subject"))
    if subject not in SUBJECT_DOMAIN:
        return None
    status = spec.get("status")
    if status == "all":
        status = None
    if subject == "invoices" and status == "unpaid":
        status = "overdue"
    days = spec.get("days") or spec.get("created_within_days")
    date_range = None
    if days:
        end = datetime.now(timezone.utc)
        date_range = DateWindow(
            start=end - timedelta(days=max(1, min(int(days), 365))),
            end=end,
            label=f"last {days} days",
        )
    return BusinessQueryV1(
        intent=f"{subject}.find", domain=SUBJECT_DOMAIN[subject],
        operation="find", subject=subject, language="en",
        query_text=spec.get("query"), status=status,
        location_id=spec.get("location_id"), date_range=date_range,
        confidence=0.98,
    )


def _is_follow_up(text: str) -> bool:
    tokens = set(text.split())
    purchase_follow_up = bool(re.search(r"\b(?:buy|bought|purchase|purchased|vaang|vang)\w*\b", text)) and bool(
        tokens & {"he", "she", "his", "her", "they", "ivar", "avar", "ivanga", "avanga", "yes"}
    )
    deictic = bool(tokens & {
        "they", "them", "those", "that", "this", "athu", "adhu", "ithu",
        "idhu", "antha", "andha", "intha", "indha", "ivar", "avar",
        "ivanga", "avanga",
    }) or any(_is_deictic_token(token) for token in tokens)
    return (purchase_follow_up or deictic or any(term in text for term in (
        "only ", "what about", "last month", "last week", "this month", "this week",
        "group by", "by location", "by branch", "now show", "show them", "of them",
        "second one", "third one", "first one", "their membership", "his membership",
        "her membership", "last visit", "open his profile", "open her profile", "open their profile",
        "who are they", "who are them", "yaaru yaaru", "yaar yaaru", "yar yar",
        "ena item", "enna item", "what item", "which item",
    ))) and len(text.split()) <= 12


def _follow_up_matches_scope(previous: BusinessQueryV1, text: str) -> bool:
    if previous.subject in {"invoices", "purchases"} and _invoice_item_follow_up(text):
        return True
    if any(term in text for term in (
        "their membership", "his membership", "her membership", "last visit",
        "of them", "open his profile", "open her profile", "open their profile",
    )) or bool(re.search(r"\b(?:buy|bought|purchase|purchased|vaang|vang)\w*\b", text)):
        return True
    subjects = _matched_subjects(text)
    return not subjects or subjects == {previous.subject}


def _is_deictic_token(token: str) -> bool:
    return bool(re.fullmatch(r"(?:a(?:th|dh)u+|i(?:th|dh)u+)", token))


def _scoped_list_follow_up(text: str) -> bool:
    return any(term in text for term in (
        "who are they", "who are them", "who are those", "show them", "list them",
        "yaaru yaaru", "yaar yaaru", "yar yar", "yaarelaam", "yar ellam",
    ))


def _invoice_item_follow_up(text: str) -> bool:
    item_word = any(_has_phrase(text, term) for term in (
        "item", "items", "product", "products", "service", "services", "பொருள்",
    ))
    return item_word and (
        any(_has_phrase(text, term) for term in (
            "what", "which", "ena", "enna", "that", "this", "athu", "adhu",
            "ithu", "idhu", "antha", "andha", "intha", "indha",
        )) or any(_is_deictic_token(token) for token in text.split())
    )


def _singular_deictic(text: str) -> bool:
    return any(_has_phrase(text, term) for term in (
        "that", "this", "that one", "this one", "that sale", "this sale",
        "that invoice", "this invoice", "athu", "adhu", "ithu", "idhu",
        "antha", "andha", "intha", "indha",
    )) or any(_is_deictic_token(token) for token in text.split())


def _compile_follow_up(previous, text, language, date_range, comparison, location_id, context_state):
    data = previous.model_dump()
    data.update({"language": language, "confidence": 0.95})
    if date_range: data["date_range"] = date_range
    if comparison: data["comparison_range"] = comparison
    if location_id: data["location_id"] = location_id
    status = _status(text, previous.subject, default_clients=False)
    if status: data["status"] = status
    if "group by" in text or "by location" in text or "by branch" in text:
        data.update({"operation": "group", "group_by": "location", "intent": f"{previous.subject}.group"})
    result_entities = context_state.get("result_entities") or []
    if previous.subject in {"invoices", "purchases"} and _invoice_item_follow_up(text):
        if previous.subject == "invoices":
            primary = context_state.get("primary_entity") or {}
            invoices = [
                item for item in result_entities if item.get("kind") == "invoice"
            ]
            if not invoices and primary.get("kind") == "invoice":
                invoices = [primary]
            if len(invoices) > 1 and _singular_deictic(text):
                return QueryClarification(
                    reason="ambiguous_entity",
                    message=_clarification_message(language),
                    candidates=invoices,
                )
            if not invoices:
                return None
            entities = [_context_entity(item) for item in invoices]
        else:
            entities = data.get("entities") or []
        data.update({
            "subject": "purchases", "domain": "shared", "operation": "find",
            "intent": "purchases.find", "entities": entities, "metric": None,
            "query_text": None, "group_by": None, "status": None,
            "sort": None, "direction": "desc", "limit": 5,
            "date_range": None, "comparison_range": None,
        })
        return BusinessQueryV1.model_validate(data)
    ordinal = next((index for word, index in (("first", 0), ("second", 1), ("third", 2), ("fourth", 3), ("fifth", 4)) if word in text), None)
    if ordinal is not None and ordinal < len(result_entities):
        entity = result_entities[ordinal]
        subject = _subject_for_resolved_entity("clients", "detail", entity["kind"])
        data.update({"subject": subject, "domain": SUBJECT_DOMAIN[subject], "operation": "detail",
                     "intent": f"{subject}.detail", "entities": [_context_entity(entity)],
                     "status": None, "date_range": None, "comparison_range": None})
    elif any(term in text for term in ("their membership", "his membership", "her membership")):
        entity = _focused_entity(context_state)
        if entity:
            data.update({"subject": "memberships", "domain": "gym", "operation": "find",
                         "intent": "memberships.find", "entities": [_context_entity(entity)], "status": None})
    elif "last visit" in text:
        entity = _focused_entity(context_state)
        if entity:
            data.update({"subject": "checkins", "domain": "gym", "operation": "history",
                         "intent": "checkins.history", "entities": [_context_entity(entity)],
                         "status": None, "direction": "desc", "limit": 5})
    elif bool(re.search(r"\b(?:buy|bought|purchase|purchased|vaang|vang)\w*\b", text)):
        entity = _focused_entity(context_state)
        if entity and entity.get("kind") in {"client", "patient"}:
            data.update({"subject": "purchases", "domain": "shared", "operation": "history",
                         "intent": "purchases.history", "entities": [_context_entity(entity)],
                         "metric": None, "query_text": None, "group_by": None,
                         "status": None, "direction": "desc", "sort": "latest_invoice", "limit": 5,
                         "date_range": None, "comparison_range": None})
    elif "profile" in text:
        entity = _focused_entity(context_state)
        if entity:
            subject = _subject_for_resolved_entity("clients", "detail", entity["kind"])
            data.update({"subject": subject, "domain": SUBJECT_DOMAIN[subject], "operation": "detail",
                         "intent": f"{subject}.detail", "entities": [_context_entity(entity)],
                         "status": None, "date_range": None, "comparison_range": None})
    elif "of them" in text and any(term in text for term in ("invoice", "unpaid", "overdue")):
        entities = [_context_entity(item) for item in result_entities if item.get("kind") in {"client", "patient"}]
        data.update({"subject": "invoices", "domain": "shared", "operation": "exceptions" if any(term in text for term in ("unpaid", "overdue")) else "find",
                     "intent": "invoices.exceptions", "entities": entities,
                     "status": "overdue" if any(term in text for term in ("unpaid", "overdue")) else None})
    elif _scoped_list_follow_up(text):
        data.update({
            "operation": "find", "intent": f"{previous.subject}.find",
            "metric": None, "group_by": None,
            "sort": None, "direction": "desc", "limit": 5,
        })
    return BusinessQueryV1.model_validate(data)


def _focused_entity(context_state: dict, kinds: set[str] | None = None) -> dict | None:
    candidates = list(context_state.get("result_entities") or [])
    if context_state.get("primary_entity"):
        candidates.append(context_state["primary_entity"])
    return next(
        (item for item in candidates if not kinds or item.get("kind") in kinds),
        None,
    )


def _context_entity(item: dict) -> dict:
    profile = item.get("profile_ref") or {}
    kind = profile.get("kind") if profile.get("kind") == "client" else item["kind"]
    row_id = profile.get("id") if profile.get("kind") == "client" else item["id"]
    return {
        "kind": kind, "id": row_id,
        "display_name": item.get("display_name") or "Business record",
        "confidence": 1.0, "profile_ref": item.get("profile_ref"),
    }


def _clarification_message(language: str) -> str:
    if language == "tanglish": return "Orey maadhiri pala records irukku. Edhu nu select pannunga."
    if language == "ta": return "ஒரே மாதிரியான பல பதிவுகள் உள்ளன. சரியானதைத் தேர்ந்தெடுக்கவும்."
    return "I found more than one matching record. Choose the one you mean."
