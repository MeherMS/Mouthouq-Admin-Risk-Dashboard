from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import engine
from app.synthetic.config import FULL
from app.synthetic.history import rebuild_population, load_db_ids, simulate_history, reset_history

for run in (1, 2):
    s = Session(engine)
    c, st = rebuild_population(FULL)
    c, st = load_db_ids(s, c, st)
    reset_history(s)
    simulate_history(s, FULL, c, st)
    s.commit()
    s.close()
    with engine.connect() as conn:
        print("run", run, "deals:", conn.execute(text("SELECT COUNT(*) FROM deals")).scalar())