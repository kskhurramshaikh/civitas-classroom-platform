"""
Voice-dictated weekly entry parsing.

Design intent: voice is the PRIMARY way a teacher adds a weekly card —
the typed add-card form is the fallback, used less and less as this
gets trusted. The teacher just talks naturally while a student is
pulled up on the voice screen ("Zayan sorted blocks by color today
without being asked, maybe an 80, still mixes up square and
rectangle" or "homework this week — practice counting past twelve
with him at home") and this turns that into a structured draft.

It is never auto-saved: the existing add-card form fields get filled
in and the teacher still taps Save, so a misheard word or a wrong
guess is always caught before anything is written to the record.
"""
import json
import re

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Student, DevelopmentalDomain, ClassSection

SYSTEM_PROMPT = """You turn a kindergarten teacher's SPOKEN, informal note about one child into \
a structured draft for her classroom app. She is talking naturally, not dictating a form — \
extract her meaning, don't expect exact phrasing or field names.

Return ONLY a single JSON object (no markdown fences, no commentary) with this exact shape:
{{
  "entry_type": "progress_note" | "reinforcement" | "unclear",
  "domain_key": "<one of the domain keys below that best fits, or null if genuinely unclear>",
  "observation": "<a clean one/two sentence version of what she observed in class, or null>",
  "needs_improvement": "<what the child needs to work on, or null if not mentioned>",
  "stage_score": <integer 0-100 reflecting how she described the child's progress, or null if \
she gave no sense of it at all — higher means more confident/independent, lower means still \
struggling>,
  "title": "<a short, parent-facing homework title, only if entry_type is reinforcement, else null>",
  "instructions": "<what the parent should practice at home, only if entry_type is reinforcement, else null>"
}}

Use "reinforcement" when she's describing something for the PARENT to practice at home. Use \
"progress_note" when she's describing what she observed IN CLASS this week. Use "unclear" only \
if the transcript has no real observation in it at all (e.g. a stray fragment).

Domains for this class: {domain_list}

Child: {student_name}"""


def _heuristic_parse(transcript: str) -> dict:
    """No-AI-key fallback (e.g. local dev with no OPENROUTER_API_KEY) —
    a plain keyword heuristic so this still returns something usable
    instead of nothing."""
    lower = transcript.lower()
    is_homework = any(
        phrase in lower
        for phrase in ("homework", "at home", "practice at home", "with him at home", "with her at home")
    )
    if is_homework:
        return {
            "entry_type": "reinforcement",
            "domain_key": None,
            "title": transcript[:60],
            "instructions": transcript,
        }
    return {
        "entry_type": "progress_note",
        "domain_key": None,
        "observation": transcript,
        "needs_improvement": None,
        "stage_score": None,
    }


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    return json.loads(text)


async def parse_voice_entry(db: Session, student: Student, transcript: str) -> dict:
    class_section = db.query(ClassSection).filter(ClassSection.id == student.class_section_id).first()
    domains = (
        db.query(DevelopmentalDomain)
        .filter(DevelopmentalDomain.school_id == class_section.school_id)
        .all()
        if class_section
        else []
    )
    domain_by_key = {d.key: d for d in domains}

    if not settings.openrouter_api_key:
        parsed = _heuristic_parse(transcript)
    else:
        domain_list = ", ".join(f"{d.key} ({d.name})" for d in domains) or "(none configured)"
        system_prompt = SYSTEM_PROMPT.format(domain_list=domain_list, student_name=student.full_name)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{settings.openrouter_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                    json={
                        "model": settings.openrouter_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": transcript},
                        ],
                    },
                )
                resp.raise_for_status()
                raw = resp.json()["choices"][0]["message"]["content"]
            parsed = _extract_json(raw)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            # Never fail the whole voice entry over a model/network hiccup —
            # degrade to the heuristic so the teacher still gets a draft.
            parsed = _heuristic_parse(transcript)

    domain = domain_by_key.get(parsed.get("domain_key"))
    score = parsed.get("stage_score")
    try:
        score = int(score) if score is not None else None
        if score is not None:
            score = max(0, min(100, score))
    except (TypeError, ValueError):
        score = None

    return {
        "entry_type": parsed.get("entry_type") or "unclear",
        "domain_id": domain.id if domain else None,
        "observation": parsed.get("observation"),
        "needs_improvement": parsed.get("needs_improvement"),
        "stage_score": score,
        "title": parsed.get("title"),
        "instructions": parsed.get("instructions"),
        "raw_transcript": transcript,
    }
