"""Pydantic schemas for API request/response."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------- AUTH ----------------
class RegisterOrgRequest(BaseModel):
    organization_name: str
    organization_slug: str
    org_type: str  # school | college | ...
    admin_email: EmailStr
    admin_password: str = Field(min_length=8)
    admin_first_name: str
    admin_last_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    org_slug: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


# ---------------- USER ----------------
class UserOut(ORMBase):
    id: str
    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    is_active: bool
    is_super_admin: bool
    organization_id: str | None = None
    avatar_url: str | None = None


class UserCreate(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    password: str = Field(min_length=8)
    phone: str | None = None
    role_ids: list[str] = []


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    is_active: bool | None = None


# ---------------- ORG ----------------
class OrganizationOut(ORMBase):
    id: str
    name: str
    slug: str
    org_type: str
    status: str
    plan: str
    contact_email: str | None = None
    logo_url: str | None = None
    ai_provider: str
    ai_model: str


class OrganizationCreate(BaseModel):
    name: str
    slug: str
    org_type: str
    contact_email: str | None = None
    contact_phone: str | None = None


class OrganizationUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    plan: str | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    contact_email: str | None = None
    logo_url: str | None = None


# ---------------- ROLE / PERMISSION ----------------
class PermissionOut(ORMBase):
    id: str
    code: str
    label: str
    module: str
    description: str | None = None


class RoleOut(ORMBase):
    id: str
    name: str
    slug: str
    description: str | None = None
    is_system: bool
    is_active: bool


class RoleCreate(BaseModel):
    name: str
    description: str | None = None
    permission_ids: list[str] = []


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    permission_ids: list[str] | None = None


class AssignRolesRequest(BaseModel):
    role_ids: list[str]


# ---------------- ACADEMIC ----------------
class DepartmentOut(ORMBase):
    id: str
    name: str
    code: str
    description: str | None = None


class DepartmentCreate(BaseModel):
    name: str
    code: str
    description: str | None = None


class AcademicUnitOut(ORMBase):
    id: str
    name: str
    code: str
    department_id: str | None


class AcademicUnitCreate(BaseModel):
    name: str
    code: str
    department_id: str | None = None


class LevelOut(ORMBase):
    id: str
    name: str
    unit_id: str
    sequence: int


class LevelCreate(BaseModel):
    name: str
    unit_id: str
    sequence: int = 0


class SectionOut(ORMBase):
    id: str
    name: str
    level_id: str
    room: str | None = None


class SectionCreate(BaseModel):
    name: str
    level_id: str
    room: str | None = None


class SubjectOut(ORMBase):
    id: str
    name: str
    code: str
    credits: int
    department_id: str | None = None
    is_active: bool


class SubjectCreate(BaseModel):
    name: str
    code: str
    credits: int = 0
    department_id: str | None = None


# ---------------- PEOPLE ----------------
class StudentOut(ORMBase):
    id: str
    admission_number: str
    first_name: str
    last_name: str
    email: str | None = None
    phone: str | None = None
    section_id: str | None = None
    department_id: str | None = None
    roll_number: str | None = None
    is_active: bool


class StudentCreate(BaseModel):
    admission_number: str
    first_name: str
    last_name: str
    email: EmailStr | None = None
    phone: str | None = None
    section_id: str | None = None
    department_id: str | None = None
    roll_number: str | None = None
    date_of_birth: str | None = None
    gender: str | None = None


class StudentUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    section_id: str | None = None
    department_id: str | None = None
    roll_number: str | None = None
    is_active: bool | None = None


class FacultyOut(ORMBase):
    id: str
    user_id: str
    employee_number: str
    designation: str | None
    department_id: str | None
    qualification: str | None
    experience_years: int | None
    is_active: bool


class FacultyCreate(BaseModel):
    employee_number: str
    email: EmailStr
    first_name: str
    last_name: str
    password: str = Field(min_length=8)
    designation: str | None = None
    department_id: str | None = None
    qualification: str | None = None
    experience_years: int | None = None


# ---------------- ATTENDANCE ----------------
class AttendanceSessionCreate(BaseModel):
    section_id: str
    subject_id: str | None = None
    session_date: str  # YYYY-MM-DD
    topic: str | None = None
    records: list[dict]  # [{student_id, status, remarks}]


class AttendanceSessionOut(ORMBase):
    id: str
    section_id: str
    subject_id: str | None
    session_date: Any
    topic: str | None
    faculty_user_id: str


# ---------------- MARKS ----------------
class ExamCreate(BaseModel):
    name: str
    exam_type: str = "internal"
    subject_id: str
    section_id: str | None = None
    max_marks: float = 100.0
    pass_marks: float = 40.0
    exam_date: str | None = None


class ExamOut(ORMBase):
    id: str
    name: str
    exam_type: str
    subject_id: str
    section_id: str | None
    max_marks: float
    pass_marks: float
    is_published: bool


class MarkEntry(BaseModel):
    student_id: str
    obtained: float
    grade: str | None = None
    remarks: str | None = None


class MarksBulkCreate(BaseModel):
    exam_id: str
    marks: list[MarkEntry]


class MarkOut(ORMBase):
    id: str
    exam_id: str
    student_id: str
    obtained: float
    grade: str | None
    remarks: str | None


# ---------------- AI ----------------
class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str


class ChatMessageOut(ORMBase):
    id: str
    conversation_id: str
    role: str
    content: str
    tool_calls: list | dict | None = None
    created_at: datetime


class ConversationOut(ORMBase):
    id: str
    title: str
    created_at: datetime
    provider: str
    model: str


# ---------------- BILLING ----------------
class CreateOrderRequest(BaseModel):
    plan: str  # starter/pro/enterprise


class WebhookEvent(BaseModel):
    event: str
    payload: dict


# ---------------- NOTIFICATION ----------------
class NotificationOut(ORMBase):
    id: str
    title: str
    body: str | None
    is_read: bool
    kind: str
    link: str | None
    created_at: datetime
