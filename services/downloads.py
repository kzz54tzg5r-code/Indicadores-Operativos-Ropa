from __future__ import annotations
import json
from core.database import connect
def register(username,role,scope,report,period,filters,fmt,records,size):
    with connect() as con: con.execute("INSERT INTO downloads(username,role,scope,report,period,filters,format,records,bytes) VALUES(?,?,?,?,?,?,?,?,?)",(username,role,scope,report,period,json.dumps(filters,ensure_ascii=False,default=str),fmt,records,size))
