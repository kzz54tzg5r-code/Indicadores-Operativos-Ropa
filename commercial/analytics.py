"""Cálculos auditables del módulo de Ventas y Análisis Comercial."""

from __future__ import annotations

import numpy as np
import pandas as pd


def merge_model_sales(capacity: pd.DataFrame, sales: pd.DataFrame) -> pd.DataFrame:
    capacity = capacity.copy() if capacity is not None else pd.DataFrame()
    sales = sales.copy() if sales is not None else pd.DataFrame()
    if capacity.empty:
        return capacity
    if sales.empty or "Modelo" not in sales.columns:
        return capacity

    sales = sales[sales["Modelo"].astype(str).str.strip().ne("")].copy()
    if sales.empty:
        return capacity
    grouped = sales.groupby(["Tienda", "Modelo"], as_index=False)[["Venta pzas", "Venta $"]].sum()
    grouped = grouped.rename(columns={"Venta pzas": "Venta pzas fuente", "Venta $": "Venta $ fuente"})
    out = capacity.merge(grouped, on=["Tienda", "Modelo"], how="left")
    has_external = out["Venta pzas fuente"].notna() | out["Venta $ fuente"].notna()
    out.loc[has_external, "Venta pzas"] = out.loc[has_external, "Venta pzas fuente"].fillna(0)
    out.loc[has_external, "Venta $"] = out.loc[has_external, "Venta $ fuente"].fillna(0)
    out["Utilidad $"] = out["Venta $"] * out["Utilidad %"] / 100
    return out.drop(columns=["Venta pzas fuente", "Venta $ fuente"], errors="ignore")


def snapshots_to_frames(snapshots: list[dict]):
    store_rows, section_rows, location_rows = [], [], []
    for snapshot in snapshots or []:
        store_rows.append({
            "Tienda": snapshot.get("store", ""),
            "Fecha": snapshot.get("report_date", ""),
            "Semana": snapshot.get("week", "Sin semana"),
            "Archivo": snapshot.get("file", ""),
            "Modelos": snapshot.get("models", 0),
            "Curva": snapshot.get("curve", 0),
            "Piso": snapshot.get("floor", 0),
            "Bodega": snapshot.get("warehouse", 0),
            "Existencia": snapshot.get("existence", 0),
            "VPD": snapshot.get("vpd", 0),
            "DDI": snapshot.get("ddi", 0),
            "DDC": snapshot.get("ddc", 0),
            "Posiciones": snapshot.get("positions", 0),
            "Estatus": snapshot.get("status", "Revisar"),
        })
        for row in snapshot.get("sections", []):
            section_rows.append({**row, "Fecha": snapshot.get("report_date", ""), "Semana": snapshot.get("week", "")})
        for row in snapshot.get("locations", []):
            location_rows.append({**row, "Fecha": snapshot.get("report_date", ""), "Semana": snapshot.get("week", "")})
    return pd.DataFrame(store_rows), pd.DataFrame(section_rows), pd.DataFrame(location_rows)


def latest_store_snapshots(store_history: pd.DataFrame) -> pd.DataFrame:
    if store_history is None or store_history.empty:
        return pd.DataFrame()
    out = store_history.copy()
    out["Fecha orden"] = pd.to_datetime(out["Fecha"], errors="coerce")
    out = out.sort_values(["Fecha orden", "Archivo"]).groupby("Tienda", as_index=False).tail(1)
    return out.drop(columns=["Fecha orden"], errors="ignore").reset_index(drop=True)


def store_summary(models: pd.DataFrame, sales: pd.DataFrame, store_history: pd.DataFrame) -> pd.DataFrame:
    rows = pd.DataFrame()
    if models is not None and not models.empty:
        base = models.groupby("Tienda", as_index=False).agg({
            "Modelo": "nunique",
            "Venta pzas": "sum",
            "Venta $": "sum",
            "Utilidad $": "sum",
            "Existencia": "sum",
            "Inversión": "sum",
            "VPD": "sum",
        }).rename(columns={"Modelo": "Modelos"})
        base["Utilidad %"] = base["Utilidad $"].div(base["Venta $"].replace(0, np.nan)).mul(100).fillna(0)
        base["DDI"] = base["Existencia"].div(base["VPD"].replace(0, np.nan)).fillna(0)
        rows = base

    sales_by_store = pd.DataFrame()
    if sales is not None and not sales.empty:
        sales_by_store = sales.groupby("Tienda", as_index=False)[["Venta pzas", "Venta $"]].sum()
        sales_by_store = sales_by_store.rename(columns={"Venta pzas": "Venta pzas sales", "Venta $": "Venta $ sales"})
    if rows.empty and not sales_by_store.empty:
        rows = sales_by_store.rename(columns={"Venta pzas sales": "Venta pzas", "Venta $ sales": "Venta $"})
        for column in ("Modelos", "Utilidad $", "Existencia", "Inversión", "VPD", "Utilidad %", "DDI"):
            rows[column] = 0.0
    elif not sales_by_store.empty:
        rows = rows.merge(sales_by_store, on="Tienda", how="outer")
        rows["Venta pzas"] = rows["Venta pzas sales"].where(rows["Venta pzas sales"].notna(), rows["Venta pzas"])
        rows["Venta $"] = rows["Venta $ sales"].where(rows["Venta $ sales"].notna(), rows["Venta $"])
        rows = rows.drop(columns=["Venta pzas sales", "Venta $ sales"], errors="ignore")

    latest = latest_store_snapshots(store_history)
    if rows.empty and not latest.empty:
        rows = latest[["Tienda", "Modelos", "Existencia", "VPD", "DDI"]].copy()
        for column in ("Venta pzas", "Venta $", "Utilidad $", "Inversión", "Utilidad %"):
            rows[column] = 0.0
    elif not latest.empty:
        overlay = latest[["Tienda", "Modelos", "Existencia", "VPD", "DDI"]].rename(columns={
            "Modelos": "Modelos PDF", "Existencia": "Existencia PDF", "VPD": "VPD PDF", "DDI": "DDI PDF",
        })
        rows = rows.merge(overlay, on="Tienda", how="outer")
        for target, source in (("Modelos", "Modelos PDF"), ("Existencia", "Existencia PDF"), ("VPD", "VPD PDF"), ("DDI", "DDI PDF")):
            rows[target] = rows[source].where(rows[source].notna(), rows.get(target, 0))
        rows = rows.drop(columns=["Modelos PDF", "Existencia PDF", "VPD PDF", "DDI PDF"], errors="ignore")

    if rows.empty:
        return rows
    for column in ("Modelos", "Venta pzas", "Venta $", "Utilidad $", "Existencia", "Inversión", "VPD", "Utilidad %", "DDI"):
        if column not in rows:
            rows[column] = 0.0
        rows[column] = pd.to_numeric(rows[column], errors="coerce").fillna(0.0)
    rows["Score"] = commercial_score(rows)
    rows["Estatus"] = np.select(
        [rows["Score"] >= 80, rows["Score"] >= 60],
        ["Óptimo", "Atención"],
        default="Crítico",
    )
    return rows.sort_values("Venta $", ascending=False).reset_index(drop=True)


def commercial_score(stores: pd.DataFrame) -> pd.Series:
    if stores is None or stores.empty:
        return pd.Series(dtype=float)
    def scaled(column, inverse=False):
        values = pd.to_numeric(stores.get(column, 0), errors="coerce").fillna(0)
        low, high = values.min(), values.max()
        score = pd.Series(50.0, index=values.index) if high == low else (values - low) / (high - low) * 100
        return 100 - score if inverse else score
    return (scaled("Venta $") * .35 + scaled("Utilidad %") * .25 + scaled("VPD") * .25 + scaled("DDI", inverse=True) * .15).round(0)


def weekly_sales(sales: pd.DataFrame) -> pd.DataFrame:
    if sales is None or sales.empty or "Fecha" not in sales:
        return pd.DataFrame()
    out = sales.copy()
    out["Fecha"] = pd.to_datetime(out["Fecha"], errors="coerce")
    out = out[out["Fecha"].notna()]
    if out.empty:
        return pd.DataFrame()
    iso = out["Fecha"].dt.isocalendar()
    out["Año"] = iso.year.astype(int)
    out["Semana ISO"] = iso.week.astype(int)
    grouped = out.groupby(["Año", "Semana ISO"], as_index=False)[["Venta pzas", "Venta $"]].sum()
    grouped["Periodo"] = grouped.apply(lambda row: f"{int(row['Año'])}-S{int(row['Semana ISO']):02d}", axis=1)
    return grouped.sort_values(["Año", "Semana ISO"]).reset_index(drop=True)


def location_summary(models: pd.DataFrame, location_history: pd.DataFrame) -> pd.DataFrame:
    if models is not None and not models.empty:
        grouped = models.groupby("Ubicación", as_index=False).agg({
            "Modelo": "nunique", "Venta pzas": "sum", "Venta $": "sum",
            "Utilidad $": "sum", "Existencia": "sum", "Inversión": "sum", "VPD": "sum",
        }).rename(columns={"Modelo": "Modelos"})
        grouped["Utilidad %"] = grouped["Utilidad $"].div(grouped["Venta $"].replace(0, np.nan)).mul(100).fillna(0)
        grouped["DDI"] = grouped["Existencia"].div(grouped["VPD"].replace(0, np.nan)).fillna(0)
        return grouped.sort_values("Venta $", ascending=False)
    if location_history is not None and not location_history.empty:
        latest = location_history.copy()
        latest["Fecha orden"] = pd.to_datetime(latest["Fecha"], errors="coerce")
        latest = latest.sort_values("Fecha orden").groupby(["Tienda", "Ubicación"], as_index=False).tail(1)
        grouped = latest.groupby("Ubicación", as_index=False).agg({
            "Modelos": "sum", "Existencia": "sum", "VPD": "sum", "DDI": "mean",
        })
        for column in ("Venta pzas", "Venta $", "Utilidad $", "Inversión", "Utilidad %"):
            grouped[column] = 0.0
        return grouped
    return pd.DataFrame()


def section_summary(models: pd.DataFrame, section_history: pd.DataFrame) -> pd.DataFrame:
    if models is not None and not models.empty:
        grouped = models.groupby("Sección", as_index=False).agg({
            "Modelo": "nunique", "Venta pzas": "sum", "Venta $": "sum",
            "Utilidad $": "sum", "Existencia": "sum", "Inversión": "sum", "VPD": "sum",
        }).rename(columns={"Modelo": "Modelos"})
        grouped["Utilidad %"] = grouped["Utilidad $"].div(grouped["Venta $"].replace(0, np.nan)).mul(100).fillna(0)
        return grouped.sort_values("Venta $", ascending=False)
    if section_history is not None and not section_history.empty:
        latest = section_history.copy()
        latest["Fecha orden"] = pd.to_datetime(latest["Fecha"], errors="coerce")
        latest = latest.sort_values("Fecha orden").groupby(["Tienda", "Sección detalle"], as_index=False).tail(1)
        grouped = latest.groupby("Sección", as_index=False).agg({"Modelos": "sum", "Existencia": "sum", "VPD": "sum"})
        for column in ("Venta pzas", "Venta $", "Utilidad $", "Inversión", "Utilidad %"):
            grouped[column] = 0.0
        return grouped
    return pd.DataFrame()


def rank_models(models: pd.DataFrame, scenario="Sugerido / VPD") -> pd.DataFrame:
    if models is None or models.empty:
        return pd.DataFrame()
    out = models.copy()
    out["Rotación"] = out["Venta pzas"].where(out["Venta pzas"].gt(0), out["VPD"] * 30)
    out["Aporte utilidad"] = out["Venta $"] * out["Utilidad %"] / 100
    if scenario == "Utilidad":
        out["Puntaje"] = out["Aporte utilidad"]
    else:
        out["Puntaje"] = out["VPD"]
    out["Estado modelo"] = np.select(
        [(out["Puntaje"] > 0) & (out["DDI"].between(15, 90)), out["DDI"] > 90],
        ["Campeón", "Lento"],
        default="En riesgo",
    )
    return out.sort_values(["Puntaje", "Venta $"], ascending=False).reset_index(drop=True)


def inventory_buckets(models: pd.DataFrame) -> pd.DataFrame:
    if models is None or models.empty:
        return pd.DataFrame(columns=["Estado", "Modelos", "Existencia", "Inversión"])
    out = models.copy()
    out["Estado"] = pd.cut(
        out["DDI"],
        bins=[-np.inf, 14, 30, 90, np.inf],
        labels=["Crítico (0-14 días)", "Bajo (15-30 días)", "Saludable (31-90 días)", "Exceso (+90 días)"],
    ).astype(str)
    return out.groupby("Estado", as_index=False, observed=True).agg({
        "Modelo": "nunique", "Existencia": "sum", "Inversión": "sum",
    }).rename(columns={"Modelo": "Modelos"})


def opportunities(models: pd.DataFrame) -> pd.DataFrame:
    columns = ["Prioridad", "Oportunidad", "Tienda", "Modelo", "Recomendación", "Impacto $", "Confianza", "Estatus"]
    if models is None or models.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for _, row in models.iterrows():
        ddi = float(row.get("DDI", 0))
        vpd = float(row.get("VPD", 0))
        existence = float(row.get("Existencia", 0))
        price = float(row.get("Precio unitario", 0))
        investment = float(row.get("Inversión", 0))
        utility = float(row.get("Utilidad %", 0))
        if vpd > 0 and ddi <= 14:
            pieces = max(int(vpd * 30 - existence), 1)
            rows.append(["Alta", "Riesgo de agotamiento", row["Tienda"], row["Modelo"], f"Resurtir {pieces:,} pzas", pieces * price, 94, "Pendiente"])
        elif ddi > 90 and existence > 0:
            rows.append(["Alta" if ddi > 150 else "Media", "Sobrestock", row["Tienda"], row["Modelo"], "Transferir o reducir espacio", investment * .25, 89, "Pendiente"])
        elif utility < 20 and float(row.get("Venta $", 0)) > 0:
            rows.append(["Media", "Baja utilidad", row["Tienda"], row["Modelo"], "Revisar precio y ubicación", float(row.get("Venta $", 0)) * .08, 82, "Pendiente"])
    result = pd.DataFrame(rows, columns=columns)
    if result.empty:
        return result
    priority_order = pd.Categorical(result["Prioridad"], ["Alta", "Media", "Baja"], ordered=True)
    result = result.assign(_priority=priority_order).sort_values(["_priority", "Impacto $"], ascending=[True, False])
    return result.drop(columns="_priority").reset_index(drop=True)


def forecast(models: pd.DataFrame, sales: pd.DataFrame, weeks=12, multiplier=1.0) -> pd.DataFrame:
    weeks = max(1, int(weeks))
    history = weekly_sales(sales)
    if not history.empty and history["Venta $"].tail(4).sum() > 0:
        base_sales = float(history["Venta $"].tail(4).mean())
        base_pieces = float(history["Venta pzas"].tail(4).mean())
    elif models is not None and not models.empty:
        base_pieces = float(models["VPD"].sum() * 7)
        average_price = float(models["Precio unitario"].replace(0, np.nan).median())
        base_sales = base_pieces * (average_price if np.isfinite(average_price) else 0)
    else:
        base_sales = base_pieces = 0.0
    utility = 0.0
    inventory = 0.0
    if models is not None and not models.empty:
        utility = float(models["Utilidad $"].sum() / max(models["Venta $"].sum(), 1) * 100)
        inventory = float(models["Existencia"].sum())
    rows = []
    remaining = inventory
    for number in range(1, weeks + 1):
        seasonal = 1 + min(number - 1, 8) * 0.004
        projected_pieces = base_pieces * multiplier * seasonal
        projected_sales = base_sales * multiplier * seasonal
        remaining = max(remaining - projected_pieces, 0)
        rows.append({
            "Semana": number,
            "Venta proyectada": projected_sales,
            "Piezas proyectadas": projected_pieces,
            "Utilidad %": utility,
            "Inventario final": remaining,
        })
    return pd.DataFrame(rows)
