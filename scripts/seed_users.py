"""
Creates the prototype admin and viewer users.

The password hash is stored for when login is added. Nothing checks it yet.

Usage (from project root):
    python -m scripts.seed_users
"""
import hashlib
import os

from sqlalchemy import select

from app.db import SessionLocal
from app.models import User, UserRole

USERS = [
    ("admin@prototype.local", UserRole.ADMIN),
    ("viewer@prototype.local", UserRole.VIEWER),
]
PLACEHOLDER_PASSWORD = "change-me-prototype"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"


def seed() -> None:
    db = SessionLocal()
    try:
        for email, role in USERS:
            existing = db.scalar(select(User).where(User.email == email))
            if existing is not None:
                print(f"{email}: already exists (id={existing.id}, role={existing.role.value})")
                continue
            user = User(
                email=email,
                password_hash=hash_password(PLACEHOLDER_PASSWORD),
                role=role,
            )
            db.add(user)
            db.flush()
            print(f"{email}: created (id={user.id}, role={role.value})")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()