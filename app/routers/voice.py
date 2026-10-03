import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Role
from app.schemas import VoiceEntryParseRequest, VoiceEntryParseResponse, VoiceConverseRequest, VoiceConverseResponse
from app.security import require_role
from app.permissions import assert_can_access_student, assert_teaches_class
from app.services.voice_entry import parse_voice_entry
from app.services.voice_conversation import converse
from app.services.conversation_log import log_converse_turn, log_parse_entry_turn

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/parse-entry", response_model=VoiceEntryParseResponse)
async def parse_entry(
    payload: VoiceEntryParseRequest,
    user: User = Depends(require_role(Role.teacher, Role.admin)),
    db: Session = Depends(get_db),
):
    """
    Turns a teacher's spoken, informal transcript about one student
    into a structured draft (progress note or reinforcement). Never
    writes anything itself — the frontend fills the existing add-card
    form with the result so the teacher reviews and saves it herself.

    Logged for product review (see app/services/conversation_log.py) —
    logging never affects this response.
    """
    student = assert_can_access_student(db, user, payload.student_id)
    started = time.monotonic()
    result = await parse_voice_entry(db, student, payload.transcript)
    response = VoiceEntryParseResponse(**result)
    log_parse_entry_turn(db, user, student.id, payload.transcript, response, started)
    return response


@router.post("/converse", response_model=VoiceConverseResponse)
async def converse_turn(
    payload: VoiceConverseRequest,
    user: User = Depends(require_role(Role.teacher, Role.admin)),
    db: Session = Depends(get_db),
):
    """
    One turn of the conversational voice screen: call a student,
    hear progress or a week's cards read back, or dictate/confirm an
    update — driven entirely by the small bit of state the frontend
    carries between turns (see VoiceConverseRequest/Response docs in
    schemas.py and the design note at the top of voice_conversation.py).

    Every turn is also logged (see app/services/conversation_log.py)
    purely for product review — it never affects this response.
    """
    assert_teaches_class(db, user, payload.class_section_id)
    started = time.monotonic()
    response = await converse(db, user, payload)
    log_converse_turn(db, user, payload, response, started)
    return response
