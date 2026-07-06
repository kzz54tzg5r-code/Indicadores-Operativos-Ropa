
import pandas as pd
import numpy as np
from .utils import safe_div, norm_text

def resumen_ejecutivo(op):
    ingresos = float(op["Número de Piezas"].sum()) if not op.empty and "Número de Piezas" in op else 0
    hab = float(op["Acondicionado"].sum()) if not op.empty and "Acondicionado" in op else 0
    ubi = float(op["Ubicado"].sum()) if not op.empty and "Ubicado" in op else 0
    return {
        "Ingresos": ingresos,
        "Acondicionado": hab,
        "Ubicado": ubi,
        "Pendiente": max(ingresos - ubi, 0),
        "% Acondicionado": safe_div(hab, ingresos),
        "% Ubicado": safe_div(ubi, ingresos),
    }

def operational_table(op, tiendas_base=None):
    tiendas = sorted(set((tiendas_base or []) + (op["Tienda"].dropna().astype(str).tolist() if not op.empty and "Tienda" in op else [])))
    rows = []

    for t in tiendas:
        ot = op[op["Tienda"] == t] if not op.empty and "Tienda" in op else pd.DataFrame()

        if not ot.empty:
            act = ot["Actividad Realizada"].map(norm_text)
            mot = ot["Motivo de ingreso"].map(norm_text)
            pzs = ot["Número de Piezas"]

            dev = float(pzs[(mot.str.contains("DEV|ADUANA|CAMBIO", na=False)) | (act.str.contains("ADUANA|CAMBIO|DEV", na=False))].sum())
            muertos = float(pzs[(mot.str.contains("MUERTO", na=False)) | (act.str.contains("MUERTO", na=False))].sum())
            cajas = float(pzs[(mot.str.contains("CAJA", na=False)) | (act.str.contains("CAJA", na=False))].sum())
            probador = float(pzs[(mot.str.contains("PROB", na=False)) | (act.str.contains("PROB", na=False))].sum())

            total = dev + muertos + cajas + probador
            if total == 0:
                total = float(pzs.sum())

            reco = float(pzs[act.str.contains("RECOLECT|RECOLEC", na=False)].sum()) or total
            hab = float(ot["Acondicionado"].sum())
            ubi = float(ot["Ubicado"].sum())
        else:
            dev = muertos = cajas = probador = total = reco = hab = ubi = 0

        rows.append({
            "Tienda": t,
            "Dev pzs": dev,
            "Muertos": muertos,
            "Cajas": cajas,
            "Probador": probador,
            "Total": total,
            "Recolectadas": reco,
            "Habilitadas": hab,
            "Pend. Hab.": max(total - hab, 0),
            "% Acond.": safe_div(hab, total),
            "Ubicadas": ubi,
            "Pend. Ubic.": max(total - ubi, 0),
            "% Ubic.": safe_div(ubi, total),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        for c in [x for x in df.columns if x not in ["Tienda", "% Acond.", "% Ubic."]]:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(0).astype(int)
        df["% Acond."] = df["% Acond."].round(1)
        df["% Ubic."] = df["% Ubic."].round(1)

    return df

def productividad(op, meta=784):
    if op.empty or "Nombre" not in op:
        return pd.DataFrame()

    df = op.copy()
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    grouped = df.groupby(["Nombre", "Tienda"], dropna=False).agg(
        Piezas=("Número de Piezas", "sum"),
        Registros=("Número de Piezas", "count"),
        Dias=("Fecha", lambda s: max(s.dt.date.nunique(), 1))
    ).reset_index()

    grouped["Productividad diaria"] = (grouped["Piezas"] / grouped["Dias"]).round(1)
    grouped["Meta diaria"] = meta
    grouped["% Cumplimiento"] = (grouped["Productividad diaria"] / meta * 100).round(1) if meta else 0
    return grouped.sort_values(["Productividad diaria", "Piezas"], ascending=False)

def indice_actividades(op):
    if op.empty:
        return pd.DataFrame()

    return (
        op.groupby(["Tienda", "Nombre", "Actividad Realizada"], dropna=False)
        .agg(Piezas=("Número de Piezas", "sum"), Registros=("Número de Piezas", "count"))
        .reset_index()
        .sort_values(["Nombre", "Piezas"], ascending=[True, False])
    )

def conversion(co):
    if co.empty:
        return pd.DataFrame(), {"Dev Pzs": 0, "Conversión Pzs": 0, "Conversión $": 0, "Pendiente Pzs": 0, "% Conversión": 0, "No Convertido $": 0}

    group_cols = [c for c in ["Semana ISO", "Tienda", "ID/Modelo", "Color"] if c in co.columns]
    if not group_cols:
        group_cols = ["Semana ISO"]

    grouped = co.groupby(group_cols, dropna=False).agg(
        **{
            "Dev Pzs Semana": ("Dev_Pzs", "sum"),
            "Venta Pzs Semana": ("Vta_Pzs", "sum"),
            "Venta $ Semana": ("Vta_Imp", "sum"),
            "Costo Dev Semana": ("Costo_Dev", "sum")
        }
    ).reset_index()

    grouped["Conversión Dev → Venta Pzs"] = grouped[["Dev Pzs Semana", "Venta Pzs Semana"]].min(axis=1)
    ratio = grouped["Conversión Dev → Venta Pzs"] / grouped["Venta Pzs Semana"].replace(0, np.nan)
    grouped["Conversión Dev → Venta $"] = (grouped["Venta $ Semana"] * ratio.fillna(0)).fillna(0)
    grouped["Pendiente por Convertir Pzs"] = (grouped["Dev Pzs Semana"] - grouped["Conversión Dev → Venta Pzs"]).clip(lower=0)
    pending_ratio = grouped["Pendiente por Convertir Pzs"] / grouped["Dev Pzs Semana"].replace(0, np.nan)
    grouped["Venta No Convertida $"] = (grouped["Costo Dev Semana"] * pending_ratio.fillna(0)).fillna(0)
    grouped["% Conversión Semanal Dev → Venta"] = (grouped["Conversión Dev → Venta Pzs"] / grouped["Dev Pzs Semana"].replace(0, np.nan) * 100).fillna(0)

    kpis = {
        "Dev Pzs": grouped["Dev Pzs Semana"].sum(),
        "Conversión Pzs": grouped["Conversión Dev → Venta Pzs"].sum(),
        "Conversión $": grouped["Conversión Dev → Venta $"].sum(),
        "Pendiente Pzs": grouped["Pendiente por Convertir Pzs"].sum(),
        "No Convertido $": grouped["Venta No Convertida $"].sum(),
    }
    kpis["% Conversión"] = safe_div(kpis["Conversión Pzs"], kpis["Dev Pzs"])
    return grouped, kpis
