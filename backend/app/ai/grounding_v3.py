"""Compact evidence construction and deterministic factual verification."""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.ai.v3_contracts import (
    EvidenceBundleV1,
    EvidenceFactV1,
    GroundedAnswerV2,
    GroundedClaimV2,
    VerificationOutcome,
)


_PRIVATE_KEYS = {
    "confirmation_token", "token", "secret", "password", "api_key", "object_key",
    "embedding", "embedding_vector", "search_vector", "raw", "payload",
}
_UI_KEYS = {"presentation", "columns", "series", "query_spec", "avatar_base64"}
_FACT_FIELDS = {
    "id", "name", "display_name", "display_meta", "status", "code", "number", "client_number",
    "admission_number", "roll_number", "invoice_number", "item_names", "item_count", "customer_name",
    "total", "count", "value", "label", "amount_paise", "total_paise", "paid_paise", "pending_paise",
    "price_paise", "quantity", "created_at", "updated_at", "starts_at", "ends_at", "starts_on", "ends_on",
    "date", "day", "readiness_band", "readiness_score", "coverage", "placement_status", "eligibility",
    "department", "program", "section", "graduation_year", "cgpa", "attendance_percentage",
    "phone", "email", "designation", "title", "description", "message",
    "program_name", "cohort_name", "current_semester", "sku", "item", "client", "type",
    "checked_in_at", "checked_out_at", "purchased_at", "method", "currency", "industry",
    "academic_year", "term", "course", "cohort", "company", "opportunity", "stage",
}
_STRUCTURED_FACT_FIELDS = {
    "factors", "factor_values", "source_records", "eligibility_reasons", "setup_gaps",
    "readiness", "academic_scope", "policy", "stock", "metrics",
}
_HIGH_RISK_MARKERS = {
    "prepare_action", "clinical", "patient", "prescription", "diagnosis", "eligibility",
    "opportunity_candidates", "invoice", "payment", "revenue", "fees", "clearance",
}
_STATUS_PHRASES = (
    "partially paid", "needs support", "needs review", "not participating",
    "ineligible", "eligible", "inactive", "active", "unpaid", "paid", "pending",
    "ready", "developing", "placed", "unplaced", "scheduled", "completed", "cancelled",
    "canceled", "refunded", "void", "draft", "issued", "failed", "expired", "cleared",
)
_COMPARISON_TERMS = {
    "more", "less", "higher", "lower", "highest", "lowest", "increased", "decreased",
    "grew", "dropped", "better", "worse", "compared",
}
_NON_ENTITY_TITLE_WORDS = {
    "The", "This", "That", "These", "Those", "Current", "Total", "Invoice", "Invoices",
    "Student", "Students", "Client", "Clients", "Employee", "Employees", "Business", "College",
    "Department", "Program", "Section", "Status", "Based", "According", "Found", "Result",
    "Results", "INR", "Edvatiq", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
    "There", "Here", "Only", "Today", "Yesterday", "Tomorrow", "Latest", "Verified",
    "Your", "Their", "Our", "They", "This", "One", "Two", "Three", "Four", "Five",
    "Revenue", "Amount", "Attendance", "Placement", "Created", "Updated", "Date",
    "Active", "Inactive", "Pending", "Paid", "Unpaid", "Eligible", "Ineligible", "Ready",
    "Ippo", "Naan", "Idhu", "Adhu", "Andha",
}


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): _json_value(item)
            for key, item in value.items()
            if str(key).casefold() not in _PRIVATE_KEYS and str(key) not in _UI_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _selected_fields(row: dict) -> dict:
    selected = {
        key: _json_value(value)
        for key, value in row.items()
        if key in _FACT_FIELDS and value not in (None, "", [], {})
    }
    for key, value in row.items():
        if len(selected) >= 28 or key in selected or key in _PRIVATE_KEYS or key in _UI_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) and value not in (None, ""):
            selected[key] = _json_value(value)
        elif key in _STRUCTURED_FACT_FIELDS and value not in (None, "", [], {}):
            selected[key] = _json_value(value)
    for key, value in list(selected.items()):
        if key.endswith("_paise") and isinstance(value, (int, float)):
            rupees = Decimal(str(value)) / Decimal(100)
            selected[f"{key[:-6]}_display"] = f"INR {rupees:,.2f}".rstrip("0").rstrip(".")
    return selected


