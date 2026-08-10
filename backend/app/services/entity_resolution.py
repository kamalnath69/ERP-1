"""Deterministic, permission-scoped resolution of human business references."""
import logging
import re
import time
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Appointment, CatalogItem, Client, ClientMedia, Employee, EmployeeLocation, Encounter, Equipment,
    CollegeStudentProfile, GymCheckIn, GymClass, LabOrder, LabTest, Location,
    Membership, MembershipPlan, Organization, PatientProfile, Prescription, SaleInvoice,
    SalePayment, StockLevel, Task, User,
)
from app.services.business_access import allowed_client_ids, allowed_location_ids, filter_clients
from app.services.rbac import get_user_permissions


logger = logging.getLogger("edvatiq.entity_resolution")


KIND_PERMISSION = {
    "client": "clients.view", "employee": "employees.view", "location": "dashboard.view",
    "catalog": "catalog.view", "inventory": "inventory.view", "appointment": "appointments.view",
    "invoice": "sales.view", "payment": "sales.view", "task": "dashboard.view",
    "membership_plan": "gym.memberships.view", "membership": "gym.memberships.view",
    "checkin": "gym.attendance.view", "class": "gym.classes.view", "equipment": "gym.equipment.view",
    "patient": "clinical.view", "encounter": "clinical.view", "prescription": "clinical.view",
    "lab_test": "clinical.view", "lab_order": "clinical.view",
}
ENTITY_KINDS = tuple(KIND_PERMISSION)
PROFILE_KIND = {"client": "client", "patient": "client", "membership": "client",
                "checkin": "client", "employee": "employee", "catalog": "catalog", "inventory": "catalog"}


def normalize_text(value) -> str:
    return " ".join(str(value or "").casefold().split())


def compact_text(value) -> str:
    return re.sub(r"[^\w]+", "", normalize_text(value), flags=re.UNICODE)


def normalize_phone(value) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) > 10 and digits.startswith("91"): digits = digits[-10:]
    elif len(digits) > 10 and digits.startswith("0"): digits = digits[-10:]
    return digits


def _score(reference, values):
    text = normalize_text(reference); compact = compact_text(reference); phone = normalize_phone(reference)
    best = (0, None)
    for field, value in values:
        if value is None: continue
        candidate = normalize_text(value); candidate_compact = compact_text(value)
        candidate_phone = normalize_phone(value) if field == "phone" else ""
        if field == "phone" and len(phone) >= 7 and candidate_phone == phone: score = 100
        elif candidate == text: score = 100
        elif candidate_compact and candidate_compact == compact: score = 98
        elif compact and (compact in candidate_compact or candidate_compact in compact): score = 84
        else: score = round(SequenceMatcher(None, compact, candidate_compact).ratio() * 70)
        if score > best[0]: best = (score, field)
    return best


def _profile_ref(kind, row_id):
    profile_kind = PROFILE_KIND.get(kind)
    return {"kind": profile_kind, "id": row_id} if profile_kind else None


def _item(kind, row_id, label, meta, status=None, fields=(), profile_id=None, payload=None):
    return {
        "kind": kind, "id": row_id, "display_name": label, "display_meta": meta,
        "status": status, "profile_ref": _profile_ref(kind, profile_id or row_id),
        "selection_ref": {"kind": kind, "id": row_id},
        "_match_fields": fields, "snapshot": payload or {},
    }


def _uuid(value):
    try: return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError): return None


def _text_filter(reference, fields):
    text = normalize_text(reference); compact = compact_text(reference)
    clauses = []
    for field in fields:
        clauses.extend([func.lower(func.coalesce(field, "")).contains(text),
                        func.regexp_replace(func.lower(func.coalesce(field, "")), r"[^[:alnum:]]+", "", "g").contains(compact)])
        if len(compact) >= 3:
            clauses.append(func.similarity(func.lower(func.coalesce(field, "")), text) >= 0.24)
    return or_(*clauses)


