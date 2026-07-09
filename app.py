
# -*- coding: utf-8 -*-
import base64
import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from openpyxl import load_workbook

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
    AGGRID_OK = True
except Exception:
    AGGRID_OK = False


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================
st.set_page_config(
    page_title="Indicadores Cambios y Muertos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = Path("data")
UPLOAD_DIR = DATA_DIR / "uploads"
CACHE_DIR = DATA_DIR / "cache"
CONFIG_DIR = DATA_DIR / "config"
ASSETS_DIR = Path("assets")
ACTIVE_FILE = UPLOAD_DIR / "base_activa.xlsx"
META_FILE = CONFIG_DIR / "metadata.json"
DB_FILE = CONFIG_DIR / "usuarios.db"

for p in [DATA_DIR, UPLOAD_DIR, CACHE_DIR, CONFIG_DIR, ASSETS_DIR]:
    p.mkdir(parents=True, exist_ok=True)

MX_TZ = ZoneInfo("America/Mexico_City")
APP_CACHE_VERSION = "v10.8"
AZUL = "#10245F"
ROSA = "#EC007C"
LAVANDA = "#F3F6FB"

PROJECT_STORES = [
    "Arco Norte", "Ecatepec", "Miravalle", "Puebla Sur", "Vallejo",
]


# ============================================================
# UTILIDADES
# ============================================================
def norm_text(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s+", " ", s)
    return s.upper().strip()


STORE_MAP = {
    "ARCO NORTE": "Arco Norte",
    "ECATEPEC": "Ecatepec",
    "MIRAVALLE": "Miravalle",
    "PUEBLA SUR": "Puebla Sur",
    "VALLEJO": "Vallejo",
    "PUEBLA": "Puebla",
    "IZTAPALAPA": "Iztapalapa",
    "TOLUCA": "Toluca",
    "CENTRO": "Centro",
    "QUERETARO": "Querétaro",
    "QUERÉTARO": "Querétaro",
    "LEON": "León",
    "LEÓN": "León",
    "NAUCALPAN": "Naucalpan",
    "OLIVAR": "Olivar",
    "AGUASCALIENTES": "Aguascalientes",
    "VERACRUZ": "Veracruz",
    "IXTAPALUCA": "Ixtapaluca",
    "VALLEJO ": "Vallejo",
}


def canon_store(x):
    if pd.isna(x):
        return ""
    raw = str(x).strip()
    if not raw:
        return ""

    s = norm_text(raw)

    # Alias robustos. Se evalúan primero por contenido para no perder variantes.
    if "MIRAVALLE" in s:
        return "Miravalle"
    if "GUADALAJARA" in s and "MIRAVALLE" in s:
        return "Miravalle"
    if "ARCO" in s and "NORTE" in s:
        return "Arco Norte"
    if "PUEBLA" in s and "SUR" in s:
        return "Puebla Sur"
    if s in ["PUEBLA CENTRO", "PUEBLA CENTRO ROPA"]:
        return "Puebla"
    if "ECATEPEC" in s:
        return "Ecatepec"
    if "VALLEJO" in s:
        return "Vallejo"
    if "IZTAPALAPA" in s:
        return "Iztapalapa"
    if "IXTAPALUCA" in s:
        return "Ixtapaluca"
    if "NAUCALPAN" in s:
        return "Naucalpan"
    if "TOLUCA" in s:
        return "Toluca"
    if "QUERETARO" in s or "QUERÉTARO" in raw.upper():
        return "Querétaro"
    if "LEON" in s or "LEÓN" in raw.upper():
        return "León"
    if "VERACRUZ" in s:
        return "Veracruz"
    if "AGUASCALIENTES" in s:
        return "Aguascalientes"
    if "OLIVAR" in s:
        return "Olivar"
    if "ATEMAJAC" in s:
        return "Atemajac"
    if "SAN LUIS" in s:
        return "San Luis"
    if s == "CENTRO" or "CENTRO HISTORICO" in s or "CENTRO HISTÓRICO" in raw.upper():
        return "Centro"
    if s == "PUEBLA":
        return "Puebla"

    # Mapa original si existe en el archivo
    try:
        for k, v in STORE_MAP.items():
            if norm_text(k) == s:
                return v
    except Exception:
        pass

    # Evitar devolver encabezados o textos que no son tienda.
    invalid = {
        "TIENDA", "DIA", "DÍA", "FECHA", "VENTAS NETA PZS", "DEV PZS",
        "VENTA NETA EN", "VENTA NETA", "CATEGORIA", "SUB CATEGORIA"
    }
    if s in invalid:
        return ""

    return raw.title()



def safe_num(x) -> float:
    if pd.isna(x):
        return 0.0
    s = str(x).strip().replace("$", "").replace(",", "").replace(" ", "")
    if s in ["", "-", "nan", "None"]:
        return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def parse_date(x):
    if pd.isna(x):
        return pd.NaT

    def _finish(d):
        if pd.isna(d):
            return pd.NaT
        return pd.to_datetime(d).normalize()

    if isinstance(x, (datetime, date)):
        return _finish(x)

    if isinstance(x, (int, float)) and 20000 < float(x) < 60000:
        d = pd.to_datetime(x, unit="D", origin="1899-12-30", errors="coerce")
        return _finish(d)

    s = str(x).strip()
    if not s or s.lower() in ["nan", "none", "-"]:
        return pd.NaT

    # ISO con hora: 2026-04-20 17:48:26
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        d = pd.to_datetime(s, errors="coerce", dayfirst=False)
        return _finish(d)

    # dd/mm/yyyy o textos de Excel en español.
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    return _finish(d)



def fmt_num(x):
    return f"{safe_num(x):,.0f}"


def fmt_money(x):
    return f"${safe_num(x):,.0f}"


def fmt_pct(x):
    return f"{safe_num(x):.1f}%"


def hash_password(pwd):
    return hashlib.sha256(str(pwd).encode("utf-8")).hexdigest()


def logo_html():
    logo = ASSETS_DIR / "price_shoes_logo.png"
    if logo.exists():
        data = base64.b64encode(logo.read_bytes()).decode("utf-8")
        return f'<img src="data:image/png;base64,{data}" class="ps-logo-img">'
    return '<div class="ps-logo-text">Price<br>Shoes</div>'


# ============================================================
# USUARIOS
# ============================================================
def init_db():
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            nomina TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            permiso TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            activo INTEGER NOT NULL DEFAULT 1,
            creado TEXT
        )
        """
    )
    cur.execute("SELECT COUNT(*) FROM usuarios")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO usuarios VALUES (?,?,?,?,?,?)",
            ("admin", "Administrador", "Administrador", hash_password("admin123"), 1, datetime.now(MX_TZ).isoformat()),
        )
    con.commit()
    con.close()


def get_user(nomina, password):
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("SELECT nomina,nombre,permiso FROM usuarios WHERE nomina=? AND password_hash=? AND activo=1", (nomina, hash_password(password)))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {"nomina": row[0], "nombre": row[1], "permiso": row[2]}


def upsert_user(nomina, nombre, permiso, password):
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO usuarios(nomina,nombre,permiso,password_hash,activo,creado)
        VALUES (?,?,?,?,1,?)
        ON CONFLICT(nomina) DO UPDATE SET
            nombre=excluded.nombre,
            permiso=excluded.permiso,
            password_hash=excluded.password_hash,
            activo=1
        """,
        (str(nomina), nombre, permiso, hash_password(password), datetime.now(MX_TZ).isoformat()),
    )
    con.commit()
    con.close()


