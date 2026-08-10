"""Platform and organization defaults for the Edvatiq business product."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.config import settings
from app.models import (
    Employee, EmployeeLocation, FeatureFlag, IndustryEnum, Location, Organization,
    AIWallet, BillingProfile, FeatureDefinition, Job, Notification, Permission,
    PlanDefinition, PlanEntitlement, PlanVersion, PlatformPermission, PlatformRole,
    PlatformRolePermission, PlatformSetting, PlatformUserRole, RechargePack, Role,
    RolePermission, Subscription, User, UserRole,
)
from app.services.wallet import ensure_wallet


PERMISSIONS = [
    ("dashboard.view", "View business dashboard", "dashboard"),
    ("clients.view", "View clients", "clients"), ("clients.manage", "Manage clients", "clients"),
    ("clients.media.view", "View client media", "clients"), ("clients.media.manage", "Manage client media", "clients"),
    ("client_memory.view", "View client relationship memory", "client intelligence"), ("client_memory.manage", "Manage client relationship memory", "client intelligence"),
    ("client_signals.view", "View client pulse and attention queues", "client intelligence"), ("client_signals.manage", "Assign and resolve client signals", "client intelligence"),
    ("employees.view", "View employees", "employees"), ("employees.manage", "Manage employees", "employees"),
    ("employees.compensation.view", "View employee compensation", "employees"),
    ("catalog.view", "View products and services", "catalog"), ("catalog.manage", "Manage products and services", "catalog"),
    ("inventory.view", "View inventory", "inventory"), ("inventory.adjust", "Adjust inventory", "inventory"),
    ("appointments.view", "View appointments", "appointments"), ("appointments.manage", "Manage appointments", "appointments"),
    ("sales.view", "View sales", "sales"), ("sales.manage", "Create and edit sales", "sales"),
    ("payments.record", "Record payments", "sales"),
    ("reports.view", "View reports", "reports"),
    ("reports.exports", "Export reports", "reports"),
    ("gym.view", "View gym operations", "gym"), ("gym.manage", "Manage gym operations", "gym"),
    ("gym.dashboard.view", "View gym dashboard", "gym"),
    ("gym.memberships.view", "View memberships", "gym"), ("gym.memberships.manage", "Manage memberships", "gym"),
    ("gym.attendance.view", "View check-ins", "gym"), ("gym.attendance.mark", "Check members in and out", "gym"),
    ("gym.attendance.correct", "Correct check-in records", "gym"),
    ("gym.coaching.view", "View coaching records", "gym"), ("gym.coaching.manage", "Manage coaching records", "gym"),
    ("gym.measurements.view", "View fitness measurements", "gym"), ("gym.measurements.manage", "Manage fitness measurements", "gym"),
    ("gym.workouts.view", "View workout plans and sessions", "gym"), ("gym.workouts.manage", "Manage workout plans and sessions", "gym"),
    ("gym.diets.view", "View diet plans", "gym"), ("gym.diets.manage", "Manage diet plans", "gym"),
    ("gym.classes.view", "View gym classes", "gym"), ("gym.classes.manage", "Manage gym classes", "gym"),
    ("gym.equipment.view", "View gym equipment", "gym"), ("gym.equipment.manage", "Manage gym equipment", "gym"),
    ("salon.notes.view", "View salon preferences and formulas", "salon"), ("salon.notes.manage", "Manage salon preferences and formulas", "salon"),
    ("clinic.view", "View clinic operations", "clinic"), ("clinic.manage", "Manage clinic operations", "clinic"),
    ("clinical.view", "View clinical records", "clinic"), ("clinical.write", "Write clinical records", "clinic"),
    ("clinical.sign", "Sign clinical records", "clinic"), ("pharmacy.dispense", "Dispense medicines", "clinic"),
    ("college.view", "View college operations", "college"),
    ("college.academics.manage", "Manage academic structure and course offerings", "college"),
    ("college.students.view", "View student academic records", "college"),
    ("college.students.manage", "Admit and update students", "college"),
    ("college.attendance.view", "View academic attendance", "college"),
    ("college.attendance.mark", "Record academic attendance", "college"),
    ("college.assessments.view", "View assessments and results", "college"),
    ("college.assessments.manage", "Create assessments and record results", "college"),
    ("college.fees.view", "View student fees", "college"),
    ("college.fees.manage", "Assign fees and create fee invoices", "college"),
    ("college.readiness.view", "View placement readiness evidence", "college placement"),
    ("college.readiness.manage", "Configure and recompute placement readiness", "college placement"),
    ("college.coding.view", "View student coding progress", "college placement"),
    ("college.coding.manage", "Manage coding accounts and synchronization", "college placement"),
    ("college.placements.view", "View placement companies, drives, and applications", "college placement"),
    ("college.companies.manage", "Manage placement companies", "college placement"),
    ("college.opportunities.manage", "Manage placement drives and eligibility rules", "college placement"),
    ("college.applications.manage", "Manage placement applications and stages", "college placement"),
    ("college.offers.manage", "Manage interviews, offers, and outcomes", "college placement"),
    ("college.imports.manage", "Import College academic and placement data", "college placement"),
    ("college.integrations.manage", "Manage College ERP and coding integrations", "college placement"),
    ("college.placement_reports.view", "View College placement reports", "college placement"),
    ("documents.view", "View documents", "documents"), ("documents.manage", "Manage documents", "documents"),
    ("notifications.send", "Send client messages", "notifications"), ("ai.use", "Use Edvatiq AI", "ai"),
    ("ai.actions", "Use AI actions", "ai"), ("ai.views.share", "Share AI views with the team", "ai"),
    ("roles.manage", "Manage roles and access", "access"),
    ("users.view", "View users", "access"), ("users.manage", "Manage users", "access"),
    ("settings.view", "View business settings", "settings"),
    ("settings.manage", "Manage all business settings", "settings"),
    ("settings.identity.manage", "Manage business identity", "settings"),
    ("settings.locations.manage", "Manage business locations", "settings"),
    ("settings.tax.manage", "Manage tax and invoicing settings", "settings"),
    ("settings.operations.manage", "Manage industry operations", "settings"),
    ("settings.communication.manage", "Manage communication preferences", "settings"),
    ("settings.security.manage", "Manage organization security", "settings"),
    ("settings.privacy.manage", "Manage data and privacy settings", "settings"),
    ("settings.audit.view", "View settings history", "settings"),
    ("billing.view", "View billing", "billing"),
    ("billing.manage", "Manage billing", "billing"), ("audit.view", "View audit log", "audit"),
]

MANAGER_DENY = {"billing.manage", "roles.manage", "clinical.sign", "employees.compensation.view"}
STAFF_ALLOW = {
    "dashboard.view", "clients.view", "clients.manage", "catalog.view", "inventory.view",
    "appointments.view", "appointments.manage", "sales.view", "sales.manage", "payments.record",
    "gym.view", "gym.dashboard.view", "gym.memberships.view", "gym.attendance.view", "gym.attendance.mark",
    "clinic.view", "clinical.view", "clinical.write", "documents.view", "ai.use", "client_memory.view", "client_signals.view",
}
ACCOUNTANT_ALLOW = {
    "dashboard.view", "clients.view", "sales.view", "sales.manage", "payments.record",
    "reports.view", "reports.exports", "billing.view", "settings.view",
    "college.view", "college.students.view", "college.fees.view", "college.fees.manage",
}
INVENTORY_STAFF_ALLOW = {
    "dashboard.view", "catalog.view", "catalog.manage", "inventory.view", "inventory.adjust",
    "reports.view", "settings.view",
}

GYM_READ = {"gym.dashboard.view", "gym.memberships.view", "gym.attendance.view", "gym.coaching.view", "gym.measurements.view", "gym.workouts.view", "gym.diets.view", "gym.classes.view", "gym.equipment.view"}
GYM_WRITE = {"gym.memberships.manage", "gym.attendance.mark", "gym.attendance.correct", "gym.coaching.manage", "gym.measurements.manage", "gym.workouts.manage", "gym.diets.manage", "gym.classes.manage", "gym.equipment.manage"}

COLLEGE_ROLE_GRANTS = {
    "principal": {
        "dashboard.view", "clients.view", "employees.view", "college.view",
        "college.students.view", "college.attendance.view", "college.assessments.view",
        "college.readiness.view", "college.coding.view", "college.placements.view",
        "college.placement_reports.view", "documents.view", "reports.view", "ai.use",
    },
    "placement-head": {
        "dashboard.view", "clients.view", "clients.manage", "employees.view", "college.view",
        "college.students.view", "college.students.manage", "college.attendance.view",
        "college.assessments.view", "college.assessments.manage", "college.readiness.view",
        "college.readiness.manage", "college.coding.view", "college.coding.manage",
        "college.placements.view", "college.companies.manage", "college.opportunities.manage",
        "college.applications.manage", "college.offers.manage", "college.imports.manage",
        "college.integrations.manage", "college.placement_reports.view", "documents.view",
        "documents.manage", "reports.view", "reports.exports", "ai.use", "ai.actions",
    },
    "placement-coordinator": {
        "dashboard.view", "clients.view", "clients.manage", "college.view",
        "college.students.view", "college.students.manage", "college.attendance.view",
        "college.assessments.view", "college.readiness.view", "college.readiness.manage",
        "college.coding.view", "college.coding.manage", "college.placements.view",
        "college.companies.manage", "college.opportunities.manage",
        "college.applications.manage", "college.offers.manage", "college.imports.manage",
        "college.placement_reports.view", "documents.view", "documents.manage", "ai.use",
        "ai.actions",
    },
    "hod": {
        "dashboard.view", "clients.view", "employees.view", "college.view",
        "college.students.view", "college.attendance.view", "college.assessments.view",
        "college.assessments.manage", "college.readiness.view", "college.readiness.manage",
        "college.coding.view", "college.placements.view", "college.placement_reports.view",
        "documents.view", "ai.use",
    },
    "academic-admin": {
        "dashboard.view", "clients.view", "clients.manage", "employees.view",
        "college.view", "college.academics.manage", "college.students.view",
        "college.students.manage", "college.attendance.view", "college.attendance.mark",
        "college.assessments.view", "college.assessments.manage", "college.fees.view",
        "documents.view", "documents.manage", "reports.view", "ai.use", "ai.actions",
    },
    "faculty": {
        "dashboard.view", "clients.view", "employees.view", "college.view",
        "college.students.view", "college.attendance.view", "college.attendance.mark",
        "college.assessments.view", "college.assessments.manage", "documents.view", "ai.use",
    },
    "admissions": {
        "dashboard.view", "clients.view", "clients.manage", "college.view",
        "college.students.view", "college.students.manage", "college.fees.view",
        "documents.view", "documents.manage", "ai.use",
    },
}

FEATURES = [
    ("module.clients", "Clients", "Modules", "boolean"), ("module.employees", "Team", "Modules", "boolean"),
    ("module.catalog", "Catalog", "Modules", "boolean"), ("module.inventory", "Inventory", "Modules", "boolean"),
    ("module.sales", "Sales", "Modules", "boolean"), ("module.appointments", "Calendar", "Modules", "boolean"),
    ("module.gym", "Gym operations", "Industries", "boolean"), ("module.salon", "Salon operations", "Industries", "boolean"),
    ("module.clinic", "Clinic operations", "Industries", "boolean"), ("module.college", "College operations", "Industries", "boolean"),
    ("module.documents", "Documents", "Modules", "boolean"),
    ("module.reports", "Reports", "Modules", "boolean"), ("module.notifications", "Client communication", "Modules", "boolean"),
    ("module.ai", "Edvatiq AI", "Modules", "boolean"), ("ai.actions", "AI assisted actions", "AI", "boolean"),
    ("reports.exports", "Report exports", "Capabilities", "boolean"),
    ("documents.knowledge", "Document knowledge", "Capabilities", "boolean"),
    ("communications.send", "Direct client communication", "Capabilities", "boolean"),
    ("communications.automations", "Communication automation", "Capabilities", "boolean"),
    ("access.custom_roles", "Custom roles", "Capabilities", "boolean"),
    ("ai.views.share", "Shared AI views", "AI", "boolean"),
    ("limits.employees", "Team member limit", "Limits", "integer"), ("limits.clients", "Client limit", "Limits", "integer"),
    ("limits.locations", "Location limit", "Limits", "integer"), ("limits.storage_mb", "Storage allowance", "Limits", "integer"),
]

PLAN_SPECS = {
    "trial": {"name": "Trial", "monthly": 0, "annual": None, "employees": 5, "clients": 100, "locations": 1, "storage": 250, "ai": 100, "tier": "basic", "support": "self-service", "tax": False},
    "starter": {"name": "Starter", "monthly": 99900, "annual": 999000, "employees": 5, "clients": 500, "locations": 1, "storage": 1024, "ai": 500, "tier": "basic", "support": "standard", "tax": True},
    "growth": {"name": "Growth", "monthly": 249900, "annual": 2499000, "employees": 15, "clients": 2000, "locations": 3, "storage": 10240, "ai": 2500, "tier": "advanced", "support": "priority", "tax": True},
    "business": {"name": "Business", "monthly": 599900, "annual": 5999000, "employees": 50, "clients": 10000, "locations": 10, "storage": 51200, "ai": 10000, "tier": "actions", "support": "priority", "tax": True},
    "enterprise": {"name": "Enterprise", "monthly": None, "annual": None, "employees": None, "clients": None, "locations": None, "storage": None, "ai": 50000, "tier": "enterprise", "support": "dedicated", "tax": True},
}


def plan_entitlement_values(slug: str, spec: dict) -> dict:
    growth = slug in {"growth", "business", "enterprise"}
    business = slug in {"business", "enterprise"}
    values = {
        "limits.employees": spec["employees"], "limits.clients": spec["clients"],
        "limits.locations": spec["locations"], "limits.storage_mb": spec["storage"],
        "reports.exports": growth, "documents.knowledge": growth,
        "communications.send": growth, "access.custom_roles": growth,
        "communications.automations": business, "ai.actions": business,
        "ai.views.share": business,
    }
    for module in ("clients", "employees", "catalog", "inventory", "sales", "appointments", "documents", "reports", "notifications", "ai", "gym", "salon", "clinic", "college"):
        values[f"module.{module}"] = True
    return values

PLATFORM_PERMISSION_SPECS = [
    ("overview.view", "View platform overview", "Overview"),
    ("organizations.view", "View organizations", "Organizations"), ("organizations.manage", "Manage organizations", "Organizations"),
    ("organizations.delete", "Approve organization deletion", "Organizations"),
    ("plans.view", "View plans and features", "Plans"), ("plans.manage", "Edit plan drafts", "Plans"), ("plans.publish", "Publish plan versions", "Plans"),
    ("billing.view", "View platform billing", "Billing"), ("billing.manage", "Manage payments", "Billing"),
    ("billing.refund", "Request refunds and credits", "Billing"), ("billing.settlement", "Manage settlements", "Billing"),
    ("wallet.view", "View AI wallets", "AI Wallet"), ("wallet.manage", "Recharge AI wallets", "AI Wallet"),
    ("platform_team.view", "View platform team", "Platform Team"), ("platform_team.manage", "Manage platform team", "Platform Team"),
    ("support.start", "Start support sessions", "Support"), ("support.write", "Request temporary support changes", "Support"),
    ("operations.view", "View operations", "Operations"), ("operations.manage", "Retry operational work", "Operations"),
    ("audit.view", "View platform audit", "Audit"), ("settings.manage", "Manage platform settings", "Settings"),
    ("approvals.decide", "Approve controlled actions", "Approvals"),
]

PLATFORM_ROLE_GRANTS = {
    "platform-owner": "*",
    "operations": {"overview.view", "organizations.view", "organizations.manage", "plans.view", "support.start", "support.write", "operations.view", "operations.manage", "audit.view", "approvals.decide"},
    "support": {"overview.view", "organizations.view", "plans.view", "support.start", "support.write", "operations.view", "audit.view"},
    "finance": {"overview.view", "organizations.view", "plans.view", "billing.view", "billing.manage", "billing.refund", "billing.settlement", "wallet.view", "wallet.manage", "audit.view", "approvals.decide"},
    "read-only": {"overview.view", "organizations.view", "plans.view", "billing.view", "wallet.view", "platform_team.view", "operations.view", "audit.view"},
}


def ensure_permissions(db: Session) -> list[Permission]:
    values = [
        {"code": code, "label": label, "module": module, "organization_id": None}
        for code, label, module in PERMISSIONS
    ]
    db.execute(
        pg_insert(Permission)
        .values(values)
        .on_conflict_do_update(
            index_elements=[Permission.code],
            set_={"label": pg_insert(Permission).excluded.label, "module": pg_insert(Permission).excluded.module},
        )
    )
    return list(db.execute(select(Permission).where(Permission.code.in_([row["code"] for row in values]))).scalars())


def sync_granular_role_permissions(db: Session, permissions: list[Permission]) -> None:
    """Backfill new capabilities for roles created before granular client permissions existed."""
    by_code = {item.code: item for item in permissions}
    role_rows = db.execute(select(Role)).scalars().all()
    existing = {
        (role_id, permission_id)
        for role_id, permission_id in db.execute(
            select(RolePermission.role_id, RolePermission.permission_id)
        )
    }
    for role in role_rows:
        codes = set(db.execute(select(Permission.code).join(RolePermission, RolePermission.permission_id == Permission.id).where(RolePermission.role_id == role.id)).scalars())
        grants = set()
        if "gym.view" in codes: grants |= GYM_READ
        if "gym.manage" in codes: grants |= GYM_READ | GYM_WRITE
        if "clients.view" in codes: grants |= {"client_memory.view", "client_signals.view"}
        if "clients.manage" in codes: grants |= {"client_memory.manage", "clients.media.view", "clients.media.manage"}
        if role.slug in {"owner", "manager"}: grants |= {"client_signals.manage", "clients.media.view", "salon.notes.view", "salon.notes.manage", "ai.views.share", "settings.view"}
        if role.slug in COLLEGE_ROLE_GRANTS: grants |= COLLEGE_ROLE_GRANTS[role.slug]
        # The owner role is authoritative and must inherit capabilities introduced
        # after an organization was created. Entitlements still gate paid modules.
        if role.slug == "owner": grants |= set(by_code)
        if role.slug == "manager": grants |= {
            "settings.identity.manage", "settings.locations.manage", "settings.operations.manage",
            "settings.communication.manage",
        }
        for code in grants:
            permission = by_code.get(code)
            if permission and (role.id, permission.id) not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))
                existing.add((role.id, permission.id))


def seed_organization_defaults(db: Session, org: Organization, owner: User, primary_location: Location) -> None:
    permissions = ensure_permissions(db)
    by_code = {p.code: p for p in permissions}
    role_specs = {
        "owner": set(by_code),
        "manager": set(by_code) - MANAGER_DENY,
        "accountant": ACCOUNTANT_ALLOW,
        "inventory-staff": INVENTORY_STAFF_ALLOW,
        "staff": STAFF_ALLOW,
    }
    roles = {}
    for slug, codes in role_specs.items():
        role = Role(
            organization_id=org.id, name=slug.title(), slug=slug,
            description=f"Default {slug} access", is_system=True,
        )
        db.add(role)
        db.flush()
        roles[slug] = role
        for code in codes:
            db.add(RolePermission(role_id=role.id, permission_id=by_code[code].id))
    db.add(UserRole(user_id=owner.id, role_id=roles["owner"].id))
    vertical_roles = {}
    if org.industry.value == "clinic":
        vertical_roles = {
            "practitioner": {"dashboard.view", "clients.view", "appointments.view", "appointments.manage", "clinic.view", "clinical.view", "clinical.write", "clinical.sign", "documents.view", "documents.manage", "ai.use", "ai.actions"},
            "receptionist": {"dashboard.view", "clients.view", "clients.manage", "appointments.view", "appointments.manage", "sales.view", "sales.manage", "payments.record", "clinic.view", "inventory.view", "ai.use"},
            "pharmacist": {"dashboard.view", "clients.view", "clinic.view", "clinical.view", "catalog.view", "inventory.view", "inventory.adjust", "pharmacy.dispense", "sales.view", "sales.manage", "payments.record"},
        }
    elif org.industry.value == "gym":
        vertical_roles = {
            "trainer": {"dashboard.view", "clients.view", "appointments.view", "appointments.manage", "gym.view", "gym.dashboard.view", "gym.memberships.view", "gym.attendance.view", "gym.attendance.mark", "gym.coaching.view", "gym.coaching.manage", "gym.measurements.view", "gym.measurements.manage", "gym.workouts.view", "gym.workouts.manage", "gym.diets.view", "gym.diets.manage", "gym.classes.view", "gym.classes.manage", "client_memory.view", "client_memory.manage", "client_signals.view", "clients.media.view", "catalog.view", "ai.use"},
            "front-desk": {"dashboard.view", "clients.view", "clients.manage", "appointments.view", "appointments.manage", "gym.view", "gym.dashboard.view", "gym.memberships.view", "gym.memberships.manage", "gym.attendance.view", "gym.attendance.mark", "client_memory.view", "client_signals.view", "sales.view", "sales.manage", "payments.record", "catalog.view", "inventory.view"},
        }
    elif org.industry.value == "salon":
        vertical_roles = {
            "stylist": {"dashboard.view", "clients.view", "appointments.view", "appointments.manage", "catalog.view", "sales.view", "ai.use"},
            "front-desk": {"dashboard.view", "clients.view", "clients.manage", "appointments.view", "appointments.manage", "sales.view", "sales.manage", "payments.record", "catalog.view", "inventory.view"},
        }
    elif org.industry.value == "college":
        vertical_roles = COLLEGE_ROLE_GRANTS
    for slug, codes in vertical_roles.items():
        role = Role(organization_id=org.id, name=slug.replace("-", " ").title(), slug=slug, description=f"Default {slug} access", is_system=True)
        db.add(role); db.flush()
        for code in codes:
            db.add(RolePermission(role_id=role.id, permission_id=by_code[code].id))
    employee = Employee(
        organization_id=org.id, user_id=owner.id, employee_number="EMP-001",
        first_name=owner.first_name, last_name=owner.last_name, email=owner.email,
        phone=owner.phone, designation="Owner", status="active",
    )
    db.add(employee)
    db.flush()
    db.add(EmployeeLocation(employee_id=employee.id, location_id=primary_location.id, is_primary=True))
    trial_version = db.execute(
        select(PlanVersion).join(PlanDefinition, PlanDefinition.id == PlanVersion.plan_id)
        .where(PlanDefinition.slug == "trial", PlanVersion.status == "published")
        .order_by(PlanVersion.version.desc())
    ).scalars().first()
    from app.services.subscriptions import start_trial
    subscription = Subscription(
        organization_id=org.id, plan="trial", status="trialing", seats=5,
        plan_version_id=trial_version.id if trial_version else None,
    )
    db.add(start_trial(subscription))
    from datetime import datetime, timezone
    db.add(Job(organization_id=org.id, kind="refresh_client_signals", payload={"organization_id": org.id}, run_at=datetime.now(timezone.utc), idempotency_key="client-signals-bootstrap"))
    for module in org.enabled_modules:
        db.add(FeatureFlag(organization_id=org.id, flag=module, enabled=True, meta={}))
    db.add(FeatureFlag(
        organization_id=org.id, flag="ai.local_intent_v2", enabled=True,
        meta={"mode": "enabled", "engine_version": "local-intent-v1"},
    ))
    if org.industry.value == "college":
        db.add(FeatureFlag(
            organization_id=org.id, flag="college.placement_v1", enabled=True,
            meta={"mode": "enabled", "version": 1},
        ))


def ensure_control_plane(db: Session) -> None:
    feature_by_code = {row.code: row for row in db.execute(select(FeatureDefinition)).scalars()}
    for code, name, category, value_type in FEATURES:
        if code not in feature_by_code:
            row = FeatureDefinition(code=code, name=name, category=category, value_type=value_type, description=f"Controls {name.lower()} availability")
            db.add(row); db.flush(); feature_by_code[code] = row

    for order, (slug, spec) in enumerate(PLAN_SPECS.items()):
        plan = db.execute(select(PlanDefinition).where(PlanDefinition.slug == slug)).scalar_one_or_none()
        if not plan:
            plan = PlanDefinition(slug=slug, name=spec["name"], display_order=order, description=f"Edvatiq {spec['name']} plan")
            db.add(plan); db.flush()
        version = db.execute(select(PlanVersion).where(PlanVersion.plan_id == plan.id, PlanVersion.version == 2)).scalar_one_or_none()
        if not version:
            version = PlanVersion(
                plan_id=plan.id, version=2, status="published", monthly_price_paise=spec["monthly"],
                annual_price_paise=spec["annual"], annual_discount_bps=1667, included_ai_credits=spec["ai"],
                tax_enabled=spec["tax"], gst_rate_bps=1800,
                support_level=spec["support"], ai_tier=spec["tier"], effective_from=datetime.now(timezone.utc),
                published_at=datetime.now(timezone.utc),
            )
            db.add(version); db.flush()
        existing_entitlements = set(db.execute(select(FeatureDefinition.code).join(
            PlanEntitlement,
            PlanEntitlement.feature_id == FeatureDefinition.id,
        ).where(PlanEntitlement.plan_version_id == version.id)).scalars())
        for code, value in plan_entitlement_values(slug, spec).items():
            if code not in existing_entitlements:
                db.add(PlanEntitlement(
                    plan_version_id=version.id,
                    feature_id=feature_by_code[code].id,
                    value={"value": value},
                ))

    permission_by_code = {row.code: row for row in db.execute(select(PlatformPermission)).scalars()}
    for code, name, category in PLATFORM_PERMISSION_SPECS:
        if code not in permission_by_code:
            row = PlatformPermission(code=code, name=name, category=category)
            db.add(row); db.flush(); permission_by_code[code] = row
    for slug, grants in PLATFORM_ROLE_GRANTS.items():
        role = db.execute(select(PlatformRole).where(PlatformRole.slug == slug)).scalar_one_or_none()
        if not role:
            role = PlatformRole(slug=slug, name=slug.replace("-", " ").title(), description=f"Default {slug.replace('-', ' ')} access")
            db.add(role); db.flush()
        granted_codes = set(permission_by_code) if grants == "*" else grants
        existing = set(db.execute(select(PlatformRolePermission.permission_id).where(PlatformRolePermission.role_id == role.id)).scalars())
        for code in granted_codes:
            permission = permission_by_code[code]
            if permission.id not in existing:
                db.add(PlatformRolePermission(role_id=role.id, permission_id=permission.id))

    for key, value in {
        "financial_approvals": {"refund_threshold_paise": 1000000, "credit_threshold_paise": 1000000, "instant_settlement_requires_approval": True, "mfa_for_money_actions": True},
        "retention": {"gst_months": 72, "clinical_months": 96, "ordinary_grace_days": 30},
        "ai_credit_policy": {
            "version": "2026-08-cost-v1", "paise_per_credit": 25, "minimum_credits": 1,
            "route_max_credits": {"business": 8, "analytics": 20, "knowledge": 25, "action": 15},
            "models": {
                "gpt-5.4-mini": {"input": 255, "cached_input": 26, "output": 1530},
                "text-embedding-3-small": {"input": 7, "cached_input": 7, "output": 0},
            },
            "fallback": {"input": 255, "cached_input": 26, "output": 1530},
        },
        "billing_identity": {"registered_state": "Tamil Nadu", "country": "IN"},
    }.items():
        if not db.execute(select(PlatformSetting).where(PlatformSetting.key == key)).scalar_one_or_none():
            db.add(PlatformSetting(key=key, value=value))

    if not db.execute(select(RechargePack)).first():
        for order, (name, credits, price) in enumerate((("Quick top-up", 500, 49900), ("Team pack", 2000, 149900), ("Business pack", 10000, 599900))):
            db.add(RechargePack(name=name, credits=credits, price_paise=price, display_order=order))
    db.flush()


def attach_organizations_to_control_plane(db: Session) -> None:
    for org in db.execute(select(Organization)).scalars():
        subscription = db.execute(select(Subscription).where(Subscription.organization_id == org.id).order_by(Subscription.created_at.desc())).scalars().first()
        if not subscription:
            subscription = Subscription(organization_id=org.id, plan=org.plan.value, status="trialing" if org.plan.value == "trial" else "active")
            if org.plan.value == "trial":
                from app.services.subscriptions import start_trial
                start_trial(subscription)
            db.add(subscription); db.flush()
        if not subscription.plan_version_id:
            version = db.execute(
                select(PlanVersion).join(PlanDefinition, PlanDefinition.id == PlanVersion.plan_id)
                .where(PlanDefinition.slug == subscription.plan, PlanVersion.status == "published")
                .order_by(PlanVersion.version.desc())
            ).scalars().first()
            if version:
                subscription.plan_version_id = version.id
        if not db.execute(select(BillingProfile).where(BillingProfile.organization_id == org.id)).scalar_one_or_none():
            owner = db.execute(select(User).where(User.organization_id == org.id).order_by(User.created_at)).scalars().first()
            db.add(BillingProfile(organization_id=org.id, legal_name=org.legal_name or org.name, billing_email=org.contact_email or (owner.email if owner else None), gstin=org.gstin))
        ensure_wallet(db, org)


def ensure_missing_business_roles(db: Session, permissions: list[Permission]) -> None:
    """Add newly introduced system templates without changing customized roles."""
    by_code = {permission.code: permission for permission in permissions}
    common = {
        "accountant": ACCOUNTANT_ALLOW,
        "inventory-staff": INVENTORY_STAFF_ALLOW,
        "staff": STAFF_ALLOW,
    }
    vertical = {
        "gym": {
            "trainer": {
                "dashboard.view", "clients.view", "appointments.view", "appointments.manage",
                "gym.view", "gym.dashboard.view", "gym.memberships.view", "gym.attendance.view",
                "gym.attendance.mark", "gym.coaching.view", "gym.coaching.manage",
                "gym.measurements.view", "gym.measurements.manage", "gym.workouts.view",
                "gym.workouts.manage", "gym.diets.view", "gym.diets.manage", "gym.classes.view",
                "gym.classes.manage", "client_memory.view", "client_memory.manage",
                "client_signals.view", "clients.media.view", "catalog.view", "ai.use",
            },
            "front-desk": {
                "dashboard.view", "clients.view", "clients.manage", "appointments.view",
                "appointments.manage", "gym.view", "gym.dashboard.view", "gym.memberships.view",
                "gym.memberships.manage", "gym.attendance.view", "gym.attendance.mark",
                "client_memory.view", "client_signals.view", "sales.view", "sales.manage",
                "payments.record", "catalog.view", "inventory.view",
            },
        },
        "salon": {
            "stylist": {
                "dashboard.view", "clients.view", "appointments.view", "appointments.manage",
                "catalog.view", "sales.view", "salon.notes.view", "salon.notes.manage", "ai.use",
            },
            "front-desk": {
                "dashboard.view", "clients.view", "clients.manage", "appointments.view",
                "appointments.manage", "sales.view", "sales.manage", "payments.record",
                "catalog.view", "inventory.view",
            },
        },
        "clinic": {
            "practitioner": {
                "dashboard.view", "clients.view", "appointments.view", "appointments.manage",
                "clinic.view", "clinical.view", "clinical.write", "clinical.sign",
                "documents.view", "documents.manage", "ai.use", "ai.actions",
            },
            "receptionist": {
                "dashboard.view", "clients.view", "clients.manage", "appointments.view",
                "appointments.manage", "sales.view", "sales.manage", "payments.record",
                "clinic.view", "inventory.view", "ai.use",
            },
            "pharmacist": {
                "dashboard.view", "clients.view", "clinic.view", "clinical.view",
                "catalog.view", "inventory.view", "inventory.adjust", "pharmacy.dispense",
                "sales.view", "sales.manage", "payments.record",
            },
        },
        "college": COLLEGE_ROLE_GRANTS,
    }
    for organization in db.execute(select(Organization)).scalars():
        specs = {**common, **vertical.get(organization.industry.value, {})}
        existing_slugs = set(db.execute(select(Role.slug).where(Role.organization_id == organization.id)).scalars())
        existing_names = set(db.execute(select(Role.name).where(Role.organization_id == organization.id)).scalars())
        for slug, codes in specs.items():
            name = slug.replace("-", " ").title()
            if slug in existing_slugs or name in existing_names:
                continue
            role = Role(
                organization_id=organization.id, name=name, slug=slug,
                description=f"Default {name.lower()} access", is_system=True,
            )
            db.add(role)
            db.flush()
            for code in codes:
                if permission := by_code.get(code):
                    db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    # Callers may invoke the template and granular backfills independently.
    # Autoflush is disabled, so make newly created grants visible to the next query.
    db.flush()


def seed_platform(db: Session) -> None:
    ensure_control_plane(db)
    permissions = ensure_permissions(db)
    ensure_missing_business_roles(db, permissions)
    # Session autoflush is disabled; persist template grants before the granular
    # backfill reads the existing role-permission pairs.
    db.flush()
    sync_granular_role_permissions(db, permissions)
    email = settings.SUPER_ADMIN_EMAIL
    admin = db.execute(select(User).where(User.email == email, User.organization_id.is_(None)).order_by(User.created_at)).scalars().first()
    if not admin:
        admin = db.execute(select(User).where(User.email == "superadmin@edvatiq.local", User.organization_id.is_(None)).order_by(User.created_at)).scalars().first()
    if admin:
        admin.email = email
        db.flush()
    else:
        if not settings.SUPER_ADMIN_INITIAL_PASSWORD:
            raise RuntimeError("SUPER_ADMIN_INITIAL_PASSWORD is required when bootstrapping the production Platform Owner")
        admin = User(
            organization_id=None, email=email, hashed_password=hash_password(settings.SUPER_ADMIN_INITIAL_PASSWORD),
            first_name="Edvatiq", last_name="Admin", is_active=True, is_super_admin=True,
            email_verified=True,
        )
        db.add(admin)
        db.flush()
    owner_role = db.execute(select(PlatformRole).where(PlatformRole.slug == "platform-owner")).scalar_one()
    if not db.execute(select(PlatformUserRole).where(PlatformUserRole.user_id == admin.id, PlatformUserRole.role_id == owner_role.id)).scalar_one_or_none():
        db.add(PlatformUserRole(user_id=admin.id, role_id=owner_role.id))
    attach_organizations_to_control_plane(db)
    db.commit()


def seed_client_signal_jobs(db: Session) -> None:
    from datetime import datetime, timezone
    organizations = db.execute(select(Organization.id)).scalars().all()
    for organization_id in organizations:
        exists = db.execute(select(Job.id).where(Job.organization_id == organization_id, Job.kind == "refresh_client_signals", Job.status.in_(["queued", "running"]))).first()
        if not exists:
            now = datetime.now(timezone.utc)
            db.add(Job(organization_id=organization_id, kind="refresh_client_signals", payload={"organization_id": organization_id}, run_at=now, idempotency_key=f"client-signals-startup-{now.isoformat()}"))
    db.commit()


def create_demo_businesses(db: Session) -> None:
    """Create demo tenants on an empty database and safely enrich known demos."""
    demo_specs = [
        (IndustryEnum.gym, "Pulse Fitness", "pulse-fitness"),
        (IndustryEnum.salon, "Malar Studio", "malar-studio"),
        (IndustryEnum.clinic, "Nalam Clinic", "nalam-clinic"),
        (IndustryEnum.college, "Crescent Arts & Science College", "crescent-college"),
    ]
    organizations_exist = bool(db.execute(select(Organization.id).limit(1)).first())
    demo_slugs = {slug for _industry, _name, slug in demo_specs}
    has_demo_tenant = bool(db.execute(select(Organization.id).where(Organization.slug.in_(demo_slugs)).limit(1)).first())
    if not organizations_exist or has_demo_tenant:
        for industry, name, slug in demo_specs:
            if db.execute(select(Organization.id).where(Organization.slug == slug)).first():
                continue
            if industry == IndustryEnum.college:
                modules = ["clients", "employees", "sales", "college", "documents", "notifications", "reports", "ai"]
            else:
                modules = ["clients", "employees", "catalog", "inventory", "sales", "appointments", "documents", "notifications", "reports", "ai", industry.value]
            org = Organization(name=name, slug=slug, industry=industry, enabled_modules=modules, onboarding_complete=True, onboarding_step=5)
            db.add(org)
            db.flush()
            loc = Location(organization_id=org.id, name="Main Location", code="MAIN", city="Chennai", is_primary=True)
            db.add(loc)
            db.flush()
            owner = User(
                organization_id=org.id, email=f"owner@{slug}.edvatiq.com", hashed_password=hash_password("Owner@123"),
                first_name="Demo", last_name="Owner", is_active=True, email_verified=True,
            )
            db.add(owner)
            db.flush()
            seed_organization_defaults(db, org, owner, loc)
    from app.db.demo_seed import seed_demo_businesses

    seed_demo_businesses(db)
    db.commit()


def seed_welcome_notifications(db: Session) -> None:
    """Ensure each tenant has a useful first inbox item without duplicating it."""
    for org in db.execute(select(Organization)).scalars():
        owner = db.execute(select(User).where(User.organization_id == org.id).order_by(User.created_at).limit(1)).scalar_one_or_none()
        if not owner:
            continue
        exists = db.execute(select(Notification.id).where(Notification.organization_id == org.id, Notification.user_id == owner.id, Notification.title == "Welcome to Edvatiq")).first()
        if not exists:
            db.add(Notification(
                organization_id=org.id, user_id=owner.id, title="Welcome to Edvatiq",
                body="Your business workspace is ready. Complete business details, review locations, and invite your team.",
                kind="success", link="/app/settings",
            ))
    db.commit()
