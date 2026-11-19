from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.api.routers import action_log
from app.api.deps import get_db
from app.api.routers import customers, stores
from app.api.routers.actions import customer_actions, store_actions
from app.api.routers import dashboard
from app.api.routers import entity_history
from app.api.routers import score_history
from app.api.routers import transaction_timeline
app = FastAPI(
    title="Admin Risk Dashboard API",
    version="0.3.0",
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

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}