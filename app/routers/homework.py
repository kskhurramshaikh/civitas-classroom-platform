import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Role, HomeworkCard, Teacher
from app.schemas import HomeworkCardCreate, HomeworkCardOut
from app.security import require_role, get_current_user
from app.permissions import assert_can_access_student
from app.services.content_generation import generate_activity_for_homework

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/homework-cards", tags=["homework"])


@router.post("", response_model=HomeworkCardOut, status_code=status.HTTP_201_CREATED)
async def create_homework_card(
    payload: HomeworkCardCreate,
    user: User = Depends(require_role(Role.teacher, Role.admin)),
    db: Session = Depends(get_db),
):
    assert_can_access_student(db, user, payload.student_id)
    teacher = db.query(Teacher).filter(Teacher.user_id == user.id).first()
    card = HomeworkCard(**payload.model_dump(), teacher_id=teacher.id if teacher else None)
    db.add(card)
    db.commit()
    db.refresh(card)

    # Every parent reinforcement gets auto-converted into a gamified
    # activity — this is the point where that happens. If generation
    # fails for any reason, the homework card itself still exists;
    # we don't fail card creation over it.
    try:
        activity = await generate_activity_for_homework(db, card)
        card.generated_activity_id = activity.id
        db.commit()
        db.refresh(card)
    except Exception:
        # Never fail card creation over generation trouble, but do log it —
        # a silent `except: pass` here previously made a real production
        # failure (see below) invisible in the logs.
        logger.exception("Activity generation failed for homework_card_id=%s", card.id)

    return card


@router.get("/student/{student_id}", response_model=list[HomeworkCardOut])
def list_homework_cards(student_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_can_access_student(db, user, student_id)
    return (
        db.query(HomeworkCard)
        .filter(HomeworkCard.student_id == student_id)
        .order_by(HomeworkCard.week_start.desc())
        .all()
    )
