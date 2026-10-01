from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Role
from app.schemas import VoiceEntryParseRequest, VoiceEntryParseResponse
from app.security import require_role
from app.permissions import assert_can_access_student
from app.services.voice_entry import parse_voice_entry

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
    """
    student = assert_can_access_student(db, user, payload.student_id)
    result = await parse_voice_entry(db, student, payload.transcript)
    return VoiceEntryParseResponse(**result)
