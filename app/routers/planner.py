from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Role, Term, TermWeek, WeekPlan
from app.schemas import TermCreate, TermOut, WeekPlanCreate, WeekPlanOut, CurrentWeekOut
from app.security import require_role, get_current_user
from app.permissions import assert_teaches_class

router = APIRouter(tags=["planner"])


@router.post("/terms", response_model=TermOut, status_code=status.HTTP_201_CREATED)
def create_term(
    payload: TermCreate,
    user: User = Depends(require_role(Role.teacher, Role.admin)),
    db: Session = Depends(get_db),
):
    """
    Create a term planner for a class and auto-generate its weeks
    (Monday-aligned, starting from payload.start_date) so the teacher
    can plan ahead week by week instead of typing raw dates.
    """
    assert_teaches_class(db, user, payload.class_section_id)
    if payload.num_weeks < 1 or payload.num_weeks > 52:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="num_weeks must be between 1 and 52")

    term = Term(
        class_section_id=payload.class_section_id,
        name=payload.name,
        start_date=payload.start_date,
        num_weeks=payload.num_weeks,
    )
    db.add(term)
    db.flush()  # get term.id without a full commit yet

    for n in range(payload.num_weeks):
        db.add(TermWeek(
            term_id=term.id,
            week_number=n + 1,
            week_start=payload.start_date + timedelta(weeks=n),
        ))

    db.commit()
    db.refresh(term)
    return term


@router.get("/classes/{class_section_id}/terms", response_model=list[TermOut])
def list_terms(class_section_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_teaches_class(db, user, class_section_id)
    return (
        db.query(Term)
        .filter(Term.class_section_id == class_section_id)
        .order_by(Term.start_date.desc())
        .all()
    )


@router.get("/terms/{term_id}", response_model=TermOut)
def get_term(term_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    term = db.query(Term).filter(Term.id == term_id).first()
    if term is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Term not found")
    assert_teaches_class(db, user, term.class_section_id)
    return term


@router.put("/term-weeks/{term_week_id}/plan", response_model=WeekPlanOut)
def upsert_week_plan(
    term_week_id: str,
    payload: WeekPlanCreate,
    user: User = Depends(require_role(Role.teacher, Role.admin)),
    db: Session = Depends(get_db),
):
    """
    Set (or replace) the pre-planned focus for one domain in one week
    of a term. Upsert on (term_week_id, domain_id) since a teacher will
    naturally revise a plan while building it out.
    """
    term_week = db.query(TermWeek).filter(TermWeek.id == term_week_id).first()
    if term_week is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Week not found")
    term = db.query(Term).filter(Term.id == term_week.term_id).first()
    assert_teaches_class(db, user, term.class_section_id)

    plan = (
        db.query(WeekPlan)
        .filter(WeekPlan.term_week_id == term_week_id, WeekPlan.domain_id == payload.domain_id)
        .first()
    )
    if plan is None:
        plan = WeekPlan(term_week_id=term_week_id, domain_id=payload.domain_id, focus=payload.focus)
        db.add(plan)
    else:
        plan.focus = payload.focus

    db.commit()
    db.refresh(plan)
    return plan


@router.get("/classes/{class_section_id}/current-week", response_model=CurrentWeekOut)
def current_week(class_section_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    The Teacher Voice Screen's anchor: given today's date, which term
    week is "current" for this class, plus the full list of that
    term's weeks so the voice screen can offer prev/next navigation.

    If more than one term happens to overlap today (not the intended
    use, but not blocked by the schema either), the most recently
    created term wins.
    """
    assert_teaches_class(db, user, class_section_id)
    today = date.today()

    terms = (
        db.query(Term)
        .filter(Term.class_section_id == class_section_id)
        .order_by(Term.created_at.desc())
        .all()
    )

    for term in terms:
        term_end = term.start_date + timedelta(weeks=term.num_weeks)
        if term.start_date <= today < term_end:
            week = None
            for w in term.weeks:
                week_end = w.week_start + timedelta(weeks=1)
                if w.week_start <= today < week_end:
                    week = w
                    break
            if week is None:
                # Between weeks somehow (shouldn't normally happen) — fall back to the last week.
                week = term.weeks[-1] if term.weeks else None
            if week is not None:
                return CurrentWeekOut(
                    term_id=term.id,
                    term_name=term.name,
                    week_id=week.id,
                    week_number=week.week_number,
                    week_start=week.week_start,
                    all_weeks=term.weeks,
                )

    # No active term covers today — fall back to the most recent term's most recent week, if any.
    if terms and terms[0].weeks:
        term = terms[0]
        week = term.weeks[-1]
        return CurrentWeekOut(
            term_id=term.id,
            term_name=term.name,
            week_id=week.id,
            week_number=week.week_number,
            week_start=week.week_start,
            all_weeks=term.weeks,
        )

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No term planner set up for this class yet")
