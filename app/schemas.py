from datetime import date, datetime
from typing import Optional
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


# ---- Digital twin ----

class TwinChatRequest(BaseModel):
    student_id: str
    message: str


class TwinChatResponse(BaseModel):
    reply: str
    escalated: bool
