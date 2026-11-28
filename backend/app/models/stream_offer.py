from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StreamOffer(Base):
    __tablename__ = "stream_offers"

    __table_args__ = (
        UniqueConstraint(
            "stream_id",
            "keitaro_offer_id",
            name="uq_stream_offer",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    stream_id: Mapped[int] = mapped_column(
        ForeignKey("streams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    keitaro_offer_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )

    share: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        default=0,
        nullable=False,
    )

    remote_share: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2),
        nullable=True,
    )

    synced_share: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2),
        nullable=True,
    )

    synced_is_fixed: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    synced_is_deleted: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    is_fixed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    is_present_in_keitaro: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    remote_state: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    position: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    raw_payload: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
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

    stream: Mapped["Stream"] = relationship(
        back_populates="offers",
    )
