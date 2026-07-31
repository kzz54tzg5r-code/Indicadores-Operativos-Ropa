from core.database import connect
VALID={"ACTIVE","READ_ONLY","MAINTENANCE","SUSPENDED","DEMO"}
def get_state():
    with connect() as con:
        row=con.execute("SELECT state,message,changed_by,changed_at FROM system_state WHERE id=1").fetchone()
    return dict(row) if row else {"state":"ACTIVE","message":""}
def set_state(state, user, message=""):
    state=str(state).upper()
    if state not in VALID: raise ValueError("Estado inválido")
    with connect() as con: con.execute("UPDATE system_state SET state=?,message=?,changed_by=?,changed_at=CURRENT_TIMESTAMP WHERE id=1",(state,message,user))
