from datetime import datetime
from typing import Annotated, Optional
from pydantic import BaseModel, EmailStr, Field
from .models import TicketType, Urgency, Priority, Status, LevelOfEffort


class TicketCreate(BaseModel):
    app: Annotated[str, Field(max_length=64)]
    type: TicketType
    title: Annotated[str, Field(min_length=1, max_length=255)]
    description: Annotated[str, Field(min_length=1, max_length=10_000)]
    submitter_urgency: Urgency
    submitter_email: EmailStr


class TicketPublic(BaseModel):
    display_id: str
    title: str
    type: TicketType
    app: str
    status: Status
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketAdmin(BaseModel):
    id: int
    display_id: str
    app: str
    type: TicketType
    title: str
    description: str
    submitter_urgency: Urgency
    admin_priority: Optional[Priority] = None
    level_of_effort: Optional[LevelOfEffort] = None
    status: Status
    submitter_email: Optional[str] = None
    clarifying_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TicketUpdate(BaseModel):
    admin_priority: Optional[Priority] = None
    level_of_effort: Optional[LevelOfEffort] = None
    status: Optional[Status] = None
    type: Optional[TicketType] = None
    title: Optional[Annotated[str, Field(min_length=1, max_length=255)]] = None
    description: Optional[Annotated[str, Field(min_length=1, max_length=10_000)]] = None
    clarifying_notes: Optional[str] = None


class AskSubmitter(BaseModel):
    question: Annotated[str, Field(min_length=1, max_length=4_000)]


class AdminLogin(BaseModel):
    password: str


class ChangePassword(BaseModel):
    current_password: str
    new_password: Annotated[str, Field(min_length=8)]


class TicketCreateResponse(BaseModel):
    display_id: str
    lookup_token: str
    message: str


class AppOut(BaseModel):
    slug: str
    label: str
    prefix: str
    display_order: int

    model_config = {"from_attributes": True}


class AppCreate(BaseModel):
    slug: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")]
    label: Annotated[str, Field(min_length=1, max_length=128)]
    prefix: Annotated[str, Field(min_length=1, max_length=8, pattern=r"^[A-Z0-9]+$")]
    display_order: int = 0


class AppUpdate(BaseModel):
    label: Optional[Annotated[str, Field(min_length=1, max_length=128)]] = None
    prefix: Optional[Annotated[str, Field(min_length=1, max_length=8, pattern=r"^[A-Z0-9]+$")]] = None
    display_order: Optional[int] = None
