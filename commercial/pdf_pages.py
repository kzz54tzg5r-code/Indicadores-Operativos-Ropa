"""Páginas del análisis comercial alimentadas únicamente por PDF AC."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import html
import re

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from .config import ADMIN_PAGE, COMMERCIAL_PAGES, MORE_PAGE, PAGE_LABELS, PROJECT_STORES
from .parsers import PDF_PARSER_VERSION, extract_pdf_snapshot
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
    load_snapshots,
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
    fig.update_xaxes(fixedrange=True); fig.update_yaxes(fixedrange=True)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "responsive": True, "scrollZoom": False, "doubleClick": False})


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
    with st.container(border=True, key=f"commercial_report_filters_{prefix}"):
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
    return out.rename(columns={"VPD": "Sugerido", "DDI": "Días de inventario"})


def _table_style(frame: pd.DataFrame, status_columns=()):
    colors = {
        "Óptimo": "#DDF7E8", "Bien": "#DDF7E8", "Mantener": "#DDF7E8", "Seguimiento": "#DDF7E8",
        "Procesado": "#DDF7E8", "Incrementar": "#E8F2FF",
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

    # Formato comercial único para todas las tablas: piezas sin decimales,
    # porcentajes con símbolo % e importes monetarios con $.
    # El formato es sólo visual; los cálculos conservan sus valores numéricos.
    formatters = {}
    for column in frame.columns:
        if not pd.api.types.is_numeric_dtype(frame[column]):
            continue
        name = str(column).strip().lower()
        if "%" in str(column) or "porcentaje" in name:
            formatters[column] = lambda value: "" if pd.isna(value) else f"{float(value):,.1f}%"
        elif any(token in name for token in ("inversión", "inversion", "venta $", "ventas $", "importe", "costo", "monto", "pesos", "$")):
            formatters[column] = lambda value: "" if pd.isna(value) else f"${float(value):,.0f}"
        else:
            formatters[column] = lambda value: "" if pd.isna(value) else f"{float(value):,.0f}"
    if formatters:
        styler = styler.format(formatters)
    for column in status_columns:
        if column in frame:
            styler = styler.map(paint, subset=[column])
    return styler


def _decision_table(frame: pd.DataFrame, *, status_columns=(), height=360) -> None:
    """Tabla corporativa en escritorio y tarjetas de decisión en móvil."""
    if frame is None or frame.empty:
        st.info("No hay registros para el alcance seleccionado.")
        return

    display = frame.copy().rename(columns={
        "Sug": "Sugerido",
        "Sug 7": "Sugerido",
        "VPD": "Sugerido",
        "Venta diaria sugerida": "Sugerido",
        "Sugerido / VPD": "Sugerido",
    })

    def fmt_value(column, value):
        if pd.isna(value):
            return ""
        name = str(column).strip().lower()
        if isinstance(value, (int, float, np.integer, np.floating)):
            number = float(value)
            if "%" in str(column) or "porcentaje" in name:
                return f"{number:,.1f}%"
            if any(token in name for token in ("inversión", "inversion", "venta $", "ventas $", "importe", "costo", "monto", "pesos", "$")):
                return f"${number:,.0f}"
            return f"{number:,.0f}"
        return str(value)

    def status_style(text):
        text = str(text).lower()
        if any(word in text for word in ("óptimo", "impulsar", "saludable", "bien")):
            return "background:#DCFCE7;color:#14532D;font-weight:800;"
        if any(word in text for word in ("atención", "mantener", "revisar", "media")):
            return "background:#FEF3C7;color:#92400E;font-weight:800;"
        if any(word in text for word in ("crítico", "reducir", "riesgo", "alta")):
            return "background:#FEE2E2;color:#991B1B;font-weight:800;"
        return ""

    headers = "".join(f"<th>{html.escape(str(c))}</th>" for c in display.columns)
    body = []
    status_set = set(status_columns or ())
    mobile_cards = []
    title_candidates = (
        "Modelo", "Tienda", "Ubicación", "Rubro", "Sección", "Categoría",
        "Elemento", "Línea", "Semana", "ID_ART",
    )
    metric_priority = (
        "Sugerido",
        "Existencia", "Piso", "Bodega", "DDI", "Días de inventario",
        "Días inventario", "Ocupación", "Capacidad", "Curva", "Inversión",
        "Inversión $", "% Utilidad", "% Part. utilidad", "Estado", "Acción",
    )
    title_column = next((column for column in title_candidates if column in display.columns), display.columns[0])
    subtitle_columns = [
        column for column in ("ID_ART", "Marca", "Sección", "Rubro", "Categoría", "Línea")
        if column in display.columns and column != title_column
    ][:2]
    metric_columns = [
        column for column in metric_priority
        if column in display.columns and column != title_column and column not in subtitle_columns
    ]
    for column in display.columns:
        if column not in metric_columns and column != title_column and column not in subtitle_columns and column != "#":
            metric_columns.append(column)
    metric_columns = metric_columns[:8]

    for _, row in display.iterrows():
        cells = []
        for col in display.columns:
            text = fmt_value(col, row[col])
            style = status_style(text) if col in status_set else ""
            cells.append(f'<td style="{style}">{html.escape(text)}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")

        title = fmt_value(title_column, row[title_column]) or "Detalle"
        subtitle = " · ".join(
            f"{column}: {fmt_value(column, row[column])}"
            for column in subtitle_columns if fmt_value(column, row[column])
        )
        badge_column = next(
            (column for column in (status_columns or ()) if column in display.columns and fmt_value(column, row[column])),
            None,
        )
        badge = ""
        if badge_column:
            badge_text = fmt_value(badge_column, row[badge_column])
            badge = f'<span class="ac-mobile-badge" style="{status_style(badge_text)}">{html.escape(badge_text)}</span>'
        rank = fmt_value("#", row["#"]) if "#" in display.columns else ""
        rank_html = f'<span class="ac-mobile-rank">#{html.escape(rank)}</span>' if rank else ""
        metrics = []
        for column in metric_columns:
            if column == badge_column:
                continue
            value = fmt_value(column, row[column])
            if not value:
                continue
            metrics.append(
                f'<div class="ac-mobile-field"><span>{html.escape(str(column))}</span>'
                f'<strong>{html.escape(value)}</strong></div>'
            )
        subtitle_html = f'<small>{html.escape(subtitle)}</small>' if subtitle else ""
        mobile_cards.append(
            '<article class="ac-mobile-card"><div class="ac-mobile-card-head"><div>'
            f'{rank_html}<strong class="ac-mobile-card-title">{html.escape(title)}</strong>{subtitle_html}'
            f'</div>{badge}</div><div class="ac-mobile-card-grid">{"".join(metrics)}</div></article>'
        )

    table_html = (
        f'<div class="ac-table-scroll" style="max-height:{int(height)}px">'
        f'<table class="ac-decision-table"><thead><tr>{headers}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
        f'<div class="ac-mobile-cards">{"".join(mobile_cards)}</div>'
    )
    st.markdown("".join(table_html), unsafe_allow_html=True)

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
        ("Sugerido", _number(total.get("VPD", 0)), "Promedio diario", CYAN),
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
        fig.update_layout(title="Modelos campeones", xaxis_title="Sugerido", yaxis_title="")
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
    display = top.rename(columns={"VPD": "Sugerido", "DDI": "Días de inventario"})
    columns = ["Estado", "Tienda", "ID_ART", "Modelo", "Marca", "Sección", "Existencia", "Sugerido", "Días de inventario", "Qué significa", "Qué hacer"]
    _decision_table(display[columns], status_columns=("Estado", "Qué hacer"), height=530)


def _section_values(frame: pd.DataFrame) -> pd.Series:
    """Normaliza la sección sin inventar categorías que no están en el PDF."""
    if frame is None or frame.empty:
        return pd.Series(dtype=str)
    raw = frame.get("Sección", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip()
    fallback = frame.get("Etiqueta", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip()
    source = raw.where(raw.ne(""), fallback)
    upper = source.str.upper()
    normalized = np.select(
        [upper.str.contains("DAMA|MUJER", regex=True), upper.str.contains("CABALL|HOMBRE", regex=True), upper.str.contains("INFANT|NIÑ|BEB", regex=True)],
        ["Dama", "Caballero", "Infantil"],
        default="Sin categoría",
    )
    return pd.Series(normalized, index=frame.index).replace({"": "Sin categoría"})


def _valid_options(key: str, options: list[str]) -> None:
    if st.session_state.get(key) not in options:
        st.session_state.pop(key, None)


def _clear_global_scope() -> None:
    for key in ("commercial_period", "commercial_store", "commercial_category", "commercial_line", "commercial_model"):
        st.session_state.pop(key, None)


def _global_scope(bundle: dict) -> dict:
    """Barra única de filtros que conserva el contexto entre módulos."""
    weeks = _weeks(bundle)
    stores = sorted(bundle["stores_pdf"].get("Tienda", pd.Series(dtype=str)).dropna().astype(str).unique())
    _valid_options("commercial_period", weeks)
    _valid_options("commercial_store", ["Compañía"] + stores)

    week = st.session_state.get("commercial_period", weeks[0])
    store = st.session_state.get("commercial_store", "Compañía")
    breakdowns = filter_period(bundle["breakdowns"], week, store)
    models = filter_period(bundle["models_pdf"], week, store)
    if not breakdowns.empty:
        breakdowns = breakdowns.copy()
        breakdowns["Categoría"] = _section_values(breakdowns)
    if not models.empty:
        models = models.copy()
        models["Categoría"] = _section_values(models)

    category_values = set(breakdowns.get("Categoría", pd.Series(dtype=str)).dropna().astype(str))
    category_values |= set(models.get("Categoría", pd.Series(dtype=str)).dropna().astype(str))
    category_order = [value for value in ("Dama", "Caballero", "Infantil") if value in category_values]
    categories = ["Todas"] + category_order
    _valid_options("commercial_category", categories)
    category = st.session_state.get("commercial_category", "Todas")

    if category != "Todas":
        if not breakdowns.empty:
            breakdowns = breakdowns[breakdowns["Categoría"].eq(category)]
        if not models.empty:
            models = models[models["Categoría"].eq(category)]
    line_values = set(
        breakdowns.loc[breakdowns.get("Tipo", pd.Series(dtype=str)).eq("rubro"), "Etiqueta"].dropna().astype(str)
        if not breakdowns.empty and "Tipo" in breakdowns and "Etiqueta" in breakdowns else []
    )
    line_values |= set(models.get("Rubro", pd.Series(dtype=str)).dropna().astype(str))
    lines = ["Todas"] + sorted(value.strip() for value in line_values if value and value.strip())
    _valid_options("commercial_line", lines)
    line = st.session_state.get("commercial_line", "Todas")

    if line != "Todas" and not models.empty:
        models = models[models.get("Rubro", pd.Series("", index=models.index)).astype(str).str.casefold().eq(line.casefold())]
    model_rows = models[[column for column in ("ID_ART", "Modelo") if column in models]].copy() if not models.empty else pd.DataFrame()
    model_options = ["Todos"]
    if "ID_ART" in model_rows:
        model_rows = model_rows.fillna("").astype(str).drop_duplicates("ID_ART")
        model_options += [
            f"{row['ID_ART']} · {row.get('Modelo', '')}".rstrip(" ·")
            for _, row in model_rows.sort_values("ID_ART").iterrows() if row["ID_ART"].strip()
        ]
    _valid_options("commercial_model", model_options)

    with st.container(border=True, key="commercial_global_filters"):
        st.markdown('<div class="ac-filter-caption">FILTROS GLOBALES · SE CONSERVAN DURANTE TODA LA NAVEGACIÓN</div>', unsafe_allow_html=True)
        c1, c2, c3, c4, c5, c6 = st.columns([1, 1.1, 1, 1.25, 1.6, .55], vertical_alignment="bottom")
        with c1:
            selected_week = st.selectbox("Periodo", weeks, key="commercial_period", format_func=lambda value: value.replace("-W", " · Semana "))
        with c2:
            selected_store = st.selectbox("Tienda", ["Compañía"] + stores, key="commercial_store")
        with c3:
            selected_category = st.selectbox("Categoría", categories, key="commercial_category")
        with c4:
            selected_line = st.selectbox("Línea", lines, key="commercial_line")
        with c5:
            selected_model = st.selectbox("Modelo / SKU", model_options, key="commercial_model")
        with c6:
            st.button("Limpiar", icon=":material/filter_alt_off:", on_click=_clear_global_scope, width="stretch")

    return {
        "week": selected_week, "store": selected_store, "category": selected_category,
        "line": selected_line, "model": selected_model,
        "model_id": "" if selected_model == "Todos" else selected_model.split(" · ", 1)[0],
    }


def _breadcrumb(scope: dict) -> None:
    levels = ["Compañía"]
    if scope["store"] != "Compañía":
        levels.append(scope["store"])
    if scope["category"] != "Todas":
        levels.append(scope["category"])
    if scope["line"] != "Todas":
        levels.append(scope["line"])
    if scope["model"] != "Todos":
        levels.append(scope["model"])
    content = '<span class="ac-crumb-separator">›</span>'.join(f'<span class="ac-crumb">{html.escape(value)}</span>' for value in levels)
    st.markdown(f'<div class="ac-breadcrumb">{content}</div>', unsafe_allow_html=True)


def _scope_frames(bundle: dict, scope: dict, *, use_selected_week: bool = True):
    week = scope["week"] if use_selected_week else None
    stores = store_pdf_summary(bundle["stores_pdf"], week, scope["store"])
    breakdowns = filter_period(bundle["breakdowns"], week, scope["store"])
    models = filter_period(bundle["models_pdf"], week, scope["store"])
    if not breakdowns.empty:
        breakdowns = breakdowns.copy()
        breakdowns["Categoría"] = _section_values(breakdowns)
    if not models.empty:
        models = models.copy()
        models["Categoría"] = _section_values(models)
    if scope["category"] != "Todas":
        breakdowns = breakdowns[breakdowns["Categoría"].eq(scope["category"])] if not breakdowns.empty else breakdowns
        models = models[models["Categoría"].eq(scope["category"])] if not models.empty else models
    if scope["line"] != "Todas":
        if not breakdowns.empty:
            line_mask = breakdowns["Tipo"].eq("rubro") & breakdowns["Etiqueta"].astype(str).str.casefold().eq(scope["line"].casefold())
            breakdowns = breakdowns[line_mask]
        if not models.empty:
            models = models[models.get("Rubro", pd.Series("", index=models.index)).astype(str).str.casefold().eq(scope["line"].casefold())]
    if scope["model_id"] and not models.empty:
        models = models[models["ID_ART"].astype(str).eq(scope["model_id"])]
    return stores, breakdowns, models


def _unique_models(models: pd.DataFrame) -> pd.DataFrame:
    if models is None or models.empty:
        return pd.DataFrame()
    out = models.copy()
    out["ID_ART"] = out.get("ID_ART", pd.Series("", index=out.index)).astype(str)
    sort_columns = [column for column in ("Semana", "Tienda", "ID_ART", "Ranking") if column in out]
    out = out.sort_values(sort_columns).drop_duplicates([column for column in ("Semana", "Tienda", "ID_ART") if column in out])
    return out


def _enrich_summary(frame: pd.DataFrame, name_column: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    def numeric(column: str) -> pd.Series:
        return pd.to_numeric(out.get(column, pd.Series(0, index=out.index)), errors="coerce").fillna(0)

    existence = numeric("Existencia")
    vpd = numeric("VPD")
    positions = numeric("Posiciones")
    out["% Inventario"] = existence.div(existence.sum() or np.nan).mul(100).fillna(0)
    out["% Part. sugerido"] = vpd.div(vpd.sum() or np.nan).mul(100).fillna(0)
    if "% Utilidad" in out:
        out["% Utilidad"] = numeric("% Utilidad")
    out["% Piso"] = numeric("Piso").div(existence.replace(0, np.nan)).mul(100).fillna(0)
    out["% Bodega"] = numeric("Bodega").div(existence.replace(0, np.nan)).mul(100).fillna(0)
    out["Productividad espacio"] = vpd.div(positions.replace(0, np.nan)).fillna(0)
    if "DDI" not in out:
        out["DDI"] = existence.div(vpd.replace(0, np.nan)).fillna(0)
    out["Estado"] = out["DDI"].map(_coverage_status)
    out["Acción"] = out["DDI"].map(_coverage_action)
    first = [name_column] if name_column in out else []
    remaining = [column for column in out if column not in first]
    return out[first + remaining]


def _category_summary(breakdowns: pd.DataFrame) -> pd.DataFrame:
    if breakdowns is None or breakdowns.empty:
        return pd.DataFrame()
    detail = breakdowns[breakdowns["Tipo"].eq("section")].copy()
    if detail.empty:
        detail = breakdowns[breakdowns["Tipo"].eq("rubro")].copy()
    detail = detail[detail["Categoría"].isin(["Dama", "Caballero", "Infantil"])]
    return _enrich_summary(aggregate_pdf(detail, "Categoría"), "Categoría")


def _line_summary(breakdowns: pd.DataFrame, models: pd.DataFrame) -> pd.DataFrame:
    detail = breakdowns[breakdowns["Tipo"].eq("rubro")].copy() if breakdowns is not None and not breakdowns.empty else pd.DataFrame()
    if not detail.empty:
        result = aggregate_pdf(detail, "Etiqueta").rename(columns={"Etiqueta": "Línea"})
        return _enrich_summary(result, "Línea")
    unique = _unique_models(models)
    if unique.empty or "Rubro" not in unique:
        return pd.DataFrame()
    return _enrich_summary(aggregate_pdf(unique.rename(columns={"Rubro": "Línea"}), "Línea"), "Línea")


def _model_summary(models: pd.DataFrame) -> pd.DataFrame:
    matrix = _model_matrix(models)
    if matrix.empty:
        return matrix
    group_columns = [column for column in ("ID_ART", "Modelo", "Marca", "Sección", "Rubro") if column in matrix]
    aggregations = {
        column: "sum" for column in ("Piso", "Bodega", "Existencia", "VPD", "Inversión")
        if column in matrix
    }
    if "% Utilidad" in matrix:
        aggregations["% Utilidad"] = "mean"
    summary = matrix.groupby(group_columns, as_index=False, dropna=False).agg(aggregations)
    summary["Categoría"] = _section_values(summary)
    summary["DDI"] = summary.get("Existencia", 0).div(summary.get("VPD", 0).replace(0, np.nan)).fillna(0)
    return _enrich_summary(summary, "ID_ART")


def _company_catalog_summary(breakdowns: pd.DataFrame) -> pd.DataFrame:
    """Estatus de catálogo a nivel compañía con las métricas publicadas por PDF."""
    if breakdowns is None or breakdowns.empty:
        return pd.DataFrame()
    data = breakdowns[breakdowns.get("Tipo", pd.Series("", index=breakdowns.index)).eq("catalog")].copy()
    if data.empty:
        return pd.DataFrame()
    data["Estatus catálogo"] = data.get("Etiqueta", pd.Series("Sin estatus", index=data.index)).fillna("Sin estatus").astype(str).str.strip().replace("", "Sin estatus")
    summary = aggregate_pdf(data, "Estatus catálogo")
    return _enrich_summary(summary, "Estatus catálogo").sort_values("VPD", ascending=False).reset_index(drop=True)


def _company_rubro_ranking(breakdowns: pd.DataFrame) -> pd.DataFrame:
    """Ranking compañía de rubros, usando VPD como venta diaria sugerida publicada."""
    if breakdowns is None or breakdowns.empty:
        return pd.DataFrame()
    data = breakdowns[breakdowns.get("Tipo", pd.Series("", index=breakdowns.index)).eq("rubro")].copy()
    if data.empty:
        return pd.DataFrame()
    data["Rubro"] = data.get("Etiqueta", pd.Series("Sin rubro", index=data.index)).fillna("Sin rubro").astype(str).str.strip().str.title().replace("", "Sin rubro")
    summary = aggregate_pdf(data, "Rubro")
    summary = _enrich_summary(summary, "Rubro").sort_values(["VPD", "Existencia"], ascending=[False, False]).reset_index(drop=True)
    summary.insert(0, "Ranking", np.arange(1, len(summary) + 1))
    return summary


def _company_model_ranking(models: pd.DataFrame, *, slow: bool = False) -> pd.DataFrame:
    """Consolida modelos compañía evitando duplicarlos entre escenarios del PDF."""
    if models is None or models.empty:
        return pd.DataFrame()
    scenario = "Baja rotación" if slow else "Sugerido / VPD"
    data = models[models.get("Escenario", pd.Series("", index=models.index)).astype(str).eq(scenario)].copy()
    if data.empty:
        return pd.DataFrame()
    for column in ("VPD", "Existencia", "Piso", "Bodega", "DDI", "% Venta", "% Utilidad"):
        data[column] = pd.to_numeric(data.get(column, 0), errors="coerce").fillna(0)
    data["Categoría"] = _section_values(data)
    data["Rubro"] = data.get("Rubro", pd.Series("", index=data.index)).fillna("").astype(str).str.title()
    # Un modelo puede aparecer en varias tiendas; el ranking compañía suma sus métricas.
    group_cols = [c for c in ("ID_ART", "Modelo", "Marca", "Categoría", "Rubro") if c in data]
    out = data.groupby(group_cols, as_index=False, dropna=False).agg({
        "VPD": "sum", "Existencia": "sum", "Piso": "sum", "Bodega": "sum",
        "% Venta": "mean", "% Utilidad": "mean",
    })
    out["DDI"] = out["Existencia"].div(out["VPD"].replace(0, np.nan)).fillna(0)
    out["% Part. sugerido"] = out["VPD"].div(out["VPD"].sum() or np.nan).mul(100).fillna(0)
    if slow:
        # Los de menor movimiento primero; ante empate, más inventario tiene mayor prioridad.
        out = out.sort_values(["VPD", "Existencia"], ascending=[True, False]).head(20).reset_index(drop=True)
    else:
        out = out.sort_values(["VPD", "Existencia"], ascending=[False, False]).head(50).reset_index(drop=True)
    out.insert(0, "Ranking", np.arange(1, len(out) + 1))
    return out


def _section_macro(breakdowns: pd.DataFrame) -> pd.DataFrame:
    data = breakdowns[breakdowns.get("Tipo", pd.Series(dtype=str)).eq("section")].copy()
    if data.empty:
        return pd.DataFrame()
    label = data.get("Etiqueta", pd.Series("", index=data.index)).astype(str).str.upper()
    data["Sección macro"] = np.select(
        [label.str.contains("DAMA|MUJER", regex=True), label.str.contains("CABALL|HOMBRE", regex=True), label.str.contains("NIÑ|BEB|INFANT", regex=True)],
        ["Dama", "Caballero", "Infantil"], default="Otros")
    numeric = [c for c in ("Curva","Piso","Bodega","Existencia","VPD","Inversión") if c in data]
    out = data.groupby("Sección macro", as_index=False)[numeric].sum()
    out["DDI"] = out.get("Existencia",0).div(out.get("VPD",0).replace(0,np.nan)).fillna(0)
    total_vpd = float(out.get("VPD",pd.Series(dtype=float)).sum())
    total_exist = float(out.get("Existencia",pd.Series(dtype=float)).sum())
    out["% Sug Cía."] = out.get("VPD",0).div(total_vpd or np.nan).mul(100).fillna(0)
    out["% Part. inventario"] = out.get("Existencia",0).div(total_exist or np.nan).mul(100).fillna(0)
    # Los porcentajes publicados por tienda se ponderan por VPD para evitar promedios simples engañosos.
    for metric in ("% Utilidad", "% Piezas"):
        if metric in data:
            tmp=data[["Sección macro","VPD",metric]].copy()
            tmp["pond"] = pd.to_numeric(tmp["VPD"],errors="coerce").fillna(0)*pd.to_numeric(tmp[metric],errors="coerce").fillna(0)
            den=tmp.groupby("Sección macro")["VPD"].sum().replace(0,np.nan)
            val=tmp.groupby("Sección macro")["pond"].sum().div(den).fillna(0)
            out[metric]=out["Sección macro"].map(val).fillna(0)
    return out[out["Sección macro"].isin(["Dama","Caballero","Infantil"])].sort_values("VPD",ascending=False)


def _model_matrix(models: pd.DataFrame) -> pd.DataFrame:
    if models is None or models.empty:
        return pd.DataFrame()
    base=models.copy()
    keys=[c for c in ("Tienda","ID_ART") if c in base]
    identity=[c for c in ("Modelo","Marca","Sección","Rubro") if c in base]
    # Un modelo aparece en cuatro rankings del PDF. Se consolida para combinar Sugerido, Utilidad e Inversión sin duplicarlo.
    rows=[]
    for key, grp in base.groupby(keys, dropna=False):
        row={}
        if len(keys)==1: key=(key,)
        row.update(dict(zip(keys,key)))
        for c in identity:
            vals=grp[c].dropna().astype(str); row[c]=next((v for v in vals if v.strip()),"")
        sug=grp[grp["Escenario"].eq("Sugerido / VPD")]
        util=grp[grp["Escenario"].eq("Utilidad")]
        inv=grp[grp["Escenario"].eq("Inversión")]
        slow=grp[grp["Escenario"].eq("Baja rotación")]
        src=sug if not sug.empty else (slow if not slow.empty else grp)
        for c in ("VPD","Existencia","Piso","Bodega","DDI"):
            row[c]=float(pd.to_numeric(src.get(c,pd.Series(dtype=float)),errors="coerce").fillna(0).max()) if c in src else 0
        row["% Utilidad"]=float(pd.to_numeric(util.get("% Utilidad",pd.Series(dtype=float)),errors="coerce").fillna(0).max()) if not util.empty else float(pd.to_numeric(grp.get("% Utilidad",pd.Series(dtype=float)),errors="coerce").fillna(0).max())
        row["Inversión"]=float(pd.to_numeric(inv.get("Inversión",pd.Series(dtype=float)),errors="coerce").fillna(0).max()) if not inv.empty else 0
        row["En baja rotación"]=not slow.empty
        rows.append(row)
    out=pd.DataFrame(rows)
    if out.empty:return out
    out["DDI"]=out["Existencia"].div(out["VPD"].replace(0,np.nan)).fillna(0)
    total=out["VPD"].sum(); out["% Part. Sug"] = out["VPD"].div(total or np.nan).mul(100).fillna(0)
    return out


def _render_model_rankings(models: pd.DataFrame, key: str) -> None:
    matrix=_model_matrix(models)
    if matrix.empty:
        st.info("Los PDF no contienen modelos para el alcance seleccionado."); return

    def section_mask(frame: pd.DataFrame, selected: str | None) -> pd.DataFrame:
        if not selected:
            return frame
        values = frame.get("Sección", pd.Series("", index=frame.index)).astype(str).str.upper()
        if selected == "Infantil":
            return frame[values.str.contains("NIÑ|NIN|BEB|INFANT", regex=True, na=False)]
        return frame[values.str.contains(selected.upper(), regex=False, na=False)]

    st.markdown('<div class="ac-section">Modelos campeones · Top 50</div>',unsafe_allow_html=True)
    c1,c2=st.columns([1.15,1])
    with c1:
        sec_champ=st.segmented_control("Filtrar campeones por sección",["Dama","Caballero","Infantil"],default=None,key=f"{key}_champ_sec")
    with c2:
        order=st.segmented_control("Ordenar campeones por",["Sugerido","Utilidad"],default="Sugerido",key=f"{key}_order") or "Sugerido"
    champs_base=section_mask(matrix,sec_champ)
    if champs_base.empty:
        st.info("No hay modelos campeones para la sección seleccionada.")
    else:
        sortcol="VPD" if order=="Sugerido" else "% Utilidad"
        champs=champs_base.sort_values([sortcol,"VPD"],ascending=[False,False]).head(50).copy()
        champs.insert(0,"#",range(1,len(champs)+1))
        champs_display = champs.rename(columns={"VPD": "Sugerido", "% Part. Sug": "% Part. sugerido"})
        cols=["#","ID_ART","Modelo","Marca","Sección","Rubro","Sugerido","% Part. sugerido","% Utilidad","Existencia","Piso","Bodega","DDI","Inversión"]
        _decision_table(champs_display[[c for c in cols if c in champs_display]],height=620)

    st.markdown('<div class="ac-section">Modelos lentos · bajo sugerido con inversión priorizada</div>',unsafe_allow_html=True)
    c1,c2=st.columns([1.15,1])
    with c1:
        sec_slow=st.segmented_control("Filtrar lentos por sección",["Dama","Caballero","Infantil"],default=None,key=f"{key}_slow_sec")
    with c2:
        slow_order=st.segmented_control("Priorizar lentos por",["Sugerido menor","Inversión mayor"],default="Sugerido menor",key=f"{key}_slow_order") or "Sugerido menor"
    slow_base=section_mask(matrix,sec_slow)
    if slow_base.empty:
        st.info("No hay modelos lentos para la sección seleccionada.")
        return
    if slow_order=="Inversión mayor":
        slow=slow_base.sort_values(["Inversión","VPD"],ascending=[False,True]).head(20).copy()
    else:
        slow=slow_base.sort_values(["VPD","Inversión"],ascending=[True,False]).head(20).copy()
    slow["Capital de atención"] = np.select([slow["Inversión"].rank(pct=True).ge(.67),slow["Inversión"].rank(pct=True).ge(.34)],["Alta","Media"],default="Baja")
    slow.insert(0,"#",range(1,len(slow)+1))
    slow_display = slow.rename(columns={"VPD": "Sugerido"})
    cols=["#","Capital de atención","ID_ART","Modelo","Marca","Sección","Rubro","Sugerido","Existencia","DDI","Inversión","% Utilidad","Piso","Bodega"]
    _decision_table(slow_display[[c for c in cols if c in slow_display]],status_columns=("Capital de atención",),height=470)

def _render_company_level(bundle: dict, scope: dict, stores: pd.DataFrame, breakdowns: pd.DataFrame, models: pd.DataFrame) -> None:
    if stores.empty:
        _no_data(); return
    total=_totals(stores)
    existence=float(total.get("Existencia",0)); floor=float(total.get("Piso",0)); warehouse=float(total.get("Bodega",0))
    curve=float(total.get("Curva",0)); sug=float(total.get("VPD",0)); ddi=existence/sug if sug else 0
    floor_pct=floor/existence*100 if existence else 0; wh_pct=warehouse/existence*100 if existence else 0
    occupancy_pct=existence/curve*100 if curve else 0
    sections=_section_macro(breakdowns)
    investment_models=_scenario_models(models,"Inversión")
    identified_investment=float(pd.to_numeric(investment_models.get("Inversión",pd.Series(dtype=float)),errors="coerce").fillna(0).sum()) if not investment_models.empty else 0

    st.markdown('<div class="ac-section">Macro · Compañía</div>',unsafe_allow_html=True)
    _kpis([
      ("Existencia total",_number(existence),f"Ocupación {occupancy_pct:.1f}% · Piso {floor_pct:.1f}% · Bodega {wh_pct:.1f}%",PURPLE),
      ("Sugerido compañía",_number(sug),"Movimiento diario publicado",CYAN),
      ("DDI compañía",f"{ddi:.0f} días","Existencia / Sugerido",ORANGE),
      ("Capacidad (Curva)",_number(curve),"Capacidad publicada en el PDF",BLUE),
      ("Part. piezas","100%","Composición por sección abajo",GREEN),
      ("Part. inventario","100%","Composición por sección abajo",PINK),
      ("Part. utilidad","100%","Participación publicada, no margen",CYAN),
      ("Inversión identificada",_money(identified_investment),"Sólo modelos del ranking Inversión",PURPLE),
    ],4)
    st.caption("La inversión mostrada corresponde únicamente a los modelos publicados en el ranking de Inversión del PDF; no se presenta como inversión total de la compañía.")

    st.markdown('<div class="ac-section">Dama · Caballero · Infantil</div>',unsafe_allow_html=True)
    if not sections.empty:
        cards=[]
        for _,r in sections.iterrows():
            title=str(r['Sección macro'])
            subtitle=(f"Sugerido {_number(r.get('VPD',0))} · {r.get('% Sug Cía.',0):.1f}% Cía. · "
                      f"Exist. {_number(r.get('Existencia',0))} · DDI {r.get('DDI',0):.0f} · "
                      f"Util. {r.get('% Utilidad',0):.1f}%")
            cards.append((title,_percent(r.get('% Piezas',0)),subtitle,BLUE if title=='Dama' else (GREEN if title=='Caballero' else ORANGE)))
        _kpis(cards,3)
        display=sections.rename(columns={"Sección macro":"Sección","VPD":"Sugerido","% Sug Cía.":"% Sug Cía","% Part. inventario":"% Part Inventario","% Piezas":"% Part Piezas"})
        _decision_table(display[[c for c in ["Sección","Curva","Piso","Bodega","Existencia","Sugerido","DDI","% Sug Cía","% Utilidad","% Part Piezas"] if c in display]],height=260)

    st.markdown('<div class="ac-section">Comparativo de tiendas</div>',unsafe_allow_html=True)
    metric_label=st.segmented_control("Métrica",["Sugerido","Existencia","Piso","Bodega","DDI"],default="Sugerido",key="macro_store_metric") or "Sugerido"
    metric="VPD" if metric_label=="Sugerido" else metric_label
    chart=stores.sort_values(metric)
    fig=go.Figure(go.Bar(y=chart["Tienda"],x=chart[metric],orientation="h",text=chart[metric].map(lambda x:f"{x:,.0f}"),textposition="outside"))
    fig.update_layout(title=f"Tiendas · {metric_label}",xaxis_title=metric_label,yaxis_title="",showlegend=False); _plot(fig,max(390,len(chart)*28+100))
    _render_model_rankings(models,"macro_models")


def _area_summary(breakdowns: pd.DataFrame) -> pd.DataFrame:
    """Consolida las cuatro áreas comerciales publicadas en el PDF."""
    if breakdowns is None or breakdowns.empty:
        return pd.DataFrame()
    loc = breakdowns[breakdowns.get("Tipo", pd.Series("", index=breakdowns.index)).eq("location")].copy()
    if loc.empty:
        return pd.DataFrame()
    loc["Área"] = loc.get("Etiqueta", pd.Series("", index=loc.index)).map(_area_name)
    loc = loc[loc["Área"].ne("")]
    if loc.empty:
        return pd.DataFrame()
    return aggregate_pdf(loc, "Área")


def _area_metric_note(breakdowns: pd.DataFrame, metric: str) -> str:
    """Detalle compacto por área para las tarjetas de tienda."""
    summary = _area_summary(breakdowns)
    if summary.empty:
        return "Sin detalle de áreas"
    specs = [
        ("Doblado", "Dob"),
        ("Colgado", "Col"),
        ("Jeans / Doblado Mezclilla", "Jeans"),
        ("Colgado Lencería", "Lenc"),
    ]
    parts = []
    for area, short in specs:
        row = summary[summary["Área"].eq(area)]
        if row.empty:
            parts.append(f"{short} —")
            continue
        r = row.iloc[0]
        if metric == "Ocupación":
            capacity = float(pd.to_numeric(pd.Series([r.get("Curva", 0)]), errors="coerce").fillna(0).iloc[0])
            existence = float(pd.to_numeric(pd.Series([r.get("Existencia", 0)]), errors="coerce").fillna(0).iloc[0])
            value = existence / capacity * 100 if capacity else 0
            parts.append(f"{short} {value:.1f}%")
        elif metric == "DDI":
            value = float(pd.to_numeric(pd.Series([r.get("DDI", 0)]), errors="coerce").fillna(0).iloc[0])
            parts.append(f"{short} {value:.0f}d")
        else:
            source = "VPD" if metric == "Sugerido" else ("Curva" if metric == "Capacidad" else metric)
            value = float(pd.to_numeric(pd.Series([r.get(source, 0)]), errors="coerce").fillna(0).iloc[0])
            parts.append(f"{short} {_number(value)}")
    return " · ".join(parts)


def _render_store_level(scope: dict, stores: pd.DataFrame, breakdowns: pd.DataFrame, models: pd.DataFrame) -> None:
    if stores.empty:
        _no_data(); return
    total = _totals(stores)
    existence = float(total.get("Existencia", 0))
    capacity = float(total.get("Curva", 0))
    occupancy = existence / capacity * 100 if capacity else 0
    _kpis([
        ("Inventario", _number(existence), _area_metric_note(breakdowns, "Existencia"), PURPLE),
        ("Piso", _number(total["Piso"]), _area_metric_note(breakdowns, "Piso"), GREEN),
        ("Bodega", _number(total["Bodega"]), _area_metric_note(breakdowns, "Bodega"), ORANGE),
        ("Sugerido", _number(total["VPD"]), _area_metric_note(breakdowns, "Sugerido"), CYAN),
        ("DDI", f'{total["DDI"]:.0f} días', _area_metric_note(breakdowns, "DDI"), PINK),
        ("Capacidad (Curva)", _number(capacity), _area_metric_note(breakdowns, "Capacidad"), BLUE),
        ("Ocupación", f"{occupancy:.1f}%", _area_metric_note(breakdowns, "Ocupación"), RED if occupancy > 100 else GREEN),
    ], 7)
    categories = _category_summary(breakdowns)
    st.markdown('<div class="ac-section">Radiografía por categoría</div>', unsafe_allow_html=True)
    columns = ["Categoría", "Estado", "Existencia", "Piso", "Bodega", "% Inventario", "% Utilidad", "VPD", "DDI", "Posiciones", "Productividad espacio", "Acción"]
    _decision_table(categories[[column for column in columns if column in categories]], status_columns=("Estado", "Acción"), height=360)
    support = _model_summary(models).sort_values("VPD", ascending=False).head(15) if not models.empty else pd.DataFrame()
    if not support.empty:
        st.markdown('<div class="ac-section">Modelos que soportan el resultado</div>', unsafe_allow_html=True)
        support = support.rename(columns={"VPD": "Sugerido", "DDI": "Días de inventario", "Rubro": "Línea"})
        support_columns = ["ID_ART", "Modelo", "Marca", "Categoría", "Línea", "Existencia", "Sugerido", "Días de inventario", "% Utilidad", "Acción"]
        _decision_table(support[[column for column in support_columns if column in support]], status_columns=("Acción",), height=360)


def _render_category_level(scope: dict, breakdowns: pd.DataFrame, models: pd.DataFrame) -> None:
    lines = _line_summary(breakdowns, models)
    if lines.empty:
        st.info("El PDF no contiene líneas para la categoría seleccionada."); return
    totals = lines.sum(numeric_only=True)
    _kpis([
        ("Categoría", scope["category"], "Nivel actual", BLUE),
        ("Líneas", _number(lines["Línea"].nunique()), "Disponibles", GREEN),
        ("Inventario", _number(totals.get("Existencia", 0)), "Piezas", PURPLE),
        ("Sugerido", _number(totals.get("VPD", 0)), "Dato del PDF", CYAN),
        ("Piso", _number(totals.get("Piso", 0)), "Piezas", GREEN),
        ("Bodega", _number(totals.get("Bodega", 0)), "Piezas", ORANGE),
    ], 6)
    display = lines.rename(columns={"VPD": "Sugerido", "DDI": "Días de inventario"})
    columns = ["Línea", "Estado", "Existencia", "Piso", "Bodega", "% Inventario", "% Utilidad", "Sugerido", "Días de inventario", "Posiciones", "Productividad espacio", "Acción"]
    st.markdown('<div class="ac-section">Líneas que explican el resultado</div>', unsafe_allow_html=True)
    _decision_table(display[[column for column in columns if column in display]], status_columns=("Estado", "Acción"), height=470)


def _render_line_level(scope: dict, models: pd.DataFrame, breakdowns: pd.DataFrame) -> None:
    summary = _model_summary(models)
    if summary.empty:
        line = _line_summary(breakdowns, models)
        if line.empty:
            st.info("El PDF no contiene información para la línea seleccionada."); return
        row = line.iloc[0]
        _kpis([
            ("Línea", scope["line"], "Nivel actual", BLUE),
            ("Inventario", _number(row.get("Existencia", 0)), "Piezas", PURPLE),
            ("Sugerido", _number(row.get("VPD", 0)), "Dato del PDF", CYAN),
            ("Días de inventario", f'{row.get("DDI", 0):.0f}', _coverage_meaning(float(row.get("DDI", 0))), PINK),
        ], 4)
        display = line.rename(columns={"VPD": "Sugerido", "DDI": "Días de inventario"})
        columns = ["Línea", "Estado", "Existencia", "Piso", "Bodega", "Sugerido", "Días de inventario", "Posiciones", "Productividad espacio", "Acción"]
        _decision_table(display[[column for column in columns if column in display]], status_columns=("Estado", "Acción"), height=230)
        st.info("El PDF contiene el total de la línea, pero no publicó modelos de esta línea dentro de sus rankings Top 40.")
        return
    _kpis([
        ("Línea", scope["line"], "Nivel actual", BLUE),
        ("Modelos publicados", _number(summary["ID_ART"].nunique()), "Rankings PDF", GREEN),
        ("Inventario", _number(summary["Existencia"].sum()), "Piezas", PURPLE),
        ("Sugerido", _number(summary["VPD"].sum()), "Dato del PDF", CYAN),
    ], 4)
    display = summary.rename(columns={"VPD": "Sugerido", "DDI": "Días de inventario", "Rubro": "Línea"})
    columns = ["ID_ART", "Modelo", "Marca", "Categoría", "Línea", "Estado", "Existencia", "Piso", "Bodega", "Sugerido", "Días de inventario", "% Utilidad", "Acción"]
    st.markdown('<div class="ac-section">Tabla maestra de modelos</div>', unsafe_allow_html=True)
    _decision_table(display[[column for column in columns if column in display]].sort_values("Sugerido", ascending=False), status_columns=("Estado", "Acción"), height=540)


def _render_model_level(bundle: dict, scope: dict, models: pd.DataFrame) -> None:
    summary = _model_summary(models)
    if summary.empty:
        st.info("No existe detalle para el modelo seleccionado en este corte."); return
    row = summary.iloc[0]
    _kpis([
        ("Modelo / SKU", scope["model"], "Selección actual", BLUE),
        ("Inventario", _number(summary["Existencia"].sum()), "Piezas", PURPLE),
        ("Piso", _number(summary.get("Piso", pd.Series(dtype=float)).sum()), "Piezas", GREEN),
        ("Bodega", _number(summary.get("Bodega", pd.Series(dtype=float)).sum()), "Piezas", ORANGE),
        ("Sugerido", _number(summary["VPD"].sum()), "Dato del PDF", CYAN),
        ("Días de inventario", f'{row.get("DDI", 0):.0f}', _coverage_meaning(float(row.get("DDI", 0))), PINK),
        ("Sugerido de inventario", "Información no disponible", "No viene en el PDF", RED),
        ("Venta en pesos", "Información no disponible", "No viene en el PDF", RED),
    ], 8)
    history = filter_period(bundle["models_pdf"], store=scope["store"])
    history = history[history["ID_ART"].astype(str).eq(scope["model_id"])] if not history.empty else history
    history = _unique_models(history)
    if not history.empty:
        trend = history.groupby("Semana", as_index=False)[[column for column in ("Existencia", "VPD") if column in history]].sum().sort_values("Semana")
        trend["DDI"] = trend.get("Existencia", 0).div(trend.get("VPD", 0).replace(0, np.nan)).fillna(0)
        fig = go.Figure()
        fig.add_scatter(x=trend["Semana"], y=trend["VPD"], mode="lines", name="Sugerido", line=dict(color=BLUE, width=4))
        fig.add_scatter(x=trend["Semana"], y=trend["DDI"], mode="lines", name="Días de inventario", yaxis="y2", line=dict(color=PINK, width=4))
        fig.update_layout(title="Historia disponible del modelo", yaxis_title="Sugerido", yaxis2=dict(title="Días de inventario", overlaying="y", side="right"))
        _plot(fig, 360)
    all_stores = filter_period(bundle["models_pdf"], scope["week"], "Compañía")
    all_stores = all_stores[all_stores["ID_ART"].astype(str).eq(scope["model_id"])] if not all_stores.empty else all_stores
    performance = _unique_models(all_stores)
    if not performance.empty:
        performance = _enrich_summary(performance, "Tienda").rename(columns={"VPD": "Sugerido", "DDI": "Días de inventario"})
        columns = ["Tienda", "Estado", "Existencia", "Piso", "Bodega", "Sugerido", "Días de inventario", "% Utilidad", "Acción"]
        st.markdown('<div class="ac-section">Desempeño del modelo por tienda</div>', unsafe_allow_html=True)
        _decision_table(performance[[column for column in columns if column in performance]], status_columns=("Estado", "Acción"), height=390)


def _page_radiography(bundle: dict) -> None:
    _header("Planeación Comercial · Macro Compañía", "Compañía → Sección → Catálogo → Rubro → Modelo", bundle)
    st.markdown('<div class="ac-source-note">La vista usa exclusivamente información publicada en los PDF. <b>Capacidad = Curva</b> y <b>Ocupación = Existencia / Capacidad × 100</b>. Los campos que requieren ventas en pesos o existencias futuras se identifican como Información no disponible.</div>', unsafe_allow_html=True)
    scope = _global_scope(bundle)
    _breadcrumb(scope)
    stores, breakdowns, models = _scope_frames(bundle, scope)
    if scope["model_id"]:
        _render_model_level(bundle, scope, models)
    elif scope["line"] != "Todas":
        _render_line_level(scope, models, breakdowns)
    elif scope["category"] != "Todas":
        _render_category_level(scope, breakdowns, models)
    elif scope["store"] != "Compañía":
        _render_store_level(scope, stores, breakdowns, models)
    else:
        _render_company_level(bundle, scope, stores, breakdowns, models)


def _page_catalog(bundle: dict) -> None:
    _header("Catálogo Comercial", "Explora categorías, líneas y modelos sin perder el contexto", bundle)
    scope = _global_scope(bundle)
    _breadcrumb(scope)
    _, breakdowns, models = _scope_frames(bundle, scope)
    level = st.segmented_control("Nivel del catálogo", ["Categorías", "Líneas", "Modelos"], default="Categorías", key="catalog_level")
    if level == "Categorías":
        data = _category_summary(breakdowns)
        columns = ["Categoría", "Existencia", "Piso", "Bodega", "% Inventario", "% Utilidad", "VPD", "DDI", "Posiciones", "Estado", "Acción"]
    elif level == "Líneas":
        data = _line_summary(breakdowns, models)
        columns = ["Línea", "Existencia", "Piso", "Bodega", "% Inventario", "% Utilidad", "VPD", "DDI", "Posiciones", "Estado", "Acción"]
    else:
        data = _model_summary(models)
        query = st.text_input("Buscar por modelo, SKU, marca, categoría o línea", key="catalog_query", placeholder="Escribe para localizar...")
        if query and not data.empty:
            search_columns = [column for column in ("ID_ART", "Modelo", "Marca", "Categoría", "Rubro") if column in data]
            mask = pd.Series(False, index=data.index)
            for column in search_columns:
                mask |= data[column].astype(str).str.contains(query, case=False, na=False, regex=False)
            data = data[mask]
        data = data.rename(columns={"Rubro": "Línea"})
        columns = ["ID_ART", "Modelo", "Marca", "Categoría", "Línea", "Existencia", "Piso", "Bodega", "% Utilidad", "VPD", "DDI", "Estado", "Acción"]
    if data.empty:
        st.info("No hay información disponible para los filtros seleccionados."); return
    display = data.rename(columns={"VPD": "Sugerido", "DDI": "Días de inventario"})
    columns = ["Sugerido" if column == "VPD" else "Días de inventario" if column == "DDI" else column for column in columns]
    _decision_table(display[[column for column in columns if column in display]], status_columns=("Estado", "Acción"), height=590)
    st.caption("Los modelos corresponden a los rankings publicados en los PDF; el sistema no inventa modelos fuera de la fuente.")


def _planning_summary(scope: dict, breakdowns: pd.DataFrame, models: pd.DataFrame, stores: pd.DataFrame) -> pd.DataFrame:
    if scope["line"] != "Todas":
        source = _model_summary(models).rename(columns={"ID_ART": "Elemento"})
    elif scope["store"] != "Compañía" or scope["category"] != "Todas":
        source = _line_summary(breakdowns, models).rename(columns={"Línea": "Elemento"})
    else:
        source = _enrich_summary(stores, "Tienda").rename(columns={"Tienda": "Elemento"})
    if source.empty:
        return source
    source = source.copy()
    source["Participación VPD"] = pd.to_numeric(source.get("VPD", 0), errors="coerce").fillna(0).div(pd.to_numeric(source.get("VPD", 0), errors="coerce").fillna(0).sum() or np.nan).mul(100).fillna(0)
    source["Participación espacio"] = pd.to_numeric(source.get("Posiciones", 0), errors="coerce").fillna(0).div(pd.to_numeric(source.get("Posiciones", 0), errors="coerce").fillna(0).sum() or np.nan).mul(100).fillna(0)
    source["Diferencia"] = source["Participación VPD"] - source["Participación espacio"]
    source["Recomendación"] = np.select(
        [source["Diferencia"].ge(3) & source["DDI"].le(120), source["Diferencia"].le(-3) | source["DDI"].gt(120)],
        ["Incrementar", "Reducir"], default="Mantener",
    )
    source["Explicación"] = source.apply(
        lambda row: f"{row['Participación VPD']:.1f}% de VPD frente a {row['Participación espacio']:.1f}% del espacio reportado; cobertura de {row['DDI']:.0f} días.", axis=1
    )
    return source


def _page_planning(bundle: dict) -> None:
    _header("Planeación Comercial", "Diagnóstico → Oportunidad → Decisión → Acción", bundle)
    scope = _global_scope(bundle)
    _breadcrumb(scope)
    stores, breakdowns, models = _scope_frames(bundle, scope)
    planning = _planning_summary(scope, breakdowns, models, stores)
    actions = pdf_opportunities(stores, breakdowns, models)
    plain = _plain_opportunities(actions)
    _kpis([
        ("Acciones para hoy", _number(plain["Cuándo"].eq("Hoy").sum()) if not plain.empty else "0", "Prioridad alta", RED),
        ("Incrementar espacio", _number(planning["Recomendación"].eq("Incrementar").sum()) if not planning.empty else "0", "Oportunidades", BLUE),
        ("Reducir espacio", _number(planning["Recomendación"].eq("Reducir").sum()) if not planning.empty else "0", "Sobreasignación", PINK),
        ("Capacidad disponible", "Información no disponible", "Requiere archivo de capacidades", ORANGE),
    ], 4)
    st.info("Las recomendaciones actuales usan VPD, días de inventario y posiciones reportadas en el PDF. No se presentan como capacidad definitiva hasta cargar la fuente de espacios.", icon=":material/info:")
    if not planning.empty:
        display = planning.rename(columns={"VPD": "Venta diaria sugerida", "DDI": "Días de inventario", "Posiciones": "Espacio actual"})
        columns = ["Elemento", "Existencia", "Venta diaria sugerida", "Días de inventario", "Espacio actual", "Participación VPD", "Participación espacio", "Diferencia", "Recomendación", "Explicación"]
        st.markdown('<div class="ac-section">Planeación de inventario y espacio</div>', unsafe_allow_html=True)
        _decision_table(display[[column for column in columns if column in display]], status_columns=("Recomendación",), height=430)
    if not plain.empty:
        st.markdown('<div class="ac-section">Plan de acción operativo</div>', unsafe_allow_html=True)
        _decision_table(plain, status_columns=("Cuándo",), height=430)


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
    _header("Histórico Comercial", "Evolución del nivel seleccionado sin perder el contexto", bundle)
    scope = _global_scope(bundle)
    _breadcrumb(scope)
    if scope["model_id"]:
        history = filter_period(bundle["models_pdf"], store=scope["store"])
        history = history[history["ID_ART"].astype(str).eq(scope["model_id"])] if not history.empty else history
        history = _unique_models(history)
    elif scope["line"] != "Todas":
        history = filter_period(bundle["breakdowns"], store=scope["store"])
        history = history[history["Tipo"].eq("rubro") & history["Etiqueta"].astype(str).str.casefold().eq(scope["line"].casefold())] if not history.empty else history
    elif scope["category"] != "Todas":
        history = filter_period(bundle["breakdowns"], store=scope["store"])
        if not history.empty:
            history = history.copy()
            history["Categoría"] = _section_values(history)
            history = history[history["Tipo"].eq("section") & history["Categoría"].eq(scope["category"])]
    else:
        history = filter_period(bundle["stores_pdf"], store=scope["store"])
    if history.empty:
        st.info("No existe histórico para el nivel seleccionado."); return
    for column in ("Existencia", "VPD", "Curva", "Piso", "Bodega", "Posiciones"):
        if column not in history:
            history[column] = 0
        history[column] = pd.to_numeric(history[column], errors="coerce").fillna(0)
    history = history.groupby(["Semana", "Tienda"], as_index=False)[["Existencia", "VPD", "Curva", "Piso", "Bodega", "Posiciones"]].sum()
    history["DDI"] = history["Existencia"].div(history["VPD"].replace(0, np.nan)).fillna(0)
    week = _latest_week(history["Semana"])
    current = history[history["Semana"].eq(week)]
    trend = history.groupby("Semana", as_index=False)[["Existencia", "VPD", "Curva"]].sum().sort_values("Semana")
    previous = trend.iloc[-2] if len(trend) > 1 else trend.iloc[-1]
    current_trend = trend.iloc[-1]
    vpd_change = (current_trend["VPD"] / previous["VPD"] - 1) * 100 if previous["VPD"] else 0
    inv_change = (current_trend["Existencia"] / previous["Existencia"] - 1) * 100 if previous["Existencia"] else 0
    _kpis([
        ("Venta diaria sugerida", f"{vpd_change:+.1f}%", "Vs. semana anterior", BLUE),
        ("Inventario total", f"{inv_change:+.1f}%", "Vs. semana anterior", GREEN),
        ("Tiendas críticas", _number(((current["DDI"] > 0) & (current["DDI"] <= 30)).sum()), "Requieren acción", RED),
        ("Cobertura del corte", _percent(current["Tienda"].nunique() / (17 if scope["store"] == "Compañía" else 1) * 100), "Tiendas con información", ORANGE),
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


def _canonical_location(values: pd.Series) -> pd.Series:
    upper = values.fillna("").astype(str).str.upper()
    return pd.Series(
        np.select(
            [
                upper.str.contains("MEZ|JEAN", regex=True),
                upper.str.contains("COLG", regex=True),
                upper.str.contains("DOBL", regex=True),
                upper.str.contains("LENCER|BRASIER|PANTALETA|ROPA INTERIOR", regex=True),
            ],
            ["Jeans", "Colgado", "Doblado", "Lencería"],
            default=values.fillna("").astype(str).str.title(),
        ),
        index=values.index,
    ).replace("", "Sin ubicación")


def _dimension_summary(breakdowns: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Resume piezas, venta y utilidad sin convertir participaciones en montos."""
    if breakdowns is None or breakdowns.empty:
        return pd.DataFrame()
    kind = {"Sección": "section", "Ubicación": "location", "Línea": "rubro"}[dimension]
    data = breakdowns[breakdowns["Tipo"].eq(kind)].copy()
    if data.empty:
        return data
    if dimension == "Sección":
        data["Elemento"] = _section_values(data)
    elif dimension == "Ubicación":
        data["Elemento"] = _canonical_location(data["Etiqueta"])
    else:
        data["Elemento"] = data["Etiqueta"].fillna("").astype(str).str.strip().str.title()
    data = data[data["Elemento"].ne("")]
    absolute = ["VPD", "Existencia", "Piso", "Bodega", "Posiciones", "Inversión"]
    percentages = ["% Piezas", "% Venta", "% Utilidad"]
    for column in absolute + percentages:
        data[column] = pd.to_numeric(data.get(column, 0), errors="coerce").fillna(0)
    per_store = data.groupby(["Tienda", "Elemento"], as_index=False)[absolute + percentages].sum()
    totals = per_store.groupby("Elemento", as_index=False)[absolute].sum()
    averages = per_store.groupby("Elemento", as_index=False)[percentages].mean()
    summary = totals.merge(averages, on="Elemento", how="left")
    summary["% Part. piezas"] = summary["VPD"].div(summary["VPD"].sum() or np.nan).mul(100).fillna(0)
    summary["% Part. venta $"] = summary["% Venta"]
    summary["% Part. utilidad"] = summary["% Utilidad"]
    summary["DDI"] = summary["Existencia"].div(summary["VPD"].replace(0, np.nan)).fillna(0)
    summary["Estado"] = summary["DDI"].map(_coverage_status)
    summary["Acción"] = [
        _coverage_action(float(days), float(warehouse) / float(existence) * 100 if existence else 0)
        for days, warehouse, existence in zip(summary["DDI"], summary["Bodega"], summary["Existencia"])
    ]
    return summary.sort_values(["VPD", "% Part. venta $"], ascending=False).reset_index(drop=True)


