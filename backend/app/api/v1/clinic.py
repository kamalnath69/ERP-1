"""Outpatient clinic workflows with practitioner-signing safeguards."""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.business import serialize
from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import (
    Allergy, Appointment, CatalogItem, Client, Diagnosis, Dispense, Employee, EmployeeLocation, Encounter,
    LabOrder, LabResult, LabTest, PatientProfile, Prescription, PrescriptionItem,
    StockLevel, StockMovement, Vital,
)
from app.services.audit import log_action
from app.services.business_access import ensure_client_access, ensure_location, organization_for, tenant_get
from app.services.clinic import (
    clinic_queue, clinic_summary, encounter_directory, encounter_for_user,
    lab_order_directory, lab_order_for_user, patient_directory, patient_for_user,
    prescription_directory, prescription_for_user,
)

router = APIRouter(prefix="/clinic", tags=["clinic"])


def require_clinic(db, user):
    org = organization_for(db, user)
    if org.industry.value != "clinic" and "clinic" not in org.enabled_modules:
        raise HTTPException(404, "Clinic module is not enabled")


def editable_encounter(db, user, encounter_id):
    row = encounter_for_user(db, user, encounter_id, lock=True)
    if row.status == "signed" or row.signed_at:
        raise HTTPException(423, "Signed clinical records are immutable")
    return row


class PatientBody(BaseModel):
    client_id: str
    abha_number: str | None = None
    blood_group: str | None = None
    emergency_contact: dict = Field(default_factory=dict)
    consent: dict = Field(default_factory=dict)
    medical_summary: str | None = None


class EncounterBody(BaseModel):
    location_id: str
    patient_id: str
    practitioner_employee_id: str
    appointment_id: str | None = None
    chief_complaint: str | None = None


class EncounterUpdate(BaseModel):
    chief_complaint: str | None = None
    clinical_notes: str | None = None
    assessment: str | None = None
    plan: str | None = None
    follow_up_on: date | None = None
    version: int


class VitalBody(BaseModel):
    values: dict


class AllergyBody(BaseModel):
    patient_id: str
    substance: str
    reaction: str | None = None
    severity: str = "unknown"


class DiagnosisBody(BaseModel):
    code: str | None = None
    description: str
    is_primary: bool = False
    ai_suggested: bool = False


class PrescriptionItemBody(BaseModel):
    medicine_item_id: str | None = None
    medicine_name: str
    dosage: str
    frequency: str
    duration: str
    instructions: str | None = None


class PrescriptionBody(BaseModel):
    encounter_id: str
    items: list[PrescriptionItemBody] = Field(min_length=1)
    notes: str | None = None
    ai_drafted: bool = False


class LabTestBody(BaseModel):
    name: str
    code: str
    price_paise: int = Field(default=0, ge=0)
    reference_ranges: dict = Field(default_factory=dict)


class LabOrderBody(BaseModel):
    encounter_id: str
    test_id: str
    notes: str | None = None


class LabResultBody(BaseModel):
    values: dict
    interpretation: str | None = None


class DispenseItemBody(BaseModel):
    prescription_item_id: str
    quantity_milli: int = Field(gt=0)
    batch_number: str = ""


class DispenseBody(BaseModel):
    location_id: str
    prescription_id: str
    items: list[DispenseItemBody] = Field(min_length=1)


@router.get("/summary")
def summary(location_id: str | None = None, user=Depends(require_permissions("clinic.view")), db: Session = Depends(get_db)):
    require_clinic(db, user)
    return clinic_summary(db, user, location_id)


@router.get("/queue")
def queue(location_id: str | None = None, user=Depends(require_permissions("clinic.view")), db: Session = Depends(get_db)):
    require_clinic(db, user)
    return clinic_queue(db, user, location_id)


@router.get("/patients")
def list_patients(location_id: str | None = None, user=Depends(require_permissions("clinical.view")), db: Session = Depends(get_db)):
    require_clinic(db, user)
    return patient_directory(db, user, location_id)


@router.post("/patients", status_code=201)
def create_patient(body: PatientBody, user=Depends(require_permissions("clinic.manage")), db: Session = Depends(get_db)):
    require_clinic(db, user)
    ensure_client_access(db, user, tenant_get(db, Client, body.client_id, user))
    exists = db.execute(select(PatientProfile).where(PatientProfile.organization_id == user.organization_id, PatientProfile.client_id == body.client_id)).scalar_one_or_none()
    if exists: return serialize(exists)
    row = PatientProfile(organization_id=user.organization_id, **body.model_dump()); db.add(row); db.commit(); db.refresh(row); return serialize(row)


