from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db import SessionLocal  # If your session factory has a different name in app/db.py, change this line


def get_db() -> Generator[Session, None, None]:
    """One database session per request, always closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()