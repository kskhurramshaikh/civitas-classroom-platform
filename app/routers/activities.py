import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, GeneratedActivity, HomeworkCard
from app.schemas import GeneratedActivityOut
from app.security import get_current_user
from app.permissions import assert_can_access_student

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("/{activity_id}", response_model=GeneratedActivityOut)
def get_activity(activity_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    activity = db.query(GeneratedActivity).filter(GeneratedActivity.id == activity_id).first()
    if activity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")

    homework = db.query(HomeworkCard).filter(HomeworkCard.id == activity.homework_card_id).first()
    if homework is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Homework card not found")
    assert_can_access_student(db, user, homework.student_id)

    return GeneratedActivityOut(
        id=activity.id,
        homework_card_id=activity.homework_card_id,
        engine_type=activity.engine_type,
        title=activity.title,
        instructions_for_parent=activity.instructions_for_parent,
        content=json.loads(activity.content_json),
        created_at=activity.created_at,
    )
