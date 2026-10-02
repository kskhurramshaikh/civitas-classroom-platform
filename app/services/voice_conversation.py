"""
Conversational Teacher Voice Screen.

Design intent (explicit directive): the voice screen is the PRIMARY
way a teacher does everything on this screen — call on a student,
hear their current progress or reinforcement read back, move between
weeks, and dictate an update to a card — without needing to drop back
to the static add-card form underneath. The form stays, as the
fallback for typing, but the voice loop should be able to drive the
whole thing on its own, turn by turn, the way a person would talk to
an assistant rather than issue one fixed command at a time.

Design choice that keeps this safe and fast: the model is used ONLY
for two narrow jobs — (1) classifying what the teacher just asked for
and pulling out a student name / week number / domain hint, and (2)
turning a dictated replacement into structured fields. Every sentence
that reports back REAL data (today's progress note, this week's
reinforcement, a save confirmation) is composed here in plain Python
straight from the database rows — never phrased by the model — so a
parent or teacher never hears a hallucinated number or observation.

Conversation state is kept entirely on the frontend and round-tripped
on every call (active_student_id / active_week_number / pending_action
/ pending_payload) rather than stored server-side — this is a single
teacher, single device, one conversation at a time, so there is
nothing to gain from a server-side session store and a real cost
(another thing that can get out of sync) in having one.
"""
import json
import re
from datetime import date, timedelta

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Student, ClassSection, DevelopmentalDomain, ProgressionCard, HomeworkCard,
    Term, TermWeek, User,
)
from app.schemas import VoiceConverseRequest, VoiceConverseResponse
from app.services.content_generation import generate_activity_for_homework

YES_WORDS = re.compile(r"\b(yes|yeah|yep|yup|sure|correct|save it|save that|do it|go ahead|confirm)\b", re.I)
NO_WORDS = re.compile(r"\b(no|nah|nope|cancel|never mind|nevermind|don't|do not|stop|forget it)\b", re.I)


# ---------------------------------------------------------------- helpers

def _roster(db: Session, class_section_id: str) -> list[Student]:
    return db.query(Student).filter(Student.class_section_id == class_section_id).all()


def _find_student(roster: list[Student], name_guess: str | None, transcript: str):
    """Fuzzy first-name match, same spirit as the old matchAndCall — try the
    NLU's guess first, then fall back to scanning the raw transcript for any
    roster first name, so a dropped/garbled NLU field doesn't fail the whole
    turn."""
    candidates = [name_guess, transcript]
    for text in candidates:
        if not text:
            continue
        lower = text.lower()
        for s in roster:
            first = s.full_name.split(" ")[0].lower()
            if first in lower:
                return s
    return None


def _domains(db: Session, school_id: str) -> list[DevelopmentalDomain]:
    return db.query(DevelopmentalDomain).filter(DevelopmentalDomain.school_id == school_id).all()


def _term_and_weeks(db: Session, class_section_id: str):
    term = (
        db.query(Term)
        .filter(Term.class_section_id == class_section_id)
        .order_by(Term.created_at.desc())
        .first()
    )
    if term is None:
        return None, []
    weeks = db.query(TermWeek).filter(TermWeek.term_id == term.id).order_by(TermWeek.week_number).all()
    return term, weeks


def _current_week_number(weeks: list[TermWeek]) -> int | None:
    today = date.today()
    for w in weeks:
        if w.week_start <= today < w.week_start + timedelta(weeks=1):
            return w.week_number
    return weeks[-1].week_number if weeks else None


def _week_start_for_number(weeks: list[TermWeek], n: int):
    for w in weeks:
        if w.week_number == n:
            return w.week_start
    return None


def _latest_progression(db: Session, student_id: str) -> ProgressionCard | None:
    return (
        db.query(ProgressionCard)
        .filter(ProgressionCard.student_id == student_id)
        .order_by(ProgressionCard.week_start.desc())
        .first()
    )


def _cards_for_week(db: Session, student_id: str, week_start: date):
    progressions = (
        db.query(ProgressionCard)
        .filter(ProgressionCard.student_id == student_id, ProgressionCard.week_start == week_start)
        .all()
    )
    homeworks = (
        db.query(HomeworkCard)
        .filter(HomeworkCard.student_id == student_id, HomeworkCard.week_start == week_start)
        .all()
    )
    return progressions, homeworks


def _domain_name(domains: list[DevelopmentalDomain], domain_id: str | None) -> str:
    d = next((d for d in domains if d.id == domain_id), None)
    return d.name if d else "General"


async def _openrouter_json(system_prompt: str, user_text: str, fallback: dict) -> dict:
    if not settings.openrouter_api_key:
        return fallback
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{settings.openrouter_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                json={
                    "model": settings.openrouter_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_text},
                    ],
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
        text = raw.strip()
        fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        return json.loads(text)
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError, IndexError):
        return fallback


INTENT_PROMPT = """You listen to one sentence a kindergarten teacher just said to her classroom \
voice assistant and classify it. Return ONLY JSON, no markdown fences, no commentary:

{{
  "intent": "call_student" | "show_week" | "show_progress" | "update_reinforcement" | \
"update_progress" | "general_dictation" | "unclear",
  "student_name": "<a name mentioned, or null>",
  "week_number": <integer week number mentioned (convert words like 'week three' to 3), or null>,
  "domain_hint": "<a developmental area she mentioned or implied, in her own words, or null>"
}}

Guidance:
- "call_student": she wants to pull up a student by name ("call on Zayan", "let's look at Ibrahim").
- "show_week": she wants to see/hear a specific week's card ("show me week 3", "what about week 4").
- "show_progress": she's asking how a student is doing generally, with no specific week named.
- "update_reinforcement": she wants to change/set the homework/reinforcement for a week.
- "update_progress": she wants to change/add a progress note for a week.
- "general_dictation": she's just describing what she observed or what to practice at home, as a \
free-form note, without asking to update a specific existing week's card.
- "unclear": none of the above fit, or the sentence is empty/a stray fragment.

Students in this class: {roster_names}
"""

CONTENT_PROMPT = """A kindergarten teacher just dictated a replacement for her classroom app. \
Turn it into structured fields. Return ONLY JSON, no markdown fences, no commentary:

{schema}

Domains for this class: {domain_list}
"""


async def _classify_intent(transcript: str, roster: list[Student]) -> dict:
    fallback = {"intent": "unclear", "student_name": None, "week_number": None, "domain_hint": None}
    names = ", ".join(s.full_name for s in roster) or "(no students yet)"
    result = await _openrouter_json(INTENT_PROMPT.format(roster_names=names), transcript, fallback)
    for key, default in fallback.items():
        result.setdefault(key, default)
    return result


async def _extract_reinforcement(transcript: str, domains: list[DevelopmentalDomain]) -> dict:
    schema = (
        '{"title": "<short, parent-facing homework title>", '
        '"instructions": "<what the parent should practice at home>", '
        '"domain_key": "<best matching domain key below, or null>"}'
    )
    domain_list = ", ".join(f"{d.key} ({d.name})" for d in domains) or "(none configured)"
    fallback = {"title": transcript[:60], "instructions": transcript, "domain_key": None}
    result = await _openrouter_json(CONTENT_PROMPT.format(schema=schema, domain_list=domain_list), transcript, fallback)
    for key, default in fallback.items():
        result.setdefault(key, default)
    return result


async def _extract_progress(transcript: str, domains: list[DevelopmentalDomain]) -> dict:
    schema = (
        '{"observation": "<clean one/two sentence version of what she observed>", '
        '"needs_improvement": "<what the child needs to work on, or null>", '
        '"stage_score": <integer 0-100 reflecting how she described it, or null>, '
        '"domain_key": "<best matching domain key below, or null>"}'
    )
    domain_list = ", ".join(f"{d.key} ({d.name})" for d in domains) or "(none configured)"
    fallback = {"observation": transcript, "needs_improvement": None, "stage_score": None, "domain_key": None}
    result = await _openrouter_json(CONTENT_PROMPT.format(schema=schema, domain_list=domain_list), transcript, fallback)
    for key, default in fallback.items():
        result.setdefault(key, default)
    return result


def _week_label(n: int | None) -> str:
    return f"week {n}" if n else "this week"


