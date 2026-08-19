"""Rich, repeatable data for the local Edvatiq demo organizations."""
from __future__ import annotations

import hashlib
import struct
import uuid
import zlib
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    AIUsage,
    AccessScope,
    Allergy,
    Appointment,
    Category,
    CatalogItem,
    ChatConversation,
    ChatMessage,
    ChatTurn,
    ClassBooking,
    ClientCommitment,
    ClientMemory,
    ClientSignal,
    CoachingNote,
    Client,
    ClientMedia,
    CollegeAssessment,
    CollegeAssessmentComponent,
    CollegeAssessmentReadinessMapping,
    CollegeAssessmentScheme,
    CollegeAssessmentSchemeAssignment,
    CollegeAssessmentScore,
    CollegeAttendanceRecord,
    CollegeAttendanceSession,
    CollegeAttendanceSnapshot,
    CollegeApplicationStageEvent,
    CollegeCareerEvidence,
    CollegeCareerProfile,
    CollegeCodingAccount,
    CollegeCodingSnapshot,
    CollegeCohort,
    CollegeCourse,
    CollegeCourseOffering,
    CollegeDepartment,
    CollegeExamCycle,
    CollegeFeePlan,
    CollegePipelineStage,
    CollegePlacementApplication,
    CollegePlacementAssessment,
    CollegePlacementCompany,
    CollegePlacementInterview,
    CollegePlacementOffer,
    CollegePlacementOpportunity,
    CollegePreparationActivity,
    CollegeProgram,
    CollegeReadinessSnapshot,
    CollegeStudentFee,
    CollegeStudentProfile,
    CollegeTerm,
    CollegeTermResult,
    Diagnosis,
    DietPlan,
    Dispense,
    Document,
    DocumentChunk,
    Employee,
    EmployeeLocation,
    Encounter,
    Equipment,
    FitnessGoal,
    FitnessMeasurement,
    FeatureFlag,
    GymCheckIn,
    GymClass,
    Invoice,
    LabOrder,
    LabResult,
    LabTest,
    Location,
    Membership,
    MembershipPlan,
    Notification,
    Organization,
    OutboundMessage,
    PatientProfile,
    PaymentEvent,
    Prescription,
    PrescriptionItem,
    Role,
    SaleInvoice,
    SaleLine,
    SalePayment,
    SalonClientProfile,
    Setting,
    StaffSchedule,
    StockLevel,
    StockMovement,
    Task,
    TrainerAssignment,
    User,
    UserRole,
    Vital,
    WorkoutPlan,
    WorkoutSession,
)


DEMO_DATA_VERSION = 3
COLLEGE_DEMO_DATA_VERSION = 7
DEMO_SLUGS = {"pulse-fitness", "malar-studio", "nalam-clinic", "crescent-college"}
STORAGE_DIR = Path(__file__).resolve().parents[2] / "storage"


PEOPLE = [
    ("Aarav", "Krishnan", "9884011001", "aarav@example.test"),
    ("Diya", "Raman", "9884011002", "diya@example.test"),
    ("Kavin", "Raj", "9884011003", "kavin@example.test"),
    ("Nila", "Suresh", "9884011004", "nila@example.test"),
    ("Vikram", "Kumar", "9884011005", "vikram@example.test"),
    ("Meena", "Iyer", "9884011006", "meena@example.test"),
    ("Arun", "Prakash", "9884011007", "arun@example.test"),
    ("Tara", "Mohan", "9884011008", "tara@example.test"),
    ("Ravi", "Chandran", "9884011009", "ravi@example.test"),
    ("Ananya", "Devi", "9884011010", "ananya@example.test"),
    ("Surya", "Narayan", "9884011011", "surya@example.test"),
    ("Lakshmi", "Bala", "9884011012", "lakshmi@example.test"),
]

COLLEGE_STUDENT_FIRST_NAMES = [
    ("Aadhira", "female"), ("Akash", "male"), ("Bhavya", "female"),
    ("Charan", "male"), ("Deepika", "female"), ("Harish", "male"),
    ("Ishita", "female"), ("Jeevan", "male"), ("Keerthana", "female"),
    ("Lokesh", "male"), ("Madhumitha", "female"), ("Naveen", "male"),
    ("Oviya", "female"), ("Pranav", "male"), ("Rithika", "female"),
    ("Sanjay", "male"), ("Shruthi", "female"), ("Varun", "male"),
    ("Yazhini", "female"), ("Zoya", "female"),
]
COLLEGE_STUDENT_LAST_NAMES = ["Anand", "Balaji", "Iyer", "Menon", "Rao"]
COLLEGE_ADDITIONAL_STUDENT_COUNT = 100


STAFF = {
    "gym": [
        ("DEMO-EMP-002", "Arjun", "Kumar", "Head Trainer", "trainer"),
        ("DEMO-EMP-003", "Meera", "Nair", "Front Desk Executive", "front-desk"),
        ("DEMO-EMP-004", "Gopal", "Varma", "Operations Manager", "manager"),
    ],
    "salon": [
        ("DEMO-EMP-002", "Kavya", "Rao", "Senior Stylist", "stylist"),
        ("DEMO-EMP-003", "Priya", "Selvam", "Front Desk Executive", "front-desk"),
        ("DEMO-EMP-004", "Asha", "Menon", "Studio Manager", "manager"),
    ],
    "clinic": [
        ("DEMO-EMP-002", "Dr Anitha", "Ramesh", "General Practitioner", "practitioner"),
        ("DEMO-EMP-003", "Janani", "K", "Receptionist", "receptionist"),
        ("DEMO-EMP-004", "Mohan", "Das", "Pharmacist", "pharmacist"),
    ],
    "college": [
        ("DEMO-EMP-002", "Dr Meera", "Raman", "Academic Administrator", "academic-admin"),
        ("DEMO-EMP-003", "Arvind", "Narayan", "Assistant Professor", "faculty"),
        ("DEMO-EMP-004", "Nandhini", "Kumar", "Admissions Officer", "admissions"),
    ],
}


CATALOG = {
    "gym": [
        ("Services", "service", "Personal Training Session", "DEMO-GYM-PT", 120000, 0, False, 60),
        ("Services", "service", "Body Composition Assessment", "DEMO-GYM-BCA", 50000, 0, False, 30),
        ("Supplements", "product", "Whey Protein 1 kg", "DEMO-GYM-WHEY", 249900, 1800, True, None),
        ("Accessories", "product", "Resistance Band", "DEMO-GYM-BAND", 79900, 1200, True, None),
        ("Accessories", "product", "Training Shaker", "DEMO-GYM-SHAKER", 34900, 1800, True, None),
    ],
    "salon": [
        ("Hair Services", "service", "Signature Haircut", "DEMO-SALON-CUT", 90000, 0, False, 45),
        ("Hair Services", "service", "Hair Spa", "DEMO-SALON-SPA", 180000, 0, False, 75),
        ("Beauty Services", "service", "Radiance Facial", "DEMO-SALON-FACIAL", 220000, 0, False, 75),
        ("Retail", "product", "Repair Shampoo", "DEMO-SALON-SHAMPOO", 89900, 1800, True, None),
        ("Retail", "product", "Argan Hair Serum", "DEMO-SALON-SERUM", 119900, 1800, True, None),
    ],
    "clinic": [
        ("Consultation", "service", "General Consultation", "DEMO-CLINIC-CONSULT", 60000, 0, False, 20),
        ("Laboratory", "lab_test", "Complete Blood Count", "DEMO-CLINIC-CBC", 45000, 0, False, None),
        ("Laboratory", "lab_test", "Thyroid Profile", "DEMO-CLINIC-THYROID", 80000, 0, False, None),
        ("Pharmacy", "medicine", "Paracetamol 500 mg", "DEMO-CLINIC-PARA", 3000, 500, True, None),
        ("Pharmacy", "medicine", "Cetirizine 10 mg", "DEMO-CLINIC-CET", 4500, 500, True, None),
        ("Pharmacy", "medicine", "ORS Sachet", "DEMO-CLINIC-ORS", 2500, 500, True, None),
    ],
}


def _marker(db: Session, organization_id: str) -> Setting | None:
    return db.execute(
        select(Setting).where(
            Setting.organization_id == organization_id,
            Setting.key == "demo.data.version",
        )
    ).scalar_one_or_none()


def _seed_locations(db: Session, org: Organization) -> list[Location]:
    locations = list(db.execute(select(Location).where(Location.organization_id == org.id).order_by(Location.created_at)).scalars())
    if not any(row.code == "DEMO2" for row in locations):
        location = Location(
            organization_id=org.id,
            name="Anna Nagar Branch",
            code="DEMO2",
            address="12 Second Avenue, Anna Nagar",
            city="Chennai",
            state="Tamil Nadu",
            postal_code="600040",
            phone="04440001010",
        )
        db.add(location)
        db.flush()
        locations.append(location)
    primary = next((row for row in locations if row.is_primary), locations[0])
    primary.address = primary.address or "48 Cathedral Road, Gopalapuram"
    primary.state = primary.state or "Tamil Nadu"
    primary.postal_code = primary.postal_code or "600086"
    primary.phone = primary.phone or "04440002020"
    return locations


def _seed_staff(db: Session, org: Organization, locations: list[Location]) -> dict[str, Employee]:
    staff: dict[str, Employee] = {}
    shared_hash = hash_password("Demo@123!")
    for number, first_name, last_name, designation, role_slug in STAFF[org.industry.value]:
        email = f"{role_slug}@{org.slug}.edvatiq.com"
        user = db.execute(select(User).where(User.organization_id == org.id, User.email == email)).scalar_one_or_none()
        if not user:
            user = User(
                organization_id=org.id,
                email=email,
                hashed_password=shared_hash,
                first_name=first_name,
                last_name=last_name,
                designation=designation,
                is_active=True,
                email_verified=True,
            )
            db.add(user)
            db.flush()
        role = db.execute(select(Role).where(Role.organization_id == org.id, Role.slug == role_slug)).scalar_one_or_none()
        if role and not db.execute(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)).scalar_one_or_none():
            db.add(UserRole(user_id=user.id, role_id=role.id))
        employee = db.execute(
            select(Employee).where(Employee.organization_id == org.id, Employee.employee_number == number)
        ).scalar_one_or_none()
        if not employee:
            employee = Employee(
                organization_id=org.id,
                user_id=user.id,
                employee_number=number,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=f"988409{number[-3:]}",
                designation=designation,
                specialties=[designation, org.industry.value.title()],
                salary_paise=4500000 if role_slug == "manager" else 3200000,
                joining_date=date.today() - timedelta(days=420),
                status="active",
            )
            db.add(employee)
            db.flush()
        staff[role_slug] = employee
        for index, location in enumerate(locations):
            if not db.execute(select(EmployeeLocation).where(EmployeeLocation.employee_id == employee.id, EmployeeLocation.location_id == location.id)).scalar_one_or_none():
                db.add(EmployeeLocation(employee_id=employee.id, location_id=location.id, is_primary=index == 0))
        for weekday in range(6):
            if not db.execute(select(StaffSchedule).where(StaffSchedule.employee_id == employee.id, StaffSchedule.location_id == locations[0].id, StaffSchedule.weekday == weekday)).scalar_one_or_none():
                db.add(StaffSchedule(
                    organization_id=org.id,
                    location_id=locations[0].id,
                    employee_id=employee.id,
                    weekday=weekday,
                    starts_at=time(9),
                    ends_at=time(18),
                ))
        for scope_type, scope_value in (("location_mode", "full"), ("client_mode", "all")):
            if not db.execute(select(AccessScope).where(AccessScope.organization_id == org.id, AccessScope.user_id == user.id, AccessScope.scope_type == scope_type)).scalar_one_or_none():
                db.add(AccessScope(organization_id=org.id, user_id=user.id, scope_type=scope_type, scope_value=scope_value, meta={"source": "demo"}))
    db.flush()
    return staff


def _seed_clients(db: Session, org: Organization, locations: list[Location]) -> list[Client]:
    today = date.today()
    clients: list[Client] = []
    for index, (first_name, last_name, phone, email) in enumerate(PEOPLE, start=1):
        number = f"DEMO-{index:03d}"
        client = db.execute(
            select(Client).where(Client.organization_id == org.id, Client.client_number == number)
        ).scalar_one_or_none()
        if not client:
            birthday = today + timedelta(days=3) if index == 1 else date(1987 + index, ((index * 2) % 12) + 1, min(5 + index, 27))
            if index == 1:
                birthday = birthday.replace(year=1992)
            client = Client(
                organization_id=org.id,
                home_location_id=locations[(index - 1) % len(locations)].id,
                client_number=number,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                email=email,
                address=f"{20 + index}, Demo Street, Chennai",
                date_of_birth=birthday,
                gender="female" if index % 2 == 0 else "male",
                joined_on=today - timedelta(days=30 + index * 18),
                last_visit_at=datetime.now(timezone.utc) - timedelta(days=index * 2),
                notes="Demo record with realistic history for product testing.",
                tags=[org.industry.value, "priority" if index in {1, 4} else "regular"],
                whatsapp_consent=index % 4 != 0,
                whatsapp_consent_at=datetime.now(timezone.utc) - timedelta(days=100) if index % 4 != 0 else None,
                whatsapp_consent_source="front_desk" if index % 4 != 0 else None,
                email_consent=index % 3 != 0,
                status="inactive" if index == 12 else "active",
            )
            db.add(client)
            db.flush()
        clients.append(client)
    return clients