def _fact_text(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))[:1600]


def evidence_from_trace(trace: list[dict]) -> EvidenceBundleV1:
    facts: list[EvidenceFactV1] = []
    warnings: list[str] = []
    missing: list[str] = []
    citations: list[dict] = []

    def add(source: str, value: dict, source_id: str | None = None, citation_index: int | None = None):
        if len(facts) >= 40:
            return
        selected = _selected_fields(value)
        if not selected:
            return
        facts.append(EvidenceFactV1(
            id=f"E{len(facts) + 1}", source=source, source_id=source_id,
            fact=_fact_text(selected), freshness="live" if source != "search_knowledge" else None,
            citation_index=citation_index,
        ))

    for call in trace:
        name = str(call.get("name") or "tool")
        result = call.get("result") or {}
        if not isinstance(result, dict):
            continue
        if result.get("access_denied"):
            warnings.append(str(result.get("message") or "Some requested evidence is outside the current access scope."))
            continue
        if result.get("error"):
            warnings.append(str(result["error"])[:400])
            continue
        if result.get("missing_evidence"):
            values = result["missing_evidence"]
            missing.extend(str(item)[:300] for item in (values if isinstance(values, list) else [values]))
        if result.get("warnings"):
            values = result["warnings"]
            warnings.extend(str(item)[:400] for item in (values if isinstance(values, list) else [values]))

        summary = {
            key: value for key, value in result.items()
            if key not in _PRIVATE_KEYS and key not in _UI_KEYS
            and not key.startswith("_") and key not in {"query", "embedding_cache_status", "insufficient_evidence"}
            and isinstance(value, (str, int, float, bool, datetime, date, Decimal))
        }
        if summary:
            add(name, summary, str(result.get("result_session_id") or "") or None)
        for collection in ("items", "rows", "metrics", "attention_items"):
            values = result.get(collection)
            if not isinstance(values, list):
                continue
            for row in values[:12]:
                if isinstance(row, dict):
                    add(name, row, str(row.get("id") or row.get("document_id") or "") or None)

        for citation in (result.get("citations") or [])[:12]:
            if not isinstance(citation, dict):
                continue
            safe = {
                key: _json_value(citation.get(key))
                for key in ("document_id", "document", "excerpt", "page", "section", "href")
                if citation.get(key) is not None
            }
            citations.append(safe)
            add(
                "search_knowledge",
                {"document": safe.get("document"), "excerpt": safe.get("excerpt"), "page": safe.get("page"), "section": safe.get("section")},
                str(safe.get("document_id") or "") or None,
                len(citations) - 1,
            )

    return EvidenceBundleV1(
        facts=facts,
        missing_evidence=list(dict.fromkeys(missing))[:12],
        warnings=list(dict.fromkeys(warnings))[:12],
        citations=citations[:12],
    )


def answer_from_text(content: str) -> GroundedAnswerV2:
    claims: list[GroundedClaimV2] = []
    used: list[str] = []
    # Providers conventionally place evidence marks after punctuation. Keep those
    # marks attached to the sentence before splitting so they cannot become an
    # orphan claim with no factual text.
    normalized = re.sub(
        r"([.!?])\s+(\[(?:E\d+(?:\s*,\s*E\d+)*)\])",
        r"\1\2",
        content.strip(),
    )
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", normalized):
        sentence = sentence.strip()
        if not sentence:
            continue
        evidence_ids = []
        for group in re.findall(r"\[((?:E\d+\s*,?\s*)+)\]", sentence):
            evidence_ids.extend(re.findall(r"E\d+", group))
        evidence_ids = list(dict.fromkeys(evidence_ids))
        used.extend(evidence_ids)
        claim_text = re.sub(r"\s*\[(?:E\d+(?:\s*,\s*E\d+)*)\]\s*$", "", sentence).strip()
        if claim_text:
            claims.append(GroundedClaimV2(text=claim_text, evidence_ids=evidence_ids))
    return GroundedAnswerV2(content=content.strip(), claims=claims, used_evidence_ids=list(dict.fromkeys(used)))


def _numbers(value: str) -> set[str]:
    result = set()
    for item in re.findall(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?", value):
        try:
            normalized = Decimal(item.replace(",", "")).normalize()
            result.add(format(normalized, "f"))
        except Exception:
            result.add(item.replace(",", ""))
    return result


def _evidence_numbers(values: Iterable[str]) -> set[str]:
    result: set[str] = set()

    def collect(value, key=""):
        if key == "id" or key.endswith("_id"):
            return
        if isinstance(value, dict):
            for child_key, child in value.items():
                collect(child, str(child_key))
        elif isinstance(value, list):
            for child in value:
                collect(child, key)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            result.update(_numbers(str(value)))
        elif isinstance(value, str):
            result.update(_numbers(value))

    for raw in values:
        try:
            collect(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            result.update(_numbers(raw))
    return result


def _status_terms(value: str) -> set[str]:
    normalized = re.sub(r"[_-]+", " ", value.casefold())
    found: set[str] = set()
    # Consume longer states first so "partially paid" cannot also authorize a
    # model claim that says the invoice is simply "paid".
    for phrase in sorted(_STATUS_PHRASES, key=len, reverse=True):
        pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
        if re.search(pattern, normalized):
            found.add(phrase)
            normalized = re.sub(pattern, " ", normalized)
    return found


def _identifier_tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b|\b[A-Z]{2,}\d+[A-Z0-9-]*\b", value)
        if token not in {"INR"}
    }


def _possible_entity_words(value: str) -> set[str]:
    return {
        token for token in re.findall(r"\b[A-Z][a-z]{2,}\b", value)
        if token not in _NON_ENTITY_TITLE_WORDS
    }


def _proper_names(value: str) -> set[str]:
    candidates = set(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", value))
    ignored = {
        "Based On", "According To", "Current Records", "Matching Records", "Indian Rupees",
        "I Found", "The Result", "No Records", "Business Snapshot",
    }
    return {candidate for candidate in candidates if candidate not in ignored}


def _requires_evidence(text: str) -> bool:
    factual_markers = (
        "₹", "INR", "%", "paid", "pending", "active", "inactive", "eligible", "ineligible",
        "ready", "placed", "invoice", "student", "client", "employee", "appointment", "sale",
        "cgpa", "attendance", "revenue", "total", "status",
    )
    return bool(_numbers(text) or _proper_names(text) or any(marker in text.casefold() for marker in factual_markers))


def is_high_risk(plan_domain: str, trace: list[dict]) -> bool:
    values = {plan_domain.casefold(), *(str(call.get("name") or "").casefold() for call in trace)}
    return any(marker in value for value in values for marker in _HIGH_RISK_MARKERS)


def verify_answer(answer: GroundedAnswerV2, evidence: EvidenceBundleV1, *, high_risk: bool) -> VerificationOutcome:
    by_id = {fact.id: fact.fact for fact in evidence.facts}
    invalid_ids: list[str] = []
    unsupported: list[str] = []
    for claim in answer.claims:
        invalid = [item for item in claim.evidence_ids if item not in by_id]
        invalid_ids.extend(invalid)
        if invalid:
            unsupported.append(claim.text)
            continue
        if not _requires_evidence(claim.text):
            continue
        if not claim.evidence_ids:
            unsupported.append(claim.text)
            continue
        cited_facts = [by_id[item] for item in claim.evidence_ids if item in by_id]
        cited = " ".join(cited_facts)
        if not _numbers(claim.text).issubset(_evidence_numbers(cited_facts)):
            unsupported.append(claim.text)
            continue
        if not _status_terms(claim.text).issubset(_status_terms(cited)):
            unsupported.append(claim.text)
            continue
        if not _identifier_tokens(claim.text).issubset(_identifier_tokens(cited)):
            unsupported.append(claim.text)
            continue
        cited_folded = cited.casefold()
        if any(name.casefold() not in cited_folded for name in _proper_names(claim.text)):
            unsupported.append(claim.text)
            continue
        if any(word.casefold() not in cited_folded for word in _possible_entity_words(claim.text)):
            unsupported.append(claim.text)
            continue
        claim_words = set(re.findall(r"[a-z]+", claim.text.casefold()))
        if claim_words & _COMPARISON_TERMS and len(_evidence_numbers(cited_facts)) < 2:
            unsupported.append(claim.text)
    status = "passed" if not unsupported and not invalid_ids else "deterministic_fallback"
    return VerificationOutcome(
        status=status,
        unsupported_claims=list(dict.fromkeys(unsupported))[:20],
        invalid_evidence_ids=list(dict.fromkeys(invalid_ids))[:20],
        high_risk=high_risk,
    )


def strip_internal_evidence_marks(content: str) -> str:
    return re.sub(r"\s*\[E\d+(?:\s*,\s*E\d+)*\]", "", content).strip()


def deterministic_evidence_summary(bundle: EvidenceBundleV1, trace: list[dict], language: str) -> str:
    errors = [*bundle.warnings, *bundle.missing_evidence]
    if not bundle.facts:
        if errors:
            return errors[0]
        if language == "tanglish":
            return "Reliable-a answer panna pothumana evidence kidaikkala. Konjam scope-a clear pannunga."
        if language == "ta":
            return "நம்பகமான பதிலுக்கு போதுமான ஆதாரம் கிடைக்கவில்லை. கேள்வியின் வரம்பை தெளிவுபடுத்துங்கள்."
        return "I could not find enough authorized evidence to answer reliably. Please narrow the request."

    first_result = next((call.get("result") for call in trace if isinstance(call.get("result"), dict)), {}) or {}
    count = first_result.get("count")
    items = first_result.get("items") if isinstance(first_result.get("items"), list) else []
    if isinstance(count, int):
        if language == "tanglish":
            return f"{count} matching records kidaichirukku. Details current records-la irukku."
        if language == "ta":
            return f"{count} பொருந்தும் பதிவுகள் கிடைத்துள்ளன. விவரங்கள் தற்போதைய பதிவுகளில் உள்ளன."
        return f"I found {count} matching records. The verified details are shown below."
    if items:
        if language == "tanglish":
            return "Verified records kidaichirukku; details keezha irukku."
        if language == "ta":
            return "சரிபார்க்கப்பட்ட பதிவுகள் கீழே காட்டப்பட்டுள்ளன."
        return "I found verified records. The current details are shown below."
    if bundle.citations:
        if language == "tanglish":
            return "Authorized documents-la relevant evidence kidaichirukku. Sources keezha irukku."
        if language == "ta":
            return "அங்கீகரிக்கப்பட்ட ஆவணங்களில் தொடர்புடைய ஆதாரம் கிடைத்துள்ளது."
        return "I found relevant evidence in the authorized documents. Review the cited sources below."
    if language == "tanglish":
        return "Current authorized data verify panniten; trusted details keezha irukku."
    if language == "ta":
        return "தற்போதைய அங்கீகரிக்கப்பட்ட தரவு சரிபார்க்கப்பட்டது; விவரங்கள் கீழே உள்ளன."
    return "I verified the current authorized data. The trusted details are shown below."
