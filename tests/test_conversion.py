import pandas as pd
from services.conversion import weekly_conversion, macro
BASE={"Tienda":"A","Año ISO":2026,"Semana ISO":1,"ID/SKU":"1","Color":"ROJO"}
def calc(dev,sale,money=100):
 d=pd.DataFrame([{**BASE,"Dev Pzs":dev,"Ventas Netas Pzs":sale,"Ventas Netas $":money}]); return weekly_conversion(d).iloc[0]
def test_sale_less(): r=calc(10,4,40); assert r["Piezas convertidas"]==4 and r["Pendiente conversión"]==6
def test_sale_equal(): assert calc(10,10)["% Conversión"]==100
def test_sale_greater_capped(): assert calc(10,20)["Piezas convertidas"]==10 and calc(10,20)["% Conversión"]==100
def test_different_week_not_mixed():
 d=pd.DataFrame([{**BASE,"Dev Pzs":10,"Ventas Netas Pzs":0,"Ventas Netas $":0},{**BASE,"Semana ISO":2,"Dev Pzs":0,"Ventas Netas Pzs":10,"Ventas Netas $":100}]); x=weekly_conversion(d); assert x.loc[x["Semana ISO"]==1,"Piezas convertidas"].iloc[0]==0
def test_different_color_not_mixed():
 d=pd.DataFrame([{**BASE,"Dev Pzs":10,"Ventas Netas Pzs":0,"Ventas Netas $":0},{**BASE,"Color":"AZUL","Dev Pzs":0,"Ventas Netas Pzs":10,"Ventas Netas $":100}]); assert weekly_conversion(d)["Piezas convertidas"].sum()==0
def test_two_returns_one_sale():
 d=pd.DataFrame([{**BASE,"Dev Pzs":4,"Ventas Netas Pzs":0,"Ventas Netas $":0},{**BASE,"Dev Pzs":6,"Ventas Netas Pzs":7,"Ventas Netas $":70}]); r=weekly_conversion(d).iloc[0]; assert r["Dev Pzs"]==10 and r["Piezas convertidas"]==7
def test_macro_weighted_not_mean():
 d=pd.DataFrame([{**BASE,"Dev Pzs":100,"Ventas Netas Pzs":50,"Ventas Netas $":500},{**BASE,"ID/SKU":"2","Dev Pzs":1,"Ventas Netas Pzs":1,"Ventas Netas $":10}]); m=macro(weekly_conversion(d)).iloc[0]; assert round(m["% Conversión"],2)==50.5