def _seed_catalog(db: Session, org: Organization) -> list[CatalogItem]:
    categories: dict[str, Category] = {}
    for category_name, kind, *_ in CATALOG[org.industry.value]:
        category = db.execute(select(Category).where(Category.organization_id == org.id, Category.name == category_name)).scalar_one_or_none()
        if not category:
            category = Category(organization_id=org.id, name=category_name, kind=kind)
            db.add(category)
            db.flush()
        categories[category_name] = category
    items: list[CatalogItem] = []
    for category_name, item_type, name, sku, price, tax, track_stock, duration in CATALOG[org.industry.value]:
        item = db.execute(select(CatalogItem).where(CatalogItem.organization_id == org.id, CatalogItem.sku == sku)).scalar_one_or_none()
        if not item:
            item = CatalogItem(
                organization_id=org.id,
                category_id=categories[category_name].id,
                name=name,
                sku=sku,
                item_type=item_type,
                description=f"Demo {name.lower()} used to test catalog, sales, and reporting.",
                hsn_sac="9997" if item_type == "service" else "3004" if item_type == "medicine" else "2106",
                price_paise=price,
                cost_paise=int(price * 0.55),
                tax_rate_bps=tax,
                duration_minutes=duration,
                unit="session" if item_type == "service" else "test" if item_type == "lab_test" else "unit",
                track_stock=track_stock,
            )
            db.add(item)
            db.flush()
        items.append(item)
    return items


def _seed_inventory(db: Session, org: Organization, owner: User, locations: list[Location], items: list[CatalogItem]) -> None:
    for item_index, item in enumerate((row for row in items if row.track_stock)):
        for location_index, location in enumerate(locations):
            batch = "DEMO-B01" if item.item_type == "medicine" else ""
            stock = db.execute(select(StockLevel).where(StockLevel.location_id == location.id, StockLevel.item_id == item.id, StockLevel.batch_number == batch)).scalar_one_or_none()
            if not stock:
                quantity = 3000 if item_index == 0 and location_index == 1 else (18 + item_index * 7 + location_index * 4) * 1000
                stock = StockLevel(
                    organization_id=org.id,
                    location_id=location.id,
                    item_id=item.id,
                    quantity_milli=quantity,
                    reorder_level_milli=5000,
                    batch_number=batch,
                    expires_on=date.today() + timedelta(days=240) if batch else None,
                )
                db.add(stock)
                db.flush()
                db.add(StockMovement(
                    organization_id=org.id,
                    location_id=location.id,
                    item_id=item.id,
                    stock_level_id=stock.id,
                    movement_type="receipt",
                    quantity_delta_milli=quantity,
                    reason="Opening demo stock",
                    reference_type="demo_seed",
                    performed_by_user_id=owner.id,
                ))


def _seed_appointments(db: Session, org: Organization, locations: list[Location], clients: list[Client], items: list[CatalogItem], staff: dict[str, Employee]) -> list[Appointment]:
    employee = staff.get("trainer") or staff.get("stylist") or staff.get("practitioner") or next(iter(staff.values()))
    services = [row for row in items if row.item_type in {"service", "lab_test"}]
    now = datetime.now(timezone.utc)
    appointments: list[Appointment] = []
    offsets = [-28, -18, -10, -4, -1, 0, 1, 3, 7, 12]
    for index, day_offset in enumerate(offsets):
        starts = (now + timedelta(days=day_offset)).replace(hour=5 + index % 7, minute=30, second=0, microsecond=0)
        status = "completed" if day_offset < -1 else "no_show" if day_offset == -1 else "scheduled"
        marker = f"DEMO appointment {index + 1}"
        appointment = db.execute(select(Appointment).where(Appointment.organization_id == org.id, Appointment.notes == marker)).scalar_one_or_none()
        if not appointment:
            appointment = Appointment(
                organization_id=org.id,
                location_id=locations[index % len(locations)].id,
                client_id=clients[index].id,
                employee_id=employee.id,
                service_id=services[index % len(services)].id,
                starts_at=starts,
                ends_at=starts + timedelta(minutes=services[index % len(services)].duration_minutes or 30),
                status=status,
                source="walk_in" if index % 4 == 0 else "staff",
                notes=marker,
                checked_in_at=starts - timedelta(minutes=5) if status == "completed" else None,
                completed_at=starts + timedelta(minutes=services[index % len(services)].duration_minutes or 30) if status == "completed" else None,
                created_at=starts - timedelta(days=2),
            )
            db.add(appointment)
            db.flush()
        appointments.append(appointment)
    return appointments


def _seed_sales(db: Session, org: Organization, owner: User, locations: list[Location], clients: list[Client], items: list[CatalogItem], staff: dict[str, Employee]) -> None:
    now = datetime.now(timezone.utc)
    employee = next(iter(staff.values()))
    for index, days_ago in enumerate((1, 3, 6, 9, 14, 21, 35, 52), start=1):
        item = items[(index - 1) % len(items)]
        key = f"demo-sale-{org.slug}-{index}"
        if db.execute(select(SaleInvoice).where(SaleInvoice.organization_id == org.id, SaleInvoice.idempotency_key == key)).scalar_one_or_none():
            continue
        total = item.price_paise * (2 if index == 3 else 1)
        paid = total if index not in {4, 7} else total // 2
        issued_at = now - timedelta(days=days_ago)
        invoice = SaleInvoice(
            organization_id=org.id,
            location_id=locations[index % len(locations)].id,
            client_id=clients[(index - 1) % len(clients)].id,
            employee_id=employee.id,
            invoice_number=f"DEMO-{org.industry.value[:3].upper()}-{index:04d}",
            status="paid" if paid == total else "partially_paid",
            subtotal_paise=total,
            total_paise=total,
            paid_paise=paid,
            notes="Demo transaction",
            idempotency_key=key,
            issued_at=issued_at,
            created_at=issued_at,
        )
        db.add(invoice)
        db.flush()
        db.add(SaleLine(
            organization_id=org.id,
            invoice_id=invoice.id,
            display_order=0,
            item_id=item.id,
            item_name=item.name,
            sku=item.sku,
            hsn_sac=item.hsn_sac,
            quantity_milli=2000 if index == 3 else 1000,
            unit_price_paise=item.price_paise,
            tax_rate_bps=item.tax_rate_bps,
            total_paise=total,
        ))
        if paid:
            db.add(SalePayment(
                organization_id=org.id,
                invoice_id=invoice.id,
                amount_paise=paid,
                method=("upi", "cash", "card")[index % 3],
                reference=f"DEMO-PAY-{index:04d}",
                status="captured",
                idempotency_key=f"demo-payment-{org.slug}-{index}",
                received_by_user_id=owner.id,
                created_at=issued_at,
            ))


def _seed_relationship_data(db: Session, org: Organization, owner: User, clients: list[Client], staff: dict[str, Employee], locations: list[Location]) -> None:
    now = datetime.now(timezone.utc)
    memory_values = {
        "gym": ("Goal", "Train for a 10 km run while improving mobility."),
        "salon": ("Preference", "Prefers quiet appointments and ammonia-free products."),
        "clinic": ("Language", "Prefers explanations in Tamil with English medicine names."),
    }
    for index, client in enumerate(clients[:6]):
        label, value = memory_values[org.industry.value]
        if not db.execute(select(ClientMemory).where(ClientMemory.client_id == client.id, ClientMemory.label == label)).scalar_one_or_none():
            db.add(ClientMemory(
                organization_id=org.id,
                client_id=client.id,
                category="goal" if org.industry.value == "gym" else "preference",
                label=label,
                value=value,
                visibility="team" if org.industry.value != "clinic" else "clinical",
                created_by_user_id=owner.id,
            ))
        title = "Review progress and agree the next step"
        if not db.execute(select(ClientCommitment).where(ClientCommitment.client_id == client.id, ClientCommitment.title == title)).scalar_one_or_none():
            db.add(ClientCommitment(
                organization_id=org.id,
                client_id=client.id,
                title=title,
                description="Follow up personally and record the outcome.",
                owner_user_id=owner.id,
                due_at=now + timedelta(days=-2 if index == 0 else index + 1),
                reminder_at=now + timedelta(days=index),
                status="open" if index < 4 else "completed",
                completion_note="Discussed and updated." if index >= 4 else None,
                completed_at=now - timedelta(days=1) if index >= 4 else None,
                created_by_user_id=owner.id,
            ))
    signal_specs = {
        "gym": ("attendance_drop", "watch", "Visit frequency has dropped", "Visits changed from 6 to 2 in the latest two-week period.", "Check in with the assigned trainer"),
        "salon": ("rebooking_due", "watch", "Usual visit window has passed", "The normal 45-day visit interval is now 12 days overdue.", "Offer two suitable rebooking times"),
        "clinic": ("clinical_follow_up", "action_needed", "Clinical follow-up is due", "The documented review date has passed by 3 days.", "Review the care follow-up"),
    }
    signal_type, state, title, explanation, action = signal_specs[org.industry.value]
    client = clients[0]
    if not db.execute(select(ClientSignal).where(ClientSignal.client_id == client.id, ClientSignal.signal_type == signal_type, ClientSignal.rule_version == "demo-v1")).scalar_one_or_none():
        db.add(ClientSignal(
            organization_id=org.id,
            location_id=client.home_location_id,
            client_id=client.id,
            signal_type=signal_type,
            pulse_state=state,
            title=title,
            explanation=explanation,
            evidence=[{"metric": "demo_evidence", "value": explanation}],
            recommended_action=action,
            status="open",
            assigned_to_user_id=next(iter(staff.values())).user_id,
            generated_at=now,
            rule_version="demo-v1",
        ))


def _seed_tasks_and_messages(db: Session, org: Organization, owner: User, locations: list[Location], clients: list[Client]) -> None:
    now = datetime.now(timezone.utc)
    tasks = [
        ("Call clients whose follow-up is due", "high", 0, "open"),
        ("Review low-stock items", "high", 1, "open"),
        ("Confirm tomorrow's appointments", "normal", 1, "open"),
        ("Complete weekly business review", "normal", -1, "completed"),
    ]
    for index, (title, priority, offset, status) in enumerate(tasks):
        if not db.execute(select(Task).where(Task.organization_id == org.id, Task.title == title)).scalar_one_or_none():
            db.add(Task(
                organization_id=org.id,
                location_id=locations[0].id,
                assigned_to_user_id=owner.id,
                client_id=clients[index].id if index < 3 else None,
                title=title,
                description="Demo task created to exercise work queues and reminders.",
                due_at=now + timedelta(days=offset),
                priority=priority,
                status=status,
                source="demo",
            ))
    notifications = [
        ("Three clients need attention", "Review their explainable signals and next actions.", "warning", "/app/attention"),
        ("Tomorrow's schedule is ready", "Upcoming bookings have been checked for conflicts.", "info", "/app/calendar"),
        ("Low stock at Anna Nagar", "One item has reached its reorder threshold.", "warning", "/app/catalog"),
        ("Weekly target achieved", "Collections are ahead of the previous week.", "success", "/app/reports"),
    ]
    for title, body, kind, link in notifications:
        if not db.execute(select(Notification).where(Notification.organization_id == org.id, Notification.user_id == owner.id, Notification.title == title)).scalar_one_or_none():
            db.add(Notification(organization_id=org.id, user_id=owner.id, title=title, body=body, kind=kind, link=link))
    key = f"demo-message-{org.slug}"
    if not db.execute(select(OutboundMessage).where(OutboundMessage.organization_id == org.id, OutboundMessage.idempotency_key == key)).scalar_one_or_none():
        db.add(OutboundMessage(
            organization_id=org.id,
            location_id=locations[0].id,
            client_id=clients[1].id,
            channel="whatsapp",
            recipient=clients[1].phone or "",
            template="demo_reminder",
            template_language="en",
            template_variables=[clients[1].first_name, org.name],
            body="This is a completed demo reminder and will not contact a provider.",
            status="sent",
            provider_message_id=f"demo-{org.slug}",
            attempts=1,
            sent_at=now - timedelta(days=1),
            idempotency_key=key,
        ))


def _seed_document_and_ai(db: Session, org: Organization, owner: User) -> None:
    if org.industry.value == "college":
        guide_lines = (
            "Daily checklist: review today's timetable, unmarked attendance, assessment deadlines, and fee follow-ups.\n"
            "Student records must stay within assigned academic and financial permissions. Fee changes require an auditable invoice.\n"
            "Escalate timetable conflicts to the academic administrator and preserve the resolution in the student workspace.\n"
        )
        assistant_content = "Focus on today's classes, attendance yet to be recorded, upcoming assessments, and student fee balances."
    else:
        guide_lines = (
            "Opening checklist: review today's appointments, unresolved client signals, and low stock.\n"
            "Client follow-ups must respect recorded communication consent. Financial and clinical actions require explicit approval.\n"
            "Escalate unresolved complaints to the manager and record the agreed commitment in the client workspace.\n"
        )
        assistant_content = "Focus on overdue follow-ups, tomorrow's bookings, and the low-stock item at Anna Nagar."
    content = f"{org.name} Demo Operations Guide\n\n{guide_lines}".encode("utf-8")
    object_key = f"{org.id}/demo/operations-guide.txt"
    path = STORAGE_DIR / object_key
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(content)
    document = db.execute(select(Document).where(Document.organization_id == org.id, Document.object_key == object_key)).scalar_one_or_none()
    if not document:
        document = Document(
            organization_id=org.id,
            location_id=None,
            uploaded_by_user_id=owner.id,
            entity_type="organization",
            entity_id=org.id,
            name="Demo Operations Guide.txt",
            object_key=object_key,
            content_type="text/plain",
            size_bytes=len(content),
            checksum=hashlib.sha256(content).hexdigest(),
            status="ready",
            extracted_text=content.decode("utf-8"),
            visibility="team",
        )
        db.add(document)
        db.flush()
    if not db.execute(select(DocumentChunk).where(DocumentChunk.document_id == document.id, DocumentChunk.chunk_index == 0)).scalar_one_or_none():
        db.add(DocumentChunk(
            organization_id=org.id,
            document_id=document.id,
            chunk_index=0,
            content=content.decode("utf-8"),
            page_number=1,
            section="Operations guide",
            token_count=70,
            meta={"source": "demo"},
        ))
    title = "Weekly business review"
    conversation = db.execute(select(ChatConversation).where(ChatConversation.organization_id == org.id, ChatConversation.user_id == owner.id, ChatConversation.title == title)).scalar_one_or_none()
    if not conversation:
        conversation = ChatConversation(organization_id=org.id, user_id=owner.id, title=title, provider="demo", model="configured")
        db.add(conversation)
        db.flush()
        completed_at = datetime.now(timezone.utc)
        turn = ChatTurn(
            organization_id=org.id,
            conversation_id=conversation.id,
            user_id=owner.id,
            request_key="demo:weekly-business-review",
            status="completed",
            completed_at=completed_at,
        )
        db.add(turn)
        db.flush()
        db.add_all([
            ChatMessage(
                organization_id=org.id,
                conversation_id=conversation.id,
                turn_id=turn.id,
                role="user",
                content="What needs my attention today?",
            ),
            ChatMessage(
                organization_id=org.id,
                conversation_id=conversation.id,
                turn_id=turn.id,
                role="assistant",
                content=assistant_content,
                outcome="success",
                artifacts=[{
                    "id": "demo-open-priorities",
                    "type": "metric",
                    "title": "Open priorities",
                    "data": {"value": 3, "format": "number"},
                    "evidence_ids": ["demo-priority-observation"],
                    "security": {"permissions": ["ai.use"], "domains": [], "scope": {}, "entity_ids": []},
                }],
                evidence=[{
                    "id": "demo-priority-observation",
                    "kind": "demo_summary",
                    "entity": "organization",
                    "facts": {"open_priorities": 3},
                    "source": "Edvatiq demo data",
                    "authorized_scope": "your organization",
                }],
            ),
        ])
        db.add(AIUsage(
            organization_id=org.id,
            user_id=owner.id,
            model="demo",
            input_tokens=18,
            output_tokens=32,
            tool_calls=2,
            latency_ms=420,
            route="business",
            status="completed",
            credits_used=2,
            tool_latency_ms=90,
        ))


def _solid_png(red: int, green: int, blue: int, size: int = 96) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    scanlines = b"".join(b"\x00" + bytes((red, green, blue)) * size for _ in range(size))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(scanlines, 9)) + chunk(b"IEND", b"")


def _seed_client_media(db: Session, org: Organization, owner: User, clients: list[Client]) -> None:
    palette = {
        "gym": [(232, 116, 25), (23, 53, 43), (224, 183, 92)],
        "salon": [(177, 82, 72), (45, 72, 63), (222, 170, 137)],
        "clinic": [(36, 119, 130), (32, 71, 66), (116, 166, 150)],
        "college": [(28, 77, 121), (28, 94, 82), (191, 132, 45)],
    }[org.industry.value]
    for client, color in zip(clients[:3], palette):
        object_key = f"{org.id}/clients/{client.id}/demo-profile.png"
        content = _solid_png(*color)
        path = STORAGE_DIR / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(content)
        document = db.execute(select(Document).where(Document.organization_id == org.id, Document.object_key == object_key)).scalar_one_or_none()
        if not document:
            document = Document(
                organization_id=org.id,
                location_id=client.home_location_id,
                uploaded_by_user_id=owner.id,
                entity_type="client",
                entity_id=client.id,
                name=f"{client.first_name.lower()}-profile.png",
                object_key=object_key,
                content_type="image/png",
                size_bytes=len(content),
                checksum=hashlib.sha256(content).hexdigest(),
                status="ready",
                visibility="team",
            )
            db.add(document)
            db.flush()
        if not db.execute(select(ClientMedia).where(ClientMedia.document_id == document.id)).scalar_one_or_none():
            db.add(ClientMedia(
                organization_id=org.id,
                location_id=client.home_location_id,
                client_id=client.id,
                document_id=document.id,
                media_kind="profile_photo",
                caption="Demo profile photo",
                captured_at=datetime.now(timezone.utc),
                visibility="team",
                is_profile=True,
                uploaded_by_user_id=owner.id,
            ))


def _seed_platform_billing(db: Session, org: Organization) -> None:
    number = f"DEMO-SUB-{org.slug.upper()}"
    if not db.execute(select(Invoice).where(Invoice.invoice_number == number)).scalar_one_or_none():
        now = datetime.now(timezone.utc)
        invoice = Invoice(
            organization_id=org.id,
            amount_paise=117882,
            subtotal_paise=99900,
            tax_paise=17982,
            cgst_paise=8991,
            sgst_paise=8991,
            gst_rate_bps=1800,
            status="paid",
            description="Demo Starter subscription",
            invoice_number=number,
            billing_snapshot={"legal_name": org.legal_name or org.name, "state": "Tamil Nadu"},
            plan_snapshot={"name": "Starter", "interval": "monthly", "price_paise": 99900},
            due_at=now - timedelta(days=20),
            paid_at=now - timedelta(days=21),
            reconciled_at=now - timedelta(days=20),
            created_at=now - timedelta(days=24),
        )
        db.add(invoice)
        db.add(PaymentEvent(
            organization_id=org.id,
            event_type="payment.captured",
            provider_event_id=f"demo-payment-event-{org.slug}",
            provider_mode="test",
            status="processed",
            processed_at=now - timedelta(days=21),
            payload={"source": "demo", "invoice_number": number},
        ))


def _seed_gym(db: Session, org: Organization, owner: User, locations: list[Location], clients: list[Client], staff: dict[str, Employee]) -> None:
    today = date.today()
    now = datetime.now(timezone.utc)
    trainer = staff["trainer"]
    plans: list[MembershipPlan] = []
    for name, duration, price, benefits in (
        ("Monthly Flex", 30, 250000, ["Gym floor", "One assessment"]),
        ("Quarterly Progress", 90, 650000, ["Gym floor", "Monthly assessment", "Two PT sessions"]),
        ("Annual Unlimited", 365, 2200000, ["All locations", "Classes", "Quarterly coaching"]),
    ):
        plan = db.execute(select(MembershipPlan).where(MembershipPlan.organization_id == org.id, MembershipPlan.name == name)).scalar_one_or_none()
        if not plan:
            plan = MembershipPlan(organization_id=org.id, name=name, duration_days=duration, price_paise=price, joining_fee_paise=50000 if duration == 30 else 0, benefits=benefits)
            db.add(plan)
            db.flush()
        plans.append(plan)
    memberships: list[Membership] = []
    for index, client in enumerate(clients[:10]):
        membership = db.execute(select(Membership).where(Membership.organization_id == org.id, Membership.client_id == client.id)).scalars().first()
        if not membership:
            plan = plans[index % len(plans)]
            starts = today - timedelta(days=15 + index * 8)
            status = "frozen" if index == 7 else "cancelled" if index == 8 else "expired" if index == 9 else "active"
            ends = today + timedelta(days=(3 if index == 0 else 12 + index * 12)) if status in {"active", "frozen"} else today - timedelta(days=8 + index)
            membership = Membership(
                organization_id=org.id,
                location_id=locations[index % len(locations)].id,
                client_id=client.id,
                plan_id=plan.id,
                starts_on=starts,
                ends_on=ends,
                amount_paise=plan.price_paise,
                status=status,
                frozen_from=today - timedelta(days=2) if status == "frozen" else None,
                frozen_until=today + timedelta(days=5) if status == "frozen" else None,
                cancellation_reason="Moved away" if status == "cancelled" else None,
            )
            db.add(membership)
            db.flush()
        memberships.append(membership)
        if index < 8 and not db.execute(select(TrainerAssignment).where(TrainerAssignment.organization_id == org.id, TrainerAssignment.client_id == client.id, TrainerAssignment.trainer_employee_id == trainer.id)).scalar_one_or_none():
            db.add(TrainerAssignment(organization_id=org.id, client_id=client.id, trainer_employee_id=trainer.id, starts_on=today - timedelta(days=60), status="active"))
    for index, membership in enumerate(memberships[:8]):
        offsets = [0, 2, 5, 8, 11, 15, 18, 22, 26] if index != 0 else [0, 15, 18, 21, 24, 27]
        for offset in offsets[: max(3, 9 - index)]:
            checked_in = (now - timedelta(days=offset)).replace(hour=1 + index % 4, minute=index * 3, second=0, microsecond=0)
            if not db.execute(select(GymCheckIn).where(GymCheckIn.membership_id == membership.id, GymCheckIn.checked_in_at == checked_in)).scalar_one_or_none():
                db.add(GymCheckIn(
                    organization_id=org.id,
                    location_id=membership.location_id,
                    membership_id=membership.id,
                    client_id=membership.client_id,
                    checked_in_at=checked_in,
                    checked_out_at=checked_in + timedelta(minutes=72),
                    method="qr" if index % 2 else "staff",
                    recorded_by_user_id=owner.id,
                    source="demo",
                ))
    for index, client in enumerate(clients[:6]):
        for month_offset, weight_delta in ((-60, 4.0), (-30, 2.1), (0, 0.0)):
            measured_on = today + timedelta(days=month_offset)
            if not db.execute(select(FitnessMeasurement).where(FitnessMeasurement.client_id == client.id, FitnessMeasurement.measured_on == measured_on)).scalar_one_or_none():
                db.add(FitnessMeasurement(
                    organization_id=org.id,
                    client_id=client.id,
                    measured_on=measured_on,
                    metrics={"weight_kg": 68 + index + weight_delta, "body_fat_pct": 24 - index * 0.5 + weight_delta / 2, "waist_cm": 82 + index + weight_delta},
                    notes="Progress measurement",
                ))
        plan = db.execute(select(WorkoutPlan).where(WorkoutPlan.organization_id == org.id, WorkoutPlan.client_id == client.id, WorkoutPlan.name == "Strength foundation")).scalar_one_or_none()
        if not plan:
            plan = WorkoutPlan(
                organization_id=org.id,
                client_id=client.id,
                trainer_employee_id=trainer.id,
                name="Strength foundation",
                schedule=[{"day": "Monday", "focus": "Lower body"}, {"day": "Thursday", "focus": "Upper body"}],
                starts_on=today - timedelta(days=40),
                ends_on=today + timedelta(days=50),
            )
            db.add(plan)
            db.flush()
        if not db.execute(select(DietPlan).where(DietPlan.organization_id == org.id, DietPlan.client_id == client.id, DietPlan.name == "Balanced performance plan")).scalar_one_or_none():
            db.add(DietPlan(
                organization_id=org.id,
                client_id=client.id,
                name="Balanced performance plan",
                meals=[{"time": "08:00", "meal": "Oats, fruit and eggs"}, {"time": "13:00", "meal": "Rice, vegetables and protein"}, {"time": "20:00", "meal": "Light dinner"}],
                notes="Hydration target: 2.5 litres daily.",
                starts_on=today - timedelta(days=20),
                ends_on=today + timedelta(days=40),
            ))
        if not db.execute(select(FitnessGoal).where(FitnessGoal.organization_id == org.id, FitnessGoal.client_id == client.id, FitnessGoal.metric_key == "weight_kg")).scalar_one_or_none():
            db.add(FitnessGoal(
                organization_id=org.id,
                client_id=client.id,
                metric_key="weight_kg",
                label="Target weight",
                baseline_value=72 + index,
                target_value=66 + index,
                current_value=68 + index,
                unit="kg",
                starts_on=today - timedelta(days=60),
                target_on=today - timedelta(days=2) if index == 1 else today + timedelta(days=45),
                status="active",
                created_by_user_id=owner.id,
            ))
        for session_index in range(3):
            scheduled = (now - timedelta(days=7 - session_index * 3)).replace(hour=2, minute=index * 2, second=0, microsecond=0)
            if not db.execute(select(WorkoutSession).where(WorkoutSession.client_id == client.id, WorkoutSession.scheduled_for == scheduled)).scalar_one_or_none():
                db.add(WorkoutSession(
                    organization_id=org.id,
                    location_id=locations[index % len(locations)].id,
                    client_id=client.id,
                    workout_plan_id=plan.id,
                    trainer_employee_id=trainer.id,
                    scheduled_for=scheduled,
                    started_at=scheduled,
                    completed_at=scheduled + timedelta(minutes=55),
                    status="completed",
                    exercise_results=[{"exercise": "Squat", "sets": 3, "reps": 10}, {"exercise": "Row", "sets": 3, "reps": 12}],
                    effort_rating=7 + session_index % 2,
                    notes="Good technique and steady progress.",
                    recorded_by_user_id=owner.id,
                ))
        note_text = "Improved squat depth; increase load gradually next week."
        if not db.execute(select(CoachingNote).where(CoachingNote.client_id == client.id, CoachingNote.note == note_text)).scalar_one_or_none():
            db.add(CoachingNote(organization_id=org.id, client_id=client.id, trainer_employee_id=trainer.id, note=note_text, visibility="assigned_staff", recorded_by_user_id=owner.id))
    classes: list[GymClass] = []
    for index, (name, hour) in enumerate((("Morning Mobility", 1), ("Strength Circuit", 12), ("Weekend Yoga", 3))):
        starts = (now + timedelta(days=index)).replace(hour=hour, minute=30, second=0, microsecond=0)
        gym_class = db.execute(select(GymClass).where(GymClass.organization_id == org.id, GymClass.name == name, GymClass.starts_at == starts)).scalar_one_or_none()
        if not gym_class:
            gym_class = GymClass(organization_id=org.id, location_id=locations[index % len(locations)].id, trainer_employee_id=trainer.id, name=name, starts_at=starts, ends_at=starts + timedelta(minutes=60), capacity=12 + index * 4, status="scheduled")
            db.add(gym_class)
            db.flush()
        classes.append(gym_class)
    for gym_class in classes:
        for client in clients[:4]:
            if not db.execute(select(ClassBooking).where(ClassBooking.gym_class_id == gym_class.id, ClassBooking.client_id == client.id)).scalar_one_or_none():
                db.add(ClassBooking(organization_id=org.id, gym_class_id=gym_class.id, client_id=client.id, status="booked"))
    for index, name in enumerate(("Treadmill 01", "Cable Machine", "Rowing Machine", "Leg Press", "Spin Bike 02"), start=1):
        code = f"DEMO-EQ-{index:03d}"
        if not db.execute(select(Equipment).where(Equipment.organization_id == org.id, Equipment.asset_code == code)).scalar_one_or_none():
            db.add(Equipment(
                organization_id=org.id,
                location_id=locations[index % len(locations)].id,
                name=name,
                asset_code=code,
                status="maintenance_due" if index == 3 else "operational",
                purchased_on=today - timedelta(days=500 + index * 40),
                next_service_on=today - timedelta(days=2) if index == 3 else today + timedelta(days=20 + index * 8),
                notes="Demo equipment maintenance record.",
            ))