@router.get("/patients/{patient_id}/record")
def patient_record(patient_id: str, user=Depends(require_permissions("clinical.view")), db: Session = Depends(get_db)):
    patient, client = patient_for_user(db, user, patient_id)
    encounters = db.execute(select(Encounter).where(Encounter.organization_id == user.organization_id, Encounter.patient_id == patient.id).order_by(Encounter.created_at.desc())).scalars().all()
    allergies = db.execute(select(Allergy).where(Allergy.organization_id == user.organization_id, Allergy.patient_id == patient.id, Allergy.status == "active")).scalars().all()
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="clinical_record.view", resource_type="patient", resource_id=patient.id)
    db.commit()
    return {"patient": serialize(patient), "client": serialize(client), "encounters": [serialize(row) for row in encounters], "allergies": [serialize(row) for row in allergies]}


@router.post("/encounters", status_code=201)
def create_encounter(body: EncounterBody, user=Depends(require_permissions("clinical.write")), db: Session = Depends(get_db)):
    require_clinic(db, user)
    ensure_location(db, user, body.location_id)
    patient, patient_client = patient_for_user(db, user, body.patient_id)
    practitioner = tenant_get(db, Employee, body.practitioner_employee_id, user)
    assigned = db.scalar(select(func.count(EmployeeLocation.id)).where(
        EmployeeLocation.employee_id == practitioner.id,
        EmployeeLocation.location_id == body.location_id,
    )) or 0
    if not assigned:
        raise HTTPException(409, "Practitioner is not assigned to this location")
    if body.appointment_id:
        appointment = tenant_get(db, Appointment, body.appointment_id, user, location_field="location_id")
        if appointment.location_id != body.location_id or appointment.client_id != patient_client.id:
            raise HTTPException(409, "Appointment does not match this Patient and location")
    row = Encounter(organization_id=user.organization_id, **body.model_dump())
    db.add(row)
    db.flush()
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="encounter.create", resource_type="encounter", resource_id=row.id, permission="clinical.write")
    db.commit(); db.refresh(row); return serialize(row)


@router.get("/encounters")
def list_encounters(location_id: str | None = None, status_filter: str | None = None, user=Depends(require_permissions("clinical.view")), db: Session = Depends(get_db)):
    require_clinic(db, user)
    return encounter_directory(db, user, location_id, status_filter)


@router.patch("/encounters/{encounter_id}")
def update_encounter(encounter_id: str, body: EncounterUpdate, user=Depends(require_permissions("clinical.write")), db: Session = Depends(get_db)):
    row = editable_encounter(db, user, encounter_id)
    if row.version != body.version: raise HTTPException(409, "Encounter was changed by another user")
    for key, value in body.model_dump(exclude={"version"}).items(): setattr(row, key, value)
    row.version += 1
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="encounter.update", resource_type="encounter", resource_id=row.id, permission="clinical.write", changes={"version": row.version})
    db.commit(); return serialize(row)


@router.post("/encounters/{encounter_id}/vitals", status_code=201)
def add_vitals(encounter_id: str, body: VitalBody, user=Depends(require_permissions("clinical.write")), db: Session = Depends(get_db)):
    editable_encounter(db, user, encounter_id); row = Vital(organization_id=user.organization_id, encounter_id=encounter_id, values=body.values)
    db.add(row); db.flush()
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="vitals.create", resource_type="vital", resource_id=row.id, permission="clinical.write")
    db.commit(); db.refresh(row); return serialize(row)


@router.post("/encounters/{encounter_id}/diagnoses", status_code=201)
def add_diagnosis(encounter_id: str, body: DiagnosisBody, user=Depends(require_permissions("clinical.write")), db: Session = Depends(get_db)):
    editable_encounter(db, user, encounter_id); row = Diagnosis(organization_id=user.organization_id, encounter_id=encounter_id, **body.model_dump())
    db.add(row); db.flush()
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="diagnosis.create", resource_type="diagnosis", resource_id=row.id, permission="clinical.write", changes={"ai_suggested": body.ai_suggested})
    db.commit(); db.refresh(row); return serialize(row)


@router.post("/patients/{patient_id}/allergies", status_code=201)
def add_allergy(patient_id: str, body: AllergyBody, user=Depends(require_permissions("clinical.write")), db: Session = Depends(get_db)):
    patient_for_user(db, user, patient_id)
    if body.patient_id != patient_id: raise HTTPException(400, "Patient mismatch")
    row = Allergy(organization_id=user.organization_id, **body.model_dump()); db.add(row); db.flush()
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="allergy.create", resource_type="allergy", resource_id=row.id, permission="clinical.write")
    db.commit(); db.refresh(row); return serialize(row)


