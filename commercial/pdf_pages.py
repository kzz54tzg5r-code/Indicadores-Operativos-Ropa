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
    labels = [PAGE_LABELS[page] for page in COMMERCIAL_PAGES]
    selected = st.radio(
        "Navegación comercial", labels, index=labels.index(PAGE_LABELS[active_page]),
        horizontal=True, label_visibility="collapsed", key=f"pdf_tabs_{active_page}",
    )
    target = {PAGE_LABELS[page]: page for page in COMMERCIAL_PAGES}[selected]
    if target != active_page:
        st.session_state["nav_page"] = target
        st.session_state["nav_request"] = target
        st.rerun()


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


def _page_summary(bundle: dict) -> None:
    _header("Análisis Comercial Semanal", "Resumen global construido exclusivamente con los PDF AC", bundle)
    _top_navigation("Resumen Comercial")
    week, store, _ = _scope(bundle, "pdf_summary")
    stores, breakdowns, _, _ = _current(bundle, week, store)
    if stores.empty:
        _no_data(); return
    total = _totals(stores)
    _kpis([
        ("IDs / artículos", _number(total["Modelos"]), "Detectados en PDF", BLUE),
        ("Curva", _number(total["Curva"]), "Inventario activo", PINK),
        ("Piso", _number(total["Piso"]), "Piezas exhibidas", GREEN),
        ("Bodega", _number(total["Bodega"]), "Piezas almacenadas", ORANGE),
        ("Existencia", _number(total["Existencia"]), "Piso + bodega", PURPLE),
        ("VPD / SUG 7", _number(total["VPD"]), "Promedio diario", CYAN),
        ("DDI", f'{total["DDI"]:,.0f} días', "Cobertura inventario", BLUE),
        ("DDC", f'{total["DDC"]:,.0f} días', "Cobertura curva", PINK),
    ], 8)
    critical = int(((stores["DDI"] > 0) & (stores["DDI"] <= 30)).sum())
    excess = int((stores["DDI"] > 120).sum())
    exit_pieces = breakdowns.loc[
        breakdowns["Tipo"].eq("catalog") & breakdowns["Etiqueta"].astype(str).str.upper().str.contains("DESCONT|PROXIMO"), "Existencia"
    ].sum() if not breakdowns.empty else 0
    st.markdown(
        f'<div class="ac-alert">⚠ {critical} tiendas con cobertura baja · {excess} con sobrecobertura · '
        f'{_number(exit_pieces)} piezas en catálogo de salida</div>', unsafe_allow_html=True,
    )
    trend = filter_period(bundle["stores_pdf"], store=store)
    trend = trend.groupby("Semana", as_index=False)[["Existencia", "VPD", "Curva"]].sum().sort_values("Semana")
    left, right = st.columns([1.55, .85], gap="medium")
    with left:
        fig = go.Figure()
        fig.add_scatter(x=trend["Semana"], y=trend["VPD"], mode="lines+markers+text", name="VPD", text=trend["VPD"].map(_number), textposition="top center", line=dict(color=BLUE, width=3), fill="tozeroy", fillcolor="rgba(21,91,239,.08)")
        fig.add_scatter(x=trend["Semana"], y=trend["Existencia"], mode="lines+markers", name="Existencia", yaxis="y2", line=dict(color=PINK, width=3))
        fig.update_layout(title="Evolución semanal de VPD y existencia", yaxis_title="VPD", yaxis2=dict(title="Existencia", overlaying="y", side="right"))
        _plot(fig, 315)
    with right:
        sections = _normalize_section(breakdowns[breakdowns["Tipo"].eq("section")])
        if not sections.empty:
            section = aggregate_pdf(sections, "Grupo")
            fig = go.Figure(go.Pie(labels=section["Grupo"], values=section["Existencia"], hole=.63, textinfo="percent", marker=dict(colors=[BLUE, "#17479E", PINK, CYAN])))
            fig.add_annotation(text=f'<b>{_number(section["Existencia"].sum())}</b><br>existencia', x=.5, y=.5, showarrow=False)
            fig.update_layout(title="Participación por sección")
            _plot(fig, 315)
    left, right = st.columns([.9, 1.5], gap="medium")
    with left:
        locations = business_location_summary(bundle["breakdowns"], week, store)
        if not locations.empty:
            chart = locations.sort_values("Existencia")
            fig = px.bar(chart, y="Ubicación", x="Existencia", orientation="h", text=chart["Existencia"].map(_number), color_discrete_sequence=[BLUE])
            fig.update_layout(title="Existencia por ubicación")
            _plot(fig, 305)
    with right:
        display = stores[["Tienda", "Modelos", "Existencia", "VPD", "DDI", "DDC", "Bodega %", "Score", "Estatus"]].head(10).copy()
        st.markdown('<div class="ac-section">Desempeño por tienda</div>', unsafe_allow_html=True)
        st.dataframe(display, width="stretch", height=305, hide_index=True, column_config={"DDI": st.column_config.NumberColumn(format="%.0f"), "DDC": st.column_config.NumberColumn(format="%.0f"), "Bodega %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%")})


def _page_stores(bundle: dict) -> None:
    _header("Comparativo de Tiendas", "Inventario, rotación y cobertura de las 17 tiendas", bundle)
    _top_navigation("Tiendas Comerciales")
    week, store, _ = _scope(bundle, "pdf_stores")
    stores = store_pdf_summary(bundle["stores_pdf"], week, store)
    if stores.empty: _no_data(); return
    total = _totals(stores)
    low = stores.loc[stores["DDI"].gt(0), "DDI"].min() if stores["DDI"].gt(0).any() else 0
    high = stores["DDI"].max()
    _kpis([
        ("Tiendas con datos", _number(stores["Tienda"].nunique()), "De 17", BLUE),
        ("Existencia", _number(total["Existencia"]), "Compañía / alcance", PURPLE),
        ("Bodega", _percent(total["Bodega"] / total["Existencia"] * 100 if total["Existencia"] else 0), "Participación", ORANGE),
        ("DDI compañía", f'{total["DDI"]:,.0f}', "Cobertura ponderada", GREEN),
        ("Menor DDI", f"{low:,.0f}", "Mayor urgencia", RED),
        ("Mayor DDI", f"{high:,.0f}", "Mayor exceso", PINK),
    ])
    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        metric = st.selectbox("Ordenar ranking por", ["VPD", "Existencia", "DDI", "DDC"], key="pdf_stores_metric")
        chart = stores.sort_values(metric)
        fig = px.bar(chart, y="Tienda", x=metric, orientation="h", text=chart[metric].map(_number), color_discrete_sequence=[BLUE])
        fig.update_layout(title=f"Ranking de tiendas por {metric}")
        _plot(fig, max(390, len(chart) * 31 + 100))
    with right:
        fig = px.scatter(stores, x="DDI", y="VPD", size="Existencia", color="Estatus", text="Tienda", color_discrete_map={"Óptimo": GREEN, "Atención": ORANGE, "Crítico": RED})
        fig.add_vrect(x0=31, x1=90, fillcolor="rgba(7,148,71,.08)", line_width=0)
        fig.update_traces(textposition="top center")
        fig.update_layout(title="Rotación vs. cobertura")
        _plot(fig, 430)
    st.dataframe(stores[["Tienda", "Modelos", "Curva", "Piso", "Bodega", "Existencia", "VPD", "DDI", "DDC", "Bodega %", "Score", "Estatus"]], width="stretch", height=440, hide_index=True)


