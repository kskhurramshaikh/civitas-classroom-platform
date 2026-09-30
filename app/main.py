from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import auth, classes, progression, homework, twin

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


@app.get("/health")
def health():
    return {"status": "ok"}
