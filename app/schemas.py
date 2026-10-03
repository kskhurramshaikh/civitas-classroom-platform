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


# ---- Term planner ----

class WeekPlanCreate(BaseModel):
    domain_id: str
    focus: str


class WeekPlanOut(BaseModel):
    id: str
    domain_id: str
    focus: str

    class Config:
        from_attributes = True


class TermWeekOut(BaseModel):
    id: str
    week_number: int
    week_start: date
    plans: list[WeekPlanOut] = []

    class Config:
        from_attributes = True


class TermCreate(BaseModel):
    class_section_id: str
    name: str
    start_date: date
    num_weeks: int


class TermOut(BaseModel):
    id: str
    class_section_id: str
    name: str
    start_date: date
    num_weeks: int
    weeks: list[TermWeekOut] = []

    class Config:
        from_attributes = True


class CurrentWeekOut(BaseModel):
    term_id: str
    term_name: str
    week_id: str
    week_number: int
    week_start: date
    all_weeks: list[TermWeekOut] = []


# ---- Voice-dictated entry parsing ----
# Voice is the primary way a teacher adds a weekly card; the typed
# add-card form is the fallback. This endpoint turns a spoken,
# informal transcript into a structured draft — it is never saved on
# its own, the frontend fills the existing form with it so the
# teacher still reviews and taps Save.

class VoiceEntryParseRequest(BaseModel):
    student_id: str
    transcript: str


class VoiceEntryParseResponse(BaseModel):
    entry_type: str  # "progress_note" | "reinforcement" | "unclear"
    domain_id: Optional[str] = None
    observation: Optional[str] = None
    needs_improvement: Optional[str] = None
    stage_score: Optional[int] = None
    title: Optional[str] = None
    instructions: Optional[str] = None
    raw_transcript: str


# ---- Conversational voice screen ----
# The voice screen is the primary way a teacher does everything — call
# on a student, hear their current progress/reinforcement read back,
# navigate by week, and dictate an update — without dropping back to
# the typed add-card form. Each turn sends the small bit of
# conversation state the frontend is holding (who's active, what week,
# and whether we're mid-way through an update) and gets back what to
# say, what to show, and a couple of next-step suggestions.

class VoiceConverseRequest(BaseModel):
    class_section_id: str
    transcript: str
    active_student_id: Optional[str] = None
    active_week_number: Optional[int] = None
    pending_action: Optional[str] = None
    pending_payload: Optional[dict] = None


class VoiceConverseResponse(BaseModel):
    speak: str
    active_student_id: Optional[str] = None
    active_week_number: Optional[int] = None
    active_week_start: Optional[str] = None
    pending_action: Optional[str] = None
    pending_payload: Optional[dict] = None
    ui_action: str = "none"   # "focus_student" | "show_week" | "none"
    suggestions: list[str] = []
    saved: bool = False


# ---- Voice conversation log (observability for Teacher Voice Screen) ----
# Every /voice/converse and /voice/parse-entry turn is logged (see
# app/services/conversation_log.py) so real usage can be reviewed to
# find where teachers get stuck and where the system falls back to
# "I didn't catch that" instead of doing what was asked.

class VoiceConversationLogOut(BaseModel):
    id: str
    source: str
    teacher_id: Optional[str] = None
    class_section_id: Optional[str] = None
    student_id: Optional[str] = None
    transcript: str
    speak: str
    pending_action_in: Optional[str] = None
    pending_action_out: Optional[str] = None
    ui_action: Optional[str] = None
    saved: bool
    friction: bool
    friction_reason: Optional[str] = None
    latency_ms: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class VoiceConversationLogSummary(BaseModel):
    total_turns: int
    friction_turns: int
    friction_rate: float
    by_friction_reason: dict[str, int]
    by_source: dict[str, int]
