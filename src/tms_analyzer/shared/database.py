import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass


def init_db():
    load_dotenv()

    BASE_DIR = Path(__file__).resolve().parent
    INSTANCE_DIR = BASE_DIR / "instance"
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{INSTANCE_DIR / 'app.db'}",
    )

    engine = create_engine(DATABASE_URL)
    # Import models to register their tables with Base
    from tms_analyzer import models

    Base.metadata.create_all(engine)
    return engine