"""Natural-language compilation into the strict semantic query contract."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from app.ai.catalog import CatalogError, SemanticCatalog
from app.ai.contracts import (
    ConversationState, EntityRef, FilterOperator, PageContext, QueryFilter,
    QueryGoal, QuerySort, SemanticQuery, TimeWindow,
)
from app.ai.definitions import DEFAULT_DEFINITIONS
from app.ai.provider import ProviderResponse


@dataclass(frozen=True)
class CompileResult:
    query: SemanticQuery
    provider: ProviderResponse | None = None
    deterministic: bool = False


STRICT_SEMANTIC_QUERY_TOOL = {
    "type": "function",
    "name": "submit_semantic_query",
    "description": (
        "Submit one semantic query using only identifiers in the supplied catalog. "
        "Never create SQL, joins, formulas, permissions, or database identifiers."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "goal": {
                "type": "string",
                "enum": [item.value for item in QueryGoal if item != QueryGoal.ACTION],
            },
            "entity": {"type": "string"},
            "fields": {"type": "array", "items": {"type": "string"}},
            "metrics": {"type": "array", "items": {"type": "string"}},
            "filters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "field": {"type": "string"},
                        "operator": {"type": "string", "enum": [item.value for item in FilterOperator]},
                        "value": {
                            "anyOf": [
                                {"type": "string"}, {"type": "number"}, {"type": "integer"},
                                {"type": "boolean"},
                                {
                                    "type": "array",
                                    "items": {"anyOf": [
                                        {"type": "string"}, {"type": "number"},
                                        {"type": "integer"}, {"type": "boolean"},
                                    ]},
                                },
                                {"type": "null"},
                            ],
                        },
                    },
                    "required": ["field", "operator", "value"],
                },
            },
            "group_by": {"type": "array", "items": {"type": "string"}},
            "sort": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "field": {"type": "string"},
                        "direction": {"type": "string", "enum": ["asc", "desc"]},
                    },
                    "required": ["field", "direction"],
                },
            },
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "kind": {"type": "string"},
                        "id": {"type": ["string", "null"]},
                        "label": {"type": ["string", "null"]},
                    },
                    "required": ["kind", "id", "label"],
                },
            },
            "time_window": {
                "anyOf": [
                    {"type": "null"},
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "start": {"type": ["string", "null"]},
                            "end": {"type": ["string", "null"]},
                            "preset": {
                                "type": ["string", "null"],
                                "enum": [
                                    "current", "previous", "last_30_days", "last_90_days",
                                    "this_academic_year", "previous_academic_year", "all", None,
                                ],
                            },
                        },
                        "required": ["start", "end", "preset"],
                    },
                ],
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            "qualitative_definition": {"type": ["string", "null"]},
            "requested_analysis": {"type": ["string", "null"]},
        },
        "required": [
            "goal", "entity", "fields", "metrics", "filters", "group_by",
            "sort", "entities", "time_window", "limit",
            "qualitative_definition", "requested_analysis",
        ],
    },
}


def _semantic_query_tool(catalog: SemanticCatalog) -> dict[str, Any]:
    tool = deepcopy(STRICT_SEMANTIC_QUERY_TOOL)
    properties = tool["parameters"]["properties"]
    entity_keys = sorted(catalog.entities)
    field_keys = sorted({
        key for entity in catalog.entities.values() for key in entity.fields
    })
    metric_keys = sorted(catalog.metrics)
    properties["entity"]["enum"] = [*entity_keys, "assistant"]
    properties["fields"]["items"]["enum"] = field_keys
    properties["metrics"]["items"]["enum"] = metric_keys
    properties["filters"]["items"]["properties"]["field"]["enum"] = field_keys
    properties["group_by"]["items"]["enum"] = field_keys
    properties["sort"]["items"]["properties"]["field"]["enum"] = field_keys
    properties["entities"]["items"]["properties"]["kind"]["enum"] = entity_keys
    properties["qualitative_definition"]["enum"] = [
        *sorted(catalog.qualitative_definitions), None,
    ]
    properties["requested_analysis"]["enum"] = [
        *sorted(catalog.analyses),
        "ambiguous_best", "general_question", "missing_company_referent",
        "missing_referent", None,
    ]
    return tool


SYSTEM_PROMPT = """You compile requests for an RBAC-governed ERP assistant.
Use only catalog identifiers. Do not decide access, write SQL, create joins or formulas, or infer unavailable values.
Projection fields describe what to show. Filters, sorts, groups, and metrics describe analytical inputs.
Use entity references for explicitly named or deictic entities. Never carry a prior person into a new population query.
Use the student entity with group_by for class, cohort, program, or department population analytics.
Use general with entity assistant for safe questions that do not ask for organization-specific ERP data.
Use clarification when wording such as 'best' has no governed definition. Overall-good-student means placement readiness.
Return exactly one submit_semantic_query function call."""


FIELD_TERMS = {
    "cgpa": ("cgpa", "gpa", "academic performance", "academics"),
    "sgpa": ("sgpa", "semester-wise", "semester wise"),
    "active_backlogs": ("backlog", "arrear"),
    "attendance_percent": ("attendance",),
    "readiness_score": ("readiness", "placement ready", "overall good"),
    "readiness_band": ("need placement support", "needs placement support"),
    "skills": ("technical skill", "skills", "know python", "know java"),
    "projects": ("project", "portfolio"),
    "certifications": ("certification", "certificate"),
    "internship_count": ("internship",),
    "training_count": ("placement training", "training"),
    "profile_complete": ("profile complete", "completed their profile", "complete profile"),
    "coding_total": ("coding", "problems solved"),
    "placement_status": ("placed", "unplaced", "placement status"),
    "offer_count": ("offer", "multiple offers"),
    "highest_package": ("package", "lpa", "salary"),
    "eligible_company_count": ("eligible", "eligibility"),
}


def _contains_any(text: str, values: tuple[str, ...] | list[str]) -> bool:
    return any(value in text for value in values)


def _number(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return float(match.group(1)) if match else None


def _comparison_operator(value: str) -> FilterOperator:
    value = value.casefold()
    if value in {"above", "over", "more than", "greater than", "higher than", ">"}:
        return FilterOperator.GT
    if value in {"at least", "minimum", ">="}:
        return FilterOperator.GTE
    if value in {"below", "under", "less than", "lower than", "<"}:
        return FilterOperator.LT
    if value in {"at most", "maximum", "<="}:
        return FilterOperator.LTE
    return FilterOperator.EQ


def _extract_threshold(text: str, terms: tuple[str, ...]) -> tuple[FilterOperator, float] | None:
    joined = "|".join(re.escape(item) for item in terms)
    pattern = rf"(?:{joined})\s*(?:is\s*)?(above|over|more than|greater than|higher than|at least|below|under|less than|lower than|at most|[<>]=?)\s*(\d+(?:\.\d+)?)\s*%?"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return _comparison_operator(match.group(1)), float(match.group(2))


def _explicit_profile_name(message: str) -> str | None:
    patterns = (
        r"^\s*who\s+is\s+(.+?)\s*[?.!]*$",
        r"^\s*(?:tell|show|give)\s+me\s+(?:everything\s+)?about\s+(.+?)\s*[?.!]*$",
        r"^\s*(?:show\s+)?(?:the\s+)?(?:complete\s+)?profile\s+of\s+(.+?)\s*[?.!]*$",
    )
    for pattern in patterns:
        match = re.match(pattern, message, flags=re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            lowered = name.casefold()
            population_targets = (
                "overall good student", "best student", "top student", "good student",
                "students ", "student of 20", "class of 20", "department", "class",
            )
            if (
                lowered not in {
                    "this student", "the student", "this person", "him", "her",
                    "best", "the best",
                }
                and not any(value in lowered for value in population_targets)
            ):
                return name
    return None


def _context_entities(
    context: PageContext | None,
    state: ConversationState,
    count: int = 1,
    *,
    kinds: set[str] | None = None,
) -> list[EntityRef]:
    allowed = kinds or {"student", "client", "company"}
    ordered = [item.ref for item in state.referents if item.ref.kind in allowed]
    if context:
        if context.entity and context.entity.kind in allowed:
            ordered.append(context.entity)
        ordered.extend(item for item in context.selected_entities if item.kind in allowed)
    deduped = []
    seen = set()
    for item in reversed(ordered):
        key = (item.kind, item.id, item.label)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return list(reversed(deduped[:count]))


def _goal(text: str) -> QueryGoal:
    if _contains_any(text, ("relationship between", "correlation", "correlate")):
        return QueryGoal.CORRELATION
    if _contains_any(text, ("trend", "over time", "sudden drop", "consistently", "improved", "improvement", "previous semester", "last semester")):
        return QueryGoal.TREND
    if _contains_any(text, ("compare", "versus", " vs ", "between these", "between the two")):
        return QueryGoal.COMPARE
    if _contains_any(text, ("who has better", "who has higher", "which student has better", "which student has higher")):
        return QueryGoal.COMPARE
    if _contains_any(text, ("eligible", "eligibility")):
        return QueryGoal.ELIGIBILITY
    if _contains_any(text, ("best match", "match for", "similar to those hired")):
        return QueryGoal.MATCH
    if _contains_any(text, ("which class", "which department")):
        return QueryGoal.AGGREGATE
    if _contains_any(text, ("academically weak", "need additional academic support")):
        return QueryGoal.AGGREGATE
    if _contains_any(text, ("rank", "top ", "highest", "lowest", "weakest", "most improved", "strongest", "best performing", "best-performing")):
        return QueryGoal.RANK
    if _contains_any(text, ("average", "percentage", "rate", "how many", "number of", "which class", "which department")):
        return QueryGoal.AGGREGATE
    if _contains_any(text, ("analyze", "factors", "what is different", "reasons", "common among", "most commonly")):
        return QueryGoal.ANALYZE
    if _contains_any(text, ("who is ", "tell me about", "profile", "this student", "student's")):
        return QueryGoal.PROFILE
    return QueryGoal.LIST


def _college_deterministic(
    message: str,
    context: PageContext | None,
    state: ConversationState,
    definitions: dict,
) -> SemanticQuery | None:
    text = " ".join(message.casefold().split())
    if re.fullmatch(r"(?:hi|hello|hey|vanakkam|\u0bb5\u0ba3\u0b95\u0bcd\u0b95\u0bae\u0bcd|good (?:morning|afternoon|evening))[!. ]*", text):
        greeting = "greeting_tanglish" if "vanakkam" in text else "greeting_tamil" if "\u0bb5\u0ba3\u0b95\u0bcd\u0b95\u0bae\u0bcd" in text else "greeting"
        return SemanticQuery(goal=QueryGoal.GENERAL, entity="assistant", requested_analysis=greeting)
    if _contains_any(text, ("what can you do", "how can you help", "help me use")):
        return SemanticQuery(goal=QueryGoal.GENERAL, entity="assistant", requested_analysis="capabilities")
    if re.search(r"\bwho\s+is\s+(?:the\s+)?best\b", text) and "overall good" not in text:
        return SemanticQuery(goal=QueryGoal.CLARIFY, entity="student", requested_analysis="ambiguous_best")
    if "average cgpa" in text and "strong placement performance" in text:
        return SemanticQuery(
            goal=QueryGoal.CLARIFY, entity="student",
            requested_analysis="undefined_student_profile_thresholds",
        )
    if _contains_any(text, ("high-package companies", "high package companies")) and not re.search(
        r"\b\d+(?:\.\d+)?\s*lpa\b", text,
    ):
        return SemanticQuery(
            goal=QueryGoal.CLARIFY, entity="student",
            requested_analysis="high_package_threshold_required",
        )

    explicit_name = _explicit_profile_name(message)
    erp_terms = (
        "student", "cgpa", "sgpa", "attendance", "academic", "semester",
        "department", "class", "cohort", "certification", "technical skill",
        "project", "internship", "placement", "placed", "unplaced", "company",
        "companies", "eligib", "package", "offer", "subject", "mathematics",
        "data structures", "readiness", "training", "profile", "cse", "ece",
        "eee", "infosys", "tcs", "wipro", "accenture",
    )
    if not explicit_name and not _contains_any(text, erp_terms):
        return None
    goal = _goal(text)
    population_language = _contains_any(text, (
        "all students", "which students", "who are", "top ", "rank", "class",
        "department", "college", "overall good student", "students with",
    ))
    entities: list[EntityRef] = []
    if explicit_name:
        entities = [EntityRef(kind="student", label=explicit_name)]
        goal = QueryGoal.PROFILE
    elif _contains_any(text, ("this student", "this student's", "the student", "these two", "these students")):
        entities = _context_entities(
            context, state, 2 if "these" in text or "two" in text else 1,
            kinds={"student", "client"},
        )
        if not entities:
            return SemanticQuery(goal=QueryGoal.CLARIFY, entity="student", requested_analysis="missing_referent")
    elif goal == QueryGoal.COMPARE and _contains_any(text, ("their", "between", "higher", "better")):
        entities = _context_entities(context, state, 2, kinds={"student", "client"})
        if len([item for item in entities if item.kind == "student"]) < 2:
            return SemanticQuery(goal=QueryGoal.CLARIFY, entity="student", requested_analysis="missing_referent")
    elif not population_language and goal == QueryGoal.PROFILE:
        entities = _context_entities(context, state, 1, kinds={"student", "client"})

    singular_student_reference = _contains_any(text, (
        "this student", "this student's", "the student", "the student's",
    ))
    if singular_student_reference and len([
        item for item in entities if item.kind in {"student", "client"}
    ]) == 1 and goal in {QueryGoal.LIST, QueryGoal.RANK, QueryGoal.AGGREGATE}:
        goal = QueryGoal.PROFILE

    entity = "student"
    subject_language = _contains_any(text, (
        "which subjects", "which subject", "subject is", "mathematics performance",
        "data structures", "score in ", "core subjects", "difficult subjects",
    ))
    grouped_subject_population = _contains_any(text, (
        "which class", "between cse", "department", "classes",
    ))
    if subject_language:
        asks_for_students = _contains_any(text, (
            "which students", "find students", "show students", "students who",
        ))
        entity = "student" if asks_for_students or grouped_subject_population else (
            "subject" if goal in {QueryGoal.RANK, QueryGoal.AGGREGATE, QueryGoal.TREND} else "student"
        )
    if _contains_any(text, ("which companies", "which company", "compare companies", "compare infosys", "company offered", "companies are")):
        entity = "company"

    company_names = [
        name for name in ("Infosys", "TCS", "Wipro", "Accenture")
        if re.search(rf"\b{re.escape(name)}\b", message, flags=re.IGNORECASE)
    ]
    company_refs = [EntityRef(kind="company", label=name) for name in company_names]
    if not company_refs and "this company" in text:
        company_refs = _context_entities(context, state, 1, kinds={"company"})
        if not company_refs:
            return SemanticQuery(
                goal=QueryGoal.CLARIFY, entity="company",
                requested_analysis="missing_company_referent",
            )
    if entity == "company":
        entities = company_refs
    elif company_refs:
        entities.extend(company_refs)

    fields = ["id", "name"]
    if entity == "student":
        if goal == QueryGoal.PROFILE and not any(term in text for terms in FIELD_TERMS.values() for term in terms):
            fields += [
                "admission_number", "status", "semester", "program", "department", "cohort",
                "graduation_year", "cgpa", "attendance_percent", "readiness_score",
                "placement_status", "skills", "projects", "certifications",
            ]
        if goal == QueryGoal.PROFILE and _contains_any(text, ("complete profile", "everything about")):
            fields += [
                "admission_number", "roll_number", "status", "semester", "program",
                "department", "cohort", "section", "graduation_year", "email", "phone",
                "cgpa", "sgpa", "active_backlogs", "attendance_percent",
                "academic_history", "attendance_history",
                "readiness_score", "readiness_band", "readiness_coverage",
                "skills", "projects", "certifications", "internship_count",
                "training_count", "profile_complete", "coding_total", "coding_languages",
                "placement_status", "offer_count", "highest_package", "offers",
            ]
        for key, terms in FIELD_TERMS.items():
            if _contains_any(text, terms):
                fields.append(key)
        if _contains_any(text, ("department", "class", "cohort", "section", "year cse")):
            fields += ["department", "program", "cohort", "section", "graduation_year"]
        if _contains_any(text, ("academic performance", "overall performance")):
            fields += ["cgpa", "sgpa", "active_backlogs"]
        if "semester-wise" in text or "semester wise" in text:
            fields += ["cgpa", "sgpa", "academic_history"]
    elif entity == "company":
        fields += ["selection_count", "eligible_count", "selection_rate", "average_package", "highest_package"]
    else:
        if "attendance" in text:
            fields += ["attendance_percent", "student_count"]
        else:
            fields += ["average_score", "failure_rate", "student_count"]

    filters: list[QueryFilter] = []
    if entity == "student":
        for key, terms in (
            ("cgpa", ("cgpa", "gpa")),
            ("attendance_percent", ("attendance", "attendance percentage")),
            ("certification_count", ("certifications", "certification")),
            ("offer_count", ("offers", "offer")),
            ("highest_package", ("package", "lpa")),
        ):
            threshold = _extract_threshold(text, terms)
            if threshold:
                operator, value = threshold
                if key == "highest_package" and "lpa" in text:
                    value = int(value * 100_000 * 100)
                filters.append(QueryFilter(field=key, operator=operator, value=value))

        cgpa_range = re.search(
            r"\bcgpa\s+(?:is\s+)?between\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)\b",
            text,
        )
        if cgpa_range:
            lower, upper = sorted((float(cgpa_range.group(1)), float(cgpa_range.group(2))))
            filters = [item for item in filters if item.field != "cgpa"]
            filters.extend((
                QueryFilter(field="cgpa", operator=FilterOperator.GTE, value=lower),
                QueryFilter(field="cgpa", operator=FilterOperator.LTE, value=upper),
            ))

        trailing_attendance = re.search(
            r"\b(above|over|at least|below|under|at most)\s+(\d+(?:\.\d+)?)\s*%?\s+attendance\b",
            text,
        )
        if trailing_attendance and not any(item.field == "attendance_percent" for item in filters):
            filters.append(QueryFilter(
                field="attendance_percent",
                operator=_comparison_operator(trailing_attendance.group(1)),
                value=float(trailing_attendance.group(2)),
            ))
        lpa_threshold = re.search(
            r"\bpackages?\s+(?:of\s+)?(above|over|at least|more than)\s+(?:inr\s*)?(\d+(?:\.\d+)?)\s*lpa\b",
            text,
        )
        if lpa_threshold and not any(item.field == "highest_package" for item in filters):
            filters.append(QueryFilter(
                field=("opportunity_package_max" if goal == QueryGoal.ELIGIBILITY else "highest_package"),
                operator=_comparison_operator(lpa_threshold.group(1)),
                value=int(float(lpa_threshold.group(2)) * 100_000 * 100),
            ))
        if "multiple offers" in text and not any(item.field == "offer_count" for item in filters):
            filters.append(QueryFilter(
                field="offer_count", operator=FilterOperator.GT, value=1,
            ))

        year = re.search(r"\b(?:of|class of|graduating|graduation year)\s*(20\d{2})\b", text)
        if not year:
            year = re.search(r"\b(20\d{2})\b", text)
        if year:
            filters.append(QueryFilter(field="graduation_year", operator=FilterOperator.EQ, value=int(year.group(1))))
        if "3rd-year" in text or "third-year" in text or "3rd year" in text or "third year" in text:
            filters.append(QueryFilter(field="semester", operator=FilterOperator.IN, value=[5, 6]))
        department_matches = list(dict.fromkeys(
            value.upper() for value in re.findall(
                r"\b(cse|it|ece|eee|computer science|information technology)\b",
                text, flags=re.IGNORECASE,
            )
        ))
        dept = department_matches[0] if department_matches else None
        if department_matches:
            filters.append(QueryFilter(
                field="department",
                operator=FilterOperator.IN if len(department_matches) > 1 else FilterOperator.CONTAINS,
                value=department_matches if len(department_matches) > 1 else department_matches[0],
            ))
        section_matches = list(dict.fromkeys(
            value.upper() for value in re.findall(
                r"\b(?:cse|it|ece|eee)\s+([a-z])\b", text, flags=re.IGNORECASE,
            )
        ))
        section = section_matches[0] if section_matches else None
        if section_matches:
            filters.append(QueryFilter(
                field="section",
                operator=FilterOperator.IN if len(section_matches) > 1 else FilterOperator.EQ,
                value=section_matches if len(section_matches) > 1 else section_matches[0],
            ))
        use_page_population = _contains_any(text, (
            "this class", "this cohort", "this department", "this program",
            "these students", "students in this",
        ))
        if context and use_page_population and not explicit_name and not any((year, dept, section)):
            if context.department_id and not any(item.field == "department" for item in filters):
                filters.append(QueryFilter(field="department_id", operator=FilterOperator.EQ, value=context.department_id))
            if context.program_id and not any(item.field == "program" for item in filters):
                filters.append(QueryFilter(field="program_id", operator=FilterOperator.EQ, value=context.program_id))
            context_cohorts = list(context.cohort_ids)
            context_cohorts.extend(
                item.id for item in context.selected_entities
                if item.kind == "cohort" and item.id
            )
            if context_cohorts and not any(item.field in {"cohort", "section"} for item in filters):
                filters.append(QueryFilter(
                    field="cohort_id", operator=FilterOperator.IN,
                    value=list(dict.fromkeys(context_cohorts)),
                ))
            if context.graduation_year and not any(item.field == "graduation_year" for item in filters):
                filters.append(QueryFilter(
                    field="graduation_year", operator=FilterOperator.EQ,
                    value=context.graduation_year,
                ))
        if "unplaced" in text or "not placed" in text:
            filters.append(QueryFilter(field="placement_status", operator=FilterOperator.EQ, value="unplaced"))
        elif re.search(r"\bplaced\b", text):
            filters.append(QueryFilter(field="placement_status", operator=FilterOperator.EQ, value="placed"))
        if _contains_any(text, ("not completed their profile", "incomplete profile", "not completed the profile")):
            filters.append(QueryFilter(field="profile_complete", operator=FilterOperator.EQ, value=False))
        if _contains_any(text, ("completed an internship", "participated in any internships", "internship participation")):
            filters.append(QueryFilter(field="internship_count", operator=FilterOperator.GT, value=0))
        if _contains_any(text, ("not attended any placement training", "no placement training")):
            filters.append(QueryFilter(field="training_count", operator=FilterOperator.EQ, value=0))
        skills = [name for name in ("Python", "Java", "JavaScript", "C++", "SQL") if name.casefold() in text]
        if skills:
            filters.append(QueryFilter(field="skills", operator=FilterOperator.CONTAINS, value=skills))
        if "high cgpa" in text and not any(item.field == "cgpa" for item in filters):
            filters.append(QueryFilter(
                field="cgpa", operator=FilterOperator.GTE,
                value=float(definitions["high_cgpa"]),
            ))
        certification_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        certification_threshold = re.search(
            r"more than\s+(\d+|one|two|three|four|five)\s+certifications?", text,
        )
        if certification_threshold and not any(item.field == "certification_count" for item in filters):
            raw = certification_threshold.group(1)
            filters.append(QueryFilter(
                field="certification_count", operator=FilterOperator.GT,
                value=int(raw) if raw.isdigit() else certification_words[raw],
            ))
        subject_match = re.search(
            r"(?:in|subject)\s+(mathematics|maths|data structures|python)\b", text,
        )
        score_match = re.search(r"(?:scored?|score)\s*(?:is\s*)?(below|under|above|over)\s*(\d+(?:\.\d+)?)", text)
        if subject_match:
            filters.append(QueryFilter(
                field="subject", operator=FilterOperator.CONTAINS,
                value=subject_match.group(1),
            ))
        if score_match:
            filters.append(QueryFilter(
                field="subject_score", operator=_comparison_operator(score_match.group(1)),
                value=float(score_match.group(2)),
            ))
    elif entity == "subject":
        subject_match = re.search(r"\b(mathematics|maths|data structures|python)\b", text)
        if subject_match:
            filters.append(QueryFilter(
                field="name", operator=FilterOperator.CONTAINS,
                value=subject_match.group(1),
            ))
    elif entity == "company":
        department_matches = list(dict.fromkeys(
            value.upper() for value in re.findall(
                r"\b(cse|it|ece|eee|computer science|information technology)\b",
                text, flags=re.IGNORECASE,
            )
        ))
        if department_matches:
            filters.append(QueryFilter(
                field="student_department",
                operator=FilterOperator.IN if len(department_matches) > 1 else FilterOperator.CONTAINS,
                value=department_matches if len(department_matches) > 1 else department_matches[0],
            ))
        section_matches = list(dict.fromkeys(
            value.upper() for value in re.findall(
                r"\b(?:cse|it|ece|eee)\s+([a-z])\b", text, flags=re.IGNORECASE,
            )
        ))
        if section_matches:
            filters.append(QueryFilter(
                field="student_section",
                operator=FilterOperator.IN if len(section_matches) > 1 else FilterOperator.EQ,
                value=section_matches if len(section_matches) > 1 else section_matches[0],
            ))

    metrics: list[str] = []
    group_by: list[str] = []
    sort: list[QuerySort] = []
    definition = None
    requested_analysis = None
    limit_match = re.search(r"\btop\s+(\d{1,2})\b", text)
    limit = min(100, int(limit_match.group(1))) if limit_match else 25

    if "overall good student" in text:
        goal = QueryGoal.RANK
        fields += ["readiness_score", "readiness_band", "readiness_coverage"]
        sort = [QuerySort(field="readiness_score", direction="desc")]
        definition = "overall_good_student"
        limit = 10
    elif _contains_any(text, ("need placement support", "needs placement support")):
        goal = QueryGoal.LIST
        fields += ["readiness_score", "readiness_band", "readiness_coverage"]
        filters.append(QueryFilter(field="readiness_band", operator=FilterOperator.EQ, value="needs_support"))
        definition = "placement_support"
    elif goal == QueryGoal.RANK and entity == "student":
        ranking_field = "cgpa"
        if "attendance" in text:
            ranking_field = "attendance_percent"
        elif "certification" in text:
            ranking_field = "certification_count"
        elif "project" in text or "portfolio" in text:
            ranking_field = "project_count"
        elif "technical skill" in text:
            ranking_field = "skill_count"
        elif "readiness" in text or "eligible" in text:
            ranking_field = "readiness_score"
        elif "improved" in text or "improvement" in text:
            ranking_field = "improvement"
        if any(item.field in {"subject", "subject_score"} for item in filters):
            ranking_field = "subject_score"
        fields.append(ranking_field)
        sort = [QuerySort(field=ranking_field, direction="asc" if "lowest" in text else "desc")]

    if entity == "subject" and "attendance" in text:
        metrics = ["subject_attendance"]
        sort = [QuerySort(
            field="attendance_percent",
            direction="asc" if "lowest" in text else "desc",
        )]
    elif entity == "subject":
        subject_sort = "failure_rate" if "failure" in text else "average_score"
        sort = [QuerySort(
            field=subject_sort,
            direction="asc" if _contains_any(text, ("lowest", "weakest")) and subject_sort == "average_score" else "desc",
        )]
    if entity == "company":
        company_sort = "selection_count"
        if "selection rate" in text:
            company_sort = "selection_rate"
        elif "average package" in text:
            company_sort = "average_package"
        elif "highest package" in text or "offered the highest" in text:
            company_sort = "highest_package"
        sort = [QuerySort(
            field=company_sort,
            direction="asc" if "lowest" in text else "desc",
        )]
        requested_analysis = (
            "eligibility_requirements" if "eligibility criteria" in text
            else "selected_students_by_company" if "students selected by" in text
            else "company_population_match" if goal == QueryGoal.MATCH
            else "recruiting_companies" if _contains_any(text, ("recruited", "recruiting"))
            else "company_performance"
        )
    if entity == "student" and any(item.field == "subject" for item in filters):
        if _contains_any(text, ("class", "cse a", "cse b")):
            group_by.append("cohort")
        if "department" in text:
            group_by.append("department")
        requested_analysis = "subject_group_comparison" if group_by else "student_subject_performance"

    grouped_eligibility = entity == "student" and "eligib" in text and _contains_any(
        text, ("class", "section", "department", "cse a", "cse b"),
    )
    if grouped_eligibility:
        goal = QueryGoal.ELIGIBILITY
        if "department" in text or re.search(r"\b(cse|it|ece|eee)\b", text):
            group_by.append("department")
        if "class" in text or "section" in text or re.search(r"\b(?:cse|it|ece|eee)\s+[ab]\b", text):
            group_by.append("cohort")

    if goal in {QueryGoal.AGGREGATE, QueryGoal.COMPARE} and entity == "student":
        population_count = _contains_any(text, (
            "number of students", "more students", "most students",
            "highest number of students", "lowest number of students",
        ))
        overall_comparison = _contains_any(text, (
            "overall comparison", "overall performance comparison",
        ))
        if population_count:
            metrics.append("student_count")
        else:
            if "attendance" in text or overall_comparison:
                metrics.append("average_attendance")
            if _contains_any(text, ("cgpa", "academic", "performed", "performance")) or overall_comparison:
                metrics.append("average_cgpa")
            if "placement" in text or overall_comparison:
                metrics.append("placement_rate")
            if "package" in text:
                metrics.append("average_package")
            if _contains_any(text, ("technical skill", "skill profile")) or overall_comparison:
                metrics.append("average_skill_count")
            if "certification" in text or overall_comparison:
                metrics.append("certification_total")
            if "internship" in text or overall_comparison:
                metrics.append("internship_participation_rate")
        if not metrics:
            metrics.append("student_count")
        if "department" in text or re.search(r"\b(cse|it|ece|eee)\b", text):
            group_by.append("department")
        if "class" in text or "section" in text or re.search(r"\b(?:cse|it|ece|eee)\s+[ab]\b", text):
            group_by.append("cohort")
        if _contains_any(text, ("academically weak", "need additional academic support")):
            requested_analysis = "academic_weakness_definition_required"
        elif _contains_any(text, ("lowest", "weakest")):
            requested_analysis = "aggregate_ascending"

    if goal == QueryGoal.CORRELATION:
        metrics = ["average_attendance", "average_cgpa"]
        requested_analysis = "attendance_academic_association"
    if goal == QueryGoal.TREND:
        requested_analysis = (
            "subject_change" if entity == "subject"
            else "attendance_drop" if "attendance" in text and "sudden drop" in text
            else "consistent_attendance" if "attendance" in text and "consistently" in text
            else "attendance_change" if "attendance" in text
            else "academic_period_comparison" if _contains_any(text, (
                "this semester's results", "this semesters results", "previous semester",
                "last semester",
            ))
            else "academic_change" if _contains_any(text, ("academic", "result", "subject", "semester"))
            else "readiness_change"
        )
        if _contains_any(text, ("consistently weak in core subjects", "consistently weak across core subjects")):
            requested_analysis = "consistent_core_subject_weakness"
            fields += ["subject", "subject_score", "improvement"]
        elif _contains_any(text, ("improved the most in their difficult subjects", "improved most in difficult subjects")):
            requested_analysis = "difficult_subject_improvement"
            fields += ["subject", "subject_score", "improvement"]
        if entity == "student":
            if "department" in text or re.search(r"\b(cse|it|ece|eee)\b", text):
                group_by.append("department")
            if "class" in text or "section" in text or re.search(r"\b(?:cse|it|ece|eee)\s+[ab]\b", text):
                group_by.append("cohort")
    if goal == QueryGoal.ANALYZE:
        requested_analysis = "placement_success_associations" if "placement" in text else "descriptive_comparison"

    if entity == "student" and _contains_any(text, ("offer but have not joined", "offer but has not joined", "offer but not joined")):
        requested_analysis = "offers_pending_joining"
    elif entity == "student" and "multiple offers" in text:
        requested_analysis = "multiple_offer_details"
    elif entity == "student" and _contains_any(text, ("attended placement drives", "attended placement drive")):
        requested_analysis = "drive_attendance_not_recorded"
    if _contains_any(text, ("reasons students are rejected", "reasons students were rejected")):
        goal = QueryGoal.ANALYZE
        requested_analysis = "rejection_reasons_not_structured"
    elif _contains_any(text, ("technical skills are most common among students who get placed", "skills are most common among students who get placed")):
        goal = QueryGoal.ANALYZE
        requested_analysis = "placed_skill_frequency"
    elif _contains_any(text, ("skills are most commonly missing", "most commonly missing among students")):
        goal = QueryGoal.ANALYZE
        requested_analysis = "unselected_missing_required_skills"
    elif _contains_any(text, ("skills are common among students selected by high-paying companies", "skills are common among students selected by high paying companies")):
        goal = QueryGoal.ANALYZE
        requested_analysis = "high_package_definition_required"

    if goal == QueryGoal.ELIGIBILITY and entity == "student":
        fields += ["eligible_company_count", "placement_status"]
        requested_analysis = (
            (
                "group_eligibility_count"
                if grouped_eligibility and _contains_any(text, ("most students", "number of students"))
                else "group_eligibility_rate"
            ) if grouped_eligibility
            else "eligible_not_applied" if "not applied" in text
            else "current_opportunity_eligibility"
        )
        if _contains_any(text, ("not eligible for any", "not eligible for any current")):
            filters.append(QueryFilter(field="eligible_company_count", operator=FilterOperator.EQ, value=0))
        eligible_threshold = re.search(r"eligible for (?:at least|more than)\s+(\d+)", text)
        if eligible_threshold:
            filters.append(QueryFilter(field="eligible_company_count", operator=FilterOperator.GTE, value=int(eligible_threshold.group(1))))
    if goal == QueryGoal.MATCH and entity == "student":
        fields += ["match_percent", "eligibility_coverage", "skills", "cgpa", "placement_status"]
        requested_analysis = "structured_company_match"
    if _contains_any(text, ("most likely to succeed", "likely to succeed")):
        goal = QueryGoal.RANK
        fields += ["readiness_score", "readiness_band", "readiness_coverage"]
        sort = [QuerySort(field="readiness_score", direction="desc")]
        requested_analysis = "explainable_readiness_not_prediction"
    if (
        entity == "student" and company_refs
        and "success rate" in text and group_by
    ):
        requested_analysis = "company_group_selection_rate"

    query = SemanticQuery(
        goal=goal,
        entity=entity,
        fields=list(dict.fromkeys(fields)),
        metrics=list(dict.fromkeys(metrics)),
        filters=filters,
        group_by=list(dict.fromkeys(group_by)),
        sort=sort,
        entities=entities,
        limit=limit,
        qualitative_definition=definition,
        requested_analysis=requested_analysis,
    )
    return query


def deterministic_compile(
    message: str,
    catalog: SemanticCatalog,
    *,
    context: PageContext | None,
    state: ConversationState,
    definitions: dict | None = None,
) -> SemanticQuery | None:
    if catalog.industry == "college":
        return _college_deterministic(message, context, state, definitions or DEFAULT_DEFINITIONS)
    text = " ".join(message.casefold().split())
    if re.fullmatch(r"(?:hi|hello|hey|vanakkam|\u0bb5\u0ba3\u0b95\u0bcd\u0b95\u0bae\u0bcd|good (?:morning|afternoon|evening))[!. ]*", text):
        greeting = "greeting_tanglish" if "vanakkam" in text else "greeting_tamil" if "\u0bb5\u0ba3\u0b95\u0bcd\u0b95\u0bae\u0bcd" in text else "greeting"
        return SemanticQuery(goal=QueryGoal.GENERAL, entity="assistant", requested_analysis=greeting)
    explicit_name = _explicit_profile_name(message)
    if explicit_name:
        return SemanticQuery(
            goal=QueryGoal.PROFILE, entity="client",
            fields=["id", "name", "status", "client_number", "last_visit_at", "email", "phone"],
            entities=[EntityRef(kind="client", label=explicit_name)],
        )
    if re.search(r"\b(?:why|explain|reason|cause|contribute)\b", text):
        return None
    if "revenue" in text or "sales" in text or "collection" in text:
        filters = [QueryFilter(
            field="location_id", operator=FilterOperator.EQ,
            value=context.location_id,
        )] if context and context.location_id else []
        current = any(term in text for term in ("today", "innaiku", "current day"))
        return SemanticQuery(
            goal=QueryGoal.AGGREGATE, entity="sale",
            fields=["id", "invoice_number", "total_paise", "status"],
            metrics=["revenue"], filters=filters,
            time_window=TimeWindow(preset="current") if current else None,
        )
    if "appointment" in text or "booking" in text:
        return SemanticQuery(goal=QueryGoal.LIST, entity="appointment", fields=["id", "client", "starts_at", "status", "location"])
    if "client" in text or "customer" in text or "member" in text or "patient" in text:
        return SemanticQuery(goal=QueryGoal.LIST, entity="client", fields=["id", "name", "status", "client_number", "last_visit_at"])
    return None


def _function_arguments(response: ProviderResponse) -> dict[str, Any]:
    calls = []
    for item in response.output:
        payload = item.model_dump(mode="json", exclude_none=True) if hasattr(item, "model_dump") else item
        if isinstance(payload, dict) and payload.get("type") == "function_call" and payload.get("name") == "submit_semantic_query":
            calls.append(payload)
    if len(calls) != 1:
        raise ValueError("Compiler must return exactly one semantic query")
    arguments = calls[0].get("arguments")
    return json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})


async def compile_query(
    *,
    message: str,
    catalog: SemanticCatalog,
    context: PageContext | None,
    state: ConversationState,
    definitions: dict,
    provider,
    model: str,
) -> CompileResult:
    deterministic = deterministic_compile(
        message, catalog, context=context, state=state, definitions=definitions,
    )
    if deterministic is not None and deterministic.goal in {QueryGoal.GENERAL, QueryGoal.CLARIFY}:
        return CompileResult(query=deterministic, deterministic=True)
    if provider is None and deterministic is not None:
        if deterministic.goal not in {QueryGoal.GENERAL, QueryGoal.CLARIFY}:
            catalog.validate(deterministic)
        return CompileResult(query=deterministic, deterministic=True)
    if provider is None:
        return CompileResult(
            query=SemanticQuery(
                goal=QueryGoal.GENERAL, entity="assistant",
                requested_analysis="general_question",
            ),
            deterministic=True,
        )

    inputs = [{
        "role": "system",
        "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
    }, {
        "role": "user",
        "content": [{"type": "input_text", "text": json.dumps({
            "request": message,
            "catalog": catalog.compiler_manifest(),
            "page_context": context.model_dump(mode="json") if context else None,
            "referents": [item.model_dump(mode="json") for item in state.referents[-6:]],
            "governed_definitions": definitions,
            "deterministic_candidate": deterministic.model_dump(mode="json") if deterministic else None,
        }, ensure_ascii=True)}],
    }]
    response = await provider.respond(
        model=model,
        inputs=inputs,
        tools=[_semantic_query_tool(catalog)],
        tool_choice={"type": "function", "name": "submit_semantic_query"},
        parallel_tool_calls=False,
        max_output_tokens=900,
    )
    try:
        query = SemanticQuery.model_validate(_function_arguments(response))
        if query.goal not in {QueryGoal.GENERAL, QueryGoal.CLARIFY}:
            catalog.validate(query)
    except (ValueError, CatalogError) as exc:
        raise ValueError("The request could not be compiled into an approved semantic query") from exc
    return CompileResult(query=query, provider=response)
