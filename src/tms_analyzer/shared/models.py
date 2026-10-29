from datetime import datetime, timezone

from sqlalchemy import (
    String, Integer, Boolean, ForeignKey, DateTime
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    ip: Mapped[str] = mapped_column(String(80), unique=True)
    tags: Mapped[str] = mapped_column(String(1200), default="")
    url: Mapped[str] = mapped_column(String(1200))
    version: Mapped[str] = mapped_column(String(80))

    reports: Mapped[list["Report"]] = relationship(
        back_populates="server",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Server {self.ip}>"


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_count: Mapped[int] = mapped_column(Integer)
    online: Mapped[bool] = mapped_column(Boolean, default=False)

    server_id: Mapped[int] = mapped_column(
        ForeignKey("servers.id"),
        index=True,
    )

    server: Mapped["Server"] = relationship(
        back_populates="reports"
    )

    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<Report server_id={self.server_id}>"