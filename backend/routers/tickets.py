import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Ticket
from ..schemas import TicketCreate, TicketPublic, TicketCreateResponse
from ..email_utils import send_confirmation_email
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
    ticket = Ticket(
        app=ticket_in.app,
        type=ticket_in.type,
        title=ticket_in.title,
        description=ticket_in.description,
        submitter_urgency=ticket_in.submitter_urgency,
        submitter_email=str(ticket_in.submitter_email) if ticket_in.submitter_email else None,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    if ticket_in.submitter_email:
        # Kick the SMTP send into a background task so the HTTP response
        # returns immediately. Previously this was awaited inline, which
        # held the request open for 20-30s on each email submission.
        background_tasks.add_task(
            _send_confirmation_safe,
            to_email=str(ticket_in.submitter_email),
            display_id=ticket.display_id,
            lookup_token=ticket.lookup_token,
            title=ticket.title,
            ticket_type=ticket.type,
            app=ticket.app,
            urgency=ticket.submitter_urgency,
        )

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
