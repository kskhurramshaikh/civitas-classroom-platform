"""
Observability log for every teacher<->system turn on the Teacher Voice
Screen (see app/models.VoiceConversationLog).

Why this exists: the goal is a durable record of exactly what teachers
say to the voice screen and exactly what the system says back, so
friction can be found and fixed from real usage instead of anecdotes —
specifically the turns where the system had to say some version of
"I didn't catch that" rather than actually doing what the teacher
asked. app/routers/admin.py exposes this log (raw feed, a summary
breakdown, and a CSV export) to the admin role.

This module is intentionally dumb and defensive:
- It never influences the conversation itself — it's only ever called
  with the already-computed request/response, after the fact, from
  app/routers/voice.py.
- A logging failure is swallowed (rolled back, never raised) so a
  database hiccup here can never break the voice screen for a teacher
  mid-conversation.
- Friction detection is a prefix match against the literal fallback
  strings app/services/voice_conversation.py returns today, plus
  entry_type == "unclear" for the dictation parser. If new fallback
  copy is added there, add its prefix to FRICTION_PREFIXES too —
  nothing else needs to change.
"""
import time
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Teacher, User, VoiceConversationLog
from app.schemas import VoiceConverseRequest, VoiceConverseResponse, VoiceEntryParseResponse

# Every phrase here is a point where the dialogue manager gave up on
# the teacher's request rather than fulfilling it — these are the
# turns worth reviewing first when deciding what to build next.
FRICTION_PREFIXES = [
    "I didn't catch a name I recognize",
    "Which student would you like first",
    "Who would you like to talk about",
    "There's no term planner set up for this class yet",
    "This term doesn't have a week",
    "I lost track of the domain for that",
    "Sorry, should I save that",
    "I didn't quite catch that",
]


def _teacher_id_for(db: Session, user: User) -> Optional[str]:
    teacher = db.query(Teacher).filter(Teacher.user_id == user.id).first()
    return teacher.id if teacher else None


def _detect_friction(speak: str) -> Tuple[bool, Optional[str]]:
    for prefix in FRICTION_PREFIXES:
        if speak.startswith(prefix):
            return True, prefix
    return False, None


def log_converse_turn(
    db: Session,
    user: User,
    payload: VoiceConverseRequest,
    response: VoiceConverseResponse,
    started_at: float,
) -> None:
    try:
        friction, reason = _detect_friction(response.speak or "")
        db.add(VoiceConversationLog(
            source="converse",
            teacher_id=_teacher_id_for(db, user),
            class_section_id=payload.class_section_id,
            student_id=response.active_student_id or payload.active_student_id,
            transcript=payload.transcript,
            speak=response.speak,
            pending_action_in=payload.pending_action,
            pending_action_out=response.pending_action,
            ui_action=response.ui_action,
            saved=response.saved,
            friction=friction,
            friction_reason=reason,
            latency_ms=int((time.monotonic() - started_at) * 1000),
        ))
        db.commit()
    except Exception:
        db.rollback()


def log_parse_entry_turn(
    db: Session,
    user: User,
    student_id: str,
    transcript: str,
    response: VoiceEntryParseResponse,
    started_at: float,
) -> None:
    try:
        friction = response.entry_type == "unclear"
        summary = response.observation or response.instructions or ""
        db.add(VoiceConversationLog(
            source="parse_entry",
            teacher_id=_teacher_id_for(db, user),
            class_section_id=None,
            student_id=student_id,
            transcript=transcript,
            speak=f"[{response.entry_type}] {summary}".strip(),
            pending_action_in=None,
            pending_action_out=None,
            ui_action="none",
            saved=False,
            friction=friction,
            friction_reason="unclear_dictation" if friction else None,
            latency_ms=int((time.monotonic() - started_at) * 1000),
        ))
        db.commit()
    except Exception:
        db.rollback()