def _seed_salon(db: Session, org: Organization, clients: list[Client], staff: dict[str, Employee]) -> None:
    stylist = staff["stylist"]
    for index, client in enumerate(clients):
        if not db.execute(select(SalonClientProfile).where(SalonClientProfile.organization_id == org.id, SalonClientProfile.client_id == client.id)).scalar_one_or_none():
            db.add(SalonClientProfile(
                organization_id=org.id,
                client_id=client.id,
                preferred_employee_id=stylist.id,
                preferred_services=["Signature Haircut", "Hair Spa"] if index % 2 else ["Radiance Facial"],
                preferences={"beverage": "green tea", "appointment_style": "quiet", "heat_level": "low"},
                sensitivities="Sensitive scalp; patch test before colour." if index % 3 == 0 else None,
                formulas="Root: 5N + 5.3, 20 vol, 35 minutes" if index % 4 == 0 else None,
                visit_interval_days=35 + index % 3 * 10,
            ))


def _seed_clinic(db: Session, org: Organization, owner: User, locations: list[Location], clients: list[Client], staff: dict[str, Employee], appointments: list[Appointment], items: list[CatalogItem]) -> None:
    now = datetime.now(timezone.utc)
    practitioner = staff["practitioner"]
    pharmacist = staff["pharmacist"]
    tests: list[LabTest] = []
    for code, name, price, ranges in (
        ("CBC", "Complete Blood Count", 45000, {"haemoglobin": "12-16 g/dL"}),
        ("THY", "Thyroid Profile", 80000, {"tsh": "0.4-4.0 mIU/L"}),
    ):
        test = db.execute(select(LabTest).where(LabTest.organization_id == org.id, LabTest.code == code)).scalar_one_or_none()
        if not test:
            test = LabTest(organization_id=org.id, name=name, code=code, price_paise=price, reference_ranges=ranges)
            db.add(test)
            db.flush()
        tests.append(test)
    medicine = next(row for row in items if row.item_type == "medicine")
    for index, client in enumerate(clients[:10]):
        patient = db.execute(select(PatientProfile).where(PatientProfile.client_id == client.id)).scalar_one_or_none()
        if not patient:
            patient = PatientProfile(
                organization_id=org.id,
                client_id=client.id,
                abha_number=f"91-0000-0000-{1000 + index}" if index < 3 else None,
                blood_group=("O+", "A+", "B+", "AB+")[index % 4],
                emergency_contact={"name": f"Family contact {index + 1}", "phone": f"988402{index:04d}"},
                consent={"care": True, "documents": True, "communications": index % 3 != 0},
                medical_summary="Stable outpatient with documented follow-up needs." if index < 4 else None,
            )
            db.add(patient)
            db.flush()
        if index == 0 and not db.execute(select(Allergy).where(Allergy.patient_id == patient.id, Allergy.substance == "Penicillin")).scalar_one_or_none():
            db.add(Allergy(organization_id=org.id, patient_id=patient.id, substance="Penicillin", reaction="Rash", severity="moderate", status="active"))
        if index >= 5:
            continue
        encounter = db.execute(select(Encounter).where(Encounter.organization_id == org.id, Encounter.patient_id == patient.id)).scalars().first()
        if encounter:
            continue
        signed = index < 4
        encounter = Encounter(
            organization_id=org.id,
            location_id=locations[index % len(locations)].id,
            patient_id=patient.id,
            appointment_id=appointments[index].id if index < len(appointments) else None,
            practitioner_employee_id=practitioner.id,
            status="signed" if signed else "open",
            chief_complaint=("Fever and fatigue", "Seasonal allergy", "Headache", "Routine review", "Abdominal discomfort")[index],
            clinical_notes="Symptoms reviewed, red flags absent, and safety advice explained.",
            assessment="Stable for outpatient management.",
            plan="Supportive treatment and review if symptoms persist.",
            follow_up_on=date.today() - timedelta(days=3) if index == 0 else date.today() + timedelta(days=7 + index),
            signed_at=now - timedelta(days=8 - index) if signed else None,
            signed_by_user_id=practitioner.user_id if signed else None,
            created_at=now - timedelta(days=8 - index),
        )
        db.add(encounter)
        db.flush()
        db.add(Vital(organization_id=org.id, encounter_id=encounter.id, values={"temperature_c": 37.2 + index * 0.1, "pulse_bpm": 76 + index * 2, "spo2_pct": 98, "bp": "118/76", "weight_kg": 62 + index * 3}))
        db.add(Diagnosis(organization_id=org.id, encounter_id=encounter.id, code="R69", description="Self-limiting outpatient condition", is_primary=True, ai_suggested=False))
        prescription = Prescription(
            organization_id=org.id,
            encounter_id=encounter.id,
            status="signed" if signed else "draft",
            notes="Take after food and return if symptoms worsen.",
            signed_at=encounter.signed_at,
            signed_by_user_id=encounter.signed_by_user_id,
        )
        db.add(prescription)
        db.flush()
        db.add(PrescriptionItem(organization_id=org.id, prescription_id=prescription.id, medicine_item_id=medicine.id, medicine_name=medicine.name, dosage="500 mg", frequency="Twice daily", duration="3 days", instructions="After food"))
        order = LabOrder(
            organization_id=org.id,
            encounter_id=encounter.id,
            test_id=tests[index % len(tests)].id,
            status="completed" if signed else "ordered",
            notes="Review with clinical context.",
            signed_at=encounter.signed_at,
            signed_by_user_id=encounter.signed_by_user_id,
        )
        db.add(order)
        db.flush()
        if signed:
            db.add(LabResult(organization_id=org.id, order_id=order.id, values={"haemoglobin": 13.4, "wbc": 7200, "platelets": 245000}, interpretation="Within expected range", reported_at=now - timedelta(days=6 - index), verified_by_user_id=practitioner.user_id))
            db.add(Dispense(organization_id=org.id, location_id=encounter.location_id, prescription_id=prescription.id, items=[{"item_id": medicine.id, "name": medicine.name, "quantity": 6}], dispensed_at=now - timedelta(days=6 - index), dispensed_by_user_id=pharmacist.user_id or owner.id))


def _seed_college(
    db: Session,
    org: Organization,
    owner: User,
    locations: list[Location],
    clients: list[Client],
    staff: dict[str, Employee],
) -> None:
    """Create a connected academic term with operational and financial history."""
    today = date.today()
    academic_year = f"{today.year}-{str(today.year + 1)[-2:]}"
    faculty = staff["faculty"]
    academic_admin = staff["academic-admin"]

    departments: dict[str, CollegeDepartment] = {}
    for code, name, hod, aliases in (
        ("CSE", "Computer Science and Engineering", faculty, ("CSE", "CS")),
        ("ECE", "Electronics and Communication Engineering", faculty, ("ECE",)),
        ("COM", "Commerce", academic_admin, ("COM",)),
    ):
        matches = list(db.execute(select(CollegeDepartment).where(
            CollegeDepartment.organization_id == org.id,
            CollegeDepartment.code.in_(aliases),
        )).scalars())
        row = next((item for item in matches if item.code == code), matches[0] if matches else None)
        if not row:
            row = CollegeDepartment(
                organization_id=org.id,
                location_id=locations[0].id,
                name=name,
                code=code,
                hod_employee_id=hod.id,
                is_active=True,
            )
            db.add(row)
            db.flush()
        else:
            row.name = name
            if not any(item.code == code for item in matches):
                row.code = code
        departments[code] = row

    programs: dict[str, CollegeProgram] = {}
    for code, name, department_code, duration_semesters in (
        ("BSC-CS", "B.Sc. Computer Science", "CSE", 6),
        ("BE-ECE", "B.E. Electronics and Communication", "ECE", 8),
        ("BCOM", "Bachelor of Commerce", "COM", 6),
    ):
        row = db.execute(select(CollegeProgram).where(
            CollegeProgram.organization_id == org.id,
            CollegeProgram.code == code,
        )).scalar_one_or_none()
        if not row:
            row = CollegeProgram(
                organization_id=org.id,
                department_id=departments[department_code].id,
                name=name,
                code=code,
                degree_type="undergraduate",
                duration_semesters=duration_semesters,
                is_active=True,
            )
            db.add(row)
            db.flush()
        else:
            row.department_id = departments[department_code].id
            row.name = name
            row.duration_semesters = duration_semesters
        programs[code] = row

    term = db.execute(select(CollegeTerm).where(
        CollegeTerm.organization_id == org.id,
        CollegeTerm.academic_year == academic_year,
        CollegeTerm.term_number == 3,
    )).scalar_one_or_none()
    if not term:
        term = CollegeTerm(
            organization_id=org.id,
            name="Semester 3",
            academic_year=academic_year,
            term_number=3,
            starts_on=today - timedelta(days=35),
            ends_on=today + timedelta(days=115),
            status="active",
            is_current=True,
        )
        db.add(term)
        db.flush()

    for years_ago in (1, 2):
        start_year = today.year - years_ago
        historical_year = f"{start_year}-{str(start_year + 1)[-2:]}"
        historical_term = db.execute(select(CollegeTerm).where(
            CollegeTerm.organization_id == org.id,
            CollegeTerm.academic_year == historical_year,
            CollegeTerm.term_number == 2,
        )).scalar_one_or_none()
        if not historical_term:
            db.add(CollegeTerm(
                organization_id=org.id,
                name="Even semester",
                academic_year=historical_year,
                term_number=2,
                starts_on=date(start_year + 1, 1, 3),
                ends_on=date(start_year + 1, 5, 31),
                status="closed",
                is_current=False,
            ))

    cohort_layout = {
        today.year: {"BSC-CS": ("A", "B"), "BCOM": ("A",)},
        today.year + 1: {"BSC-CS": ("A", "B"), "BCOM": ("A", "B"), "BE-ECE": ("A",)},
        today.year + 2: {"BSC-CS": ("A", "B"), "BCOM": ("A",), "BE-ECE": ("A", "B")},
    }
    cohort_rows: dict[tuple[str, int, str], CollegeCohort] = {}
    for graduation_year, program_sections in cohort_layout.items():
        for program_code, sections in program_sections.items():
            program = programs[program_code]
            admission_year = graduation_year - ((program.duration_semesters + 1) // 2)
            current_semester = min(
                program.duration_semesters,
                max(1, (today.year - admission_year) * 2 + (1 if today.month >= 7 else 0)),
            )
            for section in sections:
                code = f"{program_code}-{admission_year}-{section}"
                name = f"{program.name} / Class of {graduation_year} / Section {section}"
                row = db.execute(select(CollegeCohort).where(
                    CollegeCohort.organization_id == org.id,
                    CollegeCohort.code == code,
                )).scalar_one_or_none()
                if not row:
                    row = CollegeCohort(
                        organization_id=org.id,
                        program_id=program.id,
                        name=name,
                        code=code,
                        admission_year=admission_year,
                        graduation_year=graduation_year,
                        current_semester=current_semester,
                        section=section,
                        advisor_employee_id=faculty.id,
                        is_active=True,
                    )
                    db.add(row)
                    db.flush()
                else:
                    row.program_id = program.id
                    row.name = name
                    row.admission_year = admission_year
                    row.graduation_year = graduation_year
                    row.current_semester = current_semester
                    row.section = section
                    row.is_active = True
                cohort_rows[(program_code, graduation_year, section)] = row

    cohorts: dict[str, CollegeCohort] = {}
    for program_code in programs:
        preferred = cohort_rows.get((program_code, today.year + 2, "A"))
        if preferred:
            cohorts[program_code] = preferred

    course_specs = (
        ("CS301", "Data Structures", "CSE", "BSC-CS", 4, 0, "09:00:00", "10:00:00", "Lab 2"),
        ("CS302", "Database Systems", "CSE", "BSC-CS", 4, 2, "11:00:00", "12:00:00", "Room 204"),
        ("EC501", "Embedded Systems", "ECE", "BE-ECE", 4, 0, "10:00:00", "11:00:00", "Lab 4"),
        ("EC502", "Digital Communication", "ECE", "BE-ECE", 4, 3, "12:00:00", "13:00:00", "Room 302"),
        ("COM301", "Corporate Accounting", "COM", "BCOM", 4, 1, "10:00:00", "11:00:00", "Room 108"),
        ("COM302", "Business Law", "COM", "BCOM", 3, 3, "13:30:00", "14:30:00", "Room 109"),
    )
    offerings: list[CollegeCourseOffering] = []
    for code, name, department_code, program_code, credits, weekday, starts_at, ends_at, room in course_specs:
        course = db.execute(select(CollegeCourse).where(
            CollegeCourse.organization_id == org.id,
            CollegeCourse.code == code,
        )).scalar_one_or_none()
        if not course:
            course = CollegeCourse(
                organization_id=org.id,
                department_id=departments[department_code].id,
                name=name,
                code=code,
                credits=credits,
                course_type="core",
                is_active=True,
            )
            db.add(course)
            db.flush()
        else:
            course.name = name
            course.department_id = departments[department_code].id
            course.credits = credits
        cohort = cohorts[program_code]
        offering = db.execute(select(CollegeCourseOffering).where(
            CollegeCourseOffering.term_id == term.id,
            CollegeCourseOffering.course_id == course.id,
            CollegeCourseOffering.cohort_id == cohort.id,
        )).scalar_one_or_none()
        if not offering:
            offering = CollegeCourseOffering(
                organization_id=org.id,
                term_id=term.id,
                course_id=course.id,
                cohort_id=cohort.id,
                faculty_employee_id=faculty.id,
                room=room,
                weekly_schedule=[{
                    "weekday": weekday,
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "room": room,
                }],
                status="active",
            )
            db.add(offering)
            db.flush()
        offerings.append(offering)

    student_clients = list(clients[:10])
    for offset in range(COLLEGE_ADDITIONAL_STUDENT_COUNT):
        index = offset + 11
        first_name, gender = COLLEGE_STUDENT_FIRST_NAMES[offset % len(COLLEGE_STUDENT_FIRST_NAMES)]
        last_name = COLLEGE_STUDENT_LAST_NAMES[offset // len(COLLEGE_STUDENT_FIRST_NAMES)]
        client_number = f"COL-STU-{index:04d}"
        client = db.execute(select(Client).where(
            Client.organization_id == org.id,
            Client.client_number == client_number,
        )).scalar_one_or_none()
        if not client:
            client = Client(
                organization_id=org.id,
                home_location_id=locations[0].id,
                client_number=client_number,
                first_name=first_name,
                last_name=last_name,
                phone=f"97740{index:05d}",
                email=f"student.{index:03d}@{org.slug}.example.test",
                address=f"{100 + index}, College Road, Chennai",
                date_of_birth=date(
                    today.year - 18 - (offset % 4),
                    ((offset * 3) % 12) + 1,
                    ((offset * 7) % 27) + 1,
                ),
                gender=gender,
                joined_on=date(today.year - 1, 7, 1) + timedelta(days=offset % 24),
                notes="Showcase student record with connected academic and placement evidence.",
                tags=["college", "demo-student"],
                whatsapp_consent=offset % 5 != 0,
                whatsapp_consent_at=datetime.now(timezone.utc) - timedelta(days=90) if offset % 5 != 0 else None,
                whatsapp_consent_source="admissions" if offset % 5 != 0 else None,
                email_consent=True,
                status="active",
            )
            db.add(client)
            db.flush()
        else:
            client.home_location_id = locations[0].id
        if all(row.id != client.id for row in clients):
            clients.append(client)
        student_clients.append(client)

    cohort_pool = [cohort_rows[key] for key in sorted(cohort_rows, key=lambda item: (item[1], item[0], item[2]))]
    program_code_by_id = {row.id: code for code, row in programs.items()}
    profiles: list[CollegeStudentProfile] = []
    for index, client in enumerate(student_clients, start=1):
        cohort = cohort_pool[(index - 1) % len(cohort_pool)]
        program_code = program_code_by_id[cohort.program_id]
        client.home_location_id = locations[0].id
        profile = db.execute(select(CollegeStudentProfile).where(
            CollegeStudentProfile.client_id == client.id,
        )).scalar_one_or_none()
        if not profile:
            profile = CollegeStudentProfile(
                organization_id=org.id,
                client_id=client.id,
                admission_number=f"COL-{cohort.admission_year}-{index:04d}",
                roll_number=f"{program_code}-{cohort.graduation_year}-{cohort.section}-{index:03d}",
                program_id=programs[program_code].id,
                cohort_id=cohort.id,
                current_semester=cohort.current_semester,
                admitted_on=date(cohort.admission_year, 7, 1) + timedelta(days=(index - 1) % 24),
                status="active",
                guardian={"name": f"Guardian {index}", "phone": f"988403{index:04d}"},
                category="general",
            )
            db.add(profile)
            db.flush()
        else:
            profile.program_id = cohort.program_id
            profile.cohort_id = cohort.id
            profile.current_semester = cohort.current_semester
            profile.admission_number = f"COL-{cohort.admission_year}-{index:04d}"
            profile.roll_number = f"{program_code}-{cohort.graduation_year}-{cohort.section}-{index:03d}"
            profile.admitted_on = date(cohort.admission_year, 7, 1) + timedelta(days=(index - 1) % 24)
        profiles.append(profile)

    profiles_by_cohort: dict[str, list[CollegeStudentProfile]] = {}
    for profile in profiles:
        profiles_by_cohort.setdefault(profile.cohort_id, []).append(profile)
    for offering_index, offering in enumerate(offerings):
        for session_index, days_ago in enumerate((2, 5, 9)):
            held_on = today - timedelta(days=days_ago + offering_index)
            session = db.execute(select(CollegeAttendanceSession).where(
                CollegeAttendanceSession.organization_id == org.id,
                CollegeAttendanceSession.offering_id == offering.id,
                CollegeAttendanceSession.held_on == held_on,
            )).scalar_one_or_none()
            if not session:
                session = CollegeAttendanceSession(
                    organization_id=org.id,
                    offering_id=offering.id,
                    held_on=held_on,
                    starts_at=time(9 + offering_index),
                    ends_at=time(10 + offering_index),
                    topic=f"Unit {session_index + 1} review",
                    status="submitted",
                    recorded_by_user_id=faculty.user_id or owner.id,
                )
                db.add(session)
                db.flush()
            for student_index, profile in enumerate(profiles_by_cohort.get(offering.cohort_id, [])):
                record = db.execute(select(CollegeAttendanceRecord).where(
                    CollegeAttendanceRecord.session_id == session.id,
                    CollegeAttendanceRecord.student_profile_id == profile.id,
                )).scalar_one_or_none()
                if not record:
                    status_value = "absent" if (student_index + session_index + offering_index) % 9 == 0 else "late" if (student_index + session_index) % 7 == 0 else "present"
                    db.add(CollegeAttendanceRecord(
                        organization_id=org.id,
                        session_id=session.id,
                        student_profile_id=profile.id,
                        status=status_value,
                    ))

    _seed_college_assessment_patterns(
        db, org, owner, faculty, term, programs, offerings, profiles_by_cohort,
    )

    fee_plans: dict[str, CollegeFeePlan] = {}
    for program_code, amount in (("BSC-CS", 4500000), ("BE-ECE", 4800000), ("BCOM", 3800000)):
        name = f"Semester 3 tuition / {program_code}"
        plan = db.execute(select(CollegeFeePlan).where(
            CollegeFeePlan.organization_id == org.id,
            CollegeFeePlan.name == name,
        )).scalar_one_or_none()
        if not plan:
            plan = CollegeFeePlan(
                organization_id=org.id,
                name=name,
                program_id=programs[program_code].id,
                cohort_id=cohorts[program_code].id,
                term_id=term.id,
                amount_paise=amount,
                due_on=today + timedelta(days=12),
                line_items=[
                    {"name": "Tuition fee", "amount_paise": amount - 500000},
                    {"name": "Laboratory and academic services", "amount_paise": 500000},
                ],
                is_active=True,
            )
            db.add(plan)
            db.flush()
        fee_plans[program_code] = plan

    client_by_id = {row.id: row for row in student_clients}
    for index, profile in enumerate(profiles, start=1):
        program_code = program_code_by_id[profile.program_id]
        plan = fee_plans[program_code]
        client = client_by_id[profile.client_id]
        payment_bucket = ((index - 1) % 10) + 1
        concession = 200000 if payment_bucket == 3 else 0
        total = int(plan.amount_paise) - concession
        paid = total if payment_bucket in {1, 2, 7} else total // 2 if payment_bucket in {3, 8} else 0
        invoice_status = "paid" if paid == total else "partially_paid" if paid else "issued"
        invoice_number = f"COL-DEMO-{index:04d}"
        invoice_key = f"demo-college-fee-{org.slug}-{index}"
        payment_key = f"demo-college-payment-{org.slug}-{index}"
        payment_reference = f"COLLEGE-DEMO-{index:04d}"

        existing_fee = db.execute(select(CollegeStudentFee).where(
            CollegeStudentFee.student_profile_id == profile.id,
            CollegeStudentFee.fee_plan_id == plan.id,
        )).scalar_one_or_none()
        invoice = db.get(SaleInvoice, existing_fee.invoice_id) if existing_fee and existing_fee.invoice_id else None
        if invoice and invoice.organization_id != org.id:
            invoice = None
        if not invoice:
            invoice = db.execute(select(SaleInvoice).where(
                SaleInvoice.organization_id == org.id,
                SaleInvoice.idempotency_key == invoice_key,
            )).scalar_one_or_none()
        if not invoice:
            invoice = db.execute(select(SaleInvoice).where(
                SaleInvoice.organization_id == org.id,
                SaleInvoice.invoice_number == invoice_number,
            )).scalar_one_or_none()
        if not invoice:
            invoice = SaleInvoice(
                organization_id=org.id,
                location_id=client.home_location_id or locations[0].id,
                client_id=client.id,
                employee_id=academic_admin.id,
                invoice_number=invoice_number,
                status=invoice_status,
                subtotal_paise=plan.amount_paise,
                discount_paise=concession,
                total_paise=total,
                paid_paise=paid,
                tax_snapshot={"source": "college_fee", "tax_exempt": True, "fee_plan_id": plan.id},
                notes=plan.name,
                idempotency_key=invoice_key,
                issued_at=datetime.now(timezone.utc) - timedelta(days=((index - 1) % 28) + 1),
            )
            db.add(invoice)
            db.flush()
        else:
            invoice.location_id = client.home_location_id or locations[0].id

        existing_line = db.execute(select(SaleLine).where(
            SaleLine.organization_id == org.id,
            SaleLine.invoice_id == invoice.id,
        ).order_by(SaleLine.display_order, SaleLine.id)).scalars().first()
        if not existing_line:
            db.add(SaleLine(
                organization_id=org.id,
                invoice_id=invoice.id,
                display_order=0,
                item_name=plan.name,
                sku=f"COL-FEE-{program_code}",
                quantity_milli=1000,
                unit_price_paise=plan.amount_paise,
                discount_paise=concession,
                tax_rate_bps=0,
                tax_paise=0,
                total_paise=total,
            ))
        if paid:
            existing_payment = db.execute(select(SalePayment).where(
                SalePayment.organization_id == org.id,
                SalePayment.idempotency_key == payment_key,
            )).scalar_one_or_none()
            if not existing_payment:
                existing_payment = db.execute(select(SalePayment).where(
                    SalePayment.organization_id == org.id,
                    SalePayment.invoice_id == invoice.id,
                    SalePayment.reference == payment_reference,
                )).scalars().first()
            if not existing_payment:
                db.add(SalePayment(
                    organization_id=org.id,
                    invoice_id=invoice.id,
                    amount_paise=paid,
                    method="upi",
                    reference=payment_reference,
                    status="captured",
                    idempotency_key=payment_key,
                    received_by_user_id=owner.id,
                ))
        if existing_fee:
            existing_fee.invoice_id = invoice.id
        else:
            db.add(CollegeStudentFee(
                organization_id=org.id,
                student_profile_id=profile.id,
                fee_plan_id=plan.id,
                invoice_id=invoice.id,
                amount_paise=plan.amount_paise,
                concession_paise=concession,
                status=invoice_status,
            ))

    _seed_college_placement(db, org, owner, profiles, programs, cohorts, term)


def _seed_college_assessment_patterns(
    db: Session,
    org: Organization,
    owner: User,
    faculty: Employee,
    term: CollegeTerm,
    programs: dict[str, CollegeProgram],
    offerings: list[CollegeCourseOffering],
    profiles_by_cohort: dict[str, list[CollegeStudentProfile]],
) -> None:
    """Showcase institution-defined patterns without creating runtime assumptions."""
    from app.services.college_assessments import (
        assignment_scope_key, build_scheme_snapshot, component_payload,
        freeze_scheme, recalculate_assessment_score,
    )

    def pattern(code: str, name: str, domain: str, method: str, config: dict, definitions: list[dict]):
        scheme = db.scalar(select(CollegeAssessmentScheme).where(
            CollegeAssessmentScheme.organization_id == org.id,
            CollegeAssessmentScheme.code == code,
            CollegeAssessmentScheme.version_number == 1,
        ))
        if not scheme:
            scheme = CollegeAssessmentScheme(
                organization_id=org.id,
                code=code,
                name=name,
                domain=domain,
                status="active",
                final_score_max=100,
                calculation_method=method,
                calculation_config=config,
                description="Demo configuration authored by the institution, not an Edvatiq product default.",
            )
            db.add(scheme)
            db.flush()
            db.add_all([
                CollegeAssessmentComponent(
                    organization_id=org.id,
                    scheme_id=scheme.id,
                    display_order=index,
                    **definition,
                )
                for index, definition in enumerate(definitions, start=1)
            ])
            db.flush()
        components = list(db.scalars(select(CollegeAssessmentComponent).where(
            CollegeAssessmentComponent.organization_id == org.id,
            CollegeAssessmentComponent.scheme_id == scheme.id,
        ).order_by(CollegeAssessmentComponent.display_order)))
        return scheme, components

    def assign(scheme: CollegeAssessmentScheme, *, program_id: str | None = None):
        scope_key = assignment_scope_key(scheme.domain, program_id=program_id)
        row = db.scalar(select(CollegeAssessmentSchemeAssignment).where(
            CollegeAssessmentSchemeAssignment.organization_id == org.id,
            CollegeAssessmentSchemeAssignment.scope_key == scope_key,
        ))
        if not row:
            db.add(CollegeAssessmentSchemeAssignment(
                organization_id=org.id,
                scheme_id=scheme.id,
                program_id=program_id,
                scope_key=scope_key,
            ))
        elif row.scheme_id != scheme.id:
            row.scheme_id = scheme.id
            row.version += 1

    academic, academic_components = pattern(
        "DEMO_ACADEMIC_PATTERN",
        "Continuous assessment pattern",
        "academic",
        "best_n",
        {"best_n": 2, "minimum_components": 2},
        [
            {"name": "Continuous assessment 1", "code": "CA_1", "component_type": "internal", "metric_type": "number", "max_marks": 50, "weightage_bps": 3334, "pass_marks": 20, "is_required": True, "aggregation_group": None, "settings": {}},
            {"name": "Continuous assessment 2", "code": "CA_2", "component_type": "internal", "metric_type": "number", "max_marks": 50, "weightage_bps": 3333, "pass_marks": 20, "is_required": True, "aggregation_group": None, "settings": {}},
            {"name": "Continuous assessment 3", "code": "CA_3", "component_type": "internal", "metric_type": "number", "max_marks": 50, "weightage_bps": 3333, "pass_marks": 20, "is_required": False, "aggregation_group": None, "settings": {}},
        ],
    )
    commerce, commerce_components = pattern(
        "DEMO_COMMERCE_PATTERN",
        "Commerce internal pattern",
        "academic",
        "average",
        {"minimum_components": 2},
        [
            {"name": "Internal test 1", "code": "IT_1", "component_type": "internal", "metric_type": "number", "max_marks": 40, "weightage_bps": 5000, "pass_marks": 16, "is_required": True, "aggregation_group": None, "settings": {}},
            {"name": "Internal test 2", "code": "IT_2", "component_type": "internal", "metric_type": "number", "max_marks": 40, "weightage_bps": 5000, "pass_marks": 16, "is_required": True, "aggregation_group": None, "settings": {}},
        ],
    )
    coding, coding_components = pattern(
        "DEMO_CODING_PATTERN",
        "Placement coding diagnostic",
        "coding",
        "weighted_sum",
        {"minimum_components": 3},
        [
            {"name": "Coding score", "code": "CODING_SCORE", "component_type": "coding", "metric_type": "number", "max_marks": 100, "weightage_bps": 5000, "pass_marks": 45, "is_required": True, "aggregation_group": None, "settings": {}},
            {"name": "SQL", "code": "SQL", "component_type": "coding", "metric_type": "number", "max_marks": 50, "weightage_bps": 2500, "pass_marks": 20, "is_required": True, "aggregation_group": None, "settings": {}},
            {"name": "Test cases passed", "code": "TEST_CASES", "component_type": "coding", "metric_type": "count", "max_marks": 20, "weightage_bps": 2500, "pass_marks": 8, "is_required": True, "aggregation_group": None, "settings": {}},
        ],
    )
    assign(academic)
    assign(commerce, program_id=programs["BCOM"].id)
    assign(coding)
    db.flush()

    cohort_by_id = {
        row.id: row for row in db.scalars(select(CollegeCohort).where(
            CollegeCohort.organization_id == org.id,
            CollegeCohort.id.in_({item.cohort_id for item in offerings}),
        ))
    }
    academic_targets = [item for item in offerings if cohort_by_id[item.cohort_id].program_id != programs["BCOM"].id]
    commerce_targets = [item for item in offerings if cohort_by_id[item.cohort_id].program_id == programs["BCOM"].id]
    scored_pairs: list[tuple[CollegeAssessment, str]] = []

    def academic_cycles(scheme, components, targets, code_prefix):
        snapshot = build_scheme_snapshot(scheme, components)
        for component_index, component in enumerate(components):
            cycle_code = f"{code_prefix}_{term.academic_year}_{component.code}".replace("-", "_")
            cycle = db.scalar(select(CollegeExamCycle).where(
                CollegeExamCycle.organization_id == org.id,
                CollegeExamCycle.code == cycle_code,
            ))
            if not cycle:
                cycle = CollegeExamCycle(
                    organization_id=org.id,
                    scheme_id=scheme.id,
                    scheme_component_id=component.id,
                    term_id=term.id,
                    name=component.name,
                    code=cycle_code,
                    domain="academic",
                    held_on=date.today() - timedelta(days=max(1, 24 - component_index * 8)),
                    due_on=date.today() - timedelta(days=max(0, 23 - component_index * 8)),
                    status="published",
                    target_offering_ids=[item.id for item in targets],
                    scheme_snapshot=snapshot,
                )
                db.add(cycle)
                db.flush()
            for offering_index, offering in enumerate(targets):
                assessment = db.scalar(select(CollegeAssessment).where(
                    CollegeAssessment.organization_id == org.id,
                    CollegeAssessment.exam_cycle_id == cycle.id,
                    CollegeAssessment.offering_id == offering.id,
                ))
                if not assessment:
                    assessment = CollegeAssessment(
                        organization_id=org.id,
                        offering_id=offering.id,
                        cohort_id=offering.cohort_id,
                        exam_cycle_id=cycle.id,
                        scheme_id=scheme.id,
                        scheme_component_id=component.id,
                        title=component.name,
                        assessment_type=component.component_type,
                        max_marks=component.max_marks,
                        weightage_bps=component.weightage_bps,
                        due_on=cycle.due_on,
                        status="published",
                        published_at=datetime.now(timezone.utc),
                        metric_schema=[component_payload(component)],
                    )
                    db.add(assessment)
                    db.flush()
                for student_index, profile in enumerate(profiles_by_cohort.get(offering.cohort_id, [])):
                    score = db.scalar(select(CollegeAssessmentScore).where(
                        CollegeAssessmentScore.assessment_id == assessment.id,
                        CollegeAssessmentScore.student_profile_id == profile.id,
                    ))
                    if not score:
                        maximum = int(component.max_marks or 100)
                        marks = max(0, min(maximum, int(maximum * 0.55) + ((student_index * 3 + offering_index + component_index * 5) % max(1, int(maximum * 0.4)))))
                        score = CollegeAssessmentScore(
                            organization_id=org.id,
                            assessment_id=assessment.id,
                            student_profile_id=profile.id,
                            marks_awarded=marks,
                            metrics={component.code: marks},
                            grade="A" if marks >= maximum * 0.8 else "B",
                            graded_by_user_id=faculty.user_id or owner.id,
                        )
                        db.add(score)
                    scored_pairs.append((assessment, profile.id))
        freeze_scheme(scheme)

    academic_cycles(academic, academic_components, academic_targets, "DEMO_CA")
    academic_cycles(commerce, commerce_components, commerce_targets, "DEMO_COM")

    coding_snapshot = build_scheme_snapshot(coding, coding_components)
    coding_cycle_code = f"DEMO_CODING_{term.academic_year}".replace("-", "_")
    coding_cycle = db.scalar(select(CollegeExamCycle).where(
        CollegeExamCycle.organization_id == org.id,
        CollegeExamCycle.code == coding_cycle_code,
    ))
    if not coding_cycle:
        coding_cycle = CollegeExamCycle(
            organization_id=org.id,
            scheme_id=coding.id,
            term_id=term.id,
            name="Placement coding diagnostic",
            code=coding_cycle_code,
            domain="coding",
            held_on=date.today() - timedelta(days=10),
            status="published",
            target_cohort_ids=list(profiles_by_cohort),
            scheme_snapshot=coding_snapshot,
        )
        db.add(coding_cycle)
        db.flush()
    for cohort_index, (cohort_id, profiles) in enumerate(profiles_by_cohort.items()):
        assessment = db.scalar(select(CollegeAssessment).where(
            CollegeAssessment.organization_id == org.id,
            CollegeAssessment.exam_cycle_id == coding_cycle.id,
            CollegeAssessment.cohort_id == cohort_id,
        ))
        if not assessment:
            assessment = CollegeAssessment(
                organization_id=org.id,
                cohort_id=cohort_id,
                exam_cycle_id=coding_cycle.id,
                scheme_id=coding.id,
                title=coding_cycle.name,
                assessment_type="coding",
                max_marks=100,
                weightage_bps=10000,
                status="published",
                published_at=datetime.now(timezone.utc),
                metric_schema=[component_payload(item) for item in coding_components],
            )
            db.add(assessment)
            db.flush()
        for student_index, profile in enumerate(profiles):
            score = db.scalar(select(CollegeAssessmentScore).where(
                CollegeAssessmentScore.assessment_id == assessment.id,
                CollegeAssessmentScore.student_profile_id == profile.id,
            ))
            if not score:
                metrics = {
                    "CODING_SCORE": 42 + ((student_index * 7 + cohort_index) % 55),
                    "SQL": 18 + ((student_index * 5 + cohort_index) % 31),
                    "TEST_CASES": 6 + ((student_index * 2 + cohort_index) % 15),
                }
                score = CollegeAssessmentScore(
                    organization_id=org.id,
                    assessment_id=assessment.id,
                    student_profile_id=profile.id,
                    metrics=metrics,
                    graded_by_user_id=faculty.user_id or owner.id,
                )
                db.add(score)
            scored_pairs.append((assessment, profile.id))
    freeze_scheme(coding)
    db.flush()
    for assessment, student_id in scored_pairs:
        recalculate_assessment_score(db, assessment, student_id)

    mapping = db.scalar(select(CollegeAssessmentReadinessMapping).where(
        CollegeAssessmentReadinessMapping.organization_id == org.id,
        CollegeAssessmentReadinessMapping.scheme_id == coding.id,
        CollegeAssessmentReadinessMapping.metric_code == "__CALCULATED__",
    ))
    if not mapping:
        db.add(CollegeAssessmentReadinessMapping(
            organization_id=org.id,
            scheme_id=coding.id,
            metric_code="__CALCULATED__",
            factor_key="coding",
            is_active=True,
            mapped_by_user_id=owner.id,
        ))


def _seed_college_placement(
    db: Session,
    org: Organization,
    owner: User,
    profiles: list[CollegeStudentProfile],
    programs: dict[str, CollegeProgram],
    cohorts: dict[str, CollegeCohort],
    term: CollegeTerm,
) -> None:
    """Seed varied, traceable placement evidence for the College showcase."""
    from app.services.college_placement import (
        ensure_default_pipeline, recompute_readiness,
    )

    now = datetime.now(timezone.utc)
    today = now.date()
    flag = db.execute(select(FeatureFlag).where(
        FeatureFlag.organization_id == org.id,
        FeatureFlag.flag == "college.placement_v1",
    )).scalar_one_or_none()
    if not flag:
        db.add(FeatureFlag(
            organization_id=org.id,
            flag="college.placement_v1",
            enabled=True,
            meta={"mode": "enabled", "version": 1},
        ))
    data_exchange_flag = db.execute(select(FeatureFlag).where(
        FeatureFlag.organization_id == org.id,
        FeatureFlag.flag == "college.data_exchange_v1",
    )).scalar_one_or_none()
    if not data_exchange_flag:
        db.add(FeatureFlag(
            organization_id=org.id,
            flag="college.data_exchange_v1",
            enabled=True,
            meta={"mode": "enabled", "version": 1},
        ))

    stages = ensure_default_pipeline(db, org.id)
    stage_by_slug = {row.slug: row for row in stages}
    profiles_by_id = {row.id: row for row in profiles}
    profile_ids = list(profiles_by_id)
    cohort_by_id = {
        row.id: row for row in db.execute(select(CollegeCohort).where(
            CollegeCohort.organization_id == org.id,
            CollegeCohort.id.in_({profile.cohort_id for profile in profiles}),
        )).scalars()
    }
    graduation_years = sorted({row.graduation_year for row in cohort_by_id.values()})
    technical_program_ids = {programs[code].id for code in ("BSC-CS", "BE-ECE") if code in programs}
    existing_results = {
        (row.student_profile_id, row.semester, row.source_key)
        for row in db.execute(select(CollegeTermResult).where(
            CollegeTermResult.organization_id == org.id,
            CollegeTermResult.student_profile_id.in_(profile_ids),
        )).scalars()
    }
    existing_attendance = {
        (row.student_profile_id, row.as_of, row.scope_key, row.source_key)
        for row in db.execute(select(CollegeAttendanceSnapshot).where(
            CollegeAttendanceSnapshot.organization_id == org.id,
            CollegeAttendanceSnapshot.student_profile_id.in_(profile_ids),
        )).scalars()
    }
    career_by_student = {
        row.student_profile_id: row for row in db.execute(select(CollegeCareerProfile).where(
            CollegeCareerProfile.organization_id == org.id,
            CollegeCareerProfile.student_profile_id.in_(profile_ids),
        )).scalars()
    }
    evidence_students = set(db.execute(select(CollegeCareerEvidence.student_profile_id).where(
        CollegeCareerEvidence.organization_id == org.id,
        CollegeCareerEvidence.student_profile_id.in_(profile_ids),
    ).distinct()).scalars())
    assessment_students = set(db.execute(select(CollegePlacementAssessment.student_profile_id).where(
        CollegePlacementAssessment.organization_id == org.id,
        CollegePlacementAssessment.student_profile_id.in_(profile_ids),
    ).distinct()).scalars())
    activity_students = set(db.execute(select(CollegePreparationActivity.student_profile_id).where(
        CollegePreparationActivity.organization_id == org.id,
        CollegePreparationActivity.student_profile_id.in_(profile_ids),
    ).distinct()).scalars())
    coding_accounts = {
        row.student_profile_id: row for row in db.execute(select(CollegeCodingAccount).where(
            CollegeCodingAccount.organization_id == org.id,
            CollegeCodingAccount.student_profile_id.in_(profile_ids),
            CollegeCodingAccount.platform == "leetcode",
        )).scalars()
    }
    coding_students = set(db.execute(select(CollegeCodingSnapshot.student_profile_id).where(
        CollegeCodingSnapshot.organization_id == org.id,
        CollegeCodingSnapshot.student_profile_id.in_(profile_ids),
    ).distinct()).scalars())

    for index, profile in enumerate(profiles, start=1):
        cohort = cohort_by_id[profile.cohort_id]
        for semester in range(1, profile.current_semester + 1):
            if (profile.id, semester, "demo") not in existing_results:
                base_cgpa = 6.35 + ((index * 17) % 330) / 100
                sgpa = min(9.95, max(5.2, base_cgpa - 0.28 + semester * 0.14))
                active_backlogs = 2 if index % 19 == 0 else 1 if index % 11 == 0 else 0
                db.add(CollegeTermResult(
                    organization_id=org.id,
                    student_profile_id=profile.id,
                    term_id=term.id if semester == profile.current_semester else None,
                    semester=semester,
                    sgpa=round(sgpa, 2),
                    cgpa=round((base_cgpa + sgpa) / 2, 2),
                    credits_earned=semester * 22 - active_backlogs * 3,
                    total_backlogs=active_backlogs + (1 if semester < 3 and index % 13 == 0 else 0),
                    active_backlogs=active_backlogs,
                    result_status="published",
                    published_on=today - timedelta(days=(profile.current_semester - semester) * 155 + 24),
                    source_type="demo",
                    source_key="demo",
                ))

        for month_offset in (90, 60, 30, 0):
            as_of = today - timedelta(days=month_offset)
            if (profile.id, as_of, "overall", "demo") not in existing_attendance:
                percent = max(58, min(98, 69 + ((index * 11 + month_offset) % 28) + (90 - month_offset) // 30))
                classes_held = 96 + (90 - month_offset) // 3
                db.add(CollegeAttendanceSnapshot(
                    organization_id=org.id,
                    student_profile_id=profile.id,
                    term_id=term.id,
                    scope_key="overall",
                    classes_held=classes_held,
                    classes_attended=round(classes_held * percent / 100),
                    attendance_percent=percent,
                    as_of=as_of,
                    source_type="demo",
                    source_key="demo",
                ))

        career = career_by_student.get(profile.id)
        if not career:
            has_resume = index % 7 != 0
            career = CollegeCareerProfile(
                organization_id=org.id,
                student_profile_id=profile.id,
                participation_status="not_participating" if index % 23 == 0 else "participating",
                graduation_year=cohort.graduation_year,
                preferred_roles=["Software Engineer", "Data Analyst"] if profile.program_id == programs["BSC-CS"].id else ["Embedded Engineer", "Systems Engineer"] if profile.program_id == programs["BE-ECE"].id else ["Financial Analyst", "Operations Associate"],
                preferred_locations=["Chennai", "Bengaluru", "Coimbatore"],
                linkedin_url=f"https://www.linkedin.com/in/crescent-student-{index:03d}" if index % 5 else None,
                github_url=f"https://github.com/crescent-student-{index:03d}" if profile.program_id == programs["BSC-CS"].id and index % 6 else None,
                resume_status="reviewed" if has_resume else "missing",
                profile_summary="Placement-focused student profile reviewed by the demo placement cell." if has_resume else None,
                placement_status="seeking",
            )
            db.add(career)
        else:
            career.graduation_year = cohort.graduation_year
        career_by_student[profile.id] = career

        if profile.id not in evidence_students:
            skill_pool = ["Python", "SQL", "Data Structures", "Communication"] if profile.program_id == programs["BSC-CS"].id else ["Embedded C", "Digital Systems", "Python", "Communication"] if profile.program_id == programs["BE-ECE"].id else ["Financial Accounting", "Excel", "Business Analysis", "Communication"]
            for skill_index, title in enumerate(skill_pool[:2 + index % 3]):
                db.add(CollegeCareerEvidence(
                    organization_id=org.id,
                    student_profile_id=profile.id,
                    evidence_type="skill",
                    title=title,
                    proficiency=("advanced", "intermediate", "beginner")[(index + skill_index) % 3],
                    is_verified=index % 8 != 0,
                    verified_by_user_id=owner.id if index % 8 != 0 else None,
                    verified_at=now - timedelta(days=12) if index % 8 != 0 else None,
                    source_type="demo",
                ))
            if index % 4 != 0:
                db.add(CollegeCareerEvidence(
                    organization_id=org.id,
                    student_profile_id=profile.id,
                    evidence_type="project",
                    title="Campus placement portfolio project",
                    description="A reviewed project demonstrating applied academic and team skills.",
                    evidence_url=f"https://example.test/projects/crescent-{index:03d}",
                    is_verified=index % 9 != 0,
                    verified_by_user_id=owner.id if index % 9 != 0 else None,
                    verified_at=now - timedelta(days=8) if index % 9 != 0 else None,
                    source_type="demo",
                ))
            if index % 3 == 0:
                db.add(CollegeCareerEvidence(
                    organization_id=org.id,
                    student_profile_id=profile.id,
                    evidence_type="certification",
                    title="Career readiness foundation",
                    issuer="Crescent Placement Cell",
                    completed_on=today - timedelta(days=20 + index % 15),
                    is_verified=True,
                    verified_by_user_id=owner.id,
                    verified_at=now - timedelta(days=18),
                    source_type="demo",
                ))

        if profile.id not in assessment_students:
            for kind, base in (("aptitude", 58), ("technical", 54), ("communication", 62)):
                db.add(CollegePlacementAssessment(
                    organization_id=org.id,
                    student_profile_id=profile.id,
                    assessment_type=kind,
                    title=f"Placement {kind} diagnostic",
                    score_percent=min(96, base + (index * (5 if kind == "aptitude" else 7)) % 35),
                    assessed_on=today - timedelta(days=14 + index % 20),
                    provider="Crescent Placement Cell",
                    source_type="demo",
                ))
        if profile.id not in activity_students:
            for activity_index, title in enumerate(("Aptitude practice lab", "Mock interview")):
                if activity_index == 1 and index % 4 == 0:
                    continue
                db.add(CollegePreparationActivity(
                    organization_id=org.id,
                    student_profile_id=profile.id,
                    activity_type="practice" if activity_index == 0 else "mock_interview",
                    title=title,
                    status="completed",
                    occurred_on=today - timedelta(days=5 + index % 18 + activity_index * 7),
                    duration_minutes=60,
                    outcome_score=55 + (index * 9 + activity_index * 7) % 40,
                ))

        if profile.program_id in technical_program_ids and index % 6 != 0:
            account = coding_accounts.get(profile.id)
            if not account:
                account = CollegeCodingAccount(
                    id=str(uuid.uuid4()),
                    organization_id=org.id,
                    student_profile_id=profile.id,
                    platform="leetcode",
                    username=f"crescent_student_{index:03d}",
                    verification_status="verified",
                    consent_status="granted",
                    sync_status="current",
                    last_synced_at=now - timedelta(hours=index % 20),
                    last_success_at=now - timedelta(hours=index % 20),
                    is_active=True,
                )
                db.add(account)
                coding_accounts[profile.id] = account
            if profile.id not in coding_students:
                base_total = 22 + (index * 13) % 240
                for days_ago, growth in ((90, 0), (30, 28 + index % 19), (0, 57 + index % 31)):
                    total = base_total + growth
                    hard = max(0, total // 18 - 1)
                    medium = total // 3
                    easy = total - medium - hard
                    db.add(CollegeCodingSnapshot(
                        organization_id=org.id,
                        coding_account_id=account.id,
                        student_profile_id=profile.id,
                        captured_at=now - timedelta(days=days_ago, minutes=index),
                        easy_solved=easy,
                        medium_solved=medium,
                        hard_solved=hard,
                        total_solved=total,
                        contest_rating=1320 + (index * 23) % 720,
                        contest_rank=180000 - index * 590,
                        global_rank=420000 - index * 1270,
                        languages=[{"language": "Python3", "solved": round(total * 0.7)}, {"language": "C++", "solved": round(total * 0.3)}],
                        source_type="demo",
                        raw_metrics={"demo": True},
                    ))

    db.flush()
    if not db.execute(select(CollegeReadinessSnapshot.id).where(
        CollegeReadinessSnapshot.organization_id == org.id,
    ).limit(1)).first():
        recompute_readiness(db, org.id, [row.id for row in profiles], created_by_user_id=owner.id, calculated_at=now - timedelta(days=90))
        recompute_readiness(db, org.id, [row.id for row in profiles], created_by_user_id=owner.id, calculated_at=now - timedelta(days=30))
        recompute_readiness(db, org.id, [row.id for row in profiles], created_by_user_id=owner.id, calculated_at=now)

    company_specs = (
        ("Freshworks", "SaaS"), ("Zoho", "SaaS"), ("TCS", "Technology services"),
        ("Cognizant", "Technology services"), ("Deloitte", "Consulting"),
        ("HDFC Bank", "Banking"), ("Chargebee", "SaaS"), ("TVS Supply Chain", "Logistics"),
    )
    existing_companies = {
        row.name: row for row in db.execute(select(CollegePlacementCompany).where(
            CollegePlacementCompany.organization_id == org.id,
        )).scalars()
    }
    companies: list[CollegePlacementCompany] = []
    for company_index, (name, industry) in enumerate(company_specs):
        company = existing_companies.get(name)
        if not company:
            company = CollegePlacementCompany(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                name=name,
                industry=industry,
                website=f"https://{name.lower().replace(' ', '')}.example.test",
                contact_name=f"Campus Partner {company_index + 1}",
                contact_email=f"campus{company_index + 1}@recruiter.example.test",
                is_active=True,
            )
            db.add(company)
        companies.append(company)

    opportunity_specs = (
        ("Graduate Software Engineer", 0, "active", [programs["BSC-CS"].id, programs["BE-ECE"].id], 7.0, 0, 75, 100),
        ("Data Analyst Trainee", 1, "active", [programs["BSC-CS"].id, programs["BE-ECE"].id, programs["BCOM"].id], 6.5, 1, 70, None),
        ("Technology Associate", 2, "published", [programs["BSC-CS"].id, programs["BE-ECE"].id], 6.0, 1, 70, 75),
        ("Business Operations Analyst", 4, "active", [programs["BCOM"].id], 7.0, 0, 75, None),
        ("Banking Operations Trainee", 5, "published", [programs["BCOM"].id], 6.0, 1, 70, None),
        ("Product Support Intern", 6, "closed", [programs["BSC-CS"].id, programs["BE-ECE"].id, programs["BCOM"].id], 6.0, 2, 65, None),
    )
    existing_opportunities = {
        (row.company_id, row.title): row
        for row in db.execute(select(CollegePlacementOpportunity).where(
            CollegePlacementOpportunity.organization_id == org.id,
        )).scalars()
    }
    opportunities: list[CollegePlacementOpportunity] = []
    for opportunity_index, (title, company_index, opportunity_status, program_ids, min_cgpa, max_backlogs, min_attendance, min_solved) in enumerate(opportunity_specs):
        opportunity = existing_opportunities.get((companies[company_index].id, title))
        is_internship = "Intern" in title
        if not opportunity:
            rules = {
                "program_ids": program_ids,
                "graduation_years": graduation_years,
                "minimum_cgpa": min_cgpa,
                "maximum_active_backlogs": max_backlogs,
                "minimum_attendance": min_attendance,
            }
            if min_solved is not None:
                rules["minimum_solved"] = min_solved
            if is_internship:
                rules["require_fee_clearance"] = True
            opportunity = CollegePlacementOpportunity(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                company_id=companies[company_index].id,
                title=title,
                opportunity_type="internship" if is_internship else "campus_drive",
                status=opportunity_status,
                opens_at=now - timedelta(days=18 - opportunity_index),
                deadline_at=now + timedelta(days=7 + opportunity_index * 3) if opportunity_status != "closed" else now - timedelta(days=9),
                drive_at=now + timedelta(days=18 + opportunity_index * 4) if opportunity_status != "closed" else now - timedelta(days=2),
                work_location=("Chennai", "Bengaluru", "Hyderabad")[opportunity_index % 3],
                employment_type="full_time" if "Intern" not in title else "internship",
                package_min_paise=(350000 + opportunity_index * 40000) * 100,
                package_max_paise=(650000 + opportunity_index * 50000) * 100,
                role_description="Campus opportunity managed by the placement cell with evidence-based eligibility review.",
                eligibility_rules=rules,
                rounds=[{"name": "Assessment"}, {"name": "Technical interview"}, {"name": "HR interview"}],
                owner_user_id=owner.id,
            )
            db.add(opportunity)
        else:
            opportunity.eligibility_rules = {
                **(opportunity.eligibility_rules or {}),
                "program_ids": program_ids,
                "graduation_years": graduation_years,
                **({"require_fee_clearance": True} if is_internship else {}),
            }
        opportunities.append(opportunity)

    # Applications use scalar foreign keys, so persist new companies and drives
    # before flushing individual application/history chains.
    db.flush()
    stage_cycle = ("eligible", "invited", "applied", "assessment", "technical-interview", "hr-interview", "selected", "offered", "joined", "rejected")
    existing_applications = {
        (row.opportunity_id, row.student_profile_id): row
        for row in db.execute(select(CollegePlacementApplication).where(
            CollegePlacementApplication.organization_id == org.id,
        )).scalars()
    }
    for student_index, profile in enumerate(profiles, start=1):
        for application_offset in range(2 if student_index % 4 else 3):
            opportunity = opportunities[(student_index + application_offset * 2) % len(opportunities)]
            stage_slug = stage_cycle[(student_index * 3 + application_offset * 2) % len(stage_cycle)]
            stage = stage_by_slug[stage_slug]
            eligibility_status = "needs_review" if student_index % 9 == 0 else "ineligible" if student_index % 7 == 0 else "eligible"
            payment_bucket = ((student_index - 1) % 10) + 1
            fee_clearance_status = "cleared" if payment_bucket in {1, 2, 7} else "pending"
            if opportunity.opportunity_type == "internship" and fee_clearance_status != "cleared":
                eligibility_status = "ineligible"
            checks = [
                {"rule": "minimum_cgpa", "actual": 6.5 + (student_index * 17 % 330) / 100, "expected": opportunity.eligibility_rules.get("minimum_cgpa"), "passes": eligibility_status != "ineligible"},
                {"rule": "evidence_coverage", "actual": None if eligibility_status == "needs_review" else "available", "expected": "available", "passes": None if eligibility_status == "needs_review" else True},
            ]
            if opportunity.opportunity_type == "internship":
                checks.append({
                    "rule": "fee_clearance",
                    "actual": fee_clearance_status,
                    "expected": "cleared",
                    "passes": fee_clearance_status == "cleared",
                })
            eligibility = {
                "status": eligibility_status,
                "evaluated_at": (now - timedelta(days=10)).isoformat(),
                "checks": checks,
            }
            existing_application = existing_applications.get((opportunity.id, profile.id))
            if existing_application:
                existing_application.eligibility_status = eligibility_status
                existing_application.eligibility_evidence = eligibility
                existing_application.eligibility_evaluated_at = now - timedelta(days=10)
                continue
            application = CollegePlacementApplication(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                opportunity_id=opportunity.id,
                student_profile_id=profile.id,
                current_stage_id=stage.id,
                eligibility_status=eligibility["status"],
                eligibility_evidence=eligibility,
                eligibility_evaluated_at=now - timedelta(days=10),
                applied_at=now - timedelta(days=8 + application_offset) if stage.display_order >= stage_by_slug["applied"].display_order else None,
                outcome=stage.stage_type if stage.stage_type != "active" else None,
                notes="Demo application with complete pipeline evidence.",
                version=1,
            )
            db.add(application)
            db.flush([application])
            db.add(CollegeApplicationStageEvent(
                organization_id=org.id,
                application_id=application.id,
                to_stage_id=stage.id,
                changed_by_user_id=owner.id,
                reason="Demo pipeline progression",
                occurred_at=now - timedelta(days=max(1, 12 - stage.display_order)),
            ))
            if stage.display_order >= stage_by_slug["technical-interview"].display_order:
                db.add(CollegePlacementInterview(
                    organization_id=org.id,
                    application_id=application.id,
                    interview_type="technical",
                    scheduled_at=now - timedelta(days=2),
                    status="completed",
                    mode="online",
                    interviewer="Campus technical panel",
                    score_percent=62 + student_index % 32,
                    feedback="Demonstrated sound fundamentals and problem-solving approach.",
                ))
            if stage_slug in {"offered", "joined"}:
                offer_status = "joined" if stage_slug == "joined" else "offered"
                db.add(CollegePlacementOffer(
                    organization_id=org.id,
                    application_id=application.id,
                    offered_role=opportunity.title,
                    package_paise=opportunity.package_min_paise + (student_index % 4) * 5000000,
                    offered_on=today - timedelta(days=4),
                    joining_on=today + timedelta(days=45),
                    status=offer_status,
                    notes="Demo placement offer.",
                ))
                if stage_slug == "joined":
                    career_by_student[profile.id].placement_status = "joined"

    db.flush()


def _refresh_demo_activity(db: Session, org: Organization) -> None:
    """Keep a few operational records relevant to today's demo dashboards."""
    now = datetime.now(timezone.utc)
    invoice = db.execute(select(SaleInvoice).where(
        SaleInvoice.organization_id == org.id,
        SaleInvoice.idempotency_key == f"demo-sale-{org.slug}-1",
    )).scalar_one_or_none()
    if invoice:
        invoice.created_at = now - timedelta(hours=2)
        invoice.issued_at = now - timedelta(hours=2)
        payment = db.execute(select(SalePayment).where(
            SalePayment.organization_id == org.id,
            SalePayment.invoice_id == invoice.id,
        )).scalars().first()
        if payment:
            payment.created_at = now - timedelta(hours=2)
    appointment = db.execute(select(Appointment).where(
        Appointment.organization_id == org.id,
        Appointment.notes == "DEMO appointment 6",
    )).scalar_one_or_none()
    if appointment:
        duration = appointment.ends_at - appointment.starts_at
        appointment.starts_at = (now + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
        appointment.ends_at = appointment.starts_at + duration
        appointment.status = "scheduled"
    task = db.execute(select(Task).where(
        Task.organization_id == org.id,
        Task.title == "Call clients whose follow-up is due",
    )).scalar_one_or_none()
    if task:
        task.due_at = now + timedelta(hours=3)
        task.status = "open"
    if org.industry.value == "college":
        fee_invoice = db.execute(select(SaleInvoice).where(
            SaleInvoice.organization_id == org.id,
            SaleInvoice.idempotency_key.like(f"demo-college-fee-{org.slug}-%"),
            SaleInvoice.paid_paise > 0,
        ).order_by(SaleInvoice.invoice_number)).scalars().first()
        if fee_invoice:
            fee_invoice.created_at = now - timedelta(hours=2)
            fee_invoice.issued_at = now - timedelta(hours=2)
            fee_payment = db.execute(select(SalePayment).where(
                SalePayment.organization_id == org.id,
                SalePayment.invoice_id == fee_invoice.id,
                SalePayment.status == "captured",
            ).order_by(SalePayment.created_at)).scalars().first()
            if fee_payment:
                fee_payment.created_at = now - timedelta(hours=2)
        class_session = db.execute(select(CollegeAttendanceSession).where(
            CollegeAttendanceSession.organization_id == org.id,
            CollegeAttendanceSession.status == "submitted",
        ).order_by(CollegeAttendanceSession.created_at)).scalars().first()
        if class_session:
            class_session.held_on = now.date()
        return
    if org.industry.value != "gym":
        return
    membership = db.execute(select(Membership).where(
        Membership.organization_id == org.id,
        Membership.status == "active",
    ).order_by(Membership.created_at)).scalars().first()
    if membership:
        check_in = db.execute(select(GymCheckIn).where(
            GymCheckIn.organization_id == org.id,
            GymCheckIn.membership_id == membership.id,
            GymCheckIn.source == "demo",
        ).order_by(GymCheckIn.checked_in_at.desc())).scalars().first()
        if check_in:
            check_in.checked_in_at = now - timedelta(minutes=75)
            check_in.checked_out_at = now - timedelta(minutes=10)
    gym_class = db.execute(select(GymClass).where(
        GymClass.organization_id == org.id,
        GymClass.name == "Morning Mobility",
    ).order_by(GymClass.created_at)).scalars().first()
    if gym_class:
        gym_class.starts_at = (now + timedelta(hours=1)).replace(minute=30, second=0, microsecond=0)
        gym_class.ends_at = gym_class.starts_at + timedelta(minutes=60)


def seed_demo_businesses(db: Session) -> int:
    """Enrich only known demo tenants and return the number newly seeded."""
    seeded = 0
    organizations = db.execute(select(Organization).where(Organization.slug.in_(DEMO_SLUGS))).scalars().all()
    for org in organizations:
        marker = _marker(db, org.id)
        required_version = COLLEGE_DEMO_DATA_VERSION if org.industry.value == "college" else DEMO_DATA_VERSION
        if marker and int(marker.value.get("version", 0)) >= required_version:
            _refresh_demo_activity(db, org)
            continue
        if org.industry.value == "college":
            org.enabled_modules = sorted(set(org.enabled_modules or []) | {
                "clients", "employees", "sales", "college", "documents",
                "notifications", "reports", "ai",
            })
            owner = db.execute(select(User).where(
                User.organization_id == org.id,
            ).order_by(User.created_at)).scalars().first()
            if not owner:
                continue
            locations = _seed_locations(db, org)
            staff = _seed_staff(db, org, locations)
            clients = _seed_clients(db, org, locations)
            _seed_college(db, org, owner, locations, clients, staff)
            _seed_document_and_ai(db, org, owner)
            _seed_client_media(db, org, owner, clients)
            _seed_platform_billing(db, org)
            marker_value = {"version": required_version, "seeded_at": datetime.now(timezone.utc).isoformat()}
            if marker:
                marker.value = marker_value
            else:
                db.add(Setting(organization_id=org.id, key="demo.data.version", value=marker_value))
            _refresh_demo_activity(db, org)
            seeded += 1
            continue
        shared_modules = {"clients", "employees", "catalog", "inventory", "sales", "appointments", "documents", "notifications", "reports", "ai"}
        org.enabled_modules = sorted(set(org.enabled_modules or []) | shared_modules | {org.industry.value})
        owner = db.execute(select(User).where(User.organization_id == org.id).order_by(User.created_at)).scalars().first()
        if not owner:
            continue
        locations = _seed_locations(db, org)
        staff = _seed_staff(db, org, locations)
        clients = _seed_clients(db, org, locations)
        items = _seed_catalog(db, org)
        _seed_inventory(db, org, owner, locations, items)
        appointments = _seed_appointments(db, org, locations, clients, items, staff)
        _seed_sales(db, org, owner, locations, clients, items, staff)
        _seed_relationship_data(db, org, owner, clients, staff, locations)
        _seed_tasks_and_messages(db, org, owner, locations, clients)
        _seed_document_and_ai(db, org, owner)
        _seed_client_media(db, org, owner, clients)
        _seed_platform_billing(db, org)
        if org.industry.value == "gym":
            _seed_gym(db, org, owner, locations, clients, staff)
        elif org.industry.value == "salon":
            _seed_salon(db, org, clients, staff)
        elif org.industry.value == "clinic":
            _seed_clinic(db, org, owner, locations, clients, staff, appointments, items)
        if marker:
            marker.value = {"version": DEMO_DATA_VERSION, "seeded_at": datetime.now(timezone.utc).isoformat()}
        else:
            db.add(Setting(
                organization_id=org.id,
                key="demo.data.version",
                value={"version": DEMO_DATA_VERSION, "seeded_at": datetime.now(timezone.utc).isoformat()},
            ))
        _refresh_demo_activity(db, org)
        seeded += 1
    db.flush()
    return seeded
