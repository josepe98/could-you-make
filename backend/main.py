import secrets
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pathlib import Path
from sqlalchemy import text
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from .limiter import limiter
from .database import Base, engine, SessionLocal
from .models import AdminPassword, Ticket
from .auth import hash_password
from .config import settings
from .routers import tickets, admin

Base.metadata.create_all(bind=engine)


def _seed_admin_password():
    db = SessionLocal()
    try:
        if not db.query(AdminPassword).first():
            pw_hash, salt = hash_password(settings.ADMIN_PASSWORD)
            db.add(AdminPassword(password_hash=pw_hash, salt=salt))
            db.commit()
    finally:
        db.close()


def _migrate_lookup_token():
    """Add lookup_token column if missing and backfill any NULL values."""
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS "
            "lookup_token VARCHAR(64) UNIQUE"
        ))
        conn.commit()
    db = SessionLocal()
    try:
        rows = db.query(Ticket).filter(Ticket.lookup_token == None).all()
        for t in rows:
            t.lookup_token = secrets.token_urlsafe(32)
        if rows:
            db.commit()
    finally:
        db.close()


def _migrate_clarifying_notes():
    """Add clarifying_notes column if missing."""
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS clarifying_notes TEXT"
        ))
        conn.commit()


_seed_admin_password()
_migrate_lookup_token()
_migrate_clarifying_notes()

app = FastAPI(title="Could You Make", docs_url=None, redoc_url=None, openapi_url=None)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        if not request.url.path.startswith("/assets"):
            response.headers["Cache-Control"] = "no-store"
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5175", "https://couldyoumake.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tickets.router)
app.include_router(admin.router)

frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        return FileResponse(frontend_dist / "index.html")
