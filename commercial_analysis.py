"""Ventas y Análisis Comercial para PS Operaciones Ropa V53.

El módulo mantiene fuentes independientes del proyecto Muertos y Cambios:
- ventas: reutiliza el caché comercial mensual ya procesado por ORION;
- capacidades/existencias: archivo XLS/XLSX multitienda;
- PDF semanales: lote de hasta 17 análisis comerciales, con original e índice.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from pypdf import PdfReader

from core.settings import DATA_DIR, PROJECT_STORES


ROOT = DATA_DIR / "commercial_analysis"
PDF_ROOT = ROOT / "pdf_history"
CAPACITY_FILE = ROOT / "capacidades.parquet"
CAPACITY_PICKLE = ROOT / "capacidades.pkl"
CAPACITY_META = ROOT / "capacidades_meta.json"
PDF_INDEX = ROOT / "pdf_index.json"
ROOT.mkdir(parents=True, exist_ok=True)
PDF_ROOT.mkdir(parents=True, exist_ok=True)


def _norm(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]+", " ", text.upper()).strip()


STORE_ALIASES = {
    _norm(name): name for name in PROJECT_STORES
}
STORE_ALIASES.update({
    "IZTAPALAPA": "Iztapalapa", "IZTAPALUCA": "Ixtapaluca",
    "OLIVAR DEL CONDE": "Olivar", "PUEBLA SUR": "Puebla Sur",
    "ARCO NORTE": "Arco Norte",
})


def _store(value) -> str:
    n = _norm(value)
    if n in STORE_ALIASES:
        return STORE_ALIASES[n]
    for alias, canonical in sorted(STORE_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias and alias in n:
            return canonical
    return str(value or "").strip()


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write_json(path: Path, payload) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _num(series):
    if isinstance(series, pd.Series):
        return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False).str.replace("$", "", regex=False), errors="coerce").fillna(0)
    return pd.to_numeric(series, errors="coerce")


def _location(subcategory: str, category: str = "") -> str:
    n = _norm(f"{subcategory} {category}")
    if any(x in n for x in ("BRASIERE", "BRASIER", "PANTIBRAGA", "CALCETA", "BOXER", "CORSETERIA", "LENCERIA", "INTERIOR")):
        return "Lencería"
    if "JEAN" in n or "MEZCLILLA" in n:
        return "Jeans"
    if any(x in n for x in ("PLAYERA", "SUDADERA", "PANTS", "LEGGING", "SWEATER", "SHORT", "BERMUDA", "PIJAMA", "TOP")):
        return "Doblado"
    return "Colgado"


def _section(value: str) -> str:
    n = _norm(value)
    if n == "DAMA": return "Dama"
    if n == "CABALLERO": return "Caballero"
    if any(x in n for x in ("NINA", "NINO", "BEBA", "BEBE", "INFANTIL")): return "Infantil"
    return str(value or "Sin sección").title()


def save_capacities(uploaded) -> dict:
    raw = uploaded.getvalue()
    engine = "calamine" if uploaded.name.lower().endswith(".xls") else "openpyxl"
    try:
        frame = pd.read_excel(io.BytesIO(raw), engine=engine)
    except ImportError:
        # Compatibilidad local: producción instala python-calamine; entornos
        # antiguos pueden tener xlrd como lector del formato binario .xls.
        frame = pd.read_excel(io.BytesIO(raw))
    frame.columns = [str(c).strip().upper() for c in frame.columns]
    required = {"TIENDA", "ID_ART", "MODELO", "EXISTENCIA TOTAL"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Faltan columnas requeridas: " + ", ".join(missing))
    frame["TIENDA"] = frame["TIENDA"].map(_store)
    frame = frame[frame["TIENDA"].astype(str).str.len().gt(0)].copy()
    frame["Tienda"] = frame["TIENDA"]
    frame["ID_ART"] = frame["ID_ART"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    frame["MODELO"] = frame["MODELO"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    for col in ["EXISTENCIA PISO", "EXISTENCIA BODEGA", "EXISTENCIA TOTAL", "CAPACIDAD MAX TIENDA(PV)", "DIAS DE INVENTARIO SUG 7", "SUG 7", "SUG 21", "SUG 30", "VTA EN PZAS 7", "VTA EN PZAS 21", "VTA EN PZAS 30", "VTA EN $ 7", "VENTA EN $ 21", "VTA EN $ 30", "PRECIO MAYOREO", "PRECIO MENUDEO", "PRECIO OFERTA", "EXCEDENTE A 60 DIAS", "DIAS STOCK"]:
        if col in frame:
            frame[col] = _num(frame[col])
    frame["UBICACION_COMERCIAL"] = [
        _location(s, c) for s, c in zip(frame.get("SUBCATEGORIA", ""), frame.get("CATEGORIA", ""))
    ]
    frame["SECCION_CONSOLIDADA"] = frame.get("SECCION", "").map(_section)
    try:
        frame.to_parquet(CAPACITY_FILE, index=False)
        CAPACITY_PICKLE.unlink(missing_ok=True)
    except ImportError:
        frame.to_pickle(CAPACITY_PICKLE)
    meta = {
        "archivo": uploaded.name, "fecha_carga": datetime.now().isoformat(timespec="seconds"),
        "registros": int(len(frame)), "tiendas": sorted(frame["TIENDA"].dropna().unique().tolist()),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    _write_json(CAPACITY_META, meta)
    return meta


@st.cache_data(show_spinner=False)
def load_capacities(mtime=0.0) -> pd.DataFrame:
    if CAPACITY_FILE.exists():
        return pd.read_parquet(CAPACITY_FILE)
    if CAPACITY_PICKLE.exists():
        return pd.read_pickle(CAPACITY_PICKLE)
    return pd.DataFrame()


def _pdf_text(raw: bytes) -> tuple[str, int]:
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join((page.extract_text() or "") for page in reader.pages), len(reader.pages)


def _pdf_date(text: str):
    matches = re.findall(r"\b([0-3]?\d)[/-]([01]?\d)[/-](20\d{2})\b", text)
    for d, m, y in matches:
        try: return pd.Timestamp(int(y), int(m), int(d))
        except Exception: pass
    return pd.Timestamp.today().normalize()


def save_pdf_batch(files) -> dict:
    index = _read_json(PDF_INDEX, [])
    hashes = {row.get("sha256") for row in index}
    added, duplicates, errors = [], [], []
    for uploaded in files:
        try:
            raw = uploaded.getvalue(); digest = hashlib.sha256(raw).hexdigest()
            if digest in hashes:
                duplicates.append(uploaded.name); continue
            text, pages = _pdf_text(raw)
            store = _store(f"{uploaded.name} {text[:6000]}")
            if store not in PROJECT_STORES:
                errors.append(f"{uploaded.name}: no se reconoció la tienda"); continue
            stamp = _pdf_date(text); iso = stamp.isocalendar()
            folder = PDF_ROOT / f"{iso.year}-S{iso.week:02d}"
            folder.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{store}_{uploaded.name}")
            path = folder / safe
            path.write_bytes(raw)
            row = {
                "archivo": uploaded.name, "tienda": store,
                "fecha_reporte": stamp.strftime("%Y-%m-%d"), "anio_iso": int(iso.year),
                "semana_iso": int(iso.week), "paginas": pages, "sha256": digest,
                "ruta": str(path.relative_to(ROOT)), "fecha_carga": datetime.now().isoformat(timespec="seconds"),
            }
            index.append(row); hashes.add(digest); added.append(row)
        except Exception as exc:
            errors.append(f"{uploaded.name}: {exc}")
    _write_json(PDF_INDEX, index)
    return {"agregados": added, "duplicados": duplicates, "errores": errors}


def pdf_history() -> pd.DataFrame:
    rows = _read_json(PDF_INDEX, [])
    return pd.DataFrame(rows)


def _sales(co: pd.DataFrame) -> pd.DataFrame:
    if co is None or co.empty:
        return pd.DataFrame(columns=["Tienda", "Modelo llave", "Venta Pzs", "Venta $", "Días con venta", "VPD"])
    d = co.copy()
    d["Tienda"] = d.get("Tienda", "").map(_store)
    id_col = next((c for c in ("ID", "ID/Modelo", "Modelo", "MODELO") if c in d.columns), None)
    if id_col is None:
        d["Modelo llave"] = ""
    else:
        d["Modelo llave"] = d[id_col].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    d["Venta Pzs"] = _num(d.get("Vta_Pzs", 0))
    d["Venta $"] = _num(d.get("Vta_Imp", 0))
    if "Fecha" in d:
        d["Fecha"] = pd.to_datetime(d["Fecha"], errors="coerce")
    keys = ["Tienda", "Modelo llave"]
    agg = d.groupby(keys, as_index=False).agg(**{
        "Venta Pzs": ("Venta Pzs", "sum"), "Venta $": ("Venta $", "sum"),
        "Días con venta": ("Fecha", lambda x: max(x.dropna().dt.normalize().nunique(), 1)) if "Fecha" in d else ("Venta Pzs", lambda x: 1),
    })
    agg["VPD"] = agg["Venta Pzs"] / agg["Días con venta"].clip(lower=1)
    return agg


def commercial_model(co: pd.DataFrame) -> pd.DataFrame:
    source = CAPACITY_FILE if CAPACITY_FILE.exists() else CAPACITY_PICKLE
    caps = load_capacities(source.stat().st_mtime if source.exists() else 0)
    if caps.empty:
        return pd.DataFrame()
    d = caps.copy()
    d["Modelo llave"] = d["ID_ART"].astype(str).str.strip()
    sales = _sales(co)
    out = d.copy()
    sales_idx = sales.set_index(["Tienda", "Modelo llave"]) if not sales.empty else pd.DataFrame()
    primary_keys = pd.MultiIndex.from_arrays([out["Tienda"], out["Modelo llave"]])
    alternate_model = out.get("MODELO", out["Modelo llave"]).astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    alternate_keys = pd.MultiIndex.from_arrays([out["Tienda"], alternate_model])
    for col in ["Venta Pzs", "Venta $", "VPD", "Días con venta"]:
        if sales.empty or col not in sales_idx:
            out[col] = 0
            continue
        lookup = sales_idx[col]
        primary = pd.Series(lookup.reindex(primary_keys).to_numpy(), index=out.index)
        alternate = pd.Series(lookup.reindex(alternate_keys).to_numpy(), index=out.index)
        out[col] = _num(primary.fillna(alternate).fillna(0))
    out["Existencia"] = _num(out.get("EXISTENCIA TOTAL", 0))
    out["Costo unitario"] = _num(out.get("PRECIO MAYOREO", 0))
    out["Inversión"] = out["Existencia"] * out["Costo unitario"]
    out["Utilidad estimada"] = out["Venta $"] - out["Venta Pzs"] * out["Costo unitario"]
    out["Rendimiento inversión"] = np.where(out["Inversión"] > 0, out["Utilidad estimada"] / out["Inversión"], 0)
    out["Días inventario"] = np.where(out["VPD"] > 0, out["Existencia"] / out["VPD"], np.where(out["Existencia"] > 0, 999, 0))
    out["Sugerido VPD"] = _num(out.get("SUG 7", 0)) / 7
    return out


def _filter_bar(data: pd.DataFrame, key: str) -> pd.DataFrame:
    if data.empty: return data
    c1, c2, c3, c4 = st.columns(4)
    stores = sorted(data["Tienda"].dropna().unique())
    sections = sorted(data["SECCION_CONSOLIDADA"].dropna().unique())
    locations = sorted(data["UBICACION_COMERCIAL"].dropna().unique())
    with c1: store = st.selectbox("Alcance", ["Compañía"] + stores, key=f"{key}_store")
    with c2: section = st.selectbox("Sección", ["Todas"] + sections, key=f"{key}_section")
    with c3: location = st.selectbox("Ubicación", ["Todas"] + locations, key=f"{key}_location")
    with c4:
        months = sorted(pd.to_datetime(st.session_state.get("commercial_month", pd.Timestamp.today().strftime("%Y-%m")), errors="coerce").strftime("%Y-%m") for _ in [0])
        st.text_input("Periodo de ventas", value=months[0], disabled=True, key=f"{key}_period")
    out = data
    if store != "Compañía": out = out[out["Tienda"].eq(store)]
    if section != "Todas": out = out[out["SECCION_CONSOLIDADA"].eq(section)]
    if location != "Todas": out = out[out["UBICACION_COMERCIAL"].eq(location)]
    return out


def _aggregate(data: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if data.empty: return pd.DataFrame()
    return data.groupby(group_cols, as_index=False).agg({
        "Venta Pzs": "sum", "Venta $": "sum", "Existencia": "sum", "Inversión": "sum",
        "Utilidad estimada": "sum", "VPD": "sum", "Sugerido VPD": "sum",
    }).assign(**{
        "Rendimiento inversión": lambda x: np.where(x["Inversión"] > 0, x["Utilidad estimada"] / x["Inversión"], 0),
        "Días inventario": lambda x: np.where(x["VPD"] > 0, x["Existencia"] / x["VPD"], np.where(x["Existencia"] > 0, 999, 0)),
    })


def _metrics(data: pd.DataFrame):
    sales_p = data["Venta Pzs"].sum(); sales_m = data["Venta $"].sum(); inv = data["Inversión"].sum()
    utility = data["Utilidad estimada"].sum(); stock = data["Existencia"].sum(); vpd = data["VPD"].sum()
    cols = st.columns(6)
    values = [
        ("Venta en piezas", f"{sales_p:,.0f}"), ("Venta en pesos", f"${sales_m:,.0f}"),
        ("Existencia", f"{stock:,.0f}"), ("Inversión", f"${inv:,.0f}"),
        ("Utilidad estimada", f"${utility:,.0f}"), ("VPD", f"{vpd:,.1f}"),
    ]
    for col, (label, value) in zip(cols, values): col.metric(label, value)


def _table_download(frame: pd.DataFrame, filename: str):
    st.download_button("Descargar CSV", frame.to_csv(index=False).encode("utf-8-sig"), filename, "text/csv", width="stretch")


def render_dashboard(co: pd.DataFrame):
    st.title("Ventas y Análisis Comercial")
    st.caption("Vista global de compañía con detalle por tienda, ubicación, sección y modelo.")
    data = commercial_model(co)
    if data.empty:
        st.warning("Carga primero el archivo de capacidades y existencias desde Carga Comercial.")
        return
    data = _filter_bar(data, "commercial_dashboard")
    _metrics(data)
    by_store = _aggregate(data, ["Tienda"]).sort_values("Venta $", ascending=False)
    by_location = _aggregate(data, ["UBICACION_COMERCIAL"]).sort_values("Venta $", ascending=False)
    left, right = st.columns(2)
    with left:
        fig = px.bar(by_store, x="Tienda", y="Venta $", color="Utilidad estimada", title="Venta y utilidad por tienda", color_continuous_scale="Blues")
        st.plotly_chart(fig, width="stretch")
    with right:
        fig = px.bar(by_location, x="UBICACION_COMERCIAL", y="Venta $", color="Inversión", title="Venta por ubicación", color_continuous_scale="RdPu")
        st.plotly_chart(fig, width="stretch")
    st.subheader("Comparativo de tiendas")
    st.dataframe(by_store, width="stretch", hide_index=True)
    _table_download(by_store, "comparativo_comercial_tiendas.csv")


def render_rankings(co: pd.DataFrame):
    st.title("Top 20 Campeones y Modelos Lentos")
    data = commercial_model(co)
    if data.empty:
        st.warning("No hay capacidades procesadas."); return
    data = _filter_bar(data, "commercial_rank")
    model_cols = ["Modelo llave", "MODELO", "MARCA PRICE", "SECCION_CONSOLIDADA", "UBICACION_COMERCIAL"]
    model_cols = [c for c in model_cols if c in data.columns]
    ranked = _aggregate(data, model_cols)
    t1, t2, t3 = st.tabs(["Campeones por sugerido/VPD", "Campeones por utilidad", "Modelos lentos por inversión"])
    with t1:
        top = ranked.sort_values(["VPD", "Venta Pzs", "Venta $"], ascending=False).head(20)
        st.dataframe(top, width="stretch", hide_index=True); _table_download(top, "top20_campeones_vpd.csv")
    with t2:
        top = ranked.sort_values(["Utilidad estimada", "Rendimiento inversión"], ascending=False).head(20)
        st.dataframe(top, width="stretch", hide_index=True); _table_download(top, "top20_campeones_utilidad.csv")
    with t3:
        slow = ranked[ranked["Existencia"].gt(0)].copy()
        slow["Índice lento"] = slow["Inversión"] / (slow["VPD"] + 0.1)
        slow = slow.sort_values(["Índice lento", "Días inventario"], ascending=False).head(20)
        st.dataframe(slow, width="stretch", hide_index=True); _table_download(slow, "top20_modelos_lentos.csv")


def render_locations(co: pd.DataFrame):
    st.title("Análisis por Ubicación y Sección")
    data = commercial_model(co)
    if data.empty: st.warning("No hay capacidades procesadas."); return
    data = _filter_bar(data, "commercial_location")
    group = _aggregate(data, ["UBICACION_COMERCIAL", "SECCION_CONSOLIDADA"])
    _metrics(data)
    fig = px.sunburst(group, path=["UBICACION_COMERCIAL", "SECCION_CONSOLIDADA"], values="Venta $", color="Rendimiento inversión", color_continuous_scale="RdYlGn", title="Participación comercial")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(group.sort_values("Venta $", ascending=False), width="stretch", hide_index=True)


def render_history():
    st.title("Histórico Semanal de PDF")
    history = pdf_history()
    if history.empty:
        st.info("Aún no hay PDF semanales guardados."); return
    weeks = history[["anio_iso", "semana_iso"]].drop_duplicates().sort_values(["anio_iso", "semana_iso"], ascending=False)
    labels = [f"{int(y)} - Semana {int(w):02d}" for y, w in weeks.itertuples(index=False, name=None)]
    selected = st.selectbox("Semana", labels)
    y, w = map(int, re.findall(r"\d+", selected)[:2])
    current = history[(history["anio_iso"].eq(y)) & (history["semana_iso"].eq(w))].copy()
    loaded = sorted(current["tienda"].unique())
    missing = [s for s in PROJECT_STORES if s not in loaded]
    c1, c2, c3 = st.columns(3)
    c1.metric("PDF cargados", len(current)); c2.metric("Tiendas reconocidas", len(loaded)); c3.metric("Faltantes", len(missing))
    if missing: st.warning("Tiendas faltantes: " + ", ".join(missing))
    else: st.success("Lote completo: 17 de 17 tiendas.")
    st.dataframe(current[["tienda", "archivo", "fecha_reporte", "paginas", "fecha_carga"]].sort_values("tienda"), width="stretch", hide_index=True)


def render_uploads():
    st.title("Carga Comercial")
    st.caption("Las fuentes quedan separadas de Muertos y Cambios y conservan su histórico.")
    tab1, tab2 = st.tabs(["Capacidades y existencias", "PDF semanales (17 tiendas)"])
    with tab1:
        meta = _read_json(CAPACITY_META, {})
        if meta:
            st.success(f"Fuente activa: {meta.get('archivo')} · {meta.get('registros',0):,} registros · {len(meta.get('tiendas',[]))} tienda(s)")
        upload = st.file_uploader("Archivo XLS o XLSX", type=["xls", "xlsx"], key="commercial_capacity_upload")
        if st.button("Guardar capacidades", type="primary", disabled=upload is None, key="commercial_capacity_save"):
            try:
                with st.spinner("Validando y procesando capacidades..."):
                    saved = save_capacities(upload); load_capacities.clear()
                st.success(f"Procesado: {saved['registros']:,} registros y {len(saved['tiendas'])} tienda(s).")
            except Exception as exc: st.error(f"No fue posible procesar el archivo: {exc}")
    with tab2:
        files = st.file_uploader("Selecciona los PDF de la semana", type=["pdf"], accept_multiple_files=True, key="commercial_pdf_upload")
        st.caption("Puedes seleccionar los 17 archivos en una sola carga. Los duplicados no se vuelven a guardar.")
        if st.button("Guardar lote semanal", type="primary", disabled=not files, key="commercial_pdf_save"):
            result = save_pdf_batch(files)
            if result["agregados"]: st.success(f"Se guardaron {len(result['agregados'])} PDF nuevos.")
            if result["duplicados"]: st.warning("Duplicados omitidos: " + ", ".join(result["duplicados"]))
            if result["errores"]: st.error(" | ".join(result["errores"]))
        history = pdf_history()
        if not history.empty:
            latest = history.sort_values(["anio_iso", "semana_iso"], ascending=False).iloc[0]
            week = history[(history["anio_iso"].eq(latest["anio_iso"])) & (history["semana_iso"].eq(latest["semana_iso"]))]
            st.info(f"Último lote: semana {int(latest['semana_iso']):02d} de {int(latest['anio_iso'])} · {week['tienda'].nunique()} de 17 tiendas.")


def render(page: str, co: pd.DataFrame, is_admin: bool = False):
    if page == "Resumen Comercial": render_dashboard(co)
    elif page == "Ubicaciones y Secciones": render_locations(co)
    elif page == "Top 20 Modelos": render_rankings(co)
    elif page == "Histórico PDF": render_history()
    elif page == "Carga Comercial":
        if not is_admin: st.error("Disponible únicamente para Administrador o Propietario.")
        else: render_uploads()
    else: render_dashboard(co)
