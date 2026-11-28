from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Stream(Base):
    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    keitaro_id: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        index=True,
        nullable=False,
    )

    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    stream_schema: Mapped[str | None] = mapped_column(
        "schema",
        String(50),
        nullable=True,
    )

    action_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    action_payload: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    filters: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    position: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    is_present_in_keitaro: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    raw_payload: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    campaign: Mapped["Campaign"] = relationship(
        back_populates="streams",
    )

    offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="StreamOffer.position",
    )
