from __future__ import annotations
import pandas as pd
def trend(series):
    s=pd.to_numeric(pd.Series(series),errors="coerce").dropna(); avg=s.tail(4).mean() if len(s) else 0; current=s.iloc[-1] if len(s) else 0; deviation=((current-avg)/avg*100) if avg else 0
    return {"Promedio móvil 4 semanas":avg,"Actual":current,"Desviación %":deviation,"Tendencia":"Positiva" if deviation>2 else "Negativa" if deviation<-2 else "Estable"}
def score_label(score): return "Excelente" if score>=90 else "Estable" if score>=80 else "Atención" if score>=70 else "Crítico"