@router.post("/encounters/{encounter_id}/sign")
def sign_encounter(encounter_id: str, user=Depends(require_permissions("clinical.sign")), db: Session = Depends(get_db)):
    row = editable_encounter(db, user, encounter_id)
    employee = db.execute(select(Employee).where(Employee.organization_id == user.organization_id, Employee.user_id == user.id, Employee.id == row.practitioner_employee_id)).scalar_one_or_none()
    if not employee and not user.is_super_admin: raise HTTPException(403, "Only the assigned practitioner can sign this encounter")
    row.status = "signed"; row.signed_at = datetime.now(timezone.utc); row.signed_by_user_id = user.id; row.version += 1
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="encounter.sign", resource_type="encounter", resource_id=row.id)
    db.commit(); return serialize(row)


@router.post("/prescriptions", status_code=201)
def create_prescription(body: PrescriptionBody, user=Depends(require_permissions("clinical.write")), db: Session = Depends(get_db)):
    editable_encounter(db, user, body.encounter_id)
    row = Prescription(organization_id=user.organization_id, encounter_id=body.encounter_id, notes=body.notes, ai_drafted=body.ai_drafted)
    db.add(row); db.flush()
    for item in body.items:
        if item.medicine_item_id:
            catalog = tenant_get(db, CatalogItem, item.medicine_item_id, user)
            if catalog.item_type != "medicine": raise HTTPException(400, f"{catalog.name} is not a medicine")
        db.add(PrescriptionItem(organization_id=user.organization_id, prescription_id=row.id, **item.model_dump()))
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="prescription.create", resource_type="prescription", resource_id=row.id, permission="clinical.write", changes={"ai_drafted": body.ai_drafted, "item_count": len(body.items)})
    db.commit(); db.refresh(row); return serialize(row)


@router.get("/prescriptions")
def list_prescriptions(location_id: str | None = None, user=Depends(require_permissions("clinical.view")), db: Session = Depends(get_db)):
    require_clinic(db, user)
    return prescription_directory(db, user, location_id)


@router.post("/prescriptions/{prescription_id}/sign")
def sign_prescription(prescription_id: str, user=Depends(require_permissions("clinical.sign")), db: Session = Depends(get_db)):
    row = prescription_for_user(db, user, prescription_id, lock=True)
    if row.status != "draft": raise HTTPException(409, "Only draft prescriptions can be signed")
    encounter = encounter_for_user(db, user, row.encounter_id)
    if encounter.signed_by_user_id and encounter.signed_by_user_id != user.id: raise HTTPException(403, "Prescription must be signed by the encounter practitioner")
    row.status = "signed"; row.signed_at = datetime.now(timezone.utc); row.signed_by_user_id = user.id
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="prescription.sign", resource_type="prescription", resource_id=row.id)
    db.commit(); return serialize(row)


@router.get("/lab/tests")
def list_lab_tests(user=Depends(require_permissions("clinic.view")), db: Session = Depends(get_db)):
    return [serialize(row) for row in db.execute(select(LabTest).where(LabTest.organization_id == user.organization_id, LabTest.is_active.is_(True)).order_by(LabTest.name)).scalars()]


@router.post("/lab/tests", status_code=201)
def create_lab_test(body: LabTestBody, user=Depends(require_permissions("clinic.manage")), db: Session = Depends(get_db)):
    row = LabTest(organization_id=user.organization_id, **body.model_dump()); db.add(row); db.commit(); db.refresh(row); return serialize(row)


@router.post("/lab/orders", status_code=201)
def create_lab_order(body: LabOrderBody, user=Depends(require_permissions("clinical.write")), db: Session = Depends(get_db)):
    editable_encounter(db, user, body.encounter_id); tenant_get(db, LabTest, body.test_id, user)
    row = LabOrder(organization_id=user.organization_id, **body.model_dump()); db.add(row); db.flush()
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="lab_order.create", resource_type="lab_order", resource_id=row.id, permission="clinical.write")
    db.commit(); db.refresh(row); return serialize(row)


@router.get("/lab/orders")
def list_lab_orders(location_id: str | None = None, user=Depends(require_permissions("clinical.view")), db: Session = Depends(get_db)):
    require_clinic(db, user)
    return lab_order_directory(db, user, location_id)


