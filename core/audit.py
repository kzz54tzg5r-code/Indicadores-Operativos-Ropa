from __future__ import annotations
import json
from datetime import datetime, timezone
from core.database import connect
from core.settings import AUDIT_FILE
def log_event(event: str, username: str="", **details):
    payload={"timestamp":datetime.now(timezone.utc).isoformat(),"event":event,"username":username,"details":details}
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_FILE.open("a",encoding="utf-8") as f: f.write(json.dumps(payload,ensure_ascii=False,default=str)+"\n")
    with connect() as con: con.execute("INSERT INTO audit_log(event,username,details) VALUES(?,?,?)",(event,username,json.dumps(details,ensure_ascii=False,default=str)))
