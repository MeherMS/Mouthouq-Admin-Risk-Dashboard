from app.db import SessionLocal
from app.models import Action, AuditLog
from sqlalchemy import select
db = SessionLocal()
print('--- actions ---')
for a in db.scalars(select(Action).order_by(Action.id)):
    print(a.id, a.entity_type.value, a.entity_id, a.action_type.value, a.admin_id, a.reason)
print('--- audit_log ---')
for a in db.scalars(select(AuditLog).order_by(AuditLog.id)):
    print(a.id, a.admin_id, a.event, a.payload)
db.close()