from sqlalchemy.orm import Session
from app.db import engine
from app.synthetic.config import FULL
from app.synthetic.history import (
    rebuild_population, load_db_ids, simulate_history, reset_history,
)

with Session(engine) as s:
    customers, stores = rebuild_population(FULL)
    customers, stores = load_db_ids(s, customers, stores)
    reset_history(s)
    simulate_history(s, FULL, customers, stores)
    s.commit()
print("history regenerated")