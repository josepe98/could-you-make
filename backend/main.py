import logging
import secrets
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pathlib import Path
from sqlalchemy import text
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from .limiter import limiter
from .database import Base, engine, SessionLocal
from .models import AdminPassword, Ticket, App, SEED_APPS
from .auth import hash_password
from .config import settings
from .routers import tickets, admin, apps

# Without a root handler at INFO, Python's last-resort handler drops
# everything below WARNING, so the cym.* loggers' INFO lines (enrichment
# heartbeat, email sends) never reached Railway logs — a healthy pipeline
# was indistinguishable from a silently dead one (CYM-136). Uvicorn's own
# loggers keep their handlers and don't propagate, so no duplicate lines.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

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


def _run_ddl_migrations():
    """Add any columns missing from older schemas. Must run before any ORM
    queries, because SQLAlchemy SELECTs include every column on the model —
    a missing column would crash the query and prevent later migrations from
    running.

    The apps-table migration here is idempotent: it guards on pg_type to
    detect the legacy appname enum and only converts the column the first
    time new code runs against an old DB. Subsequent runs are no-ops.
    """
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS "
            "lookup_token VARCHAR(64) UNIQUE"
        ))
        conn.execute(text(
            "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS clarifying_notes TEXT"
        ))
        conn.execute(text(
            "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ"
        ))
        # Backfill resolved_at for existing closed tickets using their last updated_at.
        conn.execute(text(
            "UPDATE tickets SET resolved_at = updated_at "
            "WHERE status IN ('Done', 'Won''t Fix') AND resolved_at IS NULL"
        ))
        conn.execute(text(
            "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS "
            "level_of_effort VARCHAR(8)"
        ))
        # closed_notified_at gates the status-change email so reopen → re-close
        # doesn't re-notify. Backfill existing Done/Won't Fix rows to resolved_at
        # so the first deploy doesn't blast emails for already-closed tickets.
        conn.execute(text(
            "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS closed_notified_at TIMESTAMPTZ"
        ))
        conn.execute(text(
            "UPDATE tickets SET closed_notified_at = resolved_at "
            "WHERE status IN ('Done', 'Won''t Fix') AND closed_notified_at IS NULL"
        ))

        # ticket_messages: clarification thread between admin and submitter.
        # create_all() will add this on a fresh DB; this CREATE IF NOT EXISTS
        # covers the live Postgres DB that already exists. Index on
        # (ticket_id, created_at) so the per-ticket thread loads in order
        # without a table scan.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ticket_messages (
                id SERIAL PRIMARY KEY,
                ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                direction VARCHAR(16) NOT NULL,
                body TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ticket_messages_ticket_id_idx "
            "ON ticket_messages (ticket_id, created_at)"
        ))

        # Retire the appname PG enum in favour of a data-driven apps table.
        # We only convert the column here; the FK constraint is added later
        # (in _add_apps_fkey), after the apps table has been seeded so the
        # constraint doesn't fail against existing tickets.
        enum_exists = conn.execute(text(
            "SELECT 1 FROM pg_type WHERE typname = 'appname'"
        )).scalar()
        if enum_exists:
            conn.execute(text(
                "ALTER TABLE tickets ALTER COLUMN app TYPE VARCHAR(64) USING app::text"
            ))
            conn.execute(text("DROP TYPE appname"))

        conn.commit()


def _seed_apps():
    """Populate the apps table on first run. Only inserts missing slugs so
    admin-managed changes are never overwritten."""
    db = SessionLocal()
    try:
        for slug, label, prefix, display_order in SEED_APPS:
            if not db.query(App).filter(App.slug == slug).first():
                db.add(App(slug=slug, label=label, prefix=prefix, display_order=display_order))
        db.commit()
    finally:
        db.close()


def _add_apps_fkey():
    """Add the tickets.app -> apps.slug foreign key once the apps table has
    been seeded. On a fresh DB, create_all already added the constraint — we
    only need this to backfill it on legacy DBs that are being migrated."""
    with engine.connect() as conn:
        fkey_exists = conn.execute(text(
            "SELECT 1 FROM pg_constraint WHERE conname = 'tickets_app_fkey'"
        )).scalar()
        if not fkey_exists:
            conn.execute(text(
                "ALTER TABLE tickets ADD CONSTRAINT tickets_app_fkey "
                "FOREIGN KEY (app) REFERENCES apps(slug)"
            ))
            conn.commit()


def _backfill_lookup_tokens():
    """Populate lookup_token for any rows created before the column existed."""
    db = SessionLocal()
    try:
        rows = db.query(Ticket).filter(Ticket.lookup_token == None).all()
        for t in rows:
            t.lookup_token = secrets.token_urlsafe(32)
        if rows:
            db.commit()
    finally:
        db.close()


_run_ddl_migrations()
_seed_apps()
_add_apps_fkey()
_seed_admin_password()
_backfill_lookup_tokens()

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
            "font-src 'self' data:; "
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
app.include_router(apps.public_router)
app.include_router(apps.admin_router)

frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/.well-known/security.txt", include_in_schema=False)
    async def security_txt():
        content = (
            "Contact: mailto:viatenebrosa@yahoo.co.uk\n"
            "Expires: 2027-05-24T00:00:00.000Z\n"
            "Preferred-Languages: en\n"
        )
        return PlainTextResponse(content)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        return FileResponse(frontend_dist / "index.html")