# ---------------------------------------------------------------- main entrypoint

async def converse(db: Session, user: User, payload: VoiceConverseRequest) -> VoiceConverseResponse:
    class_section = db.query(ClassSection).filter(ClassSection.id == payload.class_section_id).first()
    roster = _roster(db, payload.class_section_id)
    domains = _domains(db, class_section.school_id) if class_section else []
    term, weeks = _term_and_weeks(db, payload.class_section_id)

    transcript = payload.transcript.strip()
    pending = payload.pending_action
    pending_payload = payload.pending_payload or {}
    active_student_id = payload.active_student_id
    active_week_number = payload.active_week_number

    def student_by_id(sid):
        return next((s for s in roster if s.id == sid), None)

    # ---- mid-flow: teacher is dictating replacement content ----
    if pending in ("awaiting_reinforcement_content", "awaiting_progress_content"):
        if NO_WORDS.search(transcript) and not YES_WORDS.search(transcript):
            return VoiceConverseResponse(
                speak="Okay, never mind — nothing changed.",
                active_student_id=active_student_id,
                active_week_number=active_week_number,
                ui_action="none",
                suggestions=["Call on another student", "Show this week"],
            )

        student = student_by_id(pending_payload.get("student_id"))
        week_number = pending_payload.get("week_number")
        week_start = pending_payload.get("week_start")

        if pending == "awaiting_reinforcement_content":
            extracted = await _extract_reinforcement(transcript, domains)
            domain = next((d for d in domains if d.key == extracted.get("domain_key")), None)
            domain_id = domain.id if domain else pending_payload.get("domain_id")
            draft = {
                "student_id": student.id if student else None,
                "week_number": week_number,
                "week_start": week_start,
                "domain_id": domain_id,
                "title": extracted.get("title") or transcript[:60],
                "instructions": extracted.get("instructions") or transcript,
            }
            speak = f'Here\'s the update: "{draft["title"]}" — {draft["instructions"]}. Should I save it?'
            return VoiceConverseResponse(
                speak=speak,
                active_student_id=active_student_id,
                active_week_number=active_week_number,
                pending_action="awaiting_confirm_reinforcement",
                pending_payload=draft,
                ui_action="none",
                suggestions=["Yes, save it", "Cancel"],
            )

        else:  # awaiting_progress_content
            extracted = await _extract_progress(transcript, domains)
            domain = next((d for d in domains if d.key == extracted.get("domain_key")), None)
            domain_id = domain.id if domain else pending_payload.get("domain_id")
            draft = {
                "student_id": student.id if student else None,
                "week_number": week_number,
                "week_start": week_start,
                "domain_id": domain_id,
                "observation": extracted.get("observation") or transcript,
                "needs_improvement": extracted.get("needs_improvement"),
                "stage_score": extracted.get("stage_score"),
            }
            score_txt = f' Score: {draft["stage_score"]}.' if draft["stage_score"] is not None else ""
            needs_txt = f' Needs work: {draft["needs_improvement"]}.' if draft["needs_improvement"] else ""
            speak = f'Here\'s the update: {draft["observation"]}{needs_txt}{score_txt} Should I save it?'
            return VoiceConverseResponse(
                speak=speak,
                active_student_id=active_student_id,
                active_week_number=active_week_number,
                pending_action="awaiting_confirm_progress",
                pending_payload=draft,
                ui_action="none",
                suggestions=["Yes, save it", "Cancel"],
            )

    # ---- mid-flow: confirming a save ----
    if pending in ("awaiting_confirm_reinforcement", "awaiting_confirm_progress"):
        if NO_WORDS.search(transcript) and not YES_WORDS.search(transcript):
            return VoiceConverseResponse(
                speak="Okay, I won't save that.",
                active_student_id=active_student_id,
                active_week_number=active_week_number,
                ui_action="none",
                suggestions=["Call on another student", "Show this week"],
            )
        if not YES_WORDS.search(transcript):
            # Didn't clearly hear yes or no — ask again rather than guessing.
            return VoiceConverseResponse(
                speak="Sorry, should I save that? Say yes or no.",
                active_student_id=active_student_id,
                active_week_number=active_week_number,
                pending_action=pending,
                pending_payload=pending_payload,
                ui_action="none",
                suggestions=["Yes, save it", "Cancel"],
            )

        student_id = pending_payload.get("student_id")
        week_start = pending_payload.get("week_start")
        domain_id = pending_payload.get("domain_id")

        if pending == "awaiting_confirm_reinforcement":
            if not (student_id and week_start and domain_id):
                return VoiceConverseResponse(
                    speak="I lost track of the domain for that — could you say the update again?",
                    active_student_id=active_student_id,
                    active_week_number=active_week_number,
                    ui_action="none",
                )
            card = (
                db.query(HomeworkCard)
                .filter(HomeworkCard.student_id == student_id, HomeworkCard.week_start == week_start,
                        HomeworkCard.domain_id == domain_id)
                .first()
            )
            if card is None:
                teacher = None
                from app.models import Teacher as TeacherModel
                teacher = db.query(TeacherModel).filter(TeacherModel.user_id == user.id).first()
                card = HomeworkCard(
                    student_id=student_id, domain_id=domain_id, week_start=week_start,
                    title=pending_payload["title"], instructions=pending_payload["instructions"],
                    teacher_id=teacher.id if teacher else None,
                )
                db.add(card)
            else:
                card.title = pending_payload["title"]
                card.instructions = pending_payload["instructions"]
            db.commit()
            db.refresh(card)
            try:
                activity = await generate_activity_for_homework(db, card)
                card.generated_activity_id = activity.id
                db.commit()
            except Exception:
                pass
            return VoiceConverseResponse(
                speak="Saved. The reinforcement is updated.",
                active_student_id=active_student_id,
                active_week_number=active_week_number,
                ui_action="focus_student",
                saved=True,
                suggestions=["Call on another student", "Show this week", "Update it again"],
            )

        else:  # awaiting_confirm_progress
            if not (student_id and week_start and domain_id):
                return VoiceConverseResponse(
                    speak="I lost track of the domain for that — could you say the update again?",
                    active_student_id=active_student_id,
                    active_week_number=active_week_number,
                    ui_action="none",
                )
            card = (
                db.query(ProgressionCard)
                .filter(ProgressionCard.student_id == student_id, ProgressionCard.week_start == week_start,
                        ProgressionCard.domain_id == domain_id)
                .first()
            )
            if card is None:
                from app.models import Teacher as TeacherModel
                teacher = db.query(TeacherModel).filter(TeacherModel.user_id == user.id).first()
                card = ProgressionCard(
                    student_id=student_id, domain_id=domain_id, week_start=week_start,
                    observation=pending_payload["observation"],
                    needs_improvement=pending_payload.get("needs_improvement"),
                    stage_score=pending_payload.get("stage_score"),
                    teacher_id=teacher.id if teacher else None,
                )
                db.add(card)
            else:
                card.observation = pending_payload["observation"]
                card.needs_improvement = pending_payload.get("needs_improvement")
                card.stage_score = pending_payload.get("stage_score")
            db.commit()
            return VoiceConverseResponse(
                speak="Saved. The progress note is updated.",
                active_student_id=active_student_id,
                active_week_number=active_week_number,
                ui_action="focus_student",
                saved=True,
                suggestions=["Call on another student", "Show this week", "Update it again"],
            )

    # ---- fresh command ----
    nlu = await _classify_intent(transcript, roster)
    intent = nlu.get("intent")

    if intent == "call_student":
        student = _find_student(roster, nlu.get("student_name"), transcript)
        if student is None:
            return VoiceConverseResponse(
                speak="I didn't catch a name I recognize. Try again, or tap a student.",
                active_student_id=active_student_id,
                active_week_number=active_week_number,
                ui_action="none",
            )
        latest = _latest_progression(db, student.id)
        first = student.full_name.split(" ")[0]
        if latest:
            domain_name = _domain_name(domains, latest.domain_id)
            speak = f"Calling on {first}. This week in {domain_name}: {latest.observation}"
        else:
            speak = f"Calling on {first}. No progress notes recorded yet."
        return VoiceConverseResponse(
            speak=speak,
            active_student_id=student.id,
            active_week_number=None,
            ui_action="focus_student",
            suggestions=[f"How is {first} doing", "Show week 3", "Update this week's reinforcement"],
        )

    if intent in ("show_progress", "show_week", "update_reinforcement", "update_progress", "general_dictation") \
            and not active_student_id:
        # try to pick up a student named in the same sentence before giving up
        student = _find_student(roster, nlu.get("student_name"), transcript)
        if student:
            active_student_id = student.id
        else:
            return VoiceConverseResponse(
                speak="Which student would you like first? Say their name.",
                active_student_id=active_student_id,
                active_week_number=active_week_number,
                ui_action="none",
            )

    student = student_by_id(active_student_id)
    if student is None:
        return VoiceConverseResponse(
            speak="Who would you like to talk about? Say a student's name.",
            ui_action="none",
        )
    first = student.full_name.split(" ")[0]

    if intent == "show_progress":
        latest = _latest_progression(db, student.id)
        if latest:
            domain_name = _domain_name(domains, latest.domain_id)
            needs_txt = f" Needs work: {latest.needs_improvement}." if latest.needs_improvement else ""
            speak = f"{first}'s latest note, {domain_name}: {latest.observation}{needs_txt}"
        else:
            speak = f"No progress notes recorded for {first} yet."
        return VoiceConverseResponse(
            speak=speak, active_student_id=student.id, active_week_number=active_week_number,
            ui_action="none", suggestions=["Show week 3", "Update this week's reinforcement"],
        )

    if intent == "show_week":
        week_number = nlu.get("week_number") or active_week_number or _current_week_number(weeks)
        if not weeks:
            return VoiceConverseResponse(
                speak="There's no term planner set up for this class yet.",
                active_student_id=student.id, ui_action="none",
            )
        week_start = _week_start_for_number(weeks, week_number)
        if week_start is None:
            return VoiceConverseResponse(
                speak=f"This term doesn't have a week {week_number}.",
                active_student_id=student.id, active_week_number=active_week_number, ui_action="none",
            )
        progressions, homeworks = _cards_for_week(db, student.id, week_start)
        parts = []
        for p in progressions:
            parts.append(f"{_domain_name(domains, p.domain_id)}: {p.observation}")
        for h in homeworks:
            parts.append(f"Homework ({_domain_name(domains, h.domain_id)}): {h.title} — {h.instructions}")
        body = " · ".join(parts) if parts else "Nothing recorded for this week yet."
        speak = f"Week {week_number} for {first}. {body}"
        return VoiceConverseResponse(
            speak=speak, active_student_id=student.id, active_week_number=week_number,
            active_week_start=week_start.isoformat(),
            ui_action="show_week",
            suggestions=["Update this week's reinforcement", "Next week", "Previous week"],
        )

    if intent == "update_reinforcement":
        week_number = nlu.get("week_number") or active_week_number or _current_week_number(weeks)
        week_start = _week_start_for_number(weeks, week_number) if weeks else None
        if week_start is None:
            return VoiceConverseResponse(
                speak="There's no term planner set up for this class yet, so I don't know which week that is.",
                active_student_id=student.id, ui_action="none",
            )
        _, homeworks = _cards_for_week(db, student.id, week_start)
        if len(homeworks) == 1:
            h = homeworks[0]
            speak = (f'Right now, {_week_label(week_number)}\'s reinforcement is "{h.title}": '
                     f'{h.instructions}. What would you like to change it to?')
            domain_id = h.domain_id
        elif len(homeworks) == 0:
            speak = f"There's no reinforcement set for {_week_label(week_number)} yet. What would you like it to be?"
            domain_id = None
        else:
            names = ", ".join(f'{_domain_name(domains, h.domain_id)} ("{h.title}")' for h in homeworks)
            speak = (f"{_week_label(week_number)} has more than one reinforcement set: {names}. "
                     f"Say which area you mean, then the update.")
            domain_id = None
        return VoiceConverseResponse(
            speak=speak, active_student_id=student.id, active_week_number=week_number,
            active_week_start=week_start.isoformat(),
            pending_action="awaiting_reinforcement_content",
            pending_payload={"student_id": student.id, "week_number": week_number,
                              "week_start": week_start.isoformat(), "domain_id": domain_id},
            ui_action="show_week",
        )

    if intent == "update_progress":
        week_number = nlu.get("week_number") or active_week_number or _current_week_number(weeks)
        week_start = _week_start_for_number(weeks, week_number) if weeks else None
        if week_start is None:
            return VoiceConverseResponse(
                speak="There's no term planner set up for this class yet, so I don't know which week that is.",
                active_student_id=student.id, ui_action="none",
            )
        progressions, _ = _cards_for_week(db, student.id, week_start)
        if len(progressions) == 1:
            p = progressions[0]
            needs_txt = f" Needs work: {p.needs_improvement}." if p.needs_improvement else ""
            speak = (f"Right now, {_week_label(week_number)}'s progress note is: {p.observation}{needs_txt} "
                      f"What would you like to change it to?")
            domain_id = p.domain_id
        elif len(progressions) == 0:
            speak = f"There's no progress note for {_week_label(week_number)} yet. What did you observe?"
            domain_id = None
        else:
            names = ", ".join(f'{_domain_name(domains, p.domain_id)}' for p in progressions)
            speak = (f"{_week_label(week_number)} already has notes in: {names}. "
                     f"Say which area you mean, then the update.")
            domain_id = None
        return VoiceConverseResponse(
            speak=speak, active_student_id=student.id, active_week_number=week_number,
            active_week_start=week_start.isoformat(),
            pending_action="awaiting_progress_content",
            pending_payload={"student_id": student.id, "week_number": week_number,
                              "week_start": week_start.isoformat(), "domain_id": domain_id},
            ui_action="show_week",
        )

    if intent == "general_dictation" and transcript:
        # Same free-form note capture as before, just folded into the
        # speak-then-confirm pattern instead of silently filling a form.
        week_number = active_week_number or _current_week_number(weeks)
        week_start = _week_start_for_number(weeks, week_number) if weeks else date.today()
        lower = transcript.lower()
        is_homework = any(p in lower for p in ("homework", "at home", "practice at home"))
        if is_homework:
            extracted = await _extract_reinforcement(transcript, domains)
            domain = next((d for d in domains if d.key == extracted.get("domain_key")), None)
            draft = {
                "student_id": student.id, "week_number": week_number,
                "week_start": week_start.isoformat() if hasattr(week_start, "isoformat") else week_start,
                "domain_id": domain.id if domain else None,
                "title": extracted.get("title") or transcript[:60],
                "instructions": extracted.get("instructions") or transcript,
            }
            speak = f'Here\'s the reinforcement: "{draft["title"]}" — {draft["instructions"]}. Should I save it?'
            return VoiceConverseResponse(
                speak=speak, active_student_id=student.id, active_week_number=week_number,
                pending_action="awaiting_confirm_reinforcement", pending_payload=draft,
                ui_action="none", suggestions=["Yes, save it", "Cancel"],
            )
        else:
            extracted = await _extract_progress(transcript, domains)
            domain = next((d for d in domains if d.key == extracted.get("domain_key")), None)
            draft = {
                "student_id": student.id, "week_number": week_number,
                "week_start": week_start.isoformat() if hasattr(week_start, "isoformat") else week_start,
                "domain_id": domain.id if domain else None,
                "observation": extracted.get("observation") or transcript,
                "needs_improvement": extracted.get("needs_improvement"),
                "stage_score": extracted.get("stage_score"),
            }
            score_txt = f' Score: {draft["stage_score"]}.' if draft["stage_score"] is not None else ""
            needs_txt = f' Needs work: {draft["needs_improvement"]}.' if draft["needs_improvement"] else ""
            speak = f'Here\'s the progress note: {draft["observation"]}{needs_txt}{score_txt} Should I save it?'
            return VoiceConverseResponse(
                speak=speak, active_student_id=student.id, active_week_number=week_number,
                pending_action="awaiting_confirm_progress", pending_payload=draft,
                ui_action="none", suggestions=["Yes, save it", "Cancel"],
            )

    return VoiceConverseResponse(
        speak="I didn't quite catch that. You can ask for a student, a week, or dictate a note.",
        active_student_id=active_student_id,
        active_week_number=active_week_number,
        ui_action="none",
    )