def delete_user(nomina):
    if nomina == "admin":
        return
    con = sqlite3.connect(DB_FILE)
    con.execute("DELETE FROM usuarios WHERE nomina=?", (nomina,))
    con.commit()
    con.close()


def list_users():
    con = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT nomina AS Nómina, nombre AS Nombre, permiso AS Permiso, activo AS Activo FROM usuarios ORDER BY nombre", con)
    con.close()
    return df


init_db()


# ============================================================
# ESTILOS
# ============================================================
def apply_styles():
    st.markdown(
        f"""
<style>
:root {{
    --azul:{AZUL};
    --rosa:{ROSA};
}}
html, body, [data-testid="stAppViewContainer"] {{
    background:#F3F6FB;
}}
.block-container {{
    padding-top:0.8rem!important;
    padding-left:1.6rem!important;
    padding-right:1.6rem!important;
    max-width:100%!important;
}}
.ps-top-line {{
    height:6px;
    background:{ROSA};
    margin:0 -1.6rem 18px -1.6rem;
}}
.ps-header {{
    width:100%;
    background:#FFF;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:22px;
    padding:14px 24px 18px 24px;
    box-sizing:border-box;
}}
.ps-header-left {{
    display:flex;
    align-items:center;
    gap:24px;
    min-width:0;
}}
.ps-logo-wrap {{
    width:126px;
    height:82px;
    display:flex;
    align-items:center;
    justify-content:center;
}}
.ps-logo-img {{
    max-width:120px!important;
    max-height:78px!important;
    object-fit:contain!important;
}}
.ps-logo-text {{
    color:{AZUL};
    font-weight:900;
    font-size:26px;
    line-height:1;
}}
.ps-header-sep {{
    width:5px;
    height:86px;
    background:{ROSA};
    border-radius:3px;
}}
.ps-title {{
    color:#1D1259;
    font-weight:900;
    font-size:33px;
    line-height:1.08;
}}
.ps-subtitle {{
    color:#5B6476;
    font-weight:800;
    font-size:15px;
    margin-top:7px;
}}
.ps-header-right {{
    display:flex;
    gap:14px;
    align-items:center;
}}
.ps-meta {{
    min-width:185px;
    background:#F8FAFC;
    border:1px solid #DDE4F0;
    border-radius:0 0 14px 14px;
    padding:12px 16px;
}}
.ps-meta-label {{
    color:#6B7280;
    letter-spacing:5px;
    font-size:12px;
    font-weight:900;
}}
.ps-meta-value {{
    color:#1D1259;
    font-size:18px;
    font-weight:900;
    margin-top:6px;
}}
.ps-tabbar {{
    background:{AZUL};
    border-top:4px solid {ROSA};
    margin:0 -1.6rem 22px -1.6rem;
    padding:0 70px;
    overflow-x:auto;
    white-space:nowrap;
}}
.ps-tabbar [role="radiogroup"] {{
    display:flex!important;
    flex-wrap:nowrap!important;
    gap:0!important;
    min-height:58px!important;
}}
.ps-tabbar label {{
    background:{AZUL}!important;
    color:#C7D2FE!important;
    min-height:58px!important;
    padding:0 18px!important;
    display:flex!important;
    align-items:center!important;
    border-radius:0!important;
    font-weight:900!important;
    white-space:nowrap!important;
}}
.ps-tabbar label:hover {{
    background:#142E73!important;
    color:#FFF!important;
}}
.ps-tabbar label:has(input:checked) {{
    background:#142E73!important;
    color:#FFF!important;
    border-bottom:4px solid {ROSA}!important;
}}
.ps-tabbar label * {{
    color:inherit!important;
    font-weight:900!important;
}}
.ps-kpi-grid {{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(250px,1fr));
    gap:18px;
    margin:18px 0 22px 0;
}}
.ps-kpi-card {{
    background:#FFF;
    border:1px solid #E1E7F0;
    border-radius:14px;
    padding:22px 18px;
    min-height:145px;
    display:flex;
    align-items:center;
    gap:18px;
    box-shadow:0 8px 20px rgba(16,36,95,.06);
    overflow:hidden;
}}
.ps-kpi-icon {{
    width:76px;
    height:76px;
    min-width:76px;
    border-radius:50%;
    color:#FFF;
    font-size:34px;
    display:flex;
    align-items:center;
    justify-content:center;
    font-weight:900;
}}
.ps-kpi-title {{
    color:#17132D;
    font-size:15px;
    font-weight:900;
    line-height:1.2;
}}
.ps-kpi-value {{
    color:{ROSA};
    font-size:30px;
    font-weight:900;
    line-height:1.1;
    margin:8px 0;
}}
.ps-kpi-sub {{
    color:#17132D;
    font-size:13px;
    line-height:1.35;
}}
.panel-title {{
    background:#FFF;
    border:1px solid #E1E7F0;
    border-radius:12px;
    padding:18px 22px;
    margin:18px 0 12px 0;
    font-size:20px;
    font-weight:900;
    color:#17132D;
}}
.ag-header,.ag-header-cell {{
    background:{AZUL}!important;
}}
.ag-header-cell-text,.ag-header-cell-label,.ag-icon {{
    color:#FFF!important;
    fill:#FFF!important;
    font-weight:900!important;
}}
.ag-root-wrapper {{
    border-radius:10px!important;
    border:1px solid #E1E7F0!important;
    overflow:hidden!important;
}}
.ag-cell {{
    font-size:12px!important;
}}
.stButton > button {{
    border-radius:8px!important;
}}
.footer {{
    color:#7A8190;
    font-size:13px;
    margin:36px 0 10px 0;
    border-top:1px solid #DDE4F0;
    padding-top:18px;
}}
@media(max-width:1200px) {{
    .ps-header{{flex-direction:column;align-items:flex-start;}}
    .ps-header-right{{flex-wrap:wrap;}}
    .ps-tabbar{{padding:0 20px;}}
}}

.week-card-grid{{
    display:grid;
    grid-template-columns:repeat(4,minmax(230px,1fr));
    gap:22px;
    margin:16px 0 28px 0;
}}
.week-card{{
    background:#F8F9FC;
    border:1px solid #D9DEE8;
    border-radius:8px;
    overflow:hidden;
    box-shadow:0 5px 14px rgba(16,36,95,.06);
}}
.week-card-head{{
    background:#3E4095;
    color:white;
    text-align:center;
    font-size:20px;
    font-weight:900;
    padding:15px 10px;
}}
.week-row{{
    display:grid;
    grid-template-columns:1fr auto 62px;
    align-items:center;
    gap:12px;
    padding:14px 16px;
    border-bottom:1px solid #E5E7EB;
}}
.week-row span{{
    color:#666;
    font-weight:900;
    font-size:13px;
}}
.week-row b{{
    color:#3E4095;
    font-size:20px;
    font-weight:900;
}}
.week-row em{{
    font-style:normal;
    font-weight:900;
    font-size:12px;
    text-align:right;
}}
@media(max-width:1200px){{
    .week-card-grid{{grid-template-columns:repeat(2,minmax(230px,1fr));}}
}}
@media(max-width:700px){{
    .week-card-grid{{grid-template-columns:1fr;}}
}}

</style>
""",
        unsafe_allow_html=True,
    )