def _page_inventory(bundle: dict) -> None:
    _header("Inventario y Cobertura", "Existencia actual, cobertura y proyección de consumo", bundle)
    _top_navigation("Inventario y Cobertura")
    week, store, _ = _scope(bundle, "pdf_inventory")
    stores, breakdowns, _, models = _current(bundle, week, store)
    if stores.empty: _no_data(); return
    total = _totals(stores)
    critical = stores[(stores["DDI"] > 0) & (stores["DDI"] <= 30)]
    excess = stores[stores["DDI"] > 120]
    exit_rows = breakdowns[breakdowns["Tipo"].eq("catalog") & breakdowns["Etiqueta"].astype(str).str.upper().str.contains("DESCONT|PROXIMO")]
    _kpis([
        ("Existencia", _number(total["Existencia"]), "Piezas", BLUE),
        ("Piso", _number(total["Piso"]), "Exhibición", GREEN),
        ("Bodega", _number(total["Bodega"]), "Almacenada", ORANGE),
        ("DDI", f'{total["DDI"]:,.0f} días', "Cobertura ponderada", PURPLE),
        ("Cobertura baja", _number(len(critical)), "Tiendas hasta 30 días", RED),
        ("Sobrecobertura", _number(len(excess)), "Tiendas >120 días", PINK),
        ("Catálogo salida", _number(exit_rows.get("Existencia", pd.Series(dtype=float)).sum()), "Piezas", ORANGE),
    ], 7)
    labels = ["0-14", "15-30", "31-60", "61-90", "91-120", "120+"]
    bucket = pd.cut(stores["DDI"], [-.1, 14, 30, 60, 90, 120, np.inf], labels=labels)
    distribution = stores.assign(Cobertura=bucket).groupby("Cobertura", observed=False, as_index=False)["Existencia"].sum()
    projection = company_projection(stores)
    left, right = st.columns([1.15, 1], gap="medium")
    with left:
        fig = px.bar(distribution, x="Cobertura", y="Existencia", text="Existencia", color="Cobertura", color_discrete_sequence=[RED, ORANGE, GREEN, "#38A169", BLUE, PINK])
        fig.update_layout(title="Inventario por rango de cobertura", showlegend=False)
        _plot(fig, 370)
    with right:
        fig = go.Figure()
        fig.add_scatter(x=projection["Días"], y=projection["Existencia proyectada"], mode="lines+markers+text", text=projection["Existencia proyectada"].map(_number), line=dict(color=BLUE, width=3), fill="tozeroy", fillcolor="rgba(21,91,239,.08)")
        fig.update_layout(title="Proyección simple al ritmo VPD actual", xaxis_title="Días", yaxis_title="Existencia")
        _plot(fig, 370)
    if not models.empty:
        featured = models.sort_values(["Tienda", "ID_ART", "Ranking"]).drop_duplicates(["Tienda", "ID_ART"])
        risk = featured[(featured["VPD"].gt(0)) & ((featured["DDI"].le(30)) | (featured["DDI"].gt(120)))].sort_values("DDI")
        st.markdown('<div class="ac-section">Modelos destacados en los rankings PDF con cobertura a revisar</div>', unsafe_allow_html=True)
        st.caption("El detalle corresponde a los modelos publicados en los Top 40 del PDF; no representa el universo completo de artículos.")
        st.dataframe(risk[["Tienda", "ID_ART", "Modelo", "Marca", "Sección", "Rubro", "Existencia", "VPD", "DDI", "Escenario"]].head(40), width="stretch", height=420, hide_index=True)


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
    _header("Secciones y Categorías", "Dama, Caballero e Infantil con detalle de catálogo, categoría y rubro", bundle)
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
        ("Elementos", _number(summary[group_col].nunique()), selected_label, BLUE),
        ("IDs", _number(total.get("IDs", 0)), "Artículos", PINK),
        ("Existencia", _number(total.get("Existencia", 0)), "Piezas reportadas", PURPLE),
        ("VPD", _number(total.get("VPD", 0)), "Sugerido diario", CYAN),
        ("DDI", f'{total.get("Existencia", 0) / max(total.get("VPD", 0), 1):,.0f}', "Ponderado", ORANGE),
        ("Posiciones", _number(total.get("Posiciones", 0)), "Espacio", GREEN),
    ])
    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        chart = summary.head(20).sort_values("Existencia")
        fig = px.bar(chart, y=group_col, x="Existencia", orientation="h", text=chart["Existencia"].map(_number), color_discrete_sequence=[BLUE])
        fig.update_layout(title=f"Top {selected_label.lower()} por existencia")
        _plot(fig, max(380, len(chart) * 25 + 110))
    with right:
        fig = px.scatter(summary.head(50), x="DDI", y="VPD", size="Existencia", text=group_col, color="VPD/posición", color_continuous_scale=["#DCE8FF", BLUE, NAVY])
        fig.update_traces(textposition="top center")
        fig.update_layout(title="Rotación, cobertura y espacio")
        _plot(fig, 430)
    st.dataframe(summary, width="stretch", height=430, hide_index=True)


