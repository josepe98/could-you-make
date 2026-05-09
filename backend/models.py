import enum
import secrets
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Integer, String, Text, Enum as SAEnum, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

# Seed list used once, on the first deploy that runs the apps-table migration.
# After that, apps are managed through the admin UI / API.
SEED_APPS = [
    ("life-folio", "Life Folio", "LF", 0),
    ("canopy", "Canopy", "CAN", 1),
    ("kno", "KNO Mgmt", "KNO", 2),
    ("practice-profiles", "Practice Profiles", "PP", 3),
    ("delta-mqds", "delta-mqds", "DLT", 4),
    ("sampras", "Sampras", "SAM", 5),
    ("proj-mgmt", "Project Gantt", "PM", 6),
    ("admin", "Admin", "ADM", 7),
    ("cym", "Could You Make", "CYM", 8),
]


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


class App(Base):
    __tablename__ = "apps"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    prefix: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    app: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("apps.slug", name="tickets_app_fkey"),
        nullable=False,
        index=True,
    )
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
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    app_obj: Mapped[App] = relationship(App, lazy="joined")

    @property
    def display_id(self) -> str:
        return f"{self.app_obj.prefix}-{self.id:03d}"


class AdminPassword(Base):
    __tablename__ = "admin_password"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
