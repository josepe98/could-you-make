from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Ticket
from ..schemas import TicketCreate, TicketPublic, TicketCreateResponse
from ..email_utils import send_confirmation_email
from ..limiter import limiter

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.post("", response_model=TicketCreateResponse)
@limiter.limit("5/minute")
async def create_ticket(request: Request, ticket_in: TicketCreate, db: Session = Depends(get_db)):
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
        try:
            await send_confirmation_email(
                to_email=str(ticket_in.submitter_email),
                display_id=ticket.display_id,
                lookup_token=ticket.lookup_token,
                title=ticket.title,
                ticket_type=ticket.type,
                app=ticket.app,
                urgency=ticket.submitter_urgency,
            )
        except Exception as e:
            print(f"[email] Failed to send confirmation: {e}")

    return TicketCreateResponse(
        display_id=ticket.display_id,
        lookup_token=ticket.lookup_token,
        message=f"Your ticket {ticket.display_id} has been submitted.",
    )


@router.get("/{lookup_token}", response_model=TicketPublic)
def get_ticket(lookup_token: str, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.lookup_token == lookup_token).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket
