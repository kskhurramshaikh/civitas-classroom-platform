import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Role, ClassSection, Student, Teacher, GeneratedActivity, ProgressionCard, HomeworkCard
from app.schemas import ClassSectionOut, StudentOut, StudentCreate, RosterStudentOut, GeneratedActivityOut
from app.security import get_current_user, require_role
from app.permissions import assert_teaches_class, student_ids_for_parent

router = APIRouter(tags=["classes"])


@router.get("/classes/mine", response_model=list[ClassSectionOut])
def my_classes(user: User = Depends(require_role(Role.teacher, Role.admin)), db: Session = Depends(get_db)):
    if user.role == Role.admin:
        return db.query(ClassSection).all()
    teacher = db.query(Teacher).filter(Teacher.user_id == user.id).first()
    if teacher is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher profile not found")
    return db.query(ClassSection).filter(ClassSection.teacher_id == teacher.id).all()


@router.get("/classes/{class_section_id}/students", response_model=list[StudentOut])
def list_class_students(class_section_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_teaches_class(db, user, class_section_id)
    return db.query(Student).filter(Student.class_section_id == class_section_id).all()


@router.get("/classes/{class_section_id}/roster", response_model=list[RosterStudentOut])
def class_roster(class_section_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Phase 2: everything the Teacher Voice Screen needs to show when a
    teacher "calls upon" a student — their latest progression card,
    latest homework card, and that homework's generated activity (if
    any), in one call per class instead of N+1 round trips.
    """
    assert_teaches_class(db, user, class_section_id)
    students = db.query(Student).filter(Student.class_section_id == class_section_id).all()

    roster = []
    for student in students:
        latest_progression = (
            db.query(ProgressionCard)
            .filter(ProgressionCard.student_id == student.id)
            .order_by(ProgressionCard.week_start.desc())
            .first()
        )
        latest_homework = (
            db.query(HomeworkCard)
            .filter(HomeworkCard.student_id == student.id)
            .order_by(HomeworkCard.week_start.desc())
            .first()
        )
        latest_activity = None
        if latest_homework and latest_homework.generated_activity_id:
            activity = (
                db.query(GeneratedActivity)
                .filter(GeneratedActivity.id == latest_homework.generated_activity_id)
                .first()
            )
            if activity:
                latest_activity = GeneratedActivityOut(
                    id=activity.id,
                    homework_card_id=activity.homework_card_id,
                    engine_type=activity.engine_type,
                    title=activity.title,
                    instructions_for_parent=activity.instructions_for_parent,
                    content=json.loads(activity.content_json),
                    created_at=activity.created_at,
                )

        roster.append(RosterStudentOut(
            id=student.id,
            full_name=student.full_name,
            latest_progression=latest_progression,
            latest_homework=latest_homework,
            latest_activity=latest_activity,
        ))

    return roster


@router.post("/students", response_model=StudentOut)
def create_student(payload: StudentCreate, user: User = Depends(require_role(Role.teacher, Role.admin)), db: Session = Depends(get_db)):
    assert_teaches_class(db, user, payload.class_section_id)
    student = Student(**payload.model_dump())
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@router.get("/students/mine", response_model=list[StudentOut])
def my_children(user: User = Depends(require_role(Role.parent)), db: Session = Depends(get_db)):
    ids = student_ids_for_parent(db, user)
    if not ids:
        return []
    return db.query(Student).filter(Student.id.in_(ids)).all()