def _page_locations(bundle: dict) -> None:
    _header("Ubicaciones y Espacio", "Doblado, Colgado, Jeans y Lencería con productividad del espacio", bundle)
    _top_navigation("Ubicaciones y Espacio")
    week, store, _ = _scope(bundle, "pdf_locations")
    summary = business_location_summary(bundle["breakdowns"], week, store)
    if summary.empty: _no_data(); return
    colors = {"Doblado": BLUE, "Colgado": "#17479E", "Jeans": PINK, "Lencería": PURPLE}
    _kpis([(row["Ubicación"], _number(row.get("Existencia", 0)), f"VPD {row.get('VPD', 0):,.0f} · DDI {row.get('DDI', 0):,.0f}", colors.get(row["Ubicación"], BLUE)) for _, row in summary.iterrows()], 4)
    st.caption("Lencería se identifica por rubro en el PDF; no debe sumarse a las ubicaciones físicas como si fuera un grupo excluyente.")
    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        fig = go.Figure()
        fig.add_bar(x=summary["Ubicación"], y=summary["Existencia"], name="Existencia", marker_color=BLUE)
        fig.add_scatter(x=summary["Ubicación"], y=summary["VPD"], name="VPD", yaxis="y2", mode="lines+markers+text", text=summary["VPD"].map(_number), line=dict(color=PINK, width=3))
        fig.update_layout(title="Existencia y velocidad por ubicación", yaxis2=dict(overlaying="y", side="right", title="VPD"))
        _plot(fig, 390)
    with right:
        fig = px.scatter(summary, x="Posiciones", y="VPD", size="Existencia", color="Ubicación", text="Ubicación", color_discrete_map=colors)
        fig.update_traces(textposition="top center")
        fig.update_layout(title="Productividad del espacio")
        _plot(fig, 390)
    st.dataframe(summary[["Ubicación", "Origen", "IDs", "Curva", "Piso", "Bodega", "Existencia", "VPD", "DDI", "DDC", "Posiciones", "VPD/posición"]], width="stretch", hide_index=True)


def _page_brands(bundle: dict) -> None:
    _header("Marcas y Catálogo", "Ranking de marcas por utilidad, velocidad, inventario y espacio", bundle)
    _top_navigation("Marcas y Catálogo")
    week, store, _ = _scope(bundle, "pdf_brands")
    brands = filter_period(bundle["brands"], week, store)
    if brands.empty: _no_data(); return
    scopes = sorted(brands["Alcance marca"].dropna().astype(str).unique())
    scope = st.segmented_control("Alcance de marca", scopes, default=scopes[0], key="pdf_brands_brand_scope")
    brands = brands[brands["Alcance marca"].eq(scope)].copy()
    metric = st.selectbox("Ranking por", ["% Utilidad", "VPD", "Existencia", "DDI", "Posiciones"], key="pdf_brands_metric")
    top = brands.sort_values(metric, ascending=False).head(20)
    utility_top = brands.sort_values("% Utilidad", ascending=False).iloc[0]
    _kpis([
        ("Marcas capturadas", _number(brands["Marca"].nunique()), scope, BLUE),
        ("Líder utilidad", utility_top["Marca"], _percent(utility_top["% Utilidad"]), GREEN),
        ("VPD", _number(brands["VPD"].sum()), "Top publicado", CYAN),
        ("Existencia", _number(brands["Existencia"].sum()), "Top publicado", PURPLE),
        ("DDI promedio", f'{brands["DDI"].replace(0, np.nan).mean():,.0f}', "Marcas capturadas", ORANGE),
        ("Posiciones", _number(brands["Posiciones"].sum()), "Espacio reportado", PINK),
    ])
    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        chart = top.sort_values(metric)
        fig = px.bar(chart, y="Marca", x=metric, orientation="h", text=chart[metric].map(lambda x: f"{x:,.1f}"), color_discrete_sequence=[BLUE])
        fig.update_layout(title=f"Top 20 marcas por {metric}")
        _plot(fig, 510)
    with right:
        fig = px.scatter(brands, x="Existencia", y="VPD", size="IDs", color="% Utilidad", text="Marca", color_continuous_scale=[PINK, BLUE, NAVY])
        fig.update_traces(textposition="top center")
        fig.update_layout(title="Inventario, velocidad y utilidad")
        _plot(fig, 430)
    st.caption("% Utilidad es el porcentaje publicado en el reporte; no representa utilidad monetaria total.")
    st.dataframe(brands[["Ranking", "Marca", "Alcance marca", "% Utilidad", "IDs", "Curva", "Piso", "Bodega", "Existencia", "VPD", "DDI", "DDC", "Posiciones"]], width="stretch", height=430, hide_index=True)


