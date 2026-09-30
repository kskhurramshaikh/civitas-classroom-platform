"""
Teacher Digital Twin — Phase 1 stub.

Design intent (carried over from the pitch prototype, now made real):
the assistant answers ONLY from a specific student's actual recorded
notes (progression cards + homework cards) and that teacher's own
persona/voice notes. It must not invent developmental claims about a
child. When the grounded context doesn't clearly cover the question,
it says so and escalates to the real teacher rather than guessing —
that boundary is enforced here in code, not left to the model's
judgment alone, by requiring the model to emit an explicit sentinel
when it cannot ground an answer.

Phase 2 should extend the grounding context with a proper retrieval
step across more history and, per teacher, with richer persona
configuration (see Teacher.persona_voice_notes).
"""
import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ProgressionCard, HomeworkCard, Teacher, Student, DevelopmentalDomain

ESCALATE_SENTINEL = "ESCALATE:"

SYSTEM_PROMPT_TEMPLATE = """You are {teacher_name}'s classroom assistant, speaking to a parent \
about their child, {student_name}.

You may ONLY use the notes below — real observations {teacher_name} recorded. Never invent \
developmental claims, diagnoses, or comparisons to other children that are not grounded in \
these notes. Keep your tone warm and plain, the way a caring teacher would talk to a parent \
in a two-minute conversation, not a report.

If the parent's question is not clearly answerable from these notes, or asks for something \
that genuinely needs the teacher's own judgment (a concern about development, a request \
outside these notes, anything sensitive), respond with EXACTLY this format and nothing else:
{sentinel} <one warm sentence telling the parent this needs {teacher_name} personally, and \
that it's been flagged to her>

Teacher's own voice/style notes: {persona_notes}

{student_name}'s recorded notes this term:
{context}
"""


def _build_context(db: Session, student_id: str) -> tuple[str, str, str]:
    student = db.query(Student).filter(Student.id == student_id).first()
    progression = (
        db.query(ProgressionCard)
        .filter(ProgressionCard.student_id == student_id)
        .order_by(ProgressionCard.week_start.desc())
        .limit(20)
        .all()
    )
    homework = (
        db.query(HomeworkCard)
        .filter(HomeworkCard.student_id == student_id)
        .order_by(HomeworkCard.week_start.desc())
        .limit(10)
        .all()
    )

    teacher = None
    if progression:
        teacher = db.query(Teacher).filter(Teacher.id == progression[0].teacher_id).first()
    elif homework:
        teacher = db.query(Teacher).filter(Teacher.id == homework[0].teacher_id).first()

    domain_cache = {d.id: d for d in db.query(DevelopmentalDomain).all()}

    lines = []
    for card in progression:
        domain = domain_cache.get(card.domain_id)
        domain_name = domain.name if domain else "General"
        lines.append(f"- [{card.week_start}] {domain_name}: {card.observation}"
                      + (f" (needs work: {card.needs_improvement})" if card.needs_improvement else ""))
    for card in homework:
        domain = domain_cache.get(card.domain_id)
        domain_name = domain.name if domain else "General"
        lines.append(f"- [{card.week_start}] Homework ({domain_name}) — {card.title}: {card.instructions}")

    context = "\n".join(lines) if lines else "(no notes recorded yet)"
    student_name = student.full_name if student else "the student"
    teacher_name = teacher.display_name if teacher else "the teacher"
    persona_notes = teacher.persona_voice_notes if teacher and teacher.persona_voice_notes else "(none set yet)"

    return context, student_name, teacher_name, persona_notes


async def ask_digital_twin(db: Session, student_id: str, message: str) -> tuple[str, bool]:
    context, student_name, teacher_name, persona_notes = _build_context(db, student_id)

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        teacher_name=teacher_name,
        student_name=student_name,
        persona_notes=persona_notes,
        context=context,
        sentinel=ESCALATE_SENTINEL,
    )

    if not settings.openrouter_api_key:
        # No key configured yet — fail safe to escalation rather than
        # a fabricated answer, and say so plainly for local dev.
        return (
            f"(Dev mode — no OPENROUTER_API_KEY set) This would normally be answered by "
            f"{teacher_name}'s assistant. For now, flagging to {teacher_name} directly.",
            True,
        )

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": settings.openrouter_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        reply = data["choices"][0]["message"]["content"].strip()

    if reply.startswith(ESCALATE_SENTINEL):
        return reply[len(ESCALATE_SENTINEL):].strip(), True

    return reply, False
