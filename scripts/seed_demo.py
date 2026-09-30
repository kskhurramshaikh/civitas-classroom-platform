"""
Seeds one school, one teacher (Ms. Sama), one class, a handful of
students (including Zayan and Ibrahim from the pitch prototype), the
six developmental domains used in the Learning Garden parent app, and
one parent account per student so the API has something real to query
immediately after first deploy.

Run with:  python -m scripts.seed_demo
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date

from app.database import Base, engine, SessionLocal
from app.models import School, User, Teacher, ClassSection, Student, ParentStudentLink, DevelopmentalDomain, Role
from app.security import hash_password

DOMAINS = [
    ("words", "Words & Stories", "--d1"),
    ("numbers", "Numbers & Patterns", "--d2"),
    ("heart", "Heart & Friends", "--d3"),
    ("moving", "Moving & Building", "--d4"),
    ("art", "Imagination & Art", "--d5"),
    ("self", "Doing It Myself", "--d6"),
]


def run():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        school = School(name="Civitas")
        db.add(school)
        db.flush()

        domains = []
        for key, name, color in DOMAINS:
            d = DevelopmentalDomain(school_id=school.id, key=key, name=name, color_hint=color)
            db.add(d)
            domains.append(d)
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

        students_data = [
            ("Zayan Khan", date(2021, 3, 12), "zayan.parent@example.com"),
            ("Ibrahim Malik", date(2021, 6, 2), "ibrahim.parent@example.com"),
        ]

        for full_name, dob, parent_email in students_data:
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
        print("Seeded: school, teacher (sama@civitas.edu.pk), class, 2 students + parents.")
        print("All demo passwords: changeme123")

    finally:
        db.close()


if __name__ == "__main__":
    run()
