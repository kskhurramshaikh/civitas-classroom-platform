"""
Phase 2: per-teacher persona configuration. Previously the digital
twin's persona notes could only be set via scripts/seed_demo.py — this
lets a teacher view and edit their own persona/voice notes through the
API, which is what a real persona-config UI needs to exist at all.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Role, Teacher
from app.schemas import TeacherPersonaOut, TeacherPersonaUpdate
from app.security import require_role

router = APIRouter(prefix="/teachers", tags=["teachers"])


def _own_teacher_profile(db: Session, user: User) -> Teacher:
    teacher = db.query(Teacher).filter(Teacher.user_id == user.id).first()
    if teacher is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher profile not found")
    return teacher


@router.get("/me/persona", response_model=TeacherPersonaOut)
def get_my_persona(user: User = Depends(require_role(Role.teacher)), db: Session = Depends(get_db)):
    return _own_teacher_profile(db, user)


@router.put("/me/persona", response_model=TeacherPersonaOut)
def update_my_persona(
    payload: TeacherPersonaUpdate,
    user: User = Depends(require_role(Role.teacher)),
    db: Session = Depends(get_db),
):
    teacher = _own_teacher_profile(db, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(teacher, field, value)
    db.commit()
    db.refresh(teacher)
    return teacher
