
from datetime import datetime
from zoneinfo import ZoneInfo

from extensions import db


HELSINKI = ZoneInfo("Europe/Helsinki")


class Server(db.Model):
    __tablename__ = "servers"

    id = db.Column(db.Integer, primary_key=True)

    ip = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
    )

    tags = db.Column(
        db.String(1200),
        nullable=False,
        default="",
    )

    url = db.Column(
        db.String(1200),
        nullable=False,
    )

    reports = db.relationship(
        "Report",
        back_populates="server",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Server {self.ip}>"


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)

    player_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    online = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    server_id = db.Column(
        db.Integer,
        db.ForeignKey("servers.id"),
        nullable=False,
        index=True,
    )

    server = db.relationship(
        "Server",
        back_populates="reports",
    )

    time = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(HELSINKI),
    )

    def __repr__(self):
        return f"<Report server_id={self.server_id} time={self.time}>"
