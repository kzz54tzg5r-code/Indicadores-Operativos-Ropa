"""Pantallas Streamlit del módulo Ventas y Análisis Comercial."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import re

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from .analytics import snapshots_to_frames
from .config import ADMIN_PAGE, COMMERCIAL_PAGES, PAGE_LABELS, PROJECT_STORES, ensure_directories
from .parsers import PDF_PARSER_VERSION, extract_pdf_snapshot
from .pdf_analytics import (
    aggregate_pdf,
    business_location_summary,
    company_projection,
    filter_period,
    pdf_opportunities,
    snapshots_to_pdf_frames,
    store_pdf_summary,
)
from .storage import (
    build_history_backup,
    cloud_enabled,
    load_manifest,
    load_snapshots,
    resolve_entry_path,
    restore_history_from_cloud,
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
MUTED = "#667085"


def _money(value) -> str:
    value = float(value or 0)
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.1f} M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:,.0f} mil"
    return f"${value:,.0f}"


def _number(value) -> str:
    return f"{float(value or 0):,.0f}"


def _percent(value) -> str:
    return f"{float(value or 0):,.1f}%"


def _latest_week(values) -> str:
    """Prioriza semanas ISO reales sobre etiquetas como 'Sin semana'."""
    clean = [str(value).strip() for value in values if str(value).strip()]
    iso_weeks = [value for value in clean if re.fullmatch(r"\d{4}-W\d{2}", value)]
    if iso_weeks:
        return max(iso_weeks)
    return max(clean) if clean else "Sin semana"


@st.cache_data(show_spinner=False)
def _cached_pdf(path_text: str, mtime: float) -> dict:
    return extract_pdf_snapshot(path_text)


def _load_bundle(existing_sales=None) -> dict:
    """Carga exclusivamente la información persistida de los PDF semanales."""
    ensure_directories()
    manifest = load_manifest()
    snapshot_cache = load_snapshots()
    snapshots = []
    for entry in manifest.get("pdfs", []):
        path = resolve_entry_path(entry)
        try:
            # Después de un reinicio de Streamlit, los PDF históricos pueden
            # permanecer sólo en el bucket privado. Su snapshot normalizado
            # conserva todas las métricas sin volver a descargar cada PDF.
            snapshot = snapshot_cache.get(str(entry.get("id")))
            if path.exists() and int((snapshot or {}).get("parser_version", 0)) < PDF_PARSER_VERSION:
                snapshot = _cached_pdf(str(path), path.stat().st_mtime)
                save_snapshot(entry["id"], snapshot)
            if not snapshot:
                continue
            snapshots.append(snapshot)
            if (
                entry.get("status") != snapshot.get("status")
                or entry.get("store") != snapshot.get("store")
                or entry.get("week") != snapshot.get("week")
                or entry.get("report_date") != snapshot.get("report_date")
                or entry.get("records") != snapshot.get("models")
            ):
                update_entry(
                    "pdfs", entry["id"], status=snapshot.get("status"), store=snapshot.get("store"),
                    week=snapshot.get("week"), report_date=snapshot.get("report_date"), pages=snapshot.get("pages"),
                    records=snapshot.get("models"),
                )
        except Exception as exc:
            if entry.get("status") != "Error":
                update_entry("pdfs", entry["id"], status="Error", error=str(exc)[:300])

    stores_pdf, sections_pdf, locations_pdf = snapshots_to_frames(snapshots)
    breakdowns, brands, models_pdf = snapshots_to_pdf_frames(snapshots)
    stores = store_pdf_summary(stores_pdf)
    return {
        "manifest": load_manifest(), "capacity": pd.DataFrame(), "sales": pd.DataFrame(), "models": models_pdf,
        "snapshots": snapshots, "stores_pdf": stores_pdf, "sections_pdf": sections_pdf,
        "locations_pdf": locations_pdf, "stores": stores, "breakdowns": breakdowns,
        "brands": brands, "models_pdf": models_pdf,
    }


def _inject_styles() -> None:
    # Marcador del módulo: permite que el CSS comercial gane por especificidad
    # a las capas heredadas V30/V31/V33 que ocultaban el sidebar global.
    st.markdown('<span class="ac-shell-marker" aria-hidden="true"></span>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <style>
        :root{{--ac-navy:{NAVY};--ac-blue:{BLUE};--ac-pink:{PINK};--ac-green:{GREEN};--ac-bg:#F4F7FB;}}
        .ac-header{{display:flex;align-items:center;justify-content:space-between;gap:16px;background:#fff;border:1px solid #E1E7F0;border-radius:15px;padding:14px 17px;margin:0 0 8px;box-shadow:0 5px 18px rgba(23,59,115,.055)}}
        .ac-title{{font-size:25px;font-weight:900;color:{NAVY};line-height:1.08}}.ac-subtitle{{font-size:12px;color:{MUTED};margin-top:5px}}
        .ac-status{{display:flex;gap:7px;align-items:center;flex-wrap:wrap;justify-content:flex-end}}.ac-pill{{border-radius:9px;padding:7px 10px;font-size:10.5px;font-weight:800;background:#E9F8F0;color:{GREEN}}}.ac-pill-blue{{background:#EAF2FF;color:{BLUE}}}.ac-updated{{font-size:10px;color:{MUTED};white-space:nowrap}}
        .ac-kpis{{display:grid;grid-template-columns:repeat(var(--columns,6),minmax(0,1fr));gap:8px;margin:10px 0 12px}}.ac-kpi{{background:#fff;border:1px solid #E1E7F0;border-radius:12px;padding:12px 11px;min-height:98px;box-shadow:0 3px 11px rgba(23,59,115,.04);position:relative;overflow:hidden}}.ac-kpi:before{{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--accent)}}.ac-kpi-label{{font-size:9px;text-transform:uppercase;letter-spacing:.35px;color:{MUTED};font-weight:850;white-space:nowrap}}.ac-kpi-value{{font-size:22px;font-weight:900;color:{NAVY};margin-top:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.ac-kpi-note{{font-size:9.5px;color:{MUTED};margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
        .ac-alert{{display:flex;align-items:center;gap:10px;border:1px solid #F8B8D2;background:#FFF4F8;color:{PINK};border-radius:11px;padding:11px 14px;margin:8px 0 14px;font-size:12px;font-weight:800}}.ac-section{{font-size:17px;font-weight:900;color:{NAVY};margin:8px 0 9px}}
        .ac-source-note{{background:#EAF2FF;border:1px solid #CADBFA;border-radius:10px;padding:10px 13px;color:{NAVY};font-size:11px;margin:8px 0 12px}}
        .ac-filter-caption{{font-size:10px;color:{MUTED};margin:-2px 0 4px}}
        div[data-testid="stRadio"] [role="radiogroup"]{{gap:6px!important;flex-wrap:wrap!important}}div[data-testid="stRadio"] [role="radiogroup"] label{{background:#fff;border:1px solid #D9E2EF;border-radius:999px;padding:7px 14px!important}}div[data-testid="stRadio"] [role="radiogroup"] label>div:first-child{{display:none!important}}div[data-testid="stRadio"] [role="radiogroup"] label:has(input:checked){{background:{BLUE}!important;color:#fff!important;border-color:{BLUE}!important}}
        [data-testid="stDataFrame"]{{border:1px solid #E1E7F0;border-radius:12px;overflow:hidden}}.stPlotlyChart{{border:1px solid #E1E7F0!important;border-radius:13px!important;background:#fff!important;box-shadow:none!important}}
        /* Shell lateral comercial. Los selectores deliberadamente incluyen el
           marcador para superar las reglas globales que usan !important. */
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) section[data-testid="stSidebar"]{{
          display:flex!important;visibility:visible!important;opacity:1!important;
          position:fixed!important;inset:0 auto 0 0!important;
          width:184px!important;min-width:184px!important;max-width:184px!important;
          height:100vh!important;flex:0 0 184px!important;transform:translateX(0)!important;
          background:linear-gradient(180deg,#0B326D 0%,#102E67 100%)!important;
          z-index:1500!important;overflow-y:auto!important;overflow-x:hidden!important;
          pointer-events:auto!important;
        }}
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) section[data-testid="stSidebar"] > div:first-child{{
          display:block!important;visibility:visible!important;opacity:1!important;
          position:relative!important;width:184px!important;min-width:184px!important;
          height:auto!important;min-height:100vh!important;padding:14px 10px!important;
          overflow:visible!important;box-sizing:border-box!important;
        }}
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) [data-testid="stMain"]{{
          margin-left:184px!important;width:calc(100% - 184px)!important;
          max-width:calc(100% - 184px)!important;padding-top:0!important;
        }}
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) [data-testid="stMainBlockContainer"],
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) .block-container{{
          width:100%!important;max-width:none!important;margin:0!important;
          padding:.55rem 1rem 2rem!important;box-sizing:border-box!important;
        }}
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) .v27-app-header,
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) .v30-project-context,
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) [data-testid="stHorizontalBlock"]:has([aria-label="Menú de Ventas y Análisis Comercial"]){{display:none!important;}}
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) section[data-testid="stSidebar"] h3,
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) section[data-testid="stSidebar"] p,
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) section[data-testid="stSidebar"] span{{color:#fff!important;}}
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) section[data-testid="stSidebar"] img{{background:#fff!important;border-radius:10px!important;padding:6px!important;margin:0 auto 8px!important;}}
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) section[data-testid="stSidebar"] h3{{font-size:17px!important;line-height:1.2!important;margin-top:8px!important;}}
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) section[data-testid="stSidebar"] .stButton>button{{
          display:flex!important;visibility:visible!important;opacity:1!important;width:100%!important;
          color:#fff!important;background:transparent!important;border:0!important;border-radius:10px!important;
          justify-content:flex-start!important;text-align:left!important;min-height:38px!important;padding:7px 9px!important;font-size:12px!important;
        }}
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) section[data-testid="stSidebar"] .stButton>button[kind="primary"]{{background:{BLUE}!important;box-shadow:0 5px 14px rgba(0,0,0,.15)!important;}}
        body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) section[data-testid="stSidebar"] .stButton>button:hover{{background:rgba(255,255,255,.12)!important;}}
        @media(max-width:1350px){{.ac-kpis{{grid-template-columns:repeat(4,minmax(0,1fr))!important}}}}@media(max-width:700px){{.ac-header{{align-items:flex-start;flex-direction:column}}.ac-title{{font-size:22px}}.ac-status{{justify-content:flex-start}}.ac-kpis{{grid-template-columns:repeat(2,minmax(0,1fr))!important}}}}@media(max-width:390px){{.ac-kpis{{grid-template-columns:1fr!important}}}}
        @media(max-width:900px){{
          body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) section[data-testid="stSidebar"]{{
            width:286px!important;min-width:286px!important;max-width:82vw!important;
            flex-basis:286px!important;transform:translateX(-100%)!important;z-index:1800!important;
          }}
          body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) section[data-testid="stSidebar"][aria-expanded="true"],
          body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) section[data-testid="stSidebar"][data-state="expanded"]{{transform:translateX(0)!important;}}
          body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) [data-testid="stMain"]{{margin-left:0!important;width:100%!important;max-width:100%!important;}}
          body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) [data-testid="stSidebarCollapsedControl"],
          body [data-testid="stAppViewContainer"]:has(.ac-shell-marker) [data-testid="collapsedControl"]{{display:flex!important;visibility:visible!important;opacity:1!important;z-index:1900!important;}}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_commercial_sidebar(active_page: str, is_admin: bool = False) -> None:
    sidebar_labels = {
        "Resumen Comercial": "Resumen",
        "Tiendas Comerciales": "Tiendas",
        "Inventario y Cobertura": "Inventario",
        "Secciones y Categorías": "Secciones",
        "Ubicaciones y Espacio": "Ubicaciones",
        "Marcas y Catálogo": "Marcas",
        "Modelos": "Modelos",
        "Oportunidades y Acciones": "Oportunidades",
        "Histórico Comercial": "Histórico",
    }
    sidebar_icons = {
        "Resumen Comercial": ":material/dashboard:",
        "Tiendas Comerciales": ":material/storefront:",
        "Inventario y Cobertura": ":material/inventory_2:",
        "Secciones y Categorías": ":material/category:",
        "Ubicaciones y Espacio": ":material/location_on:",
        "Marcas y Catálogo": ":material/loyalty:",
        "Modelos": ":material/emoji_events:",
        "Oportunidades y Acciones": ":material/bolt:",
        "Histórico Comercial": ":material/history:",
    }
    with st.sidebar:
        logo = Path(__file__).resolve().parents[1] / "assets" / "price_shoes_logo.png"
        if logo.exists():
            st.image(str(logo), width=105)
        st.markdown("### Ventas y Análisis")
        st.caption("Módulo comercial")
        for page_name in COMMERCIAL_PAGES:
            if st.button(
                sidebar_labels.get(page_name, PAGE_LABELS[page_name]), key=f"commercial_side_{page_name}",
                type="primary" if active_page == page_name else "secondary", width="stretch",
                icon=sidebar_icons.get(page_name),
            ):
                st.session_state["nav_page"] = page_name
                # El selector principal ya fue creado por legacy_app.py en esta
                # ejecución. La sincronización se solicita para el siguiente
                # ciclo, antes de que Streamlit vuelva a crear el widget.
                st.session_state["nav_request"] = page_name
                st.rerun()
        if is_admin:
            st.divider()
            if st.button("Carga PDF", key="commercial_side_upload", type="primary" if active_page == ADMIN_PAGE else "secondary", width="stretch", icon=":material/upload_file:"):
                st.session_state["nav_page"] = ADMIN_PAGE
                st.session_state["nav_request"] = ADMIN_PAGE
                st.rerun()
        st.divider()
        if st.button("Menú principal", key="commercial_back_home", width="stretch", icon=":material/arrow_back:"):
            st.session_state["active_app"] = None
            st.session_state["nav_page"] = "Inicio"
            st.rerun()


def _header(title: str, subtitle: str, bundle: dict) -> None:
    pdfs = bundle["manifest"].get("pdfs", [])
    current_week = _latest_week(item.get("week", "") for item in pdfs)
    current_pdfs = [item for item in pdfs if str(item.get("week", "")) == current_week]
    processed = sum(str(item.get("status")) == "Procesado" for item in current_pdfs)
    recognized = len({str(item.get("store", "")).strip() for item in current_pdfs if str(item.get("store", "")).strip()})
    updated = str(bundle["manifest"].get("updated_at", ""))[:16].replace("T", " · ") or "Sin actualización"
    coverage = f"{recognized} de 17" if current_week != "Sin semana" else str(processed)
    st.markdown(
        f"""
        <div class="ac-header"><div><div class="ac-title">{html.escape(title)}</div><div class="ac-subtitle">{html.escape(subtitle)}</div></div>
        <div class="ac-status"><span class="ac-pill">✓ {coverage} PDF procesados</span><span class="ac-pill ac-pill-blue">{html.escape(current_week)}</span><span class="ac-updated">Actualizado {html.escape(updated)}</span></div></div>
        """,
        unsafe_allow_html=True,
    )


def _top_navigation(active_page: str) -> None:
    labels = [PAGE_LABELS[page] for page in COMMERCIAL_PAGES]
    page_by_label = {PAGE_LABELS[page]: page for page in COMMERCIAL_PAGES}
    current_label = PAGE_LABELS.get(active_page, labels[0])
    selected = st.radio("Navegación comercial", labels, index=labels.index(current_label), horizontal=True, label_visibility="collapsed", key=f"commercial_tabs_{active_page}")
    selected_page = page_by_label[selected]
    if selected_page != active_page:
        st.session_state["nav_page"] = selected_page
        st.session_state["nav_request"] = selected_page
        st.rerun()


def _kpis(items, columns: int | None = None) -> None:
    blocks = []
    for label, value, note, color in items:
        blocks.append(
            f'<div class="ac-kpi" style="--accent:{color}"><div class="ac-kpi-label">{html.escape(str(label))}</div>'
            f'<div class="ac-kpi-value">{html.escape(str(value))}</div><div class="ac-kpi-note">{html.escape(str(note))}</div></div>'
        )
    column_count = columns or min(max(len(blocks), 1), 8)
    st.markdown(f'<div class="ac-kpis" style="--columns:{column_count}">' + "".join(blocks) + "</div>", unsafe_allow_html=True)


def _filters(bundle: dict, key: str):
    models = bundle["models"]
    stores = sorted(set(PROJECT_STORES) | set(bundle["stores"].get("Tienda", pd.Series(dtype=str)).dropna().astype(str)))
    sections = sorted(models["Sección"].dropna().astype(str).unique()) if not models.empty else ["Dama", "Caballero", "Infantil"]
    locations = sorted(models["Ubicación"].dropna().astype(str).unique()) if not models.empty else ["Doblado", "Colgado", "Jeans", "Lencería"]
    c1, c2, c3, c4 = st.columns([1.25, 1, 1, .8])
    with c1:
        store = st.selectbox("Alcance", ["Compañía"] + stores, key=f"{key}_store")
    with c2:
        section = st.selectbox("Sección", ["Todas"] + sections, key=f"{key}_section")
    with c3:
        location = st.selectbox("Ubicación", ["Todas"] + locations, key=f"{key}_location")
    with c4:
        scenario = st.selectbox("Escenario", ["Sugerido / VPD", "Utilidad"], key=f"{key}_scenario")
    filtered_models = models.copy()
    if not filtered_models.empty:
        if store != "Compañía":
            filtered_models = filtered_models[filtered_models["Tienda"].eq(store)]
        if section != "Todas":
            filtered_models = filtered_models[filtered_models["Sección"].eq(section)]
        if location != "Todas":
            filtered_models = filtered_models[filtered_models["Ubicación"].eq(location)]
    return store, section, location, scenario, filtered_models


def _clear_summary_filters() -> None:
    for state_key in ("summary_store", "summary_week", "summary_section", "summary_location", "summary_scenario"):
        st.session_state.pop(state_key, None)


def _summary_filters(bundle: dict):
    models = bundle["models"]
    data_stores = set(bundle["stores"].get("Tienda", pd.Series(dtype=str)).dropna().astype(str))
    data_stores |= set(bundle["stores_pdf"].get("Tienda", pd.Series(dtype=str)).dropna().astype(str))
    stores = sorted(data_stores)
    section_values = set(models.get("Sección", pd.Series(dtype=str)).dropna().astype(str))
    section_values |= set(bundle["sections_pdf"].get("Sección", pd.Series(dtype=str)).dropna().astype(str))
    sections = sorted(section_values)
    location_values = set(models.get("Ubicación", pd.Series(dtype=str)).dropna().astype(str))
    location_values |= set(bundle["locations_pdf"].get("Ubicación", pd.Series(dtype=str)).dropna().astype(str))
    locations = sorted(location_values)
    weeks = sorted({
        str(value).strip() for value in bundle["stores_pdf"].get("Semana", pd.Series(dtype=str))
        if re.fullmatch(r"\d{4}-W\d{2}", str(value).strip())
    }, reverse=True)
    week_options = weeks or ["Sin semana"]

    # Si el histórico cambió después de una carga, evita conservar una opción
    # antigua que ya no pertenece al selector.
    if st.session_state.get("summary_week") not in week_options:
        st.session_state.pop("summary_week", None)

    with st.container(border=True):
        st.markdown('<div class="ac-filter-caption">FILTROS DEL ANÁLISIS</div>', unsafe_allow_html=True)
        c1, c2, c3, c4, c5, c6 = st.columns([1.15, 1.2, 1, 1, .95, .58], vertical_alignment="bottom")
        with c1:
            store = st.selectbox("Alcance", ["Compañía"] + stores, key="summary_store")
        with c2:
            week = st.selectbox(
                "Semana PDF", week_options, key="summary_week",
                format_func=lambda value: value.replace("-W", " · Semana ") if "-W" in value else value,
            )
        with c3:
            section = st.selectbox("Sección", ["Todas"] + (sections or ["Dama", "Caballero", "Infantil"]), key="summary_section")
        with c4:
            location = st.selectbox("Ubicación", ["Todas"] + (locations or ["Doblado", "Colgado", "Jeans", "Lencería"]), key="summary_location")
        with c5:
            scenario = st.selectbox("Escenario", ["Sugerido / VPD", "Utilidad"], key="summary_scenario")
        with c6:
            st.button("Limpiar", icon=":material/filter_alt_off:", on_click=_clear_summary_filters, width="stretch")

    filtered_models = models.copy()
    if not filtered_models.empty:
        if store != "Compañía":
            filtered_models = filtered_models[filtered_models["Tienda"].eq(store)]
        if section != "Todas":
            filtered_models = filtered_models[filtered_models["Sección"].eq(section)]
        if location != "Todas":
            filtered_models = filtered_models[filtered_models["Ubicación"].eq(location)]
    return store, week, section, location, scenario, filtered_models


def _filtered_auxiliary(bundle: dict, store: str, section: str, location: str, week: str | None = None):
    """Aplica el mismo alcance a ventas y agregados extraídos de los PDF."""
    sales = bundle["sales"].copy()
    stores_pdf = bundle["stores_pdf"].copy()
    sections_pdf = bundle["sections_pdf"].copy()
    locations_pdf = bundle["locations_pdf"].copy()

    def filter_value(frame: pd.DataFrame, column: str, value: str, all_value: str):
        if frame.empty or value == all_value or column not in frame:
            return frame
        return frame[frame[column].astype(str).eq(value)].copy()

    sales = filter_value(sales, "Tienda", store, "Compañía")
    stores_pdf = filter_value(stores_pdf, "Tienda", store, "Compañía")
    sections_pdf = filter_value(sections_pdf, "Tienda", store, "Compañía")
    locations_pdf = filter_value(locations_pdf, "Tienda", store, "Compañía")
    if week and week != "Sin semana":
        stores_pdf = filter_value(stores_pdf, "Semana", week, "Todas")
        sections_pdf = filter_value(sections_pdf, "Semana", week, "Todas")
        locations_pdf = filter_value(locations_pdf, "Semana", week, "Todas")
    sales = filter_value(sales, "Sección", section, "Todas")
    sales = filter_value(sales, "Ubicación", location, "Todas")
    sections_pdf = filter_value(sections_pdf, "Sección", section, "Todas")
    locations_pdf = filter_value(locations_pdf, "Ubicación", location, "Todas")

    # El total de tienda del PDF no se mezcla con un filtro parcial de sección
    # o ubicación porque ese total representa toda la sucursal.
    if section != "Todas" or location != "Todas":
        stores_pdf = stores_pdf.iloc[0:0].copy()
    return sales, stores_pdf, sections_pdf, locations_pdf


def _plot(fig, height=380):
    fig.update_layout(
        height=height, margin=dict(l=24, r=20, t=48, b=35), paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="Arial", color=NAVY, size=11), legend=dict(orientation="h", y=1.12, x=0),
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "responsive": True})


def _empty_sources(bundle: dict) -> bool:
    return bundle["models"].empty and bundle["stores_pdf"].empty and bundle["sales"].empty


def _page_summary(bundle: dict) -> None:
    _header("Ventas y Análisis Comercial", "Resumen global de compañía", bundle)
    _top_navigation("Resumen Comercial")
    store, week, section_filter, location_filter, scenario, models = _summary_filters(bundle)
    sales, stores_pdf, sections_pdf, locations_pdf = _filtered_auxiliary(
        bundle, store, section_filter, location_filter, week=week
    )
    trend_sales, trend_stores_pdf, _, _ = _filtered_auxiliary(
        bundle, store, section_filter, location_filter
    )
    stores = store_summary(models, sales, stores_pdf)
    total_sales = float(stores["Venta $"].sum()) if not stores.empty else 0
    total_pieces = float(stores["Venta pzas"].sum()) if not stores.empty else 0
    total_inventory = float(stores["Existencia"].sum()) if not stores.empty else 0
    total_investment = float(stores["Inversión"].sum()) if not stores.empty else 0
    utility = float(stores["Utilidad $"].sum() / max(total_sales, 1) * 100) if not stores.empty else 0
    vpd = float(stores["VPD"].sum()) if not stores.empty else 0
    ddi = total_inventory / max(vpd, 1)
    _kpis([
        ("Venta $", _money(total_sales), "Venta disponible", BLUE),
        ("Venta pzas", _number(total_pieces), "Piezas vendidas", PINK),
        ("Utilidad", _percent(utility), "Precio vs. costo", GREEN),
        ("Inversión", _money(total_investment), "Existencia a costo", BLUE),
        ("Existencia", _number(total_inventory), "Piso + bodega", "#7C3AED"),
        ("Sugerido 7", _number(vpd * 7), "Piezas / 7 días", PINK),
        ("VPD", _number(vpd), "Promedio diario", CYAN),
        ("DDI", _number(ddi), "Días de inventario", ORANGE),
    ], columns=8)
    risks = opportunities(models)
    if not risks.empty:
        stopped = int((models.get("DDI", pd.Series(dtype=float)) > 90).sum()) if not models.empty else 0
        st.markdown(f'<div class="ac-alert">⚠ {len(risks):,} oportunidades detectadas · impacto potencial {_money(risks["Impacto $"].sum())} · {stopped:,} modelos con inversión detenida</div>', unsafe_allow_html=True)
    weekly = weekly_sales(trend_sales)
    section = section_summary(models, sections_pdf)
    location = location_summary(models, locations_pdf)
    left, right = st.columns([1.62, .88], gap="medium")
    with left:
        if not weekly.empty:
            weekly = weekly.copy()
            weekly["Venta M"] = weekly["Venta $"] / 1_000_000
            weekly["Utilidad estimada"] = utility
            fig = go.Figure()
            fig.add_scatter(x=weekly["Periodo"], y=weekly["Venta M"], mode="lines+markers+text", name="Venta $ (M)", text=weekly["Venta M"].map(lambda value: f"{value:.1f} M"), textposition="top center", line=dict(color=BLUE, width=3), fill="tozeroy", fillcolor="rgba(21,91,239,.08)")
            fig.add_scatter(x=weekly["Periodo"], y=weekly["Utilidad estimada"], mode="lines+markers", name="Utilidad estimada (%)", yaxis="y2", line=dict(color=PINK, width=3))
            fig.update_layout(title="Evolución semanal de venta y utilidad", yaxis=dict(title="Venta $ (M)"), yaxis2=dict(title="Utilidad %", overlaying="y", side="right", range=[0, max(50, utility * 1.35)]))
            _plot(fig, 315)
        elif not trend_stores_pdf.empty:
            pdf_trend = trend_stores_pdf.groupby("Semana", as_index=False)[["Existencia", "VPD"]].sum().sort_values("Semana")
            fig = go.Figure()
            fig.add_scatter(x=pdf_trend["Semana"], y=pdf_trend["VPD"], mode="lines+markers+text", name="VPD", text=pdf_trend["VPD"].map(_number), textposition="top center", line=dict(color=BLUE, width=3), fill="tozeroy", fillcolor="rgba(21,91,239,.08)")
            fig.add_scatter(x=pdf_trend["Semana"], y=pdf_trend["Existencia"], mode="lines+markers", name="Existencia", yaxis="y2", line=dict(color=PINK, width=3))
            fig.update_layout(title="Evolución semanal de VPD y existencia", yaxis=dict(title="VPD"), yaxis2=dict(title="Existencia", overlaying="y", side="right"))
            _plot(fig, 315)
        else:
            st.info("Carga los PDF semanales para iniciar la evolución histórica.")
    with right:
        if not section.empty:
            pdf_store_set = set(stores_pdf.get("Tienda", pd.Series(dtype=str)).dropna().astype(str))
            model_store_set = set(models.get("Tienda", pd.Series(dtype=str)).dropna().astype(str))
            sale_is_representative = section["Venta $"].sum() > 0 and (not pdf_store_set or pdf_store_set.issubset(model_store_set))
            value_col = "Venta $" if sale_is_representative else "Existencia"
            chart = section[pd.to_numeric(section[value_col], errors="coerce").fillna(0).gt(0)].copy()
            fig = go.Figure(go.Pie(labels=chart["Sección"], values=chart[value_col], hole=.64, sort=False, textinfo="percent", marker=dict(colors=[BLUE, "#17479E", PINK, CYAN])))
            total_label = _money(chart[value_col].sum()) if value_col == "Venta $" else _number(chart[value_col].sum())
            fig.add_annotation(text=f"<b>{total_label}</b><br><span style='font-size:10px'>{value_col}</span>", x=.5, y=.5, showarrow=False, font=dict(color=NAVY, size=13))
            fig.update_layout(title="Participación por sección", legend=dict(orientation="v", x=1.0, y=.85))
            _plot(fig, 315)
        else:
            st.info("Sin desglose de sección para el corte seleccionado.")
    left, right = st.columns([.98, 1.42], gap="medium")
    with left:
        if not location.empty:
            pdf_store_set = set(stores_pdf.get("Tienda", pd.Series(dtype=str)).dropna().astype(str))
            model_store_set = set(models.get("Tienda", pd.Series(dtype=str)).dropna().astype(str))
            sale_is_representative = location["Venta $"].sum() > 0 and (not pdf_store_set or pdf_store_set.issubset(model_store_set))
            value_col = "Venta $" if sale_is_representative else "Existencia"
            chart = location.sort_values(value_col)
            labels = chart[value_col].map(_money if value_col == "Venta $" else _number)
            fig = go.Figure(go.Bar(y=chart["Ubicación"], x=chart[value_col], orientation="h", marker_color=BLUE, text=labels, textposition="inside", insidetextanchor="end"))
            fig.update_layout(title=f"Desempeño por ubicación · {value_col}", xaxis_title=value_col, yaxis_title="")
            _plot(fig, 300)
    with right:
        if not stores.empty:
            order_col = "Venta $" if stores["Venta $"].sum() > 0 else "VPD"
            display = stores.sort_values(order_col, ascending=False).head(8)[["Tienda", "Venta $", "Utilidad %", "VPD", "DDI", "Existencia", "Score", "Estatus"]].copy()
            display.insert(0, "#", range(1, len(display) + 1))
            display["Venta $"] = display["Venta $"].map(_money)
            display["Utilidad %"] = display["Utilidad %"].map(_percent)
            display["VPD"] = display["VPD"].map(_number)
            display["DDI"] = display["DDI"].map(lambda value: f"{value:,.0f}")
            display["Existencia"] = display["Existencia"].map(_number)
            st.markdown('<div class="ac-section">Desempeño por tienda</div>', unsafe_allow_html=True)
            table_height = min(324, 39 + len(display) * 35)
            st.dataframe(display, width="stretch", height=table_height, hide_index=True)


def _page_stores(bundle: dict) -> None:
    _header("Comparativo de Tiendas", "Desempeño comercial de las 17 tiendas", bundle)
    _top_navigation("Tiendas Comerciales")
    store, section_filter, location_filter, _, models = _filters(bundle, "stores")
    sales, stores_pdf, _, _ = _filtered_auxiliary(bundle, store, section_filter, location_filter)
    stores = store_summary(models, sales, stores_pdf)
    if stores.empty:
        st.info("Carga capacidades, ventas o PDF para comparar tiendas.")
        return
    leader = stores.iloc[0]
    _kpis([
        ("Venta compañía", _money(stores["Venta $"].sum()), "Ventas cargadas", BLUE),
        ("Utilidad", _percent(stores["Utilidad $"].sum() / max(stores["Venta $"].sum(), 1) * 100), "Estimada", GREEN),
        ("Tienda líder", leader["Tienda"], _money(leader["Venta $"]), BLUE),
        ("Inversión", _money(stores["Inversión"].sum()), "Existencia a costo", PINK),
        ("Tiendas con datos", _number(stores["Tienda"].nunique()), "De 17", ORANGE),
        ("Tiendas en atención", _number((stores["Estatus"] != "Óptimo").sum()), "Según score", RED),
    ])
    left, right = st.columns([1.55, 1])
    with left:
        chart = stores.sort_values("Venta $")
        fig = go.Figure(go.Bar(y=chart["Tienda"], x=chart["Venta $"], orientation="h", marker_color=BLUE, text=chart["Venta $"].map(_money), textposition="outside"))
        fig.update_layout(title="Ranking de tiendas por venta")
        _plot(fig, max(390, len(chart) * 35 + 100))
    with right:
        fig = px.scatter(stores, x="Inversión", y="Venta $", size="Existencia", color="Estatus", text="Tienda", color_discrete_map={"Óptimo": GREEN, "Atención": ORANGE, "Crítico": RED})
        fig.update_traces(textposition="top center")
        fig.update_layout(title="Venta vs. inversión")
        _plot(fig, 430)
    display = stores.copy()
    display["Venta $"] = display["Venta $"].map(_money)
    display["Inversión"] = display["Inversión"].map(_money)
    display["Utilidad %"] = display["Utilidad %"].map(_percent)
    st.markdown('<div class="ac-section">Indicadores por tienda</div>', unsafe_allow_html=True)
    st.dataframe(display[["Tienda", "Venta $", "Utilidad %", "VPD", "DDI", "Existencia", "Inversión", "Score", "Estatus"]], width="stretch", height=420, hide_index=True)


def _page_locations(bundle: dict) -> None:
    _header("Análisis por Ubicación y Sección", "Doblado, Colgado, Jeans y Lencería", bundle)
    _top_navigation("Ubicaciones y Secciones")
    store, section_filter, location_filter, _, models = _filters(bundle, "locations")
    _, _, sections_pdf, locations_pdf = _filtered_auxiliary(bundle, store, section_filter, location_filter)
    locations = location_summary(models, locations_pdf)
    sections = section_summary(models, sections_pdf)
    if locations.empty:
        st.info("No hay información de ubicación disponible.")
        return
    cards = []
    colors = {"Doblado": BLUE, "Colgado": "#17479E", "Jeans": PINK, "Lencería": "#7C3AED"}
    for _, row in locations.iterrows():
        cards.append((row["Ubicación"], _money(row["Venta $"]) if row["Venta $"] else _number(row["Existencia"]), f"{int(row['Modelos']):,} modelos · DDI {row.get('DDI', 0):.0f}", colors.get(row["Ubicación"], BLUE)))
    _kpis(cards[:6])
    left, right = st.columns([1.35, 1])
    with left:
        matrix = models.pivot_table(index="Sección", columns="Ubicación", values="Venta $" if not models.empty and models["Venta $"].sum() else "Existencia", aggfunc="sum", fill_value=0) if not models.empty else pd.DataFrame()
        if not matrix.empty:
            fig = px.imshow(matrix, text_auto=".2s", aspect="auto", color_continuous_scale=["#EDF3FF", BLUE, NAVY])
            fig.update_layout(title="Participación por sección y ubicación")
            _plot(fig, 390)
        elif not sections.empty:
            st.dataframe(sections, width="stretch", hide_index=True)
    with right:
        metric = "Venta $" if locations["Venta $"].sum() else "Existencia"
        fig = px.bar(locations.sort_values(metric), y="Ubicación", x=metric, orientation="h", color="Utilidad %" if "Utilidad %" in locations else None, color_continuous_scale=["#F5B3D1", BLUE])
        fig.update_layout(title="Desempeño por ubicación")
        _plot(fig, 390)
    display = locations.copy()
    display["Venta $"] = display["Venta $"].map(_money)
    display["Inversión"] = display["Inversión"].map(_money)
    display["Utilidad %"] = display["Utilidad %"].map(_percent)
    st.dataframe(display, width="stretch", hide_index=True, height=350)


def _page_models(bundle: dict) -> None:
    _header("Análisis de Modelos", "Campeones, lentos y oportunidades por inversión", bundle)
    _top_navigation("Modelos")
    _, _, _, scenario, models = _filters(bundle, "models")
    ranked = rank_models(models, scenario)
    if ranked.empty:
        st.info("Carga el archivo de capacidades para analizar modelos.")
        return
    champions = ranked[ranked["Estado modelo"].eq("Campeón")]
    slow = ranked[ranked["Estado modelo"].eq("Lento")]
    risk = ranked[ranked["Estado modelo"].eq("En riesgo")]
    _kpis([
        ("Modelos analizados", _number(ranked["Modelo"].nunique()), "Alcance filtrado", BLUE),
        ("Campeones", _number(champions["Modelo"].nunique()), scenario, GREEN),
        ("Lentos", _number(slow["Modelo"].nunique()), "DDI mayor a 90", PINK),
        ("En riesgo", _number(risk["Modelo"].nunique()), "Agotamiento o sin venta", RED),
        ("Inversión campeones", _money(champions["Inversión"].sum()), "Existencia a costo", BLUE),
        ("Inversión detenida", _money(slow["Inversión"].sum()), "Modelos lentos", ORANGE),
    ])
    tab1, tab2, tab3, tab4 = st.tabs(["Campeones", "Lentos", "En riesgo", "Ficha de modelo"])
    columns = ["Tienda", "Modelo", "Marca", "Sección", "Ubicación", "Venta pzas", "Venta $", "VPD", "Utilidad %", "Existencia", "Inversión", "DDI"]
    with tab1:
        st.dataframe(champions[columns].head(20), width="stretch", height=520, hide_index=True)
    with tab2:
        st.dataframe(slow.sort_values("Inversión", ascending=False)[columns].head(20), width="stretch", height=520, hide_index=True)
    with tab3:
        st.dataframe(risk.sort_values("DDI")[columns].head(20), width="stretch", height=520, hide_index=True)
    with tab4:
        selected_model = st.selectbox("Modelo", ranked["Modelo"].drop_duplicates().tolist())
        detail = ranked[ranked["Modelo"].eq(selected_model)]
        total = detail.sum(numeric_only=True)
        _kpis([
            ("Venta pzas", _number(total.get("Venta pzas", 0)), selected_model, BLUE),
            ("Venta $", _money(total.get("Venta $", 0)), "Acumulado", PINK),
            ("VPD", _number(total.get("VPD", 0)), "Sugerido", GREEN),
            ("Existencia", _number(total.get("Existencia", 0)), "Piso + bodega", "#7C3AED"),
            ("Inversión", _money(total.get("Inversión", 0)), "A costo", ORANGE),
            ("Utilidad", _percent(detail["Utilidad %"].mean()), "Estimada", GREEN),
        ])
        st.dataframe(detail[columns], width="stretch", hide_index=True)
    fig = px.scatter(ranked.head(500), x="Inversión", y="Venta $", size="Existencia", color="Estado modelo", hover_name="Modelo", color_discrete_map={"Campeón": GREEN, "Lento": PINK, "En riesgo": ORANGE})
    fig.update_layout(title="Venta vs. inversión por modelo")
    _plot(fig, 430)


def _page_inventory(bundle: dict) -> None:
    _header("Inventario y Cobertura", "Existencia, agotamientos y sobreinventario por modelo", bundle)
    _top_navigation("Inventario y Cobertura")
    _, _, _, _, models = _filters(bundle, "inventory")
    if models.empty:
        st.info("Carga el archivo de capacidades para analizar inventario.")
        return
    buckets = inventory_buckets(models)
    critical = models[models["DDI"].le(14) & models["VPD"].gt(0)]
    excess = models[models["DDI"].gt(90)]
    avg_ddi = models["Existencia"].sum() / max(models["VPD"].sum(), 1)
    _kpis([
        ("Existencia", _number(models["Existencia"].sum()), "Piezas", BLUE),
        ("Inversión", _money(models["Inversión"].sum()), "A costo", BLUE),
        ("Cobertura promedio", f"{avg_ddi:,.0f} días", "Meta 60-90", GREEN),
        ("Agotamiento próximo", _number(critical["Modelo"].nunique()), "Hasta 14 días", RED),
        ("Sobreinventario", _number(excess["Modelo"].nunique()), "Más de 90 días", ORANGE),
        ("Inversión detenida", _money(excess["Inversión"].sum()), "Modelos en exceso", PINK),
    ])
    left, right = st.columns([1.45, 1])
    with left:
        coverage = models.nlargest(20, "Inversión").sort_values("DDI")
        fig = px.bar(coverage, y="Modelo", x="DDI", orientation="h", color="DDI", color_continuous_scale=[RED, ORANGE, GREEN, PINK], hover_data=["Tienda", "Existencia", "VPD"])
        fig.add_vrect(x0=60, x1=90, fillcolor="rgba(7,148,71,.08)", line_width=0, annotation_text="Meta")
        fig.update_layout(title="Cobertura de inventario por modelo")
        _plot(fig, 520)
    with right:
        fig = px.pie(buckets, names="Estado", values="Existencia", hole=.58, color="Estado", color_discrete_map={"Crítico (0-14 días)": RED, "Bajo (15-30 días)": ORANGE, "Saludable (31-90 días)": GREEN, "Exceso (+90 días)": PINK})
        fig.update_layout(title="Distribución por cobertura")
        _plot(fig, 390)
        st.dataframe(buckets, width="stretch", hide_index=True, height=220)
    columns = ["Tienda", "Modelo", "Marca", "Sección", "Ubicación", "VPD", "Existencia", "DDI", "Inversión"]
    st.markdown('<div class="ac-section">Modelos con riesgo de agotamiento</div>', unsafe_allow_html=True)
    st.dataframe(critical.sort_values(["DDI", "VPD"], ascending=[True, False])[columns].head(30), width="stretch", height=430, hide_index=True)


def _page_opportunities(bundle: dict) -> None:
    _header("Oportunidades y Acciones", "Recomendaciones comerciales priorizadas por impacto", bundle)
    _top_navigation("Oportunidades y Acciones")
    _, _, _, _, models = _filters(bundle, "opportunities")
    data = opportunities(models)
    if data.empty:
        st.success("No se detectaron oportunidades con los filtros actuales.")
        return
    high = data[data["Prioridad"].eq("Alta")]
    _kpis([
        ("Impacto potencial", _money(data["Impacto $"].sum()), "Estimado", BLUE),
        ("Alta prioridad", _number(len(high)), "Atención inmediata", PINK),
        ("Resurtidos", _number(data["Oportunidad"].eq("Riesgo de agotamiento").sum()), "Sugeridos", GREEN),
        ("Transferencias", _number(data["Oportunidad"].eq("Sobrestock").sum()), "Por exceso", BLUE),
        ("Precio/ubicación", _number(data["Oportunidad"].eq("Baja utilidad").sum()), "Revisiones", ORANGE),
        ("Acciones activas", _number(len(data)), "Plan semanal", "#7C3AED"),
    ])
    st.markdown(f'<div class="ac-alert">⚠ {len(high)} acciones de alta prioridad representan {_money(high["Impacto $"].sum())}</div>', unsafe_allow_html=True)
    left, right = st.columns([1.55, 1])
    with left:
        st.markdown('<div class="ac-section">Oportunidades priorizadas</div>', unsafe_allow_html=True)
        display = data.head(50).copy()
        display["Impacto $"] = display["Impacto $"].map(_money)
        display["Confianza"] = display["Confianza"].map(lambda value: f"{value:.0f}%")
        st.dataframe(display, width="stretch", height=470, hide_index=True)
    with right:
        impact = data.groupby("Oportunidad", as_index=False)["Impacto $"].sum()
        fig = px.pie(impact, names="Oportunidad", values="Impacto $", hole=.58, color_discrete_sequence=[BLUE, GREEN, ORANGE, PINK])
        fig.update_layout(title="Impacto por tipo")
        _plot(fig, 390)
        status = data.groupby("Estatus", as_index=False).size()
        st.dataframe(status, width="stretch", hide_index=True)


def _page_forecast(bundle: dict) -> None:
    _header("Pronóstico Comercial", "Proyección de venta, utilidad e inventario", bundle)
    _top_navigation("Pronóstico Comercial")
    store, section_filter, location_filter, scenario, models = _filters(bundle, "forecast")
    sales, _, _, _ = _filtered_auxiliary(bundle, store, section_filter, location_filter)
    horizon = st.segmented_control("Horizonte", [4, 8, 12], default=12, format_func=lambda value: f"{value} semanas", key="commercial_horizon") or 12
    multiplier = 1.0 if scenario == "Sugerido / VPD" else 1.04
    projection = forecast(models, sales, weeks=horizon, multiplier=multiplier)
    if projection.empty or projection["Venta proyectada"].sum() == 0:
        st.info("Carga ventas con fechas o capacidades con SUG 7 para generar la proyección.")
        return
    total_sales = projection["Venta proyectada"].sum()
    total_pieces = projection["Piezas proyectadas"].sum()
    ending_inventory = projection.iloc[-1]["Inventario final"]
    utility = projection["Utilidad %"].mean()
    _kpis([
        ("Venta proyectada", _money(total_sales), f"{horizon} semanas", BLUE),
        ("Utilidad estimada", _percent(utility), scenario, PINK),
        ("Venta pzas", _number(total_pieces), "Proyección", BLUE),
        ("Inventario final", _number(ending_inventory), "Piezas", GREEN),
        ("Modelos por agotar", _number((models["DDI"] <= horizon * 7).sum()) if not models.empty else "0", "Dentro del horizonte", ORANGE),
        ("Espacio liberado", _percent((1 - ending_inventory / max(models["Existencia"].sum(), 1)) * 100) if not models.empty else "0%", "Estimado", PINK),
    ])
    left, right = st.columns([1.65, 1])
    with left:
        fig = go.Figure()
        fig.add_scatter(x=projection["Semana"], y=projection["Venta proyectada"], mode="lines+markers", name="Venta proyectada", line=dict(color=BLUE, width=3), fill="tozeroy", fillcolor="rgba(21,91,239,.08)")
        fig.update_layout(title="Proyección de venta")
        _plot(fig, 420)
    with right:
        fig = go.Figure()
        fig.add_bar(x=projection["Semana"], y=projection["Inventario final"], name="Inventario", marker_color=GREEN)
        fig.update_layout(title="Inventario proyectado")
        _plot(fig, 420)
    comparisons = []
    for label, factor in (("Escenario base", .96), ("Sugerido / VPD", 1.0), ("Utilidad", 1.04)):
        scenario_df = forecast(models, sales, weeks=horizon, multiplier=factor)
        comparisons.append({"Escenario": label, "Venta proyectada": scenario_df["Venta proyectada"].sum(), "Piezas": scenario_df["Piezas proyectadas"].sum(), "Inventario final": scenario_df.iloc[-1]["Inventario final"], "Utilidad %": utility + (1.5 if label == "Utilidad" else 0)})
    st.markdown('<div class="ac-section">Comparación de escenarios</div>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(comparisons), width="stretch", hide_index=True)


def _page_history(bundle: dict) -> None:
    _header("Histórico Comercial", "Evolución semanal y trazabilidad de los PDF", bundle)
    _top_navigation("Histórico Comercial")
    history = bundle["stores_pdf"].copy()
    if history.empty:
        st.info("Aún no existen PDF procesados en el histórico.")
        return
    current_week = _latest_week(history["Semana"].dropna().astype(str).unique())
    current = history[history["Semana"].eq(current_week)]
    _kpis([
        ("Semana actual", current_week, "Último corte", BLUE),
        ("PDF cargados", _number(len(current)), "Archivos", GREEN),
        ("Tiendas reconocidas", _number(current["Tienda"].nunique()), "De 17", BLUE),
        ("Registros/modelos", _number(current["Modelos"].sum()), "Detectados", PINK),
        ("Existencia", _number(current["Existencia"].sum()), "Piso + bodega", "#7C3AED"),
        ("Cobertura", _percent(current["Tienda"].nunique() / 17 * 100), "Tiendas", ORANGE),
    ])
    pivot = history.assign(Disponible="✓").pivot_table(index="Tienda", columns="Semana", values="Disponible", aggfunc="first", fill_value="—")
    left, right = st.columns([1.45, 1])
    with left:
        st.markdown('<div class="ac-section">Cobertura de PDF por tienda</div>', unsafe_allow_html=True)
        st.dataframe(pivot, width="stretch", height=380)
    with right:
        trend = history.groupby("Semana", as_index=False)[["Existencia", "VPD"]].sum()
        fig = go.Figure()
        fig.add_scatter(x=trend["Semana"], y=trend["Existencia"], mode="lines+markers", name="Existencia", line=dict(color=BLUE, width=3))
        fig.add_scatter(x=trend["Semana"], y=trend["VPD"], mode="lines+markers", name="VPD", yaxis="y2", line=dict(color=PINK, width=3))
        fig.update_layout(title="Evolución histórica", yaxis2=dict(overlaying="y", side="right"))
        _plot(fig, 380)
    st.markdown('<div class="ac-section">Historial de cortes</div>', unsafe_allow_html=True)
    st.dataframe(history.sort_values(["Semana", "Tienda"], ascending=[False, True]), width="stretch", height=430, hide_index=True)


def _page_upload(bundle: dict, is_admin: bool) -> None:
    _header("Carga Comercial", "Administra ventas, capacidades y los PDF semanales", bundle)
    if not is_admin:
        st.error("Esta pestaña está disponible únicamente para Administrador o Propietario.")
        return
    flash = st.session_state.pop("commercial_upload_flash", None)
    if flash:
        level, message = flash
        getattr(st, level)(message)
    st.markdown('<div class="ac-source-note">Los archivos se validan antes de alimentar Resumen, Tiendas, Ubicaciones, Modelos, Inventario, Oportunidades, Pronóstico e Histórico.</div>', unsafe_allow_html=True)
    cloud_bootstrap = st.session_state.get("commercial_cloud_bootstrap", {})
    if cloud_bootstrap.get("error"):
        st.error(f"El almacenamiento privado está configurado, pero no respondió: {cloud_bootstrap['error']}", icon=":material/cloud_off:")
    elif cloud_enabled():
        st.success("Histórico protegido: la carga se sincroniza con el almacenamiento privado configurado.", icon=":material/cloud_done:")
    else:
        st.warning("Almacenamiento temporal: configura el respaldo privado indicado en GUIA_PERSISTENCIA_COMERCIAL.md antes de volver a cargar los 17 PDF.", icon=":material/cloud_off:")
    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        st.markdown("### 1. Ventas mensuales")
        sales_upload = st.file_uploader("Excel de ventas", type=["xlsx", "xls", "csv"], key="commercial_sales_upload")
        if st.button("Guardar ventas", disabled=sales_upload is None, type="primary", width="stretch"):
            entry = save_sales_upload(sales_upload)
            sync = sync_history_to_cloud([resolve_entry_path(entry)])
            st.cache_data.clear()
            message = "Archivo duplicado; se conservó el existente." if entry.get("duplicate") else "Ventas guardadas para validación."
            if sync.get("error"):
                st.session_state["commercial_upload_flash"] = ("error", f"{message} No se pudo sincronizar: {sync['error']}")
            elif not sync.get("configured"):
                st.session_state["commercial_upload_flash"] = ("warning", f"{message} Aún están sólo en el servidor temporal.")
            else:
                st.session_state["commercial_upload_flash"] = ("success", f"{message} Respaldo privado actualizado.")
            st.rerun()
        latest = latest_entry("sales")
        st.caption(f"Activo: {latest['name']}" if latest else "Sin archivo cargado")
    with c2:
        st.markdown("### 2. Capacidades y existencias")
        capacity_upload = st.file_uploader("XLS / XLSX de capacidades", type=["xlsx", "xls", "csv"], key="commercial_capacity_upload")
        if st.button("Guardar capacidades", disabled=capacity_upload is None, type="primary", width="stretch"):
            entry = save_capacity_upload(capacity_upload)
            sync = sync_history_to_cloud([resolve_entry_path(entry)])
            st.cache_data.clear()
            message = "Archivo duplicado; se conservó el existente." if entry.get("duplicate") else "Capacidades guardadas para validación."
            if sync.get("error"):
                st.session_state["commercial_upload_flash"] = ("error", f"{message} No se pudo sincronizar: {sync['error']}")
            elif not sync.get("configured"):
                st.session_state["commercial_upload_flash"] = ("warning", f"{message} Aún están sólo en el servidor temporal.")
            else:
                st.session_state["commercial_upload_flash"] = ("success", f"{message} Respaldo privado actualizado.")
            st.rerun()
        latest = latest_entry("capacities")
        st.caption(f"Activo: {latest['name']}" if latest else "Sin archivo cargado")
    with c3:
        st.markdown("### 3. PDF semanales")
        report_date = st.date_input("Fecha del corte", value=date.today(), key="commercial_pdf_date")
        iso = report_date.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"
        pdf_uploads = st.file_uploader("Hasta 17 PDF de tiendas", type=["pdf"], accept_multiple_files=True, key="commercial_pdf_uploads")
        if st.button("Guardar y procesar PDF", disabled=not pdf_uploads, type="primary", width="stretch"):
            saved = 0
            source_paths = []
            for uploaded in pdf_uploads:
                entry = save_pdf_upload(uploaded, week_key)
                path = resolve_entry_path(entry)
                snapshot = extract_pdf_snapshot(path)
                update_entry("pdfs", entry["id"], status=snapshot["status"], store=snapshot["store"], week=snapshot["week"] or week_key, report_date=snapshot["report_date"], pages=snapshot["pages"], records=snapshot["models"])
                save_snapshot(entry["id"], snapshot)
                source_paths.append(path)
                saved += 0 if entry.get("duplicate") else 1
            sync = sync_history_to_cloud(source_paths)
            st.cache_data.clear()
            message = f"{saved} PDF nuevos procesados. El histórico anterior se conservó."
            if sync.get("error"):
                st.session_state["commercial_upload_flash"] = ("error", f"{message} No se pudo sincronizar: {sync['error']}")
            elif not sync.get("configured"):
                st.session_state["commercial_upload_flash"] = ("warning", f"{message} Aún están sólo en el servidor temporal.")
            else:
                st.session_state["commercial_upload_flash"] = ("success", f"{message} Respaldo privado actualizado.")
            st.rerun()
        st.caption(f"Periodo seleccionado: {week_key}")

    manifest = bundle["manifest"]
    pdf_entries = pd.DataFrame(manifest.get("pdfs", []))
    current_week = _latest_week(pdf_entries.get("week", pd.Series(dtype=str)).dropna().astype(str).unique()) if not pdf_entries.empty and "week" in pdf_entries else "Sin semana"
    current_entries = pdf_entries[pdf_entries["week"].eq(current_week)] if not pdf_entries.empty and "week" in pdf_entries else pd.DataFrame()
    stores_recognized = current_entries.get("store", pd.Series(dtype=str)).replace("", np.nan).dropna().nunique() if not current_entries.empty else 0
    records = pd.to_numeric(current_entries.get("records", 0), errors="coerce").fillna(0).sum() if not current_entries.empty else 0
    _kpis([
        ("PDF recibidos", _number(len(current_entries)), current_week, GREEN),
        ("Tiendas reconocidas", _number(stores_recognized), "De 17", BLUE),
        ("Registros extraídos", _number(records), "Modelos detectados", PINK),
        ("Duplicados", _number(pdf_entries.duplicated("sha256").sum()) if not pdf_entries.empty and "sha256" in pdf_entries else "0", "Por contenido", ORANGE),
        ("Errores críticos", _number((pdf_entries.get("status", pd.Series(dtype=str)) == "Error").sum()) if not pdf_entries.empty else "0", "Validación", RED),
        ("Cobertura", _percent(stores_recognized / 17 * 100), "Semana actual", GREEN),
    ])
    if not pdf_entries.empty:
        columns = [column for column in ["store", "name", "week", "report_date", "records", "pages", "status", "uploaded_at"] if column in pdf_entries]
        st.markdown('<div class="ac-section">Archivos PDF recibidos</div>', unsafe_allow_html=True)
        st.dataframe(pdf_entries[columns].sort_values(["week", "store"], ascending=[False, True]), width="stretch", height=390, hide_index=True)

    st.divider()
    left, right = st.columns(2)
    with left:
        backup = build_history_backup()
        st.download_button("Descargar respaldo histórico", backup, file_name=f"Respaldo_Comercial_{datetime.now().strftime('%Y%m%d')}.zip", mime="application/zip", width="stretch")
        st.caption("Incluye los PDF, Excel, manifiesto y acciones para restaurar el histórico.")
    with right:
        restore_file = st.file_uploader("Restaurar respaldo comercial", type=["zip"], key="commercial_restore_backup")
        if st.button("Restaurar respaldo", disabled=restore_file is None, width="stretch"):
            restored = restore_history_backup(restore_file)
            st.cache_data.clear()
            st.success(f"Se restauraron {restored} archivos sin borrar los existentes.")
            st.rerun()


def render_commercial_page(page: str, existing_sales=None, is_admin: bool = False) -> None:
    _inject_styles()
    render_commercial_sidebar(page, is_admin=is_admin)
    if "commercial_cloud_bootstrap" not in st.session_state:
        st.session_state["commercial_cloud_bootstrap"] = restore_history_from_cloud()
        if st.session_state["commercial_cloud_bootstrap"].get("restored"):
            st.cache_data.clear()
    with st.spinner("Actualizando análisis comercial..."):
        bundle = _load_bundle(existing_sales)
    from .pdf_pages import render_pdf_page
    render_pdf_page(page, bundle, is_admin)