def _page_models(bundle: dict) -> None:
    _header("Análisis de Modelos", "Top 20 campeones y modelos lentos según los rankings publicados", bundle)
    _top_navigation("Modelos")
    week, store, scenario = _scope(bundle, "pdf_models", scenario=True)
    models = filter_period(bundle["models_pdf"], week, store)
    models = models[models["Escenario"].eq(scenario)].copy()
    if models.empty: _no_data(); return
    sections = ["Todas"] + sorted(models["Sección"].dropna().astype(str).unique())
    selected_section = st.segmented_control("Sección", sections, default="Todas", key="pdf_models_section")
    if selected_section != "Todas": models = models[models["Sección"].eq(selected_section)]
    top = models.sort_values(["Ranking", "Tienda"]).head(20)
    total = top.sum(numeric_only=True)
    top_brand = top["Marca"].mode().iat[0] if not top["Marca"].mode().empty else "—"
    _kpis([
        ("Modelos en ranking", _number(models["ID_ART"].nunique()), scenario, BLUE),
        ("Existencia Top 20", _number(total.get("Existencia", 0)), "Piso + bodega", PURPLE),
        ("VPD Top 20", _number(total.get("VPD", 0)), "Sugerido diario", CYAN),
        ("DDI promedio", f'{top["DDI"].replace(0, np.nan).mean():,.0f}', "Top mostrado", ORANGE),
        ("Marca frecuente", top_brand, "Top mostrado", PINK),
        ("Inversión Top 20", _money(total.get("Inversión", 0)) if scenario.lower().startswith("invers") else "N/D", "Sólo ranking inversión", GREEN),
    ])
    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        chart = top.sort_values("VPD")
        labels = chart["Modelo"].where(chart["Modelo"].astype(str).ne(""), chart["ID_ART"].astype(str))
        fig = px.bar(chart.assign(Etiqueta=labels), y="Etiqueta", x="VPD", orientation="h", text=chart["VPD"].map(_number), color="DDI", color_continuous_scale=[GREEN, ORANGE, PINK])
        fig.update_layout(title=f"Top 20 · {scenario}")
        _plot(fig, 520)
    with right:
        fig = px.scatter(top, x="DDI", y="VPD", size="Existencia", color="Sección", hover_name="Modelo", text="Ranking")
        fig.add_vrect(x0=31, x1=90, fillcolor="rgba(7,148,71,.08)", line_width=0)
        fig.update_layout(title="Velocidad y cobertura")
        _plot(fig, 430)
    st.caption("Los modelos mostrados corresponden a los Top 40 impresos en el PDF por sección y escenario.")
    columns = ["Ranking", "Tienda", "Sección", "ID_ART", "Modelo", "Color", "Marca", "Rubro", "Piso", "Bodega", "Existencia", "VPD", "DDI", "DDC"]
    if scenario.lower().startswith("invers"): columns.append("Inversión")
    st.dataframe(top[columns], width="stretch", height=530, hide_index=True)


def _page_opportunities(bundle: dict) -> None:
    _header("Oportunidades y Acciones", "Alertas accionables derivadas del inventario, cobertura y rankings PDF", bundle)
    _top_navigation("Oportunidades y Acciones")
    week, store, _ = _scope(bundle, "pdf_opportunities")
    stores, breakdowns, _, models = _current(bundle, week, store)
    data = pdf_opportunities(stores, breakdowns, models)
    if data.empty:
        st.success("No se detectaron oportunidades con los criterios actuales."); return
    _kpis([
        ("Acciones", _number(len(data)), "Detectadas", BLUE),
        ("Alta prioridad", _number(data["Prioridad"].eq("Alta").sum()), "Atención inmediata", RED),
        ("Resurtido", _number(data["Oportunidad"].eq("Riesgo de agotamiento").sum()), "Cobertura baja", GREEN),
        ("Sobrecobertura", _number(data["Oportunidad"].eq("Sobrecobertura").sum()), "Revisar exceso", PINK),
        ("Transferencias", _number(data["Oportunidad"].eq("Transferencia entre tiendas").sum()), "Entre sucursales", PURPLE),
        ("Catálogo salida", _number(data["Oportunidad"].eq("Catálogo de salida").sum()), "Liberar espacio", ORANGE),
    ])
    left, right = st.columns([1.55, 1], gap="medium")
    with left:
        display = data.copy()
        display["Piezas"] = display["Piezas"].round(0)
        display["Confianza"] = display["Confianza"].map(lambda value: f"{value:.0f}%")
        st.dataframe(display, width="stretch", height=520, hide_index=True)
    with right:
        counts = data.groupby("Oportunidad", as_index=False).size()
        fig = px.pie(counts, names="Oportunidad", values="size", hole=.58, color_discrete_sequence=[BLUE, GREEN, ORANGE, PINK, PURPLE])
        fig.update_layout(title="Acciones por tipo")
        _plot(fig, 390)
        priority = data.groupby("Prioridad", as_index=False)["Piezas"].sum()
        st.dataframe(priority, width="stretch", hide_index=True)
    st.caption("Las piezas sugeridas son una recomendación operativa basada en VPD y cobertura; no se calcula impacto monetario sin el archivo de ventas.")


