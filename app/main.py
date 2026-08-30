"""Pit Box -- part tracking and project management for a Baja SAE team.

Run it:
    pip install -r requirements.txt
    uvicorn app.main:app --reload

Then open http://127.0.0.1:8000 . Interactive API docs are at /docs.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fastapi import Depends
from fastapi.responses import RedirectResponse

from .config import BASE_DIR, settings
from .database import SessionLocal, engine
from .migrate import run_migrations
from .models import Base, Member
from .routers import attachments, auth, members, nodes, projects, tags
from .security import current_member_optional, purge_expired_sessions, require_member
from .seed import ensure_default_tags, seed_demo

STATIC_DIR = BASE_DIR / "static"        # the original zero-build UI
VITE_DIST = BASE_DIR / "frontend" / "dist"  # the React build, when present


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # create_all is fine while the schema is still moving and the data is
    # disposable. Once you have a season's worth of real parts in here, switch to
    # Alembic (pip install alembic; alembic init migrations) -- see docs/ARCHITECTURE.md.
    Base.metadata.create_all(bind=engine)
    # create_all builds missing tables but never alters existing ones, so adding
    # the login columns needs this for anyone with a database already.
    run_migrations(engine)
    with SessionLocal() as db:
        ensure_default_tags(db)
        seed_demo(db)  # no-op once any project exists
        purge_expired_sessions(db)
    yield


app = FastAPI(
    title=f"Pit Box -- {settings.team_name}",
    description="Hierarchical part tracking for a Baja SAE vehicle.",
    version="0.1.0",
    lifespan=lifespan,
)

# Auth first, and unguarded — you cannot require a session to sign in.
app.include_router(auth.router)

# Everything else requires one. Declaring it here rather than on each endpoint
# means a new route is protected by default: you have to go out of your way to
# expose something, instead of remembering to lock it down.
PROTECTED = [projects.router, nodes.router, tags.router, attachments.router, members.router]
for _router in PROTECTED:
    app.include_router(_router, dependencies=[Depends(require_member)])


@app.get("/api/health")
def health():
    """Deliberately public, so uptime checks and `fly status` work without a login.
    It reveals only that the service is up and the team name."""
    return {"status": "ok", "team": settings.team_name}


# The API routes are declared before any static mount so /api/* always wins.
#
# Two frontends can coexist. If the Vite app has been built (npm run build), it
# is served at / and the original no-build UI stays reachable at /static/ as a
# fallback. Nothing here changes when you switch between them.
if VITE_DIST.exists():
    assets = VITE_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index(member: Member | None = Depends(current_member_optional)):
    # Signed out, send them to the login page rather than an app shell that will
    # immediately 401 on every request it makes.
    if member is None:
        return RedirectResponse("/login", status_code=302)
    if VITE_DIST.exists():
        return FileResponse(VITE_DIST / "index.html")
    if STATIC_DIR.exists():
        return FileResponse(STATIC_DIR / "index.html")
    return {"detail": "No frontend built. Run 'npm run build' in frontend/, or use /docs."}
