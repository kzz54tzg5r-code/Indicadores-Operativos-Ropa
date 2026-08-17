"""Ventas y Análisis Comercial para PS Operaciones Ropa V54.

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
import pdfplumber
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
PDF_SUMMARY_FILE = ROOT / "pdf_summary.parquet"
PDF_SUMMARY_PICKLE = ROOT / "pdf_summary.pkl"
PDF_MODELS_FILE = ROOT / "pdf_models.parquet"
PDF_MODELS_PICKLE = ROOT / "pdf_models.pkl"
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


def _clean_cell(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("...", "").strip())


def _plain_number(value) -> float:
    text = str(value or "").replace(",", "").replace("$", "").replace("%", "").strip()
    if not text or text in {"-", "—"} or "\n" in text:
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def _column_index(headers, *, contains=(), raw_contains=None):
    for index, header in enumerate(headers):
        raw = str(header or "")
        normalized = _norm(raw)
        if raw_contains is not None and raw_contains in raw:
            return index
        if contains and all(token in normalized for token in contains):
            return index
    return None


def _row_value(row, index):
    return row[index] if index is not None and index < len(row) else None


def _summary_rows(table, dimension, store, stamp, digest):
    """Convierte una tabla de sección/categoría/ubicación/rubro a filas auditables."""
    if not table or len(table) < 3:
        return []
    headers = table[1]
    idx = {
        "ids": _column_index(headers, contains=("VALORES", "ID")),
        "curva": _column_index(headers, contains=("CURVA",)),
        "piso": _column_index(headers, contains=("PISO",)),
        "bodega": _column_index(headers, contains=("BODEGA",)),
        "sug7": _column_index(headers, contains=("SUG", "7")),
        "existencia": _column_index(headers, contains=("EXISTENCIA", "TOTAL")),
        "ddi": _column_index(headers, contains=("DDI",)),
        "ddc": _column_index(headers, contains=("DDC",)),
        "doblado": _column_index(headers, contains=("DOBLAD",)),
        "colgado": _column_index(headers, contains=("COLGAD",)),
        "posiciones": next((i for i, h in enumerate(headers) if any(x in _norm(h) for x in ("BRAZ POS", "BRAZ", " POS"))), None),
        "part_inv": _column_index(headers, contains=("PART", "INVENTARIO")),
        "part_pzs": _column_index(headers, contains=("PART", "PZAS")),
        "part_sales": _column_index(headers, raw_contains="$"),
        "inversion": _column_index(headers, contains=("INVERSION",)),
        "utilidad": _column_index(headers, contains=("UTILIDAD",)),
    }
    is_rubro = dimension == "Rubro"
    label_index = 1 if is_rubro else 0
    section_value = ""
    iso = stamp.isocalendar()
    output = []
    for row in table[2:]:
        if not row:
            continue
        if is_rubro and row[0]:
            section_value = _section(row[0])
        label = _clean_cell(_row_value(row, label_index))
        if not label or label.lower() in {"nan", "none"}:
            continue
        # pdfplumber a veces une dos renglones en una celda; se omiten para no
        # inventar una distribución que el PDF no permite separar con certeza.
        if any("\n" in str(_row_value(row, idx[k]) or "") for k in ("ids", "piso", "sug7")):
            continue
        if dimension == "Ubicación":
            nlabel = _norm(label)
            if "MEZCLILLA" in nlabel or "MEZ" in nlabel or "JEAN" in nlabel:
                label = "Jeans"
            elif "DOBLAD" in nlabel:
                label = "Doblado"
            elif "COLGAD" in nlabel:
                label = "Colgado"
            elif "LENCER" in nlabel or "INTERIOR" in nlabel:
                label = "Lencería"
        piso = _plain_number(_row_value(row, idx["piso"]))
        bodega = _plain_number(_row_value(row, idx["bodega"]))
        existencia = _plain_number(_row_value(row, idx["existencia"])) or (piso + bodega)
        sug7 = _plain_number(_row_value(row, idx["sug7"]))
        output.append({
            "Tienda": store, "Fecha reporte": stamp.strftime("%Y-%m-%d"),
            "Año ISO": int(iso.year), "Semana ISO": int(iso.week), "SHA256": digest,
            "Dimensión": dimension, "Sección": section_value if is_rubro else (_section(label) if dimension == "Sección" else ""),
            "Elemento": label, "ID activos": _plain_number(_row_value(row, idx["ids"])),
            "Curva": _plain_number(_row_value(row, idx["curva"])), "Piso": piso,
            "Bodega": bodega, "Existencia": existencia, "Sugerido 7": sug7,
            "VPD sugerida": sug7 / 7.0, "DDI": _plain_number(_row_value(row, idx["ddi"])),
            "DDC": _plain_number(_row_value(row, idx["ddc"])),
            "Doblado": _plain_number(_row_value(row, idx["doblado"])),
            "Colgado": _plain_number(_row_value(row, idx["colgado"])),
            "Brazos/Posiciones": _plain_number(_row_value(row, idx["posiciones"])),
            "% participación inventario": _plain_number(_row_value(row, idx["part_inv"])),
            "% participación piezas": _plain_number(_row_value(row, idx["part_pzs"])),
            "% participación venta $": _plain_number(_row_value(row, idx["part_sales"])),
            "% participación inversión": _plain_number(_row_value(row, idx["inversion"])),
            "% participación utilidad": _plain_number(_row_value(row, idx["utilidad"])),
        })
    return output


def _ranking_type(page_text: str) -> str:
    # El encabezado de la primera línea define el ranking. El cuerpo siempre
    # contiene una columna "% Utilidad" y no debe cambiar la clasificación.
    first_line = (page_text or "").splitlines()[0] if (page_text or "").splitlines() else ""
    n = _norm(first_line)
    if "MAYOR INVERSION" in n:
        return "Mayor inversión"
    if "SUGERIDO CERO" in n:
        return "Sugerido cero"
    if "MODELOS" in n and "UTILIDAD" in n:
        return "Campeones por utilidad"
    if "SUG 7" in n:
        return "Campeones por sugerido"
    return "Ranking PDF"


def _model_rows(table, ranking_type, store, stamp, digest):
    if not table or len(table) < 3:
        return []
    section = _section(_clean_cell(table[0][0]))
    headers = table[1]
    col = {
        "id": _column_index(headers, contains=("ID ART",)),
        "modelo": _column_index(headers, contains=("MODELO",)),
        "color": _column_index(headers, contains=("COLOR",)),
        "marca": _column_index(headers, contains=("MARCA",)),
        "subcategoria": _column_index(headers, contains=("SUBCATEGORIA",)),
        "curva": _column_index(headers, contains=("CURVA",)),
        "piso": _column_index(headers, contains=("PISO",)),
        "bodega": _column_index(headers, contains=("BODEGA",)),
        "sug7": _column_index(headers, contains=("SUG", "7")),
        "ddi": _column_index(headers, contains=("DDI",)),
        "ddc": _column_index(headers, contains=("DDC",)),
        "inversion": _column_index(headers, contains=("INVERSION",)),
        "utilidad": _column_index(headers, contains=("UTILIDAD",)),
    }
    if col["id"] is None or col["modelo"] is None:
        return []
    iso = stamp.isocalendar(); output = []
    for position, row in enumerate(table[2:], 1):
        article = _clean_cell(_row_value(row, col["id"]))
        model = _clean_cell(_row_value(row, col["modelo"]))
        if not article or not model or not re.search(r"\d", article):
            continue
        subcategory = _clean_cell(_row_value(row, col["subcategoria"]))
        piso = _plain_number(_row_value(row, col["piso"]))
        bodega = _plain_number(_row_value(row, col["bodega"]))
        sug7 = _plain_number(_row_value(row, col["sug7"]))
        output.append({
            "Tienda": store, "Fecha reporte": stamp.strftime("%Y-%m-%d"),
            "Año ISO": int(iso.year), "Semana ISO": int(iso.week), "SHA256": digest,
            "Tipo ranking": ranking_type, "Ranking": position, "Sección": section,
            "ID_ART": article, "Modelo": model, "Color": _clean_cell(_row_value(row, col["color"])),
            "Marca": _clean_cell(_row_value(row, col["marca"])), "Subcategoría": subcategory,
            "Ubicación": _location(subcategory), "Curva": _plain_number(_row_value(row, col["curva"])),
            "Piso": piso, "Bodega": bodega, "Existencia": piso + bodega,
            "Sugerido 7": sug7, "VPD sugerida": sug7 / 7.0,
            "DDI": _plain_number(_row_value(row, col["ddi"])), "DDC": _plain_number(_row_value(row, col["ddc"])),
            "Inversión": _plain_number(_row_value(row, col["inversion"])),
            "% utilidad": _plain_number(_row_value(row, col["utilidad"])),
        })
    return output


def extract_pdf_data(raw: bytes, store: str, stamp, digest: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    summaries, models = [], []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            if page_number == 1:
                for table in tables:
                    if not table or not table[0] or len(table[0]) > 25:
                        continue
                    title = _norm(table[0][0])
                    dimension = None
                    if "VENTAS POR SECCION" in title: dimension = "Sección"
                    elif "VENTAS POR CATEGORIA" in title: dimension = "Categoría"
                    elif "VENTAS POR UBICACION" in title: dimension = "Ubicación"
                    if dimension:
                        summaries.extend(_summary_rows(table, dimension, store, stamp, digest))
            elif page_number == 3 and tables:
                summaries.extend(_summary_rows(tables[0], "Rubro", store, stamp, digest))

            if page_number >= 20:
                ranking = _ranking_type(page.extract_text() or "")
                for table in tables:
                    models.extend(_model_rows(table, ranking, store, stamp, digest))
    return pd.DataFrame(summaries), pd.DataFrame(models)


def _save_frame(frame: pd.DataFrame, parquet_path: Path, pickle_path: Path) -> None:
    try:
        frame.to_parquet(parquet_path, index=False)
        pickle_path.unlink(missing_ok=True)
    except ImportError:
        frame.to_pickle(pickle_path)


def _load_frame(parquet_path: Path, pickle_path: Path) -> pd.DataFrame:
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    if pickle_path.exists():
        return pd.read_pickle(pickle_path)
    return pd.DataFrame()


def _store_extracted_data(summary: pd.DataFrame, models: pd.DataFrame, digest: str) -> None:
    current_summary = _load_frame(PDF_SUMMARY_FILE, PDF_SUMMARY_PICKLE)
    current_models = _load_frame(PDF_MODELS_FILE, PDF_MODELS_PICKLE)
    if not current_summary.empty and "SHA256" in current_summary:
        current_summary = current_summary[current_summary["SHA256"].ne(digest)]
    if not current_models.empty and "SHA256" in current_models:
        current_models = current_models[current_models["SHA256"].ne(digest)]
    if not summary.empty:
        current_summary = pd.concat([current_summary, summary], ignore_index=True)
    if not models.empty:
        current_models = pd.concat([current_models, models], ignore_index=True)
    _save_frame(current_summary, PDF_SUMMARY_FILE, PDF_SUMMARY_PICKLE)
    _save_frame(current_models, PDF_MODELS_FILE, PDF_MODELS_PICKLE)


def load_pdf_summary(latest_only=True) -> pd.DataFrame:
    frame = _load_frame(PDF_SUMMARY_FILE, PDF_SUMMARY_PICKLE)
    if frame.empty or not latest_only:
        return frame
    frame["Fecha reporte"] = pd.to_datetime(frame["Fecha reporte"], errors="coerce")
    latest = frame.groupby("Tienda")["Fecha reporte"].transform("max")
    return frame[frame["Fecha reporte"].eq(latest)].copy()


def load_pdf_models(latest_only=True) -> pd.DataFrame:
    frame = _load_frame(PDF_MODELS_FILE, PDF_MODELS_PICKLE)
    if frame.empty or not latest_only:
        return frame
    frame["Fecha reporte"] = pd.to_datetime(frame["Fecha reporte"], errors="coerce")
    latest = frame.groupby("Tienda")["Fecha reporte"].transform("max")
    return frame[frame["Fecha reporte"].eq(latest)].copy()


def _select_pdf_week(frame: pd.DataFrame, key: str) -> pd.DataFrame:
    if frame.empty or not {"Año ISO", "Semana ISO"}.issubset(frame.columns):
        return frame
    periods = (
        frame[["Año ISO", "Semana ISO"]].drop_duplicates()
        .sort_values(["Año ISO", "Semana ISO"], ascending=False)
    )
    labels = [f"{int(y)} - Semana {int(w):02d}" for y, w in periods.itertuples(index=False, name=None)]
    selected = st.selectbox("Semana del PDF", labels, key=key)
    year, week = map(int, re.findall(r"\d+", selected)[:2])
    return frame[frame["Año ISO"].eq(year) & frame["Semana ISO"].eq(week)].copy()


def save_pdf_batch(files) -> dict:
    index = _read_json(PDF_INDEX, [])
    by_hash = {row.get("sha256"): row for row in index if row.get("sha256")}
    added, reprocessed, duplicates, errors = [], [], [], []
    for uploaded in files:
        try:
            raw = uploaded.getvalue(); digest = hashlib.sha256(raw).hexdigest()
            existing = by_hash.get(digest)
            if existing and int(existing.get("registros_extraidos", 0)) > 0:
                duplicates.append(uploaded.name); continue
            text, pages = _pdf_text(raw)
            store = _store(f"{uploaded.name} {text[:6000]}")
            if store not in PROJECT_STORES:
                errors.append(f"{uploaded.name}: no se reconoció la tienda"); continue
            stamp = _pdf_date(text); iso = stamp.isocalendar()
            summary, models = extract_pdf_data(raw, store, stamp, digest)
            if summary.empty and models.empty:
                errors.append(f"{uploaded.name}: no se encontraron tablas comerciales compatibles")
                continue
            _store_extracted_data(summary, models, digest)
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
                "registros_resumen": int(len(summary)), "registros_modelos": int(len(models)),
                "registros_extraidos": int(len(summary) + len(models)), "estado_extraccion": "Procesado",
            }
            if existing:
                existing.update(row); reprocessed.append(row)
            else:
                index.append(row); by_hash[digest] = row; added.append(row)
        except Exception as exc:
            errors.append(f"{uploaded.name}: {exc}")
    _write_json(PDF_INDEX, index)
    return {"agregados": added, "reprocesados": reprocessed, "duplicados": duplicates, "errores": errors}


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


def _commercial_filters(data: pd.DataFrame, summary: pd.DataFrame, key: str):
    stores = set(data["Tienda"].dropna().astype(str)) if not data.empty and "Tienda" in data else set()
    stores.update(summary["Tienda"].dropna().astype(str) if not summary.empty and "Tienda" in summary else [])
    sections = set(data["SECCION_CONSOLIDADA"].dropna().astype(str)) if not data.empty and "SECCION_CONSOLIDADA" in data else set()
    if not summary.empty:
        sections.update(summary.loc[summary["Dimensión"].eq("Sección"), "Elemento"].map(_section).tolist())
    sections = {s for s in sections if _norm(s) not in {"TOTAL GENERAL", "TOTAL"}}
    locations = set(data["UBICACION_COMERCIAL"].dropna().astype(str)) if not data.empty and "UBICACION_COMERCIAL" in data else set()
    if not summary.empty:
        locations.update(summary.loc[summary["Dimensión"].eq("Ubicación"), "Elemento"].astype(str).tolist())
    locations = {x for x in locations if _norm(x) not in {"TOTAL GENERAL", "TOTAL"}}
    c1, c2, c3 = st.columns(3)
    with c1: selected_store = st.selectbox("Alcance", ["Compañía"] + sorted(stores), key=f"{key}_store")
    with c2: selected_section = st.selectbox("Sección", ["Todas"] + sorted(sections), key=f"{key}_section")
    with c3: selected_location = st.selectbox("Ubicación", ["Todas"] + sorted(locations), key=f"{key}_location")

    filtered_data = data.copy()
    filtered_summary = summary.copy()
    if selected_store != "Compañía":
        if not filtered_data.empty: filtered_data = filtered_data[filtered_data["Tienda"].eq(selected_store)]
        if not filtered_summary.empty: filtered_summary = filtered_summary[filtered_summary["Tienda"].eq(selected_store)]
    if selected_section != "Todas":
        if not filtered_data.empty: filtered_data = filtered_data[filtered_data["SECCION_CONSOLIDADA"].eq(selected_section)]
        if not filtered_summary.empty:
            filtered_summary = filtered_summary[
                ((filtered_summary["Dimensión"].eq("Sección")) & filtered_summary["Elemento"].map(_section).eq(selected_section))
                | ((filtered_summary["Dimensión"].eq("Rubro")) & filtered_summary["Sección"].eq(selected_section))
            ]
    if selected_location != "Todas":
        if not filtered_data.empty: filtered_data = filtered_data[filtered_data["UBICACION_COMERCIAL"].eq(selected_location)]
        if not filtered_summary.empty:
            filtered_summary = filtered_summary[
                filtered_summary["Dimensión"].eq("Ubicación") & filtered_summary["Elemento"].eq(selected_location)
            ]
    return filtered_data, filtered_summary, selected_store, selected_section, selected_location


def _pdf_store_totals(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame()
    rows = []
    for store, group in summary.groupby("Tienda"):
        total = group[group["Elemento"].map(_norm).str.contains("TOTAL")]
        if not total.empty:
            row = total.iloc[0]
        else:
            section_rows = group[group["Dimensión"].eq("Sección")]
            if section_rows.empty:
                section_rows = group
            numeric = section_rows.select_dtypes(include=[np.number]).sum()
            row = pd.Series({**numeric.to_dict(), "Tienda": store})
        rows.append({
            "Tienda": store, "ID activos PDF": float(row.get("ID activos", 0)),
            "Existencia PDF": float(row.get("Existencia", 0)), "Sugerido 7 PDF": float(row.get("Sugerido 7", 0)),
            "VPD PDF": float(row.get("VPD sugerida", 0)), "DDI PDF": float(row.get("DDI", 0)),
            "DDC PDF": float(row.get("DDC", 0)), "Brazos/Posiciones PDF": float(row.get("Brazos/Posiciones", 0)),
        })
    return pd.DataFrame(rows)


def _combined_metrics(data: pd.DataFrame, summary: pd.DataFrame):
    pdf_totals = _pdf_store_totals(summary)
    pdf_stores = set(pdf_totals["Tienda"]) if not pdf_totals.empty else set()
    cap = data[~data["Tienda"].isin(pdf_stores)] if not data.empty and pdf_stores else data
    sales_p = data["Venta Pzs"].sum() if not data.empty else 0
    sales_m = data["Venta $"].sum() if not data.empty else 0
    utility = data["Utilidad estimada"].sum() if not data.empty else 0
    investment = data["Inversión"].sum() if not data.empty else 0
    stock = (cap["Existencia"].sum() if cap is not None and not cap.empty else 0) + (pdf_totals["Existencia PDF"].sum() if not pdf_totals.empty else 0)
    sug7 = (cap["Sugerido VPD"].sum() * 7 if cap is not None and not cap.empty else 0) + (pdf_totals["Sugerido 7 PDF"].sum() if not pdf_totals.empty else 0)
    vpd = sug7 / 7.0
    has_sales = sales_p != 0 or sales_m != 0
    values = [
        ("Venta en piezas", f"{sales_p:,.0f}" if has_sales else "Sin Excel mensual"),
        ("Venta en pesos", f"${sales_m:,.0f}" if has_sales else "Sin Excel mensual"),
        ("Existencia", f"{stock:,.0f}"), ("Inversión", f"${investment:,.0f}" if investment else "Pendiente de costo"),
        ("Sugerido 7 PDF", f"{sug7:,.0f}"), ("VPD sugerida", f"{vpd:,.1f}"),
    ]
    cols = st.columns(6)
    for col, (label, value) in zip(cols, values): col.metric(label, value)
    return pdf_totals, has_sales


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
    summary = _select_pdf_week(load_pdf_summary(False), "commercial_dashboard_pdf_week")
    if data.empty and summary.empty:
        st.warning("Carga los PDF semanales o el archivo de capacidades desde Carga Comercial.")
        return
    data, summary, _, _, _ = _commercial_filters(data, summary, "commercial_dashboard")
    if not summary.empty:
        latest_label = pd.to_datetime(summary["Fecha reporte"], errors="coerce").max().strftime("%d/%m/%Y")
        st.success(f"PDF comercial procesado y aplicado al tablero · corte más reciente {latest_label}")
    if co is None or co.empty:
        st.info("El Excel mensual de ventas no está disponible. Se muestran inventario, sugerido, VPD, DDI, DDC y participaciones extraídos de los PDF.")
    pdf_totals, has_sales = _combined_metrics(data, summary)
    by_store = _aggregate(data, ["Tienda"]).sort_values("Venta $", ascending=False) if not data.empty else pd.DataFrame()
    if not pdf_totals.empty:
        by_store = pdf_totals.merge(by_store, on="Tienda", how="outer") if not by_store.empty else pdf_totals
    by_location_pdf = summary[summary["Dimensión"].eq("Ubicación")].copy() if not summary.empty else pd.DataFrame()
    by_location = _aggregate(data, ["UBICACION_COMERCIAL"]).sort_values("Venta $", ascending=False) if not data.empty else pd.DataFrame()
    left, right = st.columns(2)
    with left:
        if has_sales and not by_store.empty and "Venta $" in by_store:
            fig = px.bar(by_store, x="Tienda", y="Venta $", color="Utilidad estimada", title="Venta y utilidad por tienda", color_continuous_scale="Blues")
        else:
            chart_source = pdf_totals
            if chart_source.empty and not data.empty:
                chart_source = data.groupby("Tienda", as_index=False).agg({"Sugerido VPD": "sum", "Existencia": "sum"})
                chart_source["Sugerido 7 PDF"] = chart_source["Sugerido VPD"] * 7
                chart_source["Existencia PDF"] = chart_source["Existencia"]
            fig = px.bar(chart_source, x="Tienda", y="Sugerido 7 PDF", color="Existencia PDF", title="Sugerido e inventario por tienda", color_continuous_scale="Blues")
        st.plotly_chart(fig, width="stretch")
    with right:
        if not by_location_pdf.empty:
            fig = px.bar(by_location_pdf, x="Elemento", y="Sugerido 7", color="% participación venta $", title="Sugerido por ubicación", color_continuous_scale="RdPu")
            st.plotly_chart(fig, width="stretch")
        elif not summary.empty:
            fig = px.bar(summary, x="Elemento", y="Sugerido 7", color="% participación utilidad", title="Sugerido del filtro seleccionado", color_continuous_scale="RdPu")
            st.plotly_chart(fig, width="stretch")
        elif not by_location.empty:
            fig = px.bar(by_location, x="UBICACION_COMERCIAL", y="Venta $", color="Inversión", title="Venta por ubicación", color_continuous_scale="RdPu")
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No hay desglose de ubicación para el filtro seleccionado.")
    st.subheader("Comparativo de tiendas")
    st.dataframe(by_store, width="stretch", hide_index=True)
    _table_download(by_store, "comparativo_comercial_tiendas.csv")
    if not by_location_pdf.empty:
        st.subheader("Participación comercial extraída del PDF")
        cols = ["Tienda", "Elemento", "Existencia", "Sugerido 7", "VPD sugerida", "DDI", "DDC", "% participación inventario", "% participación piezas", "% participación venta $", "% participación utilidad"]
        st.dataframe(by_location_pdf[[c for c in cols if c in by_location_pdf]], width="stretch", hide_index=True)


def render_rankings(co: pd.DataFrame):
    st.title("Top 20 Campeones y Modelos Lentos")
    data = commercial_model(co)
    pdf_models = _select_pdf_week(load_pdf_models(False), "commercial_rank_pdf_week")
    if data.empty and pdf_models.empty:
        st.warning("No hay modelos procesados desde PDF ni capacidades."); return
    stores = sorted(set(pdf_models["Tienda"].dropna().astype(str)) | (set(data["Tienda"].dropna().astype(str)) if not data.empty else set()))
    sections = sorted(set(pdf_models["Sección"].dropna().astype(str)) | (set(data["SECCION_CONSOLIDADA"].dropna().astype(str)) if not data.empty else set()))
    c1, c2 = st.columns(2)
    with c1: selected_store = st.selectbox("Alcance", ["Compañía"] + stores, key="commercial_rank_store_v54")
    with c2: selected_section = st.selectbox("Sección", ["Todas"] + sections, key="commercial_rank_section_v54")
    if selected_store != "Compañía":
        if not data.empty: data = data[data["Tienda"].eq(selected_store)]
        if not pdf_models.empty: pdf_models = pdf_models[pdf_models["Tienda"].eq(selected_store)]
    if selected_section != "Todas":
        if not data.empty: data = data[data["SECCION_CONSOLIDADA"].eq(selected_section)]
        if not pdf_models.empty: pdf_models = pdf_models[pdf_models["Sección"].eq(selected_section)]
    model_cols = ["Modelo llave", "MODELO", "MARCA PRICE", "SECCION_CONSOLIDADA", "UBICACION_COMERCIAL"]
    model_cols = [c for c in model_cols if c in data.columns]
    ranked = _aggregate(data, model_cols) if not data.empty and model_cols else pd.DataFrame()
    t1, t2, t3 = st.tabs(["Campeones por sugerido/VPD", "Campeones por utilidad", "Modelos lentos por inversión"])
    with t1:
        from_pdf = pdf_models[pdf_models["Tipo ranking"].eq("Campeones por sugerido")].sort_values(["Ranking", "Sugerido 7"]).head(20) if not pdf_models.empty else pd.DataFrame()
        top = from_pdf if not from_pdf.empty else ranked.sort_values(["VPD", "Venta Pzs", "Venta $"], ascending=False).head(20)
        st.dataframe(top, width="stretch", hide_index=True); _table_download(top, "top20_campeones_vpd.csv")
    with t2:
        from_pdf = pdf_models[pdf_models["Tipo ranking"].eq("Campeones por utilidad")].sort_values("Ranking").head(20) if not pdf_models.empty else pd.DataFrame()
        top = from_pdf if not from_pdf.empty else ranked.sort_values(["Utilidad estimada", "Rendimiento inversión"], ascending=False).head(20)
        st.dataframe(top, width="stretch", hide_index=True); _table_download(top, "top20_campeones_utilidad.csv")
    with t3:
        from_pdf = pdf_models[pdf_models["Tipo ranking"].isin(["Sugerido cero", "Mayor inversión"])].copy() if not pdf_models.empty else pd.DataFrame()
        if not from_pdf.empty:
            from_pdf["Índice lento"] = from_pdf["Inversión"] / (from_pdf["VPD sugerida"] + 0.1)
            slow = from_pdf.sort_values(["Índice lento", "Inversión", "DDI"], ascending=False).drop_duplicates(["Tienda", "ID_ART"]).head(20)
        else:
            slow = ranked[ranked["Existencia"].gt(0)].copy()
            slow["Índice lento"] = slow["Inversión"] / (slow["VPD"] + 0.1)
            slow = slow.sort_values(["Índice lento", "Días inventario"], ascending=False).head(20)
        st.dataframe(slow, width="stretch", hide_index=True); _table_download(slow, "top20_modelos_lentos.csv")


def render_locations(co: pd.DataFrame):
    st.title("Análisis por Ubicación y Sección")
    data = commercial_model(co)
    summary = _select_pdf_week(load_pdf_summary(False), "commercial_location_pdf_week")
    if data.empty and summary.empty: st.warning("No hay PDF ni capacidades procesadas."); return
    data, summary, _, _, _ = _commercial_filters(data, summary, "commercial_location")
    _combined_metrics(data, summary)
    pdf_view = summary[summary["Dimensión"].isin(["Ubicación", "Sección", "Rubro"])].copy() if not summary.empty else pd.DataFrame()
    if not pdf_view.empty:
        hierarchy = pdf_view[pdf_view["Dimensión"].isin(["Sección", "Rubro"])].copy()
        if not hierarchy.empty:
            fig = px.sunburst(hierarchy, path=["Dimensión", "Sección", "Elemento"], values="Sugerido 7", color="% participación utilidad", color_continuous_scale="RdYlGn", title="Sugerido y participación por sección/rubro")
        else:
            fig = px.bar(pdf_view, x="Elemento", y="Sugerido 7", color="% participación venta $", color_continuous_scale="RdYlGn", title="Sugerido y participación por ubicación")
        st.plotly_chart(fig, width="stretch")
        cols = ["Tienda", "Dimensión", "Sección", "Elemento", "ID activos", "Existencia", "Sugerido 7", "VPD sugerida", "DDI", "DDC", "Doblado", "Colgado", "Brazos/Posiciones", "% participación venta $", "% participación utilidad"]
        st.dataframe(pdf_view[[c for c in cols if c in pdf_view]], width="stretch", hide_index=True)
        _table_download(pdf_view, "analisis_ubicacion_seccion_pdf.csv")
    elif not data.empty:
        group = _aggregate(data, ["UBICACION_COMERCIAL", "SECCION_CONSOLIDADA"])
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
    visible = ["tienda", "archivo", "fecha_reporte", "paginas", "registros_resumen", "registros_modelos", "estado_extraccion", "fecha_carga"]
    st.dataframe(current[[c for c in visible if c in current]].sort_values("tienda"), width="stretch", hide_index=True)


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
            with st.spinner("Leyendo tablas e integrando indicadores comerciales..."):
                result = save_pdf_batch(files)
            extracted = sum(int(x.get("registros_extraidos", 0)) for x in result["agregados"] + result["reprocesados"])
            if result["agregados"]: st.success(f"Se guardaron y procesaron {len(result['agregados'])} PDF nuevos.")
            if result["reprocesados"]: st.success(f"Se reprocesaron {len(result['reprocesados'])} PDF cargados con la versión anterior.")
            if extracted: st.info(f"{extracted:,} registros comerciales extraídos y disponibles en los tableros.")
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
