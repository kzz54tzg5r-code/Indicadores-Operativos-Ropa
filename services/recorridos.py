from __future__ import annotations
import pandas as pd
DAILY={0:5,1:5,2:5,3:8,4:8,5:8,6:8}
def calculate(df, weekly_goal=47):
    if df is None or df.empty: return pd.DataFrame()
    d=df.copy(); d["Fecha"]=pd.to_datetime(d.get("Fecha"),errors="coerce")
    if "Recorridos" in d: real=pd.to_numeric(d["Recorridos"],errors="coerce").fillna(0)
    else: real=d.get("Actividad","").astype(str).str.contains("RECORRIDO",case=False,na=False).astype(int)
    d["Realizados"]=real; d=d[d["Fecha"].notna()]
    g=d.groupby(["Tienda","Año ISO","Semana ISO"],dropna=False,as_index=False)["Realizados"].sum(); g["Meta"]=float(weekly_goal); g["Faltante"]=(g["Meta"]-g["Realizados"]).clip(lower=0); g["% Cumplimiento"]=(g["Realizados"].div(g["Meta"].replace(0,pd.NA))*100).fillna(0); return g
