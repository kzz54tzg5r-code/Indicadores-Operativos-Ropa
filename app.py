
from __future__ import annotations

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import sqlite3
import json
import io
import base64
import re
import unicodedata

import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
try:
    from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
    AGGRID_OK = True
except Exception:
    AGGRID_OK = False



# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="Indicadores Cambios y Muertos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

PRICE_BLUE = "#10245F"
PRICE_BLUE_2 = "#142E73"
PRICE_PINK = "#EC007C"
PRICE_DARK = "#15172F"
PRICE_GREEN = "#00B050"
PRICE_ORANGE = "#FF8C00"
PRICE_PURPLE = "#6D28D9"
PRICE_CYAN = "#06B6D4"
PRICE_RED = "#E11D48"
PRICE_GRAY = "#6B7280"

DATA_DIR = Path("data")
UPLOAD_DIR = DATA_DIR / "uploads"
CONFIG_DIR = DATA_DIR / "config"
ACTIVE_FILE = UPLOAD_DIR / "base_activa.xlsx"
META_FILE = CONFIG_DIR / "metadata.json"
DB_FILE = CONFIG_DIR / "app_config.db"
USERS_BACKUP = CONFIG_DIR / "users_backup.json"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# STORAGE / DB
# ============================================================

def db_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn



def load_users_backup():
    if USERS_BACKUP.exists():
        try:
            data = json.loads(USERS_BACKUP.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


def save_users_backup(users):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        USERS_BACKUP.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def init_db():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            nomina TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            permiso TEXT NOT NULL,
            password TEXT NOT NULL,
            activo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()

    # Usuario inicial de rescate
    cur.execute(
        "INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, ?, ?)",
        ("admin", "Administrador", "Administrador", "admin123", 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )

    # Restaurar usuarios creados desde respaldo local si existe.
    for u in load_users_backup():
        try:
            cur.execute(
                "INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(u.get("nomina", "")).strip(),
                    str(u.get("nombre", "")).strip() or str(u.get("nomina", "")).strip(),
                    str(u.get("permiso", "Consulta")).strip(),
                    str(u.get("password", "")).strip(),
                    int(bool(u.get("activo", True))),
                    str(u.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))),
                ),
            )
        except Exception:
            pass

    for k, v in {
        "productividad_diaria": "784",
        "recorridos_semanal": "47",
        "conversion_meta": "90.0",
        "project_stores": json.dumps(["Arco Norte", "Ecatepec", "Miravalle", "Puebla Sur", "Vallejo"], ensure_ascii=False),
        "tab_order": json.dumps(["Dashboard", "Por Día", "Reporte Semanal", "Reporte Mensual", "Conversión", "Recuperación Económica", "Productividad", "Recorridos", "Rankings", "Macro", "Diagnóstico", "Configuración", "Usuarios"], ensure_ascii=False),
    }.items():
        cur.execute("INSERT OR IGNORE INTO goals VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()

def load_users():
    init_db()
    conn = db_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY permiso DESC, nombre").fetchall()
    conn.close()
    return [dict(r) | {"activo": bool(r["activo"])} for r in rows]


def upsert_user(nomina, nombre, permiso, password=None, activo=True):
    init_db()
    conn = db_conn()
    cur = conn.cursor()
    exists = cur.execute("SELECT nomina, password FROM users WHERE nomina=?", (nomina,)).fetchone()
    if exists:
        if password:
            cur.execute(
                "UPDATE users SET nombre=?, permiso=?, password=?, activo=? WHERE nomina=?",
                (nombre, permiso, password, int(activo), nomina),
            )
        else:
            cur.execute(
                "UPDATE users SET nombre=?, permiso=?, activo=? WHERE nomina=?",
                (nombre, permiso, int(activo), nomina),
            )
    else:
        if not password:
            raise ValueError("Contraseña requerida")
        cur.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
            (nomina, nombre, permiso, password, int(activo), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
    conn.commit()
    # Respaldo JSON de usuarios
    rows = conn.execute("SELECT * FROM users ORDER BY permiso DESC, nombre").fetchall()
    save_users_backup([dict(r) | {"activo": bool(r["activo"])} for r in rows])
    conn.close()


def delete_user(nomina):
    conn = db_conn()
    conn.execute("DELETE FROM users WHERE nomina=?", (nomina,))
    conn.commit()
    rows = conn.execute("SELECT * FROM users ORDER BY permiso DESC, nombre").fetchall()
    save_users_backup([dict(r) | {"activo": bool(r["activo"])} for r in rows])
    conn.close()


def load_goals():
    init_db()
    conn = db_conn()
    rows = conn.execute("SELECT key, value FROM goals").fetchall()
    conn.close()
    d = {r["key"]: r["value"] for r in rows}
    return {
        "productividad_diaria": int(float(d.get("productividad_diaria", 784))),
        "recorridos_semanal": int(float(d.get("recorridos_semanal", 47))),
        "conversion_meta": float(d.get("conversion_meta", 90.0)),
    }


def save_goals(goals):
    conn = db_conn()
    for k, v in goals.items():
        conn.execute("INSERT OR REPLACE INTO goals VALUES (?, ?)", (k, str(v)))
    conn.commit()
    conn.close()



def get_config_value(key, default=None):
    init_db()
    conn = db_conn()
    row = conn.execute("SELECT value FROM goals WHERE key=?", (key,)).fetchone()
    conn.close()
    if row is None:
        return default
    return row["value"]


def set_config_value(key, value):
    init_db()
    conn = db_conn()
    conn.execute("INSERT OR REPLACE INTO goals VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_project_stores():
    raw = get_config_value("project_stores", "[]")
    default = ["Arco Norte", "Ecatepec", "Miravalle", "Puebla Sur", "Vallejo"]
    try:
        stores = json.loads(raw)
        clean = []
        valid_norm = {norm_text(x): x for x in PROJECT_TIENDAS}
        for x in stores:
            t = canon_tienda(x)
            # Evita que se guarden/usen occurrences o números como tiendas.
            if norm_text(t) in valid_norm:
                clean.append(valid_norm[norm_text(t)])
        # Si el historial guardó occurrence IDs, se descartan y vuelve al proyecto base.
        return sorted(set(clean), key=lambda v: PROJECT_TIENDAS.index(v) if v in PROJECT_TIENDAS else 999) if clean else default
    except Exception:
        return default

def save_project_stores(stores):
    valid_norm = {norm_text(x): x for x in PROJECT_TIENDAS}
    clean = []
    for x in stores:
        t = canon_tienda(x)
        if norm_text(t) in valid_norm:
            clean.append(valid_norm[norm_text(t)])
    set_config_value("project_stores", json.dumps(sorted(set(clean), key=lambda v: PROJECT_TIENDAS.index(v)), ensure_ascii=False))

def get_tab_order():
    default = ["Dashboard", "Por Día", "Reporte Semanal", "Reporte Mensual", "Conversión", "Recuperación Económica", "Productividad", "Recorridos", "Rankings", "Macro", "Diagnóstico", "Configuración", "Usuarios"]
    raw = get_config_value("tab_order", json.dumps(default, ensure_ascii=False))
    try:
        order = json.loads(raw)
        clean = [x for x in order if x in default]
        clean = clean + [x for x in default if x not in clean]
        return clean
    except Exception:
        return default

def save_tab_order(order):
    default = ["Dashboard", "Por Día", "Reporte Semanal", "Reporte Mensual", "Conversión", "Recuperación Económica", "Productividad", "Recorridos", "Rankings", "Macro", "Diagnóstico", "Configuración", "Usuarios"]
    clean = [x for x in order if x in default] + [x for x in default if x not in order]
    set_config_value("tab_order", json.dumps(clean, ensure_ascii=False))


def save_uploaded_file(uploaded_file):
    with open(ACTIVE_FILE, "wb") as f:
        f.write(uploaded_file.getbuffer())
    META_FILE.write_text(json.dumps({
        "nombre_original": uploaded_file.name,
        "fecha_carga": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def get_metadata():
    if META_FILE.exists():
        try:
            return json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def delete_active_file():
    if ACTIVE_FILE.exists():
        ACTIVE_FILE.unlink()
    if META_FILE.exists():
        META_FILE.unlink()
    st.cache_data.clear()


# ============================================================
# UTILIDADES
# ============================================================

def norm_text(x):
    s = "" if x is None else str(x).strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s+", " ", s)
    return s.upper()



PROJECT_TIENDAS = [
    "Iztapalapa", "Vallejo", "Ecatepec", "Toluca", "Arco Norte", "Ixtapaluca",
    "Querétaro", "Centro", "Olivar", "León", "Puebla", "Puebla Sur",
    "Aguascalientes", "Veracruz", "Naucalpan", "Miravalle", "Atemajac"
]
TIENDA_MAP = {norm_text(t): t for t in PROJECT_TIENDAS}
# Variantes frecuentes
TIENDA_MAP.update({
    "QUERETARO": "Querétaro",
    "LEON": "León",
    "PUEBLA SUR": "Puebla Sur",
    "ARCO NORTE": "Arco Norte",
    "VALLEJO": "Vallejo",
    "ECATEPEC": "Ecatepec",
    "MIRAVALLE": "Miravalle",
    "PUEBLA": "Puebla",
})


def canon_tienda(x):
    s = "" if x is None else str(x).strip()
    if not s or s.upper() == "NAN":
        return ""
    n = norm_text(s)
    if n in TIENDA_MAP:
        return TIENDA_MAP[n]
    # Buscar tienda dentro de textos largos como ocurrencia/sucursal
    for k, v in TIENDA_MAP.items():
        if k and k in n:
            return v
    return s.title()



def exact_col(df, name):
    target = norm_text(name)
    for c in df.columns:
        if norm_text(c) == target:
            return c
    return None


def pick_first_existing(df, names):
    for n in names:
        c = exact_col(df, n)
        if c is not None:
            return c
    return None


def tienda_candidate_cols(df):
    cols = []
    for c in df.columns:
        nc = norm_text(c)
        if nc == "TIENDA" or nc.startswith("TIENDA."):
            cols.append(c)
    return cols


def best_tienda_col(df):
    candidates = tienda_candidate_cols(df)
    if not candidates:
        return find_col(df, ["Tienda", "Sucursal"])

    valid = [norm_text(x) for x in PROJECT_TIENDAS]
    best = candidates[0]
    best_score = -10**9

    for c in candidates:
        s = df[c].astype(str).fillna("").str.strip()
        n = s.map(norm_text)
        numeric_ratio = pd.to_numeric(s, errors="coerce").notna().mean() if len(s) else 1
        store_hits = 0
        for v in valid:
            store_hits += n.str.contains(v, na=False).sum()
        non_empty = (s != "").sum()
        score = store_hits * 100 + non_empty - numeric_ratio * len(s) * 50
        if score > best_score:
            best_score = score
            best = c
    return best


def best_occurrence_col(df):
    # Si hay columna explícita de occurrence/ocurrencia, usarla.
    c = pick_first_existing(df, ["Occurrence", "Ocurrencia", "Ba"]) if "pick_first_existing" in globals() else None
    if c is not None:
        return c
    # Si una columna Tienda es numérica, esa es el folio/Occurrence.
    for c in tienda_candidate_cols(df):
        s = df[c].astype(str).str.strip()
        numeric_ratio = pd.to_numeric(s, errors="coerce").notna().mean() if len(s) else 0
        if numeric_ratio > 0.70:
            return c
    return None

def find_col(df, candidates):
    norm_cols = {norm_text(c): c for c in df.columns}
    for cand in candidates:
        n = norm_text(cand)
        if n in norm_cols:
            return norm_cols[n]
    for c in df.columns:
        nc = norm_text(c)
        if any(norm_text(cand) in nc for cand in candidates):
            return c
    return None


def to_number(s):
    try:
        return pd.to_numeric(s, errors="coerce").fillna(0)
    except Exception:
        return 0


def fmt_num(v):
    try:
        return f"{float(v):,.0f}"
    except Exception:
        return "0"


def fmt_pct(v):
    try:
        return f"{float(v):,.1f}%"
    except Exception:
        return "0.0%"


def fmt_money(v):
    try:
        return f"${float(v):,.0f}"
    except Exception:
        return "$0"


def safe_div(a, b):
    try:
        return (float(a) / float(b) * 100) if float(b) else 0
    except Exception:
        return 0


def pct_clip(v):
    try:
        return max(0, min(100, float(v)))
    except Exception:
        return 0


# ============================================================
# CSS / UI
# ============================================================

def apply_styles():
    st.markdown(f"""
    <style>
    .stApp {{ background:#F3F6FA; }}
    .block-container {{ max-width:100% !important; padding:0 1.6rem 2rem 1.6rem !important; }}
    section[data-testid="stSidebar"] {{ background:#FFFFFF; border-right:1px solid #DDE3EE; }}
    section[data-testid="stSidebar"] > div {{ padding-top:1rem; }}

    .top-header {{
        background:#FFFFFF; border-bottom:4px solid {PRICE_PINK};
        padding:18px 28px; display:grid; grid-template-columns:150px 1fr 460px;
        gap:26px; align-items:center; margin:0 -1.6rem 0 -1.6rem;
    }}
    .logo-fallback {{ font-weight:950; color:{PRICE_BLUE}; font-size:25px; line-height:.9; text-align:center; }}
    .header-title {{ border-left:4px solid {PRICE_PINK}; padding-left:22px; }}
    .header-title .small {{ color:{PRICE_PINK}; font-weight:900; letter-spacing:5px; font-size:13px; text-transform:uppercase; }}
    .header-title .big {{ color:{PRICE_BLUE}; font-weight:950; font-size:32px; line-height:1; letter-spacing:-.5px; }}
    .header-title .sub {{ color:#596174; font-weight:650; font-size:14px; margin-top:4px; }}
    .header-controls {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
    .header-card {{ background:#F8FAFC; border:1px solid #DCE3EF; border-radius:14px; padding:12px 14px; }}
    .header-card label {{ display:block; color:{PRICE_GRAY}; font-size:11px; font-weight:800; text-transform:uppercase; letter-spacing:1.4px; }}
    .header-card div {{ color:{PRICE_BLUE}; font-size:17px; font-weight:950; margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}

    div[data-testid="stSegmentedControl"] {{
        background:{PRICE_BLUE};
        border-top:4px solid {PRICE_PINK};
        padding:0;
        margin:0 -1.6rem 18px -1.6rem;
        overflow-x:auto;
        white-space:nowrap;
        display:block;
        border-radius:0 !important;
        box-shadow:0 10px 22px rgba(29,46,110,.18);
    }}
    div[data-testid="stSegmentedControl"] > div {{
        background:{PRICE_BLUE} !important;
        border-radius:0 !important;
        gap:0 !important;
        flex-wrap:nowrap !important;
    }}
    div[data-testid="stSegmentedControl"] button {{
        border-radius:0 !important;
        border:none !important;
        background:{PRICE_BLUE} !important;
        color:#DDE8FF !important;
        padding:15px 23px !important;
        font-weight:900 !important;
        font-size:15px !important;
        border-bottom:4px solid transparent !important;
        white-space:nowrap !important;
        box-shadow:none !important;
    }}
    div[data-testid="stSegmentedControl"] button:hover {{
        background:#233B86 !important;
        color:white !important;
    }}
    div[data-testid="stSegmentedControl"] button[aria-pressed="true"] {{
        color:white !important;
        background:#233B86 !important;
        border-bottom-color:{PRICE_PINK} !important;
    }}

    .section-title {{ color:{PRICE_DARK}; font-size:31px; line-height:1.05; font-weight:950; margin:10px 0 6px 0; }}
    .section-subtitle {{ color:{PRICE_GRAY}; font-size:15px; font-weight:550; margin-bottom:18px; }}
    .filter-card {{ background:#FFFFFF; border:1px solid #E1E7F0; border-radius:18px; padding:16px; margin-bottom:20px; box-shadow:0 8px 18px rgba(17,24,39,.04); }}
    .hero-blue {{ background:linear-gradient(135deg, {PRICE_BLUE} 0%, #2546A8 70%, {PRICE_PINK} 160%); border-radius:22px; padding:24px; color:#FFFFFF; margin-bottom:20px; box-shadow:0 18px 38px rgba(29,46,110,.25); }}
    .hero-blue h2 {{ margin:0; font-size:28px; font-weight:950; color:#FFFFFF; }}
    .hero-blue p {{ margin:6px 0 0 0; color:#E7ECFF; font-weight:650; }}
    .hero-grid {{ display:grid; grid-template-columns:repeat(5, 1fr); gap:12px; margin-top:18px; }}
    .hero-mini {{ background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.20); border-radius:15px; padding:12px; }}
    .hero-mini-label {{ opacity:.78; font-size:12px; font-weight:850; }}
    .hero-mini-value {{ font-size:20px; font-weight:950; margin-top:3px; }}

    .kpi-grid {{ display:grid; grid-template-columns:repeat(5, 1fr); gap:16px; margin-bottom:20px; }}
    .kpi-card {{ background:#FFFFFF; border:1px solid #E1E7F0; border-radius:20px; padding:18px; box-shadow:0 10px 24px rgba(17,24,39,.06); min-height:165px; position:relative; overflow:hidden; }}
    .kpi-card:after {{ content:""; position:absolute; right:-35px; top:-35px; width:100px; height:100px; border-radius:50%; background:var(--soft); }}
    .kpi-top {{ display:flex; align-items:center; gap:12px; position:relative; z-index:1; }}
    .kpi-icon {{ width:52px; height:52px; border-radius:16px; display:flex; align-items:center; justify-content:center; background:var(--accent); color:#FFFFFF; font-size:23px; font-weight:950; box-shadow:0 10px 22px var(--shadow); }}
    .kpi-label {{ color:var(--accent); font-size:14px; line-height:1.1; font-weight:950; }}
    .kpi-value {{ color:{PRICE_DARK}; font-size:28px; font-weight:950; margin-top:16px; letter-spacing:-.5px; position:relative; z-index:1; }}
    .kpi-note {{ color:{PRICE_GRAY}; font-size:13px; font-weight:650; margin-top:5px; }}
    .progress {{ height:9px; background:#EDF2F7; border-radius:99px; margin-top:14px; overflow:hidden; }}
    .progress > div {{ height:100%; background:var(--accent); width:var(--pct); border-radius:99px; }}
    .delta {{ display:inline-block; margin-top:10px; padding:5px 9px; border-radius:10px; background:var(--soft); color:var(--accent); font-size:12px; font-weight:950; }}

    .panel {{ background:#FFFFFF; border:1px solid #E1E7F0; border-radius:20px; padding:20px; box-shadow:0 10px 24px rgba(17,24,39,.05); margin-bottom:18px; }}
    .panel-title {{ color:{PRICE_DARK}; font-size:18px; font-weight:950; margin-bottom:14px; }}

    .week-grid {{ display:grid; grid-template-columns:repeat(4, 1fr); gap:16px; margin-bottom:20px; }}
    .week-card {{ background:#FFFFFF; border:1px solid #E1E7F0; border-radius:18px; overflow:hidden; box-shadow:0 10px 22px rgba(17,24,39,.06); }}
    .week-head {{ background:#3F3F91; color:#FFFFFF; padding:13px 16px; text-align:center; font-weight:950; }}
    .week-line {{ display:grid; grid-template-columns:1fr auto auto; gap:10px; align-items:center; padding:12px 16px; border-bottom:1px solid #EDF2F7; }}
    .week-label {{ color:#666; font-size:12px; font-weight:900; text-transform:uppercase; }}
    .week-value {{ color:#3F3F91; font-size:17px; font-weight:950; }}
    .week-delta {{ font-size:11px; font-weight:950; }}

    .rank-row {{ display:grid; grid-template-columns:150px 1fr 72px; gap:12px; align-items:center; padding:10px 0; border-bottom:1px solid #EDF2F7; }}
    .rank-name {{ color:{PRICE_DARK}; font-weight:850; font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .rankbar {{ height:10px; background:#EDF2F7; border-radius:99px; overflow:hidden; }}
    .rankbar-fill {{ height:100%; background:var(--accent); width:var(--w); border-radius:99px; }}
    .rank-value {{ text-align:right; color:{PRICE_DARK}; font-weight:950; font-size:13px; }}

    .login-wrap {{ min-height:72vh; display:flex; align-items:center; justify-content:center; }}
    .login-card {{ width:min(680px, 92vw); background:white; border:1px solid #DDE3EE; border-radius:26px; padding:34px; box-shadow:0 18px 45px rgba(17,24,39,.10); }}
    .login-title {{ color:{PRICE_BLUE}; font-size:34px; font-weight:950; line-height:1.05; margin-bottom:8px; }}
    .login-sub {{ color:#6B7280; font-size:16px; font-weight:600; margin-bottom:20px; }}
    .login-alert {{ background:#EEF5FF; border:1px solid #DBEAFE; color:{PRICE_BLUE}; border-radius:16px; padding:16px; font-weight:750; margin-bottom:18px; }}

    /* Navegación por st.tabs estable */


    /* Ajuste visual ligero estilo tablero ejecutivo */
    html, body, .stApp {{
        font-size:14px !important;
    }}
    .top-header {{
        padding:14px 26px !important;
        grid-template-columns:130px 1fr 420px !important;
    }}
    .header-title .small {{
        font-size:11px !important;
        letter-spacing:4px !important;
    }}
    .header-title .big {{
        font-size:29px !important;
        font-weight:900 !important;
    }}
    .header-title .sub {{
        font-size:13px !important;
    }}
    .header-card {{
        padding:10px 13px !important;
        border-radius:12px !important;
    }}
    .header-card div {{
        font-size:15px !important;
    }}
    .section-title {{
        font-size:25px !important;
        font-weight:900 !important;
        letter-spacing:0 !important;
    }}
    .section-subtitle {{
        font-size:13px !important;
    }}
    div[data-testid="stMetric"] {{
        background:#FFFFFF;
        border:1px solid #D9E2F0;
        border-radius:16px;
        padding:14px 16px;
        box-shadow:0 8px 20px rgba(16,36,95,.06);
    }}
    div[data-testid="stMetricLabel"] p {{
        color:#4B5563 !important;
        font-size:13px !important;
        font-weight:700 !important;
    }}
    div[data-testid="stMetricValue"] {{
        color:#1F2937 !important;
        font-size:28px !important;
        font-weight:700 !important;
    }}
    .panel {{
        border-radius:15px !important;
        padding:16px !important;
        box-shadow:0 8px 20px rgba(16,36,95,.05) !important;
    }}
    .panel-title {{
        font-size:16px !important;
        font-weight:800 !important;
    }}
    /* Pestañas superiores sin puntos, blanco tenue y blanco intenso al seleccionar */
    div[data-testid="stRadio"] > div {{
        background:#10245F !important;
        border-top:4px solid #EC007C !important;
        border-radius:0 !important;
        padding:0 !important;
        gap:0 !important;
        overflow-x:auto !important;
        white-space:nowrap !important;
        flex-wrap:nowrap !important;
        margin:0 -1.6rem 16px -1.6rem !important;
        box-shadow:0 8px 18px rgba(16,36,95,.16);
    }}
    div[data-testid="stRadio"] label {{
        background:#10245F !important;
        color:rgba(255,255,255,.70) !important;
        padding:14px 22px !important;
        border-radius:0 !important;
        border-bottom:4px solid transparent !important;
        font-weight:800 !important;
        min-width:max-content !important;
        font-size:14px !important;
    }}
    div[data-testid="stRadio"] label > div:first-child {{
        display:none !important;
    }}
    div[data-testid="stRadio"] label * {{
        color:rgba(255,255,255,.70) !important;
        font-weight:800 !important;
    }}
    div[data-testid="stRadio"] label:hover {{
        background:#142E73 !important;
    }}
    div[data-testid="stRadio"] label:hover * {{
        color:rgba(255,255,255,.92) !important;
    }}
    div[data-testid="stRadio"] label:has(input:checked) {{
        background:#142E73 !important;
        border-bottom-color:#EC007C !important;
    }}
    div[data-testid="stRadio"] label:has(input:checked) * {{
        color:#FFFFFF !important;
    }}


    /* Encabezados de tablas en azul con letras blancas */
    div[data-testid="stDataFrame"] [data-testid="stTableStyledTable"] thead tr th,
    div[data-testid="stDataFrame"] thead tr th,
    div[data-testid="stDataFrame"] [role="columnheader"] {{
        background:#10245F !important;
        color:#FFFFFF !important;
        font-weight:800 !important;
        border-color:#10245F !important;
    }}
    div[data-testid="stDataFrame"] [role="columnheader"] * {{
        color:#FFFFFF !important;
        fill:#FFFFFF !important;
    }}
    div[data-testid="stDataEditor"] [role="columnheader"] {{
        background:#10245F !important;
        color:#FFFFFF !important;
        font-weight:800 !important;
        border-color:#10245F !important;
    }}
    div[data-testid="stDataEditor"] [role="columnheader"] * {{
        color:#FFFFFF !important;
        fill:#FFFFFF !important;
    }}
    /* Tablas más limpias */
    div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {{
        border-radius:12px !important;
        overflow:hidden !important;
    }}


    /* Barra de pestañas estable */
    div[data-testid="stTabs"] {{
        margin:0 -1.6rem 18px -1.6rem !important;
    }}
    div[data-testid="stTabs"] div[role="tablist"] {{
        background:#10245F !important;
        border-top:4px solid #EC007C !important;
        border-radius:0 !important;
        gap:0 !important;
        overflow-x:auto !important;
        white-space:nowrap !important;
        box-shadow:0 8px 18px rgba(16,36,95,.16);
    }}
    div[data-testid="stTabs"] button[role="tab"] {{
        background:#10245F !important;
        color:rgba(255,255,255,.70) !important;
        padding:14px 22px !important;
        border-radius:0 !important;
        border-bottom:4px solid transparent !important;
        font-weight:800 !important;
        font-size:14px !important;
    }}
    div[data-testid="stTabs"] button[role="tab"] p {{
        color:rgba(255,255,255,.70) !important;
        font-weight:800 !important;
    }}
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
        background:#142E73 !important;
        border-bottom-color:#EC007C !important;
    }}
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p {{
        color:#FFFFFF !important;
    }}


    /* Navegación automática tipo pestañas */
    div[data-testid="stRadio"] > div {{
        background:#10245F !important;
        border-top:4px solid #EC007C !important;
        border-radius:0 !important;
        padding:0 !important;
        gap:0 !important;
        overflow-x:auto !important;
        white-space:nowrap !important;
        flex-wrap:nowrap !important;
        margin:0 -1.6rem 16px -1.6rem !important;
        box-shadow:0 8px 18px rgba(16,36,95,.16);
    }}
    div[data-testid="stRadio"] label {{
        background:#10245F !important;
        padding:14px 22px !important;
        border-radius:0 !important;
        border-bottom:4px solid transparent !important;
        min-width:max-content !important;
    }}
    div[data-testid="stRadio"] label > div:first-child {{
        display:none !important;
    }}
    div[data-testid="stRadio"] label p,
    div[data-testid="stRadio"] label span,
    div[data-testid="stRadio"] label div {{
        color:rgba(255,255,255,.62) !important;
        font-weight:800 !important;
        font-size:14px !important;
    }}
    div[data-testid="stRadio"] label:hover {{
        background:#142E73 !important;
    }}
    div[data-testid="stRadio"] label:hover p,
    div[data-testid="stRadio"] label:hover span,
    div[data-testid="stRadio"] label:hover div {{
        color:rgba(255,255,255,.90) !important;
    }}
    div[data-testid="stRadio"] label:has(input:checked) {{
        background:#142E73 !important;
        border-bottom-color:#EC007C !important;
    }}
    div[data-testid="stRadio"] label:has(input:checked) p,
    div[data-testid="stRadio"] label:has(input:checked) span,
    div[data-testid="stRadio"] label:has(input:checked) div {{
        color:#FFFFFF !important;
    }}


    /* Fix definitivo: navegación sin bullets visibles */
    div[data-testid="stRadio"] label > div:first-child {{
        display:none !important;
        width:0 !important;
        min-width:0 !important;
        max-width:0 !important;
    }}
    div[data-testid="stRadio"] label p {{
        color:rgba(255,255,255,.65) !important;
    }}
    div[data-testid="stRadio"] label:has(input:checked) p {{
        color:#FFFFFF !important;
    }}


    /* Navegación estable */
    div[data-testid="stPills"] {{
        background:#10245F !important;
        border-top:4px solid #EC007C !important;
        margin:0 -1.6rem 16px -1.6rem !important;
        padding:0 !important;
        overflow-x:auto !important;
        white-space:nowrap !important;
    }}
    div[data-testid="stPills"] button {{
        color:rgba(255,255,255,.65) !important;
        background:#10245F !important;
        border-radius:0 !important;
        border:none !important;
        border-bottom:4px solid transparent !important;
        font-weight:800 !important;
    }}
    div[data-testid="stPills"] button[aria-selected="true"] {{
        color:#FFFFFF !important;
        background:#142E73 !important;
        border-bottom-color:#EC007C !important;
    }}


    /* Navegación estable con selectbox */
    .nav-wrap {{
        background:#10245F;
        border-top:4px solid #EC007C;
        margin:0 -1.6rem 18px -1.6rem;
        padding:12px 18px;
        box-shadow:0 8px 18px rgba(16,36,95,.16);
    }}
    .nav-wrap button {{
        background:#142E73 !important;
        color:#FFFFFF !important;
        border:1px solid rgba(255,255,255,.20) !important;
        font-weight:900 !important;
    }}
    .nav-wrap div[data-baseweb="select"] > div {{
        background:#142E73 !important;
        color:#FFFFFF !important;
        border:1px solid rgba(255,255,255,.25) !important;
        min-height:44px !important;
    }}
    .nav-wrap div[data-baseweb="select"] * {{
        color:#FFFFFF !important;
        font-weight:900 !important;
    }}


    .nav-wrap {{ padding:6px 16px !important; margin:0 -1.6rem 14px -1.6rem !important; }}
    .nav-wrap div[data-baseweb="select"] > div {{ min-height:36px !important; height:36px !important; font-size:13px !important; }}
    .nav-wrap button {{ min-height:36px !important; height:36px !important; padding:4px 10px !important; }}
    div[data-testid="stDataFrame"] [role="columnheader"],
    div[data-testid="stDataEditor"] [role="columnheader"] {{
        background:#1D3F8F !important; color:#FFFFFF !important; font-weight:800 !important;
    }}
    div[data-testid="stDataFrame"] [role="columnheader"] *,
    div[data-testid="stDataEditor"] [role="columnheader"] * {{ color:#FFFFFF !important; fill:#FFFFFF !important; }}


    /* Menú recortado al contenido */
    .nav-wrap {{
        background:transparent !important;
        border-top:4px solid #EC007C !important;
        padding:8px 0 !important;
        margin:0 -1.6rem 18px -1.6rem !important;
        box-shadow:none !important;
    }}
    .nav-wrap [data-testid="column"]:nth-child(2) {{
        max-width:520px !important;
        flex:0 0 520px !important;
    }}
    .nav-wrap div[data-baseweb="select"] > div {{
        min-height:38px !important;
        height:38px !important;
        background:#FFFFFF !important;
        color:#111827 !important;
        border:1px solid #D1D5DB !important;
    }}
    .nav-wrap div[data-baseweb="select"] * {{
        color:#111827 !important;
        font-weight:600 !important;
    }}
    .nav-wrap button {{
        max-width:130px !important;
        height:38px !important;
        background:#FFFFFF !important;
        color:#111827 !important;
        border:1px solid #D1D5DB !important;
    }}

    .ps-kpi-grid {{
        display:grid;
        grid-template-columns: repeat(5, minmax(170px,1fr));
        gap:18px;
        margin:18px 0 20px 0;
    }}
    .ps-kpi-card {{
        background:#FFFFFF;
        border:1px solid #E1E7F0;
        border-radius:14px;
        padding:22px 18px;
        min-height:150px;
        display:flex;
        align-items:center;
        gap:18px;
        box-shadow:0 8px 20px rgba(16,36,95,.06);
    }}
    .ps-kpi-icon {{
        width:78px;
        height:78px;
        min-width:78px;
        border-radius:50%;
        color:white;
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
        margin-bottom:8px;
    }}
    .ps-kpi-value {{
        color:#EC007C;
        font-size:30px;
        font-weight:900;
        line-height:1.1;
        margin-bottom:8px;
    }}
    .ps-kpi-sub {{
        color:#17132D;
        font-size:13px;
        line-height:1.35;
    }}

    div[data-testid="stDataFrame"] [role="columnheader"],
    div[data-testid="stDataEditor"] [role="columnheader"] {{
        background:#EC007C !important;
        color:#FFFFFF !important;
        font-weight:900 !important;
        border-color:#EC007C !important;
        text-align:center !important;
    }}
    div[data-testid="stDataFrame"] [role="columnheader"] *,
    div[data-testid="stDataEditor"] [role="columnheader"] * {{
        color:#FFFFFF !important;
        fill:#FFFFFF !important;
        font-weight:900 !important;
    }}
    div[data-testid="stDataFrame"] [role="gridcell"],
    div[data-testid="stDataEditor"] [role="gridcell"] {{
        font-size:12px !important;
        color:#111827 !important;
    }}


    .top-pink-line{{height:6px;background:#EC007C;border-radius:8px;margin:0 0 16px 0;}}
    .header-card{{max-width:1180px;margin:0 auto 14px auto;background:#FFF;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:18px 28px;box-sizing:border-box;}}
    .header-brand{{display:flex;align-items:center;gap:28px;min-width:560px;}}
    .header-logo img{{max-height:76px!important;max-width:120px!important;object-fit:contain!important;}}
    .header-sep{{width:5px;height:92px;background:#EC007C;border-radius:3px;}}
    .header-title{{color:#1D1259;font-weight:900;font-size:34px;line-height:1.05;}}
    .header-sub{{color:#5B6476;font-weight:700;font-size:15px;margin-top:6px;}}
    .header-meta{{display:flex;gap:16px;flex:1;justify-content:flex-end;}}
    .meta-box{{min-width:190px;background:#F8FAFC;border:1px solid #DDE4F0;border-radius:0 0 14px 14px;padding:14px 18px;}}
    .meta-label{{color:#6B7280;letter-spacing:5px;font-size:12px;font-weight:900;}}
    .meta-value{{color:#1D1259;font-size:18px;font-weight:900;margin-top:6px;}}

    .nav-tabs-bar{{background:#10245F;border-top:4px solid #EC007C;margin:0 -1.6rem 22px -1.6rem;padding:0 72px;overflow-x:auto;white-space:nowrap;box-shadow:none;}}
    .nav-tabs-bar [data-testid="column"]{{padding:0!important;min-width:max-content!important;}}
    .nav-tabs-bar button{{background:#10245F!important;color:#C7D2FE!important;border:0!important;border-radius:0!important;height:54px!important;font-size:15px!important;font-weight:900!important;box-shadow:none!important;padding:0 14px!important;}}
    .nav-tabs-bar button:hover{{background:#142E73!important;color:#FFF!important;}}
    .nav-active-marker{{height:4px;background:transparent;margin-top:-4px;}}
    .nav-active-marker.active{{background:#EC007C;}}

    .panel-title{{background:#FFF;border:1px solid #E1E7F0;border-radius:12px;padding:18px 22px;margin:18px 0 12px 0;font-size:20px;font-weight:900;color:#17132D;}}
    div[data-testid="stDataFrame"] [role="columnheader"],div[data-testid="stDataEditor"] [role="columnheader"]{{background:#10245F!important;color:#FFF!important;font-weight:900!important;border-color:#10245F!important;text-align:center!important;}}
    div[data-testid="stDataFrame"] [role="columnheader"] *,div[data-testid="stDataEditor"] [role="columnheader"] *{{color:#FFF!important;fill:#FFF!important;font-weight:900!important;}}
    div[data-testid="stDataFrame"] [role="gridcell"],div[data-testid="stDataEditor"] [role="gridcell"]{{font-size:12px!important;color:#111827!important;}}
    @media(max-width:1200px){{.header-card{{max-width:100%;padding:14px 18px}}.header-brand{{min-width:420px;gap:18px}}.header-title{{font-size:27px}}.meta-box{{min-width:150px}}.nav-tabs-bar{{padding:0 18px}}}}


/* V9.1 FINAL */
.ps-top-line{{height:6px;background:#EC007C;margin:0 -1.6rem 18px -1.6rem;}}
.ps-header{{width:100%;max-width:1240px;margin:0 auto 18px auto;background:#fff;display:flex;align-items:center;justify-content:space-between;gap:22px;padding:16px 24px;box-sizing:border-box;overflow:visible;}}
.ps-header-left{{display:flex;align-items:center;gap:24px;min-width:0;flex:1 1 auto;}}
.ps-logo-wrap{{width:130px;min-width:130px;height:86px;display:flex;align-items:center;justify-content:center;}}
.ps-logo-img{{max-width:128px!important;max-height:82px!important;object-fit:contain!important;}}
.ps-logo-text{{color:#1D1259;font-weight:900;font-size:26px;line-height:1;}}
.ps-header-sep{{width:5px;min-width:5px;height:92px;background:#EC007C;border-radius:3px;}}
.ps-title-wrap{{min-width:0;}}
.ps-title{{color:#1D1259;font-weight:900;font-size:34px;line-height:1.08;white-space:normal;}}
.ps-subtitle{{color:#5B6476;font-weight:800;font-size:15px;margin-top:8px;}}
.ps-header-right{{display:flex;align-items:center;gap:14px;flex:0 0 auto;}}
.ps-meta{{min-width:190px;background:#F8FAFC;border:1px solid #DDE4F0;border-radius:0 0 14px 14px;padding:13px 16px;}}
.ps-meta-label{{color:#6B7280;letter-spacing:5px;font-size:12px;font-weight:900;}}
.ps-meta-value{{color:#1D1259;font-size:18px;font-weight:900;margin-top:6px;}}

.ps-tabbar{{background:#10245F;border-top:4px solid #EC007C;margin:0 -1.6rem 22px -1.6rem;padding:0 70px;display:flex;align-items:center;gap:0;overflow-x:auto;white-space:nowrap;min-height:58px;}}
.ps-tab{{display:inline-flex;align-items:center;justify-content:center;color:#C7D2FE!important;text-decoration:none!important;font-weight:900;font-size:15px;min-height:58px;padding:0 18px;border-bottom:4px solid transparent;background:#10245F;}}
.ps-tab:hover{{color:#fff!important;background:#142E73;}}
.ps-tab.active{{color:#fff!important;border-bottom-color:#EC007C;background:#142E73;}}
.nav-wrap,.nav-tabs-bar{{display:none!important;}}

.ps-kpi-grid{{display:grid;grid-template-columns:repeat(5,minmax(210px,1fr));gap:18px;margin:18px 0 22px 0;}}
.ps-kpi-card{{background:#fff;border:1px solid #E1E7F0;border-radius:14px;padding:22px 18px;min-height:150px;display:flex;align-items:center;gap:18px;box-shadow:0 8px 20px rgba(16,36,95,.06);overflow:hidden;box-sizing:border-box;}}
.ps-kpi-icon{{width:78px;height:78px;min-width:78px;border-radius:50%;color:#fff;font-size:34px;display:flex;align-items:center;justify-content:center;font-weight:900;}}
.ps-kpi-text{{min-width:0;flex:1;}}
.ps-kpi-title{{color:#17132D;font-size:15px;font-weight:900;line-height:1.2;margin-bottom:8px;}}
.ps-kpi-value{{color:#EC007C;font-size:30px;font-weight:900;line-height:1.1;margin-bottom:8px;}}
.ps-kpi-sub{{color:#17132D;font-size:13px;line-height:1.35;}}

.panel-title{{background:#fff;border:1px solid #E1E7F0;border-radius:12px;padding:18px 22px;margin:18px 0 12px 0;font-size:20px;font-weight:900;color:#17132D;}}
div[data-testid="stDataFrame"] [role="columnheader"],div[data-testid="stDataEditor"] [role="columnheader"]{{background:#10245F!important;color:#fff!important;font-weight:900!important;border-color:#10245F!important;}}
div[data-testid="stDataFrame"] [role="columnheader"] *,div[data-testid="stDataEditor"] [role="columnheader"] *{{color:#fff!important;fill:#fff!important;font-weight:900!important;}}
div[data-testid="stDataFrame"] [role="gridcell"],div[data-testid="stDataEditor"] [role="gridcell"]{{font-size:12px!important;color:#111827!important;}}
section.main > div{{max-width:100%!important;}}
.block-container{{padding-left:1.6rem!important;padding-right:1.6rem!important;}}
@media(max-width:1350px){{.ps-header{{max-width:100%;padding:14px 18px}}.ps-title{{font-size:29px}}.ps-meta{{min-width:160px}}.ps-kpi-grid{{grid-template-columns:repeat(3,minmax(210px,1fr))}}.ps-tabbar{{padding:0 20px}}}}
@media(max-width:900px){{.ps-header{{flex-direction:column;align-items:flex-start}}.ps-header-right{{width:100%;justify-content:flex-start;flex-wrap:wrap}}.ps-kpi-grid{{grid-template-columns:1fr}}}}


/* V9.2 FIX: pestañas sin abrir ventana nueva */
.ps-tabbar,
.nav-tabs-bar,
.nav-wrap{{
    display:none!important;
}}
.ps-tabbar-real{{
    background:#10245F;
    border-top:4px solid #EC007C;
    margin:0 -1.6rem 22px -1.6rem;
    padding:0 70px;
    overflow-x:auto;
    white-space:nowrap;
    min-height:58px;
}}
.ps-tabbar-real [data-testid="stHorizontalBlock"]{{
    gap:0!important;
}}
.ps-tabbar-real [data-testid="column"]{{
    padding:0!important;
    min-width:max-content!important;
    flex:0 0 auto!important;
}}
.ps-tabbar-real .stButton > button{{
    background:#10245F!important;
    color:#C7D2FE!important;
    border:0!important;
    border-radius:0!important;
    height:58px!important;
    min-height:58px!important;
    padding:0 16px!important;
    font-weight:900!important;
    font-size:15px!important;
    box-shadow:none!important;
    white-space:nowrap!important;
}}
.ps-tabbar-real .stButton > button:hover{{
    background:#142E73!important;
    color:#FFFFFF!important;
}}
.ps-tab-cell.active .stButton > button{{
    background:#142E73!important;
    color:#FFFFFF!important;
    border-bottom:4px solid #EC007C!important;
}}
.ps-tab-cell{{
    height:58px;
}}
@media(max-width:1350px){{
    .ps-tabbar-real{{padding:0 20px;}}
}}


/* ===== V9.3 FIX DISEÑO ===== */
.ps-top-line,
.top-pink-line{{
    height:6px!important;
    background:#EC007C!important;
    margin:0 -1.6rem 18px -1.6rem!important;
    border-radius:0!important;
}}
.ps-header{{
    border-top:0!important;
}}

/* Menú de pestañas en azul, letras blancas */
.ps-radio-tabbar{{
    background:#10245F!important;
    border-top:4px solid #EC007C!important;
    margin:0 -1.6rem 22px -1.6rem!important;
    padding:0 70px!important;
    min-height:58px!important;
    overflow-x:auto!important;
    white-space:nowrap!important;
}}
.ps-radio-tabbar [role="radiogroup"]{{
    display:flex!important;
    flex-wrap:nowrap!important;
    gap:0!important;
    align-items:center!important;
    min-height:58px!important;
}}
.ps-radio-tabbar label{{
    background:#10245F!important;
    color:#C7D2FE!important;
    border:0!important;
    border-radius:0!important;
    min-height:58px!important;
    padding:0 18px!important;
    display:flex!important;
    align-items:center!important;
    font-weight:900!important;
    white-space:nowrap!important;
}}
.ps-radio-tabbar label:hover{{
    background:#142E73!important;
    color:#FFFFFF!important;
}}
.ps-radio-tabbar label:has(input:checked){{
    background:#142E73!important;
    color:#FFFFFF!important;
    border-bottom:4px solid #EC007C!important;
}}
.ps-radio-tabbar label *{{
    color:inherit!important;
    font-weight:900!important;
}}
.ps-radio-tabbar div[data-testid="stRadio"]{{
    width:max-content!important;
}}
.ps-tabbar,
.ps-tabbar-real,
.nav-tabs-bar,
.nav-wrap{{
    display:none!important;
}}

/* Encabezados tablas azul + letras blancas */
div[data-testid="stDataFrame"] [role="columnheader"],
div[data-testid="stDataEditor"] [role="columnheader"],
div[data-testid="stDataFrame"] div[role="columnheader"],
div[data-testid="stDataEditor"] div[role="columnheader"]{{
    background:#10245F!important;
    color:#FFFFFF!important;
    font-weight:900!important;
    border-color:#10245F!important;
}}
div[data-testid="stDataFrame"] [role="columnheader"] *,
div[data-testid="stDataEditor"] [role="columnheader"] *,
div[data-testid="stDataFrame"] div[role="columnheader"] *,
div[data-testid="stDataEditor"] div[role="columnheader"] *{{
    color:#FFFFFF!important;
    fill:#FFFFFF!important;
    font-weight:900!important;
}}
div[data-testid="stDataFrame"] [role="gridcell"],
div[data-testid="stDataEditor"] [role="gridcell"]{{
    font-size:12px!important;
    color:#111827!important;
}}

/* Tarjetas: que no se encimen al abrir/cerrar menú */
.ps-kpi-grid{{
    grid-template-columns:repeat(auto-fit,minmax(240px,1fr))!important;
}}
.ps-kpi-card{{
    min-width:0!important;
    overflow:hidden!important;
}}
.ps-kpi-text{{
    min-width:0!important;
}}


/* V9.4 AGGRID TABLES */
.ag-header,
.ag-header-viewport,
.ag-header-container,
.ag-header-row,
.ag-header-cell{{
    background:#10245F!important;
}}
.ag-header-cell-text,
.ag-header-cell-label,
.ag-header-cell-label span{{
    color:#FFFFFF!important;
    font-weight:900!important;
}}
.ag-icon{{
    color:#FFFFFF!important;
    fill:#FFFFFF!important;
}}
.ag-root-wrapper{{
    border-radius:10px!important;
    border:1px solid #E1E7F0!important;
    overflow:hidden!important;
}}
.ag-cell{{
    font-size:12px!important;
}}
.ag-row-even{{
    background:#FFFFFF!important;
}}
.ag-row-odd{{
    background:#F8FAFC!important;
}}

    @media (max-width:1200px) {{
        .top-header {{ grid-template-columns:110px 1fr; }}
        .header-controls {{ display:none; }}
        .kpi-grid {{ grid-template-columns:repeat(2, 1fr); }}
        .hero-grid {{ grid-template-columns:repeat(2, 1fr); }}
        .week-grid {{ grid-template-columns:repeat(2, 1fr); }}
    }}
    </style>
    """, unsafe_allow_html=True)


def logo_html():
    path = Path("assets/price_shoes_logo.png")
    if path.exists():
        data = base64.b64encode(path.read_bytes()).decode("utf-8")
        return f'<img src="data:image/png;base64,{data}" class="ps-logo-img">'
    return '<div class="ps-logo-text">Price<br>Shoes</div>'


def header(user):
    now = datetime.now(ZoneInfo("America/Mexico_City"))
    st.markdown(f"""
    <div class="top-header">
        <div>{logo_html()}</div>
        <div class="header-title">
            <div class="small">Operaciones Ropa</div>
            <div class="big">Indicadores Cambios y Muertos</div>
            <div class="sub">Recuperación · Productividad · Conversión</div>
        </div>
        <div class="header-controls">
            <div class="header-card"><label>Fecha</label><div>📅 {now.strftime("%d/%m/%Y")}</div></div>
            <div class="header-card"><label>Usuario</label><div>{'👑' if user['is_admin'] else '👤'} {user.get('name') or user.get('role')}</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def login_screen():
    st.markdown("""
    <div class="login-wrap">
      <div class="login-card">
        <div class="login-title">Acceso al Sistema</div>
        <div class="login-sub">Indicadores Operaciones Ropa</div>
        <div class="login-alert">
          Para visualizar la información, inicia sesión con un usuario autorizado.
          Si aún no cuentas con acceso, solicita al Administrador del sistema la creación de tu usuario.
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def nav_bar():
    items = [t for t in get_tab_order() if t in [
        "Dashboard","Por Día","Reporte Semanal","Reporte Mensual","Conversión",
        "Recuperación Económica","Productividad","Recorridos","Rankings",
        "Macro","Diagnóstico","Configuración","Usuarios"
    ]]
    if not items:
        items = ["Dashboard","Por Día","Reporte Semanal","Reporte Mensual","Conversión",
                 "Recuperación Económica","Productividad","Recorridos","Rankings",
                 "Macro","Diagnóstico","Configuración","Usuarios"]

    labels = {
        "Dashboard":"Resumen",
        "Por Día":"Por Día",
        "Reporte Semanal":"Reporte Semanal",
        "Reporte Mensual":"Reporte Mensual",
        "Conversión":"Conversión",
        "Recuperación Económica":"Recuperación Económica",
        "Productividad":"Productividad",
        "Recorridos":"Recorridos",
        "Rankings":"Ranking",
        "Macro":"Macro",
        "Diagnóstico":"Diagnóstico",
        "Configuración":"Configuración",
        "Usuarios":"Usuarios",
    }

    label_to_item = {labels.get(i, i): i for i in items}
    current = st.session_state.get("page", items[0])
    if current not in items:
        current = items[0]
    current_label = labels.get(current, current)

    st.markdown('<div class="ps-radio-tabbar">', unsafe_allow_html=True)
    selected_label = st.radio(
        "Pestañas",
        list(label_to_item.keys()),
        index=list(label_to_item.keys()).index(current_label),
        horizontal=True,
        label_visibility="collapsed",
        key="ps_nav_radio_unique_v93",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    selected = label_to_item[selected_label]
    st.session_state.page = selected
    return selected


def section(title, subtitle=""):
    st.markdown(f'<div class="section-title">{title}</div><div class="section-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def kpi_card(label, value, icon, color, note="", pct=0, delta=""):
    st.markdown(f"""
    <div class="kpi-card" style="--accent:{color};--soft:{color}18;--shadow:{color}38;">
        <div class="kpi-top"><div class="kpi-icon">{icon}</div><div class="kpi-label">{label}</div></div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-note">{note}</div>
        <div class="progress"><div style="--pct:{pct_clip(pct)}%;"></div></div>
        {f'<div class="delta">{delta}</div>' if delta else ''}
    </div>
    """, unsafe_allow_html=True)


def kpis(res):
    vals = [
        ("↻", "Piezas Ingresadas", fmt_num(res.get("Ingresos", 0)), "Dev + muertos + cajas + probador", "#EC007C"),
        ("✓", "Piezas Acondicionadas", fmt_num(res.get("Acondicionado", 0)), "Acondicionado", "#3720B8"),
        ("⊕", "Piezas Ubicadas", fmt_num(res.get("Ubicado", 0)), "Ubicado", "#F59E0B"),
        ("⌛", "Pendientes por Ubicar", fmt_num(res.get("Pendiente", 0)), "Ingreso + pendiente ant. - ubicado", "#05B957"),
        ("%", "% Procesado", fmt_pct(res.get("% Ubicado", res.get("% Procesado", 0))), "Ubicado / base", "#3720B8"),
    ]
    html = '<div class="ps-kpi-grid">'
    for icon, title, value, sub, color in vals:
        html += (
            '<div class="ps-kpi-card">'
            f'<div class="ps-kpi-icon" style="background:{color};">{icon}</div>'
            '<div class="ps-kpi-text">'
            f'<div class="ps-kpi-title">{title}</div>'
            f'<div class="ps-kpi-value">{value}</div>'
            f'<div class="ps-kpi-sub">{sub}</div>'
            '</div></div>'
        )
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def hero(resumen, tiendas_count=0):
    st.markdown(f"""
    <div class="hero-blue">
        <h2>Dashboard Ejecutivo</h2>
        <p>Vista ejecutiva de recuperación, productividad, conversión y operación.</p>
        <div class="hero-grid">
            <div class="hero-mini"><div class="hero-mini-label">Tiendas con registro</div><div class="hero-mini-value">{tiendas_count}</div></div>
            <div class="hero-mini"><div class="hero-mini-label">Ingresos</div><div class="hero-mini-value">{fmt_num(resumen.get("Ingresos", 0))}</div></div>
            <div class="hero-mini"><div class="hero-mini-label">Habilitado</div><div class="hero-mini-value">{fmt_pct(resumen.get("% Acondicionado", 0))}</div></div>
            <div class="hero-mini"><div class="hero-mini-label">Ubicado</div><div class="hero-mini-value">{fmt_pct(resumen.get("% Ubicado", 0))}</div></div>
            <div class="hero-mini"><div class="hero-mini-label">Estado</div><div class="hero-mini-value">Activo</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def format_table_for_display(df):
    if df is None or df.empty:
        return df
    out = df.copy()
    for c in out.columns:
        cl = norm_text(c)
        if c == "Tienda" or "NOMBRE" in cl or "ACTIVIDAD" in cl or "AREA" in cl:
            continue
        if "%" in str(c) or "PORC" in cl or "CUMPL" in cl or "CONV" in cl and "%" in cl:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).map(lambda x: f"{x:.1f}%")
        elif "$" in str(c) or "IMP" in cl or "VENTA" in cl or "RECUPER" in cl or "COSTO" in cl:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).map(lambda x: f"${x:,.0f}")
        else:
            # Si es numérico, entero sin decimales y con comas.
            ser = pd.to_numeric(out[c], errors="coerce")
            if ser.notna().mean() > 0.80:
                out[c] = ser.fillna(0).map(lambda x: f"{x:,.0f}")
    return out


def safe_df(df, height=360, editable=False):
    if df is None or df.empty:
        st.info("Sin información con los filtros seleccionados.")
        return df
    view = df.head(500)
    show = format_table_for_display(view)
    if editable:
        return st.data_editor(show, width="stretch", hide_index=True, height=height, num_rows="dynamic")
    st.dataframe(show, width="stretch", hide_index=True, height=height)
    if len(df) > 500:
        st.caption(f"Vista previa de 500 filas de {len(df):,}. Descarga Excel para ver todo.")
    return df


def aggrid_table(df, height=360, editable=False, key=None):
    """Tabla corporativa con encabezado azul y letras blancas."""
    if df is None or df.empty:
        st.info("Sin información para mostrar.")
        return df

    show = format_table_for_display(df.copy())
    auto_height = min(max(118 + len(show) * 34, 170), height)

    if not AGGRID_OK:
        st.warning("AgGrid no está instalado. Se muestra tabla nativa temporal.")
        return st.data_editor(show, hide_index=True, width="stretch", height=auto_height) if editable else st.dataframe(show, hide_index=True, width="stretch", height=auto_height)

    gb = GridOptionsBuilder.from_dataframe(show)
    gb.configure_default_column(
        filter=True,
        sortable=True,
        resizable=True,
        editable=editable,
        wrapText=False,
        autoHeight=False,
        minWidth=105,
    )

    # Primera columna fija si existe Tienda / Nombre
    for first_col in ["Tienda", "Nombre", "Colaborador"]:
        if first_col in show.columns:
            gb.configure_column(first_col, pinned="left", minWidth=145)
            break

    # Alinear números a la derecha y texto a la izquierda
    for col in show.columns:
        if col not in ["Tienda", "Nombre", "Colaborador", "Actividad", "Área", "Area"]:
            gb.configure_column(col, type=["rightAligned"], minWidth=115)

    grid_options = gb.build()
    grid_options["domLayout"] = "normal"
    grid_options["rowHeight"] = 34
    grid_options["headerHeight"] = 38
    grid_options["suppressRowClickSelection"] = True
    grid_options["animateRows"] = False
    grid_options["enableCellTextSelection"] = True

    grid_options["defaultColDef"].update({
        "cellStyle": {"fontSize": "12px", "color": "#111827"},
    })

    grid_options["getRowStyle"] = JsCode("""
        function(params) {
            if (params.node.rowIndex % 2 === 0) {
                return {'backgroundColor': '#FFFFFF'};
            }
            return {'backgroundColor': '#F8FAFC'};
        }
    """)

    custom_css = {
        ".ag-header": {
            "background-color": "#10245F !important",
            "border-bottom": "2px solid #10245F !important",
        },
        ".ag-header-cell": {
            "background-color": "#10245F !important",
            "color": "#FFFFFF !important",
            "font-weight": "800 !important",
            "font-size": "12px !important",
            "border-right": "1px solid #2E4387 !important",
        },
        ".ag-header-cell-label": {
            "color": "#FFFFFF !important",
            "justify-content": "center !important",
        },
        ".ag-header-cell-text": {
            "color": "#FFFFFF !important",
            "font-weight": "800 !important",
        },
        ".ag-icon": {
            "color": "#FFFFFF !important",
            "fill": "#FFFFFF !important",
        },
        ".ag-cell": {
            "font-size": "12px !important",
            "border-right": "1px solid #E5E7EB !important",
        },
        ".ag-row-hover": {
            "background-color": "#EAF1FF !important",
        },
        ".ag-root-wrapper": {
            "border": "1px solid #E1E7F0 !important",
            "border-radius": "10px !important",
            "overflow": "hidden !important",
        },
    }

    response = AgGrid(
        show,
        gridOptions=grid_options,
        height=auto_height,
        width="100%",
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True,
        custom_css=custom_css,
        theme="alpine",
        key=key or f"aggrid_{abs(hash(str(show.columns.tolist()) + str(len(show))))}",
        reload_data=False,
    )

    if editable and response is not None and "data" in response:
        return pd.DataFrame(response["data"])
    return df


def panel(title, df, height=360, editable=False):
    st.markdown(f'<div class="panel-title">{title}</div>', unsafe_allow_html=True)
    return aggrid_table(df, height=height, editable=editable, key=f"aggrid_panel_{norm_text(title)}")


def excel_button(df, filename, label="Descargar Excel"):
    if df is None or df.empty:
        return
    b = io.BytesIO()
    with pd.ExcelWriter(b, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Detalle")
    st.download_button(label, b.getvalue(), filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def week_cards(sem_df):
    if sem_df is None or sem_df.empty:
        st.info("Sin información semanal.")
        return
    df = sem_df.tail(4).copy()
    cols = st.columns(4)
    prev = None
    for col, (_, r) in zip(cols, df.iterrows()):
        ingresos = float(r.get("Ingresos", 0) or 0)
        hab = float(r.get("Acondicionado", 0) or 0)
        ubi = float(r.get("Ubicado", 0) or 0)
        rec = float(r.get("Recorridos", 0) or 0)
        semana = r.get("Semana ISO", 0)
        delta = None if not prev else (ingresos - prev) / prev * 100
        prev = ingresos
        with col:
            st.markdown(f"### Sem {semana}")
            st.metric("Ingresos", fmt_num(ingresos), None if delta is None else f"{delta:.1f}%")
            st.caption(f"% Hab / Ing: {safe_div(hab, ingresos):.1f}%")
            st.caption(f"% Ubic / Ing: {safe_div(ubi, ingresos):.1f}%")
            st.caption(f"Recorridos: {fmt_num(rec)}")

def rank_panel(title, df, value_col, name_col="Tienda", color=PRICE_PINK):
    st.markdown(f'<div class="panel"><div class="panel-title">{title}</div>', unsafe_allow_html=True)
    if df is None or df.empty or value_col not in df.columns:
        st.info("Sin información.")
    else:
        show = df.copy()
        if name_col not in show:
            show[name_col] = show.index.astype(str)
        show = show.sort_values(value_col, ascending=False).head(12)
        mx = float(show[value_col].max()) if len(show) else 1
        for _, row in show.iterrows():
            val = float(row[value_col]) if pd.notna(row[value_col]) else 0
            w = val / mx * 100 if mx else 0
            st.markdown(f"""
            <div class="rank-row">
                <div class="rank-name">{row[name_col]}</div>
                <div class="rankbar"><div class="rankbar-fill" style="--accent:{color};--w:{w}%;"></div></div>
                <div class="rank-value">{fmt_num(val)}</div>
            </div>
            """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# EXCEL NORMALIZACIÓN
# ============================================================

OP_KEYS = ["ACTIVIDAD", "NOMBRE", "OCURRENCIA", "NUMERO DE PIEZAS", "PIEZAS", "RECORRIDOS", "HABILITADO", "UBICADO"]
COM_KEYS = ["DEV", "VTA", "VENTA", "COSTO", "MODELO", "ID", "TALLA", "COLOR"]


def classify_sheet(name, df):
    nname = norm_text(name)
    text = " ".join([nname] + [norm_text(c) for c in df.columns])
    if "PLANTILLA" in nname:
        return "plantilla"
    if "RESULTADOS" in nname and "PRODUCT" in nname:
        return "operacion"
    score_op = sum(k in text for k in OP_KEYS)
    score_co = sum(k in text for k in COM_KEYS)
    if score_co > score_op:
        return "comercial"
    if score_op > 0:
        return "operacion"
    return "otra"


def normalize_operation(df, sheet_name):
    if df is None or df.empty:
        return pd.DataFrame()
    out = pd.DataFrame()
    out["Hoja"] = sheet_name
    # IMPORTANTE:
    # En "Resultados productividad" la tienda viene en la columna "Tienda".
    # Se usan columnas exactas primero para no confundir "Fecha s" con "Fecha".
    c_fecha = pick_first_existing(df, ["Fecha", "Fecha captura", "Día", "Dia"]) or find_col(df, ["Fecha", "Fecha captura", "Día", "Dia"])
    c_tienda = best_tienda_col(df)
    c_nombre = pick_first_existing(df, ["Nombre", "Usuario", "Colaborador"]) or find_col(df, ["Nombre", "Usuario", "Colaborador"])
    c_actividad = pick_first_existing(df, ["Actividad Realizada", "Actividad", "Tabla"]) or find_col(df, ["Actividad Realizada", "Actividad", "Tabla"])
    c_piezas = pick_first_existing(df, ["Número de Piezas", "Numero de Piezas", "Piezas", "Cantidad"]) or find_col(df, ["Número de Piezas", "Numero de Piezas", "Piezas", "Cantidad"])
    c_recorridos = pick_first_existing(df, ["Recorridos", "RECORRIDOS"]) or find_col(df, ["Recorridos", "RECORRIDOS"])
    c_hab = pick_first_existing(df, ["Habilitado", "Acondicionado", "Acondicionadas", "Piezas Habilitadas"]) or find_col(df, ["Habilitado", "Acondicionado", "Acondicionadas", "Piezas Habilitadas"])
    c_ubi = pick_first_existing(df, ["Ubicado", "Ubicadas", "Piezas Ubicadas"]) or find_col(df, ["Ubicado", "Ubicadas", "Piezas Ubicadas"])
    c_ocurrencia = best_occurrence_col(df)
    c_area = pick_first_existing(df, ["Área", "Area"]) or find_col(df, ["Área", "Area"])
    c_motivo = pick_first_existing(df, ["Motivo de ingreso", "Motivo"]) or find_col(df, ["Motivo de ingreso", "Motivo"])

    out["Fecha"] = pd.to_datetime(df[c_fecha], errors="coerce") if c_fecha else pd.NaT
    # Si la columna Fecha exacta no parseó, intentar Fecha s.
    c_fecha_s = exact_col(df, "Fecha s")
    if out["Fecha"].isna().all() and c_fecha_s is not None:
        out["Fecha"] = pd.to_datetime(df[c_fecha_s], errors="coerce", dayfirst=True)
    # Usa la columna Tienda real. Si hay duplicadas, best_tienda_col evita la de occurrence numérica.
    # Usa la columna Tienda real. Si hay duplicadas, best_tienda_col evita la de occurrence numérica.
    out["Tienda"] = df[c_tienda].astype(str).map(canon_tienda) if c_tienda else ""
    out["Nombre"] = df[c_nombre].astype(str).str.strip() if c_nombre else ""
    out["Actividad Realizada"] = df[c_actividad].astype(str).str.strip() if c_actividad else ""
    out["Número de Piezas"] = to_number(df[c_piezas]) if c_piezas else 0
    out["Recorridos"] = to_number(df[c_recorridos]) if c_recorridos else 0
    out["Acondicionado"] = to_number(df[c_hab]) if c_hab else 0
    out["Ubicado"] = to_number(df[c_ubi]) if c_ubi else 0
    out["Ocurrencia"] = df[c_ocurrencia].astype(str).str.strip() if c_ocurrencia else ""
    if c_tienda is None and c_ocurrencia is not None:
        out["Tienda"] = out["Ocurrencia"].map(canon_tienda)
    out["Área"] = df[c_area].astype(str).str.strip() if c_area else ""
    out["Motivo de ingreso"] = df[c_motivo].astype(str).str.strip() if c_motivo else ""

    act_norm = out["Actividad Realizada"].map(norm_text)
    pzs = out["Número de Piezas"]
    if out["Acondicionado"].sum() == 0:
        out["Acondicionado"] = np.where(act_norm.str.contains("HABIL|ACONDICION", na=False), pzs, 0)
    if out["Ubicado"].sum() == 0:
        out["Ubicado"] = np.where(act_norm.str.contains("UBIC", na=False), pzs, 0)
    if out["Recorridos"].sum() == 0:
        out["Recorridos"] = np.where(act_norm.str.contains("RECORR", na=False), 1, 0)

    out["Semana ISO"] = out["Fecha"].dt.isocalendar().week.astype("Int64")
    out["Año ISO"] = out["Fecha"].dt.isocalendar().year.astype("Int64")
    out["Mes"] = out["Fecha"].dt.strftime("%Y-%m")
    # Blindaje: si Tienda salió numérica, reintenta con otra columna candidata.
    if "Tienda" in out and len(out) > 0:
        numeric_ratio_tienda = pd.to_numeric(out["Tienda"].astype(str), errors="coerce").notna().mean()
        if numeric_ratio_tienda > 0.50:
            bt = best_tienda_col(df)
            if bt is not None:
                out["Tienda"] = df[bt].astype(str).map(canon_tienda)

    return out



MONTH_NAMES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "SETIEMBRE": 9,
    "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12
}

def parse_header_date(v, sheet_name=""):
    d = pd.to_datetime(v, errors="coerce", dayfirst=True)
    if pd.notna(d):
        return d
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return pd.NaT
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    return d

def normalize_monthly_commercial_sheet(df, sheet_name):
    """
    Lee hojas mensuales tipo 'Junio 26' aunque pandas haya tomado como encabezado
    la fila de fechas. Ejemplo:
      columnas superiores: 28/06/2026, 28/06/2026, 28/06/2026
      fila visible debajo: Ventas Netas, Dev Pzs, Venta Neta en $
      columna base: Tienda
    Dev Pzs se usa como Ingreso Aduana.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    raw = df.copy()
    records = []
    scan = min(12, len(raw))

    def _norm(x):
        return norm_text(str(x))

    def _is_dev(x):
        n = _norm(x)
        return ("DEV PZS" in n) or ("DEV_PZS" in n) or ("DEV" in n and "PZS" in n)

    def _is_tienda(x):
        n = _norm(x)
        return n == "TIENDA" or n.endswith(" TIENDA")

    def _to_date(x):
        if pd.isna(x):
            return pd.NaT
        if isinstance(x, (int, float)) and 20000 < float(x) < 60000:
            try:
                return pd.to_datetime(x, unit="D", origin="1899-12-30").normalize()
            except Exception:
                pass
        s = str(x).strip()
        if not s or s.lower() in ["nan", "none", "-"]:
            return pd.NaT
        return pd.to_datetime(s, errors="coerce", dayfirst=True)

    def _money_number_series(s):
        ss = s.astype(str).str.strip()
        ss = ss.str.replace(",", "", regex=False).str.replace("$", "", regex=False).str.replace(" ", "", regex=False)
        ss = ss.replace({"-": "0", "": "0", "nan": "0", "None": "0"})
        return pd.to_numeric(ss, errors="coerce").fillna(0)

    # Detectar columna Tienda real buscando el texto "Tienda" en columnas o primeras filas.
    tienda_j = None
    for j in range(len(raw.columns)):
        headers = [raw.columns[j]]
        for i in range(scan):
            try:
                headers.append(raw.iloc[i, j])
            except Exception:
                pass
        if any(_is_tienda(h) for h in headers):
            tienda_j = j
            break

    # Respaldo con best_tienda_col si la hoja ya trae columna nombrada Tienda
    c_tienda = None
    if tienda_j is None:
        try:
            c_tienda = best_tienda_col(raw)
        except Exception:
            c_tienda = find_col(raw, ["Tienda", "Sucursal"])
    else:
        c_tienda = raw.columns[tienda_j]

    c_id = find_col(raw, ["ID", "Modelo", "Artículo", "Articulo", "Id"])
    c_color = find_col(raw, ["Color"])

    # Para cada columna, validar si es subcolumna Dev Pzs.
    for j in range(len(raw.columns)):
        headers = [raw.columns[j]]
        for i in range(scan):
            try:
                headers.append(raw.iloc[i, j])
            except Exception:
                pass

        if not any(_is_dev(h) for h in headers):
            continue

        # Buscar fecha asociada en columnas cercanas y filas superiores.
        fecha = pd.NaT
        for jj in range(max(0, j - 4), j + 1):
            cands = [raw.columns[jj]]
            for i in range(scan):
                try:
                    cands.append(raw.iloc[i, jj])
                except Exception:
                    pass
            for cand in cands:
                d = _to_date(cand)
                if pd.notna(d):
                    fecha = d
                    break
            if pd.notna(fecha):
                break

        if pd.isna(fecha):
            continue

        # Empezar datos después de la fila donde aparece "Dev Pzs".
        data_start = 1
        for i in range(scan):
            try:
                if _is_dev(raw.iloc[i, j]):
                    data_start = max(i + 1, 1)
                    break
            except Exception:
                pass

        vals = _money_number_series(raw.iloc[data_start:, j])

        for idx, val in vals.items():
            val = float(val)
            if val == 0:
                continue
            row = raw.loc[idx]
            tienda_val = row.iloc[tienda_j] if tienda_j is not None else row.get(c_tienda, "")
            tienda = canon_tienda(tienda_val)

            records.append({
                "Hoja": sheet_name,
                "Fecha": pd.to_datetime(fecha),
                "Tienda": tienda,
                "ID": str(row.get(c_id, "")).strip() if c_id else "",
                "Color": str(row.get(c_color, "")).strip() if c_color else "",
                "Dev_Pzs": val,
                "Costo_Dev": 0.0,
                "Vta_Pzs": 0.0,
                "Vta_Imp": 0.0,
            })

    out = pd.DataFrame(records)
    if not out.empty:
        out["Tienda"] = out["Tienda"].map(canon_tienda)
        out["Semana ISO"] = out["Fecha"].dt.isocalendar().week.astype(int)
        out["Mes"] = out["Fecha"].dt.to_period("M").astype(str)
    return out


def monthly_dev_by_date(sheets):
    frames = []
    for name, df in sheets.items():
        n = norm_text(name)
        if any(m in n for m in MONTH_NAMES):
            tmp = normalize_monthly_commercial_sheet(df, name)
            if tmp is not None and not tmp.empty:
                frames.append(tmp)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

def normalize_commercial(df, sheet_name):
    if df is None or df.empty:
        return pd.DataFrame()
    out = pd.DataFrame()
    out["Hoja"] = sheet_name
    c_fecha = find_col(df, ["Fecha", "Fecha venta", "Fecha devolución", "Dia", "Día"])
    c_tienda = find_col(df, ["Tienda", "Sucursal"])
    c_id = find_col(df, ["ID/Modelo", "Id", "Modelo", "Artículo", "Articulo"])
    c_color = find_col(df, ["Color"])
    c_talla = find_col(df, ["Talla"])
    c_dev = find_col(df, ["Dev_pzs", "Dev Pzs", "Devolución Pzs", "Devolucion Pzs", "Dev"])
    c_costo = find_col(df, ["Costo_Dev", "Costo Dev", "Costo"])
    c_vta_pzs = find_col(df, ["Vta_Pzs", "Ventas Netas Pzs", "Venta Pzs", "Vta Pzs"])
    c_vta_imp = find_col(df, ["Vta_Imp", "Venta Importe", "Ventas Netas Imp", "Vta Imp"])

    out["Fecha"] = pd.to_datetime(df[c_fecha], errors="coerce") if c_fecha else pd.NaT
    out["Tienda"] = df[c_tienda].astype(str).map(canon_tienda) if c_tienda else ""
    out["ID/Modelo"] = df[c_id].astype(str).str.strip() if c_id else ""
    out["Color"] = df[c_color].astype(str).str.strip() if c_color else ""
    out["Talla"] = df[c_talla].astype(str).str.strip() if c_talla else ""
    out["Dev_Pzs"] = to_number(df[c_dev]) if c_dev else 0
    out["Costo_Dev"] = to_number(df[c_costo]) if c_costo else 0
    out["Vta_Pzs"] = to_number(df[c_vta_pzs]) if c_vta_pzs else 0
    out["Vta_Imp"] = to_number(df[c_vta_imp]) if c_vta_imp else 0
    if out["Fecha"].notna().any():
        out["Semana ISO"] = out["Fecha"].dt.isocalendar().week.astype("Int64")
        out["Año ISO"] = out["Fecha"].dt.isocalendar().year.astype("Int64")
        out["Mes"] = out["Fecha"].dt.strftime("%Y-%m")
    else:
        out["Semana ISO"] = 0
        out["Año ISO"] = 0
        out["Mes"] = ""
    return out



def build_nombre_map(sheets):
    # Mapa manual solicitado + mapa desde hoja Plantilla.
    mp = {
        "ELO": "Eloisa Flores Camacho",
        "ELOISA": "Eloisa Flores Camacho",
        "IVON": "Ivonne Torres Garduño",
        "IVONNE": "Ivonne Torres Garduño",
    }
    for sheet_name, df in sheets.items():
        if "PLANTILLA" not in norm_text(sheet_name):
            continue
        if df is None or df.empty:
            continue
        c_tienda = find_col(df, ["Tienda", "Sucursal"])
        c_nombre = find_col(df, ["Nombre", "Nombre completo", "Colaborador"])
        c_nomina = find_col(df, ["Nomina", "Nómina"])
        c_alias = find_col(df, ["Alias", "Usuario", "Nombre corto", "Corto", "Registro", "Nombre productividad", "Nombre en productividad"])
        if c_nombre is None:
            c_nombre = df.columns[1] if len(df.columns) > 1 else df.columns[0]

        for _, row in df.iterrows():
            nombre = str(row.get(c_nombre, "")).strip()
            tienda = str(row.get(c_tienda, "")).strip() if c_tienda else ""
            nomina = str(row.get(c_nomina, "")).strip() if c_nomina else ""
            if not nombre or nombre.lower() == "nan":
                continue

            keys = set()
            if c_alias:
                alias = str(row.get(c_alias, "")).strip()
                if alias and alias.lower() != "nan":
                    keys.add(alias)
            if nomina and nomina.lower() != "nan":
                keys.add(nomina)
            partes = nombre.split()
            if partes:
                keys.add(partes[0])  # Eloisa / Ivonne
                # Alias de 3 o 4 letras para casos como Elo / Ivon
                keys.add(partes[0][:3])
                keys.add(partes[0][:4])
            if tienda and partes:
                keys.add(f"{tienda}|{partes[0]}")
                keys.add(f"{tienda}|{partes[0][:3]}")
                keys.add(f"{tienda}|{partes[0][:4]}")

            for k in keys:
                mp[norm_text(k)] = nombre
    return mp


def apply_nombre_map(op, nombre_map):
    if op is None or op.empty or "Nombre" not in op.columns:
        return op
    out = op.copy()
    out["Nombre Original"] = out["Nombre"]
    def mapper(row):
        raw = str(row.get("Nombre", "")).strip()
        tienda = str(row.get("Tienda", "")).strip()
        return (
            nombre_map.get(norm_text(f"{tienda}|{raw}"))
            or nombre_map.get(norm_text(raw))
            or raw
        )
    out["Nombre Homologado"] = out.apply(mapper, axis=1)
    out["Nombre"] = out["Nombre Homologado"]
    return out


@st.cache_data(show_spinner=False)
def load_normalized(file_path, mtime):
    sheets = pd.read_excel(file_path, sheet_name=None, engine="openpyxl")
    ops, coms, diagnostics = [], [], []
    for name, df in sheets.items():
        kind = classify_sheet(name, df)
        diagnostics.append({
            "Hoja": name,
            "Tipo detectado": kind,
            "Filas": len(df),
            "Columnas": len(df.columns),
            "Columnas Tienda candidatas": ", ".join([str(x) for x in tienda_candidate_cols(df)]),
            "Col Tienda detectada": str(best_tienda_col(df)),
            "Col Fecha detectada": str(pick_first_existing(df, ["Fecha", "Fecha captura", "Día", "Dia"]) or find_col(df, ["Fecha", "Fecha captura", "Día", "Dia"])),
            "Col Piezas detectada": str(pick_first_existing(df, ["Número de Piezas", "Numero de Piezas", "Piezas", "Cantidad"]) or find_col(df, ["Número de Piezas", "Numero de Piezas", "Piezas", "Cantidad"])),
        })
        if kind == "operacion":
            ops.append(normalize_operation(df, name))
        elif kind == "comercial":
            coms.append(normalize_commercial(df, name))
    op = pd.concat(ops, ignore_index=True) if ops else pd.DataFrame()
    co = pd.concat(coms, ignore_index=True) if coms else pd.DataFrame()
    nombre_map = build_nombre_map(sheets)
    op = apply_nombre_map(op, nombre_map)
    return op, co, pd.DataFrame(diagnostics), list(sheets.keys()), nombre_map


def filter_period(op, co, period):
    if period == "Todo el archivo":
        return op, co
    today = pd.Timestamp.today()
    op2, co2 = op.copy(), co.copy()
    if period == "Semana actual":
        sem = int(today.isocalendar().week)
        if not op2.empty and "Semana ISO" in op2:
            op2 = op2[op2["Semana ISO"] == sem]
        if not co2.empty and "Semana ISO" in co2:
            co2 = co2[co2["Semana ISO"] == sem]
    if period == "Mes actual":
        mes = today.strftime("%Y-%m")
        if not op2.empty and "Mes" in op2:
            op2 = op2[op2["Mes"] == mes]
        if not co2.empty and "Mes" in co2:
            co2 = co2[co2["Mes"] == mes]
    return op2, co2


def resumen_ejecutivo(op, co):
    ingresos_op = float(op["Número de Piezas"].sum()) if not op.empty and "Número de Piezas" in op else 0
    dev = float(co["Dev_Pzs"].sum()) if not co.empty and "Dev_Pzs" in co else 0
    ingresos = dev if dev > 0 else ingresos_op
    acondicionado = float(op["Acondicionado"].sum()) if not op.empty and "Acondicionado" in op else 0
    ubicado = float(op["Ubicado"].sum()) if not op.empty and "Ubicado" in op else 0
    recorridos = float(op["Recorridos"].sum()) if not op.empty and "Recorridos" in op else 0
    pendiente = max(ingresos - ubicado, 0)
    return {
        "Ingresos": ingresos, "Acondicionado": acondicionado, "Ubicado": ubicado,
        "Pendiente": pendiente, "Recorridos": recorridos,
        "% Acondicionado": safe_div(acondicionado, ingresos), "% Ubicado": safe_div(ubicado, ingresos),
    }


def resumen_tienda(op, co):
    tiendas = sorted(set(
        (op["Tienda"].dropna().astype(str).tolist() if not op.empty and "Tienda" in op else [])
        + (co["Tienda"].dropna().astype(str).tolist() if not co.empty and "Tienda" in co else [])
    ))
    rows = []
    for t in tiendas:
        ot = op[op["Tienda"] == t] if not op.empty and "Tienda" in op else pd.DataFrame()
        ct = co[co["Tienda"] == t] if not co.empty and "Tienda" in co else pd.DataFrame()
        r = resumen_ejecutivo(ot, ct)
        r["Tienda"] = t
        rows.append(r)
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df[["Tienda", "Ingresos", "Acondicionado", "Ubicado", "Pendiente", "Recorridos", "% Acondicionado", "% Ubicado"]]
        df = df.sort_values("Ingresos", ascending=False)
    return df


def resumen_semana(op, co):
    semanas = sorted(set(
        (op["Semana ISO"].dropna().astype(int).tolist() if not op.empty and "Semana ISO" in op else [])
        + (co["Semana ISO"].dropna().astype(int).tolist() if not co.empty and "Semana ISO" in co else [])
    ))
    rows = []
    for s in semanas:
        ot = op[op["Semana ISO"] == s] if not op.empty and "Semana ISO" in op else pd.DataFrame()
        ct = co[co["Semana ISO"] == s] if not co.empty and "Semana ISO" in co else pd.DataFrame()
        r = resumen_ejecutivo(ot, ct)
        r["Semana ISO"] = s
        rows.append(r)
    return pd.DataFrame(rows)


def resumen_mes(op, co):
    meses = sorted(set(
        (op["Mes"].dropna().astype(str).tolist() if not op.empty and "Mes" in op else [])
        + (co["Mes"].dropna().astype(str).tolist() if not co.empty and "Mes" in co else [])
    ))
    rows = []
    for m in meses:
        ot = op[op["Mes"] == m] if not op.empty and "Mes" in op else pd.DataFrame()
        ct = co[co["Mes"] == m] if not co.empty and "Mes" in co else pd.DataFrame()
        r = resumen_ejecutivo(ot, ct)
        r["Mes"] = m
        rows.append(r)
    return pd.DataFrame(rows)


def productividad(op):
    if op.empty:
        return pd.DataFrame()
    group_cols = ["Tienda", "Nombre"] if "Nombre" in op else ["Tienda"]
    df = op.groupby(group_cols, dropna=False).agg(
        Piezas=("Número de Piezas", "sum"),
        Acondicionado=("Acondicionado", "sum"),
        Ubicado=("Ubicado", "sum"),
        Recorridos=("Recorridos", "sum"),
    ).reset_index()
    df["Productividad"] = df["Acondicionado"] + df["Ubicado"]
    return df.sort_values("Productividad", ascending=False)



def operational_table(op, co=None, tiendas_base=None, periodo_label="Día", prev_pending=None):
    op = op.copy() if op is not None else pd.DataFrame()
    co = co.copy() if co is not None else pd.DataFrame()
    if not op.empty and "Tienda" in op:
        op["Tienda"] = op["Tienda"].map(canon_tienda)
    if not co.empty and "Tienda" in co:
        co["Tienda"] = co["Tienda"].map(canon_tienda)

    base_list = [canon_tienda(t) for t in (tiendas_base or []) if canon_tienda(t) and not str(canon_tienda(t)).isdigit()]
    tiendas_op = op["Tienda"].dropna().astype(str).map(canon_tienda).tolist() if not op.empty and "Tienda" in op else []
    tiendas_co = co["Tienda"].dropna().astype(str).map(canon_tienda).tolist() if not co.empty and "Tienda" in co else []
    tiendas_all = sorted(set([t for t in base_list + tiendas_op + tiendas_co if t and t.upper() != "NAN" and not str(t).isdigit()]))

    prev_map = {}
    if prev_pending is not None and not prev_pending.empty and "Tienda" in prev_pending:
        pp = prev_pending.copy()
        pp["Tienda"] = pp["Tienda"].map(canon_tienda)
        pcol = "Pendiente por Ubicar" if "Pendiente por Ubicar" in pp.columns else ("Pend. Ub." if "Pend. Ub." in pp.columns else None)
        if pcol:
            prev_map = pp.groupby("Tienda")[pcol].sum().to_dict()

    rows = []
    for t in tiendas_all:
        ot = op[op["Tienda"].map(norm_text) == norm_text(t)] if not op.empty and "Tienda" in op else pd.DataFrame()
        ct = co[co["Tienda"].map(norm_text) == norm_text(t)] if not co.empty and "Tienda" in co else pd.DataFrame()

        dev = float(ct["Dev_Pzs"].sum()) if not ct.empty and "Dev_Pzs" in ct else 0
        if dev == 0 and not co.empty and "Dev_Pzs" in co and "Tienda" in co:
            blank_co = co[co["Tienda"].astype(str).str.strip().isin(["", "nan", "None"])]
            if len(tiendas_all) == 1 and not blank_co.empty:
                dev = float(blank_co["Dev_Pzs"].sum())
        muertos = cajas = probador = recolectadas = habilitadas = ubicadas = 0.0

        if not ot.empty:
            act = ot["Actividad Realizada"].map(norm_text) if "Actividad Realizada" in ot else pd.Series([""]*len(ot), index=ot.index)
            motivo = ot["Motivo de ingreso"].map(norm_text) if "Motivo de ingreso" in ot else pd.Series([""]*len(ot), index=ot.index)
            pzs = ot["Número de Piezas"] if "Número de Piezas" in ot else pd.Series([0]*len(ot), index=ot.index)
            if dev == 0:
                dev = float(pzs[(motivo.str.contains("DEV|ADUANA|CAMBIO", na=False)) | (act.str.contains("ADUANA|CAMBIO|DEV", na=False))].sum())
            muertos = float(pzs[(motivo.str.contains("MUERTO", na=False)) | (act.str.contains("MUERTO", na=False))].sum())
            cajas = float(pzs[(motivo.str.contains("CAJA", na=False)) | (act.str.contains("CAJA", na=False))].sum())
            probador = float(pzs[(motivo.str.contains("PROB", na=False)) | (act.str.contains("PROB", na=False))].sum())
            recolectadas = float(pzs[act.str.contains("RECOLECT|RECOLEC", na=False)].sum())
            habilitadas = float(ot["Acondicionado"].sum()) if "Acondicionado" in ot else 0
            ubicadas = float(ot["Ubicado"].sum()) if "Ubicado" in ot else 0

        total = dev + muertos + cajas + probador
        pend_ant = float(prev_map.get(t, 0))
        base = total + pend_ant
        rows.append({
            "Tienda": t, "Dev pzs": dev, "Muertos": muertos, "Cajas": cajas, "Probador": probador,
            "Total": total, "Pend. Ant.": pend_ant, "Recolectadas": recolectadas,
            "Habilitadas": habilitadas, "Pend. Hab.": max(base-habilitadas, 0),
            "% Acond.": safe_div(habilitadas, base), "Ubicadas": ubicadas,
            "Pend. Ub.": max(base-ubicadas, 0), "% Ubic.": safe_div(ubicadas, base),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        for c in ["Dev pzs","Muertos","Cajas","Probador","Total","Pend. Ant.","Recolectadas","Habilitadas","Pend. Hab.","Ubicadas","Pend. Ub."]:
            df[c] = df[c].fillna(0).round(0).astype(int)
        for c in ["% Acond.","% Ubic."]:
            df[c] = df[c].fillna(0).round(1)
    return df


def add_pending_previous_day(op_all, selected_date, co_all=None, tiendas_base=None):
    prev = pd.to_datetime(selected_date).normalize() - pd.Timedelta(days=1)
    op_prev = op_all[pd.to_datetime(op_all["Fecha"], errors="coerce").dt.normalize() == prev].copy() if op_all is not None and not op_all.empty and "Fecha" in op_all else pd.DataFrame()
    co_prev = co_all[pd.to_datetime(co_all["Fecha"], errors="coerce").dt.normalize() == prev].copy() if co_all is not None and not co_all.empty and "Fecha" in co_all else pd.DataFrame()
    tprev = operational_table(op_prev, co_prev, tiendas_base=tiendas_base)
    if tprev.empty or "Pend. Ub." not in tprev:
        return pd.DataFrame(columns=["Tienda", "Pendiente por Ubicar"])
    return tprev[["Tienda", "Pend. Ub."]].rename(columns={"Pend. Ub.": "Pendiente por Ubicar"})



def combined_chart(df, title):
    if df is None or df.empty:
        st.info("Sin información para graficar.")
        return
    p = df.copy()
    ymax = 0
    for col in ["Total", "Habilitadas", "Ubicadas"]:
        if col in p:
            ymax = max(ymax, float(pd.to_numeric(p[col], errors="coerce").fillna(0).max()))
    ymax = ymax * 1.18 if ymax > 0 else 10

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=p["Tienda"], y=p["Total"], mode="lines+markers+text",
        name="Total ingresos", text=p["Total"].map(lambda x: f"{x:,.0f}"),
        textposition="top center",
        textfont=dict(color="#111827", size=12, family="Arial Black"),
        line=dict(color="#1D3F8F", width=3)
    ))
    fig.add_trace(go.Bar(
        x=p["Tienda"], y=p["Habilitadas"], name="Pzas Habilitadas",
        marker_color="#4C00C9",
        text=p["Habilitadas"].map(lambda x: f"{x:,.0f}"),
        textposition="outside",
        textfont=dict(color="#111827", size=12, family="Arial Black")
    ))
    fig.add_trace(go.Bar(
        x=p["Tienda"], y=p["Ubicadas"], name="Pzas Ubicadas",
        marker_color="#EC007C",
        text=p["Ubicadas"].map(lambda x: f"{x:,.0f}"),
        textposition="outside",
        textfont=dict(color="#111827", size=12, family="Arial Black")
    ))
    fig.update_layout(
        title=title, barmode="group", height=470, plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h", y=1.10, x=1, xanchor="right"),
        margin=dict(l=10, r=10, t=70, b=100), dragmode=False,
        uniformtext_minsize=10, uniformtext_mode="show"
    )
    fig.update_xaxes(tickangle=-45, showgrid=False, fixedrange=True)
    fig.update_yaxes(showgrid=True, gridcolor="#E5E7EB", fixedrange=True, range=[0, ymax])
    st.plotly_chart(
        fig,
        width="stretch",
        config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False, "staticPlot": False},
    )


def pdf_placeholder(title):
    # PDF básico temporal: descarga resumen/tablas principales. Evita romper Streamlit por reportlab.
    content = f"{title}\\nGenerado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n"
    st.download_button("Descargar PDF", content.encode("utf-8"), f"{title.lower().replace(' ', '_')}.pdf", "application/pdf")

def conversion(co):
    base_k = {"Dev Pzs": 0, "Conversión Pzs": 0, "Conversión $": 0, "Pendiente Pzs": 0, "% Conversión": 0, "No Convertido $": 0}
    if co is None or co.empty:
        return pd.DataFrame(), base_k

    df = co.copy()
    for c in ["Dev_Pzs", "Vta_Pzs", "Vta_Imp", "Costo_Dev"]:
        if c not in df:
            df[c] = 0

    # Regla: la conversión siempre se calcula dentro de la misma Semana ISO,
    # amarrada a tienda, id/modelo y color. No se mezcla el mes completo.
    group_cols = [c for c in ["Semana ISO", "Tienda", "ID/Modelo", "Color"] if c in df.columns]
    if "Semana ISO" not in group_cols:
        df["Semana ISO"] = 0
        group_cols = ["Semana ISO"] + [c for c in ["Tienda", "ID/Modelo", "Color"] if c in df.columns]

    g = df.groupby(group_cols, dropna=False).agg(
        **{
            "Dev Pzs Semana": ("Dev_Pzs", "sum"),
            "Venta Pzs Semana": ("Vta_Pzs", "sum"),
            "Venta $ Semana": ("Vta_Imp", "sum"),
            "Costo Dev Semana": ("Costo_Dev", "sum"),
        }
    ).reset_index()

    g["Conversión Dev → Venta Pzs"] = g[["Dev Pzs Semana", "Venta Pzs Semana"]].min(axis=1)

    # Importe de venta recuperada proporcional a las piezas que sí convierten dentro de la misma semana.
    ratio_venta = g["Conversión Dev → Venta Pzs"] / g["Venta Pzs Semana"].replace(0, pd.NA)
    g["Conversión Dev → Venta $"] = (g["Venta $ Semana"] * ratio_venta.fillna(0)).fillna(0)

    g["Pendiente por Convertir Pzs"] = (g["Dev Pzs Semana"] - g["Conversión Dev → Venta Pzs"]).clip(lower=0)

    # Venta no convertida $ = costo pendiente proporcional a piezas devueltas que no se vendieron misma semana.
    ratio_pend = g["Pendiente por Convertir Pzs"] / g["Dev Pzs Semana"].replace(0, pd.NA)
    g["Venta No Convertida $"] = (g["Costo Dev Semana"] * ratio_pend.fillna(0)).fillna(0)

    g["% Conversión Semanal Dev → Venta"] = (
        g["Conversión Dev → Venta Pzs"] / g["Dev Pzs Semana"].replace(0, pd.NA) * 100
    ).fillna(0)

    # Alias para compatibilidad con pantallas existentes.
    g["Dev Pzs"] = g["Dev Pzs Semana"]
    g["Conversión Pzs"] = g["Conversión Dev → Venta Pzs"]
    g["Conversión $"] = g["Conversión Dev → Venta $"]
    g["Pendiente Pzs"] = g["Pendiente por Convertir Pzs"]
    g["No Convertido $"] = g["Venta No Convertida $"]
    g["% Conversión"] = g["% Conversión Semanal Dev → Venta"]

    k = {
        "Dev Pzs": g["Dev Pzs Semana"].sum(),
        "Conversión Pzs": g["Conversión Dev → Venta Pzs"].sum(),
        "Conversión $": g["Conversión Dev → Venta $"].sum(),
        "Pendiente Pzs": g["Pendiente por Convertir Pzs"].sum(),
        "No Convertido $": g["Venta No Convertida $"].sum(),
    }
    k["% Conversión"] = safe_div(k["Conversión Pzs"], k["Dev Pzs"])
    return g, k


# ============================================================
# LOGIN Y APP
# ============================================================

apply_styles()
init_db()

st.sidebar.markdown("## 🔐 Acceso")
if st.session_state.get("auth_user"):
    user = st.session_state.auth_user
    st.sidebar.success(f"Sesión activa: {user.get('nombre') or user.get('nomina')}")
    st.sidebar.caption(f"Permiso: {user.get('permiso')}")
    if st.sidebar.button("Cerrar sesión"):
        st.session_state.pop("auth_user", None)
        st.rerun()
else:
    st.sidebar.info("Para visualizar, inicia sesión.")
    nomina = st.sidebar.text_input("Nómina / Usuario")
    password = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Iniciar sesión", type="primary", use_container_width=True):
        ok = None
        for u in load_users():
            if u.get("activo", True) and str(u.get("nomina", "")).strip() == str(nomina).strip() and str(u.get("password", "")) == str(password):
                ok = u
                break
        if ok:
            st.session_state.auth_user = ok
            st.rerun()
        else:
            st.sidebar.error("Usuario o contraseña incorrectos.")

if not st.session_state.get("auth_user"):
    login_screen()
    st.stop()

user = st.session_state.auth_user
is_admin = user.get("permiso") == "Administrador"

st.sidebar.divider()
st.sidebar.markdown("## 📁 Fuente de datos")
meta = get_metadata()
if ACTIVE_FILE.exists():
    st.sidebar.success("Archivo cargado")
    st.sidebar.write(meta.get("nombre_original", "Archivo activo"))
    st.sidebar.caption(meta.get("fecha_carga", ""))
else:
    st.sidebar.warning("No hay archivo cargado")

if is_admin:
    up = st.sidebar.file_uploader("Cargar/Reemplazar Excel", type=["xlsx"])
    if up is not None and st.sidebar.button("Procesar archivo", type="primary"):
        save_uploaded_file(up)
        st.cache_data.clear()
        st.sidebar.success("Archivo guardado")
        st.rerun()

    if ACTIVE_FILE.exists() and st.sidebar.button("Borrar archivo persistido"):
        delete_active_file()
        st.sidebar.success("Archivo eliminado")
        st.rerun()

st.sidebar.markdown('<div style="background:#EEF5FF;border-radius:14px;padding:14px;margin-top:24px;color:#1D2E6E;font-weight:900;">🛡️ CONFIDENCIAL<br><span style="font-weight:500;color:#6B7280;">Price Shoes | Operaciones Ropa</span></div>', unsafe_allow_html=True)

header({"role": user.get("permiso", "Consulta"), "is_admin": is_admin, "name": user.get("nombre") or user.get("nomina")})

if not ACTIVE_FILE.exists():
    st.warning("Carga un archivo Excel desde el panel lateral para iniciar.")
    st.stop()

# page se define una sola vez al final

try:
    op_all, co_all, diag_df, sheet_names, nombre_map = load_normalized(str(ACTIVE_FILE), ACTIVE_FILE.stat().st_mtime)
except Exception as e:
    st.error("No fue posible procesar el Excel. Valida que el archivo no esté dañado y que tenga hojas operativas/comerciales.")
    st.exception(e)
    st.stop()

tiendas = sorted(set([
    t for t in (
        PROJECT_TIENDAS
        + (op_all["Tienda"].dropna().astype(str).map(canon_tienda).tolist() if not op_all.empty and "Tienda" in op_all else [])
        + (co_all["Tienda"].dropna().astype(str).map(canon_tienda).tolist() if not co_all.empty and "Tienda" in co_all else [])
    )
    if t and t.upper() != "NAN" and not str(t).strip().isdigit()
]))

op_base, co_base, op, co = op_all.copy(), co_all.copy(), op_all.copy(), co_all.copy()

resumen = resumen_ejecutivo(op, co)
detalle = resumen_tienda(op, co)
sem_df = resumen_semana(op_base, co_base)
mes_df = resumen_mes(op_base, co_base)
prod_df = productividad(op)
conv_df, conv_kpis = conversion(co)
goals = load_goals()


# ============================================================

project_stores = get_project_stores()
if not project_stores:
    project_stores = ["Arco Norte", "Ecatepec", "Miravalle", "Puebla Sur", "Vallejo"]

# PÁGINAS
# ============================================================

def dashboard():
    section("Dashboard Ejecutivo", "Vista general de indicadores principales.")

    # Tiendas operativas configuradas para el proyecto.
    tiendas_cfg = get_project_stores()
    if not tiendas_cfg:
        tiendas_cfg = PROJECT_TIENDAS

    op_dash = op_all.copy()
    if not op_dash.empty and "Tienda" in op_dash:
        op_dash["Tienda"] = op_dash["Tienda"].map(canon_tienda)
        op_dash = op_dash[op_dash["Tienda"].isin(tiendas_cfg)]

    # Conversión/recuperación siguen usando todas las tiendas en sus pestañas,
    # pero el dashboard ejecutivo operativo usa el proyecto.
    resumen_dash = resumen_ejecutivo(op_dash, pd.DataFrame())
    detalle_dash = resumen_tienda(op_dash, pd.DataFrame())

    hero(resumen_dash, len(detalle_dash) if detalle_dash is not None else 0)
    kpis(resumen_dash)
    pdf_placeholder("Dashboard Ejecutivo")

    st.download_button(
        "Descargar PDF de todas las pestañas con indicador",
        b"Reporte integral PDF - version base",
        "reporte_integral_indicadores.pdf",
        "application/pdf",
    )

    section("Últimas 4 semanas", "Ingresos vs semana anterior, % habilitado y % ubicado sobre ingresos.")
    week_cards(resumen_semana(op_dash, pd.DataFrame()))

    c1, c2 = st.columns(2)
    with c1:
        rank_panel("Top tiendas por ingresos", detalle_dash, "Ingresos", "Tienda", PRICE_BLUE)
    with c2:
        prod_dash = productividad(op_dash)
        rank_panel(
            "Top colaboradores",
            prod_dash,
            "Productividad",
            "Nombre" if not prod_dash.empty and "Nombre" in prod_dash else "Tienda",
            PRICE_GREEN,
        )

def dia_anterior():
    section("Por Día", "Ingresos, pendientes y avance por tienda.")
    fechas_op = pd.to_datetime(op_all["Fecha"], errors="coerce").dropna().dt.date.tolist() if not op_all.empty and "Fecha" in op_all else []
    fechas_co = pd.to_datetime(co_all["Fecha"], errors="coerce").dropna().dt.date.tolist() if not co_all.empty and "Fecha" in co_all else []
    fechas = sorted(set(fechas_op + fechas_co))
    selected_date = st.date_input("Fecha", value=(fechas[-1] if fechas else datetime.now(ZoneInfo("America/Mexico_City")).date()))
    d = pd.to_datetime(selected_date).normalize()
    op_d = op_all[pd.to_datetime(op_all["Fecha"], errors="coerce").dt.normalize() == d].copy() if not op_all.empty and "Fecha" in op_all else pd.DataFrame()
    co_d = co_all[pd.to_datetime(co_all["Fecha"], errors="coerce").dt.normalize() == d].copy() if not co_all.empty and "Fecha" in co_all else pd.DataFrame()
    st.caption(f"Registros detectados: operación {len(op_d):,} | aduana mensual {len(co_d):,}")
    prev_pend = add_pending_previous_day(op_all, selected_date, co_all=co_all, tiendas_base=project_stores)
    table = operational_table(op_d, co_d, tiendas_base=project_stores, periodo_label="Día", prev_pending=prev_pend)

    base = (table["Total"].sum() + table["Pend. Ant."].sum()) if not table.empty else 0
    res = {
        "Ingresos": table["Total"].sum() if not table.empty else 0,
        "Acondicionado": table["Habilitadas"].sum() if not table.empty else 0,
        "Ubicado": table["Ubicadas"].sum() if not table.empty else 0,
        "Pendiente": table["Pend. Ub."].sum() if not table.empty else 0,
        "% Acondicionado": safe_div(table["Habilitadas"].sum(), base) if not table.empty else 0,
        "% Ubicado": safe_div(table["Ubicadas"].sum(), base) if not table.empty else 0,
    }
    kpis(res)
    pdf_placeholder("Reporte Por Dia")
    panel("Tabla por tienda - Por Día", table, height=390, editable=is_admin)
    combined_chart(table, "Ingreso vs Habilitado vs Ubicado por tienda")
    excel_button(table, "reporte_por_dia.xlsx")

def reporte_semanal():
    section("Reporte Semanal", "Misma estructura de Por Día, filtrada por tienda y Semana ISO.")
    semanas = sorted(op_all["Semana ISO"].dropna().astype(int).unique().tolist()) if not op_all.empty and "Semana ISO" in op_all else []
    c1, c2 = st.columns([2, 2])
    with c1:
        f_tiendas = st.multiselect("Tiendas", project_stores, placeholder="Todas las tiendas del proyecto", key="sem_tiendas")
    with c2:
        f_sem = st.multiselect("Semana ISO", semanas, default=semanas[-1:] if semanas else [], key="sem_semanas")

    op_s = op_all.copy()
    if f_tiendas and not op_s.empty and "Tienda" in op_s:
        op_s = op_s[op_s["Tienda"].isin(f_tiendas)]
    if f_sem and not op_s.empty and "Semana ISO" in op_s:
        op_s = op_s[op_s["Semana ISO"].isin(f_sem)]

    table = operational_table(op_s, co_s, tiendas_base=f_tiendas or project_stores, periodo_label="Semana")
    res = {
        "Ingresos": table["Total Ingresos"].sum() if not table.empty and "Total Ingresos" in table else 0,
        "Acondicionado": table["Pzas Habilitadas"].sum() if not table.empty and "Pzas Habilitadas" in table else 0,
        "Ubicado": table["Pzas Ubicadas"].sum() if not table.empty and "Pzas Ubicadas" in table else 0,
    }
    res["Pendiente"] = max(res["Ingresos"] - res["Ubicado"], 0)
    res["% Acondicionado"] = safe_div(res["Acondicionado"], res["Ingresos"])
    res["% Ubicado"] = safe_div(res["Ubicado"], res["Ingresos"])

    kpis(res)
    pdf_placeholder("Reporte Semanal")
    panel("Tabla por tienda - Reporte Semanal", table, height=390, editable=is_admin)
    combined_chart(table, "Ingresos vs Acondicionado y Ubicado por tienda")
    excel_button(table, "reporte_semanal.xlsx")

def reporte_mensual():
    section("Reporte Mensual", "Misma estructura de Por Día, filtrada por tienda y mes.")
    meses = sorted(op_all["Mes"].dropna().astype(str).unique().tolist()) if not op_all.empty and "Mes" in op_all else []
    c1, c2 = st.columns([2, 2])
    with c1:
        f_tiendas = st.multiselect("Tiendas", project_stores, placeholder="Todas las tiendas del proyecto", key="mes_tiendas")
    with c2:
        f_mes = st.multiselect("Mes", meses, default=meses[-1:] if meses else [], key="mes_meses")

    op_m = op_all.copy()
    if f_tiendas and not op_m.empty and "Tienda" in op_m:
        op_m = op_m[op_m["Tienda"].isin(f_tiendas)]
    if f_mes and not op_m.empty and "Mes" in op_m:
        op_m = op_m[op_m["Mes"].isin(f_mes)]

    table = operational_table(op_m, co_m, tiendas_base=f_tiendas or project_stores, periodo_label="Mes")
    res = {
        "Ingresos": table["Total Ingresos"].sum() if not table.empty and "Total Ingresos" in table else 0,
        "Acondicionado": table["Pzas Habilitadas"].sum() if not table.empty and "Pzas Habilitadas" in table else 0,
        "Ubicado": table["Pzas Ubicadas"].sum() if not table.empty and "Pzas Ubicadas" in table else 0,
    }
    res["Pendiente"] = max(res["Ingresos"] - res["Ubicado"], 0)
    res["% Acondicionado"] = safe_div(res["Acondicionado"], res["Ingresos"])
    res["% Ubicado"] = safe_div(res["Ubicado"], res["Ingresos"])

    kpis(res)
    pdf_placeholder("Reporte Mensual")
    panel("Tabla por tienda - Reporte Mensual", table, height=390, editable=is_admin)
    combined_chart(table, "Ingresos vs Acondicionado y Ubicado por tienda")
    excel_button(table, "reporte_mensual.xlsx")

def conversion_page():
    section("Conversión Semanal Dev → Venta", "La venta sólo cuenta si ocurre en la misma Semana ISO de la devolución. Se consideran todas las tiendas.")
    if co_all is None or co_all.empty:
        st.warning("No se detectó información comercial para calcular conversión. Revisa que existan columnas Dev Pzs, Vta Pzs, Vta Imp, Tienda, ID/Modelo, Color y Fecha/Semana ISO.")
        return

    semanas = sorted(co_all["Semana ISO"].dropna().astype(int).unique().tolist()) if "Semana ISO" in co_all else []
    if not semanas:
        st.warning("No se detectaron semanas ISO en la hoja comercial.")
        return

    f_sem = st.multiselect("Semana ISO", semanas, default=semanas[-1:], key="conv_sem")
    co_c = co_all.copy()
    if f_sem and "Semana ISO" in co_c:
        co_c = co_c[co_c["Semana ISO"].isin(f_sem)]

    conv_page_df, conv_page_kpis = conversion(co_c)
    st.info("Regla aplicada: Semana ISO + Tienda + ID/Modelo + Color. No se mezclan semanas aunque consultes varias semanas o un mes.")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Dev Pzs Semana", fmt_num(conv_page_kpis.get("Dev Pzs", 0)))
    c2.metric("Conversión Pzs", fmt_num(conv_page_kpis.get("Conversión Pzs", 0)))
    c3.metric("Conversión $", fmt_money(conv_page_kpis.get("Conversión $", 0)))
    c4.metric("% Conversión", fmt_pct(conv_page_kpis.get("% Conversión", 0)))
    c5.metric("Pendiente Pzs", fmt_num(conv_page_kpis.get("Pendiente Pzs", 0)))

    pdf_placeholder("Conversion Dev Venta")
    panel("Detalle de conversión", conv_page_df, height=430, editable=is_admin)
    excel_button(conv_page_df, "conversion_semanal_dev_venta.xlsx")

def recuperacion():
    section("Recuperación Económica", "Importe recuperado y pendiente. Se consideran todas las tiendas.")
    if co_all is None or co_all.empty:
        st.warning("No se detectó información comercial para calcular recuperación económica.")
        return

    semanas = sorted(co_all["Semana ISO"].dropna().astype(int).unique().tolist()) if "Semana ISO" in co_all else []
    if not semanas:
        st.warning("No se detectaron semanas ISO en la hoja comercial.")
        return

    f_sem = st.multiselect("Semana ISO", semanas, default=semanas[-1:], key="rec_sem")
    co_r = co_all.copy()
    if f_sem and "Semana ISO" in co_r:
        co_r = co_r[co_r["Semana ISO"].isin(f_sem)]

    rec_df, rec_kpis = conversion(co_r)
    c1, c2, c3 = st.columns(3)
    c1.metric("Recuperación $", fmt_money(rec_kpis.get("Conversión $", 0)))
    c2.metric("Venta No Convertida $", fmt_money(rec_kpis.get("No Convertido $", 0)))
    c3.metric("% Conversión", fmt_pct(rec_kpis.get("% Conversión", 0)))

    pdf_placeholder("Recuperacion Economica")
    panel("Detalle económico", rec_df, height=430, editable=is_admin)
    excel_button(rec_df, "recuperacion_economica.xlsx")

def productividad_page():
    section("Productividad", "Top colaboradores e índice de actividades por colaborador.")
    c1, c2 = st.columns([1, 1])
    with c1:
        fecha_ini = st.date_input("Fecha inicio", value=(pd.Timestamp.today() - pd.Timedelta(days=30)).date(), key="prod_ini")
    with c2:
        fecha_fin = st.date_input("Fecha final", value=pd.Timestamp.today().date(), key="prod_fin")

    op_p = op_all.copy()
    if not op_p.empty and "Fecha" in op_p:
        op_p = op_p[
            (pd.to_datetime(op_p["Fecha"], errors="coerce").dt.date >= fecha_ini)
            & (pd.to_datetime(op_p["Fecha"], errors="coerce").dt.date <= fecha_fin)
        ]

    prod = productividad(op_p)
    pdf_placeholder("Productividad")
    c1, c2 = st.columns([.9, 1.1])
    with c1:
        panel("Top colaboradores", prod, height=430, editable=is_admin)
    with c2:
        st.markdown('<div class="panel"><div class="panel-title">Top colaboradores</div>', unsafe_allow_html=True)
        if not prod.empty:
            name_col = "Nombre" if "Nombre" in prod else "Tienda"
            p = prod.head(15).sort_values("Productividad")
            fig = px.bar(p, x="Productividad", y=name_col, orientation="h", text="Productividad")
            fig.update_layout(height=430)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Sin información.")
        st.markdown("</div>", unsafe_allow_html=True)

    section("Índice de actividades por colaborador", "Filtro por periodo y tienda.")
    c3, c4, c5 = st.columns([1, 1, 2])
    with c3:
        idx_ini = st.date_input("Inicio índice", value=fecha_ini, key="idx_ini")
    with c4:
        idx_fin = st.date_input("Fin índice", value=fecha_fin, key="idx_fin")
    with c5:
        idx_tiendas = st.multiselect("Tienda índice", project_stores, placeholder="Todas las tiendas del proyecto", key="idx_tiendas")

    idx = op_all.copy()
    if not idx.empty and "Fecha" in idx:
        idx = idx[
            (pd.to_datetime(idx["Fecha"], errors="coerce").dt.date >= idx_ini)
            & (pd.to_datetime(idx["Fecha"], errors="coerce").dt.date <= idx_fin)
        ]
    if idx_tiendas and not idx.empty and "Tienda" in idx:
        idx = idx[idx["Tienda"].isin(idx_tiendas)]
    if not idx.empty:
        index_df = idx.groupby(["Tienda", "Nombre", "Actividad Realizada"], dropna=False).agg(
            Registros=("Actividad Realizada", "count"),
            Piezas=("Número de Piezas", "sum"),
            Acondicionado=("Acondicionado", "sum"),
            Ubicado=("Ubicado", "sum"),
        ).reset_index()
    else:
        index_df = pd.DataFrame()
    panel("Índice de actividades", index_df, height=430, editable=is_admin)
    excel_button(index_df, "indice_actividades_colaborador.xlsx")

def recorridos_page():
    section("Recorridos", "Meta vs real.")
    if not op.empty and "Tienda" in op:
        rec = op.groupby("Tienda", dropna=False).agg(Recorridos=("Recorridos", "sum")).reset_index()
        rec["Meta"] = goals.get("recorridos_semanal", 47)
        rec["% Cumplimiento"] = rec["Recorridos"] / rec["Meta"].replace(0, pd.NA) * 100
    else:
        rec = pd.DataFrame()
    a, b = st.columns([.9, 1.1])
    with a:
        panel("Cumplimiento por tienda", rec, height=430, editable=is_admin)
    with b:
        st.markdown('<div class="panel"><div class="panel-title">Recorridos por tienda</div>', unsafe_allow_html=True)
        if not rec.empty:
            fig = px.bar(rec.sort_values("Recorridos"), x="Recorridos", y="Tienda", orientation="h", text="Recorridos")
            fig.update_layout(height=430)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Sin información.")
        st.markdown("</div>", unsafe_allow_html=True)


def ranking_page():
    section("Rankings", "Top y bottom tiendas / colaboradores.")
    a, b = st.columns(2)
    with a:
        rank_panel("Top tiendas por ingresos", detalle, "Ingresos", "Tienda", PRICE_BLUE)
    with b:
        rank_panel("Top colaboradores", prod_df, "Productividad", "Nombre" if not prod_df.empty and "Nombre" in prod_df else "Tienda", PRICE_GREEN)
    panel("Detalle ranking tiendas", detalle, height=320, editable=is_admin)


def macro_page():
    section("Macro", "Últimas 4 semanas y últimos 3 meses.")
    week_cards(sem_df)
    panel("Últimos 3 meses", mes_df.tail(3) if not mes_df.empty else mes_df, height=260)


def criterios_page():
    section("Diagnóstico", "Diagnóstico y validación del archivo.")
    panel("Hojas detectadas", diag_df, height=320)
    with st.expander("Ver columnas normalizadas"):
        st.write("Operación:", list(op_all.columns))
        st.write("Comercial:", list(co_all.columns))
        st.write("Hojas:", sheet_names)
        st.write("Mapa de nombres desde Plantilla:", nombre_map)


def configuracion_page():
    section("Configuración", "Metas, tiendas del proyecto y orden de pestañas.")
    if not is_admin:
        st.warning("Sólo administrador puede modificar configuración.")
        return

    st.markdown("### Metas")
    with st.form("goals_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            prod_goal = st.number_input("Meta Productividad Diaria", min_value=0, value=int(goals.get("productividad_diaria", 784)))
        with c2:
            rec_goal = st.number_input("Meta Recorridos Semanal", min_value=0, value=int(goals.get("recorridos_semanal", 47)))
        with c3:
            conv_goal = st.number_input("Meta Conversión %", min_value=0.0, value=float(goals.get("conversion_meta", 90.0)))
        if st.form_submit_button("Guardar metas"):
            save_goals({"productividad_diaria": prod_goal, "recorridos_semanal": rec_goal, "conversion_meta": conv_goal})
            st.success("Metas guardadas.")

    st.markdown("### Tiendas del proyecto")
    selected_project = st.multiselect(
        "Selecciona las tiendas que alimentan las pestañas operativas",
        sorted(set(PROJECT_TIENDAS + tiendas)),
        default=get_project_stores() or PROJECT_TIENDAS,
        key="project_stores_cfg",
    )
    if st.button("Guardar tiendas del proyecto", type="primary"):
        save_project_stores(selected_project)
        st.success("Tiendas del proyecto guardadas.")
        st.rerun()

    st.markdown("### Mover pestañas")
    st.caption("Selecciona una pestaña y usa Subir/Bajar para cambiar su posición en la barra azul.")

    current_order = get_tab_order()
    if "tab_order_work" not in st.session_state:
        st.session_state.tab_order_work = current_order.copy()

    # Si cambió en base, sincroniza conservando pestañas faltantes.
    for t in current_order:
        if t not in st.session_state.tab_order_work:
            st.session_state.tab_order_work.append(t)
    st.session_state.tab_order_work = [t for t in st.session_state.tab_order_work if t in current_order]

    selected_tab = st.selectbox("Pestaña a mover", st.session_state.tab_order_work, key="move_tab_select")
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("⬅️ Subir / mover a la izquierda"):
            order = st.session_state.tab_order_work
            i = order.index(selected_tab)
            if i > 0:
                order[i - 1], order[i] = order[i], order[i - 1]
                st.session_state.tab_order_work = order
                st.rerun()
    with c2:
        if st.button("➡️ Bajar / mover a la derecha"):
            order = st.session_state.tab_order_work
            i = order.index(selected_tab)
            if i < len(order) - 1:
                order[i + 1], order[i] = order[i], order[i + 1]
                st.session_state.tab_order_work = order
                st.rerun()
    with c3:
        if st.button("Guardar orden de pestañas", type="primary"):
            save_tab_order(st.session_state.tab_order_work)
            st.success("Orden de pestañas guardado.")
            st.rerun()

    order_preview = pd.DataFrame({
        "Orden": list(range(1, len(st.session_state.tab_order_work) + 1)),
        "Pestaña": st.session_state.tab_order_work,
    })
    st.dataframe(order_preview, hide_index=True, width="stretch", height=430)

    with st.expander("Edición avanzada de orden"):
        st.caption("También puedes editar el número de orden y guardar.")
        edited_order = st.data_editor(order_preview, hide_index=True, width="stretch", height=430, num_rows="fixed")
        if st.button("Guardar edición avanzada"):
            edited_order["Orden"] = pd.to_numeric(edited_order["Orden"], errors="coerce").fillna(999)
            new_order = edited_order.sort_values("Orden")["Pestaña"].tolist()
            save_tab_order(new_order)
            st.session_state.tab_order_work = new_order
            st.success("Orden guardado.")
            st.rerun()

def usuarios_page():
    section("Usuarios", "Asignación de accesos: sólo los usuarios creados pueden entrar al reporte.")
    if not is_admin:
        st.warning("Sólo administrador puede crear, editar o eliminar usuarios.")
        return

    users = load_users()
    st.markdown('<div class="panel"><div class="panel-title">Crear nuevo usuario</div>', unsafe_allow_html=True)
    with st.form("user_form"):
        c1, c2, c3, c4, c5 = st.columns([1, 1.5, 1.2, 1.2, .8])
        with c1:
            nomina = st.text_input("Nómina / Usuario")
        with c2:
            nombre = st.text_input("Nombre")
        with c3:
            permiso = st.selectbox("Tipo de permiso", ["Consulta", "Administrador"])
        with c4:
            password = st.text_input("Contraseña", type="password")
        with c5:
            activo = st.checkbox("Activo", value=True)
        if st.form_submit_button("Crear usuario"):
            if not nomina or not password:
                st.error("Nómina/Usuario y contraseña son obligatorios.")
            elif any(str(u.get("nomina", "")).strip() == str(nomina).strip() for u in users):
                st.error("Ese usuario/nómina ya existe.")
            else:
                upsert_user(str(nomina).strip(), str(nombre).strip() or str(nomina).strip(), permiso, str(password), bool(activo))
                st.success("Usuario creado. Ya podrá ingresar con su usuario y contraseña.")
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### Usuarios existentes")
    users = load_users()
    users_df = pd.DataFrame([{"nomina": u.get("nomina", ""), "nombre": u.get("nombre", ""), "permiso": u.get("permiso", "Consulta"), "activo": bool(u.get("activo", True))} for u in users])
    edited = st.data_editor(
        users_df, width="stretch", hide_index=True, height=300, num_rows="fixed",
        column_config={"permiso": st.column_config.SelectboxColumn("permiso", options=["Consulta", "Administrador"]), "activo": st.column_config.CheckboxColumn("activo")},
    )

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Guardar cambios", type="primary"):
            for _, r in edited.iterrows():
                nom = str(r.get("nomina", "")).strip()
                if not nom:
                    continue
                existing = next((u for u in users if u.get("nomina") == nom), {})
                upsert_user(nom, str(r.get("nombre", "")).strip() or nom, str(r.get("permiso", "Consulta")), existing.get("password", None), bool(r.get("activo", True)))
            st.success("Cambios guardados.")
            st.rerun()
    with c2:
        eliminar = st.selectbox("Eliminar usuario", [""] + [u.get("nomina", "") for u in users], key="delete_user")
        if st.button("Eliminar seleccionado"):
            if not eliminar:
                st.warning("Selecciona un usuario.")
            elif eliminar == user.get("nomina"):
                st.error("No puedes eliminar el usuario con el que estás conectado.")
            else:
                delete_user(eliminar)
                st.success("Usuario eliminado.")
                st.rerun()

    st.markdown("### Cambiar contraseña")
    with st.form("change_pass_form"):
        c1, c2 = st.columns([1, 1])
        with c1:
            usr = st.selectbox("Usuario", [u.get("nomina", "") for u in users], key="pass_user")
        with c2:
            new_pass = st.text_input("Nueva contraseña", type="password")
        if st.form_submit_button("Actualizar contraseña"):
            if not new_pass:
                st.error("Captura una contraseña.")
            else:
                existing = next((u for u in users if u.get("nomina") == usr), None)
                if existing:
                    upsert_user(existing.get("nomina"), existing.get("nombre"), existing.get("permiso"), new_pass, existing.get("activo", True))
                    st.success("Contraseña actualizada.")
                    st.rerun()


ROUTES = {
    "Dashboard": dashboard,
    "Por Día": dia_anterior,
    "Reporte Semanal": reporte_semanal,
    "Reporte Mensual": reporte_mensual,
    "Conversión": conversion_page,
    "Recuperación Económica": recuperacion,
    "Productividad": productividad_page,
    "Recorridos": recorridos_page,
    "Rankings": ranking_page,
    "Macro": macro_page,
    "Diagnóstico": criterios_page,
    "Configuración": configuracion_page,
    "Usuarios": usuarios_page,
}

page = nav_bar()
ROUTES.get(page, dashboard)()

st.markdown("---")
st.caption("CONFIDENCIAL | Price Shoes | Operaciones Ropa")