def _page_history(bundle: dict) -> None:
    _header("Histórico Comercial", "Evolución semanal y trazabilidad de los PDF", bundle)
    _top_navigation("Histórico Comercial")
    history = bundle["stores_pdf"].copy()
    if history.empty: _no_data(); return
    week = _latest_week(history["Semana"])
    current = history[history["Semana"].eq(week)]
    total = _totals(current)
    _kpis([
        ("Semana actual", week, "Último corte", BLUE),
        ("PDF", _number(len(current)), "Archivos", GREEN),
        ("Tiendas", _number(current["Tienda"].nunique()), "De 17", BLUE),
        ("Existencia", _number(total["Existencia"]), "Piso + bodega", PURPLE),
        ("VPD", _number(total["VPD"]), "Sugerido diario", CYAN),
        ("DDI", f'{total["DDI"]:,.0f}', "Ponderado", ORANGE),
        ("Cobertura", _percent(current["Tienda"].nunique() / 17 * 100), "PDF esperados", PINK),
    ], 7)
    pivot = history.assign(Disponible="✓").pivot_table(index="Tienda", columns="Semana", values="Disponible", aggfunc="first", fill_value="—")
    trend = history.groupby("Semana", as_index=False)[["Existencia", "VPD", "Curva"]].sum().sort_values("Semana")
    left, right = st.columns([1.2, 1], gap="medium")
    with left:
        st.markdown('<div class="ac-section">Cobertura de PDF por tienda</div>', unsafe_allow_html=True)
        st.dataframe(pivot, width="stretch", height=390)
    with right:
        fig = go.Figure()
        fig.add_scatter(x=trend["Semana"], y=trend["Existencia"], mode="lines+markers", name="Existencia", line=dict(color=BLUE, width=3))
        fig.add_scatter(x=trend["Semana"], y=trend["VPD"], mode="lines+markers", name="VPD", yaxis="y2", line=dict(color=PINK, width=3))
        fig.update_layout(title="Evolución histórica", yaxis2=dict(overlaying="y", side="right"))
        _plot(fig, 390)
    st.markdown('<div class="ac-section">Historial de cortes</div>', unsafe_allow_html=True)
    st.dataframe(history.sort_values(["Semana", "Tienda"], ascending=[False, True]), width="stretch", height=430, hide_index=True)


def _page_upload(bundle: dict, is_admin: bool) -> None:
    _header("Carga de PDF", "Carga semanal de hasta 17 reportes AC; el histórico se conserva", bundle)
    if not is_admin:
        st.error("Esta pestaña está disponible únicamente para Administrador o Propietario."); return
    flash = st.session_state.pop("commercial_upload_flash", None)
    if flash:
        getattr(st, flash[0])(flash[1])
    st.markdown('<div class="ac-source-note">Esta versión utiliza únicamente los PDF semanales. No solicita archivos de ventas ni capacidades.</div>', unsafe_allow_html=True)
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
        st.metric("Periodo seleccionado", week_key)
        st.caption("El sistema también valida la fecha impresa dentro de cada PDF.")
    with right:
        uploads = st.file_uploader("Selecciona hasta 17 PDF de tiendas", type=["pdf"], accept_multiple_files=True, key="commercial_pdf_uploads")
        if uploads and len(uploads) > 17:
            st.error("Selecciona un máximo de 17 PDF por corte.")
        if st.button("Guardar y procesar PDF", disabled=not uploads or len(uploads) > 17, type="primary", width="stretch"):
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
    _kpis([
        ("PDF recibidos", _number(len(current)), current_week, GREEN),
        ("Tiendas reconocidas", _number(len(stores)), "De 17", BLUE),
        ("IDs detectados", _number(records), "Suma reportada", PINK),
        ("Pendientes", _number(len(missing)), ", ".join(missing[:3]) or "Completo", ORANGE),
        ("Errores", _number((pdfs.get("status", pd.Series(dtype=str)) == "Error").sum()), "Validación", RED),
        ("Cobertura", _percent(len(stores) / 17 * 100), "Semana actual", GREEN),
    ])
    if not current.empty:
        columns = [column for column in ("store", "name", "week", "report_date", "records", "pages", "status", "uploaded_at") if column in current]
        st.markdown('<div class="ac-section">Archivos PDF del último corte</div>', unsafe_allow_html=True)
        st.dataframe(current[columns].sort_values(["store", "name"]), width="stretch", height=410, hide_index=True)
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