@router.post("/lab/orders/{order_id}/sign")
def sign_lab_order(order_id: str, user=Depends(require_permissions("clinical.sign")), db: Session = Depends(get_db)):
    row = lab_order_for_user(db, user, order_id, lock=True)
    if row.signed_at: raise HTTPException(409, "Lab order is already signed")
    row.signed_at = datetime.now(timezone.utc); row.signed_by_user_id = user.id
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="lab_order.sign", resource_type="lab_order", resource_id=row.id, permission="clinical.sign")
    db.commit(); return serialize(row)


@router.put("/lab/orders/{order_id}/result")
def record_lab_result(order_id: str, body: LabResultBody, user=Depends(require_permissions("clinical.write")), db: Session = Depends(get_db)):
    order = lab_order_for_user(db, user, order_id, lock=True)
    if not order.signed_at: raise HTTPException(409, "Unsigned lab orders cannot receive results")
    result = db.execute(select(LabResult).where(LabResult.order_id == order.id)).scalar_one_or_none()
    if not result:
        result = LabResult(organization_id=user.organization_id, order_id=order.id, values=body.values, interpretation=body.interpretation)
        db.add(result)
    else:
        result.values = body.values; result.interpretation = body.interpretation
    order.status = "resulted"
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="lab_result.record", resource_type="lab_order", resource_id=order.id, permission="clinical.write")
    db.commit(); db.refresh(result); return serialize(result)


@router.post("/lab/orders/{order_id}/verify")
def verify_lab_result(order_id: str, user=Depends(require_permissions("clinical.sign")), db: Session = Depends(get_db)):
    order = lab_order_for_user(db, user, order_id, lock=True); result = db.execute(select(LabResult).where(LabResult.order_id == order.id)).scalar_one_or_none()
    if not result: raise HTTPException(404, "Lab result not found")
    result.verified_by_user_id = user.id; result.reported_at = datetime.now(timezone.utc); order.status = "verified"
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="lab_result.verify", resource_type="lab_order", resource_id=order.id, permission="clinical.sign")
    db.commit(); return serialize(result)


@router.post("/dispenses", status_code=201)
def dispense(body: DispenseBody, user=Depends(require_permissions("pharmacy.dispense")), db: Session = Depends(get_db)):
    ensure_location(db, user, body.location_id); prescription = prescription_for_user(db, user, body.prescription_id, lock=True)
    if prescription.status != "signed": raise HTTPException(409, "Only signed prescriptions can be dispensed")
    item_ids = [item.prescription_item_id for item in body.items]
    rx_items = {row.id: row for row in db.execute(select(PrescriptionItem).where(PrescriptionItem.organization_id == user.organization_id, PrescriptionItem.prescription_id == prescription.id, PrescriptionItem.id.in_(item_ids))).scalars()}
    if len(rx_items) != len(set(item_ids)): raise HTTPException(400, "Invalid prescription item")
    snapshot = []
    for request_item in body.items:
        rx = rx_items[request_item.prescription_item_id]
        if not rx.medicine_item_id: raise HTTPException(409, f"{rx.medicine_name} is not linked to inventory")
        level = db.execute(select(StockLevel).where(
            StockLevel.organization_id == user.organization_id, StockLevel.location_id == body.location_id,
            StockLevel.item_id == rx.medicine_item_id, StockLevel.batch_number == request_item.batch_number,
            StockLevel.quantity_milli >= request_item.quantity_milli,
        ).with_for_update()).scalar_one_or_none()
        if not level: raise HTTPException(409, f"Insufficient stock for {rx.medicine_name}")
        level.quantity_milli -= request_item.quantity_milli; level.version += 1
        db.add(StockMovement(
            organization_id=user.organization_id, location_id=body.location_id, item_id=rx.medicine_item_id,
            stock_level_id=level.id, movement_type="dispense", quantity_delta_milli=-request_item.quantity_milli,
            reason=f"Prescription {prescription.id}", reference_type="prescription", reference_id=prescription.id,
            performed_by_user_id=user.id,
        ))
        snapshot.append({"prescription_item_id": rx.id, "medicine_item_id": rx.medicine_item_id, "medicine_name": rx.medicine_name, "quantity_milli": request_item.quantity_milli, "batch_number": request_item.batch_number})
    row = Dispense(organization_id=user.organization_id, location_id=body.location_id, prescription_id=prescription.id, items=snapshot, dispensed_at=datetime.now(timezone.utc), dispensed_by_user_id=user.id)
    db.add(row); prescription.status = "dispensed"
    log_action(db, organization_id=user.organization_id, user_id=user.id, action="pharmacy.dispense", resource_type="prescription", resource_id=prescription.id, changes={"items": snapshot})
    db.commit(); db.refresh(row); return serialize(row)