def render_header():
    now = datetime.now(MX_TZ)
    user_name = st.session_state.get("user", {}).get("nombre", "Consulta")
    st.markdown(
        f"""
<div class="ps-top-line"></div>
<div class="ps-header">
    <div class="ps-header-left">
        <div class="ps-logo-wrap">{logo_html()}</div>
        <div class="ps-header-sep"></div>
        <div>
            <div class="ps-title">Indicadores Cambios y Muertos</div>
            <div class="ps-subtitle">Recuperación · Productividad · Conversión</div>
        </div>
    </div>
    <div class="ps-header-right">
        <div class="ps-meta"><div class="ps-meta-label">FECHA</div><div class="ps-meta-value">🗓️ {now.strftime('%d/%m/%Y')}</div></div>
        <div class="ps-meta"><div class="ps-meta-label">USUARIO</div><div class="ps-meta-value">👑 {user_name}</div></div>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )


# ============================================================
# ARCHIVOS Y CACHE
# ============================================================
def save_uploaded_file(uploaded):
    ACTIVE_FILE.write_bytes(uploaded.getbuffer())
    META_FILE.write_text(
        json.dumps(
            {
                "nombre_original": uploaded.name,
                "fecha_carga": datetime.now(MX_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                "mtime": ACTIVE_FILE.stat().st_mtime,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    clear_cache_files()


def clear_cache_files():
    for p in CACHE_DIR.glob("*"):
        try:
            p.unlink()
        except Exception:
            pass
    st.cache_data.clear()


def delete_active_file():
    if ACTIVE_FILE.exists():
        ACTIVE_FILE.unlink()
    if META_FILE.exists():
        META_FILE.unlink()
    clear_cache_files()


def cache_paths():
    return {
        "op": CACHE_DIR / "op.parquet",
        "co": CACHE_DIR / "co.parquet",
        "diag": CACHE_DIR / "diag.parquet",
        "meta": CACHE_DIR / "cache_meta.json",
    }


def cache_valid():
    paths = cache_paths()
    if not ACTIVE_FILE.exists() or not paths["meta"].exists() or not paths["op"].exists() or not paths["co"].exists():
        return False
    try:
        meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
        return float(meta.get("mtime", 0)) == float(ACTIVE_FILE.stat().st_mtime) and meta.get("version") == APP_CACHE_VERSION
    except Exception:
        return False


def write_cache(op, co, diag):
    paths = cache_paths()
    op.to_parquet(paths["op"], index=False)
    co.to_parquet(paths["co"], index=False)
    diag.to_parquet(paths["diag"], index=False)
    paths["meta"].write_text(
        json.dumps({"mtime": ACTIVE_FILE.stat().st_mtime, "version": APP_CACHE_VERSION, "procesado": datetime.now(MX_TZ).strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@st.cache_data(show_spinner=False)
def read_cache(mtime):
    paths = cache_paths()
    op = pd.read_parquet(paths["op"]) if paths["op"].exists() else pd.DataFrame()
    co = pd.read_parquet(paths["co"]) if paths["co"].exists() else pd.DataFrame()
    diag = pd.read_parquet(paths["diag"]) if paths["diag"].exists() else pd.DataFrame()
    return op, co, diag


# ============================================================
# PROCESAMIENTO DEL EXCEL
# ============================================================
def find_col(cols, names):
    norm_cols = {norm_text(c): c for c in cols}
    for n in names:
        nn = norm_text(n)
        if nn in norm_cols:
            return norm_cols[nn]
    for c in cols:
        cn = norm_text(c)
        if any(norm_text(n) in cn for n in names):
            return c
    return None


def apply_nombre_map(op, plantilla):
    if op.empty or plantilla.empty or "Nombre" not in op.columns:
        return op
    p = plantilla.copy()
    c_nom = find_col(p.columns, ["Nombre"])
    if not c_nom:
        return op
    aliases = {}
    for full in p[c_nom].dropna().astype(str):
        first = full.split()[0]
        aliases[norm_text(first)] = full.strip()
        if norm_text(first).startswith("ELO"):
            aliases["ELO"] = full.strip()
        if norm_text(first).startswith("IVON") or norm_text(first).startswith("IVONNE"):
            aliases["IVON"] = full.strip()
    op["Nombre Real"] = op["Nombre"].astype(str).map(lambda x: aliases.get(norm_text(x), str(x).strip()))
    return op


def read_operation_sheet(file_path):
    # Sólo lee la hoja operativa, no todo el libro.
    sheet = "Resultados productividad"
    try:
        df = pd.read_excel(file_path, sheet_name=sheet, engine="openpyxl")
    except Exception:
        xls = pd.ExcelFile(file_path, engine="openpyxl")
        cand = [s for s in xls.sheet_names if "RESULTADOS" in norm_text(s) and "PRODUCT" in norm_text(s)]
        if not cand:
            return pd.DataFrame(), pd.DataFrame([{"Hoja": "Resultados productividad", "Estado": "No encontrada"}])
        sheet = cand[0]
        df = pd.read_excel(file_path, sheet_name=sheet, engine="openpyxl")

    c_fecha = find_col(df.columns, ["Fecha", "Fecha s", "Fecha captura", "Día", "Dia"])
    c_tienda = find_col(df.columns, ["Tienda"])
    c_actividad = find_col(df.columns, ["Actividad Realizada", "Actividad"])
    c_motivo = find_col(df.columns, ["Motivo de ingreso", "Motivo"])
    c_piezas = find_col(df.columns, ["Número de Piezas", "Numero de Piezas", "Piezas", "Cantidad"])
    c_nombre = find_col(df.columns, ["Nombre", "Usuario", "Colaborador"])
    c_occ = find_col(df.columns, ["Occurrence", "Ocurrence", "Ocurrencia", "Folio"])

    if not c_fecha or not c_tienda or not c_piezas:
        return pd.DataFrame(), pd.DataFrame([{"Hoja": sheet, "Estado": "Faltan columnas Fecha/Tienda/Piezas"}])

    op = pd.DataFrame()
    op["Fecha"] = df[c_fecha].map(parse_date)
    op["Tienda"] = df[c_tienda].map(canon_store)
    op["Actividad"] = df[c_actividad].astype(str) if c_actividad else ""
    op["Motivo"] = df[c_motivo].astype(str) if c_motivo else ""
    op["Piezas"] = df[c_piezas].map(safe_num)
    op["Nombre"] = df[c_nombre].astype(str).fillna("") if c_nombre else ""
    op["Occurrence"] = df[c_occ].astype(str).fillna("") if c_occ else ""
    op = op.dropna(subset=["Fecha"])
    op = op[op["Tienda"].astype(str).str.strip() != ""]
    op["Semana ISO"] = op["Fecha"].dt.isocalendar().week.astype(int)
    op["Mes"] = op["Fecha"].dt.to_period("M").astype(str)

    diag = pd.DataFrame([{
        "Hoja": sheet,
        "Estado": "OK",
        "Filas": len(op),
        "Fecha": str(c_fecha),
        "Tienda": str(c_tienda),
        "Piezas": str(c_piezas),
        "Actividad": str(c_actividad),
        "Motivo": str(c_motivo),
    }])
    return op, diag


def read_plantilla(file_path):
    try:
        return pd.read_excel(file_path, sheet_name="Plantilla", engine="openpyxl")
    except Exception:
        return pd.DataFrame()


def read_monthly_dev(file_path, progress=None):
    """
    Lector comercial mensual v10.7 por bloques de fecha.

    Estructura:
    fila superior = fecha
    fila encabezado = Ventas Neta Pzs / Dev Pzs / Venta Neta $
    datos = tienda + valores por fecha
    """
    wb = load_workbook(file_path, read_only=True, data_only=True)
    monthly_sheets = [
        s for s in wb.sheetnames
        if s not in ["Resultados productividad", "Plantilla"]
        and re.search(r"(ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPT|OCT|NOV|DIC|ENERO|FEBR|MARZO|26|25)", norm_text(s))
    ]

    all_records = []
    diag_rows = []
    total_sheets = max(1, len(monthly_sheets))

    for idx_sheet, sheet_name in enumerate(monthly_sheets, start=1):
        if progress:
            progress.progress(min(idx_sheet / total_sheets, 0.95), text=f"Leyendo comercial por bloques: {sheet_name}")

        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 3:
            diag_rows.append({"Hoja": sheet_name, "Estado": "Hoja sin datos", "Registros": 0, "Dev Pzs": 0})
            continue

        max_cols = max(len(r) for r in rows[:30])
        top_rows = [list(r) + [None] * (max_cols - len(r)) for r in rows[:30]]

        header_idx = None
        tienda_col = None

        for ridx, row in enumerate(top_rows):
            tienda_cols = [i for i, v in enumerate(row) if norm_text(v) == "TIENDA"]
            has_dev = any(("DEV" in norm_text(v) and "PZS" in norm_text(v)) for v in row)
            if tienda_cols and has_dev:
                header_idx = ridx
                tienda_col = tienda_cols[0]
                break

        if header_idx is None:
            diag_rows.append({"Hoja": sheet_name, "Estado": "No encontró Tienda + Dev Pzs", "Registros": 0, "Dev Pzs": 0})
            continue

        header_row = list(rows[header_idx]) + [None] * (max_cols - len(rows[header_idx]))
        date_row = list(rows[header_idx - 1]) + [None] * (max_cols - len(rows[header_idx - 1])) if header_idx > 0 else [None] * max_cols

        # Forward fill de fecha: si la fecha está en DG, también aplica a DH y DI.
        date_by_col = {}
        current_date = pd.NaT
        for c in range(max_cols):
            d = parse_date(date_row[c])
            if pd.notna(d):
                current_date = d
            date_by_col[c] = current_date

        blocks = {}
        for c, h in enumerate(header_row):
            hnorm = norm_text(h)
            fecha = date_by_col.get(c, pd.NaT)
            if pd.isna(fecha):
                continue

            if "DEV" in hnorm and "PZS" in hnorm:
                blocks.setdefault(fecha, {})["dev_col"] = c
            elif ("VENTA" in hnorm or "VENTAS" in hnorm) and ("PZS" in hnorm or "NETA" in hnorm) and "$" not in str(h):
                blocks.setdefault(fecha, {})["vta_pzs_col"] = c
            elif ("VENTA" in hnorm or "NETA" in hnorm) and ("$" in str(h) or "IMP" in hnorm or " EN " in f" {hnorm} "):
                blocks.setdefault(fecha, {})["vta_imp_col"] = c

        blocks = {fecha: cols for fecha, cols in blocks.items() if cols}

        if not blocks:
            diag_rows.append({
                "Hoja": sheet_name,
                "Estado": "No encontró bloques comerciales",
                "Fila encabezado": header_idx + 1,
                "Col Tienda": tienda_col + 1,
                "Registros": 0,
                "Dev Pzs": 0
            })
            continue

        acc = {}
        sheet_dev = 0.0
        sheet_vta_pzs = 0.0
        sheet_vta_imp = 0.0
        lecturas = 0
        tiendas = set()

        for raw in rows[header_idx + 1:]:
            row = list(raw) + [None] * (max_cols - len(raw))
            if tienda_col >= len(row):
                continue

            tienda = canon_store(row[tienda_col])
            if not tienda:
                continue
            tiendas.add(tienda)

            for fecha, cols in blocks.items():
                dev = safe_num(row[cols["dev_col"]]) if "dev_col" in cols and cols["dev_col"] < len(row) else 0.0
                vta_pzs = safe_num(row[cols["vta_pzs_col"]]) if "vta_pzs_col" in cols and cols["vta_pzs_col"] < len(row) else 0.0
                vta_imp = safe_num(row[cols["vta_imp_col"]]) if "vta_imp_col" in cols and cols["vta_imp_col"] < len(row) else 0.0

                if dev == 0 and vta_pzs == 0 and vta_imp == 0:
                    continue

                key = (sheet_name, fecha, tienda)
                if key not in acc:
                    acc[key] = {"Dev_Pzs": 0.0, "Vta_Pzs": 0.0, "Vta_Imp": 0.0}
                acc[key]["Dev_Pzs"] += dev
                acc[key]["Vta_Pzs"] += vta_pzs
                acc[key]["Vta_Imp"] += vta_imp

                sheet_dev += dev
                sheet_vta_pzs += vta_pzs
                sheet_vta_imp += vta_imp
                lecturas += 1

        for (hoja, fecha, tienda), vals in acc.items():
            all_records.append({
                "Hoja": hoja,
                "Fecha": fecha,
                "Tienda": tienda,
                "Dev_Pzs": vals["Dev_Pzs"],
                "Vta_Pzs": vals["Vta_Pzs"],
                "Vta_Imp": vals["Vta_Imp"],
                "Costo_Dev": 0.0,
                "ID": "",
                "Color": "",
            })

        diag_rows.append({
            "Hoja": sheet_name,
            "Estado": "OK",
            "Fila encabezado": header_idx + 1,
            "Fila fechas": header_idx,
            "Col Tienda": tienda_col + 1,
            "Fechas detectadas": len(blocks),
            "Registros agrupados": len(acc),
            "Lecturas con valor": lecturas,
            "Tiendas detectadas": len(tiendas),
            "Dev Pzs": sheet_dev,
            "Venta Pzs": sheet_vta_pzs,
            "Venta $": sheet_vta_imp,
        })

    wb.close()

    co = pd.DataFrame(all_records)
    if not co.empty:
        co["Fecha"] = pd.to_datetime(co["Fecha"])
        co["Tienda"] = co["Tienda"].map(canon_store)
        co["Semana ISO"] = co["Fecha"].dt.isocalendar().week.astype(int)
        co["Mes"] = co["Fecha"].dt.to_period("M").astype(str)

    return co, pd.DataFrame(diag_rows)



def process_excel(file_path):
    progress = st.progress(0, text="Iniciando procesamiento...")
    progress.progress(0.10, text="Leyendo hoja Resultados productividad...")
    op, diag_op = read_operation_sheet(file_path)

    progress.progress(0.25, text="Leyendo Plantilla...")
    plantilla = read_plantilla(file_path)
    op = apply_nombre_map(op, plantilla)

    progress.progress(0.35, text="Leyendo hojas mensuales Dev Pzs...")
    co, diag_co = read_monthly_dev(file_path, progress=progress)

    progress.progress(0.90, text="Guardando cache optimizado...")
    diag = pd.concat([diag_op, diag_co], ignore_index=True)
    write_cache(op, co, diag)
    progress.progress(1.0, text="Archivo procesado correctamente.")
    return op, co, diag



def split_operation(op):
    if op.empty:
        return op
    df = op.copy()
    act = df["Actividad"].map(norm_text)
    mot = df["Motivo"].map(norm_text)

    # Regla exacta solicitada:
    # Muertos sólo cuenta cuando Actividad Realizada es Recolección de muertos
    # Y Motivo de ingreso es Muertos.
    es_recoleccion_muertos = act.str.contains("RECOLECCION DE MUERTOS|RECOLECCIÓN DE MUERTOS", na=False)
    es_motivo_muertos = mot.str.contains("MUERTO", na=False)

    df["Muertos"] = np.where(es_recoleccion_muertos & es_motivo_muertos, df["Piezas"], 0)
    df["Cajas"] = np.where(mot.str.contains("CAJA", na=False), df["Piezas"], 0)
    df["Probador"] = np.where(mot.str.contains("PROBADOR", na=False) | act.str.contains("PROBADOR", na=False), df["Piezas"], 0)
    df["Recolectadas"] = np.where(act.str.contains("RECOLECCION|RECOLECCIÓN", na=False), df["Piezas"], 0)
    df["Habilitadas"] = np.where(act.str.contains("ACONDICION|HABILIT", na=False), df["Piezas"], 0)
    df["Ubicadas"] = np.where(act.str.contains("UBIC", na=False), df["Piezas"], 0)
    return df



def filter_stores(df, stores=None):
    if df.empty or not stores:
        return df
    return df[df["Tienda"].isin(stores)]


def table_by_store(op, co, start_date, end_date, stores=None):
    op2 = split_operation(op)
    start = pd.to_datetime(start_date).normalize()
    end = pd.to_datetime(end_date).normalize()
    stores_list = stores or PROJECT_STORES

    op_p = op2[(op2["Fecha"] >= start) & (op2["Fecha"] <= end)] if not op2.empty else op2
    op_p = filter_stores(op_p, stores_list)

    co_p = co[(co["Fecha"] >= start) & (co["Fecha"] <= end)] if not co.empty else co
    co_p = filter_stores(co_p, stores_list)

    # Pendiente anterior: sólo día anterior al inicio del periodo.
    prev_day = start - pd.Timedelta(days=1)
    op_prev = op2[(op2["Fecha"] >= prev_day) & (op2["Fecha"] <= prev_day)] if not op2.empty else op2
    op_prev = filter_stores(op_prev, stores_list)

    co_prev = co[(co["Fecha"] >= prev_day) & (co["Fecha"] <= prev_day)] if not co.empty else co
    co_prev = filter_stores(co_prev, stores_list)

    rows = []
    for t in stores_list:
        dev = co_p.loc[co_p["Tienda"].eq(t), "Dev_Pzs"].sum() if not co_p.empty and "Dev_Pzs" in co_p else 0
        prev_dev = co_prev.loc[co_prev["Tienda"].eq(t), "Dev_Pzs"].sum() if not co_prev.empty and "Dev_Pzs" in co_prev else 0

        o = op_p[op_p["Tienda"].eq(t)] if not op_p.empty else pd.DataFrame()
        prev = op_prev[op_prev["Tienda"].eq(t)] if not op_prev.empty else pd.DataFrame()

        muertos = o["Muertos"].sum() if not o.empty else 0
        cajas = o["Cajas"].sum() if not o.empty else 0
        prob = o["Probador"].sum() if not o.empty else 0
        reco = o["Recolectadas"].sum() if not o.empty else 0
        hab = o["Habilitadas"].sum() if not o.empty else 0
        ubic = o["Ubicadas"].sum() if not o.empty else 0

        prev_muertos = prev["Muertos"].sum() if not prev.empty else 0
        prev_cajas = prev["Cajas"].sum() if not prev.empty else 0
        prev_prob = prev["Probador"].sum() if not prev.empty else 0
        prev_total_ing = prev_dev + prev_muertos + prev_cajas + prev_prob
        prev_ubic = prev["Ubicadas"].sum() if not prev.empty else 0
        pend_ant = max(prev_total_ing - prev_ubic, 0)

        ingresos_dia = dev + muertos + cajas + prob
        total_base = ingresos_dia + pend_ant

        pend_hab = max(total_base - hab, 0)
        pend_ub = max(total_base - ubic, 0)
        pct_hab = hab / total_base * 100 if total_base else 0
        pct_ub = ubic / total_base * 100 if total_base else 0

        rows.append({
            "Tienda": t,
            "Dev pzs": dev,
            "Muertos": muertos,
            "Cajas": cajas,
            "Probador": prob,
            "Total": total_base,
            "Pend. Ant.": pend_ant,
            "Recolectadas": reco,
            "Habilitadas": hab,
            "Pend. Hab.": pend_hab,
            "% Acond.": pct_hab,
            "Ubicadas": ubic,
            "Pend. Ub.": pend_ub,
            "% Ubic.": pct_ub,
        })
    return pd.DataFrame(rows)



def summary_from_table(df):
    if df.empty:
        return {"Ingresos":0,"Acondicionado":0,"Ubicado":0,"Pendiente":0,"% Procesado":0}
    ingresos = df["Total"].sum()
    hab = df["Habilitadas"].sum()
    ubic = df["Ubicadas"].sum()
    pend = df["Pend. Ub."].sum()
    pct = ubic / (ingresos + df["Pend. Ant."].sum()) * 100 if (ingresos + df["Pend. Ant."].sum()) else 0
    return {"Ingresos": ingresos, "Acondicionado": hab, "Ubicado": ubic, "Pendiente": pend, "% Procesado": pct}


def format_display(df):
    if df is None or df.empty:
        return df
    out = df.copy()
    for c in out.columns:
        if c == "Tienda" or c in ["Nombre", "Nombre Real", "Actividad"]:
            continue
        if "%" in str(c):
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).map(fmt_pct)
        elif "$" in str(c) or "Importe" in str(c) or "Venta" in str(c):
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).map(fmt_money)
        else:
            ser = pd.to_numeric(out[c], errors="coerce")
            if ser.notna().mean() > 0.75:
                out[c] = ser.fillna(0).map(fmt_num)
    return out


# ============================================================
# COMPONENTES VISUALES
# ============================================================
def aggrid_table(df, height=360, editable=False, key=None):
    if df is None or df.empty:
        st.info("Sin información para mostrar.")
        return df
    show = format_display(df)
    auto_height = min(max(118 + len(show) * 34, 170), height)

    if not AGGRID_OK:
        st.dataframe(show, hide_index=True, width="stretch", height=auto_height)
        return df

    gb = GridOptionsBuilder.from_dataframe(show)
    gb.configure_default_column(filter=True, sortable=True, resizable=True, editable=editable, minWidth=105)
    if "Tienda" in show.columns:
        gb.configure_column("Tienda", pinned="left", minWidth=145)
    for col in show.columns:
        if col != "Tienda":
            gb.configure_column(col, type=["rightAligned"], minWidth=105)
    opts = gb.build()
    opts["rowHeight"] = 34
    opts["headerHeight"] = 38
    opts["enableCellTextSelection"] = True
    opts["suppressRowClickSelection"] = True
    opts["getRowStyle"] = JsCode("""
        function(params) {
            if (params.node.rowIndex % 2 === 0) { return {'backgroundColor':'#FFFFFF'}; }
            return {'backgroundColor':'#F8FAFC'};
        }
    """)
    css = {
        ".ag-header": {"background-color": f"{AZUL} !important"},
        ".ag-header-cell": {"background-color": f"{AZUL} !important", "color": "#FFFFFF !important", "font-weight": "900 !important"},
        ".ag-header-cell-text": {"color": "#FFFFFF !important", "font-weight": "900 !important"},
        ".ag-icon": {"color": "#FFFFFF !important", "fill": "#FFFFFF !important"},
        ".ag-root-wrapper": {"border": "1px solid #E1E7F0 !important", "border-radius": "10px !important", "overflow": "hidden !important"},
        ".ag-cell": {"font-size": "12px !important"},
    }
    result = AgGrid(
        show,
        gridOptions=opts,
        height=auto_height,
        width="100%",
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True,
        custom_css=css,
        theme="alpine",
        key=key or f"ag_{abs(hash(str(show.columns.tolist())+str(len(show))))}",
            )
    if editable and result and "data" in result:
        return pd.DataFrame(result["data"])
    return df


def panel(title, df, height=360, editable=False):
    st.markdown(f'<div class="panel-title">{title}</div>', unsafe_allow_html=True)
    return aggrid_table(df, height=height, editable=editable, key=f"panel_{norm_text(title)}")


def kpis(res):
    vals = [
        ("↻", "Piezas Ingresadas", fmt_num(res.get("Ingresos", 0)), "Dev + muertos + cajas + probador", ROSA),
        ("✓", "Piezas Acondicionadas", fmt_num(res.get("Acondicionado", 0)), "Acondicionado", "#3720B8"),
        ("⊕", "Piezas Ubicadas", fmt_num(res.get("Ubicado", 0)), "Ubicado", "#F59E0B"),
        ("⌛", "Pendientes por Ubicar", fmt_num(res.get("Pendiente", 0)), "Ingreso + pendiente ant. - ubicado", "#05B957"),
        ("%", "% Procesado", fmt_pct(res.get("% Procesado", 0)), "Ubicado / base", "#3720B8"),
    ]
    html = '<div class="ps-kpi-grid">'
    for icon, title, val, sub, color in vals:
        html += (
            '<div class="ps-kpi-card">'
            f'<div class="ps-kpi-icon" style="background:{color};">{icon}</div>'
            '<div><div class="ps-kpi-title">'+title+'</div>'
            f'<div class="ps-kpi-value">{val}</div>'
            f'<div class="ps-kpi-sub">{sub}</div></div></div>'
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def combined_chart(df, title):
    if df is None or df.empty:
        return
    ymax = max(float(pd.to_numeric(df[c], errors="coerce").fillna(0).max()) for c in ["Total", "Habilitadas", "Ubicadas"])
    ymax = ymax * 1.18 if ymax > 0 else 10
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["Tienda"], y=df["Total"], mode="lines+markers+text", name="Total ingresos",
        text=df["Total"].map(lambda x: f"{x:,.0f}"), textposition="top center",
        textfont=dict(color="#111827", size=12, family="Arial Black"),
        line=dict(color="#1D3F8F", width=3)
    ))
    fig.add_trace(go.Bar(
        x=df["Tienda"], y=df["Habilitadas"], name="Pzas Habilitadas", marker_color="#4C00C9",
        text=df["Habilitadas"].map(lambda x: f"{x:,.0f}"), textposition="outside",
        textfont=dict(color="#111827", size=12, family="Arial Black")
    ))
    fig.add_trace(go.Bar(
        x=df["Tienda"], y=df["Ubicadas"], name="Pzas Ubicadas", marker_color=ROSA,
        text=df["Ubicadas"].map(lambda x: f"{x:,.0f}"), textposition="outside",
        textfont=dict(color="#111827", size=12, family="Arial Black")
    ))
    fig.update_layout(
        title=title, barmode="group", height=470, plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h", y=1.10, x=1, xanchor="right"),
        margin=dict(l=10, r=10, t=70, b=100), dragmode=False
    )
    fig.update_xaxes(tickangle=-45, showgrid=False, fixedrange=True)
    fig.update_yaxes(showgrid=True, gridcolor="#E5E7EB", fixedrange=True, range=[0, ymax])
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})


def download_pdf_button(label="Descargar PDF"):
    st.button(label, help="PDF en preparación para la siguiente versión modular.")


# ============================================================
# SIDEBAR / LOGIN
# ============================================================
def login_sidebar():
    st.sidebar.markdown("## 🔐 Acceso")
    if "user" in st.session_state:
        user = st.session_state.user
        st.sidebar.success(f"Sesión activa: {user['nombre']}")
        st.sidebar.caption(f"Permiso: {user['permiso']}")
        if st.sidebar.button("Cerrar sesión"):
            del st.session_state["user"]
            st.rerun()
        return True

    st.sidebar.info("Para visualizar la información, inicia sesión con un usuario autorizado.")
    nom = st.sidebar.text_input("Nómina / Usuario")
    pwd = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Iniciar sesión", type="primary", width="stretch"):
        user = get_user(nom, pwd)
        if user:
            st.session_state.user = user
            st.rerun()
        else:
            st.sidebar.error("Usuario o contraseña incorrectos.")
    return False


def sidebar_data_admin():
    st.sidebar.divider()
    st.sidebar.markdown("## 📁 Fuente de datos")
    meta = {}
    if META_FILE.exists():
        try:
            meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception:
            meta = {}

    if ACTIVE_FILE.exists():
        st.sidebar.success("Archivo cargado")
        st.sidebar.write(meta.get("nombre_original", ACTIVE_FILE.name))
        st.sidebar.caption(meta.get("fecha_carga", ""))
        if cache_valid():
            cm = json.loads(cache_paths()["meta"].read_text(encoding="utf-8"))
            st.sidebar.caption(f"Procesado: {cm.get('procesado','')}")
        else:
            st.sidebar.warning("Pendiente de procesar")
    else:
        st.sidebar.warning("No hay archivo cargado")

    if st.session_state.get("user", {}).get("permiso") == "Administrador":
        up = st.sidebar.file_uploader("Cargar/Reemplazar Excel", type=["xlsx"])
        if up is not None and st.sidebar.button("Guardar archivo", type="primary"):
            save_uploaded_file(up)
            st.sidebar.success("Archivo guardado. Ahora presiona Procesar archivo activo.")
            st.rerun()

        if ACTIVE_FILE.exists() and not cache_valid():
            if st.sidebar.button("Procesar archivo activo", type="primary", width="stretch"):
                try:
                    process_excel(str(ACTIVE_FILE))
                    st.success("Archivo procesado correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error("No fue posible procesar el archivo.")
                    st.exception(e)
                    st.stop()

        if ACTIVE_FILE.exists() and st.sidebar.button("Borrar archivo persistido"):
            delete_active_file()
            st.rerun()

    st.sidebar.markdown(
        '<div style="background:#EAF1FF;border-radius:12px;padding:16px;margin-top:24px;"><b style="color:#4F46E5;">🛡️ CONFIDENCIAL</b><br>Price Shoes | Operaciones Ropa</div>',
        unsafe_allow_html=True
    )


# ============================================================
# PÁGINAS
# ============================================================
PAGES = [
    "Resumen", "Por Día", "Reporte Semanal", "Reporte Mensual", "Conversión",
    "Recuperación Económica", "Productividad", "Recorridos", "Ranking", "Macro",
    "Diagnóstico", "Configuración", "Usuarios",
]


def nav_bar():
    st.markdown('<div class="ps-tabbar">', unsafe_allow_html=True)
    page = st.radio("Pestañas", PAGES, horizontal=True, label_visibility="collapsed", key="nav_v10")
    st.markdown("</div>", unsafe_allow_html=True)
    return page


def executive_week_cards(op, co):
    if op.empty:
        return
    max_week = int(op["Semana ISO"].max())
    weeks = list(range(max_week - 3, max_week + 1))

    html = '<div style="margin:18px 0 8px 0;font-size:24px;font-weight:900;color:#3E4095;">📊 Resumen Ejecutivo</div>'
    html += '<div class="week-card-grid">'
    prev_ing = None
    prev_hab = None
    prev_ub = None

    for w in weeks:
        dates = op.loc[op["Semana ISO"].eq(w), "Fecha"]
        if dates.empty:
            continue

        df = table_by_store(op, co, dates.min(), dates.max(), PROJECT_STORES)
        ingresos = df["Total"].sum()
        hab = df["Habilitadas"].sum()
        ub = df["Ubicadas"].sum()
        recorridos = len(op[(op["Semana ISO"].eq(w)) & (op["Actividad"].map(norm_text).str.contains("RECORRIDO|RECOLECCION|RECOLECCIÓN", na=False))])

        def delta(cur, prev):
            if prev is None or prev == 0:
                return "—", "#6B7280"
            d = (cur - prev) / prev * 100
            icon = "▲" if d >= 0 else "▼"
            color = "#00A651" if d >= 0 else "#EC004F"
            return f"{icon} {abs(d):.1f}%", color

        d_ing, c_ing = delta(ingresos, prev_ing)
        d_hab, c_hab = delta(hab, prev_hab)
        d_ub, c_ub = delta(ub, prev_ub)

        html += (
            f'<div class="week-card">'
            f'<div class="week-card-head">Sem {w}</div>'
            f'<div class="week-row"><span>INGRESOS</span><b>{ingresos:,.0f}</b><em style="color:{c_ing};">{d_ing}</em></div>'
            f'<div class="week-row"><span>ACONDICIONADO</span><b>{hab:,.0f}</b><em style="color:{c_hab};">{d_hab}</em></div>'
            f'<div class="week-row"><span>UBICADO</span><b>{ub:,.0f}</b><em style="color:{c_ub};">{d_ub}</em></div>'
            f'<div class="week-row"><span>RECORRIDOS</span><b>{recorridos:,.0f}</b><em>—</em></div>'
            f'</div>'
        )
        prev_ing, prev_hab, prev_ub = ingresos, hab, ub

    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)



def page_resumen(op, co):
    st.markdown("## Dashboard Ejecutivo")
    st.caption("Vista general de indicadores principales.")
    today = pd.to_datetime(op["Fecha"].max()) if not op.empty else pd.Timestamp.today()
    start = today - pd.Timedelta(days=27)
    df = table_by_store(op, co, start, today, PROJECT_STORES)
    kpis(summary_from_table(df))
    executive_week_cards(op, co)
    combined_chart(df, "Ingreso vs Habilitado vs Ubicado por tienda")



def page_por_dia(op, co):
    st.markdown("## Por Día")
    st.caption("Ingresos, pendientes y avance por tienda.")
    default_date = pd.to_datetime(op["Fecha"].max()).date() if not op.empty else date.today()
    d = st.date_input("Fecha", value=default_date, key="dia_fecha")
    df = table_by_store(op, co, d, d, PROJECT_STORES)
    st.caption(f"Registros detectados: operación {len(op[op['Fecha'].eq(pd.to_datetime(d))]) if not op.empty else 0:,} | Dev Pzs mensual {co.loc[co['Fecha'].eq(pd.to_datetime(d)), 'Dev_Pzs'].sum() if not co.empty else 0:,.0f}")
    kpis(summary_from_table(df))
    download_pdf_button()
    panel("Tabla por tienda - Por Día", df, height=360)
    combined_chart(df, "Ingreso vs Habilitado vs Ubicado por tienda")


def page_semanal(op, co):
    st.markdown("## Reporte Semanal")
    weeks = sorted(op["Semana ISO"].dropna().unique().tolist()) if not op.empty else [datetime.now().isocalendar().week]
    tiendas = st.multiselect("Tiendas", PROJECT_STORES, default=PROJECT_STORES)
    w = st.selectbox("Semana ISO", weeks, index=len(weeks)-1)
    dates = op.loc[op["Semana ISO"].eq(w), "Fecha"] if not op.empty else pd.Series(dtype="datetime64[ns]")
    if dates.empty:
        st.info("Sin fechas para la semana seleccionada.")
        return
    df = table_by_store(op, co, dates.min(), dates.max(), tiendas)
    kpis(summary_from_table(df))
    download_pdf_button()
    panel(f"Tabla por tienda - Semana {w}", df, height=360)
    combined_chart(df, f"Ingreso vs Habilitado vs Ubicado - Semana {w}")


def page_mensual(op, co):
    st.markdown("## Reporte Mensual")
    meses = sorted(op["Mes"].dropna().unique().tolist()) if not op.empty else []
    tiendas = st.multiselect("Tiendas", PROJECT_STORES, default=PROJECT_STORES, key="mes_tiendas")
    if not meses:
        st.info("Sin meses detectados.")
        return
    m = st.selectbox("Mes", meses, index=len(meses)-1)
    dates = op.loc[op["Mes"].eq(m), "Fecha"]
    df = table_by_store(op, co, dates.min(), dates.max(), tiendas)
    kpis(summary_from_table(df))
    download_pdf_button()
    panel(f"Tabla por tienda - Mes {m}", df, height=360)
    combined_chart(df, f"Ingreso vs Habilitado vs Ubicado - Mes {m}")


def page_conversion(op, co):
    st.markdown("## Conversión Semanal Dev → Venta")
    st.caption("Se respeta semana ISO por tienda. La conversión real requiere ventas por ID/color/semana en el archivo.")
    if co.empty:
        st.info("Sin información comercial mensual.")
        return
    weeks = sorted(co["Semana ISO"].dropna().unique().tolist())
    w = st.multiselect("Semana ISO", weeks, default=weeks[-1:])
    df = co[co["Semana ISO"].isin(w)].groupby(["Semana ISO","Tienda"], as_index=False).agg({"Dev_Pzs":"sum","Vta_Pzs":"sum","Vta_Imp":"sum"})
    df["Pend. Conv."] = df["Dev_Pzs"] - df["Vta_Pzs"]
    df["% Conv."] = np.where(df["Dev_Pzs"]>0, df["Vta_Pzs"]/df["Dev_Pzs"]*100, 0)
    df = df.rename(columns={"Dev_Pzs":"Dev Pzs", "Vta_Pzs":"Conv. Pzs", "Vta_Imp":"Conv. $"})
    panel("Detalle Conversión", df, height=420)


def page_recuperacion(op, co):
    st.markdown("## Recuperación Económica")
    if co.empty:
        st.info("Sin información comercial mensual.")
        return
    weeks = sorted(co["Semana ISO"].dropna().unique().tolist())
    w = st.multiselect("Semana ISO", weeks, default=weeks[-1:], key="rec_sem")
    df = co[co["Semana ISO"].isin(w)].groupby(["Semana ISO","Tienda"], as_index=False).agg({"Vta_Imp":"sum","Dev_Pzs":"sum"})
    df = df.rename(columns={"Vta_Imp":"Recuperación $", "Dev_Pzs":"Dev Pzs"})
    panel("Recuperación Económica", df, height=420)


def page_productividad(op, co):
    st.markdown("## Productividad")
    if op.empty:
        st.info("Sin operación.")
        return
    c1, c2 = st.columns(2)
    with c1:
        start = st.date_input("Fecha inicio", value=pd.to_datetime(op["Fecha"].min()).date(), key="prod_ini")
    with c2:
        end = st.date_input("Fecha final", value=pd.to_datetime(op["Fecha"].max()).date(), key="prod_fin")
    tiendas = st.multiselect("Tienda", PROJECT_STORES, default=PROJECT_STORES, key="prod_tiendas")
    o = split_operation(op)
    o = o[(o["Fecha"] >= pd.to_datetime(start)) & (o["Fecha"] <= pd.to_datetime(end))]
    o = filter_stores(o, tiendas)
    name_col = "Nombre Real" if "Nombre Real" in o.columns else "Nombre"
    df = o.groupby(["Tienda", name_col], as_index=False).agg({"Piezas":"sum", "Habilitadas":"sum", "Ubicadas":"sum", "Recolectadas":"sum"})
    df = df.rename(columns={name_col:"Colaborador"})
    panel("Productividad por colaborador", df.sort_values("Piezas", ascending=False), height=500)


def page_recorridos(op, co):
    st.markdown("## Recorridos")
    if op.empty:
        return
    o = op[op["Actividad"].map(norm_text).str.contains("RECORRIDO|RECOLECCION|RECOLECCIÓN", na=False)]
    df = o.groupby(["Semana ISO","Tienda"], as_index=False).size().rename(columns={"size":"Recorridos"})
    df["Meta"] = 47
    df["% Cumplimiento"] = df["Recorridos"] / 47 * 100
    panel("Recorridos por semana", df, height=420)


def page_ranking(op, co):
    st.markdown("## Ranking")
    if op.empty:
        return
    o = split_operation(op)
    df = o.groupby("Tienda", as_index=False).agg({"Piezas":"sum", "Habilitadas":"sum", "Ubicadas":"sum"})
    df["Score"] = (df["Habilitadas"] + df["Ubicadas"]) / df["Piezas"].replace(0, np.nan) * 100
    df["Score"] = df["Score"].fillna(0)
    panel("Ranking de tiendas", df.sort_values("Score", ascending=False), height=420)


def page_macro(op, co):
    st.markdown("## Macro")
    page_resumen(op, co)


def page_diagnostico(op, co, diag):
    st.markdown("## Diagnóstico")
    st.info("Alias activo: Miravalle también reconoce Guadalajara Miravalle, GDL Miravalle y variantes con Miravalle.")
    st.write(f"Operación: {len(op):,} registros")
    st.write(f"Comercial mensual Dev Pzs: {len(co):,} registros agrupados | Dev Pzs total: {co['Dev_Pzs'].sum() if not co.empty else 0:,.0f}")
    panel("Diagnóstico de hojas", diag, height=420)
    if not co.empty:
        dev_diag = co.groupby(["Fecha", "Tienda"], as_index=False)[["Dev_Pzs", "Vta_Pzs", "Vta_Imp"]].sum().sort_values(["Fecha","Tienda"])
        panel("Validación Comercial por fecha y tienda", dev_diag.tail(300), height=520)
        ecatepec_2806 = dev_diag[(dev_diag["Tienda"].eq("Ecatepec")) & (dev_diag["Fecha"].eq(pd.Timestamp("2026-06-28")))]
        if not ecatepec_2806.empty:
            st.success(f"Validación Ecatepec 28/06/2026 Dev Pzs: {ecatepec_2806['Dev_Pzs'].sum():,.0f}")



def page_configuracion():
    st.markdown("## Configuración")
    st.info("Configuración de metas y orden de pestañas en preparación modular.")
    st.write("Meta productividad diaria: 784")
    st.write("Meta recorridos semanal: 47")


def page_usuarios():
    st.markdown("## Usuarios")
    if st.session_state.get("user", {}).get("permiso") != "Administrador":
        st.warning("Sólo administrador.")
        return

    with st.form("crear_usuario"):
        st.subheader("Crear / actualizar usuario")
        nom = st.text_input("Nómina / Usuario")
        nombre = st.text_input("Nombre")
        permiso = st.selectbox("Tipo de permiso", ["Consulta", "Administrador"])
        pwd = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Guardar usuario", type="primary")
        if submitted and nom and nombre and pwd:
            upsert_user(nom, nombre, permiso, pwd)
            st.success("Usuario guardado.")
            st.rerun()

    users = list_users()
    panel("Usuarios registrados", users, height=360)

    del_nom = st.text_input("Nómina a eliminar")
    if st.button("Eliminar usuario") and del_nom:
        delete_user(del_nom)
        st.success("Usuario eliminado.")
        st.rerun()


# ============================================================
# MAIN
# ============================================================
apply_styles()
render_header()

if not login_sidebar():
    st.markdown(
        """
<div style="max-width:760px;margin:70px auto;background:#FFF;border-radius:24px;padding:42px;border:1px solid #DDE4F0;box-shadow:0 16px 44px rgba(16,36,95,.08);">
<h1 style="color:#1D1259;margin-top:0;">Acceso al Sistema</h1>
<p style="font-size:18px;color:#5B6476;">Indicadores Operaciones Ropa</p>
<div style="background:#EAF1FF;border:1px solid #D6E4FF;border-radius:16px;padding:22px;color:#10245F;font-weight:800;font-size:18px;">
Para visualizar la información, inicia sesión con un usuario autorizado. Si aún no cuentas con acceso, solicita al Administrador del sistema la creación de tu usuario.
</div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.stop()

sidebar_data_admin()

if not ACTIVE_FILE.exists():
    st.warning("Carga un archivo Excel desde el panel lateral para iniciar.")
    st.stop()

if not cache_valid():
    st.warning("El archivo está cargado, pero aún no está procesado. Presiona **Procesar archivo activo** en el panel lateral.")
    st.stop()

op_all, co_all, diag_df = read_cache(ACTIVE_FILE.stat().st_mtime)

page = nav_bar()

ROUTES = {
    "Resumen": lambda: page_resumen(op_all, co_all),
    "Por Día": lambda: page_por_dia(op_all, co_all),
    "Reporte Semanal": lambda: page_semanal(op_all, co_all),
    "Reporte Mensual": lambda: page_mensual(op_all, co_all),
    "Conversión": lambda: page_conversion(op_all, co_all),
    "Recuperación Económica": lambda: page_recuperacion(op_all, co_all),
    "Productividad": lambda: page_productividad(op_all, co_all),
    "Recorridos": lambda: page_recorridos(op_all, co_all),
    "Ranking": lambda: page_ranking(op_all, co_all),
    "Macro": lambda: page_macro(op_all, co_all),
    "Diagnóstico": lambda: page_diagnostico(op_all, co_all, diag_df),
    "Configuración": page_configuracion,
    "Usuarios": page_usuarios,
}

ROUTES.get(page, lambda: page_resumen(op_all, co_all))()

st.markdown('<div class="footer">CONFIDENCIAL | Price Shoes | Operaciones Ropa</div>', unsafe_allow_html=True)
