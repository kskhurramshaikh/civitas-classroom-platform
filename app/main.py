import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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


# The bare service URL (what gets shared/clicked as "the main link") had no
# route at all before this, so it 404'd with a raw {"detail":"Not Found"}
# instead of taking anyone anywhere useful. A small landing page pointing
# at the two real apps fixes that.
@app.get("/", response_class=HTMLResponse)
def landing():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Civitas Classroom Platform</title>
<style>
  :root{ --bg:#12131a; --panel:#1b1d29; --line:#2e3146; --ink:#f3f4f8; --ink-dim:#9a9db3; --accent:#7c8cff;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif; }
  *{box-sizing:border-box;}
  body{margin:0; background:var(--bg); color:var(--ink); min-height:100vh; display:flex; align-items:center; justify-content:center;}
  .card{max-width:420px; width:100%; padding:40px 32px; text-align:center;}
  h1{font-size:22px; margin:0 0 6px;}
  p{color:var(--ink-dim); font-size:14px; margin:0 0 28px;}
  a.app-link{display:block; background:var(--panel); border:1px solid var(--line); border-radius:14px;
    padding:18px 20px; margin-bottom:14px; text-decoration:none; color:var(--ink); font-weight:600; font-size:15px;
    transition:border-color .15s;}
  a.app-link:hover{border-color:var(--accent);}
  a.app-link span{display:block; font-weight:400; color:var(--ink-dim); font-size:12px; margin-top:4px;}
</style>
</head>
<body>
  <div class="card">
    <h1>Civitas Classroom</h1>
    <p>AI-native classroom platform</p>
    <a class="app-link" href="/web/teacher.html">Teacher Voice Screen<span>For teachers — sign in with your school account</span></a>
    <a class="app-link" href="/web/parent.html">Learning Garden<span>For parents — see how your child is growing</span></a>
  </div>
</body>
</html>"""


# Phase 2 frontends — Teacher Voice Screen and the parent app — served
# as static files straight from this API so there's no separate
# static site/host to wire up yet. /web/teacher.html and
# /web/parent.html; both call this same API by relative path.
_web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
if os.path.isdir(_web_dir):
    app.mount("/web", StaticFiles(directory=_web_dir, html=True), name="web")
