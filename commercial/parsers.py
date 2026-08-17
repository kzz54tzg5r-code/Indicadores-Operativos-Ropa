"""Lectores tolerantes para ventas, capacidades y PDF comerciales."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd

from .config import STORE_ALIASES


def norm_text(value) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    # Algunos libros .xls antiguos llegan desde Calamine con caracteres NUL
    # intercalados (T\x00I\x00E\x00N\x00D\x00A). Se eliminan antes de comparar
    # encabezados o catálogos para conservar compatibilidad con esos archivos.
    text = str(value).replace("\x00", "")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text).strip().upper()


def canon_store(value) -> str:
    key = norm_text(value)
    if not key:
        return ""
    if key in STORE_ALIASES:
        return STORE_ALIASES[key]
    for alias, canonical in STORE_ALIASES.items():
        if alias in key or key in alias:
            return canonical
    return str(value).strip().title()


def to_number(series, default=0.0):
    if series is None:
        return pd.Series(dtype=float)
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    text = series.astype(str).str.replace(r"[^0-9.\-]", "", regex=True)
    return pd.to_numeric(text, errors="coerce").fillna(default)


def _engine_for(path: Path):
    suffix = path.suffix.lower()
    if suffix == ".xls":
        return ["calamine", "xlrd"]
    if suffix == ".xlsx":
        return ["openpyxl", "calamine"]
    return [None]


def _header_row(path: Path, sheet_name=0) -> int:
    if path.suffix.lower() == ".csv":
        return 0
    keywords = {
        "TIENDA", "MODELO", "ID_ART", "ID ART", "SECCION", "EXISTENCIA",
        "VENTA", "VTA", "MARCA", "FECHA", "SUBCATEGORIA", "SUG 7",
    }
    for engine in _engine_for(path):
        try:
            preview = pd.read_excel(path, sheet_name=sheet_name, header=None, nrows=30, engine=engine)
            best_row, best_score = 0, -1
            for index, row in preview.iterrows():
                values = [norm_text(value) for value in row.tolist()]
                score = sum(any(keyword in value for keyword in keywords) for value in values if value)
                if score > best_score:
                    best_row, best_score = int(index), score
            return best_row
        except Exception:
            continue
    return 0


def _read_sheet(path: Path, sheet_name=0) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        for encoding in ("utf-8-sig", "latin-1"):
            try:
                return pd.read_csv(path, encoding=encoding)
            except Exception:
                continue
        return pd.DataFrame()
    header = _header_row(path, sheet_name)
    last_error = None
    for engine in _engine_for(path):
        try:
            frame = pd.read_excel(path, sheet_name=sheet_name, header=header, engine=engine)
            frame.columns = [str(column).replace("\x00", "") for column in frame.columns]
            for column in frame.select_dtypes(include=["object", "string"]).columns:
                frame[column] = frame[column].map(
                    lambda value: value.replace("\x00", "") if isinstance(value, str) else value
                )
            return frame
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    return pd.DataFrame()


def _sheet_names(path: Path) -> list[str]:
    if path.suffix.lower() == ".csv":
        return ["Datos"]
    for engine in _engine_for(path):
        try:
            return list(pd.ExcelFile(path, engine=engine).sheet_names)
        except Exception:
            continue
    return []


def _column_map(df: pd.DataFrame) -> dict[str, str]:
    return {norm_text(column): column for column in df.columns}


def _find_column(df: pd.DataFrame, candidates: list[str], contains=False):
    mapping = _column_map(df)
    normalized = [norm_text(value) for value in candidates]
    for candidate in normalized:
        if candidate in mapping:
            return mapping[candidate]
    if contains:
        for key, original in mapping.items():
            if any(candidate in key for candidate in normalized):
                return original
    return None


def _series(df: pd.DataFrame, candidates: list[str], default="", contains=False) -> pd.Series:
    column = _find_column(df, candidates, contains=contains)
    if column is None:
        return pd.Series([default] * len(df), index=df.index)
    return df[column]


def _section_group(value) -> str:
    key = norm_text(value)
    if "DAMA" in key:
        return "Dama"
    if "CABALLERO" in key:
        return "Caballero"
    if any(token in key for token in ("NINA", "NINO", "BEBA", "BEBE", "INFANT")):
        return "Infantil"
    return "Sin sección"


def _location_group(pasillo, subcategory, category) -> str:
    text = " ".join(norm_text(value) for value in (pasillo, subcategory, category))
    if any(token in text for token in ("LENCER", "BRASIER", "PANTIB", "BOXER", "BIKINI", "INTERIOR")):
        return "Lencería"
    if "JEAN" in text:
        return "Jeans"
    if any(token in text for token in (
        "COLG", "RACK", "CHAMARRA", "ABRIGO", "SACO", "VESTIDO", "BLUSA",
        "CHALECO", "ENSAMBLE", "PONCHO", "GABARDINA",
    )):
        return "Colgado"
    return "Doblado"


def read_capacity_file(path: str | Path) -> pd.DataFrame:
    """Normaliza el catálogo/capacidades a una fila por tienda y modelo."""
    path = Path(path)
    source = _read_sheet(path, 0)
    if source.empty:
        return pd.DataFrame()

    store = _series(source, ["TIENDA", "SUCURSAL", "TIENDA/SUCURSAL"])
    section_detail = _series(source, ["SECCION", "SECCIÓN"])
    category = _series(source, ["CATEGORIA", "CATEGORÍA"])
    subcategory = _series(source, ["SUBCATEGORIA", "SUBCATEGORÍA"])
    aisle = _series(source, ["PASILLO", "UBICACION", "UBICACIÓN"])
    model = _series(source, ["MODELO", "ID_ART", "ID ART", "ID/Modelo"])
    article_id = _series(source, ["ID_ART", "ID ART", "ID", "CODIGO"])
    wholesale = to_number(_series(source, ["PRECIO MAYOREO", "COSTO", "COSTO UNITARIO"], 0))
    retail = to_number(_series(source, ["PRECIO MENUDEO", "PRECIO VENTA", "PRECIO"], 0))
    offer = to_number(_series(source, ["PRECIO OFERTA"], 0))
    price = offer.where(offer > 0, retail.where(retail > 0, wholesale))

    out = pd.DataFrame(index=source.index)
    out["Tienda"] = store.map(canon_store)
    out["ID_ART"] = article_id.astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    out["Modelo"] = model.astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    out.loc[out["Modelo"].isin(["", "nan", "None"]), "Modelo"] = out["ID_ART"]
    out["Marca"] = _series(source, ["MARCA PRICE", "MARCA"], "Sin marca").astype(str).str.strip()
    out["Sección detalle"] = section_detail.astype(str).str.strip()
    out["Sección"] = section_detail.map(_section_group)
    out["Categoría"] = category.astype(str).str.strip()
    out["Subcategoría"] = subcategory.astype(str).str.strip()
    out["Pasillo"] = aisle.astype(str).replace("nan", "").str.strip()
    out["Ubicación"] = [
        _location_group(p, s, c)
        for p, s, c in zip(out["Pasillo"], out["Subcategoría"], out["Categoría"])
    ]
    out["Existencia piso"] = to_number(_series(source, ["EXISTENCIA PISO", "PISO"], 0))
    out["Existencia bodega"] = to_number(_series(source, ["EXISTENCIA BODEGA", "BODEGA"], 0))
    existence = to_number(_series(source, ["EXISTENCIA TOTAL", "EXISTENCIA"], 0))
    calculated_existence = out["Existencia piso"] + out["Existencia bodega"]
    out["Existencia"] = existence.where(existence > 0, calculated_existence)
    out["VPD"] = to_number(_series(source, ["SUG 7", "SUGERIDO 7", "VPD"], 0))
    out["DDI"] = to_number(_series(source, ["DIAS DE INVENTARIO SUG 7", "DDI", "DIAS STOCK"], 0))
    computed_ddi = out["Existencia"].div(out["VPD"].replace(0, np.nan))
    out["DDI"] = out["DDI"].where(out["DDI"] > 0, computed_ddi).replace([np.inf, -np.inf], np.nan).fillna(0)
    out["Venta pzas 7"] = to_number(_series(source, ["VTA EN PZAS 7", "VENTA PZAS 7"], 0))
    out["Venta pzas 30"] = to_number(_series(source, ["VTA EN PZAS 30", "VENTA PZAS 30", "VTA ACUM MES EN PZAS"], 0))
    out["Venta pzas"] = to_number(_series(source, ["VTA ACUM MES EN PZAS", "VTA EN PZAS 30", "VENTA PZAS"], 0))
    out["Venta $"] = to_number(_series(source, ["VTA ACUM MES EN $", "VTA EN $ 30", "VENTA $", "VTA_IMP"], 0))
    out["Costo unitario"] = wholesale
    out["Precio unitario"] = price
    out["Inversión"] = out["Existencia"] * wholesale
    out["Utilidad %"] = ((price - wholesale).div(price.replace(0, np.nan)) * 100).clip(-100, 100).fillna(0)
    out["Utilidad $"] = out["Venta $"] * out["Utilidad %"] / 100
    out["Capacidad"] = to_number(_series(source, ["CAPACIDAD MAX TIENDA(PV)", "CAPACIDAD", "BANDA OBJETIVO"], 0))
    out["Excedente"] = to_number(_series(source, ["EXCEDENTE A 60 DIAS", "EXCEDENTE"], 0))
    out["Estatus comercial"] = _series(source, ["ESTATUS COMERCIAL", "ESTATUS"], "").astype(str).str.strip()
    out["Fuente"] = path.name

    valid = out["Tienda"].ne("") & ~out["Modelo"].isin(["", "nan", "None"])
    out = out.loc[valid].copy()
    numeric_cols = [
        "Existencia piso", "Existencia bodega", "Existencia", "VPD", "DDI",
        "Venta pzas 7", "Venta pzas 30", "Venta pzas", "Venta $", "Costo unitario",
        "Precio unitario", "Inversión", "Utilidad %", "Utilidad $", "Capacidad", "Excedente",
    ]
    for column in numeric_cols:
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
    return out.reset_index(drop=True)


def _infer_sheet_date(sheet_name: str) -> pd.Timestamp:
    months = {
        "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
        "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
    }
    key = norm_text(sheet_name)
    month = next((number for label, number in months.items() if label in key), None)
    year_match = re.search(r"(?:20)?(\d{2})", key)
    year = 2000 + int(year_match.group(1)) if year_match else datetime.now().year
    if month:
        return pd.Timestamp(year=year, month=month, day=1)
    return pd.NaT


def read_sales_file(path: str | Path) -> pd.DataFrame:
    """Lee libros comerciales en formato largo sin depender de nombres exactos."""
    path = Path(path)
    frames = []
    for sheet_name in _sheet_names(path):
        source = _read_sheet(path, sheet_name if path.suffix.lower() != ".csv" else 0)
        if source.empty:
            continue
        pieces_col = _find_column(source, ["VENTAS NETAS PZS", "VENTA PZS", "VTA_PZS", "VTA PZS", "VTA EN PZAS", "PIEZAS VENDIDAS"], contains=True)
        amount_col = _find_column(source, ["VENTA NETA EN $", "VENTA NETA", "VTA_IMP", "VTA IMP", "VENTA $", "IMPORTE VENTA"], contains=True)
        if pieces_col is None and amount_col is None:
            continue
        out = pd.DataFrame(index=source.index)
        out["Fecha"] = pd.to_datetime(_series(source, ["FECHA", "DIA", "DÍA"]), errors="coerce", dayfirst=True)
        inferred = _infer_sheet_date(str(sheet_name))
        if pd.notna(inferred):
            out["Fecha"] = out["Fecha"].fillna(inferred)
        out["Tienda"] = _series(source, ["TIENDA", "SUCURSAL", "TIENDA/SUCURSAL"]).map(canon_store)
        out["Modelo"] = _series(source, ["MODELO", "ID_ART", "ID ART", "ID/MODELO", "CODIGO"]).astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
        out["Venta pzas"] = to_number(source[pieces_col]) if pieces_col is not None else 0.0
        out["Venta $"] = to_number(source[amount_col]) if amount_col is not None else 0.0
        out["Sección"] = _series(source, ["SECCION", "SECCIÓN"]).map(_section_group)
        out["Ubicación"] = [
            _location_group(p, s, c)
            for p, s, c in zip(
                _series(source, ["PASILLO", "UBICACION", "UBICACIÓN"]),
                _series(source, ["SUBCATEGORIA", "SUBCATEGORÍA"]),
                _series(source, ["CATEGORIA", "CATEGORÍA"]),
            )
        ]
        out["Fuente"] = f"{path.name} · {sheet_name}"
        out = out[(out["Venta pzas"].ne(0) | out["Venta $"].ne(0)) & out["Tienda"].ne("")]
        if not out.empty:
            frames.append(out)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def normalize_existing_sales(source: pd.DataFrame | None) -> pd.DataFrame:
    """Convierte la base comercial ya procesada por ORION al esquema del módulo."""
    if source is None or source.empty:
        return pd.DataFrame()
    out = pd.DataFrame(index=source.index)
    out["Fecha"] = pd.to_datetime(source.get("Fecha"), errors="coerce")
    out["Tienda"] = source.get("Tienda", pd.Series("", index=source.index)).map(canon_store)
    model = source.get("ID/Modelo", source.get("Modelo", pd.Series("", index=source.index)))
    out["Modelo"] = model.astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    out["Venta pzas"] = pd.to_numeric(source.get("Vta_Pzs", source.get("Venta pzas", 0)), errors="coerce").fillna(0)
    out["Venta $"] = pd.to_numeric(source.get("Vta_Imp", source.get("Venta $", 0)), errors="coerce").fillna(0)
    out["Sección"] = "Sin sección"
    out["Ubicación"] = "Sin ubicación"
    out["Fuente"] = source.get("Hoja", "ORION")
    return out[(out["Venta pzas"].ne(0) | out["Venta $"].ne(0)) & out["Tienda"].ne("")].reset_index(drop=True)


def _numbers_after_label(line: str, label: str) -> list[float]:
    portion = line[line.upper().find(label.upper()) + len(label):]
    tokens = re.findall(r"-?\d[\d,]*(?:\.\d+)?", portion)
    values = []
    for token in tokens:
        try:
            values.append(float(token.replace(",", "")))
        except Exception:
            continue
    return values


def _first_page_text(path: Path) -> tuple[str, int]:
    try:
        import pdfplumber
        with pdfplumber.open(path) as document:
            if not document.pages:
                return "", 0
            text = document.pages[0].extract_text(x_tolerance=1, y_tolerance=3, layout=True) or ""
            return text, len(document.pages)
    except Exception:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            text = reader.pages[0].extract_text() if reader.pages else ""
            return text or "", len(reader.pages)
        except Exception:
            return "", 0


def extract_pdf_snapshot(path: str | Path) -> dict:
    """Extrae el resumen que alimenta histórico, secciones y ubicaciones."""
    path = Path(path)
    raw_text, pages = _first_page_text(path)
    text = re.sub(r"[ \t]+", " ", raw_text)
    title_text = re.sub(r"\s+", " ", raw_text)
    store_match = re.search(r"Tienda\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ ]+?)(?:\s{2,}|\n|$)", title_text, re.IGNORECASE)
    store = canon_store(store_match.group(1)) if store_match else ""
    if not store:
        name_key = norm_text(path.stem)
        store = next((canonical for alias, canonical in STORE_ALIASES.items() if alias in name_key), "Tienda sin identificar")

    date_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", raw_text)
    report_date = pd.to_datetime(date_match.group(1), dayfirst=True, errors="coerce") if date_match else pd.NaT
    lines = [re.sub(r"\s+", " ", line).strip() for line in raw_text.splitlines() if line.strip()]
    total_line = next((line for line in lines if line.upper().startswith("TOTAL (GENERAL)")), "")
    total_values = _numbers_after_label(total_line, "Total (General)")
    while len(total_values) < 9:
        total_values.append(0.0)
    models, curve, floor, warehouse, vpd, ddi, ddc, positions, models_per_position = total_values[:9]

    section_rows = []
    section_labels = ["DAMA", "CABALLERO", "NIÑA", "NIÑO", "BEBA", "BEBE", "UNISEX"]
    for label in section_labels:
        line = next((item for item in lines if item.upper().startswith(label + " ")), "")
        values = _numbers_after_label(line, label)
        if len(values) >= 8:
            section_rows.append({
                "Tienda": store,
                "Sección detalle": label.title(),
                "Sección": _section_group(label),
                "Modelos": values[0],
                "Curva": values[1],
                "Piso": values[2],
                "Bodega": values[3],
                "VPD": values[4],
                "DDI": values[5],
                "DDC": values[6],
                "Posiciones": values[7],
                "Existencia": values[2] + values[3],
            })

    location_rows = []
    try:
        location_index = next(i for i, line in enumerate(lines) if "VENTAS POR UBIC" in norm_text(line))
        location_lines = lines[location_index + 1:]
    except StopIteration:
        location_lines = lines
    location_aliases = {
        "DOBLADA": "Doblado", "DOBLADO": "Doblado", "COLGADA": "Colgado",
        "COLGADO": "Colgado", "JEANS": "Jeans", "LENCERIA": "Lencería",
        "LENCERÍA": "Lencería",
    }
    for label, canonical in location_aliases.items():
        line = next((item for item in location_lines if norm_text(item).startswith(norm_text(label) + " ")), "")
        values = _numbers_after_label(line, label)
        if len(values) >= 8:
            location_rows.append({
                "Tienda": store,
                "Ubicación": canonical,
                "Modelos": values[0],
                "Curva": values[1],
                "Piso": values[2],
                "Bodega": values[3],
                "VPD": values[4],
                "DDI": values[5],
                "DDC": values[6],
                "Posiciones": values[7],
                "Existencia": values[2] + values[3],
            })

    if pd.notna(report_date):
        iso = report_date.isocalendar()
        week_key = f"{int(iso.year)}-W{int(iso.week):02d}"
        report_date_text = report_date.strftime("%Y-%m-%d")
    else:
        week_key = "Sin semana"
        report_date_text = ""
    return {
        "store": store,
        "report_date": report_date_text,
        "week": week_key,
        "pages": pages,
        "file": path.name,
        "models": int(models),
        "curve": curve,
        "floor": floor,
        "warehouse": warehouse,
        "existence": floor + warehouse,
        "vpd": vpd,
        "ddi": ddi,
        "ddc": ddc,
        "positions": positions,
        "models_per_position": models_per_position,
        "sections": section_rows,
        "locations": location_rows,
        "status": "Procesado" if total_line and store else "Revisar",
    }
