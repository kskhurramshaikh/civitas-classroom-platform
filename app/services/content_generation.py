"""
Phase 2: AI content-generation pipeline for gamified reinforcement.

Design intent (per the explicit "bespoke per note" decision): every
HomeworkCard a teacher writes gets its own AI-generated activity —
not a generic template filled with the card's title. The model writes
fresh content (a counting drill's exact numbers, a scenario's exact
wording) grounded in that specific card's instructions and domain,
optionally informed by the student's own recent progression notes so
the difficulty/framing actually fits the child.

That bespoke content is then rendered by one of a small, fixed set of
reusable client-side "engines" (see engine_type below) — the content
is unique per card, the *rendering shape* is reused. This is what
makes bespoke-per-note generation practical at platform scale instead
of needing a hand-built game per homework card.
"""
import json
import re

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import HomeworkCard, ProgressionCard, DevelopmentalDomain, Student, GeneratedActivity

SYSTEM_PROMPT = """You design short, playful home-practice activities for parents of \
kindergarten-age children, based on a teacher's homework note.

Return ONLY a single JSON object (no markdown fences, no commentary) with this exact shape:

{
  "engine_type": "drill_sequence" | "scenario_choice",
  "title": "short, fun title a parent would see",
  "instructions_for_parent": "1-2 warm sentences telling the parent how to run this with their child",
  "content": { ... engine-specific payload, see below ... }
}

Choose "drill_sequence" for anything with a right/wrong answer practiced in a short repeatable \
sequence (counting, letter sounds, shape/color recognition, simple sequencing). Its "content" must be:
{
  "items": [
    {"prompt": "what the child is asked/shown, e.g. 'What comes after 12?'", "answer": "the correct answer", \
"distractors": ["1-3 plausible wrong answers matching the child's actual error pattern when known"]}
  ]
}
Include 5-8 items, ordered from easiest to hardest, actually exercising the specific gap the teacher \
described (e.g. if the note says the child skips 13 after 12, the items must drill exactly that boundary).

Choose "scenario_choice" for social/emotional, motor, self-help, or creative skills with no single \
right answer. Its "content" must be:
{
  "scenarios": [
    {"scenario": "a short relatable situation the child might face", \
"options": ["2-3 reasonable things the child could do or say — none marked wrong"], \
"reflection": "one gentle question for the parent to ask afterward", \
"parent_talk_prompt": "one line coaching the parent on how to bring this up naturally"}
  ]
}
Include 2-4 scenarios.

Ground every item/scenario in the teacher's actual note below — do not invent unrelated skills."""


def _build_user_prompt(homework: HomeworkCard, student_name: str, domain_name: str, recent_notes: str) -> str:
    return (
        f"Child: {student_name}\n"
        f"Domain: {domain_name}\n"
        f"This week's homework note from the teacher — \"{homework.title}\": {homework.instructions}\n\n"
        f"Recent related progression notes (for context, may be empty):\n{recent_notes}"
    )


def _extract_json(text: str) -> dict:
    text = text.strip()
    # Strip a markdown fence if the model added one despite instructions.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    return json.loads(text)


async def generate_activity_for_homework(db: Session, homework: HomeworkCard) -> GeneratedActivity:
    student = db.query(Student).filter(Student.id == homework.student_id).first()
    domain = db.query(DevelopmentalDomain).filter(DevelopmentalDomain.id == homework.domain_id).first()
    student_name = student.full_name if student else "the child"
    domain_name = domain.name if domain else "General"

    recent = (
        db.query(ProgressionCard)
        .filter(ProgressionCard.student_id == homework.student_id, ProgressionCard.domain_id == homework.domain_id)
        .order_by(ProgressionCard.week_start.desc())
        .limit(5)
        .all()
    )
    recent_notes = "\n".join(
        f"- [{c.week_start}] {c.observation}" + (f" (needs work: {c.needs_improvement})" if c.needs_improvement else "")
        for c in recent
    ) or "(none)"

    user_prompt = _build_user_prompt(homework, student_name, domain_name, recent_notes)

    if not settings.openrouter_api_key:
        activity = GeneratedActivity(
            homework_card_id=homework.id,
            engine_type="text_fallback",
            title=homework.title,
            instructions_for_parent=(
                "(Dev mode — no OPENROUTER_API_KEY set) Practice this with your child using the "
                f"teacher's note directly: {homework.instructions}"
            ),
            content_json=json.dumps({}),
        )
        db.add(activity)
        db.commit()
        db.refresh(activity)
        return activity

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": settings.openrouter_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]

    try:
        parsed = _extract_json(raw)
        engine_type = parsed["engine_type"]
        if engine_type not in ("drill_sequence", "scenario_choice"):
            raise ValueError(f"unknown engine_type {engine_type!r}")
        activity = GeneratedActivity(
            homework_card_id=homework.id,
            engine_type=engine_type,
            title=parsed.get("title", homework.title),
            instructions_for_parent=parsed.get("instructions_for_parent"),
            content_json=json.dumps(parsed.get("content", {})),
        )
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        # The model didn't return well-formed structured content —
        # degrade to something still useful rather than failing the
        # whole homework-card creation.
        activity = GeneratedActivity(
            homework_card_id=homework.id,
            engine_type="text_fallback",
            title=homework.title,
            instructions_for_parent=raw.strip()[:2000],
            content_json=json.dumps({}),
        )

    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity
