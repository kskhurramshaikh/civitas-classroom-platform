from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Role, ProgressionCard, Teacher
from app.schemas import ProgressionCardCreate, ProgressionCardOut
from app.security import require_role, get_current_user
from app.permissions import assert_can_access_student

router = APIRouter(prefix="/progression-cards", tags=["progression"])


@router.post("", response_model=ProgressionCardOut, status_code=status.HTTP_201_CREATED)
def create_progression_card(
    payload: ProgressionCardCreate,
    user: User = Depends(require_role(Role.teacher, Role.admin)),
    db: Session = Depends(get_db),
):
    assert_can_access_student(db, user, payload.student_id)
    teacher = db.query(Teacher).filter(Teacher.user_id == user.id).first()
    card = ProgressionCard(**payload.model_dump(), teacher_id=teacher.id if teacher else None)
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@router.get("/student/{student_id}", response_model=list[ProgressionCardOut])
def list_progression_cards(student_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Works for teacher (own class), parent (own child), or admin —
    # assert_can_access_student enforces which of those actually applies.
    assert_can_access_student(db, user, student_id)
    return (
        db.query(ProgressionCard)
        .filter(ProgressionCard.student_id == student_id)
        .order_by(ProgressionCard.week_start.desc())
        .all()
    )
