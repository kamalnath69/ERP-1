"""Approved semantic surface for Edvatiq data and analytics."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from app.ai.contracts import (
    PresentationFormat, PresentationRole, QueryGoal, SemanticQuery,
)


DATA_QUERY_GOALS = frozenset(QueryGoal) - {
    QueryGoal.ACTION, QueryGoal.GENERAL, QueryGoal.CLARIFY,
}


@dataclass(frozen=True)
class FieldDefinition:
    key: str
    label: str
    value_type: Literal["string", "number", "integer", "boolean", "date", "datetime", "object", "list"]
    domains: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    projectable: bool = True
    filterable: bool = False
    sortable: bool = False
    groupable: bool = False
    sensitive_permission: str | None = None
    analytics_allowed: bool = True
    description: str = ""
    aliases: tuple[str, ...] = ()
    display_format: PresentationFormat = "text"
    display_group: str = "Details"
    display_role: PresentationRole = "detail"
    display_priority: int = 100
    visibility: Literal["display", "internal"] = "display"


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    entity: str
    domains: tuple[str, ...]
    permissions: tuple[str, ...]
    description: str
    minimum_sample: int = 1
    aliases: tuple[str, ...] = ()
    display_format: PresentationFormat = "number"
    display_priority: int = 100


@dataclass(frozen=True)
class EntityDefinition:
    key: str
    label: str
    module: str
    permission: str
    domain: str | None
    fields: dict[str, FieldDefinition] = field(default_factory=dict)
    goals: frozenset[QueryGoal] = DATA_QUERY_GOALS
    aliases: tuple[str, ...] = ()


class CatalogError(ValueError):
    pass


class SemanticCatalog:
    """Registry of identifiers the compiler and executor may exchange."""

    def __init__(
        self,
        *,
        industry: str,
        entities: Iterable[EntityDefinition],
        metrics: Iterable[MetricDefinition],
        analyses: Iterable[str] = (),
        clarifications: Iterable[str] = (),
        qualitative_definitions: Iterable[str] = (),
    ):
        self.industry = industry
        self.entities = {item.key: item for item in entities}
        self.metrics = {item.key: item for item in metrics}
        self.analyses = frozenset(analyses)
        self.clarifications = frozenset(clarifications)
        self.qualitative_definitions = frozenset(qualitative_definitions)

    def entity(self, key: str) -> EntityDefinition:
        try:
            return self.entities[key]
        except KeyError as exc:
            raise CatalogError(f"Entity '{key}' is not registered") from exc

    def field(self, entity: str, key: str) -> FieldDefinition:
        definition = self.entity(entity)
        try:
            return definition.fields[key]
        except KeyError as exc:
            raise CatalogError(f"Field '{entity}.{key}' is not registered") from exc

    def metric(self, key: str) -> MetricDefinition:
        try:
            return self.metrics[key]
        except KeyError as exc:
            raise CatalogError(f"Metric '{key}' is not registered") from exc

    def validate(
        self,
        query: SemanticQuery,
        *,
        allow_clarification: bool = False,
    ) -> SemanticQuery:
        entity = self.entity(query.entity)
        if query.goal not in entity.goals and not (
            allow_clarification and query.goal == QueryGoal.CLARIFY
        ):
            raise CatalogError(f"Goal '{query.goal}' is not available for '{query.entity}'")
        if query.requested_analysis:
            approved_analyses = (
                self.clarifications
                if query.goal == QueryGoal.CLARIFY
                else self.analyses
            )
            if query.requested_analysis not in approved_analyses:
                raise CatalogError(f"Analysis '{query.requested_analysis}' is not registered")
        if (
            query.qualitative_definition
            and query.qualitative_definition not in self.qualitative_definitions
        ):
            raise CatalogError(
                f"Qualitative definition '{query.qualitative_definition}' is not registered"
            )
        for key in query.fields:
            if not self.field(query.entity, key).projectable:
                raise CatalogError(f"Field '{key}' cannot be projected")
        for item in query.filters:
            definition = self.field(query.entity, item.field)
            if not definition.filterable or not definition.analytics_allowed:
                raise CatalogError(f"Field '{item.field}' cannot be filtered")
        for item in query.sort:
            definition = self.field(query.entity, item.field)
            if not definition.sortable or not definition.analytics_allowed:
                raise CatalogError(f"Field '{item.field}' cannot be sorted")
        for key in query.group_by:
            definition = self.field(query.entity, key)
            if not definition.groupable or not definition.analytics_allowed:
                raise CatalogError(f"Field '{key}' cannot be grouped")
        for key in query.metrics:
            metric = self.metric(key)
            if metric.entity != query.entity:
                raise CatalogError(f"Metric '{key}' does not apply to '{query.entity}'")
        for reference in query.entities:
            if reference.kind not in self.entities:
                raise CatalogError(f"Entity reference '{reference.kind}' is not registered")
        return query

    def compiler_manifest(self) -> dict[str, Any]:
        """Expose descriptions only, never storage mappings or access decisions."""
        return {
            "industry": self.industry,
            "analyses": sorted(self.analyses),
            "clarifications": sorted(self.clarifications),
            "qualitative_definitions": sorted(self.qualitative_definitions),
            "entities": {
                entity.key: {
                    "description": entity.label,
                    "aliases": list(entity.aliases),
                    "goals": sorted(goal.value for goal in entity.goals),
                    "fields": {
                        item.key: {
                            "description": item.description or item.label,
                            "type": item.value_type,
                            "filterable": item.filterable,
                            "sortable": item.sortable,
                            "groupable": item.groupable,
                            "projectable": item.projectable,
                            "aliases": list(item.aliases),
                        }
                        for item in entity.fields.values()
                    },
                }
                for entity in self.entities.values()
            },
            "metrics": {
                metric.key: {
                    "description": metric.description,
                    "entity": metric.entity,
                    "aliases": list(metric.aliases),
                }
                for metric in self.metrics.values()
            },
        }


def _field(
    key: str,
    label: str,
    value_type: str = "string",
    *,
    domain: str | None = "students",
    permission: str | None = "college.students.view",
    projectable: bool = True,
    filterable: bool = True,
    sortable: bool = False,
    groupable: bool = False,
    sensitive: str | None = None,
    analytics: bool = True,
    description: str = "",
    aliases: tuple[str, ...] = (),
    display_format: PresentationFormat | None = None,
    display_group: str = "Details",
    display_role: PresentationRole | None = None,
    display_priority: int = 100,
    visibility: Literal["display", "internal"] | None = None,
) -> FieldDefinition:
    internal = key == "id" or key.endswith("_id") or not projectable
    resolved_visibility = visibility or ("internal" if internal else "display")
    resolved_format: PresentationFormat = display_format or (
        "currency_paise" if key.endswith("_paise") or key in {"highest_package", "average_package"}
        else "percent" if "percent" in key or key.endswith("_rate")
        else "datetime" if value_type == "datetime"
        else "date" if value_type == "date"
        else "boolean" if value_type == "boolean"
        else "collection" if value_type == "list"
        else "number" if value_type in {"number", "integer"}
        else "text"
    )
    resolved_role: PresentationRole = display_role or (
        "title" if key == "name"
        else "badge" if key == "status"
        else "collection" if value_type == "list"
        else "detail"
    )
    return FieldDefinition(
        key=key, label=label, value_type=value_type,
        domains=(domain,) if domain else (),
        permissions=(permission,) if permission else (),
        projectable=projectable, filterable=filterable, sortable=sortable,
        groupable=groupable, sensitive_permission=sensitive,
        analytics_allowed=analytics, description=description, aliases=aliases,
        display_format=resolved_format, display_group=display_group,
        display_role=resolved_role, display_priority=display_priority,
        visibility=resolved_visibility,
    )


def college_catalog() -> SemanticCatalog:
    student_fields = {
        item.key: item for item in [
            _field("id", "Student ID"),
            _field("name", "Student name", sortable=True, aliases=("student", "student name"), display_group="Identity", display_role="title", display_priority=0),
            _field("admission_number", "Admission number", aliases=("admission no",), display_group="Identity", display_role="subtitle", display_priority=10),
            _field("roll_number", "Roll number", aliases=("roll no",), display_group="Identity", display_priority=20),
            _field("status", "Student status", display_format="status", display_group="Identity", display_role="badge", display_priority=5),
            _field("semester", "Current semester", "integer", sortable=True, groupable=True, display_group="Enrollment", display_priority=20),
            _field("program", "Program", sortable=True, groupable=True, aliases=("degree",), display_format="relation", display_group="Enrollment", display_role="subtitle", display_priority=10),
            _field("department", "Department", sortable=True, groupable=True, aliases=("dept",), display_format="relation", display_group="Enrollment", display_priority=30),
            _field("cohort", "Class or cohort", sortable=True, groupable=True, aliases=("class", "batch"), display_format="relation", display_group="Enrollment", display_role="subtitle", display_priority=15),
            _field("section", "Section", groupable=True, display_group="Enrollment", display_priority=40),
            _field("graduation_year", "Graduation year", "integer", sortable=True, groupable=True, aliases=("class of", "year"), display_group="Enrollment", display_priority=50),
            _field("department_id", "Department identifier", projectable=False),
            _field("program_id", "Program identifier", projectable=False),
            _field("cohort_id", "Cohort identifier", projectable=False),
            _field("email", "Email", filterable=False, sensitive="college.students.contact.view", analytics=False, display_group="Contact", display_priority=10),
            _field("phone", "Phone", filterable=False, sensitive="college.students.contact.view", analytics=False, display_group="Contact", display_priority=20),
            _field("cgpa", "Current CGPA", "number", domain="assessments", permission="college.assessments.view", sortable=True, aliases=("gpa",), display_format="decimal", display_group="Academics", display_role="metric", display_priority=10),
            _field("sgpa", "Latest SGPA", "number", domain="assessments", permission="college.assessments.view", sortable=True, display_format="decimal", display_group="Academics", display_role="metric", display_priority=20),
            _field("active_backlogs", "Active backlogs", "integer", domain="assessments", permission="college.assessments.view", sortable=True, display_group="Academics", display_priority=30),
            _field("academic_history", "Semester-wise academic history", "list", domain="assessments", permission="college.assessments.view", filterable=False, analytics=False, display_group="Academics", display_role="collection", display_priority=80),
            _field("attendance_percent", "Current attendance", "number", domain="attendance", permission="college.attendance.view", sortable=True, aliases=("attendance",), display_format="percent", display_group="Attendance", display_role="metric", display_priority=10),
            _field("attendance_history", "Attendance history", "list", domain="attendance", permission="college.attendance.view", filterable=False, analytics=False, display_group="Attendance", display_role="collection", display_priority=80),
            _field("readiness_score", "Placement readiness", "number", domain="readiness", permission="college.readiness.view", sortable=True, display_format="decimal", display_group="Readiness", display_role="metric", display_priority=10),
            _field("readiness_band", "Readiness band", domain="readiness", permission="college.readiness.view", sortable=True, display_format="status", display_group="Readiness", display_role="badge", display_priority=20),
            _field("readiness_coverage", "Evidence coverage", "number", domain="readiness", permission="college.readiness.view", sortable=True, display_format="percent", display_group="Readiness", display_priority=30),
            _field("skills", "Technical skills", "list", domain="readiness", permission="college.readiness.view", aliases=("technical skills",), display_format="tags", display_group="Career evidence", display_role="collection", display_priority=10),
            _field("projects", "Projects", "list", domain="readiness", permission="college.readiness.view", filterable=False, display_group="Career evidence", display_role="collection", display_priority=20),
            _field("certifications", "Certifications", "list", domain="readiness", permission="college.readiness.view", filterable=False, display_group="Career evidence", display_role="collection", display_priority=30),
            _field("skill_count", "Skill count", "integer", domain="readiness", permission="college.readiness.view", sortable=True),
            _field("project_count", "Project count", "integer", domain="readiness", permission="college.readiness.view", sortable=True),
            _field("certification_count", "Certification count", "integer", domain="readiness", permission="college.readiness.view", sortable=True),
            _field("internship_count", "Internship participation count", "integer", domain="readiness", permission="college.readiness.view", sortable=True, aliases=("internship", "internships")),
            _field("training_count", "Placement-training participation count", "integer", domain="readiness", permission="college.readiness.view", sortable=True),
            _field("profile_complete", "Career-profile completion", "boolean", domain="readiness", permission="college.readiness.view", sortable=True),
            _field("coding_total", "Coding problems solved", "integer", domain="coding", permission="college.coding.view", sortable=True),
            _field("coding_languages", "Coding languages", "list", domain="coding", permission="college.coding.view", display_format="tags", display_group="Coding", display_role="collection"),
            _field("placement_status", "Placement status", domain="placements", permission="college.placements.view", sortable=True, aliases=("placed", "unplaced"), display_format="status", display_group="Placement", display_role="metric", display_priority=10),
            _field("eligible_company_count", "Eligible-company count", "integer", domain="placements", permission="college.placements.view", sortable=True),
            _field("match_percent", "Requirement match", "number", domain="placements", permission="college.placements.view", sortable=True, display_format="percent", display_group="Placement", display_role="metric"),
            _field("eligibility_coverage", "Eligibility coverage", "number", domain="placements", permission="college.placements.view", sortable=True, display_format="percent", display_group="Placement"),
            _field("offer_count", "Placement offer count", "integer", domain="placements", permission="college.placements.view", sortable=True),
            _field("highest_package", "Highest offered package", "integer", domain="placements", permission="college.placements.view", sortable=True, aliases=("package", "salary"), display_format="currency_paise", display_group="Placement", display_role="metric"),
            _field("opportunity_package_max", "Placement-opportunity maximum package", "integer", domain="placements", permission="college.placements.view", projectable=False),
            _field("offers", "Placement offer details", "list", domain="placements", permission="college.placements.view", filterable=False, analytics=False),
            _field("subject", "Subject", domain="assessments", permission="college.assessments.view", groupable=True),
            _field("subject_score", "Subject score percentage", "number", domain="assessments", permission="college.assessments.view", sortable=True),
            _field("improvement", "Change across recent comparable periods", "number", domain="assessments", permission="college.assessments.view", sortable=True),
        ]
    }
    student = EntityDefinition(
        key="student", label="College students", module="college",
        permission="college.students.view", domain="students", fields=student_fields,
        aliases=("student", "students", "learner", "learners"),
    )
    group_fields = {key: student_fields[key] for key in (
        "id", "name", "department", "program", "cohort", "section", "graduation_year",
    )}
    department = EntityDefinition(
        key="department", label="College departments", module="college",
        permission="college.academics.view", domain="academics", fields=group_fields,
        aliases=("department", "departments", "dept"),
    )
    cohort = EntityDefinition(
        key="cohort", label="Classes and cohorts", module="college",
        permission="college.academics.view", domain="academics", fields=group_fields,
        aliases=("class", "classes", "cohort", "batch", "section"),
    )
    company_fields = {
        item.key: item for item in [
            _field("id", "Company ID", domain="placements", permission="college.placements.view"),
            _field("name", "Company name", domain="placements", permission="college.placements.view", sortable=True),
            _field("selection_count", "Selections", "integer", domain="placements", permission="college.placements.view", sortable=True),
            _field("eligible_count", "Eligible students", "integer", domain="placements", permission="college.placements.view", sortable=True),
            _field("selection_rate", "Selection rate", "number", domain="placements", permission="college.placements.view", sortable=True),
            _field("average_package", "Average offered package", "number", domain="placements", permission="college.placements.view", sortable=True),
            _field("highest_package", "Highest offered package", "integer", domain="placements", permission="college.placements.view", sortable=True),
            _field("requirements", "Structured job requirements", "object", domain="placements", permission="college.placements.view", filterable=False),
            _field("student_department", "Selected student department", domain="students", permission="college.students.view", projectable=False),
            _field("student_cohort", "Selected student class or cohort", domain="students", permission="college.students.view", projectable=False),
            _field("student_section", "Selected student section", domain="students", permission="college.students.view", projectable=False),
        ]
    }
    company = EntityDefinition(
        key="company", label="Placement companies", module="college",
        permission="college.placements.view", domain="placements", fields=company_fields,
        aliases=("company", "companies", "employer", "recruiter"),
    )
    subject = EntityDefinition(
        key="subject", label="Courses and subject performance", module="college",
        permission="college.assessments.view", domain="assessments",
        fields={
            "id": _field("id", "Subject ID", domain="assessments", permission="college.assessments.view"),
            "name": _field("name", "Subject name", domain="assessments", permission="college.assessments.view", sortable=True, groupable=True),
            "average_score": _field("average_score", "Average score percentage", "number", domain="assessments", permission="college.assessments.view", sortable=True),
            "failure_rate": _field("failure_rate", "Failure rate", "number", domain="assessments", permission="college.assessments.view", sortable=True),
            "attendance_percent": _field("attendance_percent", "Subject attendance percentage", "number", domain="attendance", permission="college.attendance.view", sortable=True),
            "student_count": _field("student_count", "Student count", "integer", domain="assessments", permission="college.assessments.view", sortable=True),
            "department": student_fields["department"],
            "cohort": student_fields["cohort"],
        },
        aliases=("subject", "course", "paper"),
    )
    metrics = [
        MetricDefinition("student_count", "Student count", "student", ("students",), ("college.students.view",), "Number of authorized students."),
        MetricDefinition("average_cgpa", "Average CGPA", "student", ("students", "assessments"), ("college.students.view", "college.assessments.view"), "Mean latest published CGPA among students with evidence.", display_format="decimal", display_priority=10),
        MetricDefinition("average_attendance", "Average attendance", "student", ("students", "attendance"), ("college.students.view", "college.attendance.view"), "Mean latest overall attendance among students with evidence.", display_format="percent", display_priority=10),
        MetricDefinition("placement_rate", "Placement rate", "student", ("students", "placements"), ("college.students.view", "college.placements.view"), "Placed or joined students divided by the authorized participating population.", display_format="percent", display_priority=10),
        MetricDefinition("average_package", "Average package", "student", ("students", "placements"), ("college.students.view", "college.placements.view"), "Mean package across recorded offers.", display_format="currency_paise", display_priority=10),
        MetricDefinition("readiness_score", "Placement readiness", "student", ("students", "readiness"), ("college.students.view", "college.readiness.view"), "Score from the active reviewed readiness policy with minimum coverage applied.", display_format="decimal", display_priority=10),
        MetricDefinition("average_skill_count", "Average verified skill count", "student", ("students", "readiness"), ("college.students.view", "college.readiness.view"), "Mean number of verified skill evidence records; this is evidence breadth, not an invented skill-quality score."),
        MetricDefinition("certification_total", "Verified certification total", "student", ("students", "readiness"), ("college.students.view", "college.readiness.view"), "Total verified certification evidence records in the authorized population."),
        MetricDefinition("internship_participation_rate", "Internship participation rate", "student", ("students", "readiness"), ("college.students.view", "college.readiness.view"), "Share of authorized students with at least one verified internship record.", display_format="percent"),
        MetricDefinition("subject_average", "Subject average", "subject", ("assessments",), ("college.assessments.view",), "Average normalized published assessment score.", display_format="percent"),
        MetricDefinition("failure_rate", "Failure rate", "subject", ("assessments",), ("college.assessments.view",), "Share of published scores below the configured pass mark.", display_format="percent"),
        MetricDefinition("subject_attendance", "Subject attendance", "subject", ("attendance",), ("college.attendance.view",), "Mean latest subject attendance among authorized students with evidence.", display_format="percent"),
        MetricDefinition("company_selection_count", "Company selections", "company", ("placements",), ("college.placements.view",), "Students with selected, offered, or joined outcomes."),
        MetricDefinition("company_selection_rate", "Company selection rate", "company", ("placements",), ("college.placements.view",), "Selections divided by eligible applications with known outcomes.", display_format="percent"),
        MetricDefinition("company_average_package", "Company average package", "company", ("placements",), ("college.placements.view",), "Mean package across recorded offers.", display_format="currency_paise"),
    ]
    return SemanticCatalog(
        industry="college",
        entities=(student, department, cohort, company, subject),
        metrics=metrics,
        analyses={
            "eligibility_requirements", "selected_students_by_company",
            "company_population_match", "recruiting_companies", "company_performance",
            "subject_group_comparison", "student_subject_performance",
            "academic_weakness_definition_required", "aggregate_ascending",
            "attendance_academic_association", "subject_change", "attendance_drop",
            "consistent_attendance", "attendance_change", "academic_period_comparison",
            "academic_change", "readiness_change", "consistent_core_subject_weakness",
            "difficult_subject_improvement", "placement_success_associations",
            "descriptive_comparison", "offers_pending_joining", "multiple_offer_details",
            "drive_attendance_not_recorded", "rejection_reasons_not_structured",
            "placed_skill_frequency", "unselected_missing_required_skills",
            "high_package_definition_required", "group_eligibility_count",
            "group_eligibility_rate", "eligible_not_applied",
            "current_opportunity_eligibility", "structured_company_match",
            "explainable_readiness_not_prediction", "company_group_selection_rate",
        },
        clarifications={
            "ambiguous_best", "undefined_student_profile_thresholds",
            "high_package_threshold_required", "missing_company_referent",
            "missing_referent",
        },
        qualitative_definitions={"overall_good_student", "placement_support"},
    )


def business_catalog(industry: str) -> SemanticCatalog:
    client = EntityDefinition(
        key="client", label="Clients", module="clients", permission="clients.view", domain=None,
        aliases=("client", "customer", "member", "patient", "guest"),
        fields={item.key: item for item in [
            _field("id", "Client ID", domain=None, permission="clients.view"),
            _field("name", "Client name", domain=None, permission="clients.view", sortable=True, display_group="Identity", display_role="title", display_priority=0),
            _field("status", "Client status", domain=None, permission="clients.view", sortable=True, display_format="status", display_group="Identity", display_role="badge", display_priority=5),
            _field("email", "Email", domain=None, permission="clients.view", filterable=False, analytics=False, display_group="Contact", display_priority=10),
            _field("phone", "Phone", domain=None, permission="clients.view", filterable=False, analytics=False, display_group="Contact", display_priority=20),
            _field("client_number", "Client number", domain=None, permission="clients.view", display_group="Identity", display_role="subtitle", display_priority=10),
            _field("last_visit_at", "Last visit", "datetime", domain=None, permission="clients.view", sortable=True, display_group="Activity", display_priority=10),
        ]},
    )
    appointment = EntityDefinition(
        key="appointment", label="Appointments", module="appointments",
        permission="appointments.view", domain=None, aliases=("appointment", "booking", "visit"),
        fields={item.key: item for item in [
            _field("id", "Appointment ID", domain=None, permission="appointments.view"),
            _field("status", "Status", domain=None, permission="appointments.view", sortable=True, groupable=True, display_format="status", display_group="Appointment", display_role="badge", display_priority=5),
            _field("starts_at", "Start time", "datetime", domain=None, permission="appointments.view", sortable=True, display_group="Appointment", display_role="metric", display_priority=10),
            _field("client", "Client", domain=None, permission="appointments.view", sortable=True, display_group="Appointment", display_role="title", display_priority=0),
            _field("location", "Location", domain=None, permission="appointments.view", groupable=True, display_group="Appointment", display_role="subtitle", display_priority=20),
            _field("location_id", "Location identifier", domain=None, permission="appointments.view", projectable=False),
        ]},
    )
    sale = EntityDefinition(
        key="sale", label="Sales", module="sales", permission="sales.view", domain=None,
        aliases=("sale", "sales", "invoice", "revenue"),
        fields={item.key: item for item in [
            _field("id", "Invoice ID", domain=None, permission="sales.view"),
            _field("invoice_number", "Invoice number", domain=None, permission="sales.view", display_group="Invoice", display_role="title", display_priority=0),
            _field("status", "Invoice status", domain=None, permission="sales.view", groupable=True, display_format="status", display_group="Invoice", display_role="badge", display_priority=5),
            _field("total_paise", "Total", "integer", domain=None, permission="sales.view", sortable=True, display_format="currency_paise", display_group="Payment", display_role="metric", display_priority=10),
            _field("paid_paise", "Paid", "integer", domain=None, permission="sales.view", sortable=True, display_format="currency_paise", display_group="Payment", display_role="metric", display_priority=20),
            _field("issued_at", "Issued time", "datetime", domain=None, permission="sales.view", sortable=True, display_group="Invoice", display_priority=20),
            _field("location", "Location", domain=None, permission="sales.view", groupable=True, display_group="Invoice", display_role="subtitle", display_priority=30),
            _field("location_id", "Location identifier", domain=None, permission="sales.view", projectable=False),
        ]},
    )
    metrics = [
        MetricDefinition("client_count", "Client count", "client", (), ("clients.view",), "Number of authorized clients."),
        MetricDefinition("appointment_count", "Appointment count", "appointment", (), ("appointments.view",), "Number of authorized appointments."),
        MetricDefinition("revenue", "Revenue", "sale", (), ("sales.view",), "Sum of finalized authorized invoice totals.", display_format="currency_paise", display_priority=10),
    ]
    return SemanticCatalog(industry=industry, entities=(client, appointment, sale), metrics=metrics)


def catalog_for(industry: str) -> SemanticCatalog:
    return college_catalog() if industry == "college" else business_catalog(industry)
