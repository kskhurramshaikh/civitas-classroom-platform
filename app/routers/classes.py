from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Role, ClassSection, Student, Teacher, ParentStudentLink
from app.schemas import ClassSectionOut, StudentOut, StudentCreate
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
