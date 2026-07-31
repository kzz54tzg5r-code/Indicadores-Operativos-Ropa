import pandas as pd
from services.productivity import calculate
def test_recorridos_not_pieces():
 d=pd.DataFrame({"Actividad":["Acondicionado","Recorridos"],"Piezas":[100,999],"Fecha":["2026-01-01"]*2,"Nombre":["A"]*2,"Tienda":["T"]*2}); assert calculate(d).iloc[0]["Piezas procesadas"]==100
def test_no_empty_collaborators():
 d=pd.DataFrame({"Actividad":["Acondicionado"],"Piezas":[100],"Fecha":["2026-01-01"],"Nombre":[None],"Tienda":["T"]}); assert calculate(d).empty
