from __future__ import annotations
import pandas as pd
PRODUCTIVE={"ACONDICIONADO","HABILITADO","UBICADO","MUERTOS","CAJAS","PROBADOR"}
def calculate(df, meta=784.0):
    if df is None or df.empty: return pd.DataFrame()
    d=df.copy(); d["Actividad"] = d.get("Actividad","").astype(str).str.upper().str.strip(); d=d[d["Actividad"].isin(PRODUCTIVE)]
    d["Piezas"]=pd.to_numeric(d.get("Piezas",0),errors="coerce").fillna(0); d["Fecha"]=pd.to_datetime(d.get("Fecha"),errors="coerce")
    name="Nombre Real" if "Nombre Real" in d else "Nombre"; d=d[d[name].notna() & d["Fecha"].notna()]
    if d.empty:
        return pd.DataFrame(columns=[name,"Tienda","Piezas procesadas","Días trabajados","Productividad","Meta acumulada","% Cumplimiento","Diferencia","Faltante","Ranking"])
    g=d.groupby([name,"Tienda"],dropna=False,as_index=False).agg(**{"Piezas procesadas":("Piezas","sum"),"Días trabajados":("Fecha",lambda s:s.dt.date.nunique())})
    g["Productividad"]=g["Piezas procesadas"].div(g["Días trabajados"].replace(0,pd.NA)).fillna(0)
    g["Meta acumulada"]=g["Días trabajados"]*float(meta); g["% Cumplimiento"]=(g["Piezas procesadas"].div(g["Meta acumulada"].replace(0,pd.NA))*100).fillna(0)
    g["Diferencia"]=g["Piezas procesadas"]-g["Meta acumulada"]; g["Faltante"]=(g["Meta acumulada"]-g["Piezas procesadas"]).clip(lower=0)
    return g.sort_values(["% Cumplimiento","Piezas procesadas","Días trabajados"],ascending=[False,False,False]).reset_index(drop=True).assign(Ranking=lambda x:x.index+1)
