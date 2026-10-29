# database.py
import os
from pathlib import Path

from sqlalchemy.orm import DeclarativeBase

import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{INSTANCE_DIR / 'app.db'}",
)


class Base(DeclarativeBase):
    pass