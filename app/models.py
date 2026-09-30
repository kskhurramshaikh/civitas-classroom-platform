import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Column, String, Text, Date, DateTime, ForeignKey, Enum, Integer,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class Role(str, enum.Enum):
    admin = "admin"
    teacher = "teacher"
    parent = "parent"


class School(Base):
    __tablename__ = "schools"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    classes = relationship("ClassSection", back_populates="school")
    users = relationship("User", back_populates="school")


class User(Base):
    """
    A logged-in account. A teacher account is linked 1:1 to a Teacher
    profile (which holds the persona/digital-twin config). A parent
    account is linked to one or more students via ParentStudentLink —
    most parents will have exactly one, but siblings at the same school
    are supported without a schema change.
    """
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    school_id = Column(UUID(as_uuid=False), ForeignKey("schools.id"), nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(Enum(Role), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    school = relationship("School", back_populates="users")
    teacher_profile = relationship("Teacher", back_populates="user", uselist=False)
    parent_links = relationship("ParentStudentLink", back_populates="parent_user")


class Teacher(Base):
    """
    Profile + digital-twin persona config for a teacher account.
    Kept separate from User so persona fields don't bloat the auth table,
    and so a teacher can exist before/without a login during onboarding.
    """
    __tablename__ = "teachers"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), unique=True, nullable=False)
    display_name = Column(String, nullable=False)   # e.g. "Ms. Sama"
    persona_voice_notes = Column(Text, nullable=True)  # tone/style notes used to ground the twin
    voice_gender = Column(String, nullable=True)       # for future TTS persona selection

    user = relationship("User", back_populates="teacher_profile")
    classes = relationship("ClassSection", back_populates="teacher")


class ClassSection(Base):
    __tablename__ = "class_sections"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    school_id = Column(UUID(as_uuid=False), ForeignKey("schools.id"), nullable=False)
    teacher_id = Column(UUID(as_uuid=False), ForeignKey("teachers.id"), nullable=False)
    name = Column(String, nullable=False)   # e.g. "Kindergarten B"
    created_at = Column(DateTime, default=datetime.utcnow)

    school = relationship("School", back_populates="classes")
    teacher = relationship("Teacher", back_populates="classes")
    students = relationship("Student", back_populates="class_section")


class Student(Base):
    __tablename__ = "students"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    class_section_id = Column(UUID(as_uuid=False), ForeignKey("class_sections.id"), nullable=False)
    full_name = Column(String, nullable=False)
    date_of_birth = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    class_section = relationship("ClassSection", back_populates="students")
    parent_links = relationship("ParentStudentLink", back_populates="student")
    progression_cards = relationship("ProgressionCard", back_populates="student")
    homework_cards = relationship("HomeworkCard", back_populates="student")


