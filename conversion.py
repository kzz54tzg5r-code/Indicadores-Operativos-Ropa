"""Conversión y recuperación económica por llave semanal oficial."""
from __future__ import annotations
import pandas as pd
from services.metrics import ratio_pct
KEY=["Tienda","Año ISO","Semana ISO","ID/SKU","Color"]
ALIASES={"ID":"ID/SKU","SKU":"ID/SKU","Modelo":"ID/SKU","Dev_pzs":"Dev Pzs","Vta_Pzs":"Ventas Netas Pzs","Vta_Imp":"Ventas Netas $","Venta Neta $":"Ventas Netas $"}
def normalize(df):
    out=df.copy().rename(columns={k:v for k,v in ALIASES.items() if k in df.columns})
    for col in KEY: 
        if col not in out: out[col]=""
    for col in ["Dev Pzs","Ventas Netas Pzs","Ventas Netas $"]:
        out[col]=pd.to_numeric(out.get(col,0),errors="coerce").fillna(0.0)
    return out

def weekly_conversion(df):
    d=normalize(df)
    g=d.groupby(KEY,dropna=False,as_index=False).agg({"Dev Pzs":"sum","Ventas Netas Pzs":"sum","Ventas Netas $":"sum"})
    g["Venta observada"]=g["Ventas Netas Pzs"]
    g["Piezas convertidas"]=g[["Dev Pzs","Ventas Netas Pzs"]].min(axis=1).clip(lower=0)
    g["Pendiente conversión"]=(g["Dev Pzs"]-g["Piezas convertidas"]).clip(lower=0)
    g["% Conversión"]=(g["Piezas convertidas"].div(g["Dev Pzs"].replace(0,pd.NA))*100).fillna(0).clip(0,100)
    g["Precio unitario"]=(g["Ventas Netas $"] .div(g["Ventas Netas Pzs"].replace(0,pd.NA))).fillna(0)
    g["Valor devolución"]=g["Precio unitario"]*g["Dev Pzs"]
    g["Venta recuperada $"]=g["Precio unitario"]*g["Piezas convertidas"]
    g["Pendiente recuperación $"]=(g["Valor devolución"]-g["Venta recuperada $"]).clip(lower=0)
    g["% Recuperación económica"]=(g["Venta recuperada $"] .div(g["Valor devolución"].replace(0,pd.NA))*100).fillna(0).clip(0,100)
    g["Estado"]=pd.cut(g["% Conversión"],[-1,0,99.999,100.001],labels=["Sin recuperar","Parcial","Recuperado"])
    return g

def macro(detail, by=("Tienda",)):
    if detail.empty: return pd.DataFrame()
    g=detail.groupby(list(by),dropna=False,as_index=False).agg({"Dev Pzs":"sum","Piezas convertidas":"sum","Valor devolución":"sum","Venta recuperada $":"sum","Venta observada":"sum"})
    g["% Conversión"]=(g["Piezas convertidas"].div(g["Dev Pzs"].replace(0,pd.NA))*100).fillna(0).clip(0,100)
    g["% Recuperación económica"]=(g["Venta recuperada $"] .div(g["Valor devolución"].replace(0,pd.NA))*100).fillna(0).clip(0,100)
    return g