def _scope_participation(bundle: dict, scope: dict, stores: pd.DataFrame) -> float:
    company = store_pdf_summary(bundle["stores_pdf"], scope["week"], "Compañía")
    company_vpd = pd.to_numeric(company.get("VPD", 0), errors="coerce").sum() if not company.empty else 0
    selected_vpd = pd.to_numeric(stores.get("VPD", 0), errors="coerce").sum() if not stores.empty else 0
    return selected_vpd / company_vpd * 100 if company_vpd else 0


def _scenario_models(models: pd.DataFrame, scenario: str) -> pd.DataFrame:
    if models is None or models.empty:
        return pd.DataFrame()
    data = models[models.get("Escenario", pd.Series("", index=models.index)).astype(str).eq(scenario)].copy()
    if data.empty:
        return data
    for column in ("Ranking", "Piso", "Bodega", "Existencia", "VPD", "DDI", "Inversión", "% Utilidad", "% Venta"):
        data[column] = pd.to_numeric(data.get(column, 0), errors="coerce").fillna(0)
    data["Categoría"] = _section_values(data)
    data["Línea"] = data.get("Rubro", pd.Series("", index=data.index)).fillna("").astype(str).str.title()
    data = data.sort_values(["Ranking", "Tienda", "ID_ART"]).drop_duplicates(["Tienda", "ID_ART"])
    warehouse_share = data["Bodega"].div(data["Existencia"].replace(0, np.nan)).mul(100).fillna(0)
    data["Prioridad"] = np.select(
        [data["DDI"].le(14) & data["VPD"].gt(0), data["DDI"].le(30) & data["VPD"].gt(0), data["DDI"].gt(120), warehouse_share.gt(20)],
        ["1 · Urgente", "2 · Hoy", "3 · Revisar", "4 · Piso"],
        default="5 · Mantener",
    )
    data["Acción"] = np.select(
        [data["DDI"].le(14) & data["VPD"].gt(0), data["DDI"].le(30) & data["VPD"].gt(0), data["DDI"].gt(120), warehouse_share.gt(20)],
        ["Resurtir", "Vigilar agotamiento", "Contener o transferir", "Subir de bodega a piso"],
        default="Mantener",
    )
    return data.reset_index(drop=True)


