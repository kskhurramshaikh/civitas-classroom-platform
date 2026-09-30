from datetime import date, datetime
from typing import Optional, Any
from pydantic import BaseModel, EmailStr

from app.models import Role


# ---- Auth ----

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    full_name: str


# ---- Class / Student ----

class ClassSectionOut(BaseModel):
    id: str
    name: str

    class Config:
        from_attributes = True


class StudentOut(BaseModel):
    id: str
    full_name: str
    date_of_birth: Optional[date] = None
    class_section_id: str

    class Config:
        from_attributes = True


class StudentCreate(BaseModel):
    full_name: str
    date_of_birth: Optional[date] = None
    class_section_id: str


# ---- Domains ----

class DomainOut(BaseModel):
    id: str
    key: str
    name: str
    color_hint: Optional[str] = None

    class Config:
        from_attributes = True


# ---- Progression cards ----

class ProgressionCardCreate(BaseModel):
    student_id: str
    domain_id: str
    week_start: date
    observation: str
    needs_improvement: Optional[str] = None
    stage_score: Optional[int] = None


class ProgressionCardOut(BaseModel):
    id: str
    student_id: str
    domain_id: str
    week_start: date
    observation: str
    needs_improvement: Optional[str] = None
    stage_score: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Homework cards ----

class HomeworkCardCreate(BaseModel):
    student_id: str
    domain_id: str
    week_start: date
    title: str
    instructions: str


class HomeworkCardOut(BaseModel):
    id: str
    student_id: str
    domain_id: str
    week_start: date
    title: str
    instructions: str
    generated_activity_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Generated activities (Phase 2 gamified reinforcement) ----

class GeneratedActivityOut(BaseModel):
    id: str
    homework_card_id: str
    engine_type: str
    title: str
    instructions_for_parent: Optional[str] = None
    content: Any  # decoded JSON payload, shape depends on engine_type
    created_at: datetime


# ---- Roster (Teacher Voice Screen) ----

class RosterStudentOut(BaseModel):
    id: str
    full_name: str
    latest_progression: Optional[ProgressionCardOut] = None
    latest_homework: Optional[HomeworkCardOut] = None
    latest_activity: Optional[GeneratedActivityOut] = None


# ---- Teacher persona (digital twin config) ----

class TeacherPersonaOut(BaseModel):
    display_name: str
    persona_voice_notes: Optional[str] = None
    voice_gender: Optional[str] = None


class TeacherPersonaUpdate(BaseModel):
    display_name: Optional[str] = None
    persona_voice_notes: Optional[str] = None
    voice_gender: Optional[str] = None


# ---- Digital twin ----

class TwinChatRequest(BaseModel):
    student_id: str
    message: str


class TwinChatResponse(BaseModel):
    reply: str
    escalated: bool
