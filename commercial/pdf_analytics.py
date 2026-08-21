"""Analítica comercial construida exclusivamente con los PDF AC semanales."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd


METRIC_MAP = {
    "ids": "IDs", "curve": "Curva", "floor": "Piso", "warehouse": "Bodega",
    "existence": "Existencia", "vpd": "VPD", "ddi": "DDI", "ddc": "DDC",
    "positions": "Posiciones", "models_per_position": "Modelos/posición",
    "inventory_share": "% Inventario", "pieces_share": "% Piezas",
    "sales_share": "% Venta", "investment_share": "% Inversión",
    "utility_share": "% Utilidad", "curve_share": "% Curva",
    "space_share": "% Espacio", "articles_80": "Artículos 80",
    "investment": "Inversión",
}


def snapshots_to_pdf_frames(snapshots: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    breakdown_rows, brand_rows, model_rows = [], [], []
    for snapshot in snapshots or []:
        metadata = {
            "Tienda": snapshot.get("store", ""), "Semana": snapshot.get("week", "Sin semana"),
            "Fecha": snapshot.get("report_date", ""), "Archivo": snapshot.get("file", ""),
        }
        for kind, rows in snapshot.get("breakdowns", {}).items():
            for row in rows or []:
                item = {
                    **metadata, "Tipo": kind, "Etiqueta": row.get("label", ""),
                    "Sección": row.get("section", ""), "Sección detalle": row.get("section_detail", ""),
                }
                item.update({target: row.get(source, 0) for source, target in METRIC_MAP.items()})
                breakdown_rows.append(item)
        for row in snapshot.get("brands", []) or []:
            item = {
                **metadata, "Marca": row.get("label", ""), "Alcance marca": row.get("brand_scope", "General"),
                "Ranking": row.get("rank", 0),
            }
            item.update({target: row.get(source, 0) for source, target in METRIC_MAP.items()})
            brand_rows.append(item)
        for row in snapshot.get("model_rankings", []) or []:
            item = {
                **metadata, "Escenario": row.get("scenario", ""), "Ranking": row.get("rank", 0),
                "Sección": row.get("world", ""), "Sección detalle": row.get("world_detail", ""),
                "ID_ART": row.get("article_id", ""), "Modelo": row.get("model", ""),
                "Color": row.get("color", ""), "Marca": row.get("brand", ""),
                "Rubro": row.get("subcategory", ""),
            }
            item.update({target: row.get(source, 0) for source, target in METRIC_MAP.items()})
            model_rows.append(item)
    return pd.DataFrame(breakdown_rows), pd.DataFrame(brand_rows), pd.DataFrame(model_rows)


def filter_period(frame: pd.DataFrame, week: str | None = None, store: str = "Compañía") -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    if week and week != "Todas" and "Semana" in out:
        out = out[out["Semana"].astype(str).eq(week)]
    if store != "Compañía" and "Tienda" in out:
        out = out[out["Tienda"].astype(str).eq(store)]
    return out.reset_index(drop=True)


def aggregate_pdf(frame: pd.DataFrame, group_column: str) -> pd.DataFrame:
    if frame is None or frame.empty or group_column not in frame:
        return pd.DataFrame()
    sum_columns = [
        column for column in ("IDs", "Curva", "Piso", "Bodega", "Existencia", "VPD", "Posiciones", "Inversión")
        if column in frame
    ]
    out = frame.groupby(group_column, as_index=False)[sum_columns].sum()
    # Los porcentajes publicados no se suman. Se consolidan ponderados por el
    # sugerido para conservar el valor comercial de utilidad, piezas y venta.
    weights = pd.to_numeric(frame.get("VPD", pd.Series(0, index=frame.index)), errors="coerce").fillna(0)
    for percentage in ("% Utilidad", "% Piezas", "% Venta"):
        if percentage not in frame:
            continue
        values = pd.to_numeric(frame[percentage], errors="coerce").fillna(0)
        weighted = (values * weights).groupby(frame[group_column]).sum()
        denominator = weights.groupby(frame[group_column]).sum().replace(0, np.nan)
        fallback = values.groupby(frame[group_column]).mean()
        consolidated = weighted.div(denominator).fillna(fallback).fillna(0)
        out[percentage] = out[group_column].map(consolidated).fillna(0)
    zero = pd.Series(0.0, index=out.index)
    existence = out.get("Existencia", zero)
    suggested = out.get("VPD", zero)
    curve = out.get("Curva", zero)
    warehouse = out.get("Bodega", zero)
    positions = out.get("Posiciones", zero)
    out["DDI"] = existence.div(suggested.replace(0, np.nan)).fillna(0)
    out["DDC"] = curve.div(suggested.replace(0, np.nan)).fillna(0)
    out["Bodega %"] = warehouse.div(existence.replace(0, np.nan)).mul(100).fillna(0)
    out["VPD/posición"] = suggested.div(positions.replace(0, np.nan)).fillna(0)
    return out


def store_pdf_summary(stores: pd.DataFrame, week: str | None = None, store: str = "Compañía") -> pd.DataFrame:
    out = filter_period(stores, week, store)
    if out.empty:
        return out
    out = out.copy()
    for column in ("Modelos", "Curva", "Piso", "Bodega", "Existencia", "VPD", "DDI", "DDC", "Posiciones"):
        if column not in out:
            out[column] = 0.0
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0)
    out["Bodega %"] = out["Bodega"].div(out["Existencia"].replace(0, np.nan)).mul(100).fillna(0)
    out["VPD/posición"] = out["VPD"].div(out["Posiciones"].replace(0, np.nan)).fillna(0)

    def health(ddi):
        if 31 <= ddi <= 90:
            return 100
        if 15 <= ddi <= 120:
            return 72
        if 7 <= ddi <= 150:
            return 48
        return 25

    out["Score"] = (
        out["DDI"].map(health) * .55
        + out["VPD"].rank(pct=True).mul(100) * .30
        + (100 - out["Bodega %"].clip(0, 100)) * .15
    ).round(0)
    out["Estatus"] = np.select(
        [out["Score"].ge(80), out["Score"].ge(55)], ["Óptimo", "Atención"], default="Crítico"
    )
    return out.sort_values(["Score", "VPD"], ascending=[False, False]).reset_index(drop=True)


def business_location_summary(breakdowns: pd.DataFrame, week: str, store: str) -> pd.DataFrame:
    data = filter_period(breakdowns, week, store)
    if data.empty:
        return data
    location = data[data["Tipo"].eq("location")].copy()
    rubro = data[data["Tipo"].eq("rubro")].copy()
    rows = []

    def append_group(name: str, frame: pd.DataFrame, source: str):
        if frame.empty:
            return
        totals = frame[[column for column in ("IDs", "Curva", "Piso", "Bodega", "Existencia", "VPD", "Posiciones") if column in frame]].sum()
        existence, vpd, curve = totals.get("Existencia", 0), totals.get("VPD", 0), totals.get("Curva", 0)
        rows.append({
            "Ubicación": name, **totals.to_dict(), "DDI": existence / vpd if vpd else 0,
            "DDC": curve / vpd if vpd else 0, "VPD/posición": vpd / totals.get("Posiciones", 0) if totals.get("Posiciones", 0) else 0,
            "Origen": source,
        })

    labels = location["Etiqueta"].astype(str).str.upper()
    append_group("Doblado", location[labels.str.contains("DOBL") & ~labels.str.contains("MEZ|JEAN")], "Ubicación PDF")
    append_group("Colgado", location[labels.str.contains("COLG")], "Ubicación PDF")
    append_group("Jeans", location[labels.str.contains("MEZ|JEAN")], "Ubicación PDF")
    lingerie_pattern = r"LENCER|BRASIER|PANTALETA|PANTIBLUSA|ROPA INTERIOR|BODY|CAMISON"
    append_group("Lencería", rubro[rubro["Etiqueta"].astype(str).str.upper().str.contains(lingerie_pattern, regex=True)], "Rubro PDF")
    return pd.DataFrame(rows)


def company_projection(stores: pd.DataFrame, horizons=(0, 7, 14, 30, 60)) -> pd.DataFrame:
    if stores is None or stores.empty:
        return pd.DataFrame()
    existence = float(stores["Existencia"].sum())
    vpd = float(stores["VPD"].sum())
    return pd.DataFrame({
        "Días": list(horizons),
        "Existencia proyectada": [max(existence - vpd * day, 0) for day in horizons],
        "Consumo proyectado": [min(vpd * day, existence) for day in horizons],
    })


def pdf_opportunities(stores: pd.DataFrame, breakdowns: pd.DataFrame, models: pd.DataFrame) -> pd.DataFrame:
    columns = ["Prioridad", "Oportunidad", "Tienda", "Elemento", "Recomendación", "Piezas", "Indicador", "Confianza"]
    rows = []
    for _, row in (stores if stores is not None else pd.DataFrame()).iterrows():
        ddi, vpd, existence = float(row.get("DDI", 0)), float(row.get("VPD", 0)), float(row.get("Existencia", 0))
        if vpd > 0 and ddi <= 30:
            pieces = max(vpd * 45 - existence, 0)
            rows.append(["Alta" if ddi <= 14 else "Media", "Riesgo de agotamiento", row.get("Tienda", ""), "Tienda", f"Asegurar cobertura para 45 días", pieces, f"DDI {ddi:.0f}", 94])
        if ddi > 120:
            rows.append(["Alta" if ddi > 180 else "Media", "Sobrecobertura", row.get("Tienda", ""), "Tienda", "Revisar transferencias y espacio", max(existence - vpd * 90, 0), f"DDI {ddi:.0f}", 90])
        bodega = float(row.get("Bodega", 0))
        if existence and bodega / existence > .20 and vpd > 0:
            rows.append(["Media", "Concentración en bodega", row.get("Tienda", ""), "Bodega", "Bajar mercancía prioritaria a piso", min(bodega, vpd * 14), f"{bodega/existence:.0%} en bodega", 86])

    data = breakdowns if breakdowns is not None else pd.DataFrame()
    if not data.empty:
        catalog = data[data["Tipo"].eq("catalog") & data["Etiqueta"].astype(str).str.upper().str.contains("DESCONT|PROXIMO")]
        for _, row in catalog.iterrows():
            if float(row.get("Existencia", 0)) <= 0:
                continue
            rows.append(["Alta" if float(row.get("DDI", 0)) > 120 else "Media", "Catálogo de salida", row.get("Tienda", ""), row.get("Etiqueta", ""), "Acelerar salida y liberar espacio", row.get("Existencia", 0), f"DDI {float(row.get('DDI', 0)):.0f}", 92])

    model_data = models if models is not None else pd.DataFrame()
    if not model_data.empty:
        latest = model_data.sort_values(["Semana", "Ranking"]).drop_duplicates(["Tienda", "ID_ART"], keep="first")
        slow = latest[(latest["VPD"].le(0) | latest["DDI"].gt(150)) & latest["Existencia"].gt(10)].nlargest(80, "Existencia")
        for _, row in slow.iterrows():
            rows.append(["Media", "Modelo lento", row.get("Tienda", ""), f"{row.get('ID_ART', '')} / {row.get('Modelo', '')}", "Reducir espacio o transferir", row.get("Existencia", 0), f"VPD {float(row.get('VPD', 0)):.0f} · DDI {float(row.get('DDI', 0)):.0f}", 84])

        for article, group in latest.groupby("ID_ART"):
            if len(group) < 2:
                continue
            source = group.sort_values("DDI", ascending=False).iloc[0]
            target = group.sort_values("DDI").iloc[0]
            if float(source.get("DDI", 0)) <= 120 or float(target.get("DDI", 0)) >= 30 or source.get("Tienda") == target.get("Tienda"):
                continue
            available = max(float(source.get("Existencia", 0)) - float(source.get("VPD", 0)) * 90, 0)
            needed = max(float(target.get("VPD", 0)) * 45 - float(target.get("Existencia", 0)), 0)
            pieces = min(available, needed)
            if pieces > 0:
                rows.append(["Alta", "Transferencia entre tiendas", source.get("Tienda", ""), str(article), f"Transferir a {target.get('Tienda', '')}", pieces, f"DDI {source.get('DDI', 0):.0f} → {target.get('DDI', 0):.0f}", 91])

    result = pd.DataFrame(rows, columns=columns)
    if result.empty:
        return result
    order = pd.Categorical(result["Prioridad"], ["Alta", "Media", "Baja"], ordered=True)
    return result.assign(_orden=order).sort_values(["_orden", "Piezas"], ascending=[True, False]).drop(columns="_orden").reset_index(drop=True)