def _participation_chart(data: pd.DataFrame, title: str, *, include_pieces: bool = True) -> None:
    if data.empty:
        return
    chart = data.head(14).sort_values("% Part. venta $")
    fig = go.Figure()
    if include_pieces:
        fig.add_bar(
            y=chart["Elemento"], x=chart["% Part. piezas"], orientation="h",
            name="Participación piezas", marker_color=BLUE,
            text=chart["% Part. piezas"].map(lambda value: f"{value:.1f}%"), textposition="outside",
        )
    fig.add_bar(
        y=chart["Elemento"], x=chart["% Part. venta $"], orientation="h",
        name="Participación venta $", marker_color=PINK,
        text=chart["% Part. venta $"].map(lambda value: f"{value:.1f}%"), textposition="outside",
    )
    fig.update_layout(title=title, barmode="group", xaxis_title="Participación (%)", yaxis_title="")
    _plot(fig, max(360, len(chart) * 34 + 120))


def _page_store_home(bundle: dict) -> None:
    _header("Mi tienda en 30 segundos", "Lo que aporta, lo que se mueve y lo que requiere atención", bundle)
    scope = _global_scope(bundle)
    _breadcrumb(scope)
    stores, breakdowns, models = _scope_frames(bundle, scope)
    if scope["model_id"]:
        _render_model_level(bundle, scope, models); return
    if scope["line"] != "Todas":
        _render_line_level(scope, models, breakdowns); return
    if scope["category"] != "Todas":
        _render_category_level(scope, breakdowns, models); return
    if stores.empty:
        _no_data(); return
    total = _totals(stores)
    participation = _scope_participation(bundle, scope, stores)
    actions = _plain_opportunities(pdf_opportunities(stores, breakdowns, models))
    urgent = int(actions["Cuándo"].eq("Hoy").sum()) if not actions.empty else 0
    _kpis([
        ("Venta piezas", "Información no disponible", "El PDF aporta sugerido, no venta semanal", BLUE),
        ("Venta en pesos", "Información no disponible", "Requiere fuente de ventas", PINK),
        ("Sugerido", _number(total["VPD"]), "Promedio diario de piezas", GREEN),
        ("Participación piezas", _percent(participation), "Calculada sobre sugerido compañía", BLUE),
        ("Participación venta $", "Información no disponible", "No existe total $ por tienda", PINK),
        ("Margen de utilidad", "Información no disponible", "El PDF publica participación", ORANGE),
    ], 6)
    dimension = _dimension_summary(breakdowns, "Sección")
    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        if not dimension.empty:
            _participation_chart(dimension, "Qué secciones explican el resultado")
    with right:
        _kpis([
            ("Inventario", _number(total["Existencia"]), "Piso + bodega", PURPLE),
            ("Días de inventario", f'{total["DDI"]:.0f}', _coverage_meaning(total["DDI"]), CYAN),
            ("Acciones para hoy", _number(urgent), "Prioridad operativa", RED),
        ], 1)
    st.markdown('<div class="ac-section">Qué debe hacer la tienda</div>', unsafe_allow_html=True)
    if actions.empty:
        st.success("No se detectaron acciones críticas con los datos del corte.")
    else:
        _decision_table(actions.head(12), status_columns=("Cuándo",), height=390)
    if scope["store"] == "Compañía":
        st.caption("Selecciona una tienda para convertir el resumen de compañía en una lista operativa específica para esa sucursal.")


def _page_sales_focus(bundle: dict) -> None:
    _header("Qué está vendiendo", "Participación en piezas, venta en pesos y utilidad con lectura directa", bundle)
    scope = _global_scope(bundle)
    _breadcrumb(scope)
    _, breakdowns, _ = _scope_frames(bundle, scope)
    dimension = st.segmented_control("Ver por", ["Sección", "Ubicación", "Línea"], default="Sección", key="sales_dimension") or "Sección"
    data = _dimension_summary(breakdowns, dimension)
    if data.empty:
        st.info(f"El PDF no contiene información de {dimension.lower()} para el alcance seleccionado."); return
    leader = data.iloc[0]
    _kpis([
        ("Sugerido", _number(data["VPD"].sum()), "Promedio diario de piezas", GREEN),
        ("Líder en piezas", leader["Elemento"], _percent(leader["% Part. piezas"]), BLUE),
        ("Líder en venta $", data.nlargest(1, "% Part. venta $").iloc[0]["Elemento"], _percent(data["% Part. venta $"].max()), PINK),
        ("Líder en utilidad", data.nlargest(1, "% Part. utilidad").iloc[0]["Elemento"], _percent(data["% Part. utilidad"].max()), ORANGE),
    ], 4)
    _participation_chart(data, f"Participación por {dimension.lower()}")
    display = data.rename(columns={"VPD": "Sugerido", "DDI": "Días inventario"})
    columns = ["Elemento", "Sugerido", "% Part. piezas", "% Part. venta $", "% Part. utilidad", "Existencia", "Piso", "Bodega", "Días inventario", "Estado", "Acción"]
    st.markdown('<div class="ac-section">Tabla de venta y participación</div>', unsafe_allow_html=True)
    _decision_table(display[columns], status_columns=("Estado", "Acción"), height=500)
    note = "En alcance Compañía, los porcentajes monetarios son el promedio de participación reportado por las tiendas; no son un importe consolidado. " if scope["store"] == "Compañía" else ""
    st.caption(note + "% Part. venta $ y % Part. utilidad son participaciones publicadas en el PDF; no representan monto vendido ni margen.")


