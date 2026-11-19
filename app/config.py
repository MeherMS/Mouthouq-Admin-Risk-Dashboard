import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Override with an environment variable later (for example, a PostgreSQL URL).
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR / 'data' / 'risk.db'}",
)