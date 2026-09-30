"""
Data-scoping helpers. These exist so that "a parent can only ever see
their own child" and "a teacher can only touch their own class" are
enforced once, here, rather than re-implemented (and potentially
forgotten) in every router. Every router that returns or mutates
student-linked data should filter through one of these rather than
querying the table directly.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import User, Role, Student, ClassSection, ParentStudentLink, Teacher


def assert_can_access_student(db: Session, user: User, student_id: str) -> Student:
    student = db.query(Student).filter(Student.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    if user.role == Role.admin:
        return student

    if user.role == Role.teacher:
        teacher = db.query(Teacher).filter(Teacher.user_id == user.id).first()
        class_section = db.query(ClassSection).filter(ClassSection.id == student.class_section_id).first()
        if teacher is None or class_section is None or class_section.teacher_id != teacher.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your class")
        return student

    if user.role == Role.parent:
        link = db.query(ParentStudentLink).filter(
            ParentStudentLink.parent_user_id == user.id,
            ParentStudentLink.student_id == student_id,
        ).first()
        if link is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your child")
        return student

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")


def assert_teaches_class(db: Session, user: User, class_section_id: str) -> ClassSection:
    class_section = db.query(ClassSection).filter(ClassSection.id == class_section_id).first()
    if class_section is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")

    if user.role == Role.admin:
        return class_section

    if user.role != Role.teacher:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")

    teacher = db.query(Teacher).filter(Teacher.user_id == user.id).first()
    if teacher is None or class_section.teacher_id != teacher.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your class")
    return class_section


def student_ids_for_parent(db: Session, user: User) -> list[str]:
    links = db.query(ParentStudentLink).filter(ParentStudentLink.parent_user_id == user.id).all()
    return [l.student_id for l in links]
