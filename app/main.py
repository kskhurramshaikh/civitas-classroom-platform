import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.routers import auth, classes, progression, homework, twin, admin, teachers, activities, domains

# Phase 1: create tables directly from the models on startup. This is
# intentionally not Alembic yet — fine for getting a first deploy up
# and demoing against real data, but migrations should replace this
# before the schema needs to change under real production data.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Civitas Classroom Platform API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the actual frontend origin once deployed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(classes.router)
app.include_router(progression.router)
app.include_router(homework.router)
app.include_router(twin.router)
app.include_router(admin.router)
app.include_router(teachers.router)
app.include_router(activities.router)
app.include_router(domains.router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Phase 2 frontends — Teacher Voice Screen and the parent app — served
# as static files straight from this API so there's no separate
# static site/host to wire up yet. /web/teacher.html and
# /web/parent.html; both call this same API by relative path.
_web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
if os.path.isdir(_web_dir):
    app.mount("/web", StaticFiles(directory=_web_dir, html=True), name="web")