class ParentStudentLink(Base):
    """Many-to-many: a parent user can have multiple children; a child
    can (eventually) have multiple guardian accounts."""
    __tablename__ = "parent_student_links"
    __table_args__ = (UniqueConstraint("parent_user_id", "student_id", name="uq_parent_student"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    parent_user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    student_id = Column(UUID(as_uuid=False), ForeignKey("students.id"), nullable=False)

    parent_user = relationship("User", back_populates="parent_links")
    student = relationship("Student", back_populates="parent_links")


class DevelopmentalDomain(Base):
    """
    Fixed reference list (Words & Stories, Numbers & Patterns, etc.) —
    seeded once per school so progression cards can tag which domain
    they're about. Kept as its own table (not a hardcoded enum) so a
    school can eventually add or rename domains without a migration.
    """
    __tablename__ = "developmental_domains"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    school_id = Column(UUID(as_uuid=False), ForeignKey("schools.id"), nullable=False)
    key = Column(String, nullable=False)     # e.g. "numbers"
    name = Column(String, nullable=False)    # e.g. "Numbers & Patterns"
    color_hint = Column(String, nullable=True)  # design token reused from the parent app


class ProgressionCard(Base):
    """
    One weekly, teacher-authored note about a student in one domain.
    This is the in-class record — visible to the teacher (and, in
    aggregate, surfaced to the parent through the Learning Garden view).
    """
    __tablename__ = "progression_cards"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    student_id = Column(UUID(as_uuid=False), ForeignKey("students.id"), nullable=False)
    domain_id = Column(UUID(as_uuid=False), ForeignKey("developmental_domains.id"), nullable=False)
    teacher_id = Column(UUID(as_uuid=False), ForeignKey("teachers.id"), nullable=False)
    week_start = Column(Date, nullable=False)   # Monday of the observed week
    observation = Column(Text, nullable=False)  # what the teacher actually saw
    needs_improvement = Column(Text, nullable=True)  # where the child needs work, if anything
    stage_score = Column(Integer, nullable=True)  # 0-100, drives "sprouting/growing/bloom" label
    created_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("Student", back_populates="progression_cards")


class HomeworkCard(Base):
    """
    One weekly, teacher-authored homework/reinforcement assignment for
    a student — visible to that student's parent(s). This is the card
    that can spawn a generated gamified activity (Phase 2).
    """
    __tablename__ = "homework_cards"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    student_id = Column(UUID(as_uuid=False), ForeignKey("students.id"), nullable=False)
    domain_id = Column(UUID(as_uuid=False), ForeignKey("developmental_domains.id"), nullable=False)
    teacher_id = Column(UUID(as_uuid=False), ForeignKey("teachers.id"), nullable=False)
    week_start = Column(Date, nullable=False)
    title = Column(String, nullable=False)
    instructions = Column(Text, nullable=False)   # what the teacher wants practiced at home
    generated_activity_id = Column(UUID(as_uuid=False), nullable=True)  # Phase 2 FK once that table exists
    created_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("Student", back_populates="homework_cards")


class GeneratedActivity(Base):
    """
    Phase 2: the AI-generated, bespoke gamified reinforcement activity
    for one HomeworkCard. Generated once per homework card (see
    app/services/content_generation.py) and rendered client-side by
    one of a small set of reusable "engines" identified by
    engine_type — NOT a fixed template: the content itself
    (items/scenarios/etc.) is written fresh per card by the model,
    only the rendering shape is reused.

    engine_type is currently one of:
      - "drill_sequence"   e.g. a counting/sequence drill with a quiz
                            (modeled on the Teen Number Trail prototype)
      - "scenario_choice"  e.g. social-skill scenario cards with
                            non-scored options (modeled on Friendship Path)
      - "text_fallback"    the model didn't return parseable structured
                            content; instructions_for_parent still holds
                            something useful to read.

    content_json holds the engine-specific payload as a JSON string
    (kept as text rather than a JSON column so this works unchanged on
    SQLite too, which local testing uses).

    homework_card_id is a plain reference, not a formal ForeignKey —
    same as HomeworkCard.generated_activity_id — since this table is
    new and Phase 1 has no migrations yet (see app/main.py).
    """
    __tablename__ = "generated_activities"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    homework_card_id = Column(UUID(as_uuid=False), nullable=False)
    engine_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    instructions_for_parent = Column(Text, nullable=True)
    content_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Term(Base):
    """
    A teacher's term planner for one class: a start date plus a number
    of weeks. Creating a Term auto-generates its TermWeek rows (one per
    week, Monday-aligned) so the teacher can plan ahead week by week
    rather than typing a raw date every time she adds a card. The actual
    weekly records (ProgressionCard, HomeworkCard) stay keyed by
    week_start exactly as before — a Term just gives the UI a ready-made
    list of weeks to plan against and navigate.
    """
    __tablename__ = "terms"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    class_section_id = Column(UUID(as_uuid=False), ForeignKey("class_sections.id"), nullable=False)
    name = Column(String, nullable=False)          # e.g. "Term 1"
    start_date = Column(Date, nullable=False)       # Monday of week 1
    num_weeks = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    weeks = relationship("TermWeek", back_populates="term", order_by="TermWeek.week_number")


class TermWeek(Base):
    __tablename__ = "term_weeks"
    __table_args__ = (UniqueConstraint("term_id", "week_number", name="uq_term_week_number"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    term_id = Column(UUID(as_uuid=False), ForeignKey("terms.id"), nullable=False)
    week_number = Column(Integer, nullable=False)   # 1-based
    week_start = Column(Date, nullable=False)        # Monday of that week

    term = relationship("Term", back_populates="weeks")
    plans = relationship("WeekPlan", back_populates="term_week")


class WeekPlan(Base):
    """
    A teacher's pre-planned focus/topic for one developmental domain in
    one week of a term — filled in ahead of time while building the
    term planner. Distinct from ProgressionCard.observation, which is
    the actual note recorded after the week happens.
    """
    __tablename__ = "week_plans"
    __table_args__ = (UniqueConstraint("term_week_id", "domain_id", name="uq_week_plan_domain"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    term_week_id = Column(UUID(as_uuid=False), ForeignKey("term_weeks.id"), nullable=False)
    domain_id = Column(UUID(as_uuid=False), ForeignKey("developmental_domains.id"), nullable=False)
    focus = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    term_week = relationship("TermWeek", back_populates="plans")
