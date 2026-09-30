# Civitas Classroom Platform

AI-native classroom platform connecting teachers, students, and parents —
built to replace paper-based progress notes and homework sheets with a
living, weekly, teacher-authored record that parents can act on, reinforced
through gamified practice and a teacher-grounded digital twin assistant.

## Phase 1 (this commit): backend foundation

- **Data model**: schools, users (teacher / parent / admin roles), classes,
  students, parent–student links, weekly progression cards, weekly
  homework cards, developmental domains.
- **Auth**: JWT-based login, password hashing, role-scoped access
  (a parent can only ever read their own child's data; a teacher only
  their own class).
- **Core API**: CRUD for classes, students, progression cards, homework
  cards.
- **Digital twin stub**: `/twin/chat` — answers grounded in a specific
  student's actual progression/homework notes, routed through OpenRouter
  so the model is swappable. Anything the grounded context can't answer
  confidently returns an escalation response rather than a guess.

Not yet built (Phase 2, pending review): the Teacher Voice Screen
(class command center with real voice "call upon a student"), the
AI content-generation pipeline for gamified reinforcement activities,
per-teacher persona configuration, and the parent-facing frontend wired
to real data instead of the standalone prototype
(`civitas-learning-garden.html`).

## Stack

- FastAPI (Python) — matches the stack decisions used on other active
  projects (ODDIN, NEXUS)
- PostgreSQL via SQLAlchemy
- JWT auth (python-jose + passlib/bcrypt)
- OpenRouter for the digital twin's model calls (model chosen by config,
  not hardcoded to one provider)
- Deploy target: Render

## Local setup

```bash
cp .env.example .env      # fill in DATABASE_URL, JWT_SECRET, OPENROUTER_API_KEY
pip install -r requirements.txt
uvicorn app.main:app --reload
```

On startup the app creates tables from the SQLAlchemy models directly
(no Alembic yet — intentional for Phase 1; migrations should be added
before this handles real production data in Phase 2).

## Seeding a first teacher + class

See `scripts/seed_demo.py` — creates one school, one teacher (Ms. Sana),
one class, and a handful of demo students so the API has something to
query immediately after first deploy.

## Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string |
| `JWT_SECRET` | Signing secret for auth tokens |
| `JWT_EXPIRE_MINUTES` | Access token lifetime (default 60) |
| `OPENROUTER_API_KEY` | Key for the digital twin's model calls |
| `OPENROUTER_MODEL` | Model slug to route to (default set in config) |

## Deploying to Render

`render.yaml` in the repo root defines a web service (this API) and a
managed Postgres instance. Push to `main` and connect the repo in the
Render dashboard, or use `render.yaml`'s blueprint deploy.
