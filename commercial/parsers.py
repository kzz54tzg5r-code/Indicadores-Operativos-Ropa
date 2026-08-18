"""Lectores tolerantes para ventas, capacidades y PDF comerciales."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd

from .config import PROJECT_STORES, STORE_ALIASES, STORE_FILENAME_ALIASES


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
    for alias, canonical in sorted(STORE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in key or key in alias:
            return canonical
    return str(value).strip().title()


def store_from_filename(path: str | Path) -> str:
    """Obtiene la tienda desde códigos como AC_QRO, AC_TOL o AC_VALL."""
    stem = norm_text(Path(path).stem).replace("-", "_").replace(" ", "_")
    padded = f"_{re.sub(r'_+', '_', stem).strip('_')}_"
    for code, canonical in sorted(
        STORE_FILENAME_ALIASES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if f"_{code}_" in padded:
            return canonical
    return ""


def _store_from_pdf_text(raw_text: str) -> str:
    """Busca el nombre de tienda por línea sin capturar el resto del PDF."""
    canonical_stores = set(PROJECT_STORES)
    for raw_line in raw_text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if "TIENDA" not in norm_text(line):
            continue
        match = re.search(r"\bTIENDA\s*:?-?\s*(.+)$", line, re.IGNORECASE)
        if not match:
            continue
        candidate = canon_store(match.group(1))
        if candidate in canonical_stores:
            return candidate
    return ""


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


PDF_PARSER_VERSION = 3


def _cell(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _pdf_number(value, default=0.0) -> float:
    text = _cell(value)
    if not text or text in {"-", "—"}:
        return float(default)
    # Cuando PDF-XChange une dos renglones en una celda conservamos el primer
    # valor completo. Nunca se suman porcentajes ni métricas ambiguas.
    text = text.split("\n", 1)[0]
    match = re.search(r"-?\d[\d,]*(?:\.\d+)?", text.replace("$", ""))
    if not match:
        return float(default)
    try:
        return float(match.group(0).replace(",", ""))
    except Exception:
        return float(default)


def _header_key(value) -> str:
    key = norm_text(_cell(value))
    if "VALORES #" in key and "ID" in key:
        return "ids"
    if key == "CURVA" or "VALORES CURVA" in key:
        return "curve"
    if key == "PISO":
        return "floor"
    if key == "BODEGA":
        return "warehouse"
    if "EXISTENCIA TOTAL" in key:
        return "existence"
    if "SUG 7" in key or key == "SUG7":
        return "vpd"
    if key == "DDI":
        return "ddi"
    if key == "DDC":
        return "ddc"
    if key in {"POS", "BRAZ", "BRAZ/ POS", "BRAZ/POS"}:
        return "positions"
    if key.startswith("MOD X"):
        return "models_per_position"
    if "PART INVENTARIO" in key:
        return "inventory_share"
    if "PART PZAS" in key:
        return "pieces_share"
    if "PART $" in key:
        return "sales_share"
    if "INVERSION" in key and "%" in str(value):
        return "investment_share"
    if key == "INVERSION":
        return "investment"
    if "UTILIDAD" in key:
        return "utility_share"
    if "PART CURVA" in key:
        return "curve_share"
    if "MUEBLE" in key:
        return "space_share"
    if "ART" in key and "80" in key:
        return "articles_80"
    if key == "DOBLADO" or key == "DOBLADA":
        return "folded_positions"
    if key == "COLGADO" or key == "COLGADA":
        return "hanging_positions"
    return ""


def _metric_record(kind: str, label: str, headers: list, values: list, store: str, **extra) -> dict:
    record = {"kind": kind, "label": _cell(label), "store": store, **extra}
    for header, value in zip(headers, values):
        key = _header_key(header)
        if key:
            record[key] = _pdf_number(value)
    record.setdefault("ids", 0.0)
    record.setdefault("curve", 0.0)
    record.setdefault("floor", 0.0)
    record.setdefault("warehouse", 0.0)
    record["existence"] = record.get("existence", record["floor"] + record["warehouse"])
    record.setdefault("vpd", 0.0)
    record.setdefault("ddi", 0.0)
    record.setdefault("ddc", 0.0)
    record.setdefault("positions", 0.0)
    return record


def _parse_metric_table(table: list, kind: str, store: str, label_index=0, section_index=None) -> list[dict]:
    if not table or len(table) < 3:
        return []
    headers = table[1]
    rows = []
    current_section = ""
    for row in table[2:]:
        if not row:
            continue
        label = _cell(row[label_index] if label_index < len(row) else "")
        if section_index is not None:
            section_value = _cell(row[section_index] if section_index < len(row) else "")
            if section_value:
                current_section = section_value
        if not label or "TOTAL" in norm_text(label):
            continue
        record = _metric_record(
            kind, label, headers[label_index + 1:], row[label_index + 1:], store,
            section_detail=current_section,
            section=_section_group(current_section) if current_section else "",
        )
        if record["ids"] or record["floor"] or record["warehouse"] or record["vpd"]:
            rows.append(record)
    return rows


def _parse_brand_table(table: list, store: str, scope: str) -> list[dict]:
    if not table or len(table) < 3:
        return []
    headers = table[1]
    rows = []
    for row in table[2:]:
        if len(row) < 3:
            continue
        brand = _cell(row[1])
        if not brand or "TOTAL" in norm_text(brand):
            continue
        record = _metric_record("brand", brand, headers[2:], row[2:], store, brand_scope=scope)
        record["rank"] = int(_pdf_number(row[0], len(rows) + 1))
        rows.append(record)
    return rows


def _parse_model_tables(tables: list, store: str, scenario: str) -> list[dict]:
    records = []
    for table in tables or []:
        if not table or len(table) < 3:
            continue
        world = _cell(table[0][0]) or "Sin sección"
        headers = [_header_key(value) for value in table[1]]
        raw_headers = [norm_text(value) for value in table[1]]
        has_rank = not raw_headers[0] or raw_headers[0] in {"#", "RANKING"}
        offset = 1 if has_rank else 0
        for row_number, row in enumerate(table[2:], start=1):
            if len(row) < 10:
                continue
            art_index = offset
            article = _cell(row[art_index])
            if not article or not re.search(r"\d", article):
                continue
            record = {
                "store": store,
                "world": _section_group(world),
                "world_detail": world.title(),
                "scenario": scenario,
                "rank": int(_pdf_number(row[0], row_number)) if has_rank else row_number,
                "article_id": article,
                "model": _cell(row[art_index + 1]),
                "color": _cell(row[art_index + 2]),
                "brand": _cell(row[art_index + 3]),
                "subcategory": _cell(row[art_index + 4]),
            }
            for index, key in enumerate(headers):
                if not key or index >= len(row):
                    continue
                record[key] = _pdf_number(row[index])
            record.setdefault("curve", 0.0)
            record.setdefault("floor", 0.0)
            record.setdefault("warehouse", 0.0)
            record["existence"] = record["floor"] + record["warehouse"]
            record.setdefault("vpd", 0.0)
            record.setdefault("ddi", 0.0)
            record.setdefault("ddc", 0.0)
            record.setdefault("utility_share", 0.0)
            record.setdefault("investment", 0.0)
            records.append(record)
    return records


def _extract_structured_pdf(path: Path, store: str) -> tuple[dict, list[dict], list[dict]]:
    """Extrae tablas comerciales estables de las 23 páginas del AC."""
    breakdowns: dict[str, list[dict]] = {
        "catalog": [], "section": [], "category": [], "product_type": [],
        "status": [], "location": [], "rubro": [],
    }
    brands: list[dict] = []
    models: list[dict] = []
    try:
        import pdfplumber

        with pdfplumber.open(path) as document:
            if not document.pages:
                return breakdowns, brands, models
            first_tables = document.pages[0].extract_tables() or []
            if first_tables:
                wide = first_tables[0]
                if wide and len(wide) >= 3 and len(wide[1]) >= 19:
                    left = [row[:19] for row in wide]
                    breakdowns["catalog"] = _parse_metric_table(left, "catalog", store)
                table_kinds = ["section", "category", "product_type", "status", "location"]
                for kind, table in zip(table_kinds, first_tables[1:6]):
                    breakdowns[kind] = _parse_metric_table(table, kind, store)

            if len(document.pages) >= 3:
                rubro_tables = document.pages[2].extract_tables() or []
                if rubro_tables:
                    table = rubro_tables[0]
                    # La página 3 agrega la sección en la primera columna y el
                    # rubro en la segunda.
                    if len(table) >= 3:
                        headers = table[1]
                        current_section = ""
                        for row in table[2:]:
                            if not row or len(row) < 3:
                                continue
                            if _cell(row[0]):
                                current_section = _cell(row[0])
                            label = _cell(row[1])
                            if not label or "TOTAL" in norm_text(label):
                                continue
                            record = _metric_record(
                                "rubro", label, headers[2:], row[2:], store,
                                section_detail=current_section,
                                section=_section_group(current_section),
                            )
                            if record["ids"] or record["existence"] or record["vpd"]:
                                breakdowns["rubro"].append(record)

            for page_index, scope in ((15, "General"), (17, "Nacional")):
                if page_index < len(document.pages):
                    tables = document.pages[page_index].extract_tables() or []
                    if tables:
                        brands.extend(_parse_brand_table(tables[0], store, scope))

            scenarios = ["Utilidad", "Sugerido / VPD", "Baja rotación", "Inversión"]
            if len(document.pages) >= 4:
                for page, scenario in zip(document.pages[-4:], scenarios):
                    models.extend(_parse_model_tables(page.extract_tables() or [], store, scenario))
    except Exception:
        # El resumen de primera página sigue siendo válido si una tabla cambia
        # de geometría; el error no elimina el resto del corte.
        pass
    return breakdowns, brands, models


def extract_pdf_snapshot(path: str | Path) -> dict:
    """Extrae resumen, dimensiones y rankings de un Análisis Comercial PDF."""
    path = Path(path)
    raw_text, pages = _first_page_text(path)
    text = re.sub(r"[ \t]+", " ", raw_text)
    store = _store_from_pdf_text(raw_text)
    if not store:
        store = store_from_filename(path)
    if not store:
        name_key = norm_text(path.stem)
        store = next(
            (
                canonical
                for alias, canonical in sorted(STORE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True)
                if alias in name_key
            ),
            "Tienda sin identificar",
        )

    date_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", raw_text)
    report_date = pd.to_datetime(date_match.group(1), dayfirst=True, errors="coerce") if date_match else pd.NaT
    lines = [re.sub(r"\s+", " ", line).strip() for line in raw_text.splitlines() if line.strip()]
    total_line = next((line for line in lines if line.upper().startswith("TOTAL (GENERAL)")), "")
    total_values = _numbers_after_label(total_line, "Total (General)")
    while len(total_values) < 9:
        total_values.append(0.0)
    models, curve, floor, warehouse, vpd, ddi, ddc, positions, models_per_position = total_values[:9]

    breakdowns, brands, model_rankings = _extract_structured_pdf(path, store)
    section_rows = []
    for row in breakdowns.get("section", []):
        section_rows.append({
            "Tienda": store, "Sección detalle": row["label"].title(),
            "Sección": _section_group(row["label"]), "Modelos": row["ids"],
            "Curva": row["curve"], "Piso": row["floor"], "Bodega": row["warehouse"],
            "VPD": row["vpd"], "DDI": row["ddi"], "DDC": row["ddc"],
            "Posiciones": row.get("positions", 0), "Existencia": row["existence"],
        })
    location_rows = []
    for row in breakdowns.get("location", []):
        label_key = norm_text(row["label"])
        if "MEZ" in label_key or "JEAN" in label_key:
            canonical = "Jeans"
        elif "COLG" in label_key:
            canonical = "Colgado"
        elif "DOBL" in label_key:
            canonical = "Doblado"
        else:
            canonical = row["label"].title()
        location_rows.append({
            "Tienda": store, "Ubicación": canonical, "Ubicación detalle": row["label"],
            "Modelos": row["ids"], "Curva": row["curve"], "Piso": row["floor"],
            "Bodega": row["warehouse"], "VPD": row["vpd"], "DDI": row["ddi"],
            "DDC": row["ddc"], "Posiciones": row.get("positions", 0),
            "Existencia": row["existence"],
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
        "breakdowns": breakdowns,
        "brands": brands,
        "model_rankings": model_rankings,
        "parser_version": PDF_PARSER_VERSION,
        "status": "Procesado" if total_line and store != "Tienda sin identificar" else "Revisar",
    }
