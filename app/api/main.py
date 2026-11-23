import os

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.api.auth import require_api_key
from app.api.routers import action_log
from app.api.deps import get_db
from app.api.routers import customers, stores
from app.api.routers.actions import customer_actions, store_actions
from app.api.routers import dashboard
from app.api.routers import entity_history
from app.api.routers import score_history
from app.api.routers import transaction_timeline
from app.api.routers import customer_shipments
from app.api.routers import database_overview


# Interactive docs are off by default, so a public deployment does not show the API layout.
# Set ENABLE_DOCS=1 locally to turn them on.
_docs_on = os.environ.get("ENABLE_DOCS") == "1"

app = FastAPI(
    title="Admin Risk Dashboard API",
    version="0.3.0",
    dependencies=[Depends(require_api_key)],
    docs_url="/docs" if _docs_on else None,
    redoc_url="/redoc" if _docs_on else None,
    openapi_url="/openapi.json" if _docs_on else None,
)

app.include_router(customers.router)
app.include_router(stores.router)
app.include_router(customer_actions)
app.include_router(store_actions)
app.include_router(action_log.router)
app.include_router(dashboard.router)
app.include_router(entity_history.router)
app.include_router(score_history.router)
app.include_router(transaction_timeline.router)
app.include_router(customer_shipments.router)
app.include_router(database_overview.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}