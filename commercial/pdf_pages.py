"""Páginas del análisis comercial alimentadas únicamente por PDF AC."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
import html
import re

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from .config import ADMIN_PAGE, COMMERCIAL_PAGES, PAGE_LABELS, PROJECT_STORES
from .parsers import extract_pdf_snapshot
from .pdf_analytics import (
    aggregate_pdf,
    business_location_summary,
    company_projection,
    filter_period,
    pdf_opportunities,
    store_pdf_summary,
)
from .storage import (
    build_history_backup,
    cloud_enabled,
    load_manifest,
    resolve_entry_path,
    restore_history_backup,
    save_pdf_upload,
    save_snapshot,
    sync_history_to_cloud,
    update_entry,
)

NAVY = "#173B73"
BLUE = "#155BEF"
PINK = "#E6007E"
GREEN = "#079447"
ORANGE = "#F28C00"
RED = "#E52B50"
CYAN = "#05A9D6"
PURPLE = "#7C3AED"


def _number(value) -> str:
    return f"{float(value or 0):,.0f}"


def _percent(value) -> str:
    return f"{float(value or 0):,.1f}%"


def _money(value) -> str:
    value = float(value or 0)
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.1f} M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:,.0f} mil"
    return f"${value:,.0f}"


def _latest_week(values) -> str:
    clean = [str(value).strip() for value in values if str(value).strip()]
    weeks = [value for value in clean if re.fullmatch(r"\d{4}-W\d{2}", value)]
    return max(weeks) if weeks else (max(clean) if clean else "Sin semana")


def _header(title: str, subtitle: str, bundle: dict) -> None:
    pdfs = bundle["manifest"].get("pdfs", [])
    week = _latest_week(item.get("week", "") for item in pdfs)
    current = [item for item in pdfs if str(item.get("week", "")) == week]
    stores = {str(item.get("store", "")).strip() for item in current if str(item.get("store", "")).strip()}
    updated = str(bundle["manifest"].get("updated_at", ""))[:16].replace("T", " · ") or "Sin actualización"
    st.markdown(
        f'<div class="ac-header"><div><div class="ac-title">{html.escape(title)}</div>'
        f'<div class="ac-subtitle">{html.escape(subtitle)}</div></div><div class="ac-status">'
        f'<span class="ac-pill">✓ {len(stores)} de 17 PDF procesados</span>'
        f'<span class="ac-pill ac-pill-blue">{html.escape(week)}</span>'
        f'<span class="ac-updated">Actualizado {html.escape(updated)}</span></div></div>',
        unsafe_allow_html=True,
    )


def _top_navigation(active_page: str) -> None:
    """La Propuesta C usa una sola navegación lateral para evitar duplicidad."""
    return None


def _kpis(items, columns: int | None = None) -> None:
    blocks = []
    for label, value, note, color in items:
        blocks.append(
            f'<div class="ac-kpi" style="--accent:{color}"><div class="ac-kpi-label">{html.escape(str(label))}</div>'
            f'<div class="ac-kpi-value">{html.escape(str(value))}</div><div class="ac-kpi-note">{html.escape(str(note))}</div></div>'
        )
    st.markdown(
        f'<div class="ac-kpis" style="--columns:{columns or min(max(len(blocks), 1), 8)}">'
        + "".join(blocks) + "</div>", unsafe_allow_html=True,
    )


def _plot(fig, height=380):
    fig.update_layout(
        height=height, margin=dict(l=24, r=20, t=50, b=35), paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="Arial", color=NAVY, size=11), legend=dict(orientation="h", y=1.13, x=0),
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "responsive": True})


def _weeks(bundle: dict) -> list[str]:
    frame = bundle["stores_pdf"]
    if frame.empty:
        return ["Sin semana"]
    values = sorted({str(value) for value in frame["Semana"] if str(value)}, reverse=True)
    return values or ["Sin semana"]


def _clear_scope(prefix: str) -> None:
    for suffix in ("week", "store", "scenario", "section", "metric", "type", "brand_scope"):
        st.session_state.pop(f"{prefix}_{suffix}", None)


def _scope(bundle: dict, prefix: str, *, scenario=False, section=False):
    weeks = _weeks(bundle)
    stores = sorted(bundle["stores_pdf"].get("Tienda", pd.Series(dtype=str)).dropna().astype(str).unique())
    columns = 4 if scenario or section else 3
    with st.container(border=True):
        st.markdown('<div class="ac-filter-caption">FILTROS DEL REPORTE PDF</div>', unsafe_allow_html=True)
        layout = st.columns(columns, vertical_alignment="bottom")
        with layout[0]:
            week = st.selectbox("Semana", weeks, key=f"{prefix}_week", format_func=lambda x: x.replace("-W", " · Semana "))
        with layout[1]:
            store = st.selectbox("Alcance", ["Compañía"] + stores, key=f"{prefix}_store")
        extra = None
        if scenario:
            values = sorted(bundle["models_pdf"].get("Escenario", pd.Series(dtype=str)).dropna().astype(str).unique())
            with layout[2]:
                extra = st.selectbox("Ranking PDF", values or ["Utilidad"], key=f"{prefix}_scenario")
        elif section:
            values = sorted(bundle["breakdowns"].get("Sección", pd.Series(dtype=str)).replace("", np.nan).dropna().astype(str).unique())
            with layout[2]:
                extra = st.selectbox("Sección", ["Todas"] + values, key=f"{prefix}_section")
        with layout[-1]:
            st.button("Limpiar filtros", icon=":material/filter_alt_off:", on_click=_clear_scope, args=(prefix,), width="stretch")
    return week, store, extra


def _current(bundle: dict, week: str, store: str):
    stores = store_pdf_summary(bundle["stores_pdf"], week, store)
    breakdowns = filter_period(bundle["breakdowns"], week, store)
    brands = filter_period(bundle["brands"], week, store)
    models = filter_period(bundle["models_pdf"], week, store)
    return stores, breakdowns, brands, models


def _totals(stores: pd.DataFrame) -> dict:
    if stores.empty:
        return {name: 0.0 for name in ("Modelos", "Curva", "Piso", "Bodega", "Existencia", "VPD", "DDI", "DDC", "Posiciones")}
    out = {column: float(stores.get(column, pd.Series(dtype=float)).sum()) for column in ("Modelos", "Curva", "Piso", "Bodega", "Existencia", "VPD", "Posiciones")}
    out["DDI"] = out["Existencia"] / out["VPD"] if out["VPD"] else 0
    out["DDC"] = out["Curva"] / out["VPD"] if out["VPD"] else 0
    return out


def _no_data() -> None:
    st.info("Carga los PDF AC semanales para mostrar esta vista.")


def _coverage_status(days: float) -> str:
    if days <= 0:
        return "Sin rotación"
    if days <= 30:
        return "Crítico"
    if days <= 90:
        return "Óptimo"
    if days <= 120:
        return "Atención"
    return "Exceso"


def _coverage_action(days: float, warehouse_share: float = 0) -> str:
    if days <= 0:
        return "Revisar modelo"
    if days <= 30:
        return "Resurtir"
    if days > 120:
        return "Transferir"
    if warehouse_share > 20:
        return "Bajar a piso"
    return "Mantener"


def _coverage_meaning(days: float) -> str:
    if days <= 0:
        return "Sin salida registrada"
    if days <= 30:
        return "Puede agotarse"
    if days > 120:
        return "Hay inventario de más"
    if days > 90:
        return "Requiere revisión"
    return "Inventario equilibrado"


def _friendly_store_table(stores: pd.DataFrame) -> pd.DataFrame:
    if stores.empty:
        return stores
    out = stores.copy()
    out["Estado"] = out["DDI"].map(_coverage_status)
    out["Qué significa"] = out["DDI"].map(_coverage_meaning)
    out["Qué hacer"] = [
        _coverage_action(float(days), float(warehouse))
        for days, warehouse in zip(out["DDI"], out.get("Bodega %", pd.Series(0, index=out.index)))
    ]
    return out.rename(columns={"VPD": "Venta diaria sugerida", "DDI": "Días de inventario"})


def _table_style(frame: pd.DataFrame, status_columns=()):
    colors = {
        "Óptimo": "#DDF7E8", "Bien": "#DDF7E8", "Mantener": "#DDF7E8", "Seguimiento": "#DDF7E8",
        "Atención": "#FFF1D8", "Exceso": "#FFE4EF", "Transferir": "#EEE8FF", "Bajar a piso": "#E8F2FF",
        "Crítico": "#FFE2E7", "Alta": "#FFE2E7", "Hoy": "#FFE2E7", "Resurtir": "#FFE2E7",
        "Media": "#FFF1D8", "Esta semana": "#FFF1D8", "Reducir": "#FFE4EF", "Impulsar": "#E8F2FF",
    }

    def paint(value):
        background = colors.get(str(value), "")
        return f"background-color: {background}; font-weight: 700; color: #173B73" if background else ""

    styler = frame.style.set_properties(**{"font-size": "12px", "color": "#173B73"})
    styler = styler.set_table_styles([
        {"selector": "th", "props": [("background-color", "#EAF0F8"), ("color", "#173B73"), ("font-weight", "800")]},
        {"selector": "td", "props": [("border-bottom", "1px solid #E5EAF1")]},
    ])
    for column in status_columns:
        if column in frame:
            styler = styler.map(paint, subset=[column])
    return styler


def _decision_table(frame: pd.DataFrame, *, status_columns=(), height=360) -> None:
    if frame is None or frame.empty:
        st.info("No hay registros para el alcance seleccionado.")
        return
    st.dataframe(_table_style(frame, status_columns), width="stretch", height=height, hide_index=True)


def _plain_opportunities(data: pd.DataFrame) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()
    meaning = {
        "Riesgo de agotamiento": "Puede agotarse",
        "Sobrecobertura": "Hay inventario de más",
        "Concentración en bodega": "La mercancía no está disponible en piso",
        "Catálogo de salida": "Ocupa espacio de venta",
        "Modelo lento": "La salida es muy baja",
        "Transferencia entre tiendas": "Otra tienda necesita la mercancía",
    }
    responsible = {
        "Riesgo de agotamiento": "Comercial",
        "Sobrecobertura": "Comercial",
        "Concentración en bodega": "Operación tienda",
        "Catálogo de salida": "Jefe de piso",
        "Modelo lento": "Comercial",
        "Transferencia entre tiendas": "Comercial / logística",
    }
    out = data.copy()
    out["Cuándo"] = out["Prioridad"].map({"Alta": "Hoy", "Media": "Esta semana", "Baja": "Seguimiento"}).fillna("Seguimiento")
    out["Qué pasa"] = out["Oportunidad"]
    out["Qué significa"] = out["Oportunidad"].map(meaning).fillna("Requiere revisión")
    out["Responsable"] = out["Oportunidad"].map(responsible).fillna("Supervisor")
    out["Piezas"] = pd.to_numeric(out["Piezas"], errors="coerce").fillna(0).round(0)
    return out[["Cuándo", "Tienda", "Elemento", "Qué pasa", "Qué significa", "Recomendación", "Piezas", "Responsable"]]


def _page_summary(bundle: dict) -> None:
    _header("Resumen Operativo", "Una lectura sencilla para dirección, supervisión y tiendas", bundle)
    _top_navigation("Resumen Comercial")
    week, store, _ = _scope(bundle, "pdf_summary")
    stores, breakdowns, _, models = _current(bundle, week, store)
    if stores.empty:
        _no_data(); return
    total = _totals(stores)
    critical = int(((stores["DDI"] > 0) & (stores["DDI"] <= 30)).sum())
    excess = int((stores["DDI"] > 120).sum())
    opportunities = pdf_opportunities(stores, breakdowns, models)
    state = "Crítico" if critical >= 4 else ("Atención" if critical or excess else "Óptimo")
    state_color = RED if state == "Crítico" else (ORANGE if state == "Atención" else GREEN)
    _kpis([
        ("Estado general", state, f"{critical + excess} riesgos requieren acción", state_color),
        ("Inventario", _number(total["Existencia"]), f"Alcanza para {total['DDI']:.0f} días", GREEN),
        ("Venta diaria sugerida", _number(total["VPD"]), "Promedio diario reportado", PINK),
        ("Acciones para hoy", _number((opportunities.get("Prioridad", pd.Series(dtype=str)) == "Alta").sum()), "Resurtir, mover o exhibir", ORANGE),
    ], 4)
    trend = filter_period(bundle["stores_pdf"], store=store)
    trend = trend.groupby("Semana", as_index=False)[["Existencia", "VPD", "Curva"]].sum().sort_values("Semana")
    left, right = st.columns([1.45, 1], gap="medium")
    with left:
        fig = go.Figure()
        fig.add_scatter(x=trend["Semana"], y=trend["VPD"], mode="lines", name="Venta diaria sugerida", line=dict(color=BLUE, width=4))
        fig.add_scatter(x=trend["Semana"], y=trend["Existencia"].div(trend["VPD"].replace(0, np.nan)), mode="lines", name="Días de inventario", yaxis="y2", line=dict(color=PINK, width=4))
        fig.update_layout(title="¿Qué está pasando?", yaxis_title="Venta diaria sugerida", yaxis2=dict(title="Días de inventario", overlaying="y", side="right"))
        _plot(fig, 300)
    with right:
        traffic = pd.DataFrame({
            "Estado": ["Saludable", "Requiere revisión", "Acción inmediata"],
            "Tiendas": [int(((stores["DDI"] >= 31) & (stores["DDI"] <= 90)).sum()), int(((stores["DDI"] > 90) & (stores["DDI"] <= 120)).sum() + excess), critical],
        })
        colors = [GREEN, ORANGE, RED]
        fig = go.Figure(go.Bar(y=traffic["Estado"], x=traffic["Tiendas"], orientation="h", marker_color=colors, text=traffic["Tiendas"], textposition="outside"))
        fig.update_layout(title="Semáforo de la operación", xaxis_title="Tiendas", yaxis_title="", showlegend=False)
        _plot(fig, 300)
    st.markdown('<div class="ac-section">¿Qué debemos hacer?</div>', unsafe_allow_html=True)
    actions = _plain_opportunities(opportunities).head(12)
    _decision_table(actions, status_columns=("Cuándo",), height=350)


def _page_stores(bundle: dict) -> None:
    _header("Tiendas: ¿Dónde actuar?", "Ranking sencillo y una acción clara para cada sucursal", bundle)
    _top_navigation("Tiendas Comerciales")
    week, store, _ = _scope(bundle, "pdf_stores")
    stores = store_pdf_summary(bundle["stores_pdf"], week, store)
    if stores.empty: _no_data(); return
    total = _totals(stores)
    friendly = _friendly_store_table(stores)
    healthy = int(friendly["Estado"].eq("Óptimo").sum())
    attention = int(friendly["Estado"].isin(["Atención", "Exceso"]).sum())
    critical = int(friendly["Estado"].isin(["Crítico", "Sin rotación"]).sum())
    _kpis([
        ("Tiendas saludables", _number(healthy), "Mantener ejecución", GREEN),
        ("En atención", _number(attention), "Revisar esta semana", ORANGE),
        ("Críticas", _number(critical), "Acción inmediata", RED),
        ("Cobertura completa", f'{stores["Tienda"].nunique()} / 17', "PDF reconocidos", BLUE),
    ], 4)
    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        chart = stores.sort_values("Score")
        chart_colors = chart["Estatus"].map({"Óptimo": GREEN, "Atención": ORANGE, "Crítico": RED}).fillna(BLUE)
        fig = go.Figure(go.Bar(y=chart["Tienda"], x=chart["Score"], orientation="h", marker_color=chart_colors, text=chart["Score"].map(_number), textposition="outside"))
        fig.update_layout(title="Ranking operativo de tiendas", xaxis_title="Score", yaxis_title="", showlegend=False)
        _plot(fig, max(390, len(chart) * 31 + 100))
    with right:
        coverage = friendly.sort_values("Días de inventario")
        coverage_colors = coverage["Estado"].map({"Óptimo": GREEN, "Atención": ORANGE, "Exceso": PINK, "Crítico": RED, "Sin rotación": RED}).fillna(BLUE)
        fig = go.Figure(go.Bar(y=coverage["Tienda"], x=coverage["Días de inventario"], orientation="h", marker_color=coverage_colors, text=coverage["Días de inventario"].map(lambda value: f"{value:.0f} días"), textposition="outside"))
        fig.add_vrect(x0=31, x1=90, fillcolor="rgba(7,148,71,.07)", line_width=0)
        fig.update_layout(title="Días que durará el inventario", xaxis_title="Días", yaxis_title="", showlegend=False)
        _plot(fig, max(390, len(coverage) * 31 + 100))
    st.markdown('<div class="ac-section">Detalle por tienda</div>', unsafe_allow_html=True)
    columns = ["Tienda", "Estado", "Existencia", "Venta diaria sugerida", "Días de inventario", "Bodega %", "Qué significa", "Qué hacer"]
    _decision_table(friendly[columns], status_columns=("Estado", "Qué hacer"), height=440)


def _page_inventory(bundle: dict) -> None:
    _header("Inventario: Qué mover y qué resurtir", "Cobertura explicada en días y acciones concretas", bundle)
    _top_navigation("Inventario y Cobertura")
    week, store, _ = _scope(bundle, "pdf_inventory")
    stores, breakdowns, _, models = _current(bundle, week, store)
    if stores.empty: _no_data(); return
    total = _totals(stores)
    critical = stores[(stores["DDI"] > 0) & (stores["DDI"] <= 30)]
    excess = stores[stores["DDI"] > 120]
    exit_rows = breakdowns[breakdowns["Tipo"].eq("catalog") & breakdowns["Etiqueta"].astype(str).str.upper().str.contains("DESCONT|PROXIMO")]
    _kpis([
        ("Inventario total", _number(total["Existencia"]), "Piso + bodega", BLUE),
        ("Duración estimada", f'{total["DDI"]:,.0f} días', "Rango sano: 31 a 90", GREEN),
        ("Tiendas por resurtir", _number(len(critical)), "Hasta 30 días", RED),
        ("Tiendas por transferir", _number(len(excess)), "Más de 120 días", PURPLE),
    ], 4)
    st.info("Días de inventario = tiempo aproximado que durará la mercancía al ritmo actual. Menos de 30 días indica riesgo; más de 120 días indica exceso.", icon=":material/info:")
    labels = ["0-14", "15-30", "31-60", "61-90", "91-120", "120+"]
    bucket = pd.cut(stores["DDI"], [-.1, 14, 30, 60, 90, 120, np.inf], labels=labels)
    distribution = stores.assign(Cobertura=bucket).groupby("Cobertura", observed=False, as_index=False)["Existencia"].sum()
    left, right = st.columns([1.15, 1], gap="medium")
    with left:
        fig = go.Figure()
        colors = [RED, ORANGE, GREEN, GREEN, BLUE, PINK]
        for idx, row in distribution.iterrows():
            fig.add_bar(y=["Inventario"], x=[row["Existencia"]], name=str(row["Cobertura"]), orientation="h", marker_color=colors[idx], text=[_number(row["Existencia"])], textposition="inside")
        fig.update_layout(title="¿Cómo está distribuido el inventario?", barmode="stack", xaxis_title="Piezas")
        _plot(fig, 370)
    with right:
        coverage = _friendly_store_table(stores).sort_values("Días de inventario")
        bar_colors = coverage["Estado"].map({"Óptimo": GREEN, "Atención": ORANGE, "Exceso": PINK, "Crítico": RED, "Sin rotación": RED}).fillna(BLUE)
        fig = go.Figure(go.Bar(y=coverage["Tienda"], x=coverage["Días de inventario"], orientation="h", marker_color=bar_colors, text=coverage["Qué hacer"], textposition="outside"))
        fig.update_layout(title="Tiendas que requieren movimiento", xaxis_title="Días de inventario", yaxis_title="")
        _plot(fig, 370)
    if not models.empty:
        featured = models.sort_values(["Tienda", "ID_ART", "Ranking"]).drop_duplicates(["Tienda", "ID_ART"])
        risk = featured[(featured["VPD"].gt(0)) & ((featured["DDI"].le(30)) | (featured["DDI"].gt(120)))].sort_values("DDI")
        risk = risk.copy()
        risk["Estado"] = risk["DDI"].map(_coverage_status)
        risk["Qué significa"] = risk["DDI"].map(_coverage_meaning)
        risk["Qué hacer"] = risk["DDI"].map(_coverage_action)
        risk = risk.rename(columns={"VPD": "Venta diaria sugerida", "DDI": "Días de inventario"})
        st.markdown('<div class="ac-section">Plan de inventario</div>', unsafe_allow_html=True)
        st.caption("El detalle corresponde a los modelos publicados en los Top 40 del PDF.")
        columns = ["Estado", "Tienda", "ID_ART", "Modelo", "Marca", "Existencia", "Venta diaria sugerida", "Días de inventario", "Qué significa", "Qué hacer"]
        _decision_table(risk[columns].head(40), status_columns=("Estado", "Qué hacer"), height=420)


def _normalize_section(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    label = out.get("Etiqueta", pd.Series(dtype=str)).astype(str)
    current = out.get("Sección", pd.Series("", index=out.index)).astype(str)
    inferred = np.select(
        [label.str.upper().str.contains("DAMA"), label.str.upper().str.contains("CABALL"), label.str.upper().str.contains("INFANT|NIÑ|BEB")],
        ["Dama", "Caballero", "Infantil"], default=label,
    )
    out["Grupo"] = current.where(current.ne(""), inferred)
    return out


def _page_sections(bundle: dict) -> None:
    _header("Secciones: Dónde dar más espacio", "Participación y decisión de espacio en lenguaje sencillo", bundle)
    _top_navigation("Secciones y Categorías")
    week, store, _ = _scope(bundle, "pdf_sections")
    data = filter_period(bundle["breakdowns"], week, store)
    if data.empty: _no_data(); return
    labels = {"section": "Sección", "category": "Categoría", "rubro": "Rubro", "catalog": "Catálogo", "status": "Estatus", "product_type": "Tipo de producto"}
    selected_label = st.segmented_control("Nivel de análisis", list(labels.values()), default="Sección", key="pdf_sections_type")
    kind = next(key for key, value in labels.items() if value == selected_label)
    detail = _normalize_section(data[data["Tipo"].eq(kind)])
    if detail.empty:
        st.info(f"El PDF seleccionado no contiene desglose de {selected_label.lower()}."); return
    group_col = "Grupo" if kind in ("section", "rubro") else "Etiqueta"
    summary = aggregate_pdf(detail, group_col).sort_values("Existencia", ascending=False)
    total = summary.sum(numeric_only=True)
    _kpis([
        (selected_label, _number(summary[group_col].nunique()), "Elementos analizados", BLUE),
        ("Inventario", _number(total.get("Existencia", 0)), "Piezas reportadas", PURPLE),
        ("Venta diaria sugerida", _number(total.get("VPD", 0)), "Promedio diario", CYAN),
        ("Posiciones", _number(total.get("Posiciones", 0)), "Espacio reportado", GREEN),
    ], 4)
    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        chart = summary.head(20).sort_values("Existencia")
        fig = px.bar(chart, y=group_col, x="Existencia", orientation="h", text=chart["Existencia"].map(_number), color_discrete_sequence=[BLUE])
        fig.update_layout(title=f"Participación por {selected_label.lower()}", xaxis_title="Inventario", yaxis_title="")
        _plot(fig, max(380, len(chart) * 25 + 110))
    with right:
        productivity = summary.head(20).sort_values("VPD/posición")
        productivity["Decisión"] = np.select(
            [productivity["VPD/posición"].ge(productivity["VPD/posición"].quantile(.66)), productivity["VPD/posición"].le(productivity["VPD/posición"].quantile(.33))],
            ["Impulsar", "Reducir"], default="Mantener",
        )
        bar_colors = productivity["Decisión"].map({"Impulsar": BLUE, "Mantener": GREEN, "Reducir": PINK})
        fig = go.Figure(go.Bar(y=productivity[group_col], x=productivity["VPD/posición"], orientation="h", marker_color=bar_colors, text=productivity["Decisión"], textposition="outside"))
        fig.update_layout(title="¿Qué merece más o menos espacio?", xaxis_title="Venta diaria por posición", yaxis_title="")
        _plot(fig, 430)
    summary = summary.copy()
    summary["Decisión"] = np.select(
        [summary["VPD/posición"].ge(summary["VPD/posición"].quantile(.66)), summary["VPD/posición"].le(summary["VPD/posición"].quantile(.33))],
        ["Impulsar", "Reducir"], default="Mantener",
    )
    summary["Qué significa"] = summary["Decisión"].map({"Impulsar": "Alta productividad", "Mantener": "Espacio equilibrado", "Reducir": "Baja productividad"})
    summary = summary.rename(columns={"VPD": "Venta diaria sugerida", "DDI": "Días de inventario"})
    columns = [group_col, "Existencia", "Venta diaria sugerida", "Días de inventario", "Posiciones", "VPD/posición", "Qué significa", "Decisión"]
    _decision_table(summary[columns], status_columns=("Decisión",), height=430)


def _page_locations(bundle: dict) -> None:
    _header("Ubicaciones: Qué espacio funciona mejor", "Comparación clara para decidir qué ampliar, mantener o reducir", bundle)
    _top_navigation("Ubicaciones y Espacio")
    week, store, _ = _scope(bundle, "pdf_locations")
    summary = business_location_summary(bundle["breakdowns"], week, store)
    if summary.empty: _no_data(); return
    summary = summary.copy()
    q_high = summary["VPD/posición"].quantile(.66)
    q_low = summary["VPD/posición"].quantile(.33)
    summary["Qué hacer"] = np.select([summary["VPD/posición"].ge(q_high), summary["VPD/posición"].le(q_low)], ["Ampliar", "Reducir"], default="Mantener")
    summary["Lectura"] = summary["Qué hacer"].map({"Ampliar": "Alta productividad", "Mantener": "Espacio equilibrado", "Reducir": "Baja productividad"})
    colors = {"Doblado": BLUE, "Colgado": GREEN, "Jeans": PINK, "Lencería": PURPLE}
    _kpis([(row["Ubicación"], row["Qué hacer"], f"{row.get('VPD/posición', 0):.2f} salida por posición", colors.get(row["Ubicación"], BLUE)) for _, row in summary.iterrows()], 4)
    st.caption("Lencería se identifica por rubro en el PDF; no debe sumarse a las ubicaciones físicas como si fuera un grupo excluyente.")
    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        chart = summary.sort_values("VPD/posición")
        chart_colors = chart["Qué hacer"].map({"Ampliar": BLUE, "Mantener": GREEN, "Reducir": PINK})
        fig = go.Figure(go.Bar(y=chart["Ubicación"], x=chart["VPD/posición"], orientation="h", marker_color=chart_colors, text=chart["Qué hacer"], textposition="outside"))
        fig.update_layout(title="Productividad del espacio", xaxis_title="Venta diaria por posición", yaxis_title="")
        _plot(fig, 390)
    with right:
        chart = summary.sort_values("DDI")
        fig = go.Figure(go.Bar(y=chart["Ubicación"], x=chart["DDI"], orientation="h", marker_color=[colors.get(value, BLUE) for value in chart["Ubicación"]], text=chart["DDI"].map(lambda value: f"{value:.0f} días"), textposition="outside"))
        fig.add_vrect(x0=31, x1=90, fillcolor="rgba(7,148,71,.07)", line_width=0)
        fig.update_layout(title="Días que durará el inventario", xaxis_title="Días", yaxis_title="")
        _plot(fig, 390)
    display = summary.rename(columns={"VPD": "Venta diaria sugerida", "DDI": "Días de inventario"})
    columns = ["Ubicación", "Existencia", "Venta diaria sugerida", "Días de inventario", "Posiciones", "VPD/posición", "Lectura", "Qué hacer"]
    _decision_table(display[columns], status_columns=("Qué hacer",), height=300)


def _page_brands(bundle: dict) -> None:
    _header("Marcas: Cuáles impulsar y cuáles revisar", "Un ranking fácil de explicar a cualquier nivel", bundle)
    _top_navigation("Marcas y Catálogo")
    week, store, _ = _scope(bundle, "pdf_brands")
    brands = filter_period(bundle["brands"], week, store)
    if brands.empty: _no_data(); return
    scopes = sorted(brands["Alcance marca"].dropna().astype(str).unique())
    scope = st.segmented_control("Alcance de marca", scopes, default=scopes[0], key="pdf_brands_brand_scope")
    brands = brands[brands["Alcance marca"].eq(scope)].copy()
    brands["Score operativo"] = (
        brands["% Utilidad"].rank(pct=True).mul(45)
        + brands["VPD"].rank(pct=True).mul(35)
        + brands["DDI"].map(lambda value: 20 if 31 <= value <= 90 else (10 if 15 <= value <= 120 else 0))
    ).round(0)
    brands["Decisión"] = np.select([brands["Score operativo"].ge(75), brands["Score operativo"].le(45)], ["Impulsar", "Reducir"], default="Mantener")
    top = brands.sort_values("Score operativo", ascending=False).head(20)
    utility_top = brands.sort_values("% Utilidad", ascending=False).iloc[0]
    _kpis([
        ("Marcas para impulsar", _number(brands["Decisión"].eq("Impulsar").sum()), "Alta utilidad y salida", BLUE),
        ("Marcas estables", _number(brands["Decisión"].eq("Mantener").sum()), "Conservar espacio", GREEN),
        ("Marcas por revisar", _number(brands["Decisión"].eq("Reducir").sum()), "Inventario lento", PINK),
        ("Marca líder", utility_top["Marca"], _percent(utility_top["% Utilidad"]), ORANGE),
    ], 4)
    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        chart = top.sort_values("Score operativo")
        bar_colors = chart["Decisión"].map({"Impulsar": BLUE, "Mantener": GREEN, "Reducir": PINK})
        fig = go.Figure(go.Bar(y=chart["Marca"], x=chart["Score operativo"], orientation="h", marker_color=bar_colors, text=chart["Decisión"], textposition="outside"))
        fig.update_layout(title="Ranking de marcas", xaxis_title="Score operativo", yaxis_title="")
        _plot(fig, 510)
    with right:
        mix = brands.groupby("Decisión", as_index=False).size()
        order = [value for value in ["Impulsar", "Mantener", "Reducir"] if value in set(mix["Decisión"])]
        fig = go.Figure()
        for decision in order:
            value = int(mix.loc[mix["Decisión"].eq(decision), "size"].sum())
            fig.add_bar(y=["Portafolio"], x=[value], name=decision, orientation="h", marker_color={"Impulsar": BLUE, "Mantener": GREEN, "Reducir": PINK}[decision], text=[value], textposition="inside")
        fig.update_layout(title="Lectura del portafolio", barmode="stack", xaxis_title="Marcas")
        _plot(fig, 430)
    st.caption("% Utilidad es el porcentaje publicado en el reporte; no representa utilidad monetaria total.")
    brands["Qué significa"] = brands["Decisión"].map({"Impulsar": "Líder de portafolio", "Mantener": "Desempeño estable", "Reducir": "Inventario lento"})
    display = brands.rename(columns={"VPD": "Venta diaria sugerida", "DDI": "Días de inventario"})
    columns = ["Marca", "% Utilidad", "Venta diaria sugerida", "Días de inventario", "Existencia", "Score operativo", "Qué significa", "Decisión"]
    _decision_table(display[columns].sort_values("Score operativo", ascending=False), status_columns=("Decisión",), height=430)


def _page_models(bundle: dict) -> None:
    _header("Modelos: Cuáles mover, impulsar o detener", "Campeones y lentos separados para actuar rápido", bundle)
    _top_navigation("Modelos")
    week, store, scenario = _scope(bundle, "pdf_models", scenario=True)
    models = filter_period(bundle["models_pdf"], week, store)
    models = models[models["Escenario"].eq(scenario)].copy()
    if models.empty: _no_data(); return
    sections = ["Todas"] + sorted(models["Sección"].dropna().astype(str).unique())
    selected_section = st.segmented_control("Sección", sections, default="Todas", key="pdf_models_section")
    if selected_section != "Todas": models = models[models["Sección"].eq(selected_section)]
    top = models.sort_values(["Ranking", "Tienda"]).head(40)
    total = top.sum(numeric_only=True)
    champions = top[(top["VPD"].gt(0)) & (top["DDI"].between(31, 90))].sort_values("VPD", ascending=False)
    slow = top[(top["DDI"].gt(120)) | (top["VPD"].le(0))].sort_values(["DDI", "Existencia"], ascending=False)
    risk = top[(top["VPD"].gt(0)) & (top["DDI"].le(30))].sort_values("DDI")
    _kpis([
        ("Campeones", _number(champions["ID_ART"].nunique()), "Impulsar", BLUE),
        ("Lentos", _number(slow["ID_ART"].nunique()), "Reducir o transferir", PINK),
        ("Por agotarse", _number(risk["ID_ART"].nunique()), "Resurtir", RED),
        ("Modelos analizados", _number(models["ID_ART"].nunique()), scenario, GREEN),
    ], 4)
    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        chart = (champions if not champions.empty else top.nlargest(15, "VPD")).head(15).sort_values("VPD")
        labels = chart["Modelo"].where(chart["Modelo"].astype(str).ne(""), chart["ID_ART"].astype(str))
        fig = go.Figure(go.Bar(y=labels, x=chart["VPD"], orientation="h", marker_color=BLUE, text=chart["VPD"].map(lambda value: f"{value:.0f}/día"), textposition="outside"))
        fig.update_layout(title="Modelos campeones", xaxis_title="Venta diaria sugerida", yaxis_title="")
        _plot(fig, 520)
    with right:
        chart = (slow if not slow.empty else top.nlargest(15, "DDI")).head(15).sort_values("DDI")
        labels = chart["Modelo"].where(chart["Modelo"].astype(str).ne(""), chart["ID_ART"].astype(str))
        fig = go.Figure(go.Bar(y=labels, x=chart["DDI"], orientation="h", marker_color=PINK, text=chart["DDI"].map(lambda value: f"{value:.0f} días"), textposition="outside"))
        fig.update_layout(title="Modelos lentos", xaxis_title="Días de inventario", yaxis_title="")
        _plot(fig, 520)
    st.caption("Los modelos mostrados corresponden a los Top 40 impresos en el PDF por sección y escenario.")
    top = top.copy()
    top["Estado"] = top["DDI"].map(_coverage_status)
    top["Qué significa"] = top["DDI"].map(_coverage_meaning)
    top["Qué hacer"] = top["DDI"].map(_coverage_action)
    display = top.rename(columns={"VPD": "Venta diaria sugerida", "DDI": "Días de inventario"})
    columns = ["Estado", "Tienda", "ID_ART", "Modelo", "Marca", "Sección", "Existencia", "Venta diaria sugerida", "Días de inventario", "Qué significa", "Qué hacer"]
    _decision_table(display[columns], status_columns=("Estado", "Qué hacer"), height=530)


def _page_opportunities(bundle: dict) -> None:
    _header("Plan de Acción Semanal", "Una lista operativa con responsable, prioridad y seguimiento", bundle)
    _top_navigation("Oportunidades y Acciones")
    week, store, _ = _scope(bundle, "pdf_opportunities")
    stores, breakdowns, _, models = _current(bundle, week, store)
    data = pdf_opportunities(stores, breakdowns, models)
    if data.empty:
        st.success("No se detectaron oportunidades con los criterios actuales."); return
    plain = _plain_opportunities(data)
    _kpis([
        ("Para hoy", _number(plain["Cuándo"].eq("Hoy").sum()), "Acciones críticas", RED),
        ("Esta semana", _number(plain["Cuándo"].eq("Esta semana").sum()), "Acciones programadas", ORANGE),
        ("En seguimiento", _number(plain["Cuándo"].eq("Seguimiento").sum()), "Validar avance", GREEN),
        ("Piezas sugeridas", _number(plain["Piezas"].sum()), "Mover o resurtir", BLUE),
    ], 4)
    timing = st.segmented_control("Mostrar", ["Todas", "Hoy", "Esta semana", "Seguimiento"], default="Todas", key="pdf_actions_timing")
    display = plain if timing == "Todas" else plain[plain["Cuándo"].eq(timing)]
    _decision_table(display, status_columns=("Cuándo",), height=560)
    st.caption("Las piezas sugeridas son una recomendación operativa basada en VPD y cobertura; no se calcula impacto monetario sin el archivo de ventas.")


def _page_history(bundle: dict) -> None:
    _header("Histórico: Qué mejoró y qué empeoró", "Comparaciones simples para aprender de cada semana", bundle)
    _top_navigation("Histórico Comercial")
    history = bundle["stores_pdf"].copy()
    if history.empty: _no_data(); return
    week = _latest_week(history["Semana"])
    current = history[history["Semana"].eq(week)]
    total = _totals(current)
    trend = history.groupby("Semana", as_index=False)[["Existencia", "VPD", "Curva"]].sum().sort_values("Semana")
    previous = trend.iloc[-2] if len(trend) > 1 else trend.iloc[-1]
    current_trend = trend.iloc[-1]
    vpd_change = (current_trend["VPD"] / previous["VPD"] - 1) * 100 if previous["VPD"] else 0
    inv_change = (current_trend["Existencia"] / previous["Existencia"] - 1) * 100 if previous["Existencia"] else 0
    _kpis([
        ("Venta diaria sugerida", f"{vpd_change:+.1f}%", "Vs. semana anterior", BLUE),
        ("Inventario total", f"{inv_change:+.1f}%", "Vs. semana anterior", GREEN),
        ("Tiendas críticas", _number(((current["DDI"] > 0) & (current["DDI"] <= 30)).sum()), "Requieren acción", RED),
        ("Calidad histórica", _percent(current["Tienda"].nunique() / 17 * 100), "Cobertura de PDF", ORANGE),
    ], 4)
    pivot = history.assign(Disponible="✓").pivot_table(index="Tienda", columns="Semana", values="Disponible", aggfunc="first", fill_value="—")
    left, right = st.columns([1.2, 1], gap="medium")
    with left:
        st.markdown('<div class="ac-section">Cobertura de PDF por tienda</div>', unsafe_allow_html=True)
        st.dataframe(pivot, width="stretch", height=390)
    with right:
        fig = go.Figure()
        fig.add_scatter(x=trend["Semana"], y=trend["VPD"], mode="lines", name="Venta diaria sugerida", line=dict(color=BLUE, width=4))
        fig.add_scatter(x=trend["Semana"], y=trend["Existencia"].div(trend["VPD"].replace(0, np.nan)), mode="lines", name="Días de inventario", yaxis="y2", line=dict(color=PINK, width=4))
        fig.update_layout(title="Evolución semanal", yaxis_title="Venta diaria sugerida", yaxis2=dict(title="Días de inventario", overlaying="y", side="right"))
        _plot(fig, 390)
    st.markdown('<div class="ac-section">Historial de cortes</div>', unsafe_allow_html=True)
    display = _friendly_store_table(history.sort_values(["Semana", "Tienda"], ascending=[False, True]))
    columns = ["Semana", "Tienda", "Estado", "Existencia", "Venta diaria sugerida", "Días de inventario", "Qué significa", "Qué hacer"]
    _decision_table(display[columns], status_columns=("Estado", "Qué hacer"), height=430)


def _page_upload(bundle: dict, is_admin: bool) -> None:
    _header("Carga Semanal de PDF", "Tres pasos claros para publicar información confiable", bundle)
    if not is_admin:
        st.error("Esta pestaña está disponible únicamente para Administrador o Propietario."); return
    flash = st.session_state.pop("commercial_upload_flash", None)
    if flash:
        getattr(st, flash[0])(flash[1])
    st.markdown(
        '<div class="ac-source-note"><b>1. Selecciona la semana</b> &nbsp;→&nbsp; '
        '<b>2. Carga los 17 PDF</b> &nbsp;→&nbsp; <b>3. Revisa y publica</b><br>'
        'El sistema utiliza únicamente los PDF semanales y conserva cada corte para el histórico.</div>',
        unsafe_allow_html=True,
    )
    bootstrap = st.session_state.get("commercial_cloud_bootstrap", {})
    if bootstrap.get("error"):
        st.error(f"El almacenamiento privado no respondió: {bootstrap['error']}")
    elif cloud_enabled():
        st.success("Histórico protegido en el almacenamiento privado configurado.", icon=":material/cloud_done:")
    else:
        st.warning("Almacenamiento temporal: configura el respaldo privado antes de cargar los 17 PDF.", icon=":material/cloud_off:")
    left, right = st.columns([.7, 1.3], gap="large")
    with left:
        report_date = st.date_input("Fecha del corte", value=date.today(), key="commercial_pdf_date")
        iso = report_date.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"
        st.metric("Semana que se publicará", week_key)
        st.caption("El sistema también valida la fecha impresa dentro de cada PDF.")
    with right:
        uploads = st.file_uploader("Carga hasta 17 PDF de tiendas", type=["pdf"], accept_multiple_files=True, key="commercial_pdf_uploads")
        if uploads and len(uploads) > 17:
            st.error("Selecciona un máximo de 17 PDF por corte.")
        if st.button("Validar y publicar corte", disabled=not uploads or len(uploads) > 17, type="primary", width="stretch"):
            entries = []
            for uploaded in uploads:
                entry = save_pdf_upload(uploaded, week_key)
                entries.append((entry, resolve_entry_path(entry)))
            progress = st.progress(0, text="Extrayendo información estructurada...")
            completed, errors = 0, []
            with ThreadPoolExecutor(max_workers=min(4, len(entries))) as executor:
                futures = {executor.submit(extract_pdf_snapshot, path): (entry, path) for entry, path in entries}
                for future in as_completed(futures):
                    entry, _ = futures[future]
                    try:
                        snapshot = future.result()
                        save_snapshot(entry["id"], snapshot)
                        update_entry("pdfs", entry["id"], status=snapshot["status"], store=snapshot["store"], week=snapshot["week"] or week_key, report_date=snapshot["report_date"], pages=snapshot["pages"], records=snapshot["models"])
                    except Exception as exc:
                        errors.append(f"{entry.get('name')}: {exc}")
                        update_entry("pdfs", entry["id"], status="Error", error=str(exc)[:300])
                    completed += 1
                    progress.progress(completed / len(entries), text=f"Procesados {completed} de {len(entries)} PDF")
            sync = sync_history_to_cloud([path for _, path in entries])
            st.cache_data.clear()
            message = f"{completed - len(errors)} PDF procesados; el histórico anterior se conservó."
            if errors:
                level, message = "error", f"{message} {len(errors)} archivo(s) presentaron error."
            elif sync.get("error"):
                level, message = "error", f"{message} No se pudo sincronizar: {sync['error']}"
            elif not sync.get("configured"):
                level, message = "warning", f"{message} Aún están sólo en el servidor temporal."
            else:
                level, message = "success", f"{message} Respaldo privado actualizado."
            st.session_state["commercial_upload_flash"] = (level, message)
            st.rerun()
    manifest = load_manifest()
    pdfs = pd.DataFrame(manifest.get("pdfs", []))
    current_week = _latest_week(pdfs.get("week", pd.Series(dtype=str))) if not pdfs.empty else "Sin semana"
    current = pdfs[pdfs["week"].eq(current_week)] if not pdfs.empty and "week" in pdfs else pd.DataFrame()
    stores = set(current.get("store", pd.Series(dtype=str)).replace("", np.nan).dropna().astype(str))
    missing = sorted(set(PROJECT_STORES) - stores)
    records = pd.to_numeric(current.get("records", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    errors = int((pdfs.get("status", pd.Series(dtype=str)) == "Error").sum())
    publication_state = "Listo" if len(stores) == 17 and not errors else ("Revisar" if current_week != "Sin semana" else "Sin corte")
    _kpis([
        ("Archivos recibidos", f"{len(current)} / 17", current_week, GREEN),
        ("Tiendas reconocidas", f"{len(stores)} / 17", "Identificación automática", BLUE),
        ("Errores", _number(errors), "Deben quedar en cero", RED),
        ("Estado del corte", publication_state, ", ".join(missing[:2]) if missing else "Información completa", ORANGE if missing or errors else GREEN),
    ], 4)
    if not current.empty:
        columns = [column for column in ("store", "name", "week", "report_date", "records", "pages", "status", "uploaded_at") if column in current]
        st.markdown('<div class="ac-section">Validación del último corte</div>', unsafe_allow_html=True)
        display = current[columns].sort_values(["store", "name"]).rename(columns={
            "store": "Tienda", "name": "Archivo", "week": "Semana", "report_date": "Fecha",
            "records": "Modelos", "pages": "Páginas", "status": "Resultado", "uploaded_at": "Cargado",
        })
        _decision_table(display, status_columns=("Resultado",), height=410)
    st.divider()
    left, right = st.columns(2)
    with left:
        backup = build_history_backup()
        st.download_button("Descargar respaldo histórico", backup, file_name=f"Respaldo_PDF_Comercial_{datetime.now().strftime('%Y%m%d')}.zip", mime="application/zip", width="stretch")
        st.caption("Incluye PDF, manifiesto y datos normalizados para restaurar el histórico.")
    with right:
        restore = st.file_uploader("Restaurar respaldo PDF", type=["zip"], key="commercial_restore_backup")
        if st.button("Restaurar respaldo", disabled=restore is None, width="stretch"):
            count = restore_history_backup(restore)
            st.cache_data.clear()
            st.success(f"Se restauraron {count} archivos sin borrar los existentes.")
            st.rerun()


def render_pdf_page(page: str, bundle: dict, is_admin: bool) -> None:
    routes = {
        "Resumen Comercial": _page_summary,
        "Tiendas Comerciales": _page_stores,
        "Inventario y Cobertura": _page_inventory,
        "Secciones y Categorías": _page_sections,
        "Ubicaciones y Espacio": _page_locations,
        "Marcas y Catálogo": _page_brands,
        "Modelos": _page_models,
        "Oportunidades y Acciones": _page_opportunities,
        "Histórico Comercial": _page_history,
    }
    if page == ADMIN_PAGE:
        _page_upload(bundle, is_admin)
    elif page in routes:
        routes[page](bundle)
    else:
        st.error(f"La página comercial '{page}' no está registrada.")
