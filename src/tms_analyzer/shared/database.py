import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    sessionmaker,
    Session,
)

class Base(DeclarativeBase):
    pass


engine = None
SessionLocal = None


def init_db():
    global engine, SessionLocal

    load_dotenv()

    BASE_DIR = Path(__file__).resolve().parent
    INSTANCE_DIR = BASE_DIR / "instance"
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{INSTANCE_DIR / 'app.db'}",
    )

    engine = create_engine(DATABASE_URL)

    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    from tms_analyzer.shared import models

    Base.metadata.create_all(engine)

    return engine


def get_db():
    if SessionLocal is None:
        raise RuntimeError("Database not initialized")

    db: Session = SessionLocal()

    try:
        yield db
    finally:
        db.close()