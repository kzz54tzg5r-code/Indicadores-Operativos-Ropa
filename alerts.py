from __future__ import annotations
import pandas as pd
def classify(value):
    v=float(value or 0)
    return "Crítica" if v<60 else "Advertencia" if v<80 else "Atención" if v<90 else "Correcto"
def generate(metrics: pd.DataFrame, columns=None):
    columns=columns or [c for c in metrics.columns if str(c).startswith("%")]
    rows=[]
    for _,r in metrics.iterrows():
        for c in columns:
            if c not in r: continue
            value=float(r[c] or 0); status=classify(value)
            if status!="Correcto": rows.append({"Prioridad":status,"Tienda":r.get("Tienda",""),"Indicador":c,"Valor":value,"Detalle":f"{c}: {value:.1f}%","Recomendación":"Revisar ejecución, captura y capacidad operativa."})
    return pd.DataFrame(rows)
