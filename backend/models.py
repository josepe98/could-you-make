import enum
import secrets
from datetime import datetime, timezone
from sqlalchemy import Integer, String, Text, Enum as SAEnum, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

APP_PREFIXES = {
    "life-folio": "LF",
    "canopy": "CAN",
    "kno": "KNO",
    "practice-profiles": "PP",
    "delta-mqds": "DLT",
    "sampras": "SAM",
    "proj-mgmt": "PM",
    "admin": "ADM",
    "cym": "CYM",
}

# Human-readable app names. Used anywhere we display an app to a person
# (confirmation emails, future admin exports, etc.). The frontend keeps
# its own copy of this in the APP_LABELS constants on each page — keep
# the two in sync.
APP_LABELS = {
    "life-folio": "Life Folio",
    "canopy": "Canopy",
    "kno": "KNO Mgmt",
    "practice-profiles": "Practice Profiles",
    "delta-mqds": "delta-mqds",
    "sampras": "Sampras",
    "proj-mgmt": "Project Gantt",
    "admin": "Admin",
    "cym": "Could You Make",
}


class AppName(str, enum.Enum):
    life_folio = "life-folio"
    canopy = "canopy"
    kno = "kno"
    practice_profiles = "practice-profiles"
    delta_mqds = "delta-mqds"
    sampras = "sampras"
    proj_mgmt = "proj-mgmt"
    admin = "admin"
    cym = "cym"


class TicketType(str, enum.Enum):
    bug = "Bug"
    enhancement = "Enhancement"
    question = "Question"


class Urgency(str, enum.Enum):
    low = "Low"
    medium = "Medium"
    high = "High"


class Priority(str, enum.Enum):
    low = "Low"
    medium = "Medium"
    high = "High"
    critical = "Critical"


class Status(str, enum.Enum):
    open = "Open"
    in_progress = "In Progress"
    done = "Done"
    wont_fix = "Won't Fix"


def _values(e):
    return [m.value for m in e]


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    app: Mapped[str] = mapped_column(SAEnum(AppName, values_callable=_values), nullable=False)
    type: Mapped[str] = mapped_column(SAEnum(TicketType, values_callable=_values), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    submitter_urgency: Mapped[str] = mapped_column(SAEnum(Urgency, values_callable=_values), nullable=False)
    admin_priority: Mapped[str] = mapped_column(SAEnum(Priority, values_callable=_values), nullable=True)
    status: Mapped[str] = mapped_column(
        SAEnum(Status, values_callable=_values),
        nullable=False,
        default=Status.open.value,
    )
    submitter_email: Mapped[str] = mapped_column(String(255), nullable=True)
    lookup_token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=True,
        default=lambda: secrets.token_urlsafe(32),
    )
    clarifying_notes: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def display_id(self) -> str:
        prefix = APP_PREFIXES[self.app]
        return f"{prefix}-{self.id:03d}"


class AdminPassword(Base):
    __tablename__ = "admin_password"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