def _page_restock_focus(bundle: dict) -> None:
    _header("Qué debo resurtir", "Sugerido diario, existencia y acciones ordenadas por urgencia", bundle)
    scope = _global_scope(bundle)
    _breadcrumb(scope)
    _, _, models = _scope_frames(bundle, scope)
    data = _scenario_models(models, "Sugerido / VPD")
    if data.empty:
        st.info("El PDF no publicó modelos dentro del ranking Sugerido para este alcance."); return
    urgent = data[data["Prioridad"].str.startswith(("1", "2"))]
    _kpis([
        ("Modelos publicados", _number(data["ID_ART"].nunique()), "Ranking del PDF", BLUE),
        ("Sugerido", _number(data["VPD"].sum()), "Promedio diario Top publicados", GREEN),
        ("Atención inmediata", _number(len(urgent)), "Hasta 30 días", RED),
        ("Mercancía en bodega", _number(data["Bodega"].sum()), "Piezas de modelos publicados", ORANGE),
    ], 4)
    display = data.rename(columns={"VPD": "Sugerido diario", "DDI": "Días inventario", "% Utilidad": "% Part. utilidad"})
    columns = ["Prioridad", "Tienda", "ID_ART", "Modelo", "Categoría", "Línea", "Existencia", "Piso", "Bodega", "Sugerido diario", "Días inventario", "% Part. utilidad", "Acción"]
    _decision_table(display[[column for column in columns if column in display]].sort_values(["Prioridad", "Sugerido diario"], ascending=[True, False]), status_columns=("Prioridad", "Acción"), height=610)
    st.caption("Sugerido es el promedio diario de piezas publicado por el PDF. La acción compara ese ritmo con existencia, piso, bodega y días de inventario.")


