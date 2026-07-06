"""Seed platform-wide permissions catalogue, default roles, and default super admin."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    FeatureFlag,
    Organization,
    Permission,
    Role,
    RolePermission,
    Subscription,
    User,
    UserRole,
)

# module -> list of (code, label)
PERMISSION_CATALOGUE: dict[str, list[tuple[str, str]]] = {
    "students": [
        ("students.view", "View students"),
        ("students.create", "Create student"),
        ("students.edit", "Edit student"),
        ("students.delete", "Delete student"),
    ],
    "faculty": [
        ("faculty.view", "View faculty"),
        ("faculty.create", "Create faculty"),
        ("faculty.edit", "Edit faculty"),
        ("faculty.delete", "Delete faculty"),
    ],
    "attendance": [
        ("attendance.view", "View attendance"),
        ("attendance.mark", "Mark attendance"),
        ("attendance.edit", "Edit attendance"),
        ("attendance.approve", "Approve attendance"),
    ],
    "marks": [
        ("marks.view", "View marks"),
        ("marks.enter", "Enter marks"),
        ("marks.edit", "Edit marks"),
        ("marks.publish", "Publish marks"),
    ],
    "academic": [
        ("academic.view", "View academic structure"),
        ("academic.manage", "Manage academic structure"),
        ("departments.manage", "Manage departments"),
        ("subjects.manage", "Manage subjects"),
    ],
    "users": [
        ("users.view", "View users"),
        ("users.manage", "Manage users"),
        ("roles.manage", "Manage roles and permissions"),
    ],
    "reports": [
        ("reports.view", "View reports"),
        ("reports.export", "Export reports"),
    ],
    "analytics": [
        ("analytics.view", "View analytics"),
    ],
    "ai": [
        ("ai.use", "Use AI assistant"),
        ("ai.manage", "Manage AI settings"),
    ],
    "billing": [
        ("billing.view", "View billing"),
        ("billing.manage", "Manage subscription and billing"),
    ],
    "settings": [
        ("settings.manage", "Manage organization settings"),
        ("audit.view", "View audit logs"),
    ],
    "notifications": [
        ("notifications.view", "View notifications"),
        ("notifications.send", "Send notifications"),
    ],
}


DEFAULT_ROLES: dict[str, list[str]] = {
    "Principal": [c for cats in PERMISSION_CATALOGUE.values() for c, _ in cats],  # everything
    "Administrator": [c for cats in PERMISSION_CATALOGUE.values() for c, _ in cats],
    "HOD": [
        "students.view", "faculty.view",
        "attendance.view", "attendance.approve",
        "marks.view", "marks.publish",
        "academic.view", "departments.manage", "subjects.manage",
        "reports.view", "reports.export", "analytics.view",
        "ai.use", "notifications.view", "notifications.send",
    ],
    "Faculty": [
        "students.view", "attendance.view", "attendance.mark", "attendance.edit",
        "marks.view", "marks.enter", "marks.edit",
        "academic.view", "reports.view", "ai.use", "notifications.view",
    ],
    "Class Advisor": [
        "students.view", "students.edit",
        "attendance.view", "attendance.mark", "attendance.edit", "attendance.approve",
        "marks.view", "marks.enter", "marks.edit",
        "academic.view", "reports.view", "analytics.view",
        "ai.use", "notifications.view", "notifications.send",
    ],
    "Student": [
        "students.view", "attendance.view", "marks.view", "ai.use", "notifications.view",
    ],
    "Parent": [
        "students.view", "attendance.view", "marks.view", "notifications.view",
    ],
}


def ensure_permission_catalogue(db: Session) -> dict[str, Permission]:
    existing = {p.code: p for p in db.execute(select(Permission).where(Permission.organization_id.is_(None))).scalars().all()}
    for module, items in PERMISSION_CATALOGUE.items():
        for code, label in items:
            if code not in existing:
                p = Permission(code=code, label=label, module=module)
                db.add(p)
                db.flush()
                existing[code] = p
    return existing


def seed_organization_defaults(db: Session, org: Organization, admin_user: User) -> None:
    """Create default roles for a new organization and assign Principal to admin_user."""
    perms = ensure_permission_catalogue(db)

    default_role_id_for_admin = None
    for role_name, perm_codes in DEFAULT_ROLES.items():
        role = Role(
            organization_id=org.id,
            name=role_name,
            slug=role_name.lower().replace(" ", "-"),
            is_system=True,
            is_active=True,
        )
        db.add(role)
        db.flush()
        for code in perm_codes:
            if code in perms:
                db.add(RolePermission(role_id=role.id, permission_id=perms[code].id))
        if role_name == "Principal":
            default_role_id_for_admin = role.id

    if default_role_id_for_admin:
        db.add(UserRole(user_id=admin_user.id, role_id=default_role_id_for_admin))

    # Trial subscription
    db.add(Subscription(organization_id=org.id, plan="trial", status="trialing", seats=100))

    # Default feature flags
    for flag in ["ai_assistant", "analytics", "attendance", "marks", "reports"]:
        db.add(FeatureFlag(organization_id=org.id, flag=flag, enabled=True))

    db.flush()


def seed_super_admin(db: Session) -> None:
    email = "superadmin@platform.io"
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        return
    admin = User(
        organization_id=None,
        email=email,
        hashed_password=hash_password("Super@123456"),
        first_name="Platform",
        last_name="Admin",
        is_active=True,
        is_super_admin=True,
    )
    db.add(admin)
    ensure_permission_catalogue(db)
    db.commit()


def seed_demo_organization(db: Session) -> None:
    """Create a demo college with sample data if not present."""
    from datetime import date

    from app.models import (
        AcademicLevel,
        AcademicUnit,
        AttendanceRecord,
        AttendanceSession,
        AttendanceStatusEnum,
        Department,
        Exam,
        Faculty,
        Mark,
        OrganizationTypeEnum,
        Section,
        Student,
        Subject,
    )

    if db.execute(select(Organization).where(Organization.slug == "demo-college")).scalar_one_or_none():
        return

    org = Organization(
        name="Demo College of Engineering",
        slug="demo-college",
        org_type=OrganizationTypeEnum.college,
        contact_email="principal@demo-college.edu",
        plan="pro",
        status="active",
    )
    db.add(org)
    db.flush()

    principal = User(
        organization_id=org.id,
        email="principal@demo-college.edu",
        hashed_password=hash_password("Principal@123"),
        first_name="Sundar",
        last_name="Rajan",
        is_active=True,
    )
    db.add(principal)
    db.flush()
    seed_organization_defaults(db, org, principal)

    # Departments
    cse = Department(organization_id=org.id, name="Computer Science", code="CSE")
    ece = Department(organization_id=org.id, name="Electronics", code="ECE")
    db.add_all([cse, ece])
    db.flush()

    # Academic units
    cse_unit = AcademicUnit(organization_id=org.id, department_id=cse.id, name="B.Tech CSE", code="BTECH-CSE")
    ece_unit = AcademicUnit(organization_id=org.id, department_id=ece.id, name="B.Tech ECE", code="BTECH-ECE")
    db.add_all([cse_unit, ece_unit])
    db.flush()

    # Levels + sections
    y2 = AcademicLevel(organization_id=org.id, unit_id=cse_unit.id, name="Year 2", sequence=2)
    db.add(y2)
    db.flush()
    sec_a = Section(organization_id=org.id, level_id=y2.id, name="A", room="CS-201")
    sec_b = Section(organization_id=org.id, level_id=y2.id, name="B", room="CS-202")
    db.add_all([sec_a, sec_b])
    db.flush()

    # Subjects
    subjects = [
        Subject(organization_id=org.id, department_id=cse.id, name="Data Structures", code="CS201", credits=4),
        Subject(organization_id=org.id, department_id=cse.id, name="Operating Systems", code="CS202", credits=4),
        Subject(organization_id=org.id, department_id=cse.id, name="Databases", code="CS203", credits=3),
    ]
    db.add_all(subjects)
    db.flush()

    # Faculty
    fac_users = []
    faculty_data = [
        ("meena.iyer@demo-college.edu", "Meena", "Iyer", "F001", cse.id, "Assistant Professor"),
        ("rahul.das@demo-college.edu", "Rahul", "Das", "F002", cse.id, "Associate Professor"),
    ]
    for email, fn, ln, empno, deptid, desig in faculty_data:
        u = User(
            organization_id=org.id,
            email=email,
            hashed_password=hash_password("Faculty@123"),
            first_name=fn,
            last_name=ln,
            is_active=True,
        )
        db.add(u)
        db.flush()
        db.add(Faculty(organization_id=org.id, user_id=u.id, employee_number=empno, department_id=deptid, designation=desig))
        # assign Faculty role
        faculty_role = db.execute(
            select(Role).where(Role.organization_id == org.id, Role.slug == "faculty")
        ).scalar_one()
        db.add(UserRole(user_id=u.id, role_id=faculty_role.id))
        fac_users.append(u)
    db.flush()

    # Students
    student_names = [
        ("2024CSE001", "Aditya", "Sharma", sec_a.id),
        ("2024CSE002", "Priya", "Reddy", sec_a.id),
        ("2024CSE003", "Suresh", "Kumar", sec_a.id),
        ("2024CSE004", "Ananya", "Nair", sec_b.id),
        ("2024CSE005", "Karthik", "Menon", sec_b.id),
        ("2024CSE006", "Divya", "Singh", sec_b.id),
    ]
    students = []
    for adm, fn, ln, sid in student_names:
        s = Student(
            organization_id=org.id,
            admission_number=adm,
            first_name=fn,
            last_name=ln,
            email=f"{fn.lower()}.{ln.lower()}@demo-college.edu",
            section_id=sid,
            department_id=cse.id,
            roll_number=adm[-3:],
        )
        db.add(s)
        students.append(s)
    db.flush()

    # Attendance sessions (last 5 days)
    today = date.today()
    for i in range(5):
        d = today.fromordinal(today.toordinal() - i)
        sess = AttendanceSession(
            organization_id=org.id,
            section_id=sec_a.id,
            subject_id=subjects[0].id,
            faculty_user_id=fac_users[0].id,
            session_date=d,
            topic="Session " + str(i + 1),
        )
        db.add(sess)
        db.flush()
        for idx, stu in enumerate(students[:3]):
            status_val = AttendanceStatusEnum.present if (idx + i) % 4 != 0 else AttendanceStatusEnum.absent
            db.add(
                AttendanceRecord(
                    organization_id=org.id, session_id=sess.id, student_id=stu.id, status=status_val
                )
            )
    db.flush()

    # Exams and marks
    exam = Exam(
        organization_id=org.id,
        name="Mid Term 1",
        exam_type="mid",
        subject_id=subjects[0].id,
        section_id=sec_a.id,
        max_marks=100.0,
        pass_marks=40.0,
        is_published=True,
    )
    db.add(exam)
    db.flush()
    for idx, stu in enumerate(students[:3]):
        db.add(
            Mark(
                organization_id=org.id,
                exam_id=exam.id,
                student_id=stu.id,
                obtained=[85.0, 72.0, 35.0][idx],
                grade=["A", "B", "F"][idx],
            )
        )
    db.commit()
