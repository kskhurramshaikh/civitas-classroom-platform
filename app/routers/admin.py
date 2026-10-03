"""
One-off admin utilities, plus the Teacher Voice Screen conversation
log (see app/models.VoiceConversationLog and
app/services/conversation_log.py) — the raw feed and a quick summary
of where teachers ask for something the voice screen can't yet do,
meant as the input for deciding what to build next.

/admin/seed-demo is protected by SEED_TOKEN: if that env var isn't set
on the deployment, this endpoint always rejects, regardless of what
token is passed. Once used, consider unsetting SEED_TOKEN on Render to
close it off again — seed() is idempotent either way (a second call
is a no-op).

/admin/voice-logs* are DELIBERATELY left open, no login or token — the
point of this log is to be checked often while building, the same
no-friction way the standalone ZEC tracker dashboards work (open the
page, see the data). This is fine while Civitas is still private/
pre-launch with no real student or parent data flowing through it.
BEFORE this goes live to real teachers/parents, put real auth back on
these three routes — the raw feed includes verbatim transcripts.
"""
import csv
import io
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.models import VoiceConversationLog
from app.schemas import VoiceConversationLogOut, VoiceConversationLogSummary
from app.services.seed import seed

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/seed-demo")
def seed_demo(token: str = Query(...)):
    if not settings.seed_token or token != settings.seed_token:
        raise HTTPException(status_code=403, detail="Invalid or missing token")

    db: Session = SessionLocal()
    try:
        seeded = seed(db)
    finally:
        db.close()

    if seeded:
        return {"status": "seeded"}
    return {"status": "already seeded, skipped"}


def _voice_logs_query(
    db: Session,
    friction_only: bool = False,
    class_section_id: Optional[str] = None,
    source: Optional[str] = None,
):
    q = db.query(VoiceConversationLog)
    if friction_only:
        q = q.filter(VoiceConversationLog.friction.is_(True))
    if class_section_id:
        q = q.filter(VoiceConversationLog.class_section_id == class_section_id)
    if source:
        q = q.filter(VoiceConversationLog.source == source)
    return q


@router.get("/voice-logs", response_model=list[VoiceConversationLogOut])
def list_voice_logs(
    friction_only: bool = False,
    class_section_id: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    Raw feed of teacher<->voice-screen turns, newest first — exactly
    what was said and said back on every turn. Filter friction_only=
    true to see just the turns where the system gave up on the
    teacher's request (couldn't match a name, lost track of state,
    didn't understand) instead of fulfilling it.
    """
    q = _voice_logs_query(db, friction_only, class_section_id, source)
    return q.order_by(VoiceConversationLog.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/voice-logs/summary", response_model=VoiceConversationLogSummary)
def voice_logs_summary(
    class_section_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    How often the voice screen can't do what a teacher asked, and why
    — the fastest way to see where to invest next without reading
    every log line one at a time.
    """
    base = _voice_logs_query(db, class_section_id=class_section_id)
    total = base.count()
    friction_total = base.filter(VoiceConversationLog.friction.is_(True)).count()

    by_reason = dict(
        base.filter(VoiceConversationLog.friction.is_(True))
        .with_entities(VoiceConversationLog.friction_reason, func.count(VoiceConversationLog.id))
        .group_by(VoiceConversationLog.friction_reason)
        .all()
    )
    by_source = dict(
        base.with_entities(VoiceConversationLog.source, func.count(VoiceConversationLog.id))
        .group_by(VoiceConversationLog.source)
        .all()
    )

    return VoiceConversationLogSummary(
        total_turns=total,
        friction_turns=friction_total,
        friction_rate=round(friction_total / total, 4) if total else 0.0,
        by_friction_reason={(k or "unknown"): v for k, v in by_reason.items()},
        by_source=by_source,
    )


@router.get("/voice-logs/export.csv")
def export_voice_logs_csv(
    friction_only: bool = False,
    class_section_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """CSV export of the raw log, for pulling into a spreadsheet for deeper review."""
    rows = (
        _voice_logs_query(db, friction_only, class_section_id)
        .order_by(VoiceConversationLog.created_at.desc())
        .all()
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "created_at", "source", "teacher_id", "class_section_id", "student_id",
        "transcript", "speak", "pending_action_in", "pending_action_out",
        "ui_action", "saved", "friction", "friction_reason", "latency_ms",
    ])
    for r in rows:
        writer.writerow([
            r.created_at.isoformat(), r.source, r.teacher_id, r.class_section_id, r.student_id,
            r.transcript, r.speak, r.pending_action_in, r.pending_action_out,
            r.ui_action, r.saved, r.friction, r.friction_reason, r.latency_ms,
        ])
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=voice_conversation_logs.csv"},
    )