def _page_models_focus(bundle: dict) -> None:
    _header("Mis modelos", "Campeones que debo cuidar y lentos que debo mover", bundle)
    scope = _global_scope(bundle)
    _breadcrumb(scope)
    _, _, models = _scope_frames(bundle, scope)
    scenario = st.segmented_control(
        "Ranking", ["Sugerido / VPD", "Utilidad", "Baja rotación", "Inversión"],
        default="Sugerido / VPD", key="model_scenario",
        format_func=lambda value: "Sugerido" if value == "Sugerido / VPD" else value,
    ) or "Sugerido / VPD"
    data = _scenario_models(models, scenario)
    if data.empty:
        st.info(f"No existen modelos publicados en el ranking {scenario} para este alcance."); return
    metric = "Inversión" if scenario == "Inversión" else ("% Utilidad" if scenario == "Utilidad" else ("DDI" if scenario == "Baja rotación" else "VPD"))
    chart = data.head(20).sort_values(metric)
    fig = go.Figure(go.Bar(
        y=chart["ID_ART"].astype(str) + " · " + chart["Modelo"].astype(str), x=chart[metric], orientation="h",
        marker_color=ORANGE if scenario == "Inversión" else (PINK if scenario == "Utilidad" else BLUE),
        text=chart[metric].map(_money if metric == "Inversión" else lambda value: f"{value:,.1f}"), textposition="outside",
    ))
    fig.update_layout(title=f"Top 20 · {scenario}", xaxis_title=metric, yaxis_title="", showlegend=False)
    _plot(fig, 660)
    _kpis([
        ("Modelos del ranking", _number(data["ID_ART"].nunique()), scenario, BLUE),
        ("Sugerido", _number(data["VPD"].sum()), "Top publicados", GREEN),
        ("Existencia", _number(data["Existencia"].sum()), "Top publicados", PURPLE),
        ("Inversión", _money(data["Inversión"].sum()), "Sólo cuando el PDF la publica", ORANGE),
    ], 4)
    display = data.rename(columns={"VPD": "Sugerido", "DDI": "Días inventario"})
    columns = ["Ranking", "Tienda", "ID_ART", "Modelo", "Marca", "Categoría", "Línea", "Sugerido", "Existencia", "Días inventario", "% Utilidad", "Inversión", "Acción"]
    _decision_table(display[[column for column in columns if column in display]], status_columns=("Acción",), height=560)


