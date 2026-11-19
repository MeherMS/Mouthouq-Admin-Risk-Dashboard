from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import User, UserRole


def get_current_admin(
    x_admin_id: int | None = Header(default=None, alias="X-Admin-Id"),
    db: Session = Depends(get_db),
) -> User:
    """
    TEMPORARY. Identifies the caller from a header that anyone can set.
    Replace with real authentication before any shared or production use.
    """
    if x_admin_id is None:
        raise HTTPException(status_code=401, detail="Missing X-Admin-Id header")

    user = db.get(User, x_admin_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown admin id")

    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")

    return user