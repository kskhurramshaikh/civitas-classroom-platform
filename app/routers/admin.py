"""
One-off admin utilities — currently just a way to seed demo data on a
live deploy that has no Shell access (e.g. Render's free plan).

Protected by SEED_TOKEN: if that env var isn't set on the deployment,
this endpoint always rejects, regardless of what token is passed. Once
used, consider unsetting SEED_TOKEN on Render to close it off again —
seed() is idempotent either way (a second call is a no-op).
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
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