def resolve_entities(db: Session, user: User, reference: str, kinds=None, limit=8):
    started = time.perf_counter()
    reference = str(reference or "").strip()
    if len(reference) < 2: return {"count": 0, "items": [], "resolution": "none"}
    permissions = get_user_permissions(db, user)
    requested = [kind for kind in (kinds or ENTITY_KINDS) if kind in KIND_PERMISSION and KIND_PERMISSION[kind] in permissions]
    allowed_locations = allowed_location_ids(db, user); allowed_clients = allowed_client_ids(db, user)
    organization = db.get(Organization, user.organization_id)
    is_college = bool(organization and organization.industry.value == "college")
    row_id = _uuid(reference); found = []

    def add(kind, row, label, meta, status=None, fields=(), profile_id=None, payload=None):
        score, matched = _score(reference, fields)
        if row_id and row.id == row_id: score, matched = 100, "id"
        if score >= 42:
            item = _item(kind, row.id, label, meta, status, fields, profile_id, payload)
            item["confidence"] = score; item["matched_by"] = matched
            found.append(item)

    if "client" in requested:
        full = func.trim(Client.first_name + " " + Client.last_name)
        client_fields = [
            full, Client.client_number, Client.phone, Client.email,
            CollegeStudentProfile.admission_number, CollegeStudentProfile.roll_number,
        ]
        stmt = filter_clients(select(Client).outerjoin(
            CollegeStudentProfile, CollegeStudentProfile.client_id == Client.id,
        ).where(Client.organization_id == user.organization_id), db, user)
        if is_college:
            stmt = stmt.where(CollegeStudentProfile.organization_id == user.organization_id)
        stmt = stmt.where(or_(Client.id == row_id, _text_filter(reference, client_fields)) if row_id else _text_filter(reference, client_fields))
        for row in db.execute(stmt.limit(30)).scalars():
            name = f"{row.first_name} {row.last_name}".strip()
            student = db.execute(select(CollegeStudentProfile).where(
                CollegeStudentProfile.client_id == row.id,
            )).scalar_one_or_none()
            add("client", row, name, student.admission_number if student else row.phone or row.client_number, student.status if student else row.status,
                [
                    ("name", name), ("number", row.client_number), ("phone", row.phone),
                    ("email", row.email),
                    ("admission_number", student.admission_number if student else None),
                    ("roll_number", student.roll_number if student else None),
                ],
                payload={
                    "client_number": row.client_number, "phone": row.phone, "email": row.email,
                    "last_visit_at": row.last_visit_at,
                    "admission_number": student.admission_number if student else None,
                    "roll_number": student.roll_number if student else None,
                })

    if "employee" in requested:
        full = func.trim(Employee.first_name + " " + Employee.last_name)
        stmt = select(Employee).where(Employee.organization_id == user.organization_id)
        if allowed_locations is not None:
            stmt = stmt.where(Employee.id.in_(select(EmployeeLocation.employee_id).where(EmployeeLocation.location_id.in_(allowed_locations))))
        stmt = stmt.where(or_(Employee.id == row_id, _text_filter(reference, [full, Employee.employee_number, Employee.phone, Employee.email, Employee.designation])) if row_id else _text_filter(reference, [full, Employee.employee_number, Employee.phone, Employee.email, Employee.designation]))
        for row in db.execute(stmt.limit(30)).scalars():
            name = f"{row.first_name} {row.last_name}".strip()
            add("employee", row, name, row.designation or row.employee_number, row.status,
                [("name", name), ("number", row.employee_number), ("phone", row.phone), ("email", row.email), ("designation", row.designation)],
                payload={"employee_number": row.employee_number, "phone": row.phone, "email": row.email, "designation": row.designation})

    named_models = {
        "location": (Location, [Location.name, Location.code, Location.phone, Location.gstin], lambda r: (r.name, r.city or r.code, "active" if r.is_active else "inactive", [("name", r.name), ("code", r.code), ("phone", r.phone), ("gstin", r.gstin)], {"code": r.code, "city": r.city})),
        "catalog": (CatalogItem, [CatalogItem.name, CatalogItem.sku, CatalogItem.hsn_sac], lambda r: (r.name, r.sku, "active" if r.is_active else "inactive", [("name", r.name), ("sku", r.sku), ("hsn", r.hsn_sac)], {"sku": r.sku, "item_type": r.item_type, "price_paise": r.price_paise})),
        "task": (Task, [Task.title, Task.description], lambda r: (r.title, r.priority, r.status, [("title", r.title), ("description", r.description)], {"due_at": r.due_at, "priority": r.priority})),
        "membership_plan": (MembershipPlan, [MembershipPlan.name], lambda r: (r.name, f"{r.duration_days} days", "active" if r.is_active else "inactive", [("name", r.name)], {"duration_days": r.duration_days, "price_paise": r.price_paise})),
        "class": (GymClass, [GymClass.name], lambda r: (r.name, str(r.starts_at), r.status, [("name", r.name)], {"starts_at": r.starts_at, "ends_at": r.ends_at, "capacity": r.capacity})),
        "equipment": (Equipment, [Equipment.name, Equipment.asset_code], lambda r: (r.name, r.asset_code, r.status, [("name", r.name), ("asset_code", r.asset_code)], {"next_service_on": r.next_service_on})),
        "lab_test": (LabTest, [LabTest.name, LabTest.code], lambda r: (r.name, r.code, "active" if r.is_active else "inactive", [("name", r.name), ("code", r.code)], {"price_paise": r.price_paise})),
    }
    for kind, (model, fields, describe) in named_models.items():
        if kind not in requested: continue
        stmt = select(model).where(model.organization_id == user.organization_id)
        if model is Location and allowed_locations is not None: stmt = stmt.where(Location.id.in_(allowed_locations))
        if hasattr(model, "location_id") and allowed_locations is not None: stmt = stmt.where(model.location_id.in_(allowed_locations))
        if hasattr(model, "client_id") and allowed_clients is not None:
            stmt = stmt.where(or_(model.client_id.is_(None), model.client_id.in_(allowed_clients)))
        stmt = stmt.where(or_(model.id == row_id, _text_filter(reference, fields)) if row_id else _text_filter(reference, fields))
        for row in db.execute(stmt.limit(20)).scalars():
            label, meta, status, match_fields, payload = describe(row)
            add(kind, row, label, meta, status, match_fields, payload=payload)

    # Relational records are resolved by their visible reference or an already
    # scoped client name/contact, never by scanning unrestricted rows.
    client_match = _text_filter(reference, [func.trim(Client.first_name + " " + Client.last_name), Client.client_number, Client.phone, Client.email])
    relational = {
        "appointment": (Appointment, "appointments", "appointments.view"),
        "invoice": (SaleInvoice, "invoices", "sales.view"),
        "membership": (Membership, "memberships", "gym.memberships.view"),
        "checkin": (GymCheckIn, "check-ins", "gym.attendance.view"),
    }
    for kind, (model, _label, _permission) in relational.items():
        if kind not in requested: continue
        stmt = select(model, Client).join(Client, Client.id == model.client_id).where(model.organization_id == user.organization_id)
        if allowed_locations is not None and hasattr(model, "location_id"): stmt = stmt.where(model.location_id.in_(allowed_locations))
        if allowed_clients is not None: stmt = stmt.where(Client.id.in_(allowed_clients))
        direct = model.id == row_id if row_id else None
        extra = func.lower(SaleInvoice.invoice_number).contains(normalize_text(reference)) if kind == "invoice" else None
        stmt = stmt.where(or_(*[clause for clause in [direct, extra, client_match] if clause is not None])).limit(20)
        for row, client in db.execute(stmt).all():
            name = f"{client.first_name} {client.last_name}".strip()
            if kind == "appointment": meta, status, payload = str(row.starts_at), row.status, {"starts_at": row.starts_at, "ends_at": row.ends_at}
            elif kind == "invoice": meta, status, payload = row.invoice_number, row.status, {"invoice_number": row.invoice_number, "total_paise": row.total_paise, "paid_paise": row.paid_paise}
            elif kind == "membership": meta, status, payload = str(row.ends_on), row.status, {"starts_on": row.starts_on, "ends_on": row.ends_on, "amount_paise": row.amount_paise}
            else: meta, status, payload = str(row.checked_in_at), "checked_out" if row.checked_out_at else "checked_in", {"checked_in_at": row.checked_in_at, "checked_out_at": row.checked_out_at}
            fields = [("id", row.id), ("name", name), ("number", client.client_number), ("phone", client.phone)]
            if kind == "invoice": fields.append(("invoice_number", row.invoice_number))
            add(kind, row, name, meta, status, fields, profile_id=client.id, payload=payload)

    if "payment" in requested:
        stmt = select(SalePayment, SaleInvoice).join(SaleInvoice, SaleInvoice.id == SalePayment.invoice_id).where(SalePayment.organization_id == user.organization_id)
        if allowed_locations is not None: stmt = stmt.where(SaleInvoice.location_id.in_(allowed_locations))
        if allowed_clients is not None: stmt = stmt.where(SaleInvoice.client_id.in_(allowed_clients))
        conditions = [func.lower(func.coalesce(SalePayment.reference, "")).contains(normalize_text(reference)), func.lower(SaleInvoice.invoice_number).contains(normalize_text(reference))]
        if row_id: conditions.append(SalePayment.id == row_id)
        for row, invoice in db.execute(stmt.where(or_(*conditions)).limit(20)).all():
            add("payment", row, f"Payment for {invoice.invoice_number}", row.reference or row.method, row.status,
                [("reference", row.reference), ("invoice_number", invoice.invoice_number), ("id", row.id)], payload={"amount_paise": row.amount_paise, "method": row.method})

    if "inventory" in requested:
        stmt = select(StockLevel, CatalogItem, Location).join(
            CatalogItem, CatalogItem.id == StockLevel.item_id
        ).join(Location, Location.id == StockLevel.location_id).where(
            StockLevel.organization_id == user.organization_id
        )
        if allowed_locations is not None: stmt = stmt.where(StockLevel.location_id.in_(allowed_locations))
        conditions = [_text_filter(reference, [CatalogItem.name, CatalogItem.sku, StockLevel.batch_number])]
        if row_id: conditions.append(StockLevel.id == row_id)
        for row, item, location in db.execute(stmt.where(or_(*conditions)).limit(20)).all():
            add("inventory", row, item.name, f"{item.sku} / {location.name}", "low" if row.quantity_milli <= row.reorder_level_milli else "available",
                [("name", item.name), ("sku", item.sku), ("batch", row.batch_number), ("id", row.id)],
                profile_id=item.id, payload={"quantity_milli": row.quantity_milli, "reorder_level_milli": row.reorder_level_milli,
                                              "batch_number": row.batch_number, "expires_on": row.expires_on,
                                              "location_id": location.id, "location_name": location.name})

    # Clinical child records resolve only after clinical permission and remain
    # linked to their authorized patient profile.
    if "patient" in requested:
        stmt = select(PatientProfile, Client).join(Client, Client.id == PatientProfile.client_id).where(PatientProfile.organization_id == user.organization_id)
        stmt = filter_clients(stmt, db, user, Client).where(or_(PatientProfile.id == row_id, func.lower(func.coalesce(PatientProfile.abha_number, "")).contains(normalize_text(reference)), client_match) if row_id else or_(func.lower(func.coalesce(PatientProfile.abha_number, "")).contains(normalize_text(reference)), client_match))
        for row, client in db.execute(stmt.limit(20)).all():
            name = f"{client.first_name} {client.last_name}".strip()
            add("patient", row, name, row.abha_number or "Patient", "active", [("name", name), ("abha", row.abha_number), ("phone", client.phone)], profile_id=client.id, payload={"blood_group": row.blood_group})

    clinical_children = [kind for kind in ("encounter", "prescription", "lab_order") if kind in requested]
    if clinical_children:
        patient_match = _text_filter(reference, [func.trim(Client.first_name + " " + Client.last_name), Client.client_number, Client.phone, PatientProfile.abha_number])
        if "encounter" in clinical_children:
            stmt = select(Encounter, PatientProfile, Client).join(PatientProfile, PatientProfile.id == Encounter.patient_id).join(Client, Client.id == PatientProfile.client_id).where(Encounter.organization_id == user.organization_id)
            stmt = filter_clients(stmt, db, user, Client)
            if allowed_locations is not None: stmt = stmt.where(Encounter.location_id.in_(allowed_locations))
            clauses = [patient_match]
            if row_id: clauses.append(Encounter.id == row_id)
            for row, patient, client in db.execute(stmt.where(or_(*clauses)).limit(20)).all():
                name = f"{client.first_name} {client.last_name}".strip()
                add("encounter", row, f"Encounter · {name}", row.chief_complaint or str(row.created_at), row.status,
                    [("name", name), ("number", client.client_number), ("phone", client.phone), ("id", row.id)],
                    payload={"chief_complaint": row.chief_complaint, "follow_up_on": row.follow_up_on, "signed_at": row.signed_at})
        if "prescription" in clinical_children:
            stmt = select(Prescription, Encounter, PatientProfile, Client).join(Encounter, Encounter.id == Prescription.encounter_id).join(PatientProfile, PatientProfile.id == Encounter.patient_id).join(Client, Client.id == PatientProfile.client_id).where(Prescription.organization_id == user.organization_id)
            stmt = filter_clients(stmt, db, user, Client)
            if allowed_locations is not None: stmt = stmt.where(Encounter.location_id.in_(allowed_locations))
            clauses = [patient_match]
            if row_id: clauses.append(Prescription.id == row_id)
            for row, encounter, patient, client in db.execute(stmt.where(or_(*clauses)).limit(20)).all():
                name = f"{client.first_name} {client.last_name}".strip()
                add("prescription", row, f"Prescription · {name}", str(row.created_at), row.status,
                    [("name", name), ("number", client.client_number), ("phone", client.phone), ("id", row.id)],
                    payload={"signed_at": row.signed_at})
        if "lab_order" in clinical_children:
            stmt = select(LabOrder, LabTest, Encounter, PatientProfile, Client).join(LabTest, LabTest.id == LabOrder.test_id).join(Encounter, Encounter.id == LabOrder.encounter_id).join(PatientProfile, PatientProfile.id == Encounter.patient_id).join(Client, Client.id == PatientProfile.client_id).where(LabOrder.organization_id == user.organization_id)
            stmt = filter_clients(stmt, db, user, Client)
            if allowed_locations is not None: stmt = stmt.where(Encounter.location_id.in_(allowed_locations))
            clauses = [patient_match, _text_filter(reference, [LabTest.name, LabTest.code])]
            if row_id: clauses.append(LabOrder.id == row_id)
            for row, test, encounter, patient, client in db.execute(stmt.where(or_(*clauses)).limit(20)).all():
                name = f"{client.first_name} {client.last_name}".strip()
                add("lab_order", row, test.name, f"{name} · {test.code}", row.status,
                    [("name", name), ("test", test.name), ("code", test.code), ("number", client.client_number), ("id", row.id)],
                    payload={"signed_at": row.signed_at})

    # Catalog items are the canonical entity. Stock levels are location/batch
    # children and must not appear as duplicate products when both kinds are searched.
    catalog_matches = {item["id"]: item for item in found if item["kind"] == "catalog"}
    if catalog_matches:
        canonical = []
        for item in found:
            profile = item.get("profile_ref") or {}
            catalog = catalog_matches.get(profile.get("id")) if item["kind"] == "inventory" else None
            if not catalog:
                canonical.append(item)
                continue
            stock = catalog.setdefault("snapshot", {}).setdefault("stock", {
                "level_count": 0, "total_quantity_milli": 0, "low_level_count": 0, "levels": [],
            })
            snapshot = item.get("snapshot") or {}
            stock["level_count"] += 1
            stock["total_quantity_milli"] += int(snapshot.get("quantity_milli") or 0)
            stock["low_level_count"] += int(item.get("status") == "low")
            stock["levels"].append({
                "location_id": snapshot.get("location_id"), "location_name": snapshot.get("location_name"),
                "batch_number": snapshot.get("batch_number"), "quantity_milli": snapshot.get("quantity_milli"),
                "reorder_level_milli": snapshot.get("reorder_level_milli"), "status": item.get("status"),
            })
        found = canonical

    found.sort(key=lambda item: (-item["confidence"], item["display_name"]))
    found = found[:max(1, min(limit, 20))]
    if "clients.media.view" in permissions:
        client_ids = {
            (item.get("profile_ref") or {}).get("id") for item in found
            if (item.get("profile_ref") or {}).get("kind") == "client"
        }
        if client_ids:
            photos = dict(db.execute(select(ClientMedia.client_id, func.max(ClientMedia.updated_at)).where(
                ClientMedia.organization_id == user.organization_id, ClientMedia.client_id.in_(client_ids),
                ClientMedia.is_profile.is_(True),
            ).group_by(ClientMedia.client_id)).all())
            for item in found:
                client_id = (item.get("profile_ref") or {}).get("id")
                updated_at = photos.get(client_id)
                if updated_at: item["avatar_url"] = f"/clients/{client_id}/photo?v={int(updated_at.timestamp())}"
    exact = [item for item in found if item["confidence"] >= 98]
    resolution = "unique" if len(exact) == 1 else "ambiguous" if found else "none"
    selected = exact[0] if resolution == "unique" else None
    for item in found:
        item.pop("_match_fields", None)
    logger.info(
        "entity_resolution outcome=%s requested_kinds=%d candidates=%d latency_ms=%d organization=%s",
        resolution, len(requested), len(found), int((time.perf_counter() - started) * 1000), user.organization_id,
    )
    return {"count": len(found), "items": found, "resolution": resolution, "selected": selected}


def validate_entity_ref(db: Session, user: User, kind: str, row_id: str):
    result = resolve_entities(db, user, row_id, [kind], 2)
    return result.get("selected") if result.get("resolution") == "unique" else None
