import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Ticket, AdminPassword, AdminSession
from ..schemas import TicketAdmin, TicketUpdate, AdminLogin, ChangePassword, AskSubmitter
from ..config import settings
from ..auth import hash_password, verify_password
from ..email_utils import send_status_email, send_question_email
from ..limiter import limiter

log = logging.getLogger("cym.admin")

router = APIRouter(prefix="/api/admin", tags=["admin"])

SESSION_COOKIE = "cym_session"
SESSION_TTL_DAYS = 7


def require_auth(request: Request, db: Session = Depends(get_db)):
    """Session-cookie-only auth. Used for admin password change, where we
    never want a bearer token to be sufficient."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = db.query(AdminSession).filter(
        AdminSession.token == token,
        AdminSession.expires_at > datetime.now(timezone.utc),
    ).first()
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return token


def require_auth_or_api_key(request: Request, db: Session = Depends(get_db)):
    """Accept either an admin session cookie or an API key in the
    `Authorization: Bearer <key>` header. When settings.API_KEY is unset,
    only the cookie path is available (fail-closed)."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        presented = auth_header.split(" ", 1)[1].strip()
        if settings.API_KEY and secrets.compare_digest(presented, settings.API_KEY):
            return "api_key"
    return require_auth(request, db)


def _check_password(password: str, db: Session) -> bool:
    admin_pw = db.query(AdminPassword).first()
    if admin_pw:
        return verify_password(password, admin_pw.password_hash, admin_pw.salt)
    return secrets.compare_digest(password, settings.ADMIN_PASSWORD)


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, creds: AdminLogin, response: Response, db: Session = Depends(get_db)):
    if not _check_password(creds.password, db):
        raise HTTPException(status_code=401, detail="Invalid password")
    # Clean up expired sessions on each login
    db.query(AdminSession).filter(AdminSession.expires_at <= datetime.now(timezone.utc)).delete()
    token = secrets.token_urlsafe(32)
    db.add(AdminSession(
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS),
    ))
    db.commit()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * SESSION_TTL_DAYS,
    )
    return {"message": "Logged in"}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.query(AdminSession).filter(AdminSession.token == token).delete()
        db.commit()
    response.delete_cookie(SESSION_COOKIE)
    return {"message": "Logged out"}


@router.post("/change-password")
def change_password(data: ChangePassword, db: Session = Depends(get_db), _auth: str = Depends(require_auth)):
    if not _check_password(data.current_password, db):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    new_hash, new_salt = hash_password(data.new_password)
    admin_pw = db.query(AdminPassword).first()
    if admin_pw:
        admin_pw.password_hash = new_hash
        admin_pw.salt = new_salt
    else:
        db.add(AdminPassword(password_hash=new_hash, salt=new_salt))
    db.commit()
    return {"message": "Password updated"}


@router.get("/tickets", response_model=list[TicketAdmin])
def list_tickets(
    request: Request,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_auth_or_api_key),
    app: Optional[str] = None,
    type: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
):
    query = db.query(Ticket)
    if app:
        query = query.filter(Ticket.app == app)
    if type:
        query = query.filter(Ticket.type == type)
    if status:
        query = query.filter(Ticket.status == status)
    _SORT_COLS = {"created_at", "updated_at", "status", "admin_priority", "submitter_urgency", "type", "app"}
    sort_col = getattr(Ticket, sort_by if sort_by in _SORT_COLS else "created_at")
    if sort_dir == "asc":
        query = query.order_by(asc(sort_col))
    else:
        query = query.order_by(desc(sort_col))
    return query.all()


@router.get("/tickets/{ticket_id}", response_model=TicketAdmin)
def get_ticket_admin(ticket_id: int, db: Session = Depends(get_db), _auth: str = Depends(require_auth_or_api_key)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


CLOSED_STATUSES = {"Done", "Won't Fix"}


async def _send_status_safe(**kwargs):
    """Wrap send_status_email so background-task failures are logged
    instead of crashing the worker."""
    try:
        await send_status_email(**kwargs)
    except Exception as e:
        log.error("Failed to send status email: %s", e, exc_info=True)


async def _send_question_safe(**kwargs):
    try:
        await send_question_email(**kwargs)
    except Exception as e:
        log.error("Failed to send question email: %s", e, exc_info=True)


@router.patch("/tickets/{ticket_id}", response_model=TicketAdmin)
def update_ticket(
    ticket_id: int,
    update: TicketUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_auth_or_api_key),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    new_status = update.status
    old_status = ticket.status
    for field, value in update.model_dump(exclude_none=True).items():
        setattr(ticket, field, value)
    transitioning_to_closed = (
        new_status is not None
        and new_status in CLOSED_STATUSES
        and old_status not in CLOSED_STATUSES
    )
    if new_status is not None:
        if transitioning_to_closed:
            ticket.resolved_at = datetime.now(timezone.utc)
        elif new_status not in CLOSED_STATUSES:
            ticket.resolved_at = None
    # Status-change email: fire once per ticket on the first transition into
    # a closed status. closed_notified_at is the idempotency gate — reopen →
    # re-close never re-emails. Require submitter_email; legacy tickets
    # without one are silently skipped.
    should_notify = (
        transitioning_to_closed
        and ticket.closed_notified_at is None
        and ticket.submitter_email
    )
    if should_notify:
        ticket.closed_notified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ticket)
    if should_notify:
        status_value = (
            new_status.value if hasattr(new_status, "value") else new_status
        )
        background_tasks.add_task(
            _send_status_safe,
            to_email=ticket.submitter_email,
            display_id=ticket.display_id,
            lookup_token=ticket.lookup_token,
            title=ticket.title,
            status=status_value,
            clarifying_notes=ticket.clarifying_notes,
        )
    return ticket


@router.post("/tickets/{ticket_id}/ask")
def ask_submitter(
    ticket_id: int,
    payload: AskSubmitter,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_auth_or_api_key),
):
    """Send the submitter a question about their ticket. Replies route to
    REPLY_TO (the configured Fastmail inbox) — manual threading."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if not ticket.submitter_email:
        raise HTTPException(
            status_code=400,
            detail="Ticket has no submitter_email — cannot send a question.",
        )
    background_tasks.add_task(
        _send_question_safe,
        to_email=ticket.submitter_email,
        display_id=ticket.display_id,
        lookup_token=ticket.lookup_token,
        title=ticket.title,
        question=payload.question,
    )
    return {"message": f"Question queued for {ticket.display_id}"}


@router.delete("/tickets/{ticket_id}")
def delete_ticket(ticket_id: int, db: Session = Depends(get_db), _auth: str = Depends(require_auth_or_api_key)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    db.delete(ticket)
    db.commit()
    return {"message": "Ticket deleted"}