def _page_profit_focus(bundle: dict) -> None:
    _header("Dinero y utilidad", "Participación publicada e inversión identificada", bundle)
    if st.button("← Más opciones", key="profit_back_more"):
        _open_commercial_page(MORE_PAGE); st.rerun()
    scope = _global_scope(bundle)
    _breadcrumb(scope)
    _, breakdowns, models = _scope_frames(bundle, scope)
    dimension = st.segmented_control("Ver por", ["Sección", "Ubicación", "Línea"], default="Sección", key="profit_dimension") or "Sección"
    data = _dimension_summary(breakdowns, dimension)
    if data.empty:
        st.info("No existe desglose de participación para los filtros seleccionados."); return
    investment_models = _scenario_models(models, "Inversión")
    investment = investment_models["Inversión"].sum() if not investment_models.empty else 0
    sale_leader = data.nlargest(1, "% Part. venta $").iloc[0]
    utility_leader = data.nlargest(1, "% Part. utilidad").iloc[0]
    pieces_leader = data.nlargest(1, "% Part. piezas").iloc[0] if "% Part. piezas" in data else sale_leader
    _kpis([
        ("Mayor part. venta $", sale_leader["Elemento"], _percent(sale_leader["% Part. venta $"]), BLUE),
        ("Mayor part. utilidad", utility_leader["Elemento"], _percent(utility_leader["% Part. utilidad"]), GREEN),
        ("Mayor part. piezas", pieces_leader["Elemento"], _percent(pieces_leader.get("% Part. piezas",0)), CYAN),
        ("Inversión identificada", _money(investment), "Sólo ranking Inversión publicado", PURPLE),
    ], 4)
    chart = data.head(16).sort_values("% Part. utilidad")
    fig = go.Figure()
    fig.add_bar(y=chart["Elemento"], x=chart["% Part. venta $"], orientation="h", name="Participación venta $", marker_color=BLUE, text=chart["% Part. venta $"].map(lambda value: f"{value:.1f}%"), textposition="outside")
    fig.add_bar(y=chart["Elemento"], x=chart["% Part. utilidad"], orientation="h", name="Participación utilidad", marker_color=PINK, text=chart["% Part. utilidad"].map(lambda value: f"{value:.1f}%"), textposition="outside")
    fig.update_layout(title=f"Participación por {dimension.lower()}", barmode="group", xaxis_title="Participación (%)", yaxis_title="")
    _plot(fig, max(390, len(chart) * 36 + 120))
    display = data.rename(columns={"VPD": "Sugerido", "DDI": "DDI", "Inversión": "Inversión $"})
    columns = [c for c in ["Elemento", "% Part. venta $", "% Part. utilidad", "% Part. piezas", "Sugerido", "Existencia", "Inversión $", "DDI", "Acción"] if c in display]
    _decision_table(display[columns], status_columns=("Acción",), height=490)
    st.caption("Los PDF publican participaciones porcentuales; por eso esta vista no muestra tarjetas vacías de venta total o margen que la fuente no contiene.")

def _page_store_evolution(bundle: dict) -> None:
    _header("Mi evolución", "Cómo cambia el sugerido, el inventario y la cobertura semana a semana", bundle)
    if st.button("← Más opciones", key="history_back_more"):
        _open_commercial_page(MORE_PAGE); st.rerun()
    scope = _global_scope(bundle)
    _breadcrumb(scope)
    stores, _, _ = _scope_frames(bundle, scope, use_selected_week=False)
    history = filter_period(bundle["stores_pdf"], store=scope["store"])
    if history.empty:
        st.info("Aún no existen suficientes cortes PDF para construir el histórico."); return
    for column in ("Existencia", "VPD", "Piso", "Bodega"):
        history[column] = pd.to_numeric(history.get(column, 0), errors="coerce").fillna(0)
    trend = history.groupby("Semana", as_index=False)[["Existencia", "VPD", "Piso", "Bodega"]].sum().sort_values("Semana")
    trend["DDI"] = trend["Existencia"].div(trend["VPD"].replace(0, np.nan)).fillna(0)
    current = trend.iloc[-1]
    previous = trend.iloc[-2] if len(trend) > 1 else current
    vpd_change = (current["VPD"] / previous["VPD"] - 1) * 100 if previous["VPD"] else 0
    inventory_change = (current["Existencia"] / previous["Existencia"] - 1) * 100 if previous["Existencia"] else 0
    _kpis([
        ("Sugerido", f"{vpd_change:+.1f}%", "Vs. corte anterior", GREEN if vpd_change >= 0 else RED),
        ("Inventario", f"{inventory_change:+.1f}%", "Vs. corte anterior", BLUE),
        ("Días inventario", f'{current["DDI"]:.0f}', _coverage_meaning(float(current["DDI"])), ORANGE),
        ("Venta en pesos", "Información no disponible", "No viene en el PDF", PINK),
    ], 4)
    left, right = st.columns(2, gap="medium")
    with left:
        fig = go.Figure()
        fig.add_scatter(x=trend["Semana"], y=trend["VPD"], mode="lines", name="Sugerido", line=dict(color=BLUE, width=4), fill="tozeroy", fillcolor="rgba(21,91,239,.08)")
        fig.update_layout(title="Evolución del sugerido diario", yaxis_title="Piezas por día")
        _plot(fig, 370)
    with right:
        fig = go.Figure()
        fig.add_scatter(x=trend["Semana"], y=trend["DDI"], mode="lines", name="Días inventario", line=dict(color=PINK, width=4))
        fig.update_layout(title="Evolución de cobertura", yaxis_title="Días")
        _plot(fig, 370)
    display = trend.rename(columns={"VPD": "Sugerido", "DDI": "Días inventario"}).sort_values("Semana", ascending=False)
    _decision_table(display[["Semana", "Sugerido", "Existencia", "Piso", "Bodega", "Días inventario"]], height=390)
    if len(trend) == 1:
        st.caption("Existe un solo corte. La tendencia se completará automáticamente al cargar las siguientes semanas.")


def _pending_pdf_entries(manifest: dict, week_key: str) -> list[dict]:
    """Recupera archivos incompletos para continuar después de un reinicio."""
    final_statuses = {"Procesado", "Revisar"}
    return [
        entry for entry in manifest.get("pdfs", [])
        if str(entry.get("week", "")) == week_key
        and str(entry.get("status", "")) not in final_statuses
        and resolve_entry_path(entry).exists()
    ]


def _process_pdf_entries(entries: list[tuple[dict, Path]], week_key: str, progress, status_placeholder) -> dict:
    """Procesa y persiste cada PDF antes de avanzar al siguiente.

    Se evita ejecutar varios pdfplumber en paralelo porque en Streamlit Cloud
    esa carga puede agotar memoria y dejar el corte indefinidamente al 5%.
    """
    unique_entries = {}
    for entry, path in entries:
        unique_entries[str(entry.get("id"))] = (entry, Path(path))
    queue = list(unique_entries.values())
    snapshots = load_snapshots()
    results = []
    errors = []
    reused = 0
    total = len(queue)

    def show_status() -> None:
        if not results:
            return
        frame = pd.DataFrame(results)
        status_placeholder.dataframe(frame, width="stretch", height=min(330, 42 + len(frame) * 35), hide_index=True)

    for index, (entry, path) in enumerate(queue, start=1):
        name = str(entry.get("name") or path.name)
        start_value = .03 + .90 * (index - 1) / max(total, 1)
        progress.progress(start_value, text=f"Procesando {index} de {total}: {name}")
        results.append({"#": index, "Archivo": name, "Tienda": entry.get("store", "Por identificar"), "Estado": "Procesando"})
        show_status()
        update_entry("pdfs", entry["id"], status="Procesando", error="")
        try:
            cached = snapshots.get(str(entry.get("id")), {})
            if int(cached.get("parser_version", 0)) >= PDF_PARSER_VERSION and cached.get("status") in {"Procesado", "Revisar"}:
                snapshot = cached
                reused += 1
            else:
                snapshot = extract_pdf_snapshot(path)
                save_snapshot(entry["id"], snapshot)
                snapshots[str(entry["id"])] = snapshot
            update_entry(
                "pdfs", entry["id"], status=snapshot["status"], store=snapshot["store"],
                week=snapshot["week"] or week_key, report_date=snapshot["report_date"],
                pages=snapshot["pages"], records=snapshot["models"], error="",
            )
            results[-1].update({"Tienda": snapshot.get("store", ""), "Estado": snapshot.get("status", "Procesado")})
        except Exception as exc:
            error_text = f"{type(exc).__name__}: {exc}"[:300]
            errors.append(f"{name}: {error_text}")
            update_entry("pdfs", entry["id"], status="Error", error=error_text)
            results[-1]["Estado"] = "Error"
        show_status()
        progress.progress(.03 + .90 * index / max(total, 1), text=f"Completados {index} de {total} PDF")

    return {"completed": total, "errors": errors, "reused": reused, "paths": [path for _, path in queue], "results": results}


def _page_upload(bundle: dict, is_admin: bool) -> None:
    _header("Carga Semanal de PDF", "Tres pasos claros para publicar información confiable", bundle)
    if st.button("← Más opciones", key="upload_back_more"):
        _open_commercial_page(MORE_PAGE); st.rerun()
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
        pending = _pending_pdf_entries(load_manifest(), week_key)
        new_col, resume_col = st.columns([1.35, 1])
        with new_col:
            start_new = st.button("Validar y publicar corte", disabled=not uploads or len(uploads) > 17, type="primary", width="stretch")
        with resume_col:
            resume = st.button(f"Reanudar pendientes ({len(pending)})", disabled=not pending, width="stretch", icon=":material/resume:")
        if start_new or resume:
            entries = []
            source_entries = []
            if start_new:
                for uploaded in uploads:
                    source_entries.append(save_pdf_upload(uploaded, week_key))
            else:
                source_entries = pending
            for entry in source_entries:
                entries.append((entry, resolve_entry_path(entry)))
            progress = st.progress(.01, text=f"Preparando {len(entries)} PDF...")
            status_placeholder = st.empty()
            outcome = _process_pdf_entries(entries, week_key, progress, status_placeholder)
            progress.progress(.96, text="Guardando el corte y su histórico...")
            sync = sync_history_to_cloud(outcome["paths"])
            progress.progress(1.0, text="Corte terminado")
            st.cache_data.clear()
            success_count = outcome["completed"] - len(outcome["errors"])
            message = f"{success_count} PDF procesados; el histórico anterior se conservó."
            if outcome["reused"]:
                message = f"{message} {outcome['reused']} ya estaban listos y no se procesaron nuevamente."
            if outcome["errors"]:
                level, message = "error", f"{message} {len(outcome['errors'])} archivo(s) presentaron error; puedes reintentarlos con Reanudar pendientes."
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
    errors = int((current.get("status", pd.Series(dtype=str)) == "Error").sum())
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


def _page_tiendas_v61(bundle: dict) -> None:
    _header("Tiendas", "Radiografía comercial por tienda · de mayor a menor sugerido", bundle)
    scope=_global_scope(bundle); _breadcrumb(scope)
    stores,breakdowns,models=_scope_frames(bundle,scope)
    if stores.empty:_no_data();return
    total=_totals(stores); ex=total['Existencia']; sug=total['VPD']
    _kpis([("Existencia",_number(ex),f"Piso {_percent(total['Piso']/ex*100 if ex else 0)} · Bodega {_percent(total['Bodega']/ex*100 if ex else 0)}",PURPLE),("Sugerido",_number(sug),f"DDI {ex/sug:.0f}" if sug else "Sin sugerido",CYAN),("Piso",_number(total['Piso']),"Disponibilidad en venta",GREEN),("Bodega",_number(total['Bodega']),"Reserva",ORANGE)],4)
    ranking=stores.sort_values('VPD',ascending=False).copy(); ranking.insert(0,'#',range(1,len(ranking)+1))
    ranking = ranking.rename(columns={'VPD':'Sugerido'})
    _decision_table(ranking[[c for c in ['#','Tienda','Sugerido','Existencia','Piso','Bodega','DDI','Bodega %','Posiciones','Estatus'] if c in ranking]],status_columns=('Estatus',),height=480)
    st.markdown('<div class="ac-section">Secciones de la tienda / alcance</div>',unsafe_allow_html=True)
    sec=_section_macro(breakdowns)
    if not sec.empty:_decision_table(sec.rename(columns={'Sección macro':'Sección','VPD':'Sugerido'}),height=280)
    _render_model_rankings(models,'stores_models')


