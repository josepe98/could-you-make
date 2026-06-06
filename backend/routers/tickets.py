import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Ticket, TicketMessage, App
from ..schemas import (
    TicketCreate, TicketPublic, TicketCreateResponse,
    TicketMessageCreate, TicketMessageOut,
)
from ..email_utils import send_confirmation_email
from ..llm_utils import _run_enrichment_safe
from ..limiter import limiter

log = logging.getLogger("cym.tickets")
router = APIRouter(prefix="/api/tickets", tags=["tickets"])


async def _send_confirmation_safe(**kwargs):
    """Wrap send_confirmation_email so a background-task failure is logged
    instead of crashing the worker."""
    try:
        await send_confirmation_email(**kwargs)
    except Exception as e:
        log.error("Failed to send confirmation email: %s", e, exc_info=True)


@router.post("", response_model=TicketCreateResponse)
@limiter.limit("2/minute")
async def create_ticket(
    request: Request,
    ticket_in: TicketCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    app_row = db.query(App).filter(App.slug == ticket_in.app).first()
    if not app_row:
        raise HTTPException(status_code=400, detail=f"Unknown app: {ticket_in.app}")

    ticket = Ticket(
        app=ticket_in.app,
        type=ticket_in.type,
        title=ticket_in.title,
        description=ticket_in.description,
        submitter_urgency=ticket_in.submitter_urgency,
        submitter_email=str(ticket_in.submitter_email),
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    # Confirmation email + LLM enrichment both fire-and-forget so the HTTP
    # response returns immediately. submitter_email is now required at the
    # API boundary, so the confirmation always runs for new tickets.
    background_tasks.add_task(
        _send_confirmation_safe,
        to_email=str(ticket_in.submitter_email),
        display_id=ticket.display_id,
        lookup_token=ticket.lookup_token,
        title=ticket.title,
        ticket_type=ticket.type,
        app_label=app_row.label,
        urgency=ticket.submitter_urgency,
    )
    background_tasks.add_task(_run_enrichment_safe, ticket.id)

    return TicketCreateResponse(
        display_id=ticket.display_id,
        lookup_token=ticket.lookup_token,
        message=f"Your ticket {ticket.display_id} has been submitted.",
    )


@router.get("/{lookup_token}", response_model=TicketPublic)
@limiter.limit("30/minute")
async def get_ticket(request: Request, lookup_token: str, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.lookup_token == lookup_token).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.get("/{lookup_token}/messages", response_model=list[TicketMessageOut])
@limiter.limit("30/minute")
async def list_public_messages(
    request: Request, lookup_token: str, db: Session = Depends(get_db),
):
    """Public thread view. lookup_token is the bearer — same trust model as
    the status-tracking link the submitter already received in their
    confirmation email."""
    ticket = db.query(Ticket).filter(Ticket.lookup_token == lookup_token).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return (
        db.query(TicketMessage)
        .filter(TicketMessage.ticket_id == ticket.id)
        .order_by(TicketMessage.created_at.asc())
        .all()
    )


@router.post("/{lookup_token}/messages", response_model=TicketMessageOut)
@limiter.limit("10/minute")
async def create_public_message(
    request: Request,
    lookup_token: str,
    payload: TicketMessageCreate,
    db: Session = Depends(get_db),
):
    """Submitter posts a reply from the public ticket page. No auth beyond
    the lookup_token. Rate-limited tighter than read."""
    ticket = db.query(Ticket).filter(Ticket.lookup_token == lookup_token).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    msg = TicketMessage(
        ticket_id=ticket.id,
        direction="submitter",
        body=payload.body,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg
