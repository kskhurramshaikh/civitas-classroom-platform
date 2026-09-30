"""
Shared seeding logic — one school, one teacher (Ms. Sama), one class, a
handful of students (including Zayan and Ibrahim from the pitch
prototype), the six developmental domains used in the Learning Garden
parent app, and one parent account per student.

Idempotent: if a school named "Civitas" already exists, seed() is a
no-op and returns seeded=False, so this is safe to call more than once
(e.g. from the one-off /admin/seed-demo endpoint).

Used by both scripts/seed_demo.py (local/CLI) and
app/routers/admin.py (the deployed one-off endpoint, since the Render
free plan has no Shell access to run the script directly against the
live DB).
"""
from datetime import date

from sqlalchemy.orm import Session

from app.database import Base, engine
from app.models import (
    School, User, Teacher, ClassSection, Student, ParentStudentLink,
    DevelopmentalDomain, Role,
)
from app.security import hash_password

DOMAINS = [
    ("words", "Words & Stories", "--d1"),
    ("numbers", "Numbers & Patterns", "--d2"),
    ("heart", "Heart & Friends", "--d3"),
    ("moving", "Moving & Building", "--d4"),
    ("art", "Imagination & Art", "--d5"),
    ("self", "Doing It Myself", "--d6"),
]

STUDENTS_DATA = [
    ("Zayan Khan", date(2021, 3, 12), "zayan.parent@example.com"),
    ("Ibrahim Malik", date(2021, 6, 2), "ibrahim.parent@example.com"),
]


def seed(db: Session) -> bool:
    """Seed demo data if not already present. Returns True if it seeded,
    False if it found existing data and skipped."""
    Base.metadata.create_all(bind=engine)

    if db.query(School).filter(School.name == "Civitas").first() is not None:
        return False

    school = School(name="Civitas")
    db.add(school)
    db.flush()

    for key, name, color in DOMAINS:
        db.add(DevelopmentalDomain(school_id=school.id, key=key, name=name, color_hint=color))
    db.flush()

    teacher_user = User(
        school_id=school.id,
        email="sama@civitas.edu.pk",
        hashed_password=hash_password("changeme123"),
        full_name="Sama Ahmed",
        role=Role.teacher,
    )
    db.add(teacher_user)
    db.flush()

    teacher = Teacher(
        user_id=teacher_user.id,
        display_name="Ms. Sama",
        persona_voice_notes=(
            "Warm, plain-spoken, encouraging. Talks about small concrete moments, "
            "not abstract scores. Always pairs a concern with something the child is "
            "already doing well."
        ),
        voice_gender="female",
    )
    db.add(teacher)
    db.flush()

    class_section = ClassSection(school_id=school.id, teacher_id=teacher.id, name="Kindergarten B")
    db.add(class_section)
    db.flush()

    for full_name, dob, parent_email in STUDENTS_DATA:
        student = Student(class_section_id=class_section.id, full_name=full_name, date_of_birth=dob)
        db.add(student)
        db.flush()

        parent_user = User(
            school_id=school.id,
            email=parent_email,
            hashed_password=hash_password("changeme123"),
            full_name=f"Parent of {full_name.split()[0]}",
            role=Role.parent,
        )
        db.add(parent_user)
        db.flush()

        db.add(ParentStudentLink(parent_user_id=parent_user.id, student_id=student.id))

    db.commit()
    return True