def _page_section_rubro_v61(bundle: dict) -> None:
    _header("Sección / Rubro", "Dama · Caballero · Infantil → rubro → modelos", bundle)
    scope=_global_scope(bundle); _breadcrumb(scope)
    _,breakdowns,models=_scope_frames(bundle,scope)
    if breakdowns.empty:_no_data();return
    sec=_section_macro(breakdowns)
    if not sec.empty:
        st.markdown('<div class="ac-section">Macro por sección</div>',unsafe_allow_html=True)
        _decision_table(sec.rename(columns={'Sección macro':'Sección','VPD':'Sugerido'}),height=270)
    rub=breakdowns[breakdowns['Tipo'].eq('rubro')].copy()
    if rub.empty: st.info('Los PDF no contienen rubros para este alcance.'); return
    rub['Sección macro']=_section_values(rub)
    chosen=st.segmented_control('Sección',['Todas','Dama','Caballero','Infantil'],default='Todas',key='v61_rubro_sec') or 'Todas'
    if chosen!='Todas':rub=rub[rub['Sección macro'].eq(chosen)]
    summary=aggregate_pdf(rub,'Etiqueta').rename(columns={'Etiqueta':'Rubro','VPD':'Sugerido'})
    summary=summary.sort_values('Sugerido',ascending=False); summary.insert(0,'#',range(1,len(summary)+1))
    _decision_table(summary[[c for c in ['#','Rubro','Sugerido','Existencia','Piso','Bodega','DDI','Posiciones','Inversión','% Utilidad'] if c in summary]],height=520)
    st.caption('Los rubros se ordenan siempre de mayor a menor sugerido para facilitar la lectura comercial.')
    _render_model_rankings(models,'rubro_models')


def _area_name(text: str) -> str:
    t=str(text).upper()
    if 'LENC' in t:return 'Colgado Lencería'
    if 'MEZ' in t or 'JEAN' in t:return 'Jeans / Doblado Mezclilla'
    if 'DOBL' in t:return 'Doblado'
    if 'COLG' in t:return 'Colgado'
    return ''


def _page_location_v61(bundle: dict) -> None:
    _header("Ubicación / Área", "Áreas comerciales → mesas, racks y pasillos", bundle)
    scope=_global_scope(bundle); _breadcrumb(scope)
    _,breakdowns,models=_scope_frames(bundle,scope)
    if breakdowns.empty:
        st.info('El PDF no contiene ubicaciones para este alcance.'); return

    # Áreas publicadas directamente en la tabla Ventas por Ubicación de la página 1.
    loc=breakdowns[breakdowns['Tipo'].eq('location')].copy()
    if not loc.empty:
        loc['Área']=loc['Etiqueta'].map(_area_name)
        loc=loc[loc['Área'].ne('')]
    areas=['Todas','Doblado','Colgado','Jeans / Doblado Mezclilla','Colgado Lencería']
    area=st.segmented_control('Área',areas,default='Todas',key='v64_area') or 'Todas'
    area_filtered=loc if area=='Todas' else loc[loc['Área'].eq(area)]
    if area_filtered.empty:
        st.info(f"No hay información publicada para {area} en el alcance seleccionado.")
    else:
        area_summary=aggregate_pdf(area_filtered,'Área').rename(columns={'VPD':'Sugerido'}).sort_values('Sugerido',ascending=False)
        total_ex=float(pd.to_numeric(area_summary.get('Existencia',0),errors='coerce').sum())
        total_sug=float(pd.to_numeric(area_summary.get('Sugerido',0),errors='coerce').sum())
        total_floor=float(pd.to_numeric(area_summary.get('Piso',0),errors='coerce').sum())
        total_wh=float(pd.to_numeric(area_summary.get('Bodega',0),errors='coerce').sum())
        _kpis([('Sugerido',_number(total_sug),'Área seleccionada',CYAN),('Existencia',_number(total_ex),'Piezas',PURPLE),('Piso',_number(total_floor),f"{(total_floor/total_ex*100 if total_ex else 0):.1f}% existencia",GREEN),('Bodega',_number(total_wh),f"{(total_wh/total_ex*100 if total_ex else 0):.1f}% existencia",ORANGE)],4)
        area_summary.insert(0,'#',range(1,len(area_summary)+1))
        _decision_table(area_summary[[c for c in ['#','Área','Sugerido','Existencia','Piso','Bodega','DDI','Posiciones','% Utilidad'] if c in area_summary]],height=300)

    # Tabla de ubicaciones operativas. Mesa y Pasillo se toman del detalle
    # físico; Jeans y Lencería también aprovechan el corte por ubicación cuando
    # el PDF no publica una mesa/pasillo específico para esos grupos.
    st.markdown('<div class="ac-section">Ubicaciones físicas</div>',unsafe_allow_html=True)
    physical=breakdowns[breakdowns['Tipo'].eq('physical_location')].copy()
    location_rows=breakdowns[breakdowns['Tipo'].eq('location')].copy()

    physical_filter=st.segmented_control(
        'Filtrar ubicación física',
        ['Todas','Mesa','Pasillo','Jeans','Lencería'],
        default='Todas',
        key='v65_physical_filter'
    ) or 'Todas'

    detail_source=pd.DataFrame()
    if physical_filter in ('Todas','Mesa','Pasillo') and not physical.empty:
        ph=physical.copy()
        labels=ph.get('Etiqueta',pd.Series('',index=ph.index)).fillna('').astype(str)
        ph['Tipo físico']=np.select(
            [labels.str.contains('MESA',case=False,regex=False),labels.str.contains('PASIL',case=False,regex=False)],
            ['Mesa','Pasillo'],default='Otro'
        )
        if physical_filter!='Todas':
            ph=ph[ph['Tipo físico'].eq(physical_filter)]
        else:
            ph=ph[ph['Tipo físico'].isin(['Mesa','Pasillo'])]
        detail_source=ph

    if physical_filter in ('Jeans','Lencería'):
        src=physical.copy() if not physical.empty else pd.DataFrame()
        if not src.empty:
            sec=src.get('Sección detalle',pd.Series('',index=src.index)).fillna('').astype(str)
            pattern='JEAN|MEZ' if physical_filter=='Jeans' else 'LENC'
            src=src[sec.str.contains(pattern,case=False,regex=True,na=False)]
        if src.empty and not location_rows.empty:
            src=location_rows.copy()
            area_series=src.get('Etiqueta',pd.Series('',index=src.index)).map(_area_name)
            wanted='Jeans / Doblado Mezclilla' if physical_filter=='Jeans' else 'Colgado Lencería'
            src=src[area_series.eq(wanted)]
        detail_source=src

    if detail_source.empty:
        st.info(f'No hay registros publicados para {physical_filter} en el alcance seleccionado.')
    else:
        detail=aggregate_pdf(detail_source,'Etiqueta').rename(columns={'Etiqueta':'Ubicación','VPD':'Sugerido'})
        detail=detail.sort_values(['Sugerido','Existencia'],ascending=[False,False]).reset_index(drop=True)
        detail.insert(0,'#',range(1,len(detail)+1))
        _decision_table(detail[[c for c in ['#','Ubicación','Sugerido','Existencia','Piso','Bodega','DDI','Posiciones','% Utilidad'] if c in detail]],height=620)
        st.caption('Ordenado de mayor a menor sugerido. Mesa, Pasillo, Jeans y Lencería se consultan por separado.')

    # Modelos del alcance se mantienen disponibles debajo para bajar al detalle.
    _render_model_rankings(models,'area_models')


def _open_commercial_page(page: str) -> None:
    """Solicita navegación sin escribir sobre un widget ya creado."""
    st.session_state["nav_page"] = page
    st.session_state["nav_request"] = page


def _page_more(bundle: dict, is_admin: bool) -> None:
    """Centro compacto para las vistas secundarias de Planeación Comercial."""
    _header("Más opciones", "Utilidad, evolución, carga y acceso al portafolio", bundle)
    st.markdown(
        '<div class="ac-source-note">Las consultas principales permanecen en la barra inferior. '
        'Aquí se concentran las funciones de seguimiento y administración.</div>',
        unsafe_allow_html=True,
    )
    with st.container(key="commercial_more_actions"):
        left, right = st.columns(2, gap="medium")
        with left:
            st.markdown(
                '<div class="ac-more-card"><b>Dinero y utilidad</b><span>Participación, inversión identificada y comparativos.</span></div>',
                unsafe_allow_html=True,
            )
            if st.button("Abrir dinero y utilidad", key="more_profit", width="stretch", type="primary"):
                _open_commercial_page("Utilidad Comercial"); st.rerun()
        with right:
            st.markdown(
                '<div class="ac-more-card"><b>Mi evolución</b><span>Sugerido, inventario y DDI semana contra semana.</span></div>',
                unsafe_allow_html=True,
            )
            if st.button("Abrir mi evolución", key="more_history", width="stretch"):
                _open_commercial_page("Histórico Comercial"); st.rerun()

        admin_col, portfolio_col = st.columns(2, gap="medium")
        with admin_col:
            if is_admin:
                st.markdown(
                    '<div class="ac-more-card"><b>Carga semanal</b><span>Publica los PDF y valida las 17 tiendas.</span></div>',
                    unsafe_allow_html=True,
                )
                if st.button("Abrir carga PDF", key="more_upload", width="stretch"):
                    _open_commercial_page(ADMIN_PAGE); st.rerun()
            else:
                st.markdown(
                    '<div class="ac-more-card ac-more-card-muted"><b>Carga semanal</b><span>Disponible para Administrador.</span></div>',
                    unsafe_allow_html=True,
                )
        with portfolio_col:
            st.markdown(
                '<div class="ac-more-card"><b>Menú principal</b><span>Cambia entre Planeación Comercial y Muertos y Cambios.</span></div>',
                unsafe_allow_html=True,
            )
            if st.button("Volver al menú principal", key="more_portfolio", width="stretch"):
                st.session_state["active_app"] = None
                st.session_state["nav_page"] = "Inicio"
                st.session_state.pop("project_nav_selector", None)
                st.rerun()

def render_pdf_page(page: str, bundle: dict, is_admin: bool) -> None:
    # El alcance se conserva durante la navegación. Cada pantalla se renderiza
    # de forma exclusiva mediante su ruta, sin arrastrar contenido visual de la
    # pantalla anterior.
    st.session_state["commercial_active_pdf_page"] = page

    routes = {
        "Mi Tienda Comercial": _page_radiography,
        "Ventas Comerciales": _page_tiendas_v61,
        "Sugeridos Comerciales": _page_section_rubro_v61,
        "Modelos Comerciales": _page_location_v61,
        MORE_PAGE: lambda data: _page_more(data, is_admin),
        "Utilidad Comercial": _page_profit_focus,
        "Histórico Comercial": _page_store_evolution,
    }
    if page == ADMIN_PAGE:
        _page_upload(bundle, is_admin)
    elif page in routes:
        routes[page](bundle)
    else:
        st.error(f"La página comercial '{page}' no está registrada.")
