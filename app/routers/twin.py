from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import TwinChatRequest, TwinChatResponse
from app.security import get_current_user
from app.permissions import assert_can_access_student
from app.services.twin import ask_digital_twin

router = APIRouter(prefix="/twin", tags=["twin"])


@router.post("/chat", response_model=TwinChatResponse)
async def chat(payload: TwinChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # A parent may only chat about their own child; a teacher only about
    # a student in her own class. Same rule as every other student-scoped
    # endpoint — enforced once, in assert_can_access_student.
    assert_can_access_student(db, user, payload.student_id)
    reply, escalated = await ask_digital_twin(db, payload.student_id, payload.message)
    return TwinChatResponse(reply=reply, escalated=escalated)
