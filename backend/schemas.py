from datetime import datetime
from typing import Annotated, Optional
from pydantic import BaseModel, EmailStr, Field
from .models import AppName, TicketType, Urgency, Priority, Status


class TicketCreate(BaseModel):
    app: AppName
    type: TicketType
    title: str
    description: str
    submitter_urgency: Urgency
    submitter_email: Optional[EmailStr] = None


class TicketPublic(BaseModel):
    display_id: str
    title: str
    type: TicketType
    app: AppName
    status: Status
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketAdmin(BaseModel):
    id: int
    display_id: str
    app: AppName
    type: TicketType
    title: str
    description: str
    submitter_urgency: Urgency
    admin_priority: Optional[Priority] = None
    status: Status
    submitter_email: Optional[str] = None
    clarifying_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TicketUpdate(BaseModel):
    admin_priority: Optional[Priority] = None
    status: Optional[Status] = None
    type: Optional[TicketType] = None
    title: Optional[str] = None
    description: Optional[str] = None
    clarifying_notes: Optional[str] = None


class AdminLogin(BaseModel):
    password: str


class ChangePassword(BaseModel):
    current_password: str
    new_password: Annotated[str, Field(min_length=8)]


class TicketCreateResponse(BaseModel):
    display_id: str
    lookup_token: str
    message: str
