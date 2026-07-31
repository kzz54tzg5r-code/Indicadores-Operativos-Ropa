import math
from services.metrics import ratio_pct, operational_metrics, ps_score
def test_zero_denominator(): assert ratio_pct(0,0,base_exists=True)==0 and ratio_pct(0,0,base_exists=False) is None
def test_operational_pending():
    m=operational_metrics(100,80,60); assert m["Pendiente acondicionar"]==20 and m["Pendiente ubicar"]==40 and m["% Acondicionado"]==80
def test_score_bounds(): assert 0<=ps_score(150,-1,80,90,100)<=100
