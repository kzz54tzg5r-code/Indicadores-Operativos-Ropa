from __future__ import annotations
import math

def ratio_pct(numerator, denominator, *, base_exists=True):
    try: n=float(numerator or 0); d=float(denominator or 0)
    except (TypeError,ValueError): return None
    if d==0: return 0.0 if base_exists else None
    return n/d*100.0

def clamp(value, low=0.0, high=100.0): return max(low,min(high,float(value or 0)))
def operational_metrics(ingresos, acondicionado, ubicado):
    i=float(ingresos or 0); a=float(acondicionado or 0); u=float(ubicado or 0)
    return {"Piezas ingresadas":i,"Acondicionado":a,"Ubicado":u,"Pendiente acondicionar":max(i-a,0),"Pendiente ubicar":max(i-u,0),"% Acondicionado":ratio_pct(a,i,base_exists=i>0),"% Ubicado / Ingresos":ratio_pct(u,i,base_exists=i>0),"% Ubicado / Acondicionado":ratio_pct(u,a,base_exists=a>0)}
def ps_score(conversion, recovery, productivity, recorridos, pendiente_control, weights=None):
    w=weights or {"conversion":.30,"recovery":.25,"productivity":.20,"recorridos":.15,"pending":.10}
    score=clamp(conversion)*w["conversion"]+clamp(recovery)*w["recovery"]+clamp(productivity)*w["productivity"]+clamp(recorridos)*w["recorridos"]+clamp(pendiente_control)*w["pending"]
    return clamp(score)
