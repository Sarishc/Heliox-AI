"\"\"\"Waitlist model for capturing landing page leads.\"\"\""
from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class WaitlistEntry(UUIDMixin, TimestampMixin, Base):
    """Stores waitlist signups from the public landing page."""

    __tablename__ = "waitlist_entries"

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        unique=True,
        doc="Primary contact email",
    )
    name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Full name of the submitter",
    )
    company: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Company or organization",
    )
    role: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Role or title",
    )
    source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        server_default=text("'landing'"),
        doc="Attribution source for analytics",
    )
