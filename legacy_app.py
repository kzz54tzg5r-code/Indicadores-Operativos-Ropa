
# -*- coding: utf-8 -*-
import base64
import json
import hashlib
import gc
import os
import traceback
import re
import sqlite3
import secrets
import shutil
import unicodedata
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import quote

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from io import BytesIO
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.shapes import Drawing, String, PolyLine, Circle, Rect, Line
from reportlab.graphics.charts.barcharts import VerticalBarChart
import streamlit as st
from openpyxl import load_workbook

from core.settings import (
    APP_NAME, APP_SUBTITLE, APP_SLOGAN, APP_AREA, APP_DIRECTION, APP_VERSION, APP_BUILD,
    APP_CACHE_VERSION, COLOR_PRIMARY, COLOR_ACCENT, COLOR_BACKGROUND, DATA_DIR, UPLOAD_DIR,
    CACHE_DIR, CONFIG_DIR, ASSETS_DIR, ACTIVE_FILE, META_FILE, FILE_HISTORY, DB_FILE,
    SESSION_FILE, SESSION_TIMEOUT_HOURS, PROJECT_STORES, ROLES, ROLE_LABELS,
    SYSTEM_STATUSES, SYSTEM_STATUS_LABELS, LOGO_FILE,
    PROCESS_STATUS_FILE, PROCESS_LOCK_FILE, PROCESS_LOG_FILE,
)
from core.security import hash_password, verify_password

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
    AGGRID_OK = True
except Exception:
    AGGRID_OK = False


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================
st.set_page_config(
    page_title=APP_NAME,
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

for p in [DATA_DIR, UPLOAD_DIR, CACHE_DIR, CONFIG_DIR, ASSETS_DIR]:
    p.mkdir(parents=True, exist_ok=True)

MX_TZ = ZoneInfo("America/Mexico_City")
AZUL = COLOR_PRIMARY
ROSA = COLOR_ACCENT
LAVANDA = COLOR_BACKGROUND


# ============================================================
# UTILIDADES
# ============================================================

# ============================================================
# ESTADO PERSISTENTE DEL PROCESAMIENTO
# ============================================================
def read_process_status():
    """Lee el estado del procesamiento sin interrumpir la aplicación."""
    default = {
        "state": "idle",
        "message": "",
        "progress": 0,
        "updated_at": "",
    }
    try:
        if not PROCESS_STATUS_FILE.exists():
            return default
        payload = json.loads(PROCESS_STATUS_FILE.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return default
        return {**default, **payload}
    except Exception:
        return default


def write_process_status(state="idle", message="", progress=0, **extra):
    """Guarda el estado de forma atómica."""
    PROCESS_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "state": str(state),
        "message": str(message),
        "progress": max(0, min(100, int(progress or 0))),
        "updated_at": datetime.now(MX_TZ).isoformat(),
        **extra,
    }
    temporary = PROCESS_STATUS_FILE.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(PROCESS_STATUS_FILE)
    return payload


def clear_process_status():
    """Restablece los archivos temporales del procesamiento."""
    for path in (PROCESS_STATUS_FILE, PROCESS_LOCK_FILE):
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def process_is_locked():
    """Evita iniciar dos procesamientos simultáneos."""
    try:
        if not PROCESS_LOCK_FILE.exists():
            return False
        age_seconds = (
            datetime.now(MX_TZ).timestamp()
            - PROCESS_LOCK_FILE.stat().st_mtime
        )
        if age_seconds > 7200:
            PROCESS_LOCK_FILE.unlink(missing_ok=True)
            return False
        return True
    except Exception:
        return False


def acquire_process_lock():
    PROCESS_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if process_is_locked():
        return False
    PROCESS_LOCK_FILE.write_text(
        datetime.now(MX_TZ).isoformat(),
        encoding="utf-8",
    )
    return True


def release_process_lock():
    try:
        PROCESS_LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass

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
    s_clean = re.sub(r"[^A-Z0-9]+", " ", s).strip()

    if "MIRAVALLE" in s_clean:
        return "Miravalle"
    if "ATEMAJAC" in s_clean:
        return "Atemajac"
    if s_clean in ["GUADALAJARA", "GDL", "GUADALAJARA JALISCO"]:
        return "Atemajac"

    if "ARCO" in s_clean and "NORTE" in s_clean:
        return "Arco Norte"
    if "PUEBLA" in s_clean and "SUR" in s_clean:
        return "Puebla Sur"
    if s_clean in ["PUEBLA CENTRO", "PUEBLA CENTRO ROPA"] or s_clean == "PUEBLA":
        return "Puebla"
    if "ECATEPEC" in s_clean:
        return "Ecatepec"
    if "VALLEJO" in s_clean:
        return "Vallejo"
    if "IZTAPALAPA" in s_clean:
        return "Iztapalapa"
    if "IXTAPALUCA" in s_clean:
        return "Ixtapaluca"
    if "NAUCALPAN" in s_clean:
        return "Naucalpan"
    if "TOLUCA" in s_clean:
        return "Toluca"
    if "QUERETARO" in s_clean or "QUERÉTARO" in raw.upper():
        return "Querétaro"
    if "LEON" in s_clean or "LEÓN" in raw.upper():
        return "León"
    if "VERACRUZ" in s_clean:
        return "Veracruz"
    if "AGUASCALIENTES" in s_clean:
        return "Aguascalientes"
    if "OLIVAR" in s_clean:
        return "Olivar"
    if "SAN LUIS" in s_clean:
        return "San Luis"
    if s_clean == "CENTRO" or "CENTRO HISTORICO" in s_clean or "CENTRO HISTÓRICO" in raw.upper():
        return "Centro"

    try:
        for k, v in STORE_MAP.items():
            if norm_text(k) == s or norm_text(k) == s_clean:
                return v
    except Exception:
        pass

    invalid = {
        "TIENDA", "TIENDAS", "DIA", "DÍA", "FECHA", "VENTAS NETA PZS", "VENTAS NETAS",
        "DEV PZS", "VENTA NETA EN", "VENTA NETA", "CATEGORIA", "SUB CATEGORIA",
        "SUB CATEGORÍA", "FAMILIA RLN", "GRUPO RLN", "PRECIO MENUDEO"
    }
    if s_clean in invalid or s in invalid:
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



def excel_col_name(n):
    """Convierte índice 0-based a letra de Excel."""
    n = int(n) + 1
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def parse_date(x):
    """Convierte fechas de Excel/UI a Timestamp normalizado sin invertir mes y día.

    Casos soportados:
    - 2026-07-09
    - 2026/07/09
    - 2026-07-09 17:00:14
    - 2026/07/09 17:00:14
    - 09/07/2026
    - Fechas reales de Excel
    - Números seriales de Excel
    """
    if x is None:
        return pd.NaT

    try:
        if pd.isna(x):
            return pd.NaT
    except Exception:
        pass

    # Objetos de fecha reales.
    if isinstance(x, (pd.Timestamp, datetime, date)):
        try:
            return pd.Timestamp(x).normalize()
        except Exception:
            return pd.NaT

    # Seriales de Excel o timestamps numéricos.
    if isinstance(x, (int, float, np.integer, np.floating)):
        val = float(x)
        if not np.isfinite(val):
            return pd.NaT

        if 20000 <= val <= 60000:
            try:
                return (
                    pd.Timestamp("1899-12-30")
                    + pd.to_timedelta(val, unit="D")
                ).normalize()
            except Exception:
                return pd.NaT

        for unit, minimum in [("ns", 10**14), ("ms", 10**11), ("s", 10**9)]:
            if val > minimum:
                try:
                    parsed = pd.to_datetime(int(val), unit=unit, errors="coerce")
                    return parsed.normalize() if pd.notna(parsed) else pd.NaT
                except Exception:
                    pass

    s = str(x).strip()
    if not s or s in {"-", "nan", "NaT", "None"}:
        return pd.NaT

    # Año primero, con o sin hora. Este es el formato de Resultados productividad 2.
    # Ejemplo: 2026-07-09 17:00:14.
    if re.match(
        r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?$",
        s,
    ):
        parsed = pd.to_datetime(
            s,
            errors="coerce",
            yearfirst=True,
            dayfirst=False,
        )
        return parsed.normalize() if pd.notna(parsed) else pd.NaT

    # Día primero, con o sin hora.
    # Ejemplo: 09/07/2026 17:00:14.
    if re.match(
        r"^\d{1,2}[-/]\d{1,2}[-/]\d{4}(?:[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?$",
        s,
    ):
        parsed = pd.to_datetime(
            s,
            errors="coerce",
            dayfirst=True,
            yearfirst=False,
        )
        return parsed.normalize() if pd.notna(parsed) else pd.NaT

    # Posible serial guardado como texto.
    compact = s.replace("$", "").replace(",", "").replace(" ", "")
    if re.fullmatch(r"-?\d+(?:\.\d+)?", compact):
        try:
            val = float(compact)
            if 20000 <= val <= 60000:
                return (
                    pd.Timestamp("1899-12-30")
                    + pd.to_timedelta(val, unit="D")
                ).normalize()
        except Exception:
            pass

    # Último intento controlado. Se prueba primero año-mes-día y después día-mes-año.
    parsed = pd.to_datetime(
        s,
        errors="coerce",
        yearfirst=True,
        dayfirst=False,
    )
    if pd.isna(parsed):
        parsed = pd.to_datetime(
            s,
            errors="coerce",
            dayfirst=True,
            yearfirst=False,
        )

    return parsed.normalize() if pd.notna(parsed) else pd.NaT


def fmt_num(x):
    return f"{safe_num(x):,.0f}"


def fmt_money(x):
    return f"${safe_num(x):,.0f}"


def fmt_pct(x):
    return f"{safe_num(x):.1f}%"


def logo_html():
    logo = LOGO_FILE
    if logo.exists():
        data = base64.b64encode(logo.read_bytes()).decode("utf-8")
        return f'<img src="data:image/png;base64,{data}" class="ps-logo-img">'
    return '<div class="ps-logo-text">Price<br>Shoes</div>'


# ============================================================
# USUARIOS, ALCANCES Y CONTROL DEL SISTEMA
# ============================================================
def normalize_role(value):
    raw = norm_text(value)
    aliases = {
        "PROPIETARIO": "OWNER",
        "PROPIETARIO DEL SISTEMA": "OWNER",
        "OWNER": "OWNER",
        "ADMINISTRADOR": "ADMIN",
        "ADMIN": "ADMIN",
        "DIRECTOR": "DIRECTOR",
        "GERENTE REGIONAL": "REGIONAL",
        "REGIONAL": "REGIONAL",
        "GERENTE DE TIENDA": "TIENDA",
        "TIENDA": "TIENDA",
        "SUPERVISOR": "SUPERVISOR",
        "CONSULTA": "CONSULTA",
    }
    return aliases.get(raw, "CONSULTA")


ROLE_LEVEL = {
    "CONSULTA": 10,
    "TIENDA": 20,
    "SUPERVISOR": 30,
    "REGIONAL": 40,
    "DIRECTOR": 50,
    "ADMIN": 80,
    "OWNER": 100,
}


def role_level(user=None):
    user = user or st.session_state.get("user", {})
    role = normalize_role(user.get("role") or user.get("permiso"))
    return ROLE_LEVEL.get(role, 10)


def is_owner(user=None):
    return role_level(user) >= ROLE_LEVEL["OWNER"]


def is_admin(user=None):
    # El Propietario hereda todos los permisos de Administrador.
    # Un Administrador no puede ejecutar acciones exclusivas del Propietario.
    return role_level(user) >= ROLE_LEVEL["ADMIN"]


def can_write(user=None):
    status = get_system_status().get("status", "ACTIVE")
    return is_admin(user) and status == "ACTIVE"

def _table_columns(con, table):
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


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
    cols = _table_columns(con, "usuarios")
    migrations = {
        "correo": "TEXT DEFAULT ''",
        "role": "TEXT DEFAULT 'CONSULTA'",
        "scope_type": "TEXT DEFAULT 'COMPANY'",
        "scope_value": "TEXT DEFAULT ''",
        "must_change_password": "INTEGER DEFAULT 0",
        "password_algorithm": "TEXT DEFAULT 'legacy_sha256'",
        "ultimo_acceso": "TEXT DEFAULT ''",
    }
    for col, definition in migrations.items():
        if col not in cols:
            cur.execute(f"ALTER TABLE usuarios ADD COLUMN {col} {definition}")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS system_control (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            demo_mode INTEGER NOT NULL DEFAULT 0,
            maintenance_text TEXT DEFAULT '',
            changed_by TEXT DEFAULT '',
            changed_at TEXT DEFAULT ''
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            accion TEXT NOT NULL,
            modulo TEXT DEFAULT '',
            detalle TEXT DEFAULT '',
            creado TEXT NOT NULL
        )
        """
    )
    cur.execute("INSERT OR IGNORE INTO system_control(id,status,demo_mode,maintenance_text,changed_by,changed_at) VALUES(1,'ACTIVE',0,'','','')")
    # Cuenta propietaria inicial. La contraseña no se guarda en texto plano; solo se
    # incluye el hash Argon2id solicitado para el primer acceso.
    owner_hash = "$argon2id$v=19$m=65536,t=3,p=4$uGzgUHh0bnf2WhN7DnzMgQ$eBHOmzeNkrxgn/Kcdr7XMfCzwQtpj6hae1RtpqCRSig"
    owner_exists = cur.execute("SELECT 1 FROM usuarios WHERE upper(nomina)='JDA'").fetchone()
    if not owner_exists:
        cur.execute(
            """INSERT INTO usuarios
            (nomina,nombre,permiso,password_hash,activo,creado,correo,role,scope_type,scope_value,must_change_password,password_algorithm)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("JDA", "Jesús Del Ángel", "Propietario del Sistema", owner_hash, 1,
             datetime.now(MX_TZ).isoformat(), "", "OWNER", "COMPANY", "", 0, "argon2id"),
        )

    # Desactiva la credencial de demostración insegura heredada, sin borrar su historial.
    cur.execute("UPDATE usuarios SET activo=0 WHERE lower(nomina)='admin'")
    cur.execute("UPDATE usuarios SET role=CASE WHEN permiso='Administrador' THEN 'ADMIN' ELSE COALESCE(NULLIF(role,''),'CONSULTA') END WHERE upper(nomina)<>'JDA'")
    con.commit()
    con.close()


def get_system_status():
    con = sqlite3.connect(DB_FILE)
    row = con.execute("SELECT status,demo_mode,maintenance_text,changed_by,changed_at FROM system_control WHERE id=1").fetchone()
    con.close()
    if not row:
        return {"status": "ACTIVE", "demo_mode": False, "maintenance_text": "", "changed_by": "", "changed_at": ""}
    return {"status": row[0], "demo_mode": bool(row[1]), "maintenance_text": row[2] or "", "changed_by": row[3] or "", "changed_at": row[4] or ""}


def audit(action, module="", detail="", user=None):
    user = user or st.session_state.get("user", {})
    try:
        con = sqlite3.connect(DB_FILE)
        con.execute(
            "INSERT INTO audit_logs(usuario,accion,modulo,detalle,creado) VALUES(?,?,?,?,?)",
            (str(user.get("nomina", "sistema")), str(action), str(module), str(detail), datetime.now(MX_TZ).isoformat()),
        )
        con.commit(); con.close()
    except Exception:
        pass


def set_system_status(status, justification, user=None):
    user = user or st.session_state.get("user", {})
    if not is_owner(user):
        raise PermissionError("Acceso exclusivo para el Propietario del Sistema.")
    if status not in SYSTEM_STATUSES:
        raise ValueError("Estado no válido.")
    if len(str(justification).strip()) < 10:
        raise ValueError("La justificación debe tener al menos 10 caracteres.")
    previous = get_system_status().get("status", "ACTIVE")
    now = datetime.now(MX_TZ).isoformat()
    con = sqlite3.connect(DB_FILE)
    con.execute(
        "UPDATE system_control SET status=?,maintenance_text=?,changed_by=?,changed_at=? WHERE id=1",
        (status, str(justification).strip(), str(user.get("nomina", "")), now),
    )
    con.commit(); con.close()
    audit("CAMBIO_ESTADO", "Centro de Control", f"{previous} -> {status}. {justification}", user)


def get_user(nomina, password):
    identifier = str(nomina or "").strip()
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute(
        """SELECT nomina,nombre,permiso,correo,role,scope_type,scope_value,
        must_change_password,password_hash
        FROM usuarios WHERE (upper(nomina)=upper(?) OR lower(correo)=lower(?)) AND activo=1""",
        (identifier, identifier),
    )
    row = cur.fetchone()
    if not row:
        con.close()
        return None
    valid, needs_rehash = verify_password(password, row[8])
    if not valid:
        con.close()
        return None
    now = datetime.now(MX_TZ).isoformat()
    if needs_rehash:
        cur.execute(
            "UPDATE usuarios SET password_hash=?,password_algorithm='argon2id',ultimo_acceso=? WHERE nomina=?",
            (hash_password(password), now, row[0]),
        )
    else:
        cur.execute("UPDATE usuarios SET ultimo_acceso=? WHERE nomina=?", (now, row[0]))
    con.commit(); con.close()
    role = normalize_role(row[4] or row[2])
    return {
        "nomina": row[0], "nombre": row[1], "permiso": ROLE_LABELS.get(role, role),
        "correo": row[3] or "", "role": role, "scope_type": row[5] or "COMPANY",
        "scope_value": row[6] or "", "must_change_password": bool(row[7]),
    }


def upsert_user(nomina, nombre, role, password, correo="", scope_type="COMPANY", scope_value=""):
    role = normalize_role(role)
    if role == "OWNER" and not is_owner():
        raise PermissionError("Solo el Propietario puede crear o modificar otro OWNER.")
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO usuarios(nomina,nombre,permiso,password_hash,activo,creado,correo,role,scope_type,scope_value,must_change_password,password_algorithm)
        VALUES (?,?,?,?,1,?,?,?,?,?,1,'argon2id')
        ON CONFLICT(nomina) DO UPDATE SET
            nombre=excluded.nombre, permiso=excluded.permiso, password_hash=excluded.password_hash,
            activo=1, correo=excluded.correo, role=excluded.role,
            scope_type=excluded.scope_type, scope_value=excluded.scope_value,
            must_change_password=1, password_algorithm='argon2id'
        """,
        (str(nomina), nombre, ROLE_LABELS.get(role, role), hash_password(password), datetime.now(MX_TZ).isoformat(),
         correo, role, scope_type, scope_value),
    )
    con.commit(); con.close()
    audit("GUARDAR_USUARIO", "Usuarios", f"Usuario={nomina}; rol={role}; alcance={scope_type}:{scope_value}")


def delete_user(nomina):
    con = sqlite3.connect(DB_FILE)
    row = con.execute("SELECT role FROM usuarios WHERE nomina=?", (nomina,)).fetchone()
    if row and normalize_role(row[0]) == "OWNER":
        con.close(); raise PermissionError("El perfil OWNER no puede eliminarse desde la interfaz.")
    con.execute("DELETE FROM usuarios WHERE nomina=?", (nomina,)); con.commit(); con.close()
    audit("ELIMINAR_USUARIO", "Usuarios", f"Usuario={nomina}")


def list_users():
    con = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query(
        """SELECT nomina AS Nómina,nombre AS Nombre,correo AS Correo,role AS Rol,
        scope_type AS Alcance,scope_value AS Asignación,activo AS Activo
        FROM usuarios ORDER BY nombre""", con,
    )
    con.close(); return df


def apply_user_scope(df, user=None):
    """Aplica el alcance territorial. La interfaz no puede ampliar este filtro."""
    if df is None or df.empty or "Tienda" not in df.columns:
        return df
    user = user or st.session_state.get("user", {})
    scope_type = str(user.get("scope_type", "COMPANY")).upper()
    scope_value = str(user.get("scope_value", "")).strip()
    role = normalize_role(user.get("role", user.get("permiso")))
    if role in {"OWNER", "ADMIN", "DIRECTOR"} or scope_type == "COMPANY":
        return df
    allowed = [canon_store(x) for x in re.split(r"[,;|]", scope_value) if str(x).strip()]
    if not allowed:
        return df.iloc[0:0].copy()
    return df[df["Tienda"].map(canon_store).isin(allowed)].copy()


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


/* Navegación corporativa de extremo a extremo */
.ps-tabbar {{
    position: relative !important;
    left: 50% !important;
    right: 50% !important;
    margin-left: -50vw !important;
    margin-right: -50vw !important;
    width: 100vw !important;
    max-width: 100vw !important;
    box-sizing: border-box !important;
    background: var(--azul) !important;
    border-top: 5px solid var(--rosa) !important;
    padding: 0 24px !important;
    overflow-x: auto !important;
}}
.ps-tabbar [role="radiogroup"] {{
    width: max-content !important;
    min-width: 100% !important;
    justify-content: flex-start !important;
    background: var(--azul) !important;
}}
.ps-tabbar label {{
    background: var(--azul) !important;
    color: rgba(255,255,255,.72) !important;
    border: 0 !important;
    border-radius: 0 !important;
    min-height: 58px !important;
    padding: 0 22px !important;
}}
.ps-tabbar label p,
.ps-tabbar label span {{
    color: rgba(255,255,255,.72) !important;
    font-weight: 800 !important;
}}
.ps-tabbar label:has(input:checked) {{
    background: #142E73 !important;
    box-shadow: inset 0 -5px 0 var(--rosa) !important;
}}
.ps-tabbar label:has(input:checked) p,
.ps-tabbar label:has(input:checked) span {{
    color: #FFFFFF !important;
    font-weight: 900 !important;
}}
.ps-tabbar input[type="radio"] {{
    accent-color: #FFFFFF !important;
}}


/* =========================================================
   VISTA RESPONSIVA: COMPUTADORA Y MÓVIL
   ========================================================= */

/* Computadora y tablet horizontal */
@media (min-width: 769px) {{
    .ps-kpi-grid {{
        grid-template-columns: repeat(5, minmax(0, 1fr)) !important;
    }}

    .ps-kpi-card {{
        min-width: 0 !important;
    }}
}}

/* Móvil y tablet vertical */
@media (max-width: 768px) {{
    html, body, [data-testid="stAppViewContainer"] {{
        overflow-x: hidden !important;
    }}

    .block-container {{
        padding-top: .35rem !important;
        padding-left: .65rem !important;
        padding-right: .65rem !important;
        padding-bottom: 1rem !important;
    }}

    .ps-top-line {{
        height: 4px !important;
        margin: 0 -.65rem 8px -.65rem !important;
    }}

    .ps-header {{
        padding: 8px 8px 10px 8px !important;
        gap: 8px !important;
        flex-direction: column !important;
        align-items: stretch !important;
    }}

    .ps-header-left {{
        gap: 9px !important;
        width: 100% !important;
    }}

    .ps-logo-wrap {{
        width: 58px !important;
        height: 50px !important;
        min-width: 58px !important;
    }}

    .ps-logo-img {{
        max-width: 56px !important;
        max-height: 46px !important;
    }}

    .ps-logo-text {{
        font-size: 15px !important;
    }}

    .ps-header-sep {{
        width: 3px !important;
        height: 48px !important;
        min-width: 3px !important;
    }}

    .ps-title {{
        font-size: 19px !important;
        line-height: 1.05 !important;
    }}

    .ps-subtitle {{
        font-size: 10px !important;
        line-height: 1.15 !important;
        margin-top: 3px !important;
    }}

    .ps-header-right {{
        display: grid !important;
        grid-template-columns: 1fr 1fr !important;
        gap: 7px !important;
        width: 100% !important;
    }}

    .ps-meta {{
        min-width: 0 !important;
        border-radius: 8px !important;
        padding: 7px 9px !important;
    }}

    .ps-meta-label {{
        letter-spacing: 2px !important;
        font-size: 8px !important;
    }}

    .ps-meta-value {{
        font-size: 12px !important;
        margin-top: 3px !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }}

    .ps-tabbar {{
        margin: 0 -.65rem 12px -.65rem !important;
        padding: 0 6px !important;
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        scrollbar-width: thin !important;
    }}

    .ps-tabbar [role="radiogroup"] {{
        min-height: 44px !important;
        width: max-content !important;
    }}

    .ps-tabbar label {{
        min-height: 44px !important;
        padding: 0 11px !important;
        font-size: 10px !important;
    }}

    h1 {{
        font-size: 1.55rem !important;
    }}

    h2 {{
        font-size: 1.32rem !important;
    }}

    h3 {{
        font-size: 1.1rem !important;
    }}

    .ps-kpi-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        gap: 9px !important;
        margin: 10px 0 14px 0 !important;
    }}

    .ps-kpi-card {{
        min-height: 112px !important;
        height: auto !important;
        padding: 11px 9px !important;
        border-radius: 12px !important;
        gap: 8px !important;
        align-items: center !important;
        box-shadow: 0 4px 12px rgba(16,36,95,.06) !important;
    }}

    .ps-kpi-card:nth-child(5) {{
        grid-column: 1 / -1 !important;
        min-height: 96px !important;
    }}

    .ps-kpi-icon {{
        width: 47px !important;
        height: 47px !important;
        min-width: 47px !important;
        font-size: 23px !important;
    }}

    .ps-kpi-title {{
        font-size: 11px !important;
        line-height: 1.12 !important;
    }}

    .ps-kpi-value {{
        font-size: 22px !important;
        line-height: 1 !important;
        margin: 5px 0 !important;
        white-space: nowrap !important;
    }}

    .ps-kpi-sub {{
        font-size: 8.5px !important;
        line-height: 1.18 !important;
    }}

    .panel-title {{
        font-size: 14px !important;
        padding: 12px 13px !important;
        margin: 12px 0 8px 0 !important;
    }}

    .week-card-grid {{
        grid-template-columns: 1fr !important;
        gap: 10px !important;
        margin: 10px 0 16px 0 !important;
    }}

    .week-card-head {{
        font-size: 16px !important;
        padding: 10px 8px !important;
    }}

    .week-row {{
        padding: 9px 11px !important;
        gap: 8px !important;
    }}

    .week-row span {{
        font-size: 10px !important;
    }}

    .week-row b {{
        font-size: 16px !important;
    }}

    .week-row em {{
        font-size: 10px !important;
    }}

    /* Tablas: conservar estructura completa con desplazamiento horizontal */
    [data-testid="stDataFrame"],
    [data-testid="stDataEditor"],
    .ag-root-wrapper {{
        max-width: 100% !important;
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
    }}

    .ag-cell {{
        font-size: 10px !important;
    }}

    .ag-header-cell-text {{
        font-size: 10px !important;
    }}

    /* Gráficos adaptados al ancho del teléfono */
    [data-testid="stPlotlyChart"] {{
        width: 100% !important;
        overflow: hidden !important;
    }}

    [data-testid="stPlotlyChart"] > div {{
        width: 100% !important;
    }}

    .footer {{
        font-size: 10px !important;
        margin-top: 22px !important;
        padding-top: 12px !important;
    }}

    /* Evita que botones flotantes tapen contenido */
    .block-container {{
        padding-bottom: 5.5rem !important;
    }}
}}

/* Teléfonos muy angostos */
@media (max-width: 390px) {{
    .ps-kpi-grid {{
        gap: 7px !important;
    }}

    .ps-kpi-card {{
        padding: 9px 7px !important;
        gap: 6px !important;
    }}

    .ps-kpi-icon {{
        width: 42px !important;
        height: 42px !important;
        min-width: 42px !important;
        font-size: 20px !important;
    }}

    .ps-kpi-title {{
        font-size: 10px !important;
    }}

    .ps-kpi-value {{
        font-size: 19px !important;
    }}

    .ps-kpi-sub {{
        font-size: 7.7px !important;
    }}
}}


/* =========================================================
   V11 — DISEÑO RESPONSIVE EJECUTIVO
   ========================================================= */

:root {{
    --ps-gap: 14px;
    --ps-radius: 14px;
}}

.block-container {{
    max-width: 100% !important;
    width: 100% !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
}}

.ps-kpi-grid {{
    width: 100% !important;
    gap: var(--ps-gap) !important;
}}

.ps-kpi-card {{
    min-width: 0 !important;
    width: 100% !important;
    border-radius: var(--ps-radius) !important;
}}

.week-card-grid {{
    display: grid !important;
    grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
    gap: 14px !important;
    width: 100% !important;
    margin: 12px 0 18px 0 !important;
}}

.week-card {{
    min-width: 0 !important;
    width: 100% !important;
    border-radius: 12px !important;
    overflow: hidden !important;
}}

.week-card-head {{
    padding: 11px 8px !important;
    font-size: 17px !important;
    line-height: 1.1 !important;
}}

.week-row {{
    display: grid !important;
    grid-template-columns: minmax(92px, 1fr) auto auto !important;
    align-items: center !important;
    gap: 8px !important;
    padding: 9px 12px !important;
    min-height: 43px !important;
}}

.week-row span {{
    font-size: 10px !important;
    white-space: nowrap !important;
}}

.week-row b {{
    font-size: 17px !important;
    white-space: nowrap !important;
}}

.week-row em {{
    min-width: 56px !important;
    text-align: right !important;
    font-size: 10px !important;
    white-space: nowrap !important;
}}

.panel-title {{
    margin-bottom: 6px !important;
}}

[data-testid="stDataFrame"],
[data-testid="stDataEditor"],
.ag-root-wrapper {{
    width: 100% !important;
    max-width: 100% !important;
    border-radius: 10px !important;
}}

[data-testid="stPlotlyChart"] {{
    width: 100% !important;
    max-width: 100% !important;
    margin-left: 0 !important;
    margin-right: 0 !important;
}}

[data-testid="stPlotlyChart"] > div,
.js-plotly-plot,
.plot-container,
.svg-container {{
    width: 100% !important;
    max-width: 100% !important;
}}

@media (min-width: 1440px) {{
    .block-container {{
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
    }}

    .ps-kpi-card {{
        min-height: 126px !important;
    }}

    .week-card-grid {{
        gap: 18px !important;
    }}

    .week-row {{
        min-height: 46px !important;
    }}
}}

@media (min-width: 769px) and (max-width: 1100px) {{
    .week-card-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    }}

    .ps-kpi-grid {{
        grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
    }}
}}

@media (max-width: 768px) {{
    .block-container {{
        padding-left: .5rem !important;
        padding-right: .5rem !important;
        padding-top: .3rem !important;
    }}

    .ps-kpi-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        gap: 8px !important;
    }}

    .ps-kpi-card {{
        min-height: 104px !important;
        padding: 10px 8px !important;
        gap: 7px !important;
        border-radius: 12px !important;
    }}

    .ps-kpi-card:nth-child(5) {{
        grid-column: 1 / -1 !important;
        min-height: 90px !important;
    }}

    .ps-kpi-icon {{
        width: 44px !important;
        height: 44px !important;
        min-width: 44px !important;
        font-size: 21px !important;
    }}

    .ps-kpi-title {{
        font-size: 10px !important;
        line-height: 1.1 !important;
    }}

    .ps-kpi-value {{
        font-size: 20px !important;
        line-height: 1 !important;
        margin: 4px 0 !important;
    }}

    .ps-kpi-sub {{
        font-size: 7.8px !important;
        line-height: 1.15 !important;
    }}

    .week-card-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        gap: 8px !important;
        margin: 10px 0 14px 0 !important;
    }}

    .week-card-head {{
        padding: 9px 6px !important;
        font-size: 14px !important;
    }}

    .week-row {{
        grid-template-columns: 1fr auto !important;
        gap: 5px !important;
        padding: 7px 8px !important;
        min-height: 38px !important;
    }}

    .week-row span {{
        font-size: 8px !important;
    }}

    .week-row b {{
        font-size: 13px !important;
    }}

    .week-row em {{
        grid-column: 1 / -1 !important;
        min-width: 0 !important;
        text-align: right !important;
        font-size: 8px !important;
        margin-top: -3px !important;
    }}

    [data-testid="stDataFrame"],
    [data-testid="stDataEditor"],
    .ag-root-wrapper {{
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
    }}

    .ag-header-cell-text,
    .ag-cell {{
        font-size: 9px !important;
    }}

    [data-testid="stPlotlyChart"] {{
        width: calc(100vw - 1rem) !important;
        margin-left: 0 !important;
        margin-right: 0 !important;
    }}

    [data-testid="stPlotlyChart"] .svg-container {{
        min-height: 430px !important;
    }}
}}

@media (max-width: 390px) {{
    .ps-kpi-grid {{
        gap: 6px !important;
    }}

    .ps-kpi-card {{
        padding: 8px 6px !important;
    }}

    .ps-kpi-icon {{
        width: 40px !important;
        height: 40px !important;
        min-width: 40px !important;
    }}

    .ps-kpi-value {{
        font-size: 18px !important;
    }}

    .week-card-grid {{
        gap: 6px !important;
    }}

    .week-row {{
        padding: 6px 6px !important;
    }}
}}


/* =========================================================
   V11.3 — MENÚ TIPO CARRUSEL
   Inspirado en navegación móvil por tarjetas deslizables
   ========================================================= */

.ps-mobile-nav-title {{
    display:none;
}}

/* Escritorio: navegación corporativa horizontal */
@media (min-width: 769px) {{
    .ps-tabbar {{
        background:var(--azul)!important;
        border-top:5px solid var(--rosa)!important;
        overflow-x:auto!important;
        scroll-behavior:smooth!important;
    }}

    .ps-tabbar [role="radiogroup"] {{
        display:flex!important;
        flex-wrap:nowrap!important;
        min-width:max-content!important;
    }}

    .ps-tabbar label {{
        min-height:58px!important;
        padding:0 20px!important;
        background:var(--azul)!important;
        color:rgba(255,255,255,.76)!important;
        transition:background .18s ease, color .18s ease!important;
    }}

    .ps-tabbar label:has(input:checked) {{
        background:#142E73!important;
        box-shadow:inset 0 -5px 0 var(--rosa)!important;
        color:#FFF!important;
    }}
}}

/* Móvil: carrusel de reportes */
@media (max-width: 768px) {{
    .ps-mobile-nav-title {{
        display:flex!important;
        align-items:center!important;
        justify-content:space-between!important;
        margin:8px 2px 7px 2px!important;
        color:#5B6476!important;
        font-size:11px!important;
        font-weight:800!important;
    }}

    .ps-mobile-nav-arrow {{
        color:var(--rosa)!important;
        font-size:17px!important;
        font-weight:900!important;
    }}

    .ps-tabbar {{
        position:relative!important;
        left:auto!important;
        right:auto!important;
        width:calc(100% + 1rem)!important;
        max-width:none!important;
        margin:0 -.5rem 16px -.5rem!important;
        padding:8px 0 12px 0!important;
        background:
            linear-gradient(135deg,#111A55 0%,#24126E 55%,#3B146E 100%)!important;
        border-top:4px solid var(--rosa)!important;
        border-bottom:1px solid rgba(255,255,255,.12)!important;
        overflow-x:auto!important;
        overflow-y:hidden!important;
        scroll-snap-type:x mandatory!important;
        scroll-padding-inline:calc(50vw - 92px)!important;
        -webkit-overflow-scrolling:touch!important;
        scrollbar-width:none!important;
    }}

    .ps-tabbar::-webkit-scrollbar {{
        display:none!important;
    }}

    .ps-tabbar [role="radiogroup"] {{
        display:flex!important;
        flex-wrap:nowrap!important;
        align-items:center!important;
        gap:10px!important;
        width:max-content!important;
        min-width:max-content!important;
        padding:0 calc(50vw - 92px)!important;
        min-height:106px!important;
    }}

    .ps-tabbar label {{
        position:relative!important;
        flex:0 0 154px!important;
        width:154px!important;
        min-width:154px!important;
        height:82px!important;
        min-height:82px!important;
        padding:39px 9px 8px 9px!important;
        border-radius:15px!important;
        border:1px solid rgba(255,255,255,.22)!important;
        background:rgba(255,255,255,.10)!important;
        color:rgba(255,255,255,.82)!important;
        display:flex!important;
        align-items:center!important;
        justify-content:center!important;
        text-align:center!important;
        white-space:normal!important;
        scroll-snap-align:center!important;
        box-shadow:0 8px 18px rgba(0,0,0,.16)!important;
        transform:scale(.91)!important;
        opacity:.76!important;
        transition:
            transform .22s ease,
            opacity .22s ease,
            background .22s ease,
            border-color .22s ease!important;
    }}

    .ps-tabbar label p,
    .ps-tabbar label span {{
        color:inherit!important;
        font-size:11px!important;
        line-height:1.08!important;
        font-weight:900!important;
        text-align:center!important;
    }}

    .ps-tabbar label::before {{
        content:"▦";
        position:absolute!important;
        top:9px!important;
        left:50%!important;
        transform:translateX(-50%)!important;
        width:27px!important;
        height:27px!important;
        border-radius:50%!important;
        display:flex!important;
        align-items:center!important;
        justify-content:center!important;
        background:rgba(255,255,255,.16)!important;
        color:#FFF!important;
        font-size:15px!important;
        font-weight:900!important;
    }}

    /* Iconos por reporte */
    .ps-tabbar label:nth-child(1)::before {{content:"▦";}}
    .ps-tabbar label:nth-child(2)::before {{content:"◷";}}
    .ps-tabbar label:nth-child(3)::before {{content:"W";}}
    .ps-tabbar label:nth-child(4)::before {{content:"M";}}
    .ps-tabbar label:nth-child(5)::before {{content:"↗";}}
    .ps-tabbar label:nth-child(6)::before {{content:"$";}}
    .ps-tabbar label:nth-child(7)::before {{content:"✓";}}
    .ps-tabbar label:nth-child(8)::before {{content:"↻";}}
    .ps-tabbar label:nth-child(9)::before {{content:"#";}}
    .ps-tabbar label:nth-child(10)::before {{content:"Σ";}}
    .ps-tabbar label:nth-child(11)::before {{content:"!";}}
    .ps-tabbar label:nth-child(12)::before {{content:"⚙";}}
    .ps-tabbar label:nth-child(13)::before {{content:"♙";}}

    .ps-tabbar label:hover {{
        background:rgba(255,255,255,.15)!important;
        color:#FFF!important;
    }}

    .ps-tabbar label:has(input:checked) {{
        transform:scale(1.04)!important;
        opacity:1!important;
        z-index:3!important;
        background:
            linear-gradient(145deg,rgba(255,255,255,.24),rgba(255,255,255,.13))!important;
        border:2px solid #FFF!important;
        box-shadow:
            0 12px 25px rgba(0,0,0,.25),
            0 0 0 3px rgba(255,0,128,.30)!important;
        color:#FFF!important;
    }}

    .ps-tabbar label:has(input:checked)::before {{
        background:var(--rosa)!important;
        box-shadow:0 4px 10px rgba(255,0,128,.35)!important;
    }}

    .ps-tabbar label:has(input:checked)::after {{
        content:"";
        position:absolute!important;
        bottom:-9px!important;
        left:50%!important;
        transform:translateX(-50%)!important;
        width:30px!important;
        height:4px!important;
        border-radius:4px!important;
        background:var(--rosa)!important;
    }}

    .ps-tabbar input[type="radio"] {{
        position:absolute!important;
        opacity:0!important;
        pointer-events:none!important;
    }}
}}

/* Teléfono angosto */
@media (max-width: 390px) {{
    .ps-tabbar [role="radiogroup"] {{
        padding-left:calc(50vw - 82px)!important;
        padding-right:calc(50vw - 82px)!important;
        gap:8px!important;
    }}

    .ps-tabbar label {{
        flex-basis:140px!important;
        width:140px!important;
        min-width:140px!important;
        height:78px!important;
        min-height:78px!important;
    }}
}}


/* V11.4 — CARRUSEL HORIZONTAL REAL */
.st-key-nav_v114_carousel,
.st-key-nav_v113_carousel {{
    width: calc(100% + 3.2rem) !important;
    margin-left: -1.6rem !important;
    margin-right: -1.6rem !important;
    margin-bottom: 22px !important;
    padding: 0 1.6rem !important;
    box-sizing: border-box !important;
    background: var(--azul) !important;
    border-top: 4px solid var(--rosa) !important;
    overflow: hidden !important;
}}
.st-key-nav_v114_carousel [data-testid="stRadio"],
.st-key-nav_v113_carousel [data-testid="stRadio"] {{
    width: 100% !important;
}}
.st-key-nav_v114_carousel [role="radiogroup"],
.st-key-nav_v113_carousel [role="radiogroup"] {{
    display: flex !important;
    flex-flow: row nowrap !important;
    align-items: stretch !important;
    gap: 0 !important;
    width: max-content !important;
    min-width: 100% !important;
    min-height: 58px !important;
    overflow: visible !important;
}}
.st-key-nav_v114_carousel label,
.st-key-nav_v113_carousel label {{
    flex: 0 0 auto !important;
    min-width: max-content !important;
    min-height: 58px !important;
    padding: 0 18px !important;
    margin: 0 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    border: 0 !important;
    border-radius: 0 !important;
    background: transparent !important;
    color: rgba(255,255,255,.76) !important;
    white-space: nowrap !important;
    font-weight: 850 !important;
    box-shadow: none !important;
}}
.st-key-nav_v114_carousel label:hover,
.st-key-nav_v113_carousel label:hover {{
    color: #FFFFFF !important;
    background: rgba(255,255,255,.06) !important;
}}
.st-key-nav_v114_carousel label:has(input:checked),
.st-key-nav_v113_carousel label:has(input:checked) {{
    color: #FFFFFF !important;
    background: #142E73 !important;
    box-shadow: inset 0 -5px 0 var(--rosa) !important;
}}
.st-key-nav_v114_carousel label *,
.st-key-nav_v113_carousel label * {{
    color: inherit !important;
    font-weight: inherit !important;
}}
.st-key-nav_v114_carousel [data-testid="stRadio"] input,
.st-key-nav_v113_carousel [data-testid="stRadio"] input,
.st-key-nav_v114_carousel [data-testid="stRadio"] [data-baseweb="radio"] > div:first-child,
.st-key-nav_v113_carousel [data-testid="stRadio"] [data-baseweb="radio"] > div:first-child {{
    position: absolute !important;
    opacity: 0 !important;
    width: 1px !important;
    height: 1px !important;
    pointer-events: none !important;
}}
@media (max-width: 768px) {{
    .ps-mobile-nav-title {{
        display: flex !important;
        align-items: center !important;
        justify-content: space-between !important;
        margin: 8px 2px 7px 2px !important;
        color: #5B6476 !important;
        font-size: 12px !important;
        font-weight: 850 !important;
    }}
    .ps-mobile-nav-arrow {{
        color: var(--rosa) !important;
        font-size: 18px !important;
        font-weight: 900 !important;
    }}
    .st-key-nav_v114_carousel,
    .st-key-nav_v113_carousel {{
        width: calc(100% + 1rem) !important;
        margin-left: -.5rem !important;
        margin-right: -.5rem !important;
        margin-bottom: 18px !important;
        padding: 10px 0 12px 0 !important;
        background: linear-gradient(135deg,#111A55 0%,#24126E 55%,#3B146E 100%) !important;
        border-top: 4px solid var(--rosa) !important;
        border-bottom: 1px solid rgba(255,255,255,.14) !important;
        overflow-x: auto !important;
        overflow-y: hidden !important;
        scroll-snap-type: x proximity !important;
        scroll-padding-inline: 18px !important;
        overscroll-behavior-x: contain !important;
        -webkit-overflow-scrolling: touch !important;
        scrollbar-width: none !important;
        touch-action: pan-x !important;
    }}
    .st-key-nav_v114_carousel::-webkit-scrollbar,
    .st-key-nav_v113_carousel::-webkit-scrollbar {{
        display: none !important;
    }}
    .st-key-nav_v114_carousel [data-testid="stRadio"],
    .st-key-nav_v113_carousel [data-testid="stRadio"] {{
        width: max-content !important;
        min-width: max-content !important;
        overflow: visible !important;
    }}
    .st-key-nav_v114_carousel [role="radiogroup"],
    .st-key-nav_v113_carousel [role="radiogroup"] {{
        display: flex !important;
        flex-flow: row nowrap !important;
        width: max-content !important;
        min-width: max-content !important;
        gap: 10px !important;
        padding: 0 14px !important;
        min-height: 58px !important;
    }}
    .st-key-nav_v114_carousel label,
    .st-key-nav_v113_carousel label {{
        flex: 0 0 auto !important;
        width: auto !important;
        min-width: 126px !important;
        max-width: 190px !important;
        height: 54px !important;
        min-height: 54px !important;
        padding: 0 15px !important;
        border-radius: 12px !important;
        border: 1px solid rgba(255,255,255,.22) !important;
        background: rgba(255,255,255,.09) !important;
        color: rgba(255,255,255,.80) !important;
        white-space: nowrap !important;
        text-align: center !important;
        scroll-snap-align: center !important;
        box-shadow: 0 5px 13px rgba(0,0,0,.14) !important;
        transform: none !important;
        opacity: 1 !important;
        font-size: 13px !important;
        line-height: 1.1 !important;
    }}
    .st-key-nav_v114_carousel label:has(input:checked),
    .st-key-nav_v113_carousel label:has(input:checked) {{
        background: #FFFFFF !important;
        color: var(--azul) !important;
        border-color: #FFFFFF !important;
        box-shadow: 0 7px 18px rgba(0,0,0,.22), inset 0 -5px 0 var(--rosa) !important;
    }}
    .st-key-nav_v114_carousel label:has(input:checked) *,
    .st-key-nav_v113_carousel label:has(input:checked) * {{
        color: var(--azul) !important;
    }}
}}
@media (min-width: 769px) {{
    .ps-mobile-nav-title {{
        display: none !important;
    }}
}}


/* V11.5: el carrusel es un componente independiente; ocultar restos del menú radio anterior. */
.ps-mobile-nav-title,
.st-key-nav_v114_carousel,
.st-key-nav_v113_carousel {{
    display: none !important;
}}


/* V11.6 — CARRUSEL CLICABLE SIN IFRAME */
.ps-carousel-title {{ display:none; }}
.ps-carousel-shell {{
  width:calc(100% + 3.2rem); margin-left:-1.6rem; margin-right:-1.6rem; margin-bottom:22px;
  background:linear-gradient(135deg,#111A55 0%,#24126E 55%,#3B146E 100%);
  border-top:4px solid var(--rosa); border-bottom:1px solid rgba(255,255,255,.14);
  overflow-x:auto; overflow-y:hidden; -webkit-overflow-scrolling:touch; scrollbar-width:none;
  overscroll-behavior-x:contain; touch-action:pan-x;
}}
.ps-carousel-shell::-webkit-scrollbar {{ display:none; }}
.ps-carousel-track {{ display:flex; flex-flow:row nowrap; align-items:stretch; gap:0; width:max-content; min-width:100%; min-height:58px; padding:0 1.6rem; }}
.ps-carousel-card {{
  flex:0 0 auto; min-width:max-content; min-height:58px; padding:0 18px; display:flex; align-items:center; justify-content:center;
  color:rgba(255,255,255,.76)!important; text-decoration:none!important; font-weight:850; white-space:nowrap;
  background:transparent; border-radius:0; box-shadow:none; cursor:pointer; -webkit-tap-highlight-color:transparent; user-select:none;
}}
.ps-carousel-card:hover {{ color:#fff!important; background:rgba(255,255,255,.06); }}
.ps-carousel-card.active {{ color:#fff!important; background:#142E73; box-shadow:inset 0 -5px 0 var(--rosa); }}
@media (max-width:768px) {{
  .ps-carousel-title {{ display:flex; align-items:center; justify-content:space-between; margin:8px 2px 7px; color:#5B6476; font-size:12px; font-weight:850; }}
  .ps-carousel-arrow {{ color:var(--rosa); font-size:18px; font-weight:900; }}
  .ps-carousel-shell {{ width:calc(100% + 1rem); margin-left:-.5rem; margin-right:-.5rem; margin-bottom:18px; padding:10px 0 12px; scroll-snap-type:x proximity; scroll-padding-inline:18px; }}
  .ps-carousel-track {{ gap:10px; min-width:max-content; padding:0 14px; min-height:58px; }}
  .ps-carousel-card {{
    flex:0 0 154px; width:154px; min-width:154px; max-width:190px; height:58px; min-height:58px; padding:0 15px;
    border-radius:14px; border:1px solid rgba(255,255,255,.22); background:rgba(255,255,255,.09);
    color:rgba(255,255,255,.80)!important; text-align:center; white-space:normal; line-height:1.08; font-size:13px;
    scroll-snap-align:center; box-shadow:0 5px 13px rgba(0,0,0,.14); transform:scale(.92); opacity:.78;
  }}
  .ps-carousel-card.active {{
    background:#fff; color:var(--azul)!important; border-color:#fff;
    box-shadow:0 7px 18px rgba(0,0,0,.22), inset 0 -5px 0 var(--rosa); transform:scale(1); opacity:1;
  }}
}}


/* V11.7 — MENÚ NATIVO SIN PÉRDIDA DE SESIÓN */
.ps-carousel-title {{
    display:none;
}}
.st-key-nav_session_safe {{
    width: calc(100% + 3.2rem) !important;
    margin-left: -1.6rem !important;
    margin-right: -1.6rem !important;
    margin-bottom: 22px !important;
    padding: 0 1.6rem !important;
    background: var(--azul) !important;
    border-top: 4px solid var(--rosa) !important;
    overflow-x: auto !important;
    overflow-y: hidden !important;
    -webkit-overflow-scrolling: touch !important;
    scrollbar-width: none !important;
}}
.st-key-nav_session_safe::-webkit-scrollbar {{ display:none !important; }}
.st-key-nav_session_safe [role="radiogroup"] {{
    display:flex !important;
    flex-flow:row nowrap !important;
    width:max-content !important;
    min-width:100% !important;
    gap:0 !important;
}}
.st-key-nav_session_safe label {{
    flex:0 0 auto !important;
    min-width:max-content !important;
    min-height:58px !important;
    padding:0 18px !important;
    display:flex !important;
    align-items:center !important;
    justify-content:center !important;
    white-space:nowrap !important;
    color:rgba(255,255,255,.78) !important;
    background:transparent !important;
    border-radius:0 !important;
    font-weight:850 !important;
}}
.st-key-nav_session_safe label:has(input:checked) {{
    color:#fff !important;
    background:#142E73 !important;
    box-shadow:inset 0 -5px 0 var(--rosa) !important;
}}
.st-key-nav_session_safe label * {{ color:inherit !important; font-weight:inherit !important; }}
.st-key-nav_session_safe input,
.st-key-nav_session_safe [data-baseweb="radio"] > div:first-child {{
    position:absolute !important;
    opacity:0 !important;
    width:1px !important;
    height:1px !important;
}}

/* PORTAL DE ACCESO ESTILO PRICE SHOES */
[data-testid="stSidebar"]:has(.login-portal-shell) {{ display:none !important; }}
.login-portal-shell {{
    position:relative;
    max-width:760px;
    min-height:290px;
    margin:50px auto 0;
    border-radius:24px 24px 0 0;
    overflow:hidden;
    background:
      linear-gradient(rgba(3,25,20,.78),rgba(3,25,20,.86)),
      radial-gradient(circle at 50% 15%,rgba(236,0,126,.20),transparent 38%),
      linear-gradient(135deg,#10245F,#063A2D);
    box-shadow:0 20px 55px rgba(16,36,95,.20);
}}
.login-portal-brand {{
    position:relative;
    z-index:2;
    display:flex;
    flex-direction:column;
    align-items:center;
    padding:44px 20px 28px;
    color:#fff;
}}
.login-portal-logo {{
    width:150px;
    height:92px;
    border:3px solid #fff;
    border-radius:50%;
    display:flex;
    align-items:center;
    justify-content:center;
    text-align:center;
    font-family:Georgia,serif;
    font-size:34px;
    line-height:.72;
    font-weight:900;
    text-shadow:0 2px 5px rgba(0,0,0,.45);
}}
.login-portal-title {{ margin-top:18px; font-size:30px; font-weight:900; }}
.login-portal-subtitle {{ margin-top:5px; font-size:13px; opacity:.8; }}
[data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) {{
    max-width:760px;
    margin:0 auto 40px;
    padding:0 150px 36px;
    background:#08251F;
    border-radius:0 0 24px 24px;
    border:0 !important;
    box-shadow:0 20px 55px rgba(16,36,95,.20);
}}
[data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) label {{ color:#fff !important; }}
[data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) input {{
    color:#fff !important;
    background:transparent !important;
    border:0 !important;
    border-bottom:1px solid rgba(255,255,255,.7) !important;
    border-radius:0 !important;
}}
[data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) button {{
    margin-top:12px !important;
    background:var(--rosa) !important;
    color:#fff !important;
    border-radius:0 !important;
    min-height:52px !important;
    font-weight:900 !important;
}}
@media(max-width:768px) {{
    .ps-carousel-title {{
        display:flex;
        align-items:center;
        justify-content:space-between;
        margin:8px 2px 7px;
        color:#5B6476;
        font-size:12px;
        font-weight:850;
    }}
    .ps-carousel-arrow {{ color:var(--rosa); font-size:18px; }}
    .st-key-nav_session_safe {{
        width:calc(100% + 1rem) !important;
        margin-left:-.5rem !important;
        margin-right:-.5rem !important;
        padding:10px 0 12px !important;
        background:linear-gradient(135deg,#111A55,#24126E 55%,#3B146E) !important;
        scroll-snap-type:x proximity !important;
    }}
    .st-key-nav_session_safe [role="radiogroup"] {{ gap:10px !important; padding:0 14px !important; min-width:max-content !important; }}
    .st-key-nav_session_safe label {{
        min-width:154px !important;
        width:154px !important;
        min-height:58px !important;
        border:1px solid rgba(255,255,255,.22) !important;
        border-radius:14px !important;
        background:rgba(255,255,255,.09) !important;
        color:rgba(255,255,255,.8) !important;
        scroll-snap-align:center !important;
    }}
    .st-key-nav_session_safe label:has(input:checked) {{
        background:#fff !important;
        color:var(--azul) !important;
        border-color:#fff !important;
        box-shadow:0 7px 18px rgba(0,0,0,.22), inset 0 -5px 0 var(--rosa) !important;
    }}
    .login-portal-shell {{ margin:20px auto 0; min-height:230px; border-radius:18px 18px 0 0; }}
    .login-portal-brand {{ padding:28px 14px 22px; }}
    .login-portal-logo {{ width:118px; height:72px; font-size:27px; }}
    .login-portal-title {{ font-size:25px; }}
    [data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) {{
        padding:0 24px 28px;
        border-radius:0 0 18px 18px;
    }}
}}


/* V11.8 — Portal corporativo, login completo y menú superior */
.login-fullscreen-bg {{
    position: fixed;
    inset: 0;
    z-index: -1;
    background:
        linear-gradient(rgba(0,25,28,.82), rgba(0,36,31,.92)),
        radial-gradient(circle at 50% 20%, rgba(255,255,255,.08), transparent 38%),
        linear-gradient(145deg,#071F2A,#003B31);
}}
.login-brand-zone {{
    max-width: 650px;
    margin: 5vh auto 0;
    text-align: center;
    color: #fff;
}}
.login-portal-title {{
    font-size: 40px !important;
    margin-top: 20px;
}}
.login-portal-subtitle {{
    font-size: 25px !important;
    font-weight: 800;
    margin-top: 4px;
}}
[data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) {{
    max-width: 650px !important;
    margin: 25px auto 0 !important;
    padding: 28px 38px 34px !important;
    border-radius: 18px !important;
    background: rgba(0,39,34,.90) !important;
    border: 1px solid rgba(255,255,255,.18) !important;
    box-shadow: 0 18px 50px rgba(0,0,0,.30) !important;
}}
[data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) label,
[data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) p {{
    color: #fff !important;
    font-weight: 800 !important;
}}
[data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) input {{
    color: #111827 !important;
    background: #fff !important;
    -webkit-text-fill-color: #111827 !important;
}}
[data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) input::placeholder {{
    color: #667085 !important;
    opacity: 1 !important;
}}
.portal-main-brand {{
    display: flex;
    align-items: center;
    gap: 18px;
    min-height: 88px;
}}
.portal-main-logo {{
    width: 110px;
    min-width: 110px;
}}
.portal-main-title {{
    color: var(--azul);
    font-weight: 900;
    font-size: 31px;
    line-height: 1.05;
}}
.portal-main-subtitle {{
    color: #596174;
    font-weight: 700;
    font-size: 14px;
    margin-top: 8px;
}}
.portal-user-date {{
    text-align: right;
    color: #71798A;
    font-size: 11px;
    margin-top: 4px;
}}
.portal-pink-line {{
    height: 5px;
    background: var(--rosa);
    margin: 2px -1rem 14px;
}}
.portal-readonly-badge {{
    border: 1px solid #D5DCEA;
    background: #fff;
    border-radius: 8px;
    padding: 10px 14px;
    color: #596174;
    text-align: center;
    font-weight: 750;
}}
@media (max-width: 768px) {{
    .login-brand-zone {{
        margin-top: 2vh;
        padding: 0 14px;
    }}
    .login-portal-title {{
        font-size: 28px !important;
    }}
    .login-portal-subtitle {{
        font-size: 19px !important;
    }}
    [data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) {{
        margin: 18px 10px 0 !important;
        padding: 22px 18px 26px !important;
    }}
    .portal-main-brand {{
        gap: 10px;
        min-height: 66px;
    }}
    .portal-main-logo {{
        width: 72px;
        min-width: 72px;
    }}
    .portal-main-title {{
        font-size: 21px;
    }}
    .portal-main-subtitle {{
        font-size: 10px;
        margin-top: 4px;
    }}
}}


/* V11.9 — corrección de acceso, cabecera y administración */
.login-brand-card {{
    text-align: center;
    color: #fff;
    margin: 0 auto 18px;
}}
.login-real-logo {{
    width: 180px;
    margin: 0 auto 8px;
}}
.login-real-logo img {{
    width: 100% !important;
    max-height: 120px !important;
    object-fit: contain !important;
    filter: none !important;
}}
.login-portal-title {{
    color: #fff !important;
    font-size: 40px !important;
    font-weight: 900 !important;
    line-height: 1.05 !important;
    margin-top: 8px !important;
}}
.login-portal-subtitle {{
    color: #fff !important;
    font-size: 24px !important;
    font-weight: 800 !important;
    margin-top: 4px !important;
}}
[data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) {{
    width: 100% !important;
    max-width: 760px !important;
    margin: 0 auto !important;
    padding: 28px 38px 34px !important;
    border-radius: 18px !important;
    background: rgba(0,55,47,.94) !important;
    border: 1px solid rgba(255,255,255,.20) !important;
    box-shadow: 0 20px 55px rgba(0,0,0,.35) !important;
}}
[data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) input {{
    color: #111827 !important;
    -webkit-text-fill-color: #111827 !important;
    background: #fff !important;
}}
.portal-header-spacer {{
    height: 28px;
}}
.portal-main-brand {{
    padding-top: 12px !important;
    padding-bottom: 12px !important;
    overflow: visible !important;
}}
.portal-main-logo {{
    background: transparent !important;
    border: 0 !important;
    overflow: visible !important;
}}
.portal-main-logo img {{
    background: transparent !important;
    mix-blend-mode: multiply !important;
    object-fit: contain !important;
}}
.portal-main-title,
.portal-main-subtitle {{
    overflow: visible !important;
}}
[data-testid="stPopover"] button {{
    min-height: 46px !important;
}}
@media (max-width:768px) {{
    .login-real-logo {{
        width: 135px;
    }}
    .login-portal-title {{
        font-size: 30px !important;
    }}
    .login-portal-subtitle {{
        font-size: 20px !important;
    }}
    [data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) {{
        padding: 22px 18px 26px !important;
    }}
    .portal-header-spacer {{
        height: 16px;
    }}
}}


/* V12 — Portal de aplicaciones y módulo Cambios y Muertos */
.portal-home-brand {{
    display:flex;
    align-items:center;
    gap:18px;
    min-height:92px;
    padding:12px 0;
}}
.portal-home-logo {{
    width:105px;
    min-width:105px;
}}
.portal-home-title {{
    color:var(--azul);
    font-size:32px;
    font-weight:900;
    line-height:1.05;
}}
.portal-home-subtitle {{
    color:#667085;
    font-size:14px;
    font-weight:700;
    margin-top:7px;
}}
.portal-section-title {{
    margin-top:22px;
    color:var(--azul);
    font-size:28px;
    font-weight:900;
}}
.portal-section-subtitle {{
    color:#6B7280;
    margin:5px 0 18px;
}}
.app-tile {{
    display:flex;
    align-items:center;
    gap:20px;
    min-height:150px;
    padding:24px 28px;
    border:1px solid #D9E1EF;
    border-radius:16px;
    background:#FFFFFF;
    box-shadow:0 12px 30px rgba(31,42,68,.08);
}}
.app-tile-icon {{
    display:flex;
    align-items:center;
    justify-content:center;
    width:72px;
    height:72px;
    min-width:72px;
    border-radius:18px;
    background:linear-gradient(135deg,var(--azul),#402080);
    color:#FFFFFF;
    font-size:36px;
    font-weight:900;
}}
.app-tile-title {{
    color:var(--azul);
    font-size:25px;
    font-weight:900;
}}
.app-tile-subtitle {{
    color:#667085;
    margin-top:6px;
    line-height:1.35;
}}

/* Pestañas internas de Cambios y Muertos */
.st-key-nav_v123_tabs {{
    width:calc(100% + 2rem) !important;
    margin-left:-1rem !important;
    margin-right:-1rem !important;
    margin-bottom:22px !important;
    padding:0 1rem !important;
    background:var(--azul) !important;
    border-top:4px solid var(--rosa) !important;
    overflow-x:auto !important;
    overflow-y:hidden !important;
    scrollbar-width:none !important;
    -webkit-overflow-scrolling:touch !important;
}}
.st-key-nav_v123_tabs::-webkit-scrollbar {{
    display:none !important;
}}
.st-key-nav_v123_tabs [role="radiogroup"] {{
    display:flex !important;
    flex-flow:row nowrap !important;
    width:max-content !important;
    min-width:100% !important;
    gap:0 !important;
}}
.st-key-nav_v123_tabs label {{
    flex:0 0 auto !important;
    min-width:max-content !important;
    min-height:58px !important;
    padding:0 18px !important;
    margin:0 !important;
    display:flex !important;
    align-items:center !important;
    justify-content:center !important;
    color:rgba(255,255,255,.76) !important;
    white-space:nowrap !important;
    font-weight:850 !important;
    background:transparent !important;
}}
.st-key-nav_v123_tabs label:has(input:checked) {{
    color:#FFFFFF !important;
    background:#142E73 !important;
    box-shadow:inset 0 -5px 0 var(--rosa) !important;
}}
.st-key-nav_v123_tabs label *,
.st-key-nav_v123_tabs label:has(input:checked) * {{
    color:inherit !important;
    font-weight:inherit !important;
}}
.st-key-nav_v123_tabs input,
.st-key-nav_v123_tabs [data-baseweb="radio"] > div:first-child {{
    position:absolute !important;
    opacity:0 !important;
    width:1px !important;
    height:1px !important;
}}

@media(max-width:768px) {{
    .portal-home-brand {{
        gap:10px;
        min-height:70px;
    }}
    .portal-home-logo {{
        width:72px;
        min-width:72px;
    }}
    .portal-home-title {{
        font-size:23px;
    }}
    .portal-home-subtitle {{
        font-size:10px;
    }}
    .app-tile {{
        padding:18px;
        min-height:125px;
    }}
    .app-tile-icon {{
        width:58px;
        height:58px;
        min-width:58px;
        font-size:28px;
    }}
    .app-tile-title {{
        font-size:20px;
    }}
    .st-key-nav_v123_tabs {{
        width:calc(100% + 1rem) !important;
        margin-left:-.5rem !important;
        margin-right:-.5rem !important;
        padding:10px 0 12px !important;
        background:linear-gradient(135deg,#111A55,#24126E 55%,#3B146E) !important;
        scroll-snap-type:x proximity !important;
    }}
    .st-key-nav_v123_tabs [role="radiogroup"] {{
        gap:10px !important;
        padding:0 14px !important;
        min-width:max-content !important;
    }}
    .st-key-nav_v123_tabs label {{
        min-width:145px !important;
        height:56px !important;
        min-height:56px !important;
        border-radius:13px !important;
        border:1px solid rgba(255,255,255,.22) !important;
        background:rgba(255,255,255,.09) !important;
        scroll-snap-align:center !important;
    }}
    .st-key-nav_v123_tabs label:has(input:checked) {{
        background:#FFFFFF !important;
        color:var(--azul) !important;
        border-color:#FFFFFF !important;
        box-shadow:0 7px 18px rgba(0,0,0,.22), inset 0 -5px 0 var(--rosa) !important;
    }}
}}


/* V12.1 — estructura inspirada en Portal Web Price Shoes */
:root {{ --portal-blue:#004B85; --portal-dark:#01315A; --portal-light:#337AB7; --portal-pink:#DA0080; --portal-active:#EA0083; }}
.ps-portal-top-spacer,.ps-module-spacer{{height:18px}}
.ps-portal-topbar-brand{{display:flex;align-items:center;gap:18px;min-height:68px}}
.ps-portal-logo,.ps-module-logo{{width:100px;min-width:100px;background:transparent!important}}
.ps-portal-logo img,.ps-module-logo img{{width:100%!important;max-height:68px!important;object-fit:contain!important;background:transparent!important}}
.ps-portal-system{{font-size:22px;font-weight:800;color:var(--portal-dark)}}
.ps-portal-pinkbar{{margin:4px -1rem 18px;padding:8px 20px;background:var(--portal-pink);color:#fff;font-size:16px;font-weight:800}}
.ps-profile-card,.ps-portal-panel{{background:#fff;border:1px solid #ccc;border-radius:10px;overflow:hidden;margin-bottom:20px}}
.ps-profile-title,.ps-portal-panel-head{{padding:9px 15px;background:var(--portal-blue);color:#fff;font-size:16px;font-weight:800;text-align:center}}
.ps-profile-row{{display:grid;grid-template-columns:125px 1fr;gap:12px;padding:10px 16px;border-bottom:1px solid #eee;color:var(--portal-dark)}}
.ps-profile-row:last-child{{border-bottom:0}}.ps-profile-row span{{font-weight:700}}.ps-profile-row b{{font-weight:600;color:#333}}
.ps-notice-row{{display:grid;grid-template-columns:95px 1fr;gap:10px;padding:12px 15px;border-bottom:1px solid #eee}}.ps-notice-row:last-child{{border:0}}
.ps-promo-head{{padding:9px 15px;background:#3B9741;color:#fff;font-size:16px;font-weight:800;text-align:center}}
.ps-app-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin:14px 0}}
.ps-app-card{{position:relative;min-height:145px;padding:24px 18px 18px;background:#fff;border:1px solid #e1e4e8;border-bottom:4px solid #ccc;text-align:center;box-shadow:0 4px 12px rgba(0,0,0,.04)}}
.ps-app-card-main{{border-bottom-color:var(--portal-pink)}}.ps-app-disabled{{opacity:.58}}
.ps-app-code{{position:absolute;left:14px;bottom:10px;color:var(--portal-blue);font-weight:900;font-size:13px}}
.ps-app-icon{{color:var(--portal-blue);font-size:34px;font-weight:900}}.ps-app-name{{font-size:20px;font-weight:800;color:#454545;margin-top:4px}}.ps-app-desc{{font-size:12px;color:#777;margin-top:7px}}
.ps-module-brand{{display:flex;align-items:center;gap:15px;min-height:78px;padding:10px 0}}.ps-module-title{{font-size:30px;line-height:1.05;font-weight:900;color:var(--portal-dark)}}.ps-module-subtitle{{margin-top:7px;color:#596174;font-weight:700}}
.ps-module-pinkline{{height:5px;margin:2px -1rem 12px;background:var(--portal-pink)}}
.st-key-nav_v123_tabs{{background:var(--portal-blue)!important;border-top:0!important;border-bottom:3px solid var(--portal-pink)!important}}
.st-key-nav_v123_tabs label:has(input:checked){{background:var(--portal-light)!important;box-shadow:inset 0 -4px 0 #fff!important}}
.ag-header,.ag-header-row,.ag-header-cell{{background:var(--portal-dark)!important;color:#fff!important}}.ag-header-cell-text{{color:#fff!important;font-weight:700!important}}
@media(max-width:768px){{
 .ps-portal-topbar-brand{{gap:10px}}.ps-portal-logo,.ps-module-logo{{width:70px;min-width:70px}}.ps-portal-system{{font-size:18px}}.ps-portal-pinkbar{{font-size:12px;padding:7px 10px}}
 .ps-app-grid{{grid-template-columns:1fr}}.ps-profile-row{{grid-template-columns:95px 1fr;font-size:12px}}.ps-module-title{{font-size:20px}}.ps-module-subtitle{{font-size:10px}}
}}


/* V12.4 — tarjeta clicable completa y menú administrativo de tres puntos */
.ps-portal-top-spacer {{
    height: 54px !important;
}}
.ps-portal-topbar-brand {{
    padding-top: 18px !important;
    padding-bottom: 14px !important;
    overflow: visible !important;
}}
.ps-portal-logo,
.ps-portal-logo img {{
    overflow: visible !important;
}}
.ps-portal-logo img {{
    object-fit: contain !important;
    max-height: 105px !important;
}}

/* Convertir el botón de Streamlit en tarjeta de aplicación */
.st-key-open_cambios_muertos_card button {{
    min-height: 210px !important;
    height: 210px !important;
    padding: 34px 24px !important;
    border: 1px solid #D8DEE9 !important;
    border-radius: 0 !important;
    border-bottom: 6px solid var(--portal-pink) !important;
    background: #FFFFFF !important;
    color: #3E3E3E !important;
    box-shadow: 0 4px 0 rgba(0,0,0,.14) !important;
    white-space: pre-line !important;
    font-size: 16px !important;
    font-weight: 700 !important;
    line-height: 1.65 !important;
    transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease !important;
}}
.st-key-open_cambios_muertos_card button::first-line {{
    color: var(--portal-blue) !important;
    font-size: 36px !important;
}}
.st-key-open_cambios_muertos_card button:hover {{
    transform: translateY(-2px) !important;
    box-shadow: 0 10px 24px rgba(0,75,133,.16) !important;
    border-color: var(--portal-blue) !important;
}}
.st-key-open_cambios_muertos_card button p {{
    color: inherit !important;
    font-size: inherit !important;
    font-weight: inherit !important;
}}

/* Tres puntos alineados arriba a la derecha de la tarjeta */
.st-key-open_cambios_muertos_card {{
    position: relative !important;
}}
[data-testid="stPopover"]:has(button[aria-label="⋮"]) {{
    margin-top: -220px !important;
    margin-left: auto !important;
    width: 46px !important;
    position: relative !important;
    z-index: 6 !important;
}}
[data-testid="stPopover"]:has(button[aria-label="⋮"]) > button,
[data-testid="stPopover"] button:has(p:only-child) {{
    min-width: 42px !important;
    width: 42px !important;
    height: 42px !important;
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
    font-size: 28px !important;
    color: var(--portal-blue) !important;
    box-shadow: none !important;
}}

@media(max-width:768px) {{
    .ps-portal-top-spacer {{
        height: 34px !important;
    }}
    .ps-portal-topbar-brand {{
        padding-top: 12px !important;
    }}
    .st-key-open_cambios_muertos_card button {{
        min-height: 175px !important;
        height: 175px !important;
        padding: 26px 16px !important;
        font-size: 14px !important;
    }}
    [data-testid="stPopover"]:has(button[aria-label="⋮"]) {{
        margin-top: -184px !important;
    }}
}}


/* V12.5 — usuario compacto, icono grande, menú superior y logo navegable */

div[data-testid="column"]:last-child [data-testid="stPopover"] button {{
    min-width: 190px !important;
    width: 100% !important;
    max-width: 100% !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
}}
div[data-testid="column"]:last-child [data-testid="stPopover"] button p {{
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    font-size: 15px !important;
}}

.st-key-app_card_shell {{
    position: relative !important;
    width: 100% !important;
}}
.st-key-app_admin_menu {{
    position: absolute !important;
    top: 8px !important;
    right: 8px !important;
    z-index: 20 !important;
    width: 46px !important;
}}
.st-key-app_admin_menu [data-testid="stPopover"] {{
    width: 46px !important;
}}
.st-key-app_admin_menu [data-testid="stPopover"] > button {{
    width: 42px !important;
    min-width: 42px !important;
    height: 42px !important;
    min-height: 42px !important;
    padding: 0 !important;
    border: 0 !important;
    border-radius: 50% !important;
    background: rgba(255,255,255,.94) !important;
    color: var(--portal-blue) !important;
    font-size: 28px !important;
    line-height: 1 !important;
    box-shadow: 0 3px 10px rgba(0,0,0,.12) !important;
}}
.st-key-app_admin_menu [data-testid="stPopover"] > button:hover {{
    background: #F2F6FC !important;
}}

.st-key-open_cambios_muertos_card button {{
    padding-top: 24px !important;
}}
.st-key-open_cambios_muertos_card button p {{
    white-space: pre-line !important;
    line-height: 1.7 !important;
}}
.st-key-open_cambios_muertos_card button p::first-line {{
    font-size: 58px !important;
    line-height: 1 !important;
    color: var(--portal-blue) !important;
    font-weight: 900 !important;
}}

.st-key-logo_home_btn button {{
    cursor: pointer !important;
}}

.st-key-back_to_apps {{
    display: none !important;
}}

@media(max-width:768px) {{
    div[data-testid="column"]:last-child [data-testid="stPopover"] button {{
        min-width: 135px !important;
    }}
    .st-key-open_cambios_muertos_card button p::first-line {{
        font-size: 46px !important;
    }}
}}


/* V12.6 — corrección de icono y usuario */

/* El icono crece sin modificar el tamaño de los textos de la tarjeta. */
.st-key-open_cambios_muertos_card button {{
    position: relative !important;
    padding: 92px 22px 28px !important;
    white-space: pre-line !important;
    font-size: 18px !important;
    line-height: 1.55 !important;
}}
.st-key-open_cambios_muertos_card button::before {{
    content: "↻";
    position: absolute;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    color: var(--portal-blue);
    font-size: 64px;
    font-weight: 900;
    line-height: 1;
}}
.st-key-open_cambios_muertos_card button p {{
    font-size: 18px !important;
    line-height: 1.55 !important;
    font-weight: 750 !important;
    white-space: pre-line !important;
}}
.st-key-open_cambios_muertos_card button p::first-line {{
    font-size: 18px !important;
    line-height: 1.55 !important;
    color: inherit !important;
    font-weight: 850 !important;
}}

/* Usuario de una sola línea y con ancho suficiente. */
.st-key-portal_user_menu,
.st-key-module_user_menu {{
    width: 100% !important;
    min-width: 0 !important;
}}
.st-key-portal_user_menu [data-testid="stPopover"],
.st-key-module_user_menu [data-testid="stPopover"] {{
    width: 100% !important;
}}
.st-key-portal_user_menu [data-testid="stPopover"] > button,
.st-key-module_user_menu [data-testid="stPopover"] > button {{
    width: 100% !important;
    min-width: 0 !important;
    height: 58px !important;
    padding: 0 16px !important;
    white-space: nowrap !important;
    overflow: hidden !important;
}}
.st-key-portal_user_menu [data-testid="stPopover"] > button p,
.st-key-module_user_menu [data-testid="stPopover"] > button p {{
    width: 100% !important;
    display: block !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    text-align: center !important;
    font-size: 15px !important;
    line-height: 1.2 !important;
}}
.st-key-module_user_menu .portal-user-date {{
    white-space: nowrap !important;
    text-align: right !important;
    font-size: 11px !important;
}}

@media (max-width: 768px) {{
    .st-key-open_cambios_muertos_card button {{
        padding-top: 78px !important;
        font-size: 15px !important;
    }}
    .st-key-open_cambios_muertos_card button::before {{
        top: 16px;
        font-size: 52px;
    }}
    .st-key-open_cambios_muertos_card button p,
    .st-key-open_cambios_muertos_card button p::first-line {{
        font-size: 15px !important;
    }}
    .st-key-portal_user_menu [data-testid="stPopover"] > button,
    .st-key-module_user_menu [data-testid="stPopover"] > button {{
        height: 50px !important;
        padding: 0 10px !important;
    }}
    .st-key-portal_user_menu [data-testid="stPopover"] > button p,
    .st-key-module_user_menu [data-testid="stPopover"] > button p {{
        font-size: 13px !important;
    }}
}}


/* V12.8 — diálogo modal para administración de archivos */
div[data-testid="stDialog"] [data-testid="stFileUploader"] {{
    margin-top: 12px !important;
}}
div[data-testid="stDialog"] [data-testid="stAlert"] {{
    margin-bottom: 12px !important;
}}
div[data-testid="stDialog"] button[kind="primary"] {{
    background: var(--portal-pink) !important;
    border-color: var(--portal-pink) !important;
}}


/* V12.9 — acceso más compacto */
.login-brand-card {{ margin: 0 auto 10px !important; }}
.login-real-logo {{ width: 125px !important; margin: 0 auto 4px !important; }}
.login-real-logo img {{ max-height: 82px !important; }}
.login-portal-title {{ font-size: 30px !important; margin-top: 4px !important; }}
.login-portal-subtitle {{ font-size: 18px !important; margin-top: 2px !important; }}
[data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) {{
    max-width: 610px !important;
    padding: 20px 28px 24px !important;
    margin-top: 10px !important;
    border-radius: 16px !important;
}}
[data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) [data-testid="stTextInput"] {{ margin-bottom: 6px !important; }}
[data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) input {{ min-height: 46px !important; }}
[data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) button[kind="primary"] {{ min-height: 48px !important; margin-top: 6px !important; }}
body:has(input[aria-label="Usuario o correo"]) .block-container {{
    justify-content: center !important;
    padding-top: 1.5vh !important;
    padding-bottom: 1.5vh !important;
}}
@media (max-width: 768px) {{
    .login-real-logo {{ width: 105px !important; }}
    .login-real-logo img {{ max-height: 68px !important; }}
    .login-portal-title {{ font-size: 25px !important; }}
    .login-portal-subtitle {{ font-size: 16px !important; }}
    [data-testid="stForm"]:has(input[aria-label="Usuario o correo"]) {{
        margin: 8px 10px 0 !important;
        padding: 17px 16px 20px !important;
    }}
}}


/* V13.1 — modal de carga en dos pasos */
div[data-testid="stDialog"] {{
    max-width: 980px !important;
}}
div[data-testid="stDialog"] [data-testid="stFileUploader"] {{
    margin-top: 8px !important;
}}
div[data-testid="stDialog"] [data-testid="stFileUploaderDropzone"] {{
    min-height: 94px !important;
    padding: 12px !important;
}}
div[data-testid="stDialog"] button[kind="primary"] {{
    min-height: 46px !important;
}}


/* V14.0 — Administración estable sin diálogos */
.st-key-app_admin_menu [data-testid="stPopoverBody"],
div[data-baseweb="popover"] [data-testid="stPopoverBody"] {{
    min-width: 430px !important;
    max-width: 520px !important;
    max-height: 78vh !important;
    overflow-y: auto !important;
}}

.st-key-app_admin_menu [data-testid="stFileUploaderDropzone"] {{
    min-height: 86px !important;
    padding: 10px !important;
}}

.st-key-app_admin_menu button[kind="primary"] {{
    background: var(--portal-pink) !important;
    border-color: var(--portal-pink) !important;
}}

@media (max-width: 768px) {{
    .st-key-app_admin_menu [data-testid="stPopoverBody"],
    div[data-baseweb="popover"] [data-testid="stPopoverBody"] {{
        min-width: min(92vw, 430px) !important;
        max-width: 92vw !important;
        max-height: 72vh !important;
    }}
}}


/* V15.0 — Administración como página estable */
.admin-section-title {{
    background: #244F93;
    color: #FFFFFF;
    font-weight: 800;
    font-size: 18px;
    padding: 12px 16px;
    border-radius: 10px 10px 0 0;
    margin-bottom: 14px;
}}
.admin-status {{
    margin-top: 12px;
    border-radius: 10px;
    padding: 12px 14px;
    font-weight: 750;
}}
.admin-status-ok {{
    background: #E7F8EE;
    color: #087A3D;
    border: 1px solid #B8E7CC;
}}
.admin-status-warn {{
    background: #FFF7DA;
    color: #9A6900;
    border: 1px solid #F0D88A;
}}
.st-key-app_admin_menu {{
    position: absolute !important;
    top: 8px !important;
    right: 8px !important;
    z-index: 20 !important;
    width: 46px !important;
}}
.st-key-app_admin_menu button {{
    width: 42px !important;
    min-width: 42px !important;
    height: 42px !important;
    min-height: 42px !important;
    padding: 0 !important;
    border-radius: 50% !important;
    border: 0 !important;
    background: rgba(255,255,255,.96) !important;
    color: #244F93 !important;
    font-size: 26px !important;
    box-shadow: 0 3px 10px rgba(0,0,0,.12) !important;
}}
.st-key-app_admin_menu button p {{
    font-size: 26px !important;
    line-height: 1 !important;
}}
@media (max-width: 768px) {{
    .admin-section-title {{
        font-size: 16px;
    }}
}}


/* V16 Enterprise */
[data-testid="stMetric"] {{
    min-height: 118px !important;
    border: 1px solid #DCE3EF !important;
    border-radius: 14px !important;
    padding: 15px !important;
    background: #FFFFFF !important;
    box-shadow: 0 5px 14px rgba(16,36,95,.06) !important;
}}
[data-testid="stMetricLabel"] p {{
    font-weight: 750 !important;
    color: #24134F !important;
}}
[data-testid="stMetricValue"] {{
    color: #EC007C !important;
}}


/* ===== V16.2 DISEÑO PORTAL WEB / REPORTES EJECUTIVOS ===== */
:root{{
  --portal-navy:#082B63;
  --portal-blue:#173B73;
  --portal-cobalt:#3366CC;
  --portal-purple:#A26BFF;
  --portal-pink:#FF6FB5;
  --portal-bg:#F3F6FB;
  --portal-border:#DDE5F1;
}}
html,body,[data-testid="stAppViewContainer"]{{
  background:var(--portal-bg)!important;
}}
.block-container{{
  padding-top:.75rem!important;
  padding-left:1.35rem!important;
  padding-right:1.35rem!important;
  max-width:100%!important;
}}
[data-testid="stSidebar"]{{
  background:linear-gradient(180deg,#06285F 0%,#0B3A84 100%)!important;
  min-width:245px!important;
  max-width:245px!important;
  border-right:0!important;
}}
[data-testid="stSidebar"] > div:first-child{{
  padding:0!important;
}}
.side-brand{{
  height:64px;
  padding:0 18px;
  display:flex;
  align-items:center;
  gap:12px;
  color:#FFF;
  font-size:16px;
  font-weight:850;
  border-bottom:1px solid rgba(255,255,255,.13);
}}
.side-brand-menu{{font-size:22px}}
[data-testid="stSidebar"] [role="radiogroup"]{{
  padding:14px 10px!important;
  gap:4px!important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label{{
  color:#DCE7FF!important;
  min-height:43px!important;
  border-radius:7px!important;
  padding:0 12px!important;
  transition:.15s ease;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:hover{{
  background:rgba(255,255,255,.1)!important;
  color:#FFF!important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){{
  background:#3366CC!important;
  color:#FFF!important;
  box-shadow:inset 3px 0 0 #FFFFFF;
}}
[data-testid="stSidebar"] [role="radiogroup"] label p{{
  font-size:13px!important;
  font-weight:760!important;
}}
.executive-top-shell{{
  position:fixed;
  top:0;
  left:245px;
  right:0;
  height:64px;
  background:linear-gradient(90deg,#06285F,#0C3C86);
  z-index:5;
  box-shadow:0 4px 14px rgba(6,40,95,.14);
}}
.st-key-logo_home_btn,.executive-brand,.st-key-module_user_menu{{
  position:relative;
  z-index:10;
}}
.executive-brand{{
  color:#FFF;
  min-height:46px;
  display:flex;
  align-items:center;
}}
.executive-brand-title{{
  font-size:16px;
  font-weight:850;
}}
.st-key-module_user_menu button{{
  min-height:42px!important;
  border:0!important;
  background:transparent!important;
  color:#FFF!important;
  font-size:12px!important;
  text-align:right!important;
}}
[data-testid="stMain"]{{
  padding-top:65px!important;
}}
h1,h2,h3{{
  color:#16213B!important;
  letter-spacing:-.02em;
}}
h2{{
  font-size:24px!important;
  margin-top:.25rem!important;
  margin-bottom:.4rem!important;
}}
[data-testid="stMetric"]{{
  background:#FFF!important;
  border:1px solid var(--portal-border)!important;
  border-radius:8px!important;
  min-height:105px!important;
  padding:14px 16px!important;
  box-shadow:0 4px 14px rgba(23,59,115,.05)!important;
}}
[data-testid="stMetricLabel"] p{{
  color:#4B5565!important;
  font-size:12px!important;
  font-weight:700!important;
}}
[data-testid="stMetricValue"]{{
  color:#173B73!important;
  font-size:25px!important;
  font-weight:850!important;
}}
.panel-title{{
  border-radius:8px 8px 0 0!important;
  border:1px solid var(--portal-border)!important;
  padding:13px 16px!important;
  font-size:15px!important;
  color:#16213B!important;
  box-shadow:none!important;
}}
[data-testid="stDataFrame"]{{
  border:1px solid var(--portal-border)!important;
  border-radius:0 0 8px 8px!important;
  overflow:hidden!important;
  background:#FFF!important;
}}
[data-testid="stDateInput"] input,
[data-testid="stSelectbox"] > div > div,
[data-testid="stMultiSelect"] > div > div{{
  border-color:#D9E2EF!important;
  border-radius:7px!important;
  background:#FFF!important;
}}
[data-testid="stDownloadButton"] button,
.stButton button{{
  border-radius:7px!important;
  font-weight:750!important;
}}
[data-testid="stPlotlyChart"]{{
  border:1px solid var(--portal-border);
  border-radius:8px;
  background:#FFF;
  padding:6px;
}}
@media(max-width:900px){{
  [data-testid="stSidebar"]{{
    min-width:0!important;
  }}
  .executive-top-shell{{
    left:0;
  }}
}}


/* V16.3 — Correcciones visuales y de lectura */
header[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stStatusWidget"],
[data-testid="stDecoration"]{{
    display:none!important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label,
[data-testid="stSidebar"] [role="radiogroup"] label *,
[data-testid="stSidebar"] [role="radiogroup"] label p,
[data-testid="stSidebar"] [role="radiogroup"] label span,
[data-testid="stSidebar"] [role="radiogroup"] label div{{
    color:#FFFFFF!important;
    opacity:1!important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked),
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) *{{
    color:#FFFFFF!important;
}}
.st-key-module_user_menu{{
    display:flex!important;
    justify-content:flex-end!important;
    align-items:center!important;
    min-width:230px!important;
    max-width:290px!important;
}}
.st-key-module_user_menu button{{
    width:auto!important;
    min-width:190px!important;
    max-width:285px!important;
    min-height:42px!important;
    padding:7px 14px!important;
    white-space:nowrap!important;
    overflow:hidden!important;
    text-overflow:ellipsis!important;
    text-align:right!important;
    color:#FFFFFF!important;
    background:rgba(255,255,255,.08)!important;
    border:1px solid rgba(255,255,255,.18)!important;
    border-radius:8px!important;
}}
.st-key-module_user_menu button p,
.st-key-module_user_menu button span{{
    color:#FFFFFF!important;
    white-space:nowrap!important;
    overflow:hidden!important;
    text-overflow:ellipsis!important;
}}
.executive-brand-title{{
    color:#FFFFFF!important;
}}
.portal-top-strip{{
    background:#173B73!important;
    color:#FFFFFF!important;
}}
@media(max-width:900px){{
    .st-key-module_user_menu{{
        min-width:150px!important;
        max-width:190px!important;
    }}
    .st-key-module_user_menu button{{
        min-width:145px!important;
        max-width:185px!important;
        font-size:11px!important;
    }}
}}


/* =========================================================
   V17 ENTERPRISE — PRICE SHOES CORPORATE SYSTEM
   ========================================================= */
:root{{
  --ps-primary:#173B73;
  --ps-secondary:#3366CC;
  --ps-purple:#A26BFF;
  --ps-pink:#FF6FB5;
  --ps-gray:#667085;
  --ps-bg:#F2F4F7;
  --ps-white:#FFFFFF;
  --ps-border:#E1E7EF;
  --ps-sidebar:270px;
  --ps-header:72px;
}}
html,body,[data-testid="stAppViewContainer"]{{
  background:var(--ps-bg)!important;
  font-family:Inter,Arial,sans-serif!important;
}}
header[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stStatusWidget"],
[data-testid="stDecoration"],
#MainMenu,footer{{display:none!important}}
[data-testid="stSidebar"]{{
  position:fixed!important;
  top:0!important;
  left:0!important;
  bottom:0!important;
  width:var(--ps-sidebar)!important;
  min-width:var(--ps-sidebar)!important;
  max-width:var(--ps-sidebar)!important;
  background:linear-gradient(180deg,#0B326C,#173B73)!important;
  z-index:1000!important;
  overflow-y:auto!important;
}}
.ps-sidebar-brand{{
  height:var(--ps-header);
  display:flex;
  align-items:center;
  gap:14px;
  padding:0 22px;
  color:#FFF;
  font-size:16px;
  font-weight:800;
  border-bottom:1px solid rgba(255,255,255,.13);
  position:sticky;
  top:0;
  background:#0B326C;
  z-index:3;
}}
.ps-sidebar-menu{{font-size:23px}}
[data-testid="stSidebar"] [role="radiogroup"]{{
  padding:14px 12px 28px!important;
  gap:4px!important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label{{
  min-height:44px!important;
  border-radius:7px!important;
  padding:0 12px!important;
  color:#FFF!important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label *,
[data-testid="stSidebar"] [role="radiogroup"] label p{{
  color:#FFF!important;
  opacity:1!important;
  font-size:13px!important;
  font-weight:650!important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:hover{{
  background:rgba(255,255,255,.10)!important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){{
  background:var(--ps-secondary)!important;
  box-shadow:inset 4px 0 0 #FFF!important;
}}
.ps-fixed-header{{
  position:fixed;
  top:0;
  left:var(--ps-sidebar);
  right:0;
  height:var(--ps-header);
  z-index:999;
  background:#FFF;
  border-bottom:1px solid var(--ps-border);
  box-shadow:0 3px 12px rgba(23,59,115,.08);
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding:0 28px;
}}
.ps-header-brand{{
  display:flex;
  align-items:center;
  gap:14px;
  color:var(--ps-primary);
  font-weight:800;
  font-size:16px;
}}
.ps-header-brand img{{width:78px;height:48px;object-fit:contain}}
.ps-header-user{{display:flex;align-items:center;gap:12px}}
.ps-header-copy{{text-align:right;color:var(--ps-primary);font-size:12px;font-weight:750;line-height:1.25}}
.ps-header-copy small{{color:var(--ps-gray);font-size:10px;font-weight:600}}
.ps-avatar{{
  width:38px;height:38px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,var(--ps-secondary),var(--ps-purple));
  color:#FFF;font-size:12px;font-weight:900;
  box-shadow:0 4px 12px rgba(51,102,204,.25);
}}
.st-key-fixed_user_menu{{
  position:fixed!important;
  top:15px!important;
  right:23px!important;
  width:210px!important;
  z-index:1002!important;
  opacity:0!important;
}}
.st-key-fixed_user_menu button{{height:42px!important;width:100%!important}}
[data-testid="stMain"]{{
  margin-left:var(--ps-sidebar)!important;
  padding-top:var(--ps-header)!important;
  width:calc(100% - var(--ps-sidebar))!important;
}}
.block-container{{
  max-width:100%!important;
  padding:24px 28px 50px!important;
}}
h1,h2,h3{{color:#1D2939!important;letter-spacing:-.02em}}
h2{{font-size:25px!important}}
[data-testid="stMetric"]{{
  background:#FFF!important;
  border:1px solid var(--ps-border)!important;
  border-radius:10px!important;
  padding:15px 17px!important;
  min-height:112px!important;
  box-shadow:0 4px 13px rgba(23,59,115,.055)!important;
}}
[data-testid="stMetricLabel"] p{{color:#475467!important;font-size:12px!important;font-weight:700!important}}
[data-testid="stMetricValue"]{{color:var(--ps-primary)!important;font-size:26px!important;font-weight:850!important}}
[data-testid="stDataFrame"],[data-testid="stPlotlyChart"]{{
  background:#FFF!important;
  border:1px solid var(--ps-border)!important;
  border-radius:10px!important;
  overflow:hidden!important;
  box-shadow:0 3px 12px rgba(23,59,115,.04)!important;
}}
.panel-title{{
  background:#FFF!important;
  border:1px solid var(--ps-border)!important;
  border-bottom:0!important;
  color:#1D2939!important;
  border-radius:10px 10px 0 0!important;
  padding:14px 17px!important;
}}
.stButton button,[data-testid="stDownloadButton"] button{{
  border-radius:7px!important;
  font-weight:750!important;
}}
.employee-avatar{{
  width:76px;height:76px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  color:#FFF;background:linear-gradient(135deg,#173B73,#3366CC);
  font-size:24px;font-weight:900;margin:8px 0 18px;
}}
@media(max-width:900px){{
  :root{{--ps-sidebar:0px}}
  [data-testid="stSidebar"]{{position:relative!important;width:auto!important;min-width:auto!important}}
  .ps-fixed-header{{left:0}}
  [data-testid="stMain"]{{margin-left:0!important;width:100%!important}}
}}


/* =========================================================
   V20 ENTERPRISE — LAYOUT CORPORATIVO UNIFICADO
   ========================================================= */
:root{{
  --v20-primary:#173B73;
  --v20-secondary:#3366CC;
  --v20-purple:#A26BFF;
  --v20-pink:#FF6FB5;
  --v20-gray:#667085;
  --v20-bg:#F2F4F7;
  --v20-white:#FFFFFF;
  --v20-border:#E1E7EF;
  --v20-sidebar:280px;
  --v20-header:74px;
}}
html, body, [data-testid="stAppViewContainer"]{{
  background:var(--v20-bg)!important;
  font-family:Inter,Arial,sans-serif!important;
}}
header[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stStatusWidget"],
[data-testid="stDecoration"],
#MainMenu, footer{{
  display:none!important;
}}
[data-testid="stSidebar"]{{
  position:fixed!important;
  inset:0 auto 0 0!important;
  width:var(--v20-sidebar)!important;
  min-width:var(--v20-sidebar)!important;
  max-width:var(--v20-sidebar)!important;
  background:linear-gradient(180deg,#0A3067,#173B73)!important;
  z-index:1000!important;
  overflow-y:auto!important;
  padding-top:0!important;
}}
.v20-sidebar-brand{{
  position:sticky;
  top:0;
  z-index:3;
  height:var(--v20-header);
  padding:0 22px;
  display:flex;
  align-items:center;
  gap:14px;
  color:#FFF;
  font-weight:850;
  font-size:16px;
  background:#0A3067;
  border-bottom:1px solid rgba(255,255,255,.15);
}}
.v20-sidebar-menu{{font-size:24px}}
[data-testid="stSidebar"] [role="radiogroup"]{{
  padding:13px 12px 28px!important;
  gap:3px!important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label{{
  min-height:43px!important;
  border-radius:7px!important;
  padding:0 12px!important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label *,
[data-testid="stSidebar"] [role="radiogroup"] label p{{
  color:#FFF!important;
  opacity:1!important;
  font-size:13px!important;
  font-weight:700!important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:hover{{
  background:rgba(255,255,255,.10)!important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){{
  background:var(--v20-secondary)!important;
  box-shadow:inset 4px 0 0 #FFF!important;
}}
.v20-header{{
  position:fixed;
  top:0;
  left:var(--v20-sidebar);
  right:0;
  height:var(--v20-header);
  z-index:999;
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding:0 30px;
  background:#FFF;
  border-bottom:1px solid var(--v20-border);
  box-shadow:0 3px 12px rgba(23,59,115,.08);
}}
.v20-header-brand{{
  display:flex;
  align-items:center;
  gap:14px;
  color:var(--v20-primary);
  font-size:17px;
  font-weight:850;
}}
.v20-header-brand img{{
  width:82px;
  height:52px;
  object-fit:contain;
}}
.v20-header-account{{
  display:flex;
  align-items:center;
  gap:12px;
  min-width:245px;
  justify-content:flex-end;
}}
.v20-header-account-copy{{
  text-align:right;
  line-height:1.2;
  white-space:nowrap;
}}
.v20-header-account-copy strong{{
  display:block;
  color:var(--v20-primary);
  font-size:12px;
}}
.v20-header-account-copy small{{
  display:block;
  color:var(--v20-gray);
  font-size:10px;
  margin-top:4px;
}}
.v20-header-avatar{{
  width:40px;
  height:40px;
  border-radius:50%;
  display:flex;
  align-items:center;
  justify-content:center;
  color:#FFF;
  font-weight:900;
  font-size:12px;
  background:linear-gradient(135deg,var(--v20-secondary),var(--v20-purple));
  box-shadow:0 4px 13px rgba(51,102,204,.28);
}}
.st-key-v20_user_menu{{
  position:fixed!important;
  top:14px!important;
  right:24px!important;
  width:270px!important;
  height:46px!important;
  z-index:1002!important;
  opacity:0!important;
}}
.st-key-v20_user_menu button{{
  width:100%!important;
  height:46px!important;
}}
[data-testid="stMain"]{{
  margin-left:var(--v20-sidebar)!important;
  width:calc(100% - var(--v20-sidebar))!important;
  padding-top:var(--v20-header)!important;
}}
.block-container{{
  max-width:100%!important;
  padding:24px 28px 48px!important;
  margin:0!important;
}}
.v20-portal-content{{
  padding-top:6px;
}}
.ps-portal-top-spacer,
.ps-portal-pinkbar,
.executive-top-shell{{
  display:none!important;
}}
.ps-portal-topbar-brand,
.st-key-portal_user_menu{{
  display:none!important;
}}
.st-key-v20_open_cambios_muertos button{{
  min-height:305px!important;
  border-radius:10px!important;
  border:1px solid var(--v20-border)!important;
  background:#FFF!important;
  color:#1D2939!important;
  font-size:20px!important;
  font-weight:800!important;
  box-shadow:0 5px 18px rgba(23,59,115,.08)!important;
  border-bottom:6px solid var(--v20-pink)!important;
}}
.ps-app-disabled{{
  min-height:305px!important;
}}
h1,h2,h3{{
  color:#1D2939!important;
  letter-spacing:-.02em;
}}
[data-testid="stMetric"]{{
  background:#FFF!important;
  border:1px solid var(--v20-border)!important;
  border-radius:10px!important;
  padding:15px 17px!important;
  box-shadow:0 4px 13px rgba(23,59,115,.055)!important;
}}
[data-testid="stDataFrame"],
[data-testid="stPlotlyChart"]{{
  background:#FFF!important;
  border:1px solid var(--v20-border)!important;
  border-radius:10px!important;
  overflow:hidden!important;
  box-shadow:0 3px 12px rgba(23,59,115,.04)!important;
}}
@media(max-width:900px){{
  :root{{--v20-sidebar:0px}}
  [data-testid="stSidebar"]{{
    position:relative!important;
    width:auto!important;
    min-width:auto!important;
    max-width:none!important;
  }}
  .v20-header{{left:0;padding:0 14px}}
  .v20-header-brand span{{display:none}}
  .v20-header-account{{min-width:auto}}
  [data-testid="stMain"]{{
    margin-left:0!important;
    width:100%!important;
  }}
}}


/* ===== V20.1 RESPONSIVE / PERMISOS ===== */
.st-key-v20_open_cambios_muertos button p{{
  white-space:pre-line!important;
  line-height:1.45!important;
  font-size:18px!important;
}}
.st-key-v20_open_cambios_muertos button p::first-letter{{
  font-size:68px!important;
  line-height:.8!important;
  color:#173B73!important;
  font-weight:500!important;
}}
.st-key-v20_mobile_nav_container{{
  display:none!important;
}}
@media(min-width:901px){{
  [data-testid="stMain"]{{
    min-width:0!important;
  }}
  .block-container{{
    width:100%!important;
    max-width:none!important;
  }}
}}
@media(max-width:900px){{
  :root{{
    --v20-sidebar:0px;
    --v20-header:66px;
  }}
  [data-testid="stSidebar"]{{
    display:none!important;
  }}
  [data-testid="stMain"]{{
    margin-left:0!important;
    width:100%!important;
    padding-top:calc(var(--v20-header) + 70px)!important;
  }}
  .v20-header{{
    left:0!important;
    height:var(--v20-header)!important;
    padding:0 12px!important;
  }}
  .v20-header-brand{{
    gap:8px!important;
    font-size:14px!important;
  }}
  .v20-header-brand img{{
    width:61px!important;
    height:42px!important;
  }}
  .v20-header-account{{
    min-width:0!important;
    gap:7px!important;
  }}
  .v20-header-account-copy strong{{
    font-size:10px!important;
    max-width:115px!important;
    overflow:hidden!important;
    text-overflow:ellipsis!important;
  }}
  .v20-header-account-copy small{{
    font-size:9px!important;
  }}
  .v20-header-avatar{{
    width:34px!important;
    height:34px!important;
    font-size:10px!important;
  }}
  .st-key-v20_user_menu{{
    top:10px!important;
    right:8px!important;
    width:180px!important;
  }}
  .st-key-v20_mobile_nav_container{{
    display:block!important;
    position:fixed!important;
    top:var(--v20-header)!important;
    left:0!important;
    right:0!important;
    z-index:998!important;
    padding:8px 12px 6px!important;
    background:#F2F4F7!important;
    border-bottom:1px solid #E1E7EF!important;
  }}
  .st-key-v20_mobile_nav_container [data-testid="stSelectbox"]{{
    margin:0!important;
  }}
  .block-container{{
    width:100%!important;
    max-width:100%!important;
    padding:14px 12px 32px!important;
  }}
  .v20-portal-content [data-testid="stHorizontalBlock"]{{
    flex-direction:column!important;
  }}
  .v20-portal-content [data-testid="stColumn"]{{
    width:100%!important;
    flex:1 1 100%!important;
  }}
  .ps-profile-card,
  .ps-portal-panel,
  .ps-app-card,
  .st-key-v20_open_cambios_muertos button{{
    width:100%!important;
  }}
  .st-key-v20_open_cambios_muertos button{{
    min-height:240px!important;
  }}
  [data-testid="stMetric"]{{
    min-height:96px!important;
  }}
}}
@media(max-width:520px){{
  .v20-header-brand span{{
    display:none!important;
  }}
  .v20-header-account-copy{{
    display:none!important;
  }}
  .st-key-v20_open_cambios_muertos button p::first-letter{{
    font-size:56px!important;
  }}
}}


/* ===== V20.2: MENÚ DE USUARIO FUNCIONAL ===== */
.v20-header{{
  padding-right:310px!important;
}}
.st-key-v202_user_menu{{
  position:fixed!important;
  top:14px!important;
  right:24px!important;
  width:270px!important;
  height:48px!important;
  z-index:3000!important;
  display:block!important;
  opacity:1!important;
  pointer-events:auto!important;
}}
.st-key-v202_user_menu > div{{
  width:100%!important;
}}
.st-key-v202_user_menu button{{
  width:100%!important;
  min-height:46px!important;
  padding:5px 12px!important;
  border:0!important;
  border-radius:9px!important;
  background:transparent!important;
  color:#173B73!important;
  font-weight:800!important;
  white-space:nowrap!important;
  box-shadow:none!important;
}}
.st-key-v202_user_menu button:hover{{
  background:#F2F4F7!important;
}}
.st-key-v202_user_menu button p,
.st-key-v202_user_menu button span{{
  color:#173B73!important;
  white-space:nowrap!important;
}}
.admin-section-title{{
  background:#173B73;
  color:#FFFFFF;
  font-size:17px;
  font-weight:850;
  border-radius:9px 9px 0 0;
  padding:15px 18px;
  margin-bottom:16px;
}}
@media(max-width:900px){{
  .v20-header{{
    padding-right:78px!important;
  }}
  .st-key-v202_user_menu{{
    top:10px!important;
    right:7px!important;
    width:62px!important;
  }}
  .st-key-v202_user_menu button{{
    font-size:0!important;
    width:52px!important;
    min-width:52px!important;
    border-radius:50%!important;
    background:linear-gradient(135deg,#3366CC,#A26BFF)!important;
  }}
  .st-key-v202_user_menu button::after{{
    content:"👤";
    font-size:20px!important;
    color:#FFFFFF!important;
  }}
}}


/* ===== V20.3: PROCESAMIENTO SIN CAPA TRANSPARENTE ===== */
[data-testid="stAppViewBlockContainer"]{{
  opacity:1!important;
  filter:none!important;
}}
[data-testid="stSpinner"]{{
  position:static!important;
  background:transparent!important;
}}
[data-testid="stStatusWidget"]{{
  display:none!important;
}}
div[data-testid="stAppViewContainer"] > div[style*="opacity"]{{
  opacity:1!important;
}}
.st-key-v202_excel_uploader{{
  opacity:1!important;
  filter:none!important;
}}


/* ===== V20.5: SIDEBAR VISIBLE Y ENCABEZADO FIJO ===== */
@media(min-width:901px){{
  [data-testid="stSidebar"]{{
    overflow-y:auto!important;
    overflow-x:hidden!important;
    scrollbar-width:thin!important;
    scrollbar-color:rgba(255,255,255,.28) transparent!important;
  }}

  [data-testid="stSidebar"] > div:first-child{{
    min-height:100vh!important;
    height:auto!important;
    overflow:visible!important;
  }}

  .v20-sidebar-brand{{
    position:sticky!important;
    top:0!important;
    left:auto!important;
    width:100%!important;
    min-height:var(--v20-header)!important;
    height:var(--v20-header)!important;
    box-sizing:border-box!important;
    z-index:5000!important;
    background:#0A3067!important;
  }}

  [data-testid="stSidebar"] [role="radiogroup"]{{
    position:static!important;
    display:flex!important;
    flex-direction:column!important;
    width:100%!important;
    height:auto!important;
    min-height:0!important;
    margin:0!important;
    padding:14px 12px 30px!important;
    overflow:visible!important;
    transform:none!important;
    clip:auto!important;
    opacity:1!important;
  }}

  [data-testid="stSidebar"] [role="radiogroup"] > label{{
    display:flex!important;
    visibility:visible!important;
    opacity:1!important;
    width:100%!important;
    min-height:43px!important;
    flex:0 0 auto!important;
  }}

  [data-testid="stSidebar"] [role="radiogroup"] > label *,
  [data-testid="stSidebar"] [role="radiogroup"] > label p,
  [data-testid="stSidebar"] [role="radiogroup"] > label span{{
    visibility:visible!important;
    opacity:1!important;
  }}

  [data-testid="stSidebar"]::-webkit-scrollbar{{
    width:7px!important;
  }}

  [data-testid="stSidebar"]::-webkit-scrollbar-thumb{{
    background:rgba(255,255,255,.28)!important;
    border-radius:8px!important;
  }}
}}

</style>
""",
        unsafe_allow_html=True,
    )


def render_portal_header():
    render_header()


def _session_greeting(now):
    if now.hour < 12:
        return "Buenos días"
    if now.hour < 19:
        return "Buena tarde"
    return "Buenas noches"


def _user_initials(full_name):
    parts = [part for part in str(full_name).strip().split() if part]
    if not parts:
        return "PS"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return f"{parts[0][0]}{parts[1][0]}".upper()


def render_header():
    """Encabezado corporativo compacto y estable en cualquier ancho."""
    now = datetime.now(MX_TZ)
    user = st.session_state.get("user", {})
    full_name = str(user.get("nombre", "Consulta")).strip() or "Consulta"
    first_name = full_name.split()[0]
    permiso = str(user.get("permiso", "Consulta"))
    initials = _user_initials(full_name)

    logo_data = ""
    if LOGO_FILE.exists():
        logo_data = base64.b64encode(LOGO_FILE.read_bytes()).decode("utf-8")

    left, right = st.columns([8.4, 1.6], vertical_alignment="center", gap="small")
    with left:
        st.markdown(
            f"""
            <div class="v21-header-brand">
              <img src="data:image/png;base64,{logo_data}" alt="Price Shoes">
              <span>PS Operaciones Ropa</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        # El texto corto evita que el nombre se parta letra por letra.
        with st.popover(f"👤 {first_name} ▾", width="stretch"):
            st.markdown(f"### {full_name}")
            st.caption(f"{permiso} · {now.strftime('%d/%m/%Y')}")
            st.divider()
            if st.button("⌂ Volver al menú principal", key="v21_return_portal", width="stretch"):
                st.session_state["active_app"] = None
                st.session_state["portal_view"] = "apps"
                st.session_state["nav_page"] = "Centro Ejecutivo"
                st.rerun()
            if st.button("👤 Mi perfil", key="v21_profile", width="stretch"):
                st.session_state["nav_page"] = "Perfil de Usuario"
                st.rerun()
            if is_admin() and st.button("⬆ Cargar Excel", key="v21_upload", width="stretch"):
                st.session_state["nav_page"] = "Carga de Excel"
                st.rerun()
            if st.button("Cerrar sesión", key="v21_logout", width="stretch"):
                logout_current_session()
                st.rerun()
    st.divider()


def render_portal_header():
    """El portal utiliza el mismo encabezado fijo del resto del sistema."""
    render_header()


def read_file_history():
    """Lee el historial de archivos sin afectar la operación principal."""
    try:
        if not FILE_HISTORY.exists():
            return []
        data = json.loads(FILE_HISTORY.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def append_file_history(accion, archivo, estado, detalle=""):
    """Agrega un registro al historial; nunca bloquea la carga."""
    try:
        rows = read_file_history()
        rows.append({
            "fecha": datetime.now(MX_TZ).strftime("%Y-%m-%d %H:%M:%S"),
            "accion": str(accion),
            "archivo": str(archivo),
            "estado": str(estado),
            "detalle": str(detalle),
        })
        FILE_HISTORY.parent.mkdir(parents=True, exist_ok=True)
        FILE_HISTORY.write_text(
            json.dumps(rows[-100:], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def save_uploaded_file(uploaded):
    """
    Guarda el archivo una sola vez y conserva el caché cuando el contenido
    seleccionado coincide con el archivo activo.
    """
    uploaded_bytes = bytes(uploaded.getbuffer())
    uploaded_hash = hashlib.sha256(uploaded_bytes).hexdigest()

    previous_meta = {}
    if META_FILE.exists():
        try:
            previous_meta = json.loads(
                META_FILE.read_text(encoding="utf-8")
            )
        except Exception:
            previous_meta = {}

    same_content = (
        ACTIVE_FILE.exists()
        and previous_meta.get("sha256") == uploaded_hash
        and ACTIVE_FILE.stat().st_size == len(uploaded_bytes)
    )

    if not same_content:
        temporary_file = ACTIVE_FILE.with_suffix(".xlsx.tmp")
        temporary_file.write_bytes(uploaded_bytes)
        temporary_file.replace(ACTIVE_FILE)
        clear_cache_files()

    META_FILE.write_text(
        json.dumps(
            {
                "nombre_original": uploaded.name,
                "fecha_carga": datetime.now(MX_TZ).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "mtime": ACTIVE_FILE.stat().st_mtime,
                "sha256": uploaded_hash,
                "mismo_contenido": same_content,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "same_content": same_content,
        "sha256": uploaded_hash,
    }


def clear_cache_files():
    for p in CACHE_DIR.glob("*"):
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink()
        except Exception:
            pass
    try:
        STAGE_STATE_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    st.cache_data.clear()


def delete_active_file():
    clear_process_status()
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


def _file_sha256(path, chunk_size=4 * 1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        while True:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def cache_valid():
    """
    El caché depende del archivo, no de la versión visual de la aplicación.

    Esto evita volver a procesar un Excel de 80 MB cada vez que se publica
    una corrección de diseño.
    """
    paths = cache_paths()
    op_exists = paths["op"].exists() or paths["op"].with_suffix(".pkl").exists()
    co_exists = paths["co"].exists() or paths["co"].with_suffix(".pkl").exists()

    if (
        not ACTIVE_FILE.exists()
        or not paths["meta"].exists()
        or not op_exists
        or not co_exists
    ):
        return False

    try:
        meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
        active_stat = ACTIVE_FILE.stat()

        # Camino rápido para cachés ya existentes.
        if float(meta.get("mtime", 0)) == float(active_stat.st_mtime):
            return True

        # Si el archivo fue guardado de nuevo, validar por contenido.
        saved_hash = str(meta.get("sha256", "")).strip()
        if saved_hash:
            return saved_hash == _file_sha256(ACTIVE_FILE)

        return False
    except Exception:
        return False


def _read_sessions():
    try:
        if not SESSION_FILE.exists():
            return {}
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_sessions(data):
    try:
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _session_token_hash(token):
    """Genera el hash del token de sesión de forma segura."""
    import hashlib as _hashlib
    return _hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def create_persistent_session(user, remember=False):
    """
    Crea una sesión recuperable.

    - Recordarme activado: 30 días.
    - Recordarme desactivado: 8 horas.
    """
    token = secrets.token_urlsafe(32)
    token_hash = _session_token_hash(token)
    now = datetime.now(MX_TZ)
    sessions = _read_sessions()

    clean = {}
    for key, row in sessions.items():
        try:
            if datetime.fromisoformat(row.get("expires_at", "")) > now:
                clean[key] = row
        except Exception:
            continue

    duration = timedelta(days=30) if remember else timedelta(
        hours=SESSION_TIMEOUT_HOURS
    )

    clean[token_hash] = {
        "user": {
            "nomina": str(user.get("nomina", "")),
            "nombre": str(user.get("nombre", "Consulta")),
            "permiso": str(
                user.get(
                    "permiso",
                    ROLE_LABELS.get(
                        normalize_role(user.get("role")),
                        "Consulta",
                    ),
                )
            ),
            "role": normalize_role(
                user.get("role", user.get("permiso"))
            ),
            "scope_type": str(user.get("scope_type", "COMPANY")),
            "scope_value": str(user.get("scope_value", "")),
        },
        "remember": bool(remember),
        "created_at": now.isoformat(),
        "last_activity": now.isoformat(),
        "expires_at": (now + duration).isoformat(),
    }

    _write_sessions(clean)
    st.query_params["session"] = token
    if remember:
        st.query_params["remember_user"] = str(user.get("nomina", ""))
    else:
        try:
            del st.query_params["remember_user"]
        except Exception:
            pass

    st.session_state["auth_token"] = token
    st.session_state["remember_session"] = bool(remember)
    return token


def restore_persistent_session():
    """Recupera la sesión mediante un token firmado por hash en el servidor."""
    if "user" in st.session_state:
        touch_persistent_session()
        return True

    token = st.query_params.get("session", "")
    if isinstance(token, list):
        token = token[0] if token else ""
    if not token:
        return False

    sessions = _read_sessions()
    row = sessions.get(_session_token_hash(token))
    if not row:
        try:
            del st.query_params["session"]
        except Exception:
            pass
        return False

    now = datetime.now(MX_TZ)
    try:
        expires_at = datetime.fromisoformat(row.get("expires_at", ""))
    except Exception:
        expires_at = now - timedelta(seconds=1)

    if expires_at <= now:
        sessions.pop(_session_token_hash(token), None)
        _write_sessions(sessions)
        try:
            del st.query_params["session"]
        except Exception:
            pass
        return False

    user = row.get("user", {})
    user["role"] = normalize_role(user.get("role", user.get("permiso")))
    user["permiso"] = ROLE_LABELS.get(user["role"], user.get("permiso", "Consulta"))
    user["scope_type"] = user.get("scope_type", "COMPANY")
    user["scope_value"] = user.get("scope_value", "")
    st.session_state["user"] = user
    st.session_state["auth_token"] = token
    touch_persistent_session()
    return True


def touch_persistent_session():
    """Renueva la sesión según el modo elegido al iniciar sesión."""
    token = (
        st.session_state.get("auth_token")
        or st.query_params.get("session", "")
    )
    if isinstance(token, list):
        token = token[0] if token else ""
    if not token:
        return

    sessions = _read_sessions()
    token_hash = _session_token_hash(token)
    row = sessions.get(token_hash)
    if not row:
        return

    now = datetime.now(MX_TZ)
    remember = bool(row.get("remember", False))
    duration = timedelta(days=30) if remember else timedelta(
        hours=SESSION_TIMEOUT_HOURS
    )
    row["last_activity"] = now.isoformat()
    row["expires_at"] = (now + duration).isoformat()
    sessions[token_hash] = row
    _write_sessions(sessions)


def clear_auth_session():
    token = st.session_state.get("auth_token") or st.query_params.get("session", "")
    if isinstance(token, list):
        token = token[0] if token else ""
    if token:
        sessions = _read_sessions()
        sessions.pop(_session_token_hash(token), None)
        _write_sessions(sessions)

    for key in [
        "user", "auth_token", "active_app", "portal_view", "nav_page",
    ]:
        st.session_state.pop(key, None)
    try:
        del st.query_params["session"]
    except Exception:
        pass

def normalize_selected_date(x):
    d = parse_date(x)
    return d.date() if pd.notna(d) else date.today()

def normalize_commercial_df(co):
    """Normaliza fecha y tienda comercial antes de usar en reportes."""
    if co is None or co.empty:
        return co
    co = co.copy()

    if "Fecha" in co.columns:
        co["Fecha"] = co["Fecha"].apply(parse_date)
        co = co[co["Fecha"].notna()]
        co["Fecha_txt"] = co["Fecha"].dt.strftime("%Y-%m-%d")

    if "Tienda" in co.columns:
        co["Tienda"] = co["Tienda"].map(canon_store)
        co = co[co["Tienda"].astype(str).str.len() > 0]

    for c in ["Dev_Pzs", "Vta_Pzs", "Vta_Imp", "Costo_Dev"]:
        if c not in co.columns:
            co[c] = 0
        co[c] = pd.to_numeric(co[c], errors="coerce").fillna(0)

    group_cols = [c for c in ["Hoja", "Fecha", "Fecha_txt", "Tienda", "ID", "Descripción", "Color"] if c in co.columns]
    if "Fecha" in group_cols and "Tienda" in group_cols:
        co = co.groupby(group_cols, as_index=False)[["Dev_Pzs", "Vta_Pzs", "Vta_Imp", "Costo_Dev"]].sum()
        iso = co["Fecha"].dt.isocalendar()
        co["Año ISO"] = iso.year.astype(int)
        co["Semana ISO"] = iso.week.astype(int)
        co["Mes"] = co["Fecha"].dt.to_period("M").astype(str)

    return co

def write_cache(op, co, diag):
    """Guarda caché de forma atómica y evita archivos corruptos."""
    paths = cache_paths()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    op = op if op is not None else pd.DataFrame()
    co = co if co is not None else pd.DataFrame()
    diag = diag.copy() if diag is not None else pd.DataFrame()

    for col in diag.columns:
        if diag[col].dtype == "object":
            diag[col] = diag[col].map(
                lambda value: "" if value is None else str(value)
            )

    payloads = {
        "op": op,
        "co": co,
        "diag": diag,
    }

    for key, frame in payloads.items():
        final_path = paths[key]
        temp_path = final_path.with_suffix(final_path.suffix + ".tmp")
        pickle_path = final_path.with_suffix(".pkl")
        temp_pickle = pickle_path.with_suffix(".pkl.tmp")

        try:
            frame.to_parquet(temp_path, index=False)
            os.replace(temp_path, final_path)
            if temp_pickle.exists():
                temp_pickle.unlink(missing_ok=True)
            pickle_path.unlink(missing_ok=True)
        except Exception:
            temp_path.unlink(missing_ok=True)
            frame.to_pickle(temp_pickle)
            os.replace(temp_pickle, pickle_path)
            final_path.unlink(missing_ok=True)

    meta_tmp = paths["meta"].with_suffix(".json.tmp")
    meta_tmp.write_text(
        json.dumps(
            {
                "mtime": ACTIVE_FILE.stat().st_mtime,
                "sha256": (
                    json.loads(META_FILE.read_text(encoding="utf-8")).get(
                        "sha256",
                        "",
                    )
                    if META_FILE.exists()
                    else ""
                ),
                "data_schema": "ps-operaciones-cache-v3",
                "version_visual": APP_CACHE_VERSION,
                "procesado": datetime.now(MX_TZ).strftime("%Y-%m-%d %H:%M:%S"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(meta_tmp, paths["meta"])


@st.cache_data(show_spinner=False)
def read_diag_cache(mtime):
    """Carga solo el diagnóstico, sin abrir operación ni comercial."""
    paths = cache_paths()
    parquet_path = paths["diag"]
    pickle_path = parquet_path.with_suffix(".pkl")
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    if pickle_path.exists():
        return pd.read_pickle(pickle_path)
    return pd.DataFrame()



@st.cache_data(show_spinner=False)
def _cache_date_bounds(cache_key, mtime):
    """Obtiene el horizonte temporal leyendo solamente la columna Fecha."""
    paths = cache_paths()
    parquet_path = paths[cache_key]
    pickle_path = parquet_path.with_suffix(".pkl")
    try:
        if parquet_path.exists():
            dates = pd.read_parquet(parquet_path, columns=["Fecha"])
        elif pickle_path.exists():
            dates = pd.read_pickle(pickle_path)[["Fecha"]]
        else:
            return None, None
        values = pd.to_datetime(dates["Fecha"], errors="coerce").dropna()
        if values.empty:
            return None, None

        # Ignorar fechas futuras o históricas anómalas. Una sola captura con
        # año incorrecto no debe mover la ventana de todos los reportes y
        # dejar los KPI en cero al cambiar de página.
        today = pd.Timestamp.today().normalize()
        min_allowed = pd.Timestamp("2020-01-01")
        max_allowed = today + pd.Timedelta(days=2)
        reliable = values[values.between(min_allowed, max_allowed)]
        if reliable.empty:
            reliable = values
        return reliable.min().normalize(), reliable.max().normalize()
    except Exception:
        return None, None


@st.cache_data(show_spinner=False)
def _read_cache_slice(cache_key, mtime, start_iso="", end_iso=""):
    """Lee únicamente el rango de fechas requerido desde Parquet."""
    paths = cache_paths()
    parquet_path = paths[cache_key]
    pickle_path = parquet_path.with_suffix(".pkl")
    start = pd.Timestamp(start_iso) if start_iso else None
    end = pd.Timestamp(end_iso) if end_iso else None

    if parquet_path.exists():
        filters = []
        if start is not None:
            filters.append(("Fecha", ">=", start.to_pydatetime()))
        if end is not None:
            filters.append(("Fecha", "<=", end.to_pydatetime()))
        try:
            return pd.read_parquet(
                parquet_path,
                filters=filters or None,
            )
        except Exception:
            # Respaldo para archivos Parquet antiguos sin estadísticas útiles.
            frame = pd.read_parquet(parquet_path)
    elif pickle_path.exists():
        frame = pd.read_pickle(pickle_path)
    else:
        return pd.DataFrame()

    if frame is None or frame.empty or "Fecha" not in frame.columns:
        return frame if frame is not None else pd.DataFrame()
    dates = pd.to_datetime(frame["Fecha"], errors="coerce")
    mask = dates.notna()
    if start is not None:
        mask &= dates.ge(start)
    if end is not None:
        mask &= dates.le(end)
    return frame.loc[mask].copy()


def _monday(value):
    value = pd.Timestamp(value).normalize()
    return value - pd.Timedelta(days=int(value.weekday()))


def _month_start(value):
    return pd.Timestamp(value).to_period("M").start_time


@st.cache_data(show_spinner=False, ttl=300)
def load_data_for_page(page, mtime):
    """Carga la ventana requerida usando horizontes independientes.

    La versión anterior tomaba una sola fecha máxima entre operación y
    comercial. Si una fuente terminaba después que la otra, el filtro podía
    dejar vacío uno de los DataFrames aun cuando el caché sí contenía datos.
    """
    op = pd.DataFrame()
    co = pd.DataFrame()
    diag = pd.DataFrame()

    op_min, op_max = _cache_date_bounds("op", mtime)
    co_min, co_max = _cache_date_bounds("co", mtime)

    def _window(latest_value, source, page_name):
        if latest_value is None:
            return None, None
        latest_value = pd.Timestamp(latest_value).normalize()
        if page_name == "Operación Diaria":
            return latest_value, latest_value
        if page_name in {"Centro Ejecutivo", "Reporte Semanal"}:
            start_value = _monday(latest_value) - pd.Timedelta(weeks=3)
            return start_value, _monday(latest_value) + pd.Timedelta(days=6)
        if page_name == "Reporte Mensual":
            return _month_start(latest_value) - pd.DateOffset(months=2), latest_value
        if page_name == "Productividad" and source == "op":
            return latest_value - pd.Timedelta(days=30), latest_value
        if page_name == "Recorridos" and source == "op":
            start_value = _monday(latest_value)
            return start_value, start_value + pd.Timedelta(days=6)
        if page_name == "Recuperación" and source == "co":
            start_value = _monday(latest_value) - pd.Timedelta(weeks=11)
            return start_value, _monday(latest_value) + pd.Timedelta(days=6)
        if page_name in {
            "Detalle por Tienda", "Detalle por Colaborador",
            "Alertas Inteligentes", "Inteligencia Operativa",
        }:
            return latest_value - pd.Timedelta(days=90), latest_value
        return None, None

    op_start, op_end = _window(op_max, "op", page)
    co_start, co_end = _window(co_max, "co", page)

    pages_with_op = {
        "Centro Ejecutivo", "Operación Diaria", "Reporte Semanal",
        "Reporte Mensual", "Productividad", "Recorridos",
        "Detalle por Tienda", "Detalle por Colaborador",
        "Alertas Inteligentes", "Inteligencia Operativa",
    }
    pages_with_co = {
        "Centro Ejecutivo", "Operación Diaria", "Reporte Semanal",
        "Reporte Mensual", "Recuperación", "Alertas Inteligentes",
        "Inteligencia Operativa",
    }

    if page in pages_with_op:
        op = _read_cache_slice(
            "op", mtime,
            op_start.isoformat() if op_start is not None else "",
            op_end.isoformat() if op_end is not None else "",
        )
        # Respaldo: si el rango optimizado no devuelve filas, leer el caché
        # completo para no ocultar información válida por una fecha anómala.
        if (op is None or op.empty) and op_max is not None:
            op = _read_cache_slice("op", mtime)
        op = normalize_operation_df(op)

    if page in pages_with_co:
        co = _read_cache_slice(
            "co", mtime,
            co_start.isoformat() if co_start is not None else "",
            co_end.isoformat() if co_end is not None else "",
        )
        if (co is None or co.empty) and co_max is not None:
            co = _read_cache_slice("co", mtime)
        co = normalize_commercial_df(co)

    return op, co, diag


@st.cache_data(show_spinner=False)
def read_cache(mtime):
    paths = cache_paths()

    def _read_frame(key):
        parquet_path = paths[key]
        pickle_path = parquet_path.with_suffix(".pkl")
        if parquet_path.exists():
            return pd.read_parquet(parquet_path)
        if pickle_path.exists():
            return pd.read_pickle(pickle_path)
        return pd.DataFrame()

    op = _read_frame("op")
    co = _read_frame("co")
    diag = _read_frame("diag")
    op = normalize_operation_df(op)
    co = normalize_commercial_df(co)
    return op, co, diag

# ============================================================
# PROCESAMIENTO LOW MEMORY — UNA HOJA POR EJECUCIÓN
# ============================================================
STAGE_DIR = CACHE_DIR / "staged_processing"
STAGE_STATE_FILE = CONFIG_DIR / "staged_processing.json"


def _stage_path(prefix, index):
    return STAGE_DIR / f"{prefix}_{index:03d}.parquet"


def _write_stage_frame(path, frame):
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = frame if frame is not None else pd.DataFrame()
    temp = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temp, index=False)
    os.replace(temp, path)


def clear_staged_processing():
    shutil.rmtree(STAGE_DIR, ignore_errors=True)
    STAGE_STATE_FILE.unlink(missing_ok=True)


def _sheet_names(file_path):
    for engine in ("calamine", "openpyxl"):
        try:
            with pd.ExcelFile(file_path, engine=engine) as xls:
                return list(xls.sheet_names)
        except Exception:
            continue
    raise RuntimeError("No fue posible obtener la lista de hojas del Excel.")


def _operation_sheet_names(file_path):
    names = _sheet_names(file_path)
    normalized = {norm_text(name): name for name in names}
    result = []
    for wanted in ("RESULTADOS PRODUCTIVIDAD", "RESULTADOS PRODUCTIVIDAD 2"):
        if wanted in normalized:
            result.append(normalized[wanted])
    if len(result) < 2 and "RESULTADOS POR CHECKLIST" in normalized:
        result.append(normalized["RESULTADOS POR CHECKLIST"])
    return result


def _commercial_sheet_names(file_path):
    return [
        sheet for sheet in _sheet_names(file_path)
        if norm_text(sheet) not in {
            "RESULTADOS PRODUCTIVIDAD", "RESULTADOS PRODUCTIVIDAD 2",
            "RESULTADOS POR CHECKLIST", "PLANTILLA",
        }
        and re.search(
            r"(ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPT|OCT|NOV|DIC|ENERO|FEBR|MARZO|26|25)",
            norm_text(sheet),
        )
    ]


def _active_file_identity():
    if not ACTIVE_FILE.exists():
        return {}
    stat = ACTIVE_FILE.stat()
    meta = {}
    if META_FILE.exists():
        try:
            meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"mtime": float(stat.st_mtime), "size": int(stat.st_size), "sha256": str(meta.get("sha256", ""))}


def read_staged_state():
    default = {
        "status": "idle", "step": "initialize",
        "operation_sheets": [], "operation_index": 0,
        "commercial_sheets": [], "commercial_index": 0,
        "completed_steps": 0, "total_steps": 1,
        "message": "Listo para iniciar.", "file_identity": {}, "last_error": "",
    }
    try:
        if STAGE_STATE_FILE.exists():
            data = json.loads(STAGE_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {**default, **data}
    except Exception:
        pass
    return default


def write_staged_state(state):
    STAGE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = dict(state)
    state["updated_at"] = datetime.now(MX_TZ).isoformat()
    tmp = STAGE_STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STAGE_STATE_FILE)
    return state


def initialize_staged_processing(file_path):
    clear_staged_processing()
    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    operation_sheets = _operation_sheet_names(file_path)
    commercial_sheets = _commercial_sheet_names(file_path)
    total = len(operation_sheets) + len(commercial_sheets) + 1
    state = {
        "status": "ready", "step": "operation" if operation_sheets else "commercial",
        "operation_sheets": operation_sheets, "operation_index": 0,
        "commercial_sheets": commercial_sheets, "commercial_index": 0,
        "completed_steps": 0, "total_steps": max(1, total),
        "message": "Preparado. Cada clic procesará únicamente una hoja.",
        "file_identity": _active_file_identity(), "last_error": "",
    }
    write_staged_state(state)
    return state


def staged_progress_percent(state):
    return min(100, round(int(state.get("completed_steps", 0)) / max(1, int(state.get("total_steps", 1))) * 100))


def _append_parquet_files(paths, output_path):
    """Combina Parquet por lotes usando un esquema común y estable.

    Algunas hojas guardan ``Piezas`` como entero y otras como decimal. PyArrow
    exige que todos los lotes escritos en un mismo archivo tengan exactamente
    el mismo esquema. Esta función inspecciona primero los esquemas parciales,
    promueve tipos numéricos incompatibles a ``float64`` y después escribe cada
    lote sin cargar los DataFrames completos en memoria.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    valid_paths = [Path(path) for path in paths if Path(path).exists()]
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    writer = None

    try:
        if not valid_paths:
            pd.DataFrame().to_parquet(tmp, index=False)
            os.replace(tmp, output_path)
            return

        schemas = [pq.ParquetFile(path).schema_arrow.remove_metadata() for path in valid_paths]

        # Mantener el orden de columnas del primer archivo y agregar cualquier
        # columna adicional que aparezca posteriormente.
        column_order = []
        for schema in schemas:
            for name in schema.names:
                if name not in column_order:
                    column_order.append(name)

        def promoted_type(name):
            types = []
            for schema in schemas:
                index = schema.get_field_index(name)
                if index >= 0:
                    types.append(schema.field(index).type)

            if not types:
                return pa.null()
            if all(item.equals(types[0]) for item in types):
                return types[0]
            if any(pa.types.is_floating(item) for item in types) and all(
                pa.types.is_integer(item) or pa.types.is_floating(item)
                for item in types
            ):
                return pa.float64()
            if all(pa.types.is_integer(item) for item in types):
                return pa.int64()
            if all(pa.types.is_string(item) or pa.types.is_large_string(item) for item in types):
                return pa.large_string()
            if all(pa.types.is_timestamp(item) for item in types):
                return pa.timestamp("us")
            # Para mezclas inesperadas se conserva la información como texto.
            return pa.large_string()

        target_schema = pa.schema([
            pa.field(name, promoted_type(name), nullable=True)
            for name in column_order
        ])

        writer = pq.ParquetWriter(
            tmp,
            target_schema,
            compression="snappy",
            use_dictionary=True,
        )

        for path in valid_paths:
            parquet = pq.ParquetFile(path)
            for batch in parquet.iter_batches(batch_size=25000):
                table = pa.Table.from_batches([batch]).remove_column(0) if False else pa.Table.from_batches([batch])

                arrays = []
                for field in target_schema:
                    if field.name in table.column_names:
                        column = table[field.name]
                        try:
                            column = column.cast(field.type, safe=False)
                        except Exception:
                            # Último respaldo para valores incompatibles.
                            column = column.cast(pa.large_string(), safe=False)
                            if not field.type.equals(pa.large_string()):
                                column = column.cast(field.type, safe=False)
                    else:
                        column = pa.nulls(table.num_rows, type=field.type)
                    arrays.append(column)

                normalized = pa.Table.from_arrays(
                    arrays,
                    schema=target_schema,
                )
                writer.write_table(normalized)
                del normalized, arrays, table, batch
                gc.collect()

        writer.close()
        writer = None
        os.replace(tmp, output_path)

    finally:
        if writer is not None:
            writer.close()
        tmp.unlink(missing_ok=True)



def _write_final_cache_meta():
    paths = cache_paths()
    meta = {}
    if META_FILE.exists():
        try: meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception: pass
    temp = paths["meta"].with_suffix(".json.tmp")
    temp.write_text(json.dumps({
        "mtime": ACTIVE_FILE.stat().st_mtime,
        "sha256": meta.get("sha256", ""),
        "data_schema": "ps-operaciones-cache-low-memory-v1",
        "version_visual": APP_CACHE_VERSION,
        "procesado": datetime.now(MX_TZ).strftime("%Y-%m-%d %H:%M:%S"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, paths["meta"])


def process_next_stage(file_path):
    if cache_valid():
        state = read_staged_state()
        state.update({"status":"complete","step":"complete","completed_steps":state.get("total_steps",1),"message":"Información disponible."})
        return write_staged_state(state)

    state = read_staged_state()
    if state.get("status") == "idle" or state.get("file_identity") != _active_file_identity():
        return initialize_staged_processing(file_path)
    if not acquire_process_lock():
        raise RuntimeError("Ya existe una etapa en ejecución.")

    try:
        state["status"] = "running"
        step = state.get("step")

        if step == "operation":
            idx = int(state.get("operation_index", 0))
            sheets = state.get("operation_sheets", [])
            if idx >= len(sheets):
                state["step"] = "commercial" if state.get("commercial_sheets") else "finalize"
            else:
                sheet = sheets[idx]
                state["message"] = f"Procesando hoja operativa: {sheet}"
                write_staged_state(state)
                op, diag = read_operation_sheet(file_path, only_sheets=[sheet])
                plantilla = read_plantilla(file_path)
                op = apply_nombre_map(op, plantilla)
                del plantilla
                op = normalize_operation_df(op)
                _write_stage_frame(_stage_path("operation", idx), op)
                _write_stage_frame(_stage_path("diag_operation", idx), diag)
                del op, diag
                gc.collect()
                state["operation_index"] = idx + 1
                state["completed_steps"] += 1
                if state["operation_index"] >= len(sheets):
                    state["step"] = "commercial" if state.get("commercial_sheets") else "finalize"
                state["message"] = f"Hoja {sheet} terminada."

        elif step == "commercial":
            idx = int(state.get("commercial_index", 0))
            sheets = state.get("commercial_sheets", [])
            if idx >= len(sheets):
                state["step"] = "finalize"
            else:
                sheet = sheets[idx]
                state["message"] = f"Procesando hoja comercial: {sheet}"
                write_staged_state(state)
                co, diag = read_monthly_dev(file_path, progress=None, only_sheets=[sheet])
                co = normalize_commercial_df(co)
                _write_stage_frame(_stage_path("commercial", idx), co)
                _write_stage_frame(_stage_path("diag_commercial", idx), diag)
                del co, diag
                gc.collect()
                state["commercial_index"] = idx + 1
                state["completed_steps"] += 1
                if state["commercial_index"] >= len(sheets): state["step"] = "finalize"
                state["message"] = f"Hoja {sheet} terminada."

        elif step == "finalize":
            state["message"] = "Consolidando archivos sin cargarlos completos en memoria."
            write_staged_state(state)
            paths = cache_paths()
            op_parts = [_stage_path("operation", i) for i in range(len(state.get("operation_sheets", [])))]
            co_parts = [_stage_path("commercial", i) for i in range(len(state.get("commercial_sheets", [])))]
            diag_parts = ([_stage_path("diag_operation", i) for i in range(len(state.get("operation_sheets", [])))] +
                          [_stage_path("diag_commercial", i) for i in range(len(state.get("commercial_sheets", [])))])
            _append_parquet_files(op_parts, paths["op"])
            _append_parquet_files(co_parts, paths["co"])
            _append_parquet_files(diag_parts, paths["diag"])
            _write_final_cache_meta()
            st.cache_data.clear()
            state["completed_steps"] = state["total_steps"]
            state["step"] = "complete"; state["status"] = "complete"
            state["message"] = "Archivo procesado correctamente."

        state["status"] = "complete" if state.get("step") == "complete" else "ready"
        write_process_status(state=state["status"], message=state["message"], progress=staged_progress_percent(state))
        return write_staged_state(state)
    except Exception as exc:
        state["status"] = "error"; state["last_error"] = str(exc)
        state["message"] = "La etapa falló; las anteriores se conservaron."
        write_staged_state(state)
        PROCESS_LOG_FILE.write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        release_process_lock(); gc.collect()


def process_excel(file_path):
    return process_next_stage(file_path)

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


def read_operation_sheet(file_path, only_sheets=None):
    """Lee las hojas operativas con Calamine y usa OpenPyXL como respaldo."""
    engine = "calamine"
    try:
        xls = pd.ExcelFile(file_path, engine=engine)
        sheet_names = list(xls.sheet_names)
    except Exception:
        engine = "openpyxl"
        try:
            xls = pd.ExcelFile(file_path, engine=engine)
            sheet_names = list(xls.sheet_names)
        except Exception as exc:
            return pd.DataFrame(), pd.DataFrame([{
                "Hoja": "Libro",
                "Tipo": "Error",
                "Estado": f"No fue posible abrir el archivo: {exc}",
            }])

    normalized = {norm_text(sheet): sheet for sheet in sheet_names}
    sources = []

    for wanted, source_type in [
        ("RESULTADOS PRODUCTIVIDAD", "Histórica"),
        ("RESULTADOS PRODUCTIVIDAD 2", "Nueva"),
    ]:
        real_name = normalized.get(wanted)
        if real_name:
            sources.append((source_type, real_name))

    if not any(source_type == "Nueva" for source_type, _ in sources):
        alias = normalized.get("RESULTADOS POR CHECKLIST")
        if alias:
            sources.append(("Nueva", alias))

    if only_sheets:
        requested = {norm_text(name) for name in only_sheets}
        sources = [
            (source_type, sheet_name)
            for source_type, sheet_name in sources
            if norm_text(sheet_name) in requested
        ]

    if not sources:
        return pd.DataFrame(), pd.DataFrame([{
            "Hoja": "Resultados productividad",
            "Tipo": "Operación",
            "Estado": "No se encontraron las hojas operativas solicitadas",
        }])

    frames = []
    diagnostics = []

    for source_type, sheet_name in sources:
        try:
            df = pd.read_excel(
                xls,
                sheet_name=sheet_name,
                header=0,
                dtype=object,
            )
        except Exception as exc:
            diagnostics.append({
                "Hoja": sheet_name,
                "Tipo": source_type,
                "Estado": f"Error de lectura: {exc}",
            })
            continue

        df.columns = [str(column).strip() for column in df.columns]

        occurrence_col = find_col(
            df.columns,
            ["Occurrence", "Ocurrence", "Ocurrencia", "Folio"],
        )
        date_col = find_col(
            df.columns,
            ["Fecha", "Fecha s", "Fecha captura"],
        )
        store_col = find_col(
            df.columns,
            ["Tienda", "Ubicación", "Ubicacion", "Sucursal"],
        )
        table_col = find_col(df.columns, ["Tabla"])
        employee_col = find_col(
            df.columns,
            ["Nombre", "Nómina", "Nomina", "Colaborador", "Usuario"],
        )
        activity_col = find_col(
            df.columns,
            ["Actividad Realizada", "Actividad"],
        )
        reason_col = find_col(
            df.columns,
            [
                "Motivo de ingreso",
                "Ingreso al area de acondicionado",
                "Ingreso al área de acondicionado",
                "Motivo",
            ],
        )
        pieces_col = find_col(
            df.columns,
            [
                "Número de piezas",
                "Numero de piezas",
                "Número de Piezas",
                "Numero de Piezas",
                "Piezas",
                "Cantidad",
            ],
        )

        missing = []
        for label, column in [
            ("Fecha", date_col),
            ("Tienda/Ubicación", store_col),
            ("Actividad", activity_col),
            ("Motivo", reason_col),
            ("Número de piezas", pieces_col),
        ]:
            if column is None:
                missing.append(label)

        if missing:
            diagnostics.append({
                "Hoja": sheet_name,
                "Tipo": source_type,
                "Estado": "Faltan columnas: " + ", ".join(missing),
                "Encabezados encontrados": " | ".join(
                    df.columns.astype(str).tolist()
                ),
            })
            continue

        operation = pd.DataFrame({
            "Occurrence": (
                df[occurrence_col].astype(str).str.strip()
                if occurrence_col else ""
            ),
            "Fecha": df[date_col].map(parse_date),
            "Tienda": df[store_col].map(canon_store),
            "Tabla": (
                df[table_col].astype(str).str.strip()
                if table_col else ""
            ),
            "Nombre": (
                df[employee_col].astype(str).str.strip()
                if employee_col else ""
            ),
            "Actividad": df[activity_col].astype(str).str.strip(),
            "Motivo": df[reason_col].astype(str).str.strip(),
            "Piezas": pd.to_numeric(
                df[pieces_col],
                errors="coerce",
            ).fillna(0),
            "Hoja origen": sheet_name,
            "Prioridad fuente": 2 if source_type == "Nueva" else 1,
        })

        operation = operation.dropna(subset=["Fecha"])
        operation = operation[
            operation["Tienda"].astype(str).str.strip().ne("")
        ]
        operation = operation[
            operation["Actividad"].map(norm_text).ne("")
        ]
        operation = operation[
            pd.to_numeric(
                operation["Piezas"],
                errors="coerce",
            ).fillna(0).ge(0)
        ]

        operation["Semana ISO"] = (
            operation["Fecha"].dt.isocalendar().week.astype(int)
        )
        operation["Año ISO"] = (
            operation["Fecha"].dt.isocalendar().year.astype(int)
        )
        operation["Mes"] = (
            operation["Fecha"].dt.to_period("M").astype(str)
        )

        frames.append(operation)
        diagnostics.append({
            "Hoja": sheet_name,
            "Tipo": source_type,
            "Estado": f"OK · motor {engine}",
            "Filas leídas": len(df),
            "Filas válidas": len(operation),
            "Fecha mínima": (
                operation["Fecha"].min().strftime("%Y-%m-%d")
                if not operation.empty else ""
            ),
            "Fecha máxima": (
                operation["Fecha"].max().strftime("%Y-%m-%d")
                if not operation.empty else ""
            ),
            "Actividad": activity_col,
        })

        del df

    if not frames:
        return pd.DataFrame(), pd.DataFrame(diagnostics)

    result = pd.concat(frames, ignore_index=True)

    # Priorizar la segunda hoja cuando exista un registro duplicado.
    duplicate_columns = [
        column for column in
        [
            "Occurrence",
            "Fecha",
            "Tienda",
            "Nombre",
            "Actividad",
            "Motivo",
            "Piezas",
        ]
        if column in result.columns
    ]
    result = result.sort_values("Prioridad fuente")
    result = result.drop_duplicates(
        subset=duplicate_columns,
        keep="last",
    )

    return result, pd.DataFrame(diagnostics)


def read_plantilla(file_path):
    """Lee únicamente la hoja Plantilla con el motor más rápido disponible."""
    for engine in ("calamine", "openpyxl"):
        try:
            return pd.read_excel(
                file_path,
                sheet_name="Plantilla",
                engine=engine,
                dtype=object,
            )
        except Exception:
            continue
    return pd.DataFrame()


def _read_monthly_dev_openpyxl(file_path, progress=None):
    """Lector comercial optimizado por bloques.

    Evita cargar cada hoja completa en memoria. Lee únicamente:
    Tienda, ID, Color y las columnas comerciales detectadas.
    """
    wb = load_workbook(file_path, read_only=True, data_only=True)
    monthly_sheets = [
        s for s in wb.sheetnames
        if norm_text(s) not in [
            "RESULTADOS PRODUCTIVIDAD",
            "RESULTADOS PRODUCTIVIDAD 2",
            "RESULTADOS POR CHECKLIST",
            "PLANTILLA",
        ]
        and re.search(
            r"(ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPT|OCT|NOV|DIC|ENERO|FEBR|MARZO|26|25)",
            norm_text(s),
        )
    ]

    all_records = []
    diag_rows = []
    sample_rows = []
    total_sheets = max(1, len(monthly_sheets))

    for idx_sheet, sheet_name in enumerate(monthly_sheets, start=1):
        if progress:
            progress.progress(
                0.35 + (idx_sheet - 1) / total_sheets * 0.48,
                text=f"Leyendo información comercial: {sheet_name}",
            )

        ws = wb[sheet_name]

        # Solo inspeccionar las primeras 30 filas para ubicar encabezados.
        top_raw = list(
            ws.iter_rows(
                min_row=1,
                max_row=min(30, ws.max_row or 30),
                values_only=True,
            )
        )
        if len(top_raw) < 3:
            diag_rows.append({
                "Tipo": "Centro Ejecutivo",
                "Hoja": sheet_name,
                "Estado": "Hoja sin datos",
                "Registros": 0,
                "Dev Pzs": 0,
            })
            continue

        max_cols = max(len(r) for r in top_raw)
        top_rows = [list(r) + [None] * (max_cols - len(r)) for r in top_raw]

        header_idx = None
        tienda_col = None
        for ridx, row in enumerate(top_rows):
            tienda_cols = [
                i for i, value in enumerate(row)
                if norm_text(value) in ["TIENDA", "TIENDAS"]
            ]
            has_dev = any(
                "DEV" in norm_text(value) and "PZS" in norm_text(value)
                for value in row
            )
            if tienda_cols and has_dev:
                header_idx = ridx
                tienda_col = tienda_cols[0]
                break

        if header_idx is None or tienda_col is None:
            diag_rows.append({
                "Tipo": "Centro Ejecutivo",
                "Hoja": sheet_name,
                "Estado": "No encontró Tienda/Tiendas + Dev Pzs",
                "Registros": 0,
                "Dev Pzs": 0,
            })
            continue

        header_row = top_rows[header_idx]
        date_row = top_rows[header_idx - 1] if header_idx > 0 else [None] * max_cols

        id_aliases = {
            "ID", "SKU", "ID/SKU", "ID ARTICULO", "ID ARTÍCULO",
            "ID MODELO", "MODELO ID", "MODELO", "CODIGO", "CÓDIGO",
        }
        description_aliases = {
            "DESCRIPCION", "DESCRIPCIÓN", "DESC", "DESCRIPCION ARTICULO",
            "DESCRIPCIÓN ARTÍCULO", "ARTICULO", "ARTÍCULO",
        }
        color_aliases = {"COLOR", "COLOUR"}

        id_col = next(
            (i for i, value in enumerate(header_row) if norm_text(value) in id_aliases),
            None,
        )
        description_col = next(
            (i for i, value in enumerate(header_row) if norm_text(value) in description_aliases),
            None,
        )
        color_col = next(
            (i for i, value in enumerate(header_row) if norm_text(value) in color_aliases),
            None,
        )

        date_by_col = {}
        current_date = pd.NaT
        for col_idx in range(max_cols):
            parsed_date = parse_date(date_row[col_idx])
            if pd.notna(parsed_date):
                current_date = parsed_date
            date_by_col[col_idx] = current_date

        blocks = {}
        for col_idx, header in enumerate(header_row):
            header_norm = norm_text(header)
            fecha = date_by_col.get(col_idx, pd.NaT)
            if pd.isna(fecha):
                continue

            fecha = pd.to_datetime(fecha).normalize()
            if "DEV" in header_norm and "PZS" in header_norm:
                blocks.setdefault(fecha, {})["dev_col"] = col_idx
            elif (
                ("VENTA" in header_norm or "VENTAS" in header_norm)
                and ("PZS" in header_norm or "NETA" in header_norm)
                and "$" not in str(header)
            ):
                blocks.setdefault(fecha, {})["vta_pzs_col"] = col_idx
            elif (
                ("VENTA" in header_norm or "NETA" in header_norm)
                and (
                    "$" in str(header)
                    or "IMP" in header_norm
                    or " EN " in f" {header_norm} "
                )
            ):
                blocks.setdefault(fecha, {})["vta_imp_col"] = col_idx

        blocks = {fecha: cols for fecha, cols in blocks.items() if cols}
        if not blocks:
            diag_rows.append({
                "Tipo": "Centro Ejecutivo",
                "Hoja": sheet_name,
                "Estado": "No encontró bloques comerciales",
                "Fila encabezado": header_idx + 1,
                "Registros": 0,
                "Dev Pzs": 0,
            })
            continue

        for fecha, cols in sorted(blocks.items(), key=lambda item: item[0]):
            diag_rows.append({
                "Tipo": "Columnas detectadas",
                "Hoja": sheet_name,
                "Fecha": fecha.strftime("%Y-%m-%d"),
                "Fila encabezado": header_idx + 1,
                "Col Tienda": excel_col_name(tienda_col),
                "Col ID": excel_col_name(id_col) if id_col is not None else "",
                "Col Ventas Pzs": (
                    excel_col_name(cols["vta_pzs_col"])
                    if "vta_pzs_col" in cols else ""
                ),
                "Col Dev Pzs": (
                    excel_col_name(cols["dev_col"])
                    if "dev_col" in cols else ""
                ),
                "Col Venta $": (
                    excel_col_name(cols["vta_imp_col"])
                    if "vta_imp_col" in cols else ""
                ),
            })

        # Solo conservar columnas realmente necesarias.
        required_cols = {tienda_col}
        if id_col is not None:
            required_cols.add(id_col)
        if description_col is not None:
            required_cols.add(description_col)
        if color_col is not None:
            required_cols.add(color_col)
        for cols in blocks.values():
            required_cols.update(cols.values())

        min_col = min(required_cols) + 1
        max_col = max(required_cols) + 1

        # Ajustar índices al rango reducido de lectura.
        def local_index(original_index):
            return original_index - (min_col - 1)

        local_tienda = local_index(tienda_col)
        local_id = local_index(id_col) if id_col is not None else None
        local_description = (
            local_index(description_col) if description_col is not None else None
        )
        local_color = local_index(color_col) if color_col is not None else None
        local_blocks = {
            fecha: {
                key: local_index(col_idx)
                for key, col_idx in cols.items()
            }
            for fecha, cols in blocks.items()
        }

        acc = {}
        sheet_dev = 0.0
        sheet_vta_pzs = 0.0
        sheet_vta_imp = 0.0
        lecturas = 0
        tiendas = set()
        samples_per_sheet = 0

        row_iterator = ws.iter_rows(
            min_row=header_idx + 2,
            max_row=ws.max_row,
            min_col=min_col,
            max_col=max_col,
            values_only=True,
        )

        for excel_row_num, row in enumerate(row_iterator, start=header_idx + 2):
            raw_tienda = row[local_tienda] if local_tienda < len(row) else None
            tienda = canon_store(raw_tienda)
            if not tienda:
                continue
            tiendas.add(tienda)

            raw_id = (
                row[local_id]
                if local_id is not None and local_id < len(row)
                else ""
            )
            item_id = str(raw_id).strip()
            if item_id.lower() in {"none", "nan"}:
                item_id = ""

            raw_description = (
                row[local_description]
                if local_description is not None and local_description < len(row)
                else ""
            )
            description = str(raw_description).strip()
            if description.lower() in {"none", "nan"}:
                description = ""

            raw_color = (
                row[local_color]
                if local_color is not None and local_color < len(row)
                else ""
            )
            color = str(raw_color).strip()
            if color.lower() in {"none", "nan"}:
                color = ""

            for fecha, cols in local_blocks.items():
                dev_raw = (
                    row[cols["dev_col"]]
                    if "dev_col" in cols and cols["dev_col"] < len(row)
                    else None
                )
                vta_raw = (
                    row[cols["vta_pzs_col"]]
                    if "vta_pzs_col" in cols and cols["vta_pzs_col"] < len(row)
                    else None
                )
                imp_raw = (
                    row[cols["vta_imp_col"]]
                    if "vta_imp_col" in cols and cols["vta_imp_col"] < len(row)
                    else None
                )

                dev = safe_num(dev_raw)
                vta_pzs = safe_num(vta_raw)
                vta_imp = safe_num(imp_raw)

                if dev == 0 and vta_pzs == 0 and vta_imp == 0:
                    continue

                key = (sheet_name, fecha, tienda, item_id, description, color)
                values = acc.setdefault(
                    key,
                    {"Dev_Pzs": 0.0, "Vta_Pzs": 0.0, "Vta_Imp": 0.0},
                )
                values["Dev_Pzs"] += dev
                values["Vta_Pzs"] += vta_pzs
                values["Vta_Imp"] += vta_imp

                sheet_dev += dev
                sheet_vta_pzs += vta_pzs
                sheet_vta_imp += vta_imp
                lecturas += 1

                raw_norm = norm_text(raw_tienda)
                if (
                    samples_per_sheet < 80
                    and (
                        dev != 0
                        or "MIRAVALLE" in raw_norm
                        or "GUADALAJARA" in raw_norm
                        or "ATEMAJAC" in raw_norm
                    )
                ):
                    sample_rows.append({
                        "Hoja": sheet_name,
                        "Fila Excel": excel_row_num,
                        "Fecha": fecha.strftime("%Y-%m-%d"),
                        "Tienda cruda": str(raw_tienda),
                        "Tienda homologada": tienda,
                        "ID": item_id,
                        "Dev crudo": str(dev_raw),
                        "Dev num": dev,
                        "Ventas crudo": str(vta_raw),
                        "Ventas num": vta_pzs,
                        "Venta $ crudo": str(imp_raw),
                        "Venta $ num": vta_imp,
                    })
                    samples_per_sheet += 1

        for (hoja, fecha, tienda, item_id, description, color), values in acc.items():
            all_records.append({
                "Hoja": hoja,
                "Fecha": fecha,
                "Fecha_txt": fecha.strftime("%Y-%m-%d"),
                "Tienda": tienda,
                "Dev_Pzs": values["Dev_Pzs"],
                "Vta_Pzs": values["Vta_Pzs"],
                "Vta_Imp": values["Vta_Imp"],
                "Costo_Dev": 0.0,
                "ID": item_id,
                "Descripción": description,
                "Color": color,
            })

        diag_rows.append({
            "Tipo": "Centro Ejecutivo",
            "Hoja": sheet_name,
            "Estado": "OK",
            "Fila encabezado": header_idx + 1,
            "Fila fechas": header_idx,
            "Col Tienda": excel_col_name(tienda_col),
            "Col ID": excel_col_name(id_col) if id_col is not None else "",
            "Fechas detectadas": len(blocks),
            "Registros agrupados": len(acc),
            "Lecturas con valor": lecturas,
            "Tiendas detectadas": len(tiendas),
            "Dev Pzs": sheet_dev,
            "Venta Pzs": sheet_vta_pzs,
            "Venta $": sheet_vta_imp,
        })

        # Liberar la hoja de lectura antes de continuar.
        del acc

    wb.close()

    co = pd.DataFrame(all_records)
    if not co.empty:
        co["Fecha"] = pd.to_datetime(co["Fecha"], errors="coerce")
        co = co[co["Fecha"].notna()]
        co["Fecha_txt"] = co["Fecha"].dt.strftime("%Y-%m-%d")
        co["Tienda"] = co["Tienda"].map(canon_store)
        co = (
            co.groupby(
                ["Hoja", "Fecha", "Fecha_txt", "Tienda", "ID", "Descripción", "Color"],
                as_index=False,
                dropna=False,
            )[["Dev_Pzs", "Vta_Pzs", "Vta_Imp", "Costo_Dev"]]
            .sum()
        )
        iso = co["Fecha"].dt.isocalendar()
        co["Año ISO"] = iso.year.astype(int)
        co["Semana ISO"] = iso.week.astype(int)
        co["Mes"] = co["Fecha"].dt.to_period("M").astype(str)

    diag = pd.DataFrame(diag_rows)
    samples = pd.DataFrame(sample_rows)
    if not samples.empty:
        samples.insert(0, "Tipo", "Muestra lectura")
        diag = pd.concat([diag, samples], ignore_index=True, sort=False)

    return co, diag


def _excel_fast_engine_available():
    try:
        import python_calamine  # noqa: F401
        return True
    except Exception:
        return False


def read_monthly_dev(file_path, progress=None, only_sheets=None):
    """
    Lector comercial acelerado.

    Usa Calamine (motor Rust) para leer únicamente las columnas requeridas.
    Si el entorno no dispone del motor o una hoja tiene una estructura no
    compatible, utiliza automáticamente el lector OpenPyXL anterior.
    """
    if not _excel_fast_engine_available():
        return _read_monthly_dev_openpyxl(file_path, progress=progress)

    try:
        xls = pd.ExcelFile(file_path, engine="calamine")
        monthly_sheets = [
            sheet for sheet in xls.sheet_names
            if norm_text(sheet) not in {
                "RESULTADOS PRODUCTIVIDAD",
                "RESULTADOS PRODUCTIVIDAD 2",
                "RESULTADOS POR CHECKLIST",
                "PLANTILLA",
            }
            and re.search(
                r"(ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPT|OCT|NOV|DIC|ENERO|FEBR|MARZO|26|25)",
                norm_text(sheet),
            )
        ]

        if only_sheets:
            requested = {norm_text(sheet) for sheet in only_sheets}
            monthly_sheets = [
                sheet for sheet in monthly_sheets
                if norm_text(sheet) in requested
            ]

        all_frames = []
        diag_rows = []
        total_sheets = max(1, len(monthly_sheets))

        for sheet_number, sheet_name in enumerate(monthly_sheets, start=1):
            if progress:
                progress.progress(
                    0.36 + (sheet_number - 1) / total_sheets * 0.46,
                    text=f"Lectura rápida comercial: {sheet_name}",
                )

            top = pd.read_excel(
                xls,
                sheet_name=sheet_name,
                header=None,
                nrows=30,
                dtype=object,
            )
            top = top.where(pd.notna(top), None)
            top_rows = top.values.tolist()

            header_idx = None
            tienda_col = None
            for row_index, row in enumerate(top_rows):
                tienda_cols = [
                    index for index, value in enumerate(row)
                    if norm_text(value) in {"TIENDA", "TIENDAS"}
                ]
                has_dev = any(
                    "DEV" in norm_text(value) and "PZS" in norm_text(value)
                    for value in row
                )
                if tienda_cols and has_dev:
                    header_idx = row_index
                    tienda_col = tienda_cols[0]
                    break

            if header_idx is None or tienda_col is None:
                diag_rows.append({
                    "Tipo": "Centro Ejecutivo",
                    "Hoja": sheet_name,
                    "Estado": "No encontró Tienda/Tiendas + Dev Pzs",
                    "Registros": 0,
                })
                continue

            header_row = top_rows[header_idx]
            date_row = (
                top_rows[header_idx - 1]
                if header_idx > 0
                else [None] * len(header_row)
            )

            id_aliases = {
                "ID", "SKU", "ID/SKU", "ID ARTICULO", "ID ARTÍCULO",
                "ID MODELO", "MODELO ID", "MODELO", "CODIGO", "CÓDIGO",
            }
            description_aliases = {
                "DESCRIPCION", "DESCRIPCIÓN", "DESC",
                "DESCRIPCION ARTICULO", "DESCRIPCIÓN ARTÍCULO",
                "ARTICULO", "ARTÍCULO",
            }
            color_aliases = {"COLOR", "COLOUR"}

            id_col = next(
                (i for i, value in enumerate(header_row)
                 if norm_text(value) in id_aliases),
                None,
            )
            description_col = next(
                (i for i, value in enumerate(header_row)
                 if norm_text(value) in description_aliases),
                None,
            )
            color_col = next(
                (i for i, value in enumerate(header_row)
                 if norm_text(value) in color_aliases),
                None,
            )

            date_by_col = {}
            current_date = pd.NaT
            for col_idx in range(len(header_row)):
                parsed = parse_date(
                    date_row[col_idx] if col_idx < len(date_row) else None
                )
                if pd.notna(parsed):
                    current_date = parsed
                date_by_col[col_idx] = current_date

            blocks = {}
            for col_idx, header in enumerate(header_row):
                header_norm = norm_text(header)
                fecha = date_by_col.get(col_idx, pd.NaT)
                if pd.isna(fecha):
                    continue
                fecha = pd.to_datetime(fecha).normalize()

                if "DEV" in header_norm and "PZS" in header_norm:
                    blocks.setdefault(fecha, {})["dev_col"] = col_idx
                elif (
                    ("VENTA" in header_norm or "VENTAS" in header_norm)
                    and ("PZS" in header_norm or "NETA" in header_norm)
                    and "$" not in str(header)
                ):
                    blocks.setdefault(fecha, {})["vta_pzs_col"] = col_idx
                elif (
                    ("VENTA" in header_norm or "NETA" in header_norm)
                    and (
                        "$" in str(header)
                        or "IMP" in header_norm
                        or " EN " in f" {header_norm} "
                    )
                ):
                    blocks.setdefault(fecha, {})["vta_imp_col"] = col_idx

            blocks = {date_key: cols for date_key, cols in blocks.items() if cols}
            if not blocks:
                diag_rows.append({
                    "Tipo": "Centro Ejecutivo",
                    "Hoja": sheet_name,
                    "Estado": "No encontró bloques comerciales",
                    "Registros": 0,
                })
                continue

            required_cols = {tienda_col}
            for optional_col in (id_col, description_col, color_col):
                if optional_col is not None:
                    required_cols.add(optional_col)
            for block_cols in blocks.values():
                required_cols.update(block_cols.values())

            selected_cols = sorted(required_cols)
            original_to_local = {
                original: local
                for local, original in enumerate(selected_cols)
            }

            data = pd.read_excel(
                xls,
                sheet_name=sheet_name,
                header=header_idx,
                usecols=selected_cols,
                dtype=object,
            )

            stores = data.iloc[:, original_to_local[tienda_col]].map(canon_store)
            valid_store = stores.astype(str).str.strip().ne("")

            def clean_text_column(original_col):
                if original_col is None:
                    return pd.Series("", index=data.index, dtype="object")
                values = data.iloc[:, original_to_local[original_col]]
                values = values.fillna("").astype(str).str.strip()
                return values.mask(values.str.lower().isin(["none", "nan"]), "")

            item_ids = clean_text_column(id_col)
            descriptions = clean_text_column(description_col)
            colors_series = clean_text_column(color_col)

            sheet_frames = []
            for fecha, block_cols in blocks.items():
                def numeric_value(key):
                    original = block_cols.get(key)
                    if original is None:
                        return pd.Series(0.0, index=data.index)
                    return pd.to_numeric(
                        data.iloc[:, original_to_local[original]],
                        errors="coerce",
                    ).fillna(0.0)

                dev = numeric_value("dev_col")
                vta_pzs = numeric_value("vta_pzs_col")
                vta_imp = numeric_value("vta_imp_col")
                mask = valid_store & ((dev != 0) | (vta_pzs != 0) | (vta_imp != 0))

                if not mask.any():
                    continue

                sheet_frames.append(pd.DataFrame({
                    "Hoja": sheet_name,
                    "Fecha": fecha,
                    "Fecha_txt": fecha.strftime("%Y-%m-%d"),
                    "Tienda": stores[mask].values,
                    "Dev_Pzs": dev[mask].values,
                    "Vta_Pzs": vta_pzs[mask].values,
                    "Vta_Imp": vta_imp[mask].values,
                    "Costo_Dev": 0.0,
                    "ID": item_ids[mask].values,
                    "Descripción": descriptions[mask].values,
                    "Color": colors_series[mask].values,
                }))

            if sheet_frames:
                sheet_result = pd.concat(sheet_frames, ignore_index=True)
                all_frames.append(sheet_result)
                diag_rows.append({
                    "Tipo": "Centro Ejecutivo",
                    "Hoja": sheet_name,
                    "Estado": "OK · Lectura rápida",
                    "Fechas detectadas": len(blocks),
                    "Registros": len(sheet_result),
                    "Dev Pzs": float(sheet_result["Dev_Pzs"].sum()),
                    "Venta Pzs": float(sheet_result["Vta_Pzs"].sum()),
                    "Venta $": float(sheet_result["Vta_Imp"].sum()),
                })
            else:
                diag_rows.append({
                    "Tipo": "Centro Ejecutivo",
                    "Hoja": sheet_name,
                    "Estado": "Sin valores comerciales",
                    "Registros": 0,
                })

        if not all_frames:
            return pd.DataFrame(), pd.DataFrame(diag_rows)

        co = pd.concat(all_frames, ignore_index=True)
        co["Fecha"] = pd.to_datetime(co["Fecha"], errors="coerce")
        co = co[co["Fecha"].notna()]
        co["Tienda"] = co["Tienda"].map(canon_store)

        co = co.groupby(
            ["Hoja", "Fecha", "Fecha_txt", "Tienda", "ID", "Descripción", "Color"],
            as_index=False,
            dropna=False,
        )[["Dev_Pzs", "Vta_Pzs", "Vta_Imp", "Costo_Dev"]].sum()

        iso = co["Fecha"].dt.isocalendar()
        co["Año ISO"] = iso.year.astype(int)
        co["Semana ISO"] = iso.week.astype(int)
        co["Mes"] = co["Fecha"].dt.to_period("M").astype(str)

        return co, pd.DataFrame(diag_rows)

    except Exception:
        # El respaldo mantiene compatibilidad con cualquier estructura especial.
        return _read_monthly_dev_openpyxl(file_path, progress=progress)


def split_operation(op):
    if op is None or op.empty:
        return op
    df = op.copy()
    act = df["Actividad"].map(norm_text)
    mot = df["Motivo"].map(norm_text)

    es_recoleccion_muertos = act.str.contains(
        r"RECOLECCION DE MUERTOS|RECOLECCIÓN DE MUERTOS",
        regex=True,
        na=False,
    )
    es_motivo_muertos = mot.str.contains("MUERTO", na=False)

    # Muertos: únicamente Recolección de muertos + motivo Muertos.
    df["Muertos"] = np.where(
        es_recoleccion_muertos & es_motivo_muertos,
        df["Piezas"],
        0,
    )

    # Cajas y Probador son ingresos, no cualquier actividad posterior.
    es_ingreso_o_recoleccion = act.str.contains(
        r"^INGRESO$|RECOLECCION|RECOLECCIÓN",
        regex=True,
        na=False,
    )
    df["Cajas"] = np.where(
        es_ingreso_o_recoleccion & mot.str.contains("CAJA", na=False),
        df["Piezas"],
        0,
    )
    df["Probador"] = np.where(
        es_ingreso_o_recoleccion
        & (
            mot.str.contains("PROBADOR", na=False)
            | act.str.contains("PROBADOR", na=False)
        ),
        df["Piezas"],
        0,
    )

    # Recolectadas considera Recolección e Ingreso de la nueva fuente.
    df["Recolectadas"] = np.where(
        act.str.contains(r"RECOLECCION|RECOLECCIÓN|^INGRESO$", regex=True, na=False),
        df["Piezas"],
        0,
    )
    df["Habilitadas"] = np.where(
        act.str.contains(r"ACONDICION|HABILIT", regex=True, na=False),
        df["Piezas"],
        0,
    )
    df["Ubicadas"] = np.where(
        act.str.contains(r"UBIC", regex=True, na=False),
        df["Piezas"],
        0,
    )
    return df


def filter_stores(df, stores=None):
    if df.empty or not stores:
        return df
    return df[df["Tienda"].isin(stores)]



def normalize_operation_df(op):
    """Normaliza fechas/tiendas operativas antes de reportar."""
    if op is None or op.empty:
        return op
    op = op.copy()

    # Recalcular fecha desde columnas originales si están disponibles.
    for cand in ["Fecha s", "Fecha_s", "Fecha original", "Fecha Original"]:
        if cand in op.columns:
            parsed = op[cand].apply(parse_date)
            if parsed.notna().sum() >= max(1, len(op) * 0.4):
                op["Fecha"] = parsed
                break

    if "Fecha" in op.columns:
        op["Fecha"] = op["Fecha"].apply(parse_date)
        op = op[op["Fecha"].notna()]
        op["Semana ISO"] = op["Fecha"].dt.isocalendar().week.astype(int)
        op["Mes"] = op["Fecha"].dt.to_period("M").astype(str)

    if "Tienda" in op.columns:
        op["Tienda"] = op["Tienda"].map(canon_store)

    return op


def filter_commercial_by_date(co, start, end, stores_list):
    if co is None or co.empty:
        return pd.DataFrame()
    co = normalize_commercial_df(co)
    co = filter_stores(co, stores_list)
    if co.empty:
        return co

    start_txt = pd.to_datetime(start).strftime("%Y-%m-%d")
    end_txt = pd.to_datetime(end).strftime("%Y-%m-%d")

    if "Fecha_txt" not in co.columns:
        co["Fecha_txt"] = pd.to_datetime(co["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")

    out = co[(co["Fecha_txt"] >= start_txt) & (co["Fecha_txt"] <= end_txt)].copy()

    # Rescate: si no encontró Dev y es un solo día, intenta fecha con día/mes invertido.
    if out.empty and start_txt == end_txt:
        try:
            d = pd.to_datetime(start)
            alt = pd.Timestamp(year=d.year, month=d.day, day=d.month)
            alt_txt = alt.strftime("%Y-%m-%d")
            out = co[co["Fecha_txt"].eq(alt_txt)].copy()
        except Exception:
            pass

    return out

def closing_pending_by_store(op, co, cutoff_date, stores=None):
    """Calcula el saldo pendiente real por tienda hasta una fecha de cierre.

    Saldo diario:
        saldo final = máximo(saldo anterior + ingresos del día - ubicadas del día, 0)

    Esto evita que las ubicaciones excedentes de una tienda compensen el
    pendiente de otra y permite trasladar correctamente el cierre del domingo
    a la semana siguiente.
    """
    op = normalize_operation_df(op)
    co = normalize_commercial_df(co)
    stores_list = stores or PROJECT_STORES
    cutoff = parse_date(cutoff_date)

    result = {store: 0.0 for store in stores_list}
    if pd.isna(cutoff):
        return result

    op2 = split_operation(op)
    min_dates = []

    if op2 is not None and not op2.empty and "Fecha" in op2.columns:
        valid_op_dates = pd.to_datetime(op2["Fecha"], errors="coerce").dropna()
        if not valid_op_dates.empty:
            min_dates.append(valid_op_dates.min().normalize())

    if co is not None and not co.empty and "Fecha" in co.columns:
        valid_co_dates = pd.to_datetime(co["Fecha"], errors="coerce").dropna()
        if not valid_co_dates.empty:
            min_dates.append(valid_co_dates.min().normalize())

    if not min_dates:
        return result

    first_date = min(min_dates)
    if cutoff < first_date:
        return result

    op_cut = (
        op2[
            (pd.to_datetime(op2["Fecha"], errors="coerce") >= first_date)
            & (pd.to_datetime(op2["Fecha"], errors="coerce") <= cutoff)
        ].copy()
        if op2 is not None and not op2.empty
        else pd.DataFrame()
    )
    op_cut = filter_stores(op_cut, stores_list)

    co_cut = filter_commercial_by_date(co, first_date, cutoff, stores_list)

    daily_parts = []

    if not op_cut.empty:
        op_cut["Fecha"] = pd.to_datetime(op_cut["Fecha"], errors="coerce").dt.normalize()
        op_daily = (
            op_cut.groupby(["Fecha", "Tienda"], as_index=False)
            .agg({
                "Muertos": "sum",
                "Cajas": "sum",
                "Probador": "sum",
                "Ubicadas": "sum",
            })
        )
        op_daily["Ingresos operación"] = (
            pd.to_numeric(op_daily["Muertos"], errors="coerce").fillna(0)
            + pd.to_numeric(op_daily["Cajas"], errors="coerce").fillna(0)
            + pd.to_numeric(op_daily["Probador"], errors="coerce").fillna(0)
        )
        daily_parts.append(
            op_daily[["Fecha", "Tienda", "Ingresos operación", "Ubicadas"]]
        )

    if not co_cut.empty:
        co_cut["Fecha"] = pd.to_datetime(co_cut["Fecha"], errors="coerce").dt.normalize()
        co_daily = (
            co_cut.groupby(["Fecha", "Tienda"], as_index=False)["Dev_Pzs"]
            .sum()
            .rename(columns={"Dev_Pzs": "Dev diario"})
        )
    else:
        co_daily = pd.DataFrame(columns=["Fecha", "Tienda", "Dev diario"])

    if daily_parts:
        daily = daily_parts[0]
    else:
        daily = pd.DataFrame(
            columns=["Fecha", "Tienda", "Ingresos operación", "Ubicadas"]
        )

    daily = daily.merge(co_daily, on=["Fecha", "Tienda"], how="outer")
    for col in ["Ingresos operación", "Ubicadas", "Dev diario"]:
        daily[col] = pd.to_numeric(daily.get(col, 0), errors="coerce").fillna(0)

    daily["Ingresos"] = daily["Ingresos operación"] + daily["Dev diario"]
    daily = daily.sort_values(["Tienda", "Fecha"])

    for store in stores_list:
        saldo = 0.0
        store_daily = daily[daily["Tienda"].eq(store)]
        for row in store_daily.itertuples(index=False):
            saldo = max(
                saldo + float(row.Ingresos) - float(row.Ubicadas),
                0.0,
            )
        result[store] = saldo

    return result

def table_by_store(
    op,
    co,
    start_date,
    end_date,
    stores=None,
    carryover_mode="previous_day",
):
    """Construye la tabla por tienda para un periodo.

    carryover_mode:
    - "previous_day": traslada el saldo acumulado al cierre del día anterior.
    - "previous_sunday": traslada el saldo acumulado al domingo anterior.
    - "none": no agrega saldo anterior; se usan solo ingresos del periodo.
    """
    op = normalize_operation_df(op)
    co = normalize_commercial_df(co)

    op2 = split_operation(op)
    start = parse_date(start_date)
    end = parse_date(end_date)
    stores_list = stores or PROJECT_STORES

    op_p = (
        op2[(op2["Fecha"] >= start) & (op2["Fecha"] <= end)]
        if op2 is not None and not op2.empty
        else pd.DataFrame()
    )
    op_p = filter_stores(op_p, stores_list)
    co_p = filter_commercial_by_date(co, start, end, stores_list)

    if carryover_mode == "none":
        prior_balances = {store: 0.0 for store in stores_list}
    else:
        # Para una semana ISO el día anterior al lunes es exactamente el domingo previo.
        cutoff = start - pd.Timedelta(days=1)
        prior_balances = closing_pending_by_store(
            op,
            co,
            cutoff,
            stores_list,
        )

    rows = []
    for t in stores_list:
        dev = (
            pd.to_numeric(
                co_p.loc[co_p["Tienda"].eq(t), "Dev_Pzs"],
                errors="coerce",
            ).fillna(0).sum()
            if not co_p.empty and "Dev_Pzs" in co_p.columns
            else 0
        )

        o = op_p[op_p["Tienda"].eq(t)] if not op_p.empty else pd.DataFrame()

        muertos = o["Muertos"].sum() if not o.empty and "Muertos" in o.columns else 0
        cajas = o["Cajas"].sum() if not o.empty and "Cajas" in o.columns else 0
        prob = o["Probador"].sum() if not o.empty and "Probador" in o.columns else 0
        reco = o["Recolectadas"].sum() if not o.empty and "Recolectadas" in o.columns else 0
        hab = o["Habilitadas"].sum() if not o.empty and "Habilitadas" in o.columns else 0
        ubic = o["Ubicadas"].sum() if not o.empty and "Ubicadas" in o.columns else 0

        ingresos_periodo = dev + muertos + cajas + prob
        pend_ant = float(prior_balances.get(t, 0))
        total_base = ingresos_periodo + pend_ant

        pend_hab = max(total_base - hab, 0)
        pend_ub = max(total_base - ubic, 0)
        procesado = max(total_base - pend_ub, 0)

        pct_hab = min(hab / total_base * 100, 100) if total_base else 0
        pct_ub = min(procesado / total_base * 100, 100) if total_base else 0

        rows.append({
            "Tienda": t,
            "Dev pzs": dev,
            "Muertos": muertos,
            "Cajas": cajas,
            "Probador": prob,
            "Ingresos periodo": ingresos_periodo,
            "Pend. Ant.": pend_ant,
            "Total": total_base,
            "Recolectadas": reco,
            "Habilitadas": hab,
            "Pend. Hab.": pend_hab,
            "% Acond.": pct_hab,
            "Ubicadas": ubic,
            "Pend. Ub.": pend_ub,
            "% Ubic.": pct_ub,
        })

    return pd.DataFrame(rows)


def summary_from_table(df, income_column="Total"):
    """Calcula KPI respetando los pendientes individuales por tienda.

    - Pendiente general = suma de `Pend. Ub.` de cada tienda.
    - % Procesado = (base - pendiente) / base.
    - Nunca se compensan pendientes entre tiendas.
    """
    if df is None or df.empty:
        return {
            "Ingresos": 0,
            "Acondicionado": 0,
            "Ubicado": 0,
            "Pendiente": 0,
            "% Procesado": 0,
        }

    base_col = income_column if income_column in df.columns else "Total"

    ingresos = pd.to_numeric(
        df.get(base_col, pd.Series(dtype=float)),
        errors="coerce",
    ).fillna(0).sum()

    hab = pd.to_numeric(
        df.get("Habilitadas", pd.Series(dtype=float)),
        errors="coerce",
    ).fillna(0).sum()

    ubic = pd.to_numeric(
        df.get("Ubicadas", pd.Series(dtype=float)),
        errors="coerce",
    ).fillna(0).sum()

    pendiente = pd.to_numeric(
        df.get("Pend. Ub.", pd.Series(dtype=float)),
        errors="coerce",
    ).fillna(0).clip(lower=0).sum()

    procesado = max(float(ingresos) - float(pendiente), 0)
    pct = min(procesado / float(ingresos) * 100, 100) if ingresos > 0 else 0

    return {
        "Ingresos": ingresos,
        "Acondicionado": hab,
        "Ubicado": ubic,
        "Pendiente": pendiente,
        "% Procesado": pct,
    }


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
    column_count = max(len(show.columns), 1)
    adaptive_min = 62 if column_count >= 8 else 82
    gb.configure_default_column(
        filter=True, sortable=True, resizable=True, editable=editable,
        minWidth=adaptive_min, wrapHeaderText=True, autoHeaderHeight=True
    )
    if "Tienda" in show.columns:
        gb.configure_column("Tienda", pinned="left", minWidth=105, maxWidth=150)
    for col in show.columns:
        if col != "Tienda":
            if col == "% Ubic.":
                gb.configure_column(
                    col,
                    type=["rightAligned"],
                    minWidth=68,
                    cellStyle=JsCode("""
                        function(params) {
                            const v = parseFloat(String(params.value).replace('%','').replace(',',''));
                            if (isNaN(v)) return {};
                            if (v < 75) {
                                return {'color':'#D71920','fontWeight':'900'};
                            }
                            if (v >= 90) {
                                return {'color':'#008A3B','fontWeight':'900'};
                            }
                            return {'color':'#111827','fontWeight':'700'};
                        }
                    """)
                )
            else:
                gb.configure_column(col, type=["rightAligned"], minWidth=62)
    opts = gb.build()
    opts["rowHeight"] = 34
    opts["headerHeight"] = 46
    opts["suppressHorizontalScroll"] = True
    opts["onGridReady"] = JsCode("function(params){setTimeout(function(){params.api.sizeColumnsToFit();},80);}")
    opts["onGridSizeChanged"] = JsCode("function(params){setTimeout(function(){params.api.sizeColumnsToFit();},50);}")
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
        ".ag-cell": {"font-size": "11px !important", "padding-left": "6px !important", "padding-right": "6px !important"},
        ".ag-header-cell": {"padding-left": "5px !important", "padding-right": "5px !important"},
        ".ag-header-cell-text": {"font-size": "10px !important", "white-space": "normal !important", "line-height": "1.1 !important"},
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
        ("⌛", "Pendientes por Ubicar", fmt_num(res.get("Pendiente", 0)), "Piezas ingresadas - piezas ubicadas", "#05B957"),
        ("%", "% Procesado", fmt_pct(res.get("% Procesado", 0)), "Piezas ubicadas / piezas ingresadas", "#3720B8"),
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


def combined_chart(df, title, income_column="Total"):
    if df is None or df.empty:
        return

    chart_df = df.copy()
    for c in [income_column, "Habilitadas", "Ubicadas"]:
        if c not in chart_df.columns:
            chart_df[c] = 0
        chart_df[c] = pd.to_numeric(chart_df[c], errors="coerce").fillna(0)

    raw_max = max(float(chart_df[c].max()) for c in [income_column, "Habilitadas", "Ubicadas"])
    ymax = raw_max * 1.55 if raw_max > 0 else 10
    leader_gap = max(ymax * 0.075, 30)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=chart_df["Tienda"],
        y=chart_df[income_column],
        mode="lines+markers",
        name="Total ingresos",
        line=dict(color="#43A5FF", width=4),
        marker=dict(color="#43A5FF", size=9),
        hovertemplate="<b>%{x}</b><br>Total ingresos: %{y:,.0f}<extra></extra>",
    ))

    fig.add_trace(go.Bar(
        x=chart_df["Tienda"],
        y=chart_df["Habilitadas"],
        name="Pzas Habilitadas",
        marker_color=AZUL,
        text=chart_df["Habilitadas"].map(lambda x: f"<b>{x:,.0f}</b>"),
        textposition="outside",
        textfont=dict(color="#111827", size=13, family="Arial Black"),
        cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>Habilitadas: %{y:,.0f}<extra></extra>",
    ))

    fig.add_trace(go.Bar(
        x=chart_df["Tienda"],
        y=chart_df["Ubicadas"],
        name="Pzas Ubicadas",
        marker_color=ROSA,
        text=chart_df["Ubicadas"].map(lambda x: f"<b>{x:,.0f}</b>"),
        textposition="outside",
        textfont=dict(color="#111827", size=13, family="Arial Black"),
        cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>Ubicadas: %{y:,.0f}<extra></extra>",
    ))

    for tienda, total, habilitadas, ubicadas in zip(
        chart_df["Tienda"],
        chart_df[income_column],
        chart_df["Habilitadas"],
        chart_df["Ubicadas"],
    ):
        group_top = max(float(total), float(habilitadas), float(ubicadas))
        label_y = min(group_top + leader_gap, ymax * 0.94)

        fig.add_shape(
            type="line",
            x0=tienda,
            x1=tienda,
            y0=float(total) + max(ymax * 0.012, 5),
            y1=label_y - max(ymax * 0.018, 8),
            line=dict(color="#43A5FF", width=2, dash="dot"),
            layer="above",
        )
        fig.add_annotation(
            x=tienda,
            y=label_y,
            text=f"<b>{float(total):,.0f}</b>",
            showarrow=False,
            font=dict(color="#111827", size=13, family="Arial Black"),
            bgcolor="rgba(255,255,255,0.96)",
            bordercolor="#D9E1EE",
            borderwidth=1,
            borderpad=3,
        )

    fig.update_layout(
        title=title,
        barmode="group",
        height=580,
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(orientation="h", y=1.08, x=1, xanchor="right"),
        margin=dict(l=8, r=8, t=72, b=92),
        dragmode=False,
        uniformtext_minsize=10,
        uniformtext_mode="show",
    )
    fig.update_xaxes(tickangle=-45, showgrid=False, fixedrange=True)
    fig.update_yaxes(
        showgrid=True,
        gridcolor="#E5E7EB",
        fixedrange=True,
        range=[0, ymax],
        tickformat=",d",
    )
    st.plotly_chart(
        fig,
        width="stretch",
        config={
            "displayModeBar": False,
            "scrollZoom": False,
            "doubleClick": False,
            "responsive": True,
        },
    )


def _pdf_icon(symbol, color_hex):
    d = Drawing(34, 34)
    d.add(Circle(17, 17, 16, fillColor=colors.HexColor(color_hex), strokeColor=None))
    d.add(String(
        17, 12, symbol,
        textAnchor="middle",
        fontName="Helvetica-Bold",
        fontSize=16,
        fillColor=colors.white,
    ))
    return d


def _pdf_kpi_card(symbol, title, value, note, color_hex, styles):
    icon = _pdf_icon(symbol, color_hex)

    title_p = Paragraph(
        f"<b>{title}</b>",
        ParagraphStyle(
            f"kpi_title_{re.sub(r'[^A-Za-z0-9]', '', title)}",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.1,
            leading=8.2,
            textColor=colors.HexColor("#15102E"),
            spaceAfter=0,
        ),
    )
    value_p = Paragraph(
        f"<font color='{ROSA}' size='14'><b>{value}</b></font>",
        ParagraphStyle(
            f"kpi_value_{re.sub(r'[^A-Za-z0-9]', '', title)}",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=15,
            textColor=colors.HexColor(ROSA),
            spaceAfter=0,
        ),
    )
    note_p = Paragraph(
        note,
        ParagraphStyle(
            f"kpi_note_{re.sub(r'[^A-Za-z0-9]', '', title)}",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=5.2,
            leading=6.2,
            textColor=colors.HexColor("#4B5563"),
            spaceAfter=0,
        ),
    )

    text_stack = Table(
        [[title_p], [value_p], [note_p]],
        colWidths=[102],
        rowHeights=[17, 18, 18],
    )
    text_stack.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 1),
        ("RIGHTPADDING", (0,0), (-1,-1), 1),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))

    inner = Table(
        [[icon, text_stack]],
        colWidths=[36, 104],
        rowHeights=[58],
    )
    inner.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (0,0), 1),
        ("RIGHTPADDING", (0,0), (0,0), 3),
        ("LEFTPADDING", (1,0), (1,0), 1),
        ("RIGHTPADDING", (1,0), (1,0), 1),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))

    outer = Table([[inner]], colWidths=[146], rowHeights=[66])
    outer.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.white),
        ("BOX", (0,0), (-1,-1), 0.55, colors.HexColor("#D9E1EE")),
        ("LEFTPADDING", (0,0), (-1,-1), 3),
        ("RIGHTPADDING", (0,0), (-1,-1), 3),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    return outer



def _pdf_footer(canvas, doc):
    canvas.saveState()
    page_width, _ = landscape(letter)

    canvas.setStrokeColor(colors.HexColor("#D9E1EE"))
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 18, page_width - doc.rightMargin, 18)

    canvas.setFont("Helvetica-Bold", 6.2)
    canvas.setFillColor(colors.HexColor("#5B6476"))
    canvas.drawString(
        doc.leftMargin,
        8,
        "INFORMACIÓN CONFIDENCIAL | Price Shoes | Operaciones Ropa",
    )
    canvas.restoreState()


def _pdf_chart(df):
    drawing = Drawing(742, 215)
    x0, y0 = 48, 34
    width, height = 655, 134

    tiendas = list(df["Tienda"].astype(str))
    hab = pd.to_numeric(df["Habilitadas"], errors="coerce").fillna(0).astype(float).tolist()
    ubic = pd.to_numeric(df["Ubicadas"], errors="coerce").fillna(0).astype(float).tolist()
    total = pd.to_numeric(df["Total"], errors="coerce").fillna(0).astype(float).tolist()

    maxv = max(hab + ubic + total + [10.0])
    ymax = maxv * 1.62

    # Ejes y retícula.
    drawing.add(Line(x0, y0, x0 + width, y0, strokeColor=colors.HexColor("#AEB8C8"), strokeWidth=0.7))
    for i in range(6):
        val = ymax * i / 5
        y = y0 + height * i / 5
        drawing.add(Line(x0, y, x0 + width, y, strokeColor=colors.HexColor("#E6EAF0"), strokeWidth=0.5))
        drawing.add(String(
            x0 - 8, y - 2, f"{val:,.0f}",
            textAnchor="end", fontSize=5.5,
            fillColor=colors.HexColor("#586174"),
        ))

    n = max(1, len(tiendas))
    group_w = width / n
    bar_w = min(24, group_w * 0.27)
    line_points = []

    def add_label_box(cx, cy, text, font_size=6.5, pad_x=3.5, pad_y=2.0):
        label_w = max(18, len(text) * font_size * 0.56 + pad_x * 2)
        label_h = font_size + pad_y * 2 + 1
        drawing.add(Rect(
            cx - label_w / 2,
            cy - pad_y - 1,
            label_w,
            label_h,
            fillColor=colors.white,
            strokeColor=colors.HexColor("#D9E1EE"),
            strokeWidth=0.35,
        ))
        drawing.add(String(
            cx,
            cy,
            text,
            textAnchor="middle",
            fontName="Helvetica-Bold",
            fontSize=font_size,
            fillColor=colors.black,
        ))

    for i, tienda in enumerate(tiendas):
        center = x0 + group_w * (i + 0.5)
        x_h = center - bar_w - 1.5
        x_u = center + 1.5

        h_h = height * hab[i] / ymax
        h_u = height * ubic[i] / ymax
        point_y = y0 + height * total[i] / ymax

        drawing.add(Rect(
            x_h, y0, bar_w, h_h,
            fillColor=colors.HexColor(AZUL),
            strokeColor=None,
        ))
        drawing.add(Rect(
            x_u, y0, bar_w, h_u,
            fillColor=colors.HexColor(ROSA),
            strokeColor=None,
        ))

        # Etiquetas de barras: siempre visibles sobre fondo blanco.
        hab_label_y = y0 + h_h + 7
        ubic_label_y = y0 + h_u + 7
        add_label_box(x_h + bar_w / 2, hab_label_y, f"{hab[i]:,.0f}", font_size=6.4)
        add_label_box(x_u + bar_w / 2, ubic_label_y, f"{ubic[i]:,.0f}", font_size=6.4)

        line_points.append((center, point_y))

        # El número de la línea se coloca por encima de la barra más alta del grupo.
        group_top_value = max(total[i], hab[i], ubic[i])
        group_top_y = y0 + height * group_top_value / ymax
        label_y = min(group_top_y + 26, y0 + height + 23)

        leader = Line(
            center,
            point_y + 3,
            center,
            label_y - 8,
            strokeColor=colors.HexColor("#43A5FF"),
            strokeWidth=1.1,
        )
        leader.strokeDashArray = [2, 2]
        drawing.add(leader)
        add_label_box(center, label_y, f"{total[i]:,.0f}", font_size=6.7)

        drawing.add(String(
            center + 2,
            y0 - 13,
            tienda,
            textAnchor="end",
            fontSize=5.7,
            fillColor=colors.HexColor("#4B5563"),
            angle=35,
        ))

    if len(line_points) >= 2:
        drawing.add(PolyLine(
            line_points,
            strokeColor=colors.HexColor("#43A5FF"),
            strokeWidth=2.2,
        ))
    for x, y in line_points:
        drawing.add(Circle(
            x, y, 2.5,
            fillColor=colors.HexColor("#43A5FF"),
            strokeColor=None,
        ))

    # Leyenda.
    legend_y = 201
    drawing.add(Line(500, legend_y, 518, legend_y, strokeColor=colors.HexColor("#43A5FF"), strokeWidth=2.2))
    drawing.add(String(522, legend_y - 2, "Total ingresos", fontSize=5.8, fillColor=colors.HexColor("#313847")))
    drawing.add(Rect(588, legend_y - 4, 8, 8, fillColor=colors.HexColor(AZUL), strokeColor=None))
    drawing.add(String(600, legend_y - 2, "Pzas Habilitadas", fontSize=5.8, fillColor=colors.HexColor("#313847")))
    drawing.add(Rect(675, legend_y - 4, 8, 8, fillColor=colors.HexColor(ROSA), strokeColor=None))
    drawing.add(String(687, legend_y - 2, "Pzas Ubicadas", fontSize=5.8, fillColor=colors.HexColor("#313847")))

    return drawing


def build_pdf_report(title, subtitle, kpi_values, df):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=18,
        leftMargin=18,
        topMargin=14,
        bottomMargin=28,
    )
    styles = getSampleStyleSheet()
    story = []

    # Encabezado con logo Price Shoes.
    logo_path = LOGO_FILE
    logo = RLImage(str(logo_path), width=58, height=34) if logo_path.exists() else Paragraph("<b>Price Shoes</b>", styles["Normal"])
    title_block = Paragraph(
        f"<font name='Helvetica-Bold' color='#1D1259' size='13'>PS Operaciones Ropa</font><br/>"
        f"<font name='Helvetica-Bold' color='#1D1259' size='10'>{title}</font>"
        f"<font name='Helvetica' color='#5B6476' size='8'> | {subtitle}</font>",
        ParagraphStyle("pdf_header", parent=styles["Normal"], leading=14),
    )
    header = Table([[logo, title_block]], colWidths=[72, 650], rowHeights=[40])
    header.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    story.append(header)

    pink_line = Table([[""]], colWidths=[744], rowHeights=[3])
    pink_line.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), colors.HexColor(ROSA))]))
    story.append(pink_line)
    story.append(Spacer(1, 7))

    cards = [
        _pdf_kpi_card("↻", "Piezas Ingresadas", fmt_num(kpi_values.get("Ingresos", 0)), "Dev + muertos + cajas + probador", ROSA, styles),
        _pdf_kpi_card("✓", "Piezas Acondicionadas", fmt_num(kpi_values.get("Acondicionado", 0)), "Acondicionado", "#5B00D6", styles),
        _pdf_kpi_card("⊕", "Piezas Ubicadas", fmt_num(kpi_values.get("Ubicado", 0)), "Ubicado", "#F59E0B", styles),
        _pdf_kpi_card("⌛", "Pendientes por Ubicar", fmt_num(kpi_values.get("Pendiente", 0)), "Piezas ingresadas - piezas ubicadas", "#05B957", styles),
        _pdf_kpi_card("%", "% Procesado", fmt_pct(kpi_values.get("% Procesado", 0)), "Piezas ubicadas / piezas ingresadas", "#5B00D6", styles),
    ]
    cards_row = Table([cards], colWidths=[148,148,148,148,148], rowHeights=[68])
    cards_row.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 2),
        ("RIGHTPADDING", (0,0), (-1,-1), 2),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(cards_row)
    story.append(Spacer(1, 6))

    story.append(Paragraph(
        "<b>Tabla por tienda - Por Día</b>",
        ParagraphStyle("pdf_h2", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#1D1259"), spaceAfter=5),
    ))

    columns = ["Tienda","Dev pzs","Muertos","Cajas","Probador","Pend. Ant.","Total","Recolectadas","Habilitadas","Pend. Hab.","% Acond.","Ubicadas","Pend. Ub.","% Ubic."]
    pdf_df = df[[c for c in columns if c in df.columns]].copy()

    raw_pct_ubic = pd.to_numeric(pdf_df["% Ubic."], errors="coerce").fillna(0).tolist() if "% Ubic." in pdf_df.columns else []
    for col in pdf_df.columns:
        if col == "Tienda":
            continue
        values = pd.to_numeric(pdf_df[col], errors="coerce").fillna(0)
        pdf_df[col] = values.map(lambda x: f"{x:.1f}%" if "%" in col else f"{x:,.0f}")

    data = [list(pdf_df.columns)] + pdf_df.astype(str).values.tolist()
    widths = [70,45,45,43,46,52,48,60,58,55,52,50,54,48]
    table = Table(data, colWidths=widths, repeatRows=1)
    table_style = [
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor(AZUL)),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 6.1),
        ("FONTSIZE", (0,1), (-1,-1), 6.0),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
        ("ALIGN", (0,0), (-1,0), "CENTER"),
        ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#DDE4F0")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F7F9FC")]),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]

    # Semáforo en porcentaje de ubicación.
    if "% Ubic." in pdf_df.columns:
        pct_col = list(pdf_df.columns).index("% Ubic.")
        for row_idx, pct in enumerate(raw_pct_ubic, start=1):
            if pct < 75:
                color = colors.HexColor("#D71920")
            elif pct >= 90:
                color = colors.HexColor("#008A3B")
            else:
                color = colors.HexColor("#111827")
            table_style.extend([
                ("TEXTCOLOR", (pct_col, row_idx), (pct_col, row_idx), color),
                ("FONTNAME", (pct_col, row_idx), (pct_col, row_idx), "Helvetica-Bold"),
            ])

    table.setStyle(TableStyle(table_style))
    story.append(table)
    story.append(Spacer(1, 7))
    story.append(Paragraph(
        "<b>Ingreso vs Habilitado vs Ubicado por tienda</b>",
        ParagraphStyle("pdf_h3", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#1D1259"), spaceAfter=2),
    ))
    story.append(_pdf_chart(df))

    doc.build(story, onFirstPage=_pdf_footer, onLaterPages=_pdf_footer)
    buffer.seek(0)
    return buffer.getvalue()

def download_pdf_button(label="Descargar PDF", title="Reporte", subtitle="", kpi_values=None, df=None, key=None):
    if kpi_values is not None and df is not None:
        pdf = build_pdf_report(title, subtitle, kpi_values, df)

        # Extrae la fecha del subtítulo, por ejemplo: "Fecha: 2026-06-28".
        date_match = re.search(r"(\d{4})[-/](\d{2})[-/](\d{2})", str(subtitle))
        if date_match:
            yyyy, mm, dd = date_match.groups()
            date_suffix = f"{dd}-{mm}-{yyyy}"
        else:
            date_suffix = pd.Timestamp.today().strftime("%d-%m-%Y")

        clean_title = re.sub(r"[^A-Za-z0-9ÁÉÍÓÚáéíóúÑñ]+", "_", str(title)).strip("_")
        if clean_title.lower().replace("_", "") in {"pordia", "reporte_pordia"}:
            file_name = f"Reporte_Por_Dia_{date_suffix}.pdf"
        else:
            file_name = f"{clean_title}_{date_suffix}.pdf"

        st.download_button(
            label,
            data=pdf,
            file_name=file_name,
            mime="application/pdf",
            key=key or f"pdf_{clean_title}_{date_suffix}",
        )
    else:
        st.button(label, help="PDF disponible en pestañas con indicadores.")



def build_generic_table_pdf(title, subtitle, df, kpi_values=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=18,
        leftMargin=18,
        topMargin=14,
        bottomMargin=28,
    )
    styles = getSampleStyleSheet()
    story = []

    logo_path = LOGO_FILE
    logo = RLImage(str(logo_path), width=58, height=34) if logo_path.exists() else Paragraph("<b>Price Shoes</b>", styles["Normal"])
    _pdf_user = st.session_state.get("user", {})
    _pdf_scope = _pdf_user.get("scope_value") or ("Compañía" if _pdf_user.get("scope_type", "COMPANY") == "COMPANY" else _pdf_user.get("scope_type", ""))
    header_text = Paragraph(
        f"<font name='Helvetica-Bold' color='#1D1259' size='13'>PS Operaciones Ropa</font><br/>"
        f"<font name='Helvetica-Bold' color='#1D1259' size='10'>{title}</font>"
        f"<font name='Helvetica' color='#5B6476' size='8'> | {subtitle}</font><br/>"
        f"<font name='Helvetica' color='#6B7280' size='7'>Usuario: {_pdf_user.get('nombre','')} · Alcance: {_pdf_scope} · Generado: {datetime.now(MX_TZ).strftime('%d/%m/%Y %H:%M')}</font>",
        ParagraphStyle("generic_header", parent=styles["Normal"], leading=14),
    )
    header = Table([[logo, header_text]], colWidths=[72, 650], rowHeights=[40])
    header.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(header)

    pink_line = Table([[""]], colWidths=[744], rowHeights=[3])
    pink_line.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor(ROSA)),
    ]))
    story.append(pink_line)
    story.append(Spacer(1, 7))

    if kpi_values:
        cards = [
            _pdf_kpi_card("↻", "Piezas Ingresadas", fmt_num(kpi_values.get("Ingresos", 0)), "Dev + muertos + cajas + probador", ROSA, styles),
            _pdf_kpi_card("✓", "Piezas Acondicionadas", fmt_num(kpi_values.get("Acondicionado", 0)), "Acondicionado", "#5B00D6", styles),
            _pdf_kpi_card("⊕", "Piezas Ubicadas", fmt_num(kpi_values.get("Ubicado", 0)), "Ubicado", "#F59E0B", styles),
            _pdf_kpi_card("⌛", "Pendientes por Ubicar", fmt_num(kpi_values.get("Pendiente", 0)), "Piezas ingresadas - piezas ubicadas", "#05B957", styles),
            _pdf_kpi_card("%", "% Procesado", fmt_pct(kpi_values.get("% Procesado", 0)), "Piezas ubicadas / piezas ingresadas", "#5B00D6", styles),
        ]
        cards_row = Table([cards], colWidths=[148] * 5, rowHeights=[68])
        cards_row.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 2),
            ("RIGHTPADDING", (0,0), (-1,-1), 2),
        ]))
        story.append(cards_row)
        story.append(Spacer(1, 7))

    if df is None or df.empty:
        story.append(Paragraph("Sin información para el periodo seleccionado.", styles["Normal"]))
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    out = df.copy()
    numeric_raw = {}
    for col in out.columns:
        if pd.api.types.is_numeric_dtype(out[col]):
            numeric_raw[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).tolist()
            values = pd.to_numeric(out[col], errors="coerce").fillna(0)
            if "%" in str(col):
                out[col] = values.map(lambda x: f"{x:.1f}%")
            elif "$" in str(col) or "Importe" in str(col) or "Recuperación" in str(col):
                out[col] = values.map(lambda x: f"${x:,.0f}")
            else:
                out[col] = values.map(lambda x: f"{x:,.0f}")

    max_cols = max(1, len(out.columns))
    widths = [730 / max_cols] * max_cols
    data = [list(out.columns)] + out.astype(str).values.tolist()
    table = Table(data, colWidths=widths, repeatRows=1)

    style_cmds = [
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor(AZUL)),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 6.2),
        ("FONTSIZE", (0,1), (-1,-1), 5.9),
        ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#DDE4F0")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F7F9FC")]),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]

    # Semáforo solicitado para porcentajes de ubicación:
    # menor de 75% rojo; 90% o más verde.
    for pct_name in ["% Ubic.", "% Ubicado", "% Ubicación"]:
        if pct_name in out.columns and pct_name in numeric_raw:
            col_idx = list(out.columns).index(pct_name)
            for row_idx, pct in enumerate(numeric_raw[pct_name], start=1):
                if pct < 75:
                    color = colors.HexColor("#D71920")
                elif pct >= 90:
                    color = colors.HexColor("#008A3B")
                else:
                    color = colors.HexColor("#111827")
                style_cmds.extend([
                    ("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), color),
                    ("FONTNAME", (col_idx, row_idx), (col_idx, row_idx), "Helvetica-Bold"),
                ])

    table.setStyle(TableStyle(style_cmds))
    story.append(table)

    # Semanal y mensual usan la misma tabla operativa, por lo que se agrega
    # también el gráfico combinado dentro del PDF.
    chart_cols = {"Tienda", "Total", "Habilitadas", "Ubicadas"}
    if chart_cols.issubset(set(df.columns)):
        story.append(Spacer(1, 7))
        story.append(Paragraph(
            "<b>Ingreso vs Habilitado vs Ubicado por tienda</b>",
            ParagraphStyle(
                "generic_chart_title",
                parent=styles["Normal"],
                fontSize=9,
                textColor=colors.HexColor("#1D1259"),
                spaceAfter=2,
            ),
        ))
        story.append(_pdf_chart(df))

    doc.build(story, onFirstPage=_pdf_footer, onLaterPages=_pdf_footer)
    buffer.seek(0)
    return buffer.getvalue()


def generic_pdf_button(title, subtitle, df, kpi_values=None, file_name=None, key=None):
    pdf = build_generic_table_pdf(title, subtitle, df, kpi_values)
    if not file_name:
        clean = re.sub(r"[^A-Za-z0-9ÁÉÍÓÚáéíóúÑñ]+", "_", title).strip("_")
        file_name = f"{clean}.pdf"
    st.download_button(
        "Descargar PDF",
        data=pdf,
        file_name=file_name,
        mime="application/pdf",
        key=key or f"pdf_generic_{re.sub(r'[^A-Za-z0-9]', '', title)}",
    )

def login_sidebar():
    if restore_persistent_session():
        return True

    logo_data = ""
    if LOGO_FILE.exists():
        logo_data = base64.b64encode(LOGO_FILE.read_bytes()).decode("utf-8")

    boutique_file = ASSETS_DIR / "login_boutique_reference.png"
    boutique_data = ""
    if boutique_file.exists():
        boutique_data = base64.b64encode(boutique_file.read_bytes()).decode("utf-8")

    st.markdown(
        f"""
        <style>
        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        #MainMenu,
        footer {{
            display:none!important;
        }}
        [data-testid="stAppViewContainer"] {{
            background:
                radial-gradient(circle at 10% 20%,rgba(51,102,204,.12),transparent 28%),
                radial-gradient(circle at 92% 82%,rgba(162,107,255,.18),transparent 30%),
                linear-gradient(145deg,#F2F7FF 0%,#FFFFFF 58%,#EEF2FF 100%)!important;
        }}
        [data-testid="stMain"] {{
            min-height:100vh!important;
        }}
        .block-container {{
            max-width:1080px!important;
            min-height:100vh!important;
            padding:3vh 1rem!important;
            display:flex!important;
            flex-direction:column!important;
            justify-content:center!important;
        }}
        .login-shell {{
            display:grid;
            grid-template-columns:0.92fr 1.08fr;
            min-height:610px;
            background:#FFF;
            border:1px solid #E0E7F1;
            border-radius:18px;
            overflow:hidden;
            box-shadow:0 22px 65px rgba(23,59,115,.17);
        }}
        .login-left {{
            padding:38px 44px 310px;
            background:#FFF;
            position:relative;
        }}
        .login-logo {{
            display:flex;
            justify-content:center;
            height:105px;
            margin-bottom:10px;
        }}
        .login-logo img {{
            width:210px;
            height:105px;
            object-fit:contain;
            display:block;
        }}
        .login-title {{
            color:#173B73;
            text-align:center;
            font-size:27px;
            font-weight:900;
            line-height:1.15;
        }}
        .login-subtitle {{
            color:#667085;
            text-align:center;
            font-size:14px;
            font-weight:600;
            margin-top:7px;
        }}
        .login-boutique {{
            min-height:610px;
            background:
                linear-gradient(180deg,rgba(13,43,91,.05),rgba(11,31,73,.22)),
                url("data:image/png;base64,{boutique_data}") center/cover no-repeat;
            position:relative;
        }}
        .login-boutique::after {{
            content:"";
            position:absolute;
            inset:0;
            background:linear-gradient(90deg,rgba(51,102,204,.12),transparent 36%);
            pointer-events:none;
        }}
        [data-testid="stForm"] {{
            position:relative!important;
            z-index:20!important;
            width:calc(46% - 62px)!important;
            max-width:390px!important;
            margin:-355px 0 0 44px!important;
            padding:0!important;
            border:0!important;
            background:transparent!important;
        }}
        [data-testid="stForm"] label p {{
            color:#173B73!important;
            font-weight:750!important;
        }}
        [data-testid="stForm"] input {{
            min-height:48px!important;
            border-radius:7px!important;
            background:#FFF!important;
            color:#111827!important;
            border-color:#CED9E8!important;
        }}
        [data-testid="stForm"] button[kind="primary"] {{
            min-height:50px!important;
            border-radius:7px!important;
            border:none!important;
            background:linear-gradient(90deg,#173B73,#1657AD)!important;
            font-weight:850!important;
            margin-top:10px!important;
        }}
        .login-version {{
            position:relative;
            z-index:20;
            width:calc(46% - 62px);
            max-width:390px;
            margin:20px 0 0 44px;
            padding-top:16px;
            border-top:1px solid #E5EAF2;
            color:#667085;
            text-align:center;
            font-size:12px;
            line-height:1.55;
        }}
        @media(max-width:820px) {{
            .block-container {{
                max-width:520px!important;
                padding:18px 12px 28px!important;
            }}
            .login-shell {{
                display:block;
                min-height:auto;
            }}
            .login-left {{
                padding:28px 24px 300px;
            }}
            .login-boutique {{
                min-height:250px;
            }}
            [data-testid="stForm"] {{
                width:auto!important;
                max-width:none!important;
                margin:-545px 26px 0!important;
            }}
            .login-version {{
                width:auto;
                max-width:none;
                margin:18px 26px 20px;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="login-shell">
          <section class="login-left">
            <div class="login-logo">
              <img src="data:image/png;base64,{logo_data}" alt="Price Shoes">
            </div>
            <div class="login-title">PS Operaciones Ropa</div>
            <div class="login-subtitle">Plataforma Integral de Gestión Operativa</div>
          </section>
          <section class="login-boutique" aria-label="Boutique Price Shoes"></section>
        </div>
        """,
        unsafe_allow_html=True,
    )

    remembered_user = st.query_params.get("remember_user", "")
    if isinstance(remembered_user, list):
        remembered_user = remembered_user[0] if remembered_user else ""

    with st.form("login_portal_form", clear_on_submit=False):
        nom = st.text_input(
            "Usuario",
            value=str(remembered_user or ""),
            key="login_user",
            placeholder="Ingresa tu usuario",
        )
        pwd = st.text_input(
            "Contraseña",
            type="password",
            key="login_password",
            placeholder="Ingresa tu contraseña",
        )
        remember = st.checkbox(
            "Recordarme durante 30 días",
            value=bool(remembered_user),
            key="login_remember",
        )
        submitted = st.form_submit_button(
            "↪  Iniciar sesión",
            type="primary",
            width="stretch",
        )

    st.markdown(
        '<div class="login-version">Versión 16.3<br>© Operaciones Ropa</div>',
        unsafe_allow_html=True,
    )

    if submitted:
        user = get_user(nom, pwd)
        if user:
            user["role"] = normalize_role(user.get("role", user.get("permiso")))
            user["permiso"] = ROLE_LABELS.get(
                user["role"], user.get("permiso", "Consulta")
            )
            st.session_state["user"] = user
            st.session_state["nav_page"] = "Centro Ejecutivo"
            create_persistent_session(user, remember=remember)
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos.")
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

    if is_admin():
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


def render_file_admin_panel():
    """Panel administrativo embebido en el menú de tres puntos.

    No utiliza st.dialog, por lo que evita por completo los errores de
    diálogos anidados en Streamlit.
    """
    meta = {}
    if META_FILE.exists():
        try:
            meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception:
            meta = {}

    if ACTIVE_FILE.exists():
        st.success("Archivo guardado")
        st.write(f"**Nombre:** {meta.get('nombre_original', ACTIVE_FILE.name)}")
        if meta.get("fecha_carga"):
            st.caption(f"Cargado: {meta.get('fecha_carga')}")

        if cache_valid():
            st.caption("Estado: Procesado y disponible")
        else:
            st.warning("Estado: Guardado, pendiente de procesar")
    else:
        st.warning("No hay archivo cargado")

    uploaded = st.file_uploader(
        "Selecciona un archivo Excel",
        type=["xlsx"],
        key="popover_upload_excel_v140",
        help="Primero se guarda el archivo y después se procesa.",
    )

    if uploaded is not None:
        st.caption(
            f"Seleccionado: {uploaded.name} · "
            f"{uploaded.size / (1024 * 1024):,.1f} MB"
        )

        if st.button(
            "1. Guardar archivo",
            key="popover_save_only_v140",
            type="primary",
            width="stretch",
        ):
            try:
                with st.spinner("Guardando archivo..."):
                    save_uploaded_file(uploaded)

                append_file_history(
                    "Carga",
                    uploaded.name,
                    "Guardado",
                    "Archivo guardado; pendiente de procesamiento",
                )
                st.success("Archivo guardado. Continúa con el procesamiento.")
                st.rerun()
            except Exception as exc:
                st.error("No fue posible guardar el archivo.")
                st.exception(exc)

    if ACTIVE_FILE.exists() and not cache_valid():
        st.divider()
        st.info(
            "El archivo ya está guardado. El procesamiento puede tardar "
            "porque se revisan las hojas operativas y comerciales."
        )

        if st.button(
            "2. Procesar archivo activo",
            key="popover_process_active_v140",
            type="primary",
            width="stretch",
        ):
            try:
                process_excel(str(ACTIVE_FILE))

                append_file_history(
                    "Proceso",
                    meta.get("nombre_original", ACTIVE_FILE.name),
                    "Procesado",
                    "Archivo procesado correctamente",
                )
                st.success("Archivo procesado correctamente.")
                st.rerun()
            except Exception as exc:
                st.error("No fue posible procesar el archivo.")
                st.exception(exc)

    if ACTIVE_FILE.exists():
        st.divider()
        if st.button(
            "Eliminar archivo activo",
            key="popover_delete_active_v140",
            width="stretch",
        ):
            file_name = meta.get("nombre_original", ACTIVE_FILE.name)
            delete_active_file()

            append_file_history(
                "Eliminación",
                file_name,
                "Eliminado",
                "Archivo activo eliminado",
            )
            st.success("Archivo eliminado.")
            st.rerun()


def page_portal_admin():
    """Página empresarial para administrar la fuente de Cambios y Muertos."""
    user = st.session_state.get("user", {})
    if not is_admin(user):
        st.error("Acceso exclusivo para Administrador.")
        if st.button("Volver al portal", key="admin_back_unauthorized"):
            st.session_state["portal_view"] = "apps"
            st.rerun()
        return

    render_header()
    st.markdown("## Administración · Cambios y Muertos")
    st.caption("Carga, procesamiento, historial y eliminación de la fuente de datos.")

    meta = {}
    if META_FILE.exists():
        try:
            meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception:
            meta = {}

    status_col, action_col = st.columns([3.2, 6.8], gap="large")

    with status_col:
        st.markdown('<div class="admin-section-title">Estado del archivo</div>', unsafe_allow_html=True)

        if ACTIVE_FILE.exists():
            st.success("Archivo guardado")
            st.markdown(f"**Nombre:** {meta.get('nombre_original', ACTIVE_FILE.name)}")
            if meta.get("fecha_carga"):
                st.caption(f"Cargado: {meta.get('fecha_carga')}")

            try:
                size_mb = ACTIVE_FILE.stat().st_size / (1024 * 1024)
                st.caption(f"Tamaño: {size_mb:,.1f} MB")
            except Exception:
                pass

            if cache_valid():
                st.markdown(
                    '<div class="admin-status admin-status-ok">● Procesado y disponible</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="admin-status admin-status-warn">● Pendiente de procesar</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.warning("No hay archivo cargado")

        st.divider()
        st.markdown("#### Flujo")
        st.markdown(
            """
            1. Seleccionar el Excel  
            2. Guardar el archivo  
            3. Procesar el archivo activo  
            4. Consultar los indicadores
            """
        )

    with action_col:
        st.markdown('<div class="admin-section-title">Administrar fuente</div>', unsafe_allow_html=True)

        uploaded = st.file_uploader(
            "Selecciona un archivo Excel",
            type=["xlsx"],
            key="admin_page_upload_v150",
            help="El archivo seleccionado sustituirá al archivo activo cuando se guarde.",
        )

        if uploaded is not None:
            st.info(
                f"Seleccionado: **{uploaded.name}** · "
                f"{uploaded.size / (1024 * 1024):,.1f} MB"
            )

        save_col, process_col = st.columns(2)
        with save_col:
            save_disabled = uploaded is None or not can_write()
            if st.button(
                "1. Guardar archivo",
                key="admin_page_save_v150",
                type="primary",
                width="stretch",
                disabled=save_disabled,
            ):
                try:
                    with st.spinner("Guardando archivo en el servidor..."):
                        save_uploaded_file(uploaded)
                    append_file_history(
                        "Carga",
                        uploaded.name,
                        "Guardado",
                        "Archivo guardado; pendiente de procesamiento",
                    )
                    st.success("Archivo guardado. Ahora presiona Procesar archivo activo.")
                    st.rerun()
                except Exception as exc:
                    st.error("No fue posible guardar el archivo.")
                    st.exception(exc)

        with process_col:
            process_disabled = not ACTIVE_FILE.exists() or cache_valid() or not can_write()
            if st.button(
                "2. Procesar archivo activo",
                key="admin_page_process_v150",
                type="primary",
                width="stretch",
                disabled=process_disabled,
            ):
                try:
                    with st.spinner(
                        "Procesando hojas operativas y comerciales. "
                        "No cierres esta ventana..."
                    ):
                        process_excel(str(ACTIVE_FILE))
                    append_file_history(
                        "Proceso",
                        meta.get("nombre_original", ACTIVE_FILE.name),
                        "Procesado",
                        "Archivo procesado correctamente",
                    )
                    st.success("Archivo procesado correctamente.")
                    st.rerun()
                except Exception as exc:
                    st.error("No fue posible procesar el archivo.")
                    st.exception(exc)

        if ACTIVE_FILE.exists() and cache_valid():
            st.success("La información está lista para consultarse.")

        st.divider()
        st.markdown("#### Acciones adicionales")
        repro_col, delete_col = st.columns(2)

        with repro_col:
            if ACTIVE_FILE.exists() and st.button(
                "Reprocesar archivo",
                key="admin_page_reprocess_v150",
                width="stretch",
                disabled=not can_write(),
            ):
                try:
                    process_excel(str(ACTIVE_FILE))
                    append_file_history(
                        "Reproceso",
                        meta.get("nombre_original", ACTIVE_FILE.name),
                        "Procesado",
                        "Archivo reprocesado correctamente",
                    )
                    st.success("Archivo reprocesado.")
                    st.rerun()
                except Exception as exc:
                    st.error("No fue posible reprocesar el archivo.")
                    st.exception(exc)

        with delete_col:
            if ACTIVE_FILE.exists() and st.button(
                "Eliminar archivo activo",
                key="admin_page_delete_v150",
                width="stretch",
                disabled=not can_write(),
            ):
                file_name = meta.get("nombre_original", ACTIVE_FILE.name)
                delete_active_file()
                append_file_history(
                    "Eliminación",
                    file_name,
                    "Eliminado",
                    "Archivo activo eliminado",
                )
                st.success("Archivo eliminado.")
                st.rerun()

    st.markdown("### Historial de archivos")
    history = read_file_history() if "read_file_history" in globals() else []
    if history:
        history_df = pd.DataFrame(history)
        desired = ["fecha", "accion", "archivo", "estado", "detalle"]
        history_df = history_df[[c for c in desired if c in history_df.columns]]
        st.dataframe(
            history_df.iloc[::-1].head(100),
            width="stretch",
            hide_index=True,
            height=340,
        )
    else:
        st.info("Aún no hay movimientos registrados en el historial.")

def render_app_portal():
    user = st.session_state.get("user", {})
    permiso = user.get("permiso", "Consulta")
    nombre = user.get("nombre", "Consulta")
    nomina = user.get("nomina", "—")

    # El menú principal no utiliza sidebar; ocupa el 100% del viewport.
    st.markdown(
        """
        <style>
        [data-testid="stMain"]{
          margin-left:0!important;
          width:100%!important;
        }
        .v20-header{
          left:0!important;
        }
        .block-container{
          width:100%!important;
          max-width:1440px!important;
          margin:0 auto!important;
          padding-left:clamp(18px,3vw,44px)!important;
          padding-right:clamp(18px,3vw,44px)!important;
        }
        

</style>
        """,
        unsafe_allow_html=True,
    )

    render_header()

    st.markdown('<main class="v20-portal-content">', unsafe_allow_html=True)
    left, right = st.columns([2.65, 7.35], gap="large", vertical_alignment="top")

    with left:
        st.markdown(
            f"""
            <section class="ps-profile-card">
              <div class="ps-profile-title">Información de usuario</div>
              <div class="ps-profile-row"><span>👤 Usuario</span><b>{nombre}</b></div>
              <div class="ps-profile-row"><span>▣ Nómina</span><b>{nomina}</b></div>
              <div class="ps-profile-row"><span>📍 Área</span><b>Comercial Operativo Ropa</b></div>
              <div class="ps-profile-row"><span>🔐 Perfil</span><b>{permiso}</b></div>
            </section>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <section class="ps-portal-panel">
              <div class="ps-portal-panel-head">Comunicados</div>
              <div class="ps-notice-row"><b>26/07/2026</b><span>Portal empresarial disponible.</span></div>
              <div class="ps-notice-row"><b>Confidencial</b><span>Uso exclusivo de Price Shoes.</span></div>
            </section>
            """,
            unsafe_allow_html=True,
        )

    with right:
        search = st.text_input(
            "Buscar aplicativo",
            placeholder="Siglas o nombre de aplicativo",
            label_visibility="collapsed",
            key="v20_portal_search",
        )

        show_main = not search or any(
            token in search.lower()
            for token in ["cambio", "muerto", "operacion", "indicador", "recuperacion"]
        )

        if show_main:
            app_col, future_col = st.columns(2, gap="medium")
            with app_col:
                if st.button(
                    "⟳\n\nCambios y Muertos\n\nRecuperación · Productividad · Conversión",
                    key="v20_open_cambios_muertos",
                    width="stretch",
                ):
                    st.session_state["active_app"] = "Cambios y Muertos"
                    st.session_state["nav_page"] = "Centro Ejecutivo"
                    st.rerun()

            with future_col:
                st.markdown(
                    """
                    <div class="ps-app-card ps-app-disabled">
                      <div class="ps-app-code">PRX</div>
                      <div class="ps-app-icon">▤</div>
                      <div class="ps-app-name">Módulos autorizados</div>
                      <div class="ps-app-desc">Consulta los módulos disponibles de acuerdo con tu perfil.</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("No se encontraron aplicativos con ese criterio.")

    st.markdown("</main>", unsafe_allow_html=True)


def nav_bar():
    """Menú lateral con control explícito para ocultar y volver a mostrar."""
    role = normalize_role(
        st.session_state.get("user", {}).get("role")
        or st.session_state.get("user", {}).get("permiso", "Consulta")
    )
    pages = [
        "Centro Ejecutivo", "Operación Diaria", "Reporte Semanal",
        "Reporte Mensual", "Productividad", "Recuperación", "Recorridos",
        "Reportes", "Detalle por Tienda", "Detalle por Colaborador",
        "Histórico de Descargas", "Alertas Inteligentes", "Perfil de Usuario",
        "Inteligencia Operativa",
    ]
    if role_level() >= ROLE_LEVEL["ADMIN"]:
        pages += ["Centro de Control", "Administración", "Configuración de Metas",
                  "Carga de Excel", "Diagnóstico del Archivo"]

    current = st.session_state.get("nav_page", "Centro Ejecutivo")
    if current not in pages:
        current = "Centro Ejecutivo"
    if "sidebar_open" not in st.session_state:
        st.session_state["sidebar_open"] = True

    if st.session_state["sidebar_open"]:
        st.markdown("""
        <style>
        [data-testid="stSidebar"]{display:block!important;visibility:visible!important;transform:none!important;width:300px!important;min-width:300px!important;max-width:300px!important;}
        [data-testid="stMain"]{margin-left:300px!important;width:calc(100% - 300px)!important;max-width:calc(100% - 300px)!important;}
        </style>
        """, unsafe_allow_html=True)
        with st.sidebar:
            st.markdown("### PS Operaciones Ropa")
            if st.button("← Ocultar menú", key="v253_hide_menu", width="stretch"):
                st.session_state["sidebar_open"] = False
                st.rerun()
            st.divider()
            selected = st.radio(
                "Navegación", pages, index=pages.index(current),
                label_visibility="collapsed", key="v253_navigation"
            )
    else:
        st.markdown("""
        <style>
        [data-testid="stSidebar"]{display:none!important;width:0!important;min-width:0!important;max-width:0!important;}
        [data-testid="stMain"]{margin-left:0!important;width:100%!important;max-width:100%!important;}
        </style>
        """, unsafe_allow_html=True)
        if st.button("☰ Mostrar menú", key="v253_show_menu", type="primary"):
            st.session_state["sidebar_open"] = True
            st.rerun()
        selected = current

    st.session_state["nav_page"] = selected
    return selected


def reliable_data_horizon(op, co):
    """Obtiene el horizonte real sin eliminar la nueva operación de julio.

    Antes se utilizaba únicamente la fecha máxima comercial. Como las hojas
    comerciales cargadas terminaban el 28/06/2026, toda la información de
    `Resultados productividad 2` del 29/06 en adelante quedaba descartada.

    Ahora:
    - se toman fechas válidas tanto de operación como de comercial;
    - se descartan únicamente fechas futuras anómalas;
    - se conserva la información operativa nueva hasta la fecha actual.
    """
    op = normalize_operation_df(op)
    co = normalize_commercial_df(co)

    op_dates = (
        pd.to_datetime(op["Fecha"], errors="coerce").dropna()
        if op is not None and not op.empty and "Fecha" in op.columns
        else pd.Series(dtype="datetime64[ns]")
    )
    co_dates = (
        pd.to_datetime(co["Fecha"], errors="coerce").dropna()
        if co is not None and not co.empty and "Fecha" in co.columns
        else pd.Series(dtype="datetime64[ns]")
    )

    # Tolerancia corta para capturas con diferencia de zona horaria.
    max_allowed = pd.Timestamp.today().normalize() + pd.Timedelta(days=2)

    if not op_dates.empty:
        op_dates = op_dates[op_dates <= max_allowed]
    if not co_dates.empty:
        co_dates = co_dates[co_dates <= max_allowed]

    all_dates = pd.concat(
        [s for s in [op_dates, co_dates] if not s.empty],
        ignore_index=True,
    ) if (not op_dates.empty or not co_dates.empty) else pd.Series(dtype="datetime64[ns]")

    if all_dates.empty:
        today = pd.Timestamp.today().normalize()
        return today, today

    return all_dates.min().normalize(), all_dates.max().normalize()


def reliable_operation(op, co):
    """Conserva la operación válida de ambas hojas y elimina fechas anómalas."""
    op = normalize_operation_df(op)
    if op is None or op.empty:
        return op

    min_date, max_date = reliable_data_horizon(op, co)
    dates = pd.to_datetime(op["Fecha"], errors="coerce")

    out = op[
        dates.notna()
        & (dates >= min_date)
        & (dates <= max_date)
    ].copy()

    if "Fecha" in out.columns and not out.empty:
        out["Fecha"] = pd.to_datetime(out["Fecha"], errors="coerce").dt.normalize()
        out["Semana ISO"] = out["Fecha"].dt.isocalendar().week.astype(int)
        out["Año ISO"] = out["Fecha"].dt.isocalendar().year.astype(int)
        out["Mes"] = out["Fecha"].dt.to_period("M").astype(str)

    return out


def available_iso_weeks(op, co):
    """Devuelve pares (año ISO, semana ISO) válidos y ordenados."""
    op = reliable_operation(op, co)
    if op is None or op.empty or "Fecha" not in op.columns:
        return []

    fechas = pd.to_datetime(op["Fecha"], errors="coerce")
    valid = fechas.notna()
    if not valid.any():
        return []

    iso = fechas[valid].dt.isocalendar()
    pairs = (
        pd.DataFrame({
            "iso_year": iso["year"].astype(int).to_numpy(),
            "iso_week": iso["week"].astype(int).to_numpy(),
        })
        .drop_duplicates()
        .sort_values(["iso_year", "iso_week"])
    )

    # name=None evita que pandas cambie nombres de columnas con guion bajo
    # al convertirlas en namedtuples.
    return [(int(year), int(week)) for year, week in pairs.itertuples(index=False, name=None)]


def last_four_iso_week_ranges(op, co=None):
    """Cuatro semanas ISO consecutivas terminando en la última fecha real cargada."""
    op = reliable_operation(op, co)
    if op is None or op.empty:
        return []

    _, latest = reliable_data_horizon(op, co)
    current_monday = latest - pd.Timedelta(days=int(latest.weekday()))
    ranges = []
    for offset in [3, 2, 1, 0]:
        monday = current_monday - pd.Timedelta(weeks=offset)
        sunday = monday + pd.Timedelta(days=6)
        iso = monday.isocalendar()
        ranges.append({
            "iso_year": int(iso.year),
            "iso_week": int(iso.week),
            "start": monday,
            "end": sunday,
        })
    return ranges


def executive_week_cards(op, co):
    op = reliable_operation(op, co)
    co = normalize_commercial_df(co)
    week_ranges = last_four_iso_week_ranges(op, co)
    if not week_ranges:
        return

    html = '<div style="margin:18px 0 8px 0;font-size:24px;font-weight:900;color:#3E4095;">📊 Resumen Ejecutivo</div>'
    html += '<div class="week-card-grid">'
    prev_ing = None
    prev_hab = None
    prev_ub = None

    for wr in week_ranges:
        df = table_by_store(op, co, wr["start"], wr["end"], PROJECT_STORES)
        ingresos = float(pd.to_numeric(df["Total"], errors="coerce").fillna(0).sum())
        hab = float(pd.to_numeric(df["Habilitadas"], errors="coerce").fillna(0).sum())
        ub = float(pd.to_numeric(df["Ubicadas"], errors="coerce").fillna(0).sum())

        week_mask = (
            (pd.to_datetime(op["Fecha"], errors="coerce") >= wr["start"])
            & (pd.to_datetime(op["Fecha"], errors="coerce") <= wr["end"])
        )
        if "Actividad" in op.columns:
            actividad = op["Actividad"].map(norm_text)
            recorridos = int(
                (
                    week_mask
                    & actividad.str.contains(r"\bRECORRIDO(S)?\b", regex=True, na=False)
                ).sum()
            )
        else:
            recorridos = 0

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
            f'<div class="week-card-head">Sem {wr["iso_week"]}</div>'
            f'<div class="week-row"><span>INGRESOS</span><b>{ingresos:,.0f}</b><em style="color:{c_ing};">{d_ing}</em></div>'
            f'<div class="week-row"><span>ACONDICIONADO</span><b>{hab:,.0f}</b><em style="color:{c_hab};">{d_hab}</em></div>'
            f'<div class="week-row"><span>UBICADO</span><b>{ub:,.0f}</b><em style="color:{c_ub};">{d_ub}</em></div>'
            f'<div class="week-row"><span>RECORRIDOS</span><b>{recorridos:,.0f}</b><em>—</em></div>'
            f'</div>'
        )
        prev_ing, prev_hab, prev_ub = ingresos, hab, ub

    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)



def authorized_stores(op=None, co=None, user=None):
    """Devuelve únicamente las tiendas disponibles dentro del alcance autenticado."""
    user = user or st.session_state.get("user", {})
    frames = []
    for df in (op, co):
        if df is not None and not df.empty and "Tienda" in df.columns:
            frames.extend([canon_store(v) for v in df["Tienda"].dropna().tolist()])
    stores = sorted({s for s in frames if s})
    if stores:
        return stores
    scope_type = str(user.get("scope_type", "COMPANY")).upper()
    scope_value = str(user.get("scope_value", "")).strip()
    if scope_type in {"STORE", "REGION", "TEAM"} and scope_value:
        return sorted({canon_store(v) for v in re.split(r"[,;|]", scope_value) if canon_store(v)})
    return list(PROJECT_STORES)


def user_experience_context(user=None):
    user = user or st.session_state.get("user", {})
    role = normalize_role(user.get("role", user.get("permiso")))
    scope_type = str(user.get("scope_type", "COMPANY")).upper()
    scope_value = str(user.get("scope_value", "")).strip()
    label = {
        "OWNER": "Vista integral y estado de la plataforma",
        "ADMIN": "Administración funcional y calidad de la información",
        "DIRECTOR": "Resumen consolidado de la compañía",
        "REGIONAL": f"Resumen de las tiendas asignadas: {scope_value or 'Región'}",
        "TIENDA": f"Resumen operativo de {scope_value or 'tu tienda'}",
        "SUPERVISOR": f"Seguimiento operativo de {scope_value or 'tu equipo'}",
        "CONSULTA": "Información autorizada en modo consulta",
    }.get(role, "Información autorizada")
    return role, scope_type, scope_value, label


def recovery_executive_summary(co):
    empty = {
        "Dev Pzs": 0.0, "Piezas Recuperadas": 0.0, "% Recuperación Piezas": 0.0,
        "Valor Devolución": 0.0, "Recuperación $": 0.0, "% Recuperación $": 0.0,
        "Pendiente Pzs": 0.0, "Pendiente $": 0.0,
    }
    if co is None or co.empty:
        return empty, pd.DataFrame()
    try:
        detail, _ = cached_recovery_fifo(co)
    except Exception:
        detail, _ = recovery_fifo_engine(co)
    if detail is None or detail.empty:
        return empty, pd.DataFrame()
    dev = pd.to_numeric(detail.get("Dev Pzs", 0), errors="coerce").fillna(0).sum()
    rec_pzs = pd.to_numeric(detail.get("Piezas Recuperadas", 0), errors="coerce").fillna(0).sum()
    val_dev = pd.to_numeric(detail.get("Valor de la Devolución a Precio Neto", 0), errors="coerce").fillna(0).sum()
    rec_money = pd.to_numeric(detail.get("Recuperación $", 0), errors="coerce").fillna(0).sum()
    summary = {
        "Dev Pzs": float(dev),
        "Piezas Recuperadas": float(rec_pzs),
        "% Recuperación Piezas": float(rec_pzs / dev * 100) if dev else 0.0,
        "Valor Devolución": float(val_dev),
        "Recuperación $": float(rec_money),
        "% Recuperación $": float(rec_money / val_dev * 100) if val_dev else 0.0,
        "Pendiente Pzs": float(max(dev - rec_pzs, 0)),
        "Pendiente $": float(max(val_dev - rec_money, 0)),
    }
    return summary, detail


def render_personalized_executive_header(user, op, co):
    role, scope_type, scope_value, label = user_experience_context(user)
    name = user.get("nombre", user.get("nomina", "Usuario"))
    now = datetime.now(MX_TZ)
    greeting = _session_greeting(now)
    status = get_system_status()
    scope_display = scope_value or (
        "Compañía" if scope_type == "COMPANY" else scope_type.title()
    )

    st.markdown(
        f"""
        <div style="
            background:linear-gradient(135deg,#10245F,#244D92);
            border-radius:22px;
            padding:24px 28px;
            color:white;
            margin-bottom:18px;
            box-shadow:0 14px 35px rgba(16,36,95,.18)
        ">
          <div style="
              font-size:13px;
              font-weight:800;
              letter-spacing:.08em;
              text-transform:uppercase;
              opacity:.82
          ">
            Centro Ejecutivo · {ROLE_LABELS.get(role, role)}
          </div>
          <div style="font-size:30px;font-weight:900;margin-top:4px">
            {greeting}, {name}
          </div>
          <div style="font-size:15px;margin-top:5px;opacity:.9">{label}</div>
          <div style="
              display:flex;
              gap:18px;
              flex-wrap:wrap;
              margin-top:17px;
              font-size:13px;
              font-weight:700
          ">
            <span>📍 Alcance: {scope_display}</span>
            <span>🕒 {now.strftime('%d/%m/%Y %H:%M')}</span>
            <span>● Sistema: {
                SYSTEM_STATUS_LABELS.get(
                    status.get('status','ACTIVE'),
                    status.get('status','ACTIVE')
                )
            }</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def executive_insights(recovery_summary, recovery_detail, stores):
    messages = []
    if recovery_detail is not None and not recovery_detail.empty and "Tienda" in recovery_detail.columns:
        grouped = recovery_detail.groupby("Tienda", as_index=False).agg({
            "Dev Pzs": "sum", "Piezas Recuperadas": "sum",
            "Valor de la Devolución a Precio Neto": "sum", "Recuperación $": "sum",
        })
        grouped["% Piezas"] = grouped["Piezas Recuperadas"] / grouped["Dev Pzs"].replace(0, np.nan) * 100
        grouped["% Pesos"] = grouped["Recuperación $"] / grouped["Valor de la Devolución a Precio Neto"].replace(0, np.nan) * 100
        grouped = grouped.fillna(0)
        if not grouped.empty:
            best = grouped.sort_values("% Piezas", ascending=False).iloc[0]
            worst = grouped.sort_values("% Piezas", ascending=True).iloc[0]
            messages.append(("success", f"Mejor recuperación en piezas: {best['Tienda']} con {best['% Piezas']:.1f}%."))
            if len(grouped) > 1:
                messages.append(("warning", f"Mayor oportunidad: {worst['Tienda']} con {worst['% Piezas']:.1f}% de recuperación."))
    if recovery_summary.get("Pendiente Pzs", 0) > 0:
        messages.append(("info", f"Existen {recovery_summary['Pendiente Pzs']:,.0f} piezas pendientes dentro del periodo disponible."))
    return messages

def page_resumen(op, co):
    op = reliable_operation(op, co)
    co = normalize_commercial_df(co)
    user = st.session_state.get("user", {})
    render_personalized_executive_header(user, op, co)

    if (op is None or op.empty) and (co is None or co.empty):
        st.info("Sin información disponible dentro del alcance asignado.")
        return

    stores = authorized_stores(op, co, user)
    recovery_summary, recovery_detail = recovery_executive_summary(co)

    op_summary = {}
    table = pd.DataFrame()
    if op is not None and not op.empty:
        dates = pd.to_datetime(op["Fecha"], errors="coerce").dropna()
        if not dates.empty:
            start, end = dates.min().normalize(), dates.max().normalize()
            table = table_by_store(op, co, start, end, stores)
            op_summary = summary_from_table(table)
            st.caption(f"Información autorizada del {start.strftime('%d/%m/%Y')} al {end.strftime('%d/%m/%Y')}.")

    st.markdown("### Pulso operativo")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Recuperación piezas", fmt_pct(recovery_summary["% Recuperación Piezas"]))
    c2.metric("Recuperación económica", fmt_pct(recovery_summary["% Recuperación $"]))
    c3.metric("Pendiente piezas", fmt_num(recovery_summary["Pendiente Pzs"]))
    c4.metric("Pendiente económico", fmt_money(recovery_summary["Pendiente $"]))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Dev Pzs", fmt_num(recovery_summary["Dev Pzs"]))
    c6.metric("Piezas recuperadas", fmt_num(recovery_summary["Piezas Recuperadas"]))
    c7.metric("Valor devolución", fmt_money(recovery_summary["Valor Devolución"]))
    c8.metric("Recuperación $", fmt_money(recovery_summary["Recuperación $"]))

    pdf_summary = {
        "Perfil": ROLE_LABELS.get(normalize_role(user.get("role", user.get("permiso"))), "Consulta"),
        "Alcance": user.get("scope_value") or "Compañía",
        **recovery_summary,
    }
    pdf_table = table if table is not None and not table.empty else recovery_detail.head(200)
    generic_pdf_button(
        "Centro Ejecutivo",
        "Resumen personalizado conforme al perfil y alcance del usuario",
        pdf_table,
        pdf_summary,
        file_name="PS_Operaciones_Ropa_Centro_Ejecutivo.pdf",
        key="pdf_centro_ejecutivo_v03",
    )

    insight_col, status_col = st.columns([6.5, 3.5], gap="large")
    with insight_col:
        st.markdown("### Prioridades y hallazgos")
        insights = executive_insights(recovery_summary, recovery_detail, stores)
        if not insights:
            st.info("No se detectaron hallazgos suficientes con la información disponible.")
        for level, message in insights:
            getattr(st, level)(message)
    with status_col:
        st.markdown("### Mi alcance")
        st.write(f"**Perfil:** {ROLE_LABELS.get(normalize_role(user.get('role', user.get('permiso'))), 'Consulta')}")
        st.write(f"**Asignación:** {user.get('scope_value') or 'Compañía'}")
        st.write(f"**Tiendas visibles:** {len(stores)}")
        st.write(f"**Modo:** {SYSTEM_STATUS_LABELS.get(get_system_status().get('status','ACTIVE'),'Activo')}")

    if table is not None and not table.empty:
        panel("Resumen operativo por tienda", table, height=380)
        combined_chart(table, "Ingreso vs Acondicionado vs Ubicado — alcance autorizado")

    if recovery_detail is not None and not recovery_detail.empty:
        macro = recovery_detail.groupby("Tienda", as_index=False).agg({
            "Dev Pzs": "sum", "Piezas Recuperadas": "sum",
            "Valor de la Devolución a Precio Neto": "sum", "Recuperación $": "sum",
        })
        macro["% Recuperación Piezas"] = macro["Piezas Recuperadas"] / macro["Dev Pzs"].replace(0, np.nan) * 100
        macro["% Recuperación $"] = macro["Recuperación $"] / macro["Valor de la Devolución a Precio Neto"].replace(0, np.nan) * 100
        macro = macro.fillna(0).sort_values("% Recuperación Piezas", ascending=False)
        panel("Macro de recuperación por tienda", macro, height=390)


def page_por_dia(op, co):
    op = reliable_operation(op, co)
    co = normalize_commercial_df(co)
    st.markdown("## Por Día")
    st.caption("Ingresos, pendientes y avance por tienda.")

    if co is not None and not co.empty and "Fecha" in co.columns:
        default_date = pd.to_datetime(co["Fecha"].max()).date()
    elif op is not None and not op.empty:
        default_date = pd.to_datetime(op["Fecha"].max()).date()
    else:
        default_date = date.today()

    d = st.date_input("Fecha", value=default_date, key="dia_fecha")
    d_ts = parse_date(d)
    df = table_by_store(op, co, d_ts, d_ts, PROJECT_STORES)

    op_count = len(op[pd.to_datetime(op["Fecha"], errors="coerce").dt.normalize().eq(d_ts)]) if op is not None and not op.empty else 0
    co_dia = filter_commercial_by_date(co, d_ts, d_ts, PROJECT_STORES)
    dev_sum = co_dia["Dev_Pzs"].sum() if co_dia is not None and not co_dia.empty and "Dev_Pzs" in co_dia.columns else 0
    st.caption(f"Registros detectados: operación {op_count:,} | Dev Pzs mensual {dev_sum:,.0f}")

    resumen = summary_from_table(df)
    kpis(resumen)
    download_pdf_button("Descargar PDF", "Por Dia", f"Fecha: {pd.to_datetime(d_ts).strftime('%Y-%m-%d')}", resumen, df, key="pdf_por_dia")
    panel("Tabla por tienda - Por Día", df, height=360)
    combined_chart(df, "Ingreso vs Habilitado vs Ubicado por tienda", income_column="Ingresos periodo")


def page_semanal(op, co):
    op = reliable_operation(op, co)
    st.markdown("## Reporte Semanal")
    available_stores = authorized_stores(op, co)
    tiendas = st.multiselect("Tiendas", available_stores, default=available_stores, key="sem_tiendas")

    week_pairs = available_iso_weeks(op, co)
    if not week_pairs:
        st.info("Sin semanas válidas detectadas.")
        return

    labels = [f"{year}-Sem {week:02d}" for year, week in week_pairs]
    selected_label = st.selectbox("Semana ISO", labels, index=len(labels)-1, key="sem_iso")
    year, week = week_pairs[labels.index(selected_label)]

    dates = pd.to_datetime(op["Fecha"], errors="coerce")
    iso = dates.dt.isocalendar()
    mask = (iso.year.astype(int) == year) & (iso.week.astype(int) == week)
    week_dates = dates[mask]
    if week_dates.empty:
        st.info("Sin fechas para la semana seleccionada.")
        return

    start, end = week_dates.min().normalize(), week_dates.max().normalize()
    df = table_by_store(op, co, start, end, tiendas, carryover_mode="previous_sunday")
    resumen = summary_from_table(df, income_column="Total")
    kpis(resumen)
    st.caption("La base semanal incluye el saldo pendiente acumulado al cierre del domingo anterior.")

    generic_pdf_button(
        f"Reporte Semanal - Semana {week}",
        f"Periodo: {start.strftime('%d-%m-%Y')} al {end.strftime('%d-%m-%Y')}",
        df,
        resumen,
        file_name=f"Reporte_Semanal_Semana_{week:02d}_{year}.pdf",
        key=f"pdf_sem_{year}_{week}",
    )
    panel(f"Tabla por tienda - Semana {week}", df, height=360)
    combined_chart(df, f"Ingreso vs Habilitado vs Ubicado - Semana {week}")


def page_mensual(op, co):
    op = reliable_operation(op, co)
    st.markdown("## Reporte Mensual")
    available_stores = authorized_stores(op, co)
    tiendas = st.multiselect("Tiendas", available_stores, default=available_stores, key="mes_tiendas")
    meses = sorted(op["Mes"].dropna().unique().tolist()) if op is not None and not op.empty else []
    if not meses:
        st.info("Sin meses detectados.")
        return
    m = st.selectbox("Mes", meses, index=len(meses)-1, key="mes_select")
    dates = pd.to_datetime(op.loc[op["Mes"].eq(m), "Fecha"], errors="coerce").dropna()
    if dates.empty:
        st.info("Sin fechas para el mes seleccionado.")
        return
    start, end = dates.min().normalize(), dates.max().normalize()
    df = table_by_store(op, co, start, end, tiendas, carryover_mode="none")
    resumen = summary_from_table(df, income_column="Ingresos periodo")
    kpis(resumen)
    st.caption("Los ingresos mensuales consideran únicamente movimientos del mes; el pendiente se suma por tienda.")
    generic_pdf_button(
        f"Reporte Mensual - {m}",
        f"Periodo: {start.strftime('%d-%m-%Y')} al {end.strftime('%d-%m-%Y')}",
        df, resumen,
        file_name=f"Reporte_Mensual_{m}.pdf",
        key=f"pdf_mes_{m}",
    )
    panel(f"Tabla por tienda - Mes {m}", df, height=360)
    combined_chart(df, f"Ingreso vs Habilitado vs Ubicado - Mes {m}", income_column="Ingresos periodo")


def recovery_fifo_engine(co):
    """Motor semanal cerrado de conversión y recuperación por ID/SKU.

    Llave: Tienda + ID/SKU + Color + Año ISO + Semana ISO.
    Las ventas se asignan FIFO y únicamente si Fecha venta >= Fecha devolución.
    """
    output_columns = [
        "Tienda", "Año ISO", "Semana ISO", "ID/SKU", "Descripción", "Color",
        "Dev Pzs", "Ventas Netas Pzs", "Venta Neta $",
        "Precio Unitario Neto", "Piezas Recuperadas", "Pendiente Pzs",
        "% Rec. Pzs", "Valor de la Devolución a Precio Neto",
        "Recuperación $", "Pendiente $", "% Rec. $", "Estado Recuperación",
    ]
    if co is None or co.empty:
        return pd.DataFrame(columns=output_columns), pd.DataFrame()

    data = normalize_commercial_df(co).copy()
    for col in ["ID", "Descripción", "Color"]:
        if col not in data.columns:
            data[col] = ""
        data[col] = data[col].fillna("").astype(str).str.strip()

    data["ID"] = data["ID"].replace("", "SIN ID")
    data["Descripción"] = data["Descripción"].replace("", "Sin descripción")
    data["Color"] = data["Color"].replace("", "SIN COLOR")
    data["Dev_Pzs"] = pd.to_numeric(data["Dev_Pzs"], errors="coerce").fillna(0.0)
    data["Vta_Pzs"] = pd.to_numeric(data["Vta_Pzs"], errors="coerce").fillna(0.0)
    data["Vta_Imp"] = pd.to_numeric(data["Vta_Imp"], errors="coerce").fillna(0.0)
    data["Fecha"] = pd.to_datetime(data["Fecha"], errors="coerce").dt.normalize()

    diagnostics = []
    invalid_dates = data["Fecha"].isna()
    for _, row in data.loc[invalid_dates].head(2000).iterrows():
        diagnostics.append({
            "Alerta": "Fecha no válida",
            "Tienda": row.get("Tienda", ""),
            "ID/SKU": row.get("ID", ""),
            "Detalle": "El registro fue excluido del emparejamiento.",
        })
    data = data.loc[~invalid_dates].copy()

    negative_dev = data["Dev_Pzs"] < 0
    for _, row in data.loc[negative_dev].head(2000).iterrows():
        diagnostics.append({
            "Alerta": "Devolución negativa convertida a valor absoluto",
            "Tienda": row["Tienda"],
            "ID/SKU": row["ID"],
            "Detalle": f"Valor original: {row['Dev_Pzs']}",
        })
    data["Dev_Pzs"] = data["Dev_Pzs"].abs()
    data["Vta_Pzs"] = data["Vta_Pzs"].clip(lower=0)
    data["Vta_Imp"] = data["Vta_Imp"].clip(lower=0)

    iso = data["Fecha"].dt.isocalendar()
    data["Año ISO"] = iso.year.astype(int)
    data["Semana ISO"] = iso.week.astype(int)

    group_cols = ["Tienda", "ID", "Color", "Año ISO", "Semana ISO"]
    rows = []

    for group_key, group in data.groupby(group_cols, dropna=False, sort=False):
        tienda, item_id, color, iso_year, iso_week = group_key
        group = group.sort_values("Fecha").copy()

        dev_total = float(group["Dev_Pzs"].sum())
        sales_total = float(group["Vta_Pzs"].sum())
        net_amount = float(group["Vta_Imp"].sum())

        unit_price = net_amount / sales_total if sales_total > 0 else 0.0
        if not np.isfinite(unit_price) or unit_price < 0:
            diagnostics.append({
                "Alerta": "Precio unitario inválido",
                "Tienda": tienda,
                "ID/SKU": item_id,
                "Detalle": f"Precio calculado: {unit_price}",
            })
            unit_price = 0.0

        if dev_total > 0 and sales_total <= 0:
            diagnostics.append({
                "Alerta": "ID con devolución y sin ventas netas",
                "Tienda": tienda,
                "ID/SKU": item_id,
                "Detalle": f"{iso_year}-Sem {int(iso_week):02d}",
            })
        if dev_total > 0 and unit_price <= 0:
            diagnostics.append({
                "Alerta": "Sin precio unitario disponible",
                "Tienda": tienda,
                "ID/SKU": item_id,
                "Detalle": "Ventas Netas Pzs o Venta Neta $ sin valor válido.",
            })

        # FIFO diario: las devoluciones del día entran antes de las ventas del mismo día.
        queue = []
        recovered = 0.0
        for movement_date, day in group.groupby("Fecha", sort=True):
            day_dev = float(day["Dev_Pzs"].sum())
            day_sales = float(day["Vta_Pzs"].sum())

            if day_dev > 0:
                queue.append({"fecha": movement_date, "pendiente": day_dev})

            available_sales = day_sales
            while available_sales > 0 and queue:
                current = queue[0]
                if movement_date < current["fecha"]:
                    break
                assigned = min(available_sales, current["pendiente"])
                recovered += assigned
                available_sales -= assigned
                current["pendiente"] -= assigned
                if current["pendiente"] <= 1e-9:
                    queue.pop(0)

        recovered = min(max(recovered, 0.0), dev_total)
        pending_pieces = max(dev_total - recovered, 0.0)
        pct_pieces = min((recovered / dev_total * 100.0) if dev_total > 0 else 0.0, 100.0)

        return_value = max(unit_price * dev_total, 0.0)
        recovery_value = min(max(recovered * unit_price, 0.0), return_value)
        pending_value = max(return_value - recovery_value, 0.0)
        pct_value = min(
            (recovery_value / return_value * 100.0) if return_value > 0 else 0.0,
            100.0,
        )

        if recovered <= 0:
            state = "Sin recuperación"
        elif recovered + 1e-9 >= dev_total:
            state = "Recuperación total"
        else:
            state = "Recuperación parcial"

        description_values = (
            group["Descripción"]
            .replace("Sin descripción", np.nan)
            .dropna()
            .astype(str)
        )
        description = (
            description_values.iloc[0]
            if not description_values.empty
            else "Sin descripción"
        )

        rows.append({
            "Tienda": tienda,
            "Año ISO": int(iso_year),
            "Semana ISO": int(iso_week),
            "ID/SKU": item_id,
            "Descripción": description,
            "Color": color,
            "Dev Pzs": dev_total,
            "Ventas Netas Pzs": sales_total,
            "Venta Neta $": net_amount,
            "Precio Unitario Neto": unit_price,
            "Piezas Recuperadas": recovered,
            "Pendiente Pzs": pending_pieces,
            "% Rec. Pzs": pct_pieces,
            "Valor de la Devolución a Precio Neto": return_value,
            "Recuperación $": recovery_value,
            "Pendiente $": pending_value,
            "% Rec. $": pct_value,
            "Estado Recuperación": state,
        })

    result = pd.DataFrame(rows, columns=output_columns)

    # Validaciones finales y límites.
    if not result.empty:
        result["Piezas Recuperadas"] = np.minimum(
            result["Piezas Recuperadas"], result["Dev Pzs"]
        ).clip(lower=0)
        result["Pendiente Pzs"] = (
            result["Dev Pzs"] - result["Piezas Recuperadas"]
        ).clip(lower=0)
        result["Recuperación $"] = np.minimum(
            result["Recuperación $"],
            result["Valor de la Devolución a Precio Neto"],
        ).clip(lower=0)
        result["Pendiente $"] = (
            result["Valor de la Devolución a Precio Neto"]
            - result["Recuperación $"]
        ).clip(lower=0)
        result["% Rec. Pzs"] = result["% Rec. Pzs"].clip(0, 100)
        result["% Rec. $"] = result["% Rec. $"].clip(0, 100)

    return result, pd.DataFrame(diagnostics)


@st.cache_data(show_spinner=False)
def cached_recovery_fifo(co):
    return recovery_fifo_engine(co)


def recovery_totals(detail):
    if detail is None or detail.empty:
        return {
            "dev": 0.0, "recovered": 0.0, "pending": 0.0,
            "pct_pieces": 0.0, "return_value": 0.0,
            "recovery_value": 0.0, "pending_value": 0.0,
            "pct_value": 0.0, "stores": 0, "ids": 0,
        }
    dev = float(detail["Dev Pzs"].sum())
    recovered = float(detail["Piezas Recuperadas"].sum())
    return_value = float(detail["Valor de la Devolución a Precio Neto"].sum())
    recovery_value = float(detail["Recuperación $"].sum())
    return {
        "dev": dev,
        "recovered": recovered,
        "pending": max(dev - recovered, 0.0),
        "pct_pieces": min(recovered / dev * 100 if dev > 0 else 0.0, 100.0),
        "return_value": return_value,
        "recovery_value": recovery_value,
        "pending_value": max(return_value - recovery_value, 0.0),
        "pct_value": min(
            recovery_value / return_value * 100 if return_value > 0 else 0.0,
            100.0,
        ),
        "stores": int(detail["Tienda"].nunique()),
        "ids": int(detail["ID/SKU"].nunique()),
    }


def recovery_store_macro(detail):
    if detail is None or detail.empty:
        return pd.DataFrame()
    macro = (
        detail.groupby("Tienda", as_index=False)[[
            "Dev Pzs", "Piezas Recuperadas", "Pendiente Pzs",
            "Valor de la Devolución a Precio Neto",
            "Recuperación $", "Pendiente $",
        ]]
        .sum()
    )
    macro["% Recuperación Piezas"] = np.divide(
        macro["Piezas Recuperadas"] * 100,
        macro["Dev Pzs"],
        out=np.zeros(len(macro), dtype=float),
        where=macro["Dev Pzs"].to_numpy() > 0,
    ).clip(0, 100)
    macro["% Recuperación $"] = np.divide(
        macro["Recuperación $"] * 100,
        macro["Valor de la Devolución a Precio Neto"],
        out=np.zeros(len(macro), dtype=float),
        where=macro["Valor de la Devolución a Precio Neto"].to_numpy() > 0,
    ).clip(0, 100)
    return macro


def detail_with_total_row(detail):
    if detail is None or detail.empty:
        return detail
    totals = recovery_totals(detail)
    row = {col: "" for col in detail.columns}
    row.update({
        "Tienda": "TOTAL COMPAÑÍA",
        "ID/SKU": f"{totals['ids']:,} IDs",
        "Dev Pzs": totals["dev"],
        "Ventas Netas Pzs": detail["Ventas Netas Pzs"].sum(),
        "Venta Neta $": detail["Venta Neta $"].sum(),
        "Piezas Recuperadas": totals["recovered"],
        "Pendiente Pzs": totals["pending"],
        "% Rec. Pzs": totals["pct_pieces"],
        "Valor de la Devolución a Precio Neto": totals["return_value"],
        "Recuperación $": totals["recovery_value"],
        "Pendiente $": totals["pending_value"],
        "% Rec. $": totals["pct_value"],
    })
    return pd.concat([detail, pd.DataFrame([row])], ignore_index=True)


def recovery_exports(detail):
    csv_data = detail.to_csv(index=False).encode("utf-8-sig")
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        detail.to_excel(writer, index=False, sheet_name="Detalle por ID")
        recovery_store_macro(detail).to_excel(
            writer, index=False, sheet_name="Macro por Tienda"
        )
    return csv_data, excel_buffer.getvalue()


def render_recovery_charts(macro, key_prefix):
    if macro is None or macro.empty:
        return

    pieces = macro.sort_values("% Recuperación Piezas", ascending=False)
    fig_pieces = go.Figure()
    fig_pieces.add_bar(
        x=pieces["Tienda"], y=pieces["Dev Pzs"],
        name="Dev Pzs", marker_color=AZUL,
        text=pieces["Dev Pzs"].map(lambda x: f"{x:,.0f}"),
        textposition="outside",
    )
    fig_pieces.add_bar(
        x=pieces["Tienda"], y=pieces["Piezas Recuperadas"],
        name="Piezas Recuperadas", marker_color=ROSA,
        text=pieces["Piezas Recuperadas"].map(lambda x: f"{x:,.0f}"),
        textposition="outside",
    )
    fig_pieces.update_layout(
        title="Recuperación en piezas por tienda",
        barmode="group", height=470, margin=dict(t=70, b=90),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig_pieces, width="stretch", key=f"{key_prefix}_chart_pieces")

    money = macro.sort_values("% Recuperación $", ascending=False)
    fig_money = go.Figure()
    fig_money.add_bar(
        x=money["Tienda"],
        y=money["Valor de la Devolución a Precio Neto"],
        name="Valor Devolución", marker_color=AZUL,
        text=money["Valor de la Devolución a Precio Neto"].map(
            lambda x: f"${x:,.0f}"
        ),
        textposition="outside",
    )
    fig_money.add_bar(
        x=money["Tienda"], y=money["Recuperación $"],
        name="Recuperación $", marker_color=ROSA,
        text=money["Recuperación $"].map(lambda x: f"${x:,.0f}"),
        textposition="outside",
    )
    fig_money.update_layout(
        title="Recuperación económica por tienda",
        barmode="group", height=470, margin=dict(t=70, b=90),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig_money, width="stretch", key=f"{key_prefix}_chart_money")

    comparison = macro.sort_values("% Recuperación Piezas", ascending=False)
    fig_compare = go.Figure()
    fig_compare.add_bar(
        x=comparison["Tienda"], y=comparison["% Recuperación Piezas"],
        name="% Recuperación Piezas", marker_color=AZUL,
        text=comparison["% Recuperación Piezas"].map(lambda x: f"{x:.1f}%"),
        textposition="outside",
    )
    fig_compare.add_bar(
        x=comparison["Tienda"], y=comparison["% Recuperación $"],
        name="% Recuperación $", marker_color=ROSA,
        text=comparison["% Recuperación $"].map(lambda x: f"{x:.1f}%"),
        textposition="outside",
    )
    fig_compare.update_layout(
        title="Comparativo de recuperación: piezas contra pesos",
        barmode="group", height=440, yaxis=dict(range=[0, 110]),
        margin=dict(t=70, b=90), legend=dict(orientation="h"),
    )
    st.plotly_chart(fig_compare, width="stretch", key=f"{key_prefix}_chart_compare")


def render_recovery_enterprise(co, key_prefix, title):
    st.markdown(f"## {title}")
    st.caption(
        "Semana cerrada: misma tienda, ID/SKU, color, año ISO y semana ISO. "
        "Las ventas se asignan FIFO y su fecha debe ser igual o posterior "
        "a la devolución."
    )
    if co is None or co.empty:
        st.info("Sin información comercial.")
        return

    detail_all, diagnostics = cached_recovery_fifo(co)
    if detail_all.empty:
        st.info("No se encontraron registros válidos.")
        return

    c1, c2, c3 = st.columns([1.1, 1.4, 2.5])
    with c1:
        years = sorted(detail_all["Año ISO"].dropna().astype(int).unique())
        selected_years = st.multiselect(
            "Año ISO", years, default=years[-1:], key=f"{key_prefix}_years"
        )
    year_base = detail_all[
        detail_all["Año ISO"].isin(selected_years)
    ] if selected_years else detail_all

    with c2:
        weeks = sorted(year_base["Semana ISO"].dropna().astype(int).unique())
        selected_weeks = st.multiselect(
            "Semana ISO", weeks, default=weeks[-1:] if weeks else [],
            key=f"{key_prefix}_weeks",
        )
    with c3:
        stores = sorted(year_base["Tienda"].dropna().astype(str).unique())
        selected_stores = st.multiselect(
            "Tienda", stores, default=stores, key=f"{key_prefix}_stores"
        )

    f1, f2, f3 = st.columns([2.2, 1.5, 1.5])
    with f1:
        search = st.text_input(
            "Buscar ID/SKU o descripción",
            key=f"{key_prefix}_search",
            placeholder="Escribe ID/SKU o descripción",
        )
    with f2:
        colors_available = sorted(
            year_base["Color"].dropna().astype(str).unique()
        )
        selected_colors = st.multiselect(
            "Color", colors_available, default=[],
            key=f"{key_prefix}_colors",
            help="Vacío equivale a todos los colores.",
        )
    with f3:
        state = st.selectbox(
            "Estado de recuperación",
            ["Todos", "Sin recuperación", "Recuperación parcial", "Recuperación total"],
            key=f"{key_prefix}_state",
        )

    detail = detail_all.copy()
    if selected_years:
        detail = detail[detail["Año ISO"].isin(selected_years)]
    if selected_weeks:
        detail = detail[detail["Semana ISO"].isin(selected_weeks)]
    if selected_stores:
        detail = detail[detail["Tienda"].isin(selected_stores)]
    if selected_colors:
        detail = detail[detail["Color"].isin(selected_colors)]
    if state != "Todos":
        detail = detail[detail["Estado Recuperación"].eq(state)]
    if search:
        search_norm = norm_text(search)
        detail = detail[
            detail["ID/SKU"].map(norm_text).str.contains(search_norm, na=False)
            | detail["Descripción"].map(norm_text).str.contains(search_norm, na=False)
        ]

    if detail.empty:
        st.warning("Los filtros no encontraron información.")
        return

    totals = recovery_totals(detail)
    cards = [
        ("Total Dev Pzs", f"{totals['dev']:,.0f}"),
        ("Piezas Recuperadas", f"{totals['recovered']:,.0f}"),
        ("% Recuperación Piezas", f"{totals['pct_pieces']:.1f}%"),
        ("Valor Devolución a Precio Neto", f"${totals['return_value']:,.2f}"),
        ("Recuperación Económica", f"${totals['recovery_value']:,.2f}"),
        ("% Recuperación Económica", f"{totals['pct_value']:.1f}%"),
        ("Pendiente Pzs", f"{totals['pending']:,.0f}"),
        ("Pendiente $", f"${totals['pending_value']:,.2f}"),
        ("Tiendas analizadas", f"{totals['stores']:,}"),
        ("IDs analizados", f"{totals['ids']:,}"),
    ]
    first = st.columns(5)
    second = st.columns(5)
    for col, (label, value) in zip(first + second, cards):
        col.metric(label, value)

    macro = recovery_store_macro(detail)
    st.markdown("### Macro Ejecutivo de Recuperación por Tienda")
    ranking_view = st.segmented_control(
        "Vista",
        ["Ranking por piezas", "Ranking por pesos", "Vista comparativa"],
        default="Ranking por piezas",
        key=f"{key_prefix}_ranking_view",
    )

    if ranking_view == "Ranking por pesos":
        rank = macro.sort_values("% Recuperación $", ascending=False).copy()
        rank.insert(0, "Ranking", range(1, len(rank) + 1))
        rank = rank[[
            "Ranking", "Tienda", "Valor de la Devolución a Precio Neto",
            "Recuperación $", "Pendiente $", "% Recuperación $",
        ]]
    elif ranking_view == "Vista comparativa":
        rank = macro.sort_values("% Recuperación Piezas", ascending=False).copy()
        rank.insert(0, "Ranking", range(1, len(rank) + 1))
    else:
        rank = macro.sort_values("% Recuperación Piezas", ascending=False).copy()
        rank.insert(0, "Ranking", range(1, len(rank) + 1))
        rank = rank[[
            "Ranking", "Tienda", "Dev Pzs", "Piezas Recuperadas",
            "Pendiente Pzs", "% Recuperación Piezas",
        ]]
    panel("Ranking de recuperación", rank, height=420)

    render_recovery_charts(macro, key_prefix)

    st.markdown("### Detalle General por ID")
    display_detail = detail_with_total_row(
        detail.sort_values(
            ["Año ISO", "Semana ISO", "Tienda", "ID/SKU"],
            ascending=[False, False, True, True],
        )
    )
    csv_data, excel_data = recovery_exports(detail)
    d1, d2, d3 = st.columns([1, 1, 3])
    with d1:
        st.download_button(
            "Descargar CSV", csv_data,
            file_name="Detalle_Recuperacion_por_ID.csv",
            mime="text/csv", key=f"{key_prefix}_csv",
            width="stretch",
        )
    with d2:
        st.download_button(
            "Descargar Excel", excel_data,
            file_name="Detalle_Recuperacion_por_ID.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}_xlsx", width="stretch",
        )
    panel("Detalle General por ID", display_detail, height=560)

    with st.expander("Auditoría y calidad de datos"):
        st.metric("Alertas detectadas", len(diagnostics))
        if diagnostics is not None and not diagnostics.empty:
            st.download_button(
                "Descargar diagnóstico CSV",
                diagnostics.to_csv(index=False).encode("utf-8-sig"),
                file_name="Diagnostico_Recuperacion.csv",
                mime="text/csv", key=f"{key_prefix}_diag_csv",
            )
            panel("Detalle de alertas", diagnostics, height=380)
        else:
            st.success("No se detectaron alertas en los registros filtrados.")


def page_conversion(op, co):
    render_recovery_enterprise(
        co, "conversion_enterprise",
        "Conversión en Piezas — Recuperación Semanal por ID/SKU",
    )


def page_recuperacion(op, co):
    render_recovery_enterprise(
        co, "recovery_enterprise",
        "Recuperación Económica — Precio Neto de Venta",
    )

def page_productividad(op, co):
    st.markdown("## Productividad por colaborador")
    if op is None or op.empty:
        st.info("Sin información operativa.")
        return

    c1, c2, c3 = st.columns([1.2, 1.2, 2.6])
    with c1:
        start = st.date_input(
            "Fecha inicio",
            value=pd.to_datetime(op["Fecha"].min()).date(),
            key="prod_ini",
        )
    with c2:
        end = st.date_input(
            "Fecha final",
            value=pd.to_datetime(op["Fecha"].max()).date(),
            key="prod_fin",
        )
    with c3:
        available_stores = authorized_stores(op, co)
        tiendas = st.multiselect(
            "Tienda", available_stores, default=available_stores,
            key="prod_tiendas",
        )

    o = split_operation(op)
    o = o[
        (o["Fecha"] >= pd.to_datetime(start))
        & (o["Fecha"] <= pd.to_datetime(end))
    ]
    o = filter_stores(o, tiendas)
    name_col = "Nombre Real" if "Nombre Real" in o.columns else "Nombre"

    df = (
        o.groupby(["Tienda", name_col], as_index=False)
        .agg(
            Piezas=("Piezas", "sum"),
            Habilitadas=("Habilitadas", "sum"),
            Ubicadas=("Ubicadas", "sum"),
            Recolectadas=("Recolectadas", "sum"),
            Dias=("Fecha", "nunique"),
        )
        .rename(columns={name_col: "Colaborador"})
    )
    df["Promedio pzs/día"] = np.divide(
        df["Piezas"], df["Dias"],
        out=np.zeros(len(df), dtype=float),
        where=df["Dias"].to_numpy() > 0,
    )
    ranking = df.sort_values("Promedio pzs/día", ascending=False).reset_index(drop=True)
    ranking.insert(0, "Ranking", np.arange(1, len(ranking) + 1))

    top = ranking.head(3)[["Ranking", "Colaborador", "Tienda", "Promedio pzs/día"]]
    bottom = ranking.tail(3).sort_values("Promedio pzs/día")[
        ["Ranking", "Colaborador", "Tienda", "Promedio pzs/día"]
    ]

    left, right = st.columns(2, gap="large")
    with left:
        panel("Top 3 Colaboradores", top, height=210)
    with right:
        panel("Bottom 3 Colaboradores", bottom, height=210)

    generic_pdf_button(
        "Productividad por colaborador",
        f"Periodo: {start} al {end}",
        ranking,
        file_name="Reporte_Productividad.pdf",
        key="pdf_productividad",
    )
    panel("Ranking general", ranking, height=520)


def page_recorridos(op, co):
    st.markdown("## Recorridos")
    if op is None or op.empty:
        st.info("Sin información operativa.")
        return

    o = op[
        op["Actividad"].map(norm_text).str.contains(
            "RECORRIDO|RECOLECCION|RECOLECCIÓN", na=False
        )
    ].copy()
    if o.empty:
        st.info("No se encontraron recorridos.")
        return

    weeks = sorted(o["Semana ISO"].dropna().astype(int).unique())
    selected_week = st.selectbox(
        "Semana ISO", weeks, index=len(weeks) - 1, key="rec_week"
    )
    current = o[o["Semana ISO"].astype(int).eq(int(selected_week))]
    by_store = (
        current.groupby("Tienda", as_index=False)
        .size()
        .rename(columns={"size": "Recorridos"})
    )
    by_store["Meta"] = 47
    by_store["% Cumplimiento"] = (
        by_store["Recorridos"] / by_store["Meta"] * 100
    )

    total = float(by_store["Recorridos"].sum())
    goal = 47 * max(len(by_store), 1)
    compliance = total / goal * 100 if goal else 0
    average = total / max(len(by_store), 1)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Meta semanal", "47")
    c2.metric("Recorridos realizados", f"{total:,.0f}")
    c3.metric("Cumplimiento", f"{compliance:.1f}%")
    c4.metric("Promedio por tienda", f"{average:.1f}")

    left, right = st.columns(2, gap="large")
    with left:
        fig = go.Figure()
        ranked = by_store.sort_values("% Cumplimiento", ascending=True)
        fig.add_bar(
            y=ranked["Tienda"],
            x=ranked["% Cumplimiento"],
            orientation="h",
            marker_color="#3366CC",
            text=ranked["% Cumplimiento"].map(lambda x: f"{x:.1f}%"),
            textposition="outside",
        )
        fig.add_vline(x=100, line_dash="dash", line_color="#FF6B6B")
        fig.update_layout(
            title="Cumplimiento de recorridos por tienda",
            height=430,
            margin=dict(l=20, r=55, t=65, b=30),
            xaxis_title="% Cumplimiento",
        )
        st.plotly_chart(fig, width="stretch")
    with right:
        by_day = (
            current.groupby(current["Fecha"].dt.day_name(), as_index=False)
            .size().rename(columns={"size": "Realizados", "Fecha": "Día"})
        )
        fig2 = go.Figure()
        fig2.add_bar(
            x=by_day["Día"], y=by_day["Realizados"],
            marker_color="#3366CC",
            text=by_day["Realizados"],
            textposition="outside",
            name="Realizados",
        )
        fig2.add_scatter(
            x=by_day["Día"], y=[47 / 7] * len(by_day),
            mode="lines", line=dict(color="#FF6B6B", dash="dash"),
            name="Meta diaria",
        )
        fig2.update_layout(
            title="Recorridos realizados vs meta",
            height=430,
            margin=dict(l=20, r=20, t=65, b=30),
        )
        st.plotly_chart(fig2, width="stretch")

    generic_pdf_button(
        "Recorridos", f"Semana ISO {selected_week}", by_store,
        file_name="Reporte_Recorridos.pdf", key="pdf_recorridos",
    )
    panel("Detalle de recorridos por tienda", by_store, height=360)


def page_ranking(op, co):
    st.markdown("## Ranking")
    if op.empty:
        return
    o = split_operation(op)
    df = o.groupby("Tienda", as_index=False).agg({"Piezas":"sum", "Habilitadas":"sum", "Ubicadas":"sum"})
    df["Score"] = (df["Habilitadas"] + df["Ubicadas"]) / df["Piezas"].replace(0, np.nan) * 100
    df["Score"] = df["Score"].fillna(0)
    df_rank = df.sort_values("Score", ascending=False)
    generic_pdf_button("Ranking de tiendas", "Clasificación por score", df_rank, file_name="Reporte_Ranking.pdf", key="pdf_ranking")
    panel("Ranking de tiendas", df_rank, height=420)


def page_macro(op, co):
    render_recovery_enterprise(
        co, "macro_recovery_enterprise",
        "Macro Ejecutivo de Recuperación por Tienda",
    )


def page_diagnostico(op, co, diag):
    st.markdown("## Diagnóstico")
    st.info("Homologación v10.13: acepta encabezado Tienda/Tiendas; Guadalajara Miravalle/Miravalle => Miravalle; Guadalajara/Guadalajara Atemajac/Atemajac => Atemajac.")
    st.info("Homologación v10.12: Guadalajara Miravalle/Miravalle => Miravalle; Guadalajara/Guadalajara Atemajac/Atemajac => Atemajac.")
    st.write(f"Operación: {len(op):,} registros")
    st.write(f"Comercial mensual por ID: {len(co):,} registros agrupados | Dev Pzs total: {co['Dev_Pzs'].sum() if not co.empty else 0:,.0f}")
    if diag is not None and not diag.empty and "Tipo" in diag.columns:
        diag_op = diag[diag["Tipo"].astype(str).str.contains("Histórica|Nueva|Consolidado", case=False, na=False)]
        if not diag_op.empty:
            panel("Diagnóstico operativo — unión de hojas", diag_op, height=260)
    panel("Diagnóstico de hojas", diag, height=420)
    if not co.empty:
        _enterprise_detail, _enterprise_diag = cached_recovery_fifo(co)
        st.write(
            f"Motor FIFO: {_enterprise_detail['ID/SKU'].nunique() if not _enterprise_detail.empty else 0:,} IDs | "
            f"{len(_enterprise_diag):,} alertas de calidad"
        )
        if _enterprise_diag is not None and not _enterprise_diag.empty:
            panel("Diagnóstico financiero FIFO", _enterprise_diag, height=360)
        _co_diag = normalize_commercial_df(co)
        dev_diag = (
            _co_diag.groupby(["Fecha", "Tienda"], as_index=False)[["Dev_Pzs", "Vta_Pzs", "Vta_Imp"]]
            .sum()
            .sort_values(["Fecha", "Tienda"])
        )
        dev_diag["Fecha"] = pd.to_datetime(dev_diag["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
        panel("Validación Comercial por fecha y tienda", dev_diag.tail(300), height=520)
        ecatepec_2806 = dev_diag[(dev_diag["Tienda"].eq("Ecatepec")) & (dev_diag["Fecha"].eq(pd.Timestamp("2026-06-28")))]
        if not ecatepec_2806.empty:
            st.success(f"Validación Ecatepec 28/06/2026 Dev Pzs: {ecatepec_2806['Dev_Pzs'].sum():,.0f}")



def page_configuracion():
    st.markdown("## Configuración")
    if not is_admin():
        st.warning("Acceso exclusivo para Administración.")
        return
    if not can_write():
        st.warning("Modo Solo consulta: la configuración no puede modificarse.")
    st.info("Configuración de metas y orden de pestañas en preparación modular.")
    st.write("Meta productividad diaria: 784")
    st.write("Meta recorridos semanal: 47")


def page_usuarios():
    st.markdown("## Usuarios y alcances")
    if not is_admin():
        st.warning("Acceso exclusivo para Administración.")
        return

    role_options = ROLES if is_owner() else [r for r in ROLES if r != "OWNER"]
    with st.form("crear_usuario"):
        st.subheader("Crear / actualizar usuario")
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nómina / Usuario")
            nombre = st.text_input("Nombre")
            correo = st.text_input("Correo")
            role = st.selectbox("Perfil", role_options, format_func=lambda x: ROLE_LABELS.get(x, x))
        with c2:
            scope_type = st.selectbox("Tipo de alcance", ["COMPANY", "REGION", "STORE", "TEAM"])
            scope_value = st.text_input("Asignación", help="Para varias tiendas usa comas, por ejemplo: Toluca, Vallejo")
            pwd = st.text_input("Contraseña temporal", type="password")
        submitted = st.form_submit_button("Guardar usuario", type="primary")
        if submitted and nom and nombre and pwd:
            try:
                upsert_user(nom, nombre, role, pwd, correo, scope_type, scope_value)
                st.success("Usuario guardado. Se recomienda cambiar la contraseña en el primer acceso.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    panel("Usuarios registrados", list_users(), height=420)
    del_nom = st.text_input("Nómina a eliminar")
    if st.button("Eliminar usuario", disabled=not can_write()) and del_nom:
        try:
            delete_user(del_nom); st.success("Usuario eliminado."); st.rerun()
        except Exception as exc:
            st.error(str(exc))


def page_centro_control():
    st.markdown("## Centro de Control del Sistema")
    if not is_owner():
        st.error("Acceso exclusivo para el Propietario del Sistema.")
        return
    current = get_system_status()
    st.info(f"Estado actual: **{SYSTEM_STATUS_LABELS.get(current['status'], current['status'])}**")
    if current.get("changed_at"):
        st.caption(f"Último cambio: {current['changed_at']} · {current.get('changed_by','')}")
    with st.form("system_control_form"):
        status = st.selectbox("Nuevo estado", SYSTEM_STATUSES, index=SYSTEM_STATUSES.index(current.get("status", "ACTIVE")), format_func=lambda x: SYSTEM_STATUS_LABELS.get(x, x))
        justification = st.text_area("Justificación obligatoria", placeholder="Describe el motivo del cambio (mínimo 10 caracteres).")
        submitted = st.form_submit_button("Aplicar estado", type="primary")
    if submitted:
        try:
            set_system_status(status, justification)
            st.success("Estado actualizado y registrado en auditoría.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    con = sqlite3.connect(DB_FILE)
    logs = pd.read_sql_query("SELECT creado AS Fecha,usuario AS Usuario,accion AS Acción,modulo AS Módulo,detalle AS Detalle FROM audit_logs ORDER BY id DESC LIMIT 200", con)
    con.close()
    panel("Auditoría reciente", logs, height=420)


# ============================================================
# MAIN
# ============================================================
apply_styles()


# V20X.4 — layout nativo estable, sin parches acumulados
st.markdown(
    """
    <style>
    :root{
      --ps-sidebar-width:292px;
      --ps-header-height:76px;
    }

    html,body,[data-testid="stAppViewContainer"]{
      overflow-x:hidden!important;
      background:#F2F4F7!important;
    }

    /* Layout principal en flex: el sidebar reserva su espacio y nunca cubre el reporte. */
    [data-testid="stAppViewContainer"]{
      display:flex!important;
      align-items:stretch!important;
      width:100%!important;
      min-height:100vh!important;
    }

    [data-testid="stSidebar"]{
      position:relative!important;
      inset:auto!important;
      flex:0 0 var(--ps-sidebar-width)!important;
      width:var(--ps-sidebar-width)!important;
      min-width:var(--ps-sidebar-width)!important;
      max-width:var(--ps-sidebar-width)!important;
      height:100vh!important;
      transform:none!important;
      background:linear-gradient(180deg,#0A3067,#173B73)!important;
      overflow:hidden!important;
      z-index:20!important;
    }

    [data-testid="stSidebar"] > div:first-child{
      position:sticky!important;
      top:0!important;
      width:100%!important;
      height:100vh!important;
      overflow-y:auto!important;
      overflow-x:hidden!important;
      box-sizing:border-box!important;
    }

    [data-testid="stMain"]{
      position:relative!important;
      flex:1 1 0!important;
      width:0!important;
      min-width:0!important;
      max-width:none!important;
      margin:0!important;
      padding:0!important;
      overflow-x:hidden!important;
    }

    [data-testid="stMainBlockContainer"],
    [data-testid="stAppViewBlockContainer"],
    .block-container{
      width:100%!important;
      max-width:100%!important;
      min-width:0!important;
      margin:0!important;
      padding:22px clamp(16px,2.2vw,34px) 48px!important;
      box-sizing:border-box!important;
      overflow-x:hidden!important;
    }

    /* Header corporativo dentro del flujo del reporte: fijo visualmente, sin cálculos laterales. */
    .v20-header{
      position:sticky!important;
      top:0!important;
      left:auto!important;
      right:auto!important;
      width:100%!important;
      max-width:100%!important;
      height:var(--ps-header-height)!important;
      padding:0 clamp(18px,2.2vw,32px)!important;
      box-sizing:border-box!important;
      z-index:15!important;
    }

    /* El contenido empieza debajo del header sticky, sin padding artificial acumulado. */
    [data-testid="stMain"]{
      padding-top:0!important;
    }

    [data-testid="stHorizontalBlock"]{
      width:100%!important;
      max-width:100%!important;
      min-width:0!important;
      align-items:stretch!important;
    }
    [data-testid="stColumn"]{
      min-width:0!important;
      max-width:100%!important;
      box-sizing:border-box!important;
      overflow:hidden!important;
    }
    [data-testid="stColumn"] > div{
      min-width:0!important;
      max-width:100%!important;
    }

    [data-testid="stDataFrame"],
    [data-testid="stPlotlyChart"],
    [data-testid="stFileUploader"]{
      width:100%!important;
      max-width:100%!important;
      min-width:0!important;
      box-sizing:border-box!important;
    }

    button[kind="primary"],button[kind="secondary"]{
      max-width:100%!important;
      box-sizing:border-box!important;
    }

    .ps-kpi-grid{
      display:grid!important;
      grid-template-columns:repeat(5,minmax(0,1fr))!important;
      gap:12px!important;
      width:100%!important;
      max-width:100%!important;
    }
    .ps-kpi-card{
      width:100%!important;
      min-width:0!important;
      overflow:hidden!important;
      box-sizing:border-box!important;
    }
    .ps-kpi-card > div:last-child{min-width:0!important;overflow:hidden!important;}
    .ps-kpi-title,.ps-kpi-sub{overflow-wrap:anywhere!important;}
    .ps-kpi-value{white-space:nowrap!important;font-size:clamp(20px,1.6vw,28px)!important;}

    /* Se mantiene visible el control nativo si el usuario contrae el menú. */
    header[data-testid="stHeader"]{
      display:block!important;
      visibility:visible!important;
      background:transparent!important;
      height:0!important;
      min-height:0!important;
      z-index:100!important;
    }
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapsedControl"]{
      display:flex!important;
      visibility:visible!important;
      opacity:1!important;
      position:fixed!important;
      top:14px!important;
      left:14px!important;
      width:44px!important;
      height:44px!important;
      border-radius:10px!important;
      background:#173B73!important;
      color:#fff!important;
      z-index:1000!important;
    }

    @media (max-width:1250px){
      .ps-kpi-grid{grid-template-columns:repeat(3,minmax(0,1fr))!important;}
    }

    @media (max-width:900px){
      :root{--ps-sidebar-width:276px;--ps-header-height:68px;}
      [data-testid="stAppViewContainer"]{display:block!important;}
      [data-testid="stSidebar"]{
        position:fixed!important;
        top:0!important;
        left:0!important;
        bottom:0!important;
        width:var(--ps-sidebar-width)!important;
        min-width:var(--ps-sidebar-width)!important;
        max-width:var(--ps-sidebar-width)!important;
        transform:translateX(-100%);
        z-index:1000!important;
      }
      [data-testid="stSidebar"][aria-expanded="true"],
      [data-testid="stSidebar"][data-state="expanded"]{
        transform:translateX(0)!important;
      }
      [data-testid="stMain"]{
        width:100%!important;
        min-width:0!important;
        margin:0!important;
      }
      .v20-header{
        padding-left:64px!important;
      }
      [data-testid="stMainBlockContainer"],.block-container{
        padding:14px 10px 38px!important;
      }
      [data-testid="stHorizontalBlock"]{
        flex-wrap:wrap!important;
        gap:10px!important;
      }
      [data-testid="stColumn"]{
        flex:1 1 100%!important;
        width:100%!important;
        min-width:100%!important;
      }
      .ps-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:10px!important;}
    }

    @media (max-width:520px){
      .ps-kpi-grid{grid-template-columns:1fr!important;}
      .v20-header-brand span{display:none!important;}
      .v20-header-account-copy small{display:none!important;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)



st.markdown(
    """
    <style>
    /* V21: restauración del layout nativo */
    [data-testid="stAppViewContainer"]{display:block!important;overflow:visible!important;}
    [data-testid="stSidebar"]{
      position:fixed!important;left:0!important;top:0!important;bottom:0!important;
      width:300px!important;min-width:300px!important;max-width:300px!important;
      transform:none!important;visibility:visible!important;opacity:1!important;
      background:#173B73!important;z-index:999!important;
    }
    [data-testid="stSidebar"] > div:first-child{padding:28px 16px 24px!important;overflow-y:auto!important;}
    [data-testid="stSidebar"] *{visibility:visible!important;opacity:1!important;}
    [data-testid="stSidebar"] [role="radiogroup"] label p{color:#fff!important;font-weight:650!important;}
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){background:#3366CC!important;border-radius:10px!important;}
    [data-testid="stMain"]{margin-left:300px!important;width:calc(100% - 300px)!important;max-width:calc(100% - 300px)!important;}
    [data-testid="stMainBlockContainer"],.block-container{
      width:100%!important;max-width:100%!important;padding:24px 30px 48px!important;
      opacity:1!important;visibility:visible!important;filter:none!important;overflow-x:hidden!important;
    }
    [data-testid="stMainBlockContainer"] > div{opacity:1!important;visibility:visible!important;}
    .v20-header{display:none!important;}
    .v21-header-brand{display:flex;align-items:center;gap:16px;min-height:72px;}
    .v21-header-brand img{width:105px;height:58px;object-fit:contain;}
    .v21-header-brand span{font-size:22px;font-weight:800;color:#173B73;}
    [data-testid="stHorizontalBlock"]{width:100%!important;max-width:100%!important;gap:16px!important;}
    [data-testid="stColumn"]{min-width:0!important;max-width:100%!important;}
    [data-testid="stDataFrame"],[data-testid="stPlotlyChart"]{width:100%!important;max-width:100%!important;}
    button{max-width:100%!important;}
    @media(max-width:900px){
      [data-testid="stSidebar"]{width:278px!important;min-width:278px!important;max-width:278px!important;transform:translateX(-100%)!important;}
      [data-testid="stSidebar"][aria-expanded="true"],[data-testid="stSidebar"][data-state="expanded"]{transform:translateX(0)!important;}
      [data-testid="stMain"]{margin-left:0!important;width:100%!important;max-width:100%!important;}
      [data-testid="collapsedControl"],[data-testid="stSidebarCollapsedControl"]{display:flex!important;visibility:visible!important;opacity:1!important;position:fixed!important;top:12px!important;left:12px!important;z-index:1200!important;background:#173B73!important;border-radius:10px!important;}
      [data-testid="stMainBlockContainer"],.block-container{padding:14px 12px 40px!important;}
      .v21-header-brand{padding-left:48px;}
      .v21-header-brand img{width:82px;height:48px;}
      .v21-header-brand span{font-size:18px;}
      [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;}
      [data-testid="stColumn"]{flex:1 1 100%!important;width:100%!important;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


if not login_sidebar():
    st.stop()

if "active_app" not in st.session_state:
    st.session_state["active_app"] = None
if "portal_view" not in st.session_state:
    st.session_state["portal_view"] = "apps"

if not st.session_state.get("active_app"):
    if st.session_state.get("portal_view") == "admin":
        page_portal_admin()
    else:
        render_app_portal()
    st.stop()

render_header()
page = nav_bar()

DATA_PAGES = {
    "Centro Ejecutivo",
    "Operación Diaria",
    "Reporte Semanal",
    "Reporte Mensual",
    "Productividad",
    "Recuperación",
    "Recorridos",
    "Reportes",
    "Detalle por Tienda",
    "Detalle por Colaborador",
    "Alertas Inteligentes",
    "Inteligencia Operativa",
}

op_all = pd.DataFrame()
co_all = pd.DataFrame()
diag_df = pd.DataFrame()

needs_data = page in DATA_PAGES

if needs_data:
    if ACTIVE_FILE.exists() and cache_valid():
        with st.spinner("Consultando el periodo requerido..."):
            op_all, co_all, diag_df = load_data_for_page(
                page,
                ACTIVE_FILE.stat().st_mtime,
            )
            op_all = apply_user_scope(op_all)
            co_all = apply_user_scope(co_all)
    else:
        if not ACTIVE_FILE.exists():
            st.warning(
                "No hay un archivo activo. Abre **Carga de Excel** para seleccionar, "
                "guardar y procesar la fuente de datos."
            )
        else:
            st.warning(
                "El archivo está guardado, pero todavía no está procesado. "
                "Abre **Carga de Excel** y continúa con el procesamiento por etapas."
            )

elif page == "Diagnóstico del Archivo":
    if ACTIVE_FILE.exists() and cache_valid():
        diag_df = read_diag_cache(ACTIVE_FILE.stat().st_mtime)

_system = get_system_status()
if _system["status"] in {"MAINTENANCE", "SUSPENDED"} and not is_owner():
    st.error(_system.get("maintenance_text") or "PS Operaciones Ropa no está disponible temporalmente.")
    st.stop()
if _system["status"] == "READ_ONLY":
    st.warning("La plataforma se encuentra en modo Solo consulta. Las acciones de modificación están bloqueadas.")

def _v17_title(title, subtitle=""):
    st.markdown(f"## {title}")
    if subtitle:
        st.caption(subtitle)


def page_reportes(op, co):
    _v17_title("Centro de Reportes", "Consulta, genera y descarga reportes operativos.")
    c1, c2, c3 = st.columns([2.2, 1.2, 1.2])
    with c1:
        search = st.text_input("Buscar reporte", placeholder="Nombre del reporte")
    with c2:
        format_sel = st.selectbox("Formato", ["Todos", "PDF", "Excel", "CSV"])
    with c3:
        period_sel = st.selectbox("Periodo", ["Todos", "Diario", "Semanal", "Mensual"])

    rows = [
        ["Centro Ejecutivo", "PDF", "Semanal", "Indicadores principales y alertas"],
        ["Operación Diaria", "PDF", "Diario", "Ingresos, acondicionado, ubicado y pendientes"],
        ["Reporte Semanal", "Excel", "Semanal", "Comparativo de cuatro semanas"],
        ["Reporte Mensual", "PDF", "Mensual", "Comparativo e histórico mensual"],
        ["Productividad", "Excel", "Semanal", "Ranking de colaboradores y tiendas"],
        ["Recuperación", "Excel", "Semanal", "Conversión FIFO y recuperación económica"],
        ["Recorridos", "PDF", "Semanal", "Cumplimiento y ranking por tienda"],
    ]
    df = pd.DataFrame(rows, columns=["Reporte", "Formato", "Periodo", "Descripción"])
    if search:
        df = df[df["Reporte"].str.contains(search, case=False, na=False)]
    if format_sel != "Todos":
        df = df[df["Formato"].eq(format_sel)]
    if period_sel != "Todos":
        df = df[df["Periodo"].eq(period_sel)]
    panel("Reportes disponibles", df, height=390)


def page_administracion_v17():
    _v17_title("Administración", "Usuarios, roles, permisos, tiendas y regiones.")
    tab1, tab2, tab3, tab4 = st.tabs(["Usuarios", "Roles y permisos", "Tiendas", "Regiones"])
    with tab1:
        page_usuarios()
    with tab2:
        roles = pd.DataFrame([
            ["Propietario", "Control total del sistema", "Activo"],
            ["Administrador", "Carga, configuración y reportes", "Activo"],
            ["Consulta", "Visualización y descargas autorizadas", "Activo"],
        ], columns=["Rol", "Alcance", "Estado"])
        panel("Roles configurados", roles, height=260)
    with tab3:
        tiendas = pd.DataFrame({"Tienda": STORES, "Estado": "Activa"})
        panel("Catálogo de tiendas", tiendas, height=420)
    with tab4:
        regions = pd.DataFrame([
            ["Centro", "Centro, Iztapalapa, Vallejo, Ecatepec, Naucalpan"],
            ["Occidente", "León, Aguascalientes, Miravalle, Atemajac"],
            ["Bajío", "Toluca, Querétaro, Arco Norte"],
            ["Golfo", "Veracruz, Puebla, Puebla Sur"],
        ], columns=["Región", "Tiendas"])
        panel("Regiones operativas", regions, height=300)


def page_configuracion_metas_v17():
    _v17_title("Configuración de Metas", "Parámetros operativos editables por administrador.")
    metas_file = CONFIG_DIR / "metas.json"
    try:
        metas = json.loads(metas_file.read_text(encoding="utf-8")) if metas_file.exists() else {}
    except Exception:
        metas = {}
    t1, t2, t3, t4 = st.tabs(["Productividad", "Recorridos", "Conversión", "Recuperación"])
    with t1:
        productividad = st.number_input("Meta productividad diaria", min_value=1, value=int(metas.get("productividad", 784)))
    with t2:
        cols = st.columns(7)
        defaults = [5, 5, 5, 8, 8, 8, 8]
        days = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        rec = {}
        for col, day, default in zip(cols, days, defaults):
            with col:
                rec[day] = st.number_input(day, min_value=0, value=int(metas.get("recorridos", {}).get(day, default)), key=f"goal_{day}")
        st.metric("Meta semanal total", sum(rec.values()))
    with t3:
        conversion = st.number_input("Meta conversión misma semana ISO (%)", min_value=0.0, max_value=100.0, value=float(metas.get("conversion", 30.0)))
    with t4:
        recovery = st.number_input("Meta recuperación económica (%)", min_value=0.0, value=float(metas.get("recuperacion", 100.0)))
    if st.button("Guardar cambios", type="primary"):
        metas_file.write_text(json.dumps({
            "productividad": productividad,
            "recorridos": rec,
            "conversion": conversion,
            "recuperacion": recovery,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        st.success("Metas guardadas correctamente.")



def page_carga_excel_v17():
    """Carga y procesamiento por etapas con layout estable para PC y móvil."""
    _v17_title(
        "Carga de Excel",
        "Procesa el archivo por etapas para evitar reinicios por memoria.",
    )

    user = st.session_state.get("user", {})
    if not is_admin(user):
        st.error("Esta función está disponible únicamente para Administrador o Propietario.")
        return

    meta = {}
    if META_FILE.exists():
        try:
            meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception:
            meta = {}

    stage_state = read_staged_state()

    st.markdown('<div class="admin-section-title">Estado de la fuente</div>', unsafe_allow_html=True)
    state_cols = st.columns(3, gap="medium")

    with state_cols[0]:
        if ACTIVE_FILE.exists():
            st.success("Archivo guardado")
            st.markdown(f"**Nombre:** {meta.get('nombre_original', ACTIVE_FILE.name)}")
            st.caption(f"Tamaño: {ACTIVE_FILE.stat().st_size / (1024 * 1024):,.1f} MB")
        else:
            st.info("Todavía no hay un archivo cargado.")

    with state_cols[1]:
        if ACTIVE_FILE.exists() and cache_valid():
            st.success("Procesado y disponible")
            st.caption("Los reportes pueden consultarse.")
        elif ACTIVE_FILE.exists():
            st.warning("Procesamiento pendiente o incompleto")
            st.markdown(f"**Etapa:** {stage_state.get('step', 'initialize')}")
        else:
            st.info("Esperando archivo")

    with state_cols[2]:
        progress_value = staged_progress_percent(stage_state) if ACTIVE_FILE.exists() else 0
        st.metric("Avance acumulado", f"{progress_value}%")
        if ACTIVE_FILE.exists() and not cache_valid():
            st.progress(progress_value / 100)
            st.caption(stage_state.get("message", "Listo para iniciar."))

    st.markdown('<div class="admin-section-title">Archivo y procesamiento por etapas</div>', unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Selecciona un archivo Excel",
        type=["xlsx"],
        key="v20x4_excel_uploader",
        help="Al guardar un archivo diferente se reinician las etapas.",
    )

    if uploaded is not None:
        st.info(f"Seleccionado: **{uploaded.name}** · {uploaded.size / (1024 * 1024):,.1f} MB")

    action_cols = st.columns(2, gap="medium")
    with action_cols[0]:
        if st.button(
            "1. Guardar archivo",
            key="v20x4_save_excel",
            type="primary",
            width="stretch",
            disabled=uploaded is None or not can_write(),
        ):
            try:
                result = save_uploaded_file(uploaded)
                if not result.get("same_content", False):
                    clear_staged_processing()
                append_file_history("Carga", uploaded.name, "Guardado", "Archivo guardado para procesamiento por etapas")
                st.success("Archivo guardado correctamente.")
                st.rerun()
            except Exception as exc:
                st.error("No fue posible guardar el archivo.")
                st.exception(exc)

    with action_cols[1]:
        if cache_valid():
            process_label = "Información procesada"
        elif stage_state.get("status") == "idle":
            process_label = "2. Preparar procesamiento"
        elif stage_state.get("step") == "finalize":
            process_label = "2. Consolidar información"
        else:
            process_label = "2. Procesar siguiente etapa"

        if st.button(
            process_label,
            key="v20x4_process_next",
            type="primary",
            width="stretch",
            disabled=(not ACTIVE_FILE.exists() or not can_write() or cache_valid()),
        ):
            try:
                with st.status("Ejecutando solamente una etapa...", expanded=True) as status_box:
                    previous = read_staged_state()
                    status_box.write(previous.get("message", "Preparando etapa."))
                    result = process_next_stage(str(ACTIVE_FILE))
                    status_box.write(result.get("message", "Etapa terminada."))
                    status_box.update(
                        label=("Procesamiento completo." if result.get("status") == "complete" else "Etapa terminada. Continúa con la siguiente."),
                        state="complete",
                        expanded=False,
                    )

                if result.get("status") == "complete" and cache_valid():
                    append_file_history("Proceso", meta.get("nombre_original", ACTIVE_FILE.name), "Procesado", "Archivo procesado por etapas correctamente")
                    st.success("La información ya está disponible en todos los reportes.")
                    st.session_state["nav_page"] = "Centro Ejecutivo"
                else:
                    st.success("La etapa terminó y quedó guardada. Presiona nuevamente para continuar.")
                st.rerun()
            except Exception as exc:
                st.error("La etapa no terminó, pero las etapas anteriores se conservaron.")
                if PROCESS_LOG_FILE.exists():
                    st.code(PROCESS_LOG_FILE.read_text(encoding="utf-8", errors="replace")[-6000:], language="text")
                else:
                    st.exception(exc)

    with st.expander("Flujo recomendado", expanded=False):
        st.markdown("""
        1. Selecciona y guarda el archivo una sola vez.  
        2. Presiona **Procesar siguiente etapa**.  
        3. Cada ejecución procesa una hoja o bloque y libera memoria.  
        4. Si Streamlit se reinicia, continúa desde la última etapa guardada.  
        5. La última etapa consolida los reportes.
        """)

    if ACTIVE_FILE.exists() and not cache_valid():
        if st.button("Reiniciar etapas", key="v20x4_restart_stages", width="stretch", disabled=not can_write()):
            clear_staged_processing()
            clear_process_status()
            st.success("Se reinició el avance por etapas.")
            st.rerun()

    if ACTIVE_FILE.exists():
        st.divider()
        if st.button("Eliminar archivo activo", key="v20x4_delete_active", width="stretch", disabled=not can_write()):
            file_name = meta.get("nombre_original", ACTIVE_FILE.name)
            delete_active_file()
            clear_staged_processing()
            append_file_history("Eliminación", file_name, "Eliminado", "Archivo activo eliminado")
            st.success("Archivo activo eliminado.")
            st.rerun()


def page_diagnostico_archivo_v17(op, co, diag):
    _v17_title("Diagnóstico del Archivo", "Validaciones, errores, advertencias y vista previa.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registros operación", f"{len(op):,}" if op is not None else "0")
    c2.metric("Registros comerciales", f"{len(co):,}" if co is not None else "0")
    c3.metric("Alertas detectadas", f"{len(diag):,}" if diag is not None else "0")
    c4.metric("Estado general", "Válido" if diag is not None else "Pendiente")
    page_diagnostico(op, co, diag)


def page_detalle_tienda_v17(op, co):
    _v17_title("Detalle por Tienda", "KPIs, evolución, actividades e histórico.")
    stores = authorized_stores(op, co)
    store = st.selectbox("Tienda", stores)
    o = filter_stores(op, [store]) if op is not None else pd.DataFrame()
    if o.empty:
        st.info("Sin información para la tienda seleccionada.")
        return
    split = split_operation(o)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Piezas procesadas", f"{split['Piezas'].sum():,.0f}")
    c2.metric("Acondicionado", f"{split['Habilitadas'].sum():,.0f}")
    c3.metric("Ubicado", f"{split['Ubicadas'].sum():,.0f}")
    c4.metric("Recorridos", f"{split['Recorridos'].sum():,.0f}")
    daily = split.groupby("Fecha", as_index=False)[["Piezas", "Habilitadas", "Ubicadas"]].sum()
    fig = go.Figure()
    for col, color in [("Piezas", "#3366CC"), ("Habilitadas", "#A26BFF"), ("Ubicadas", "#FF6FB5")]:
        fig.add_scatter(x=daily["Fecha"], y=daily[col], mode="lines+markers", name=col, line=dict(color=color))
    fig.update_layout(title="Evolución diaria", height=400)
    st.plotly_chart(fig, width="stretch")
    panel("Detalle operativo", split.tail(500), height=430)


def page_detalle_colaborador_v17(op, co):
    _v17_title("Detalle por Colaborador", "Productividad, actividades, recorridos e histórico.")
    if op is None or op.empty:
        st.info("Sin información.")
        return
    name_col = "Nombre Real" if "Nombre Real" in op.columns else "Nombre"
    names = sorted(op[name_col].dropna().astype(str).unique())
    selected = st.selectbox("Colaborador", names)
    o = op[op[name_col].astype(str).eq(selected)].copy()
    split = split_operation(o)
    initials = "".join([w[0].upper() for w in selected.split()[:2]])
    st.markdown(f'<div class="employee-avatar">{initials}</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Productividad", f"{split['Piezas'].sum():,.0f}")
    c2.metric("Días trabajados", f"{split['Fecha'].nunique():,}")
    c3.metric("Promedio pzs/día", f"{split['Piezas'].sum()/max(split['Fecha'].nunique(),1):,.0f}")
    c4.metric("Recorridos", f"{split['Recorridos'].sum():,.0f}")
    by_activity = split.groupby("Actividad", as_index=False)["Piezas"].sum().sort_values("Piezas", ascending=False)
    panel("Actividades realizadas", by_activity, height=330)
    panel("Histórico del colaborador", split.sort_values("Fecha", ascending=False), height=420)


def page_historico_descargas_v17():
    _v17_title("Histórico de Descargas", "Trazabilidad de reportes generados por usuario.")
    history_file = CONFIG_DIR / "descargas.json"
    try:
        rows = json.loads(history_file.read_text(encoding="utf-8")) if history_file.exists() else []
    except Exception:
        rows = []
    if not rows:
        st.info("Aún no existen descargas registradas para el alcance actual.")
        return
    panel("Descargas registradas", pd.DataFrame(rows), height=440)


def page_alertas_inteligentes_v17(op, co):
    _v17_title("Alertas Inteligentes", "Alertas calculadas desde datos reales y alcance autorizado.")
    if op is None or op.empty:
        st.info("Sin información operativa para calcular alertas.")
        return
    try:
        table = operational_table(op, sorted(op["Tienda"].dropna().astype(str).unique()))
        from services.alerts import generate
        alerts = generate(table)
    except Exception as exc:
        st.warning(f"No fue posible calcular alertas: {exc}")
        return
    if alerts.empty:
        st.success("No se detectaron indicadores debajo del umbral configurado.")
        return
    c1,c2,c3=st.columns(3)
    c1.metric("Críticas",int((alerts["Prioridad"]=="Crítica").sum()))
    c2.metric("Advertencias",int((alerts["Prioridad"]=="Advertencia").sum()))
    c3.metric("Atención",int((alerts["Prioridad"]=="Atención").sum()))
    panel("Alertas activas",alerts,height=420)

def page_perfil_usuario_v17():
    _v17_title("Perfil de Usuario", "Información personal, seguridad, preferencias y sesiones.")
    user = st.session_state.get("user", {})

    # Contenedor compacto: evita que el perfil vuelva a ocupar todo el ancho
    # en monitores grandes y conserva el ajuste responsive en móvil.
    st.markdown('<div class="ps-profile-page-marker"></div>', unsafe_allow_html=True)
    t1, t2, t3, t4 = st.tabs(["Información personal", "Seguridad", "Preferencias", "Sesiones activas"])

    with t1:
        left, right = st.columns(2, gap="large")
        with left:
            st.text_input("Nombre completo", value=str(user.get("nombre", "")), key="profile_name")
            st.text_input("Nómina", value=str(user.get("nomina", "")), disabled=True, key="profile_nomina")
        with right:
            st.text_input("Perfil", value=str(user.get("permiso", "")), disabled=True, key="profile_role")
            st.text_input("Alcance", value=str(user.get("scope_label", user.get("scope_type", "Compañía"))), disabled=True, key="profile_scope")
        st.button("Guardar información", type="primary", key="profile_save_info")

    with t2:
        left, right = st.columns(2, gap="large")
        with left:
            st.text_input("Contraseña actual", type="password", key="profile_current_password")
        with right:
            st.text_input("Nueva contraseña", type="password", key="profile_new_password")
            st.text_input("Confirmar nueva contraseña", type="password", key="profile_confirm_password")
        st.button("Guardar contraseña", type="primary", key="profile_save_password")

    with t3:
        left, right = st.columns(2, gap="large")
        with left:
            st.checkbox("Recibir alertas críticas", value=True, key="profile_alerts")
            st.checkbox("Recibir resumen semanal", value=True, key="profile_weekly")
        with right:
            st.selectbox("Página inicial", ["Centro Ejecutivo", "Operación Diaria", "Reporte Semanal"], key="profile_home")
        st.button("Guardar preferencias", type="primary", key="profile_save_preferences")

    with t4:
        sessions = pd.DataFrame(
            [["Sesión actual", str(user.get("nomina", "")), pd.Timestamp.now().strftime("%d/%m/%Y %H:%M")]],
            columns=["Sesión", "Usuario", "Última actividad"],
        )
        panel("Sesiones", sessions, height=180)


def page_inteligencia_operativa_v17(op, co):
    _v17_title("Inteligencia Operativa", "Tendencias calculadas desde información real.")
    if op is None or op.empty:
        st.info("Sin información para generar tendencias.")
        return
    d=op.copy(); d["Fecha"]=pd.to_datetime(d.get("Fecha"),errors="coerce"); d["Piezas"]=pd.to_numeric(d.get("Piezas",0),errors="coerce").fillna(0); d=d[d["Fecha"].notna()]
    weekly=d.groupby(d["Fecha"].dt.to_period("W").astype(str))["Piezas"].sum().sort_index()
    from services.intelligence import trend
    info=trend(weekly)
    c1,c2,c3=st.columns(3); c1.metric("Promedio móvil 4 semanas",f"{info['Promedio móvil 4 semanas']:,.0f}"); c2.metric("Resultado actual",f"{info['Actual']:,.0f}"); c3.metric("Tendencia",info["Tendencia"],f"{info['Desviación %']:.1f}%")
    fig=go.Figure(); fig.add_scatter(x=weekly.index,y=weekly.values,mode="lines+markers",name="Piezas",line=dict(color="#3366CC")); fig.update_layout(title="Tendencia semanal real",height=420); st.plotly_chart(fig,width="stretch")

# ============================================================
# V25 — REPORTES EJECUTIVOS, DISEÑO Y ECUACIONES ESTANDARIZADAS
# ============================================================
def _v25_excel_bytes(sheets):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            safe_name = re.sub(r"[\\/*?:\[\]]", "_", str(sheet_name))[:31] or "Reporte"
            (frame if frame is not None else pd.DataFrame()).to_excel(writer, index=False, sheet_name=safe_name)
    output.seek(0)
    return output.getvalue()


def _v25_downloads(title, subtitle, detail, summary, key, extra_sheets=None):
    c_pdf, c_xlsx = st.columns(2)
    with c_pdf:
        generic_pdf_button(
            title,
            subtitle,
            detail if detail is not None else pd.DataFrame(),
            summary,
            file_name=f"PS_Operaciones_Ropa_{re.sub(r'[^A-Za-z0-9]+','_',title).strip('_')}.pdf",
            key=f"{key}_pdf",
        )
    with c_xlsx:
        summary_df = pd.DataFrame([summary])
        sheets = {"Resumen": summary_df, "Detalle": detail if detail is not None else pd.DataFrame()}
        if extra_sheets:
            sheets.update(extra_sheets)
        st.download_button(
            "Descargar Excel",
            data=_v25_excel_bytes(sheets),
            file_name=f"PS_Operaciones_Ropa_{re.sub(r'[^A-Za-z0-9]+','_',title).strip('_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key}_xlsx",
            width="stretch",
        )


def _v25_date_filter(df, start, end):
    if df is None or df.empty or "Fecha" not in df.columns:
        return pd.DataFrame()
    out = df.copy()
    out["Fecha"] = pd.to_datetime(out["Fecha"], errors="coerce").dt.normalize()
    return out[out["Fecha"].between(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize())].copy()


def _v25_week_bounds(year, week):
    start = pd.Timestamp(date.fromisocalendar(int(year), int(week), 1))
    return start, start + pd.Timedelta(days=6)


def _v25_recovery_period(co, start, end, stores=None):
    current = _v25_date_filter(normalize_commercial_df(co), start, end)
    current = filter_stores(current, stores)
    if current.empty:
        return recovery_executive_summary(current)
    return recovery_executive_summary(current)


def _v25_productivity_period(op, start, end, stores=None, meta=784):
    current = _v25_date_filter(normalize_operation_df(op), start, end)
    current = filter_stores(current, stores)
    if current.empty:
        return pd.DataFrame(), {"Piezas": 0.0, "Días": 0, "Productividad": 0.0, "% Productividad": 0.0}
    split = split_operation(current)
    name_col = "Nombre Real" if "Nombre Real" in split.columns else "Nombre"
    productive_mask = split["Actividad"].map(norm_text).str.contains(
        r"ACONDICION|HABILIT|UBIC|RECOLECCION DE MUERTOS|RECOLECCIÓN DE MUERTOS|CAJA|PROBADOR",
        regex=True, na=False,
    )
    prod = split[productive_mask].copy()
    if prod.empty:
        return pd.DataFrame(), {"Piezas": 0.0, "Días": 0, "Productividad": 0.0, "% Productividad": 0.0}
    prod["Fecha"] = pd.to_datetime(prod["Fecha"], errors="coerce")
    grouped = prod.groupby([name_col, "Tienda"], dropna=False).agg(
        **{"Piezas procesadas": ("Piezas", "sum"), "Días trabajados": ("Fecha", lambda s: s.dt.date.nunique())}
    ).reset_index()
    grouped["Productividad diaria"] = grouped["Piezas procesadas"].div(grouped["Días trabajados"].replace(0, np.nan)).fillna(0)
    grouped["Meta acumulada"] = grouped["Días trabajados"] * float(meta)
    grouped["% Cumplimiento"] = grouped["Piezas procesadas"].div(grouped["Meta acumulada"].replace(0, np.nan)).mul(100).fillna(0)
    grouped["Diferencia"] = grouped["Piezas procesadas"] - grouped["Meta acumulada"]
    grouped["Faltante"] = (grouped["Meta acumulada"] - grouped["Piezas procesadas"]).clip(lower=0)
    grouped = grouped.sort_values(["% Cumplimiento", "Piezas procesadas", "Días trabajados"], ascending=[False, False, False]).reset_index(drop=True)
    grouped["Ranking"] = grouped.index + 1
    pieces = float(grouped["Piezas procesadas"].sum())
    days = int(grouped["Días trabajados"].sum())
    productivity = pieces / days if days else 0.0
    return grouped, {"Piezas": pieces, "Días": days, "Productividad": productivity, "% Productividad": productivity / float(meta) * 100 if meta else 0.0}


def _v25_recorridos_period(op, start, end, stores=None, weekly_goal=47):
    current = _v25_date_filter(normalize_operation_df(op), start, end)
    current = filter_stores(current, stores)
    if current.empty:
        return pd.DataFrame(), {"Realizados": 0.0, "Meta": 0.0, "% Recorridos": 0.0, "Faltante": 0.0}
    split = split_operation(current)
    act = split["Actividad"].map(norm_text)
    if "Recorridos" in split.columns:
        numeric = pd.to_numeric(split["Recorridos"], errors="coerce").fillna(0)
        if numeric.sum() <= 0:
            numeric = act.str.contains("RECORRIDO", na=False).astype(int)
    else:
        numeric = act.str.contains("RECORRIDO", na=False).astype(int)
    split["Recorridos calculados"] = numeric
    by_store = split.groupby("Tienda", as_index=False)["Recorridos calculados"].sum().rename(columns={"Recorridos calculados": "Recorridos"})
    days = max((pd.Timestamp(end).normalize() - pd.Timestamp(start).normalize()).days + 1, 1)
    meta_store = float(weekly_goal) if days >= 7 else float(weekly_goal) / 7 * days
    by_store["Meta"] = meta_store
    by_store["Faltante"] = (by_store["Meta"] - by_store["Recorridos"]).clip(lower=0)
    by_store["% Cumplimiento"] = by_store["Recorridos"].div(by_store["Meta"].replace(0, np.nan)).mul(100).fillna(0)
    total = float(by_store["Recorridos"].sum())
    meta = float(by_store["Meta"].sum())
    return by_store.sort_values("% Cumplimiento", ascending=False), {
        "Realizados": total, "Meta": meta, "% Recorridos": total / meta * 100 if meta else 0.0, "Faltante": max(meta-total, 0)
    }


def _v25_operational_period(op, co, start, end, stores, carryover="none"):
    table = table_by_store(op, co, start, end, stores, carryover_mode=carryover)
    total = float(pd.to_numeric(table.get("Total", table.get("Ingresos periodo", 0)), errors="coerce").fillna(0).sum()) if not table.empty else 0.0
    hab = float(pd.to_numeric(table.get("Habilitadas", 0), errors="coerce").fillna(0).sum()) if not table.empty else 0.0
    ubi = float(pd.to_numeric(table.get("Ubicadas", 0), errors="coerce").fillna(0).sum()) if not table.empty else 0.0
    return table, {
        "Piezas ingresadas": total,
        "Acondicionado": hab,
        "Ubicado": ubi,
        "Pendiente acondicionar": max(total-hab, 0),
        "Pendiente ubicar": max(total-ubi, 0),
        "% Acondicionado": hab/total*100 if total else 0.0,
        "% Ubicado / Ingresos": ubi/total*100 if total else 0.0,
        "% Ubicado / Acondicionado": ubi/hab*100 if hab else 0.0,
    }


def _v25_score(op_metrics, rec_metrics, prod_metrics, route_metrics):
    pending_control = (1 - op_metrics["Pendiente ubicar"] / op_metrics["Piezas ingresadas"]) * 100 if op_metrics["Piezas ingresadas"] else 0.0
    components = {
        "conversion": max(0, min(100, rec_metrics.get("% Recuperación Piezas", 0))),
        "recovery": max(0, min(100, rec_metrics.get("% Recuperación $", 0))),
        "productivity": max(0, min(100, prod_metrics.get("% Productividad", 0))),
        "routes": max(0, min(100, route_metrics.get("% Recorridos", 0))),
        "pending": max(0, min(100, pending_control)),
    }
    score = components["conversion"]*.30 + components["recovery"]*.25 + components["productivity"]*.20 + components["routes"]*.15 + components["pending"]*.10
    return max(0, min(100, score)), components


def _v25_kpi_cards(items):
    html = '<div class="v25-kpi-grid">'
    for title, value, sub, tone in items:
        html += f'''<div class="v25-kpi-card"><div class="v25-kpi-accent" style="background:{tone}"></div><div class="v25-kpi-label">{title}</div><div class="v25-kpi-value">{value}</div><div class="v25-kpi-sub">{sub}</div></div>'''
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def _v25_macro(recovery_detail):
    if recovery_detail is None or recovery_detail.empty:
        return pd.DataFrame()
    macro = recovery_detail.groupby("Tienda", as_index=False).agg({
        "Dev Pzs":"sum", "Piezas Recuperadas":"sum", "Valor de la Devolución a Precio Neto":"sum", "Recuperación $":"sum"
    })
    macro["% Conversión"] = macro["Piezas Recuperadas"].div(macro["Dev Pzs"].replace(0, np.nan)).mul(100).fillna(0).clip(0,100)
    macro["% Recuperación económica"] = macro["Recuperación $"].div(macro["Valor de la Devolución a Precio Neto"].replace(0, np.nan)).mul(100).fillna(0).clip(0,100)
    macro["Pendiente Pzs"] = (macro["Dev Pzs"] - macro["Piezas Recuperadas"]).clip(lower=0)
    macro["Pendiente $"] = (macro["Valor de la Devolución a Precio Neto"] - macro["Recuperación $"]).clip(lower=0)
    return macro


def page_resumen(op, co):
    op = reliable_operation(op, co); co = normalize_commercial_df(co)
    user = st.session_state.get("user", {})
    render_personalized_executive_header(user, op, co)
    if (op is None or op.empty) and (co is None or co.empty):
        st.info("Sin información disponible dentro del alcance asignado."); return
    stores = authorized_stores(op, co, user)
    date_series = []
    for frame in (op, co):
        if frame is not None and not frame.empty and "Fecha" in frame:
            date_series.extend(pd.to_datetime(frame["Fecha"], errors="coerce").dropna().tolist())
    end = pd.Timestamp(max(date_series)).normalize() if date_series else pd.Timestamp.today().normalize()
    start = end - pd.Timedelta(days=27)
    op_table, opm = _v25_operational_period(op, co, start, end, stores, carryover="none")
    recm, rec_detail = _v25_recovery_period(co, start, end, stores)
    prod_table, prodm = _v25_productivity_period(op, start, end, stores)
    route_table, routem = _v25_recorridos_period(op, start, end, stores)
    score, components = _v25_score(opm, recm, prodm, routem)
    st.caption(f"Periodo ejecutivo: {start.strftime('%d/%m/%Y')} al {end.strftime('%d/%m/%Y')} · Última actualización real: {end.strftime('%d/%m/%Y')}")
    _v25_kpi_cards([
        ("Piezas ingresadas", fmt_num(opm["Piezas ingresadas"]), f"Acondicionado {opm['% Acondicionado']:.1f}%", "#3366CC"),
        ("Conversión", fmt_pct(recm["% Recuperación Piezas"]), f"{recm['Piezas Recuperadas']:,.0f} piezas recuperadas", "#7C3AED"),
        ("Recuperación económica", fmt_pct(recm["% Recuperación $"]), fmt_money(recm["Recuperación $"]), "#E6007E"),
        ("Productividad", fmt_pct(prodm["% Productividad"]), f"{prodm['Productividad']:,.0f} pzs/día", "#10B981"),
        ("Recorridos", fmt_pct(routem["% Recorridos"]), f"{routem['Realizados']:,.0f} de {routem['Meta']:,.0f}", "#F59E0B"),
        ("PS Score", f"{score:.1f}", "Excelente" if score>=90 else "Estable" if score>=80 else "Atención" if score>=70 else "Crítico", "#173B73"),
    ])
    macro = _v25_macro(rec_detail)
    st.markdown("### Alertas y prioridades")
    alert_items = []
    if not macro.empty:
        worst = macro.sort_values("Pendiente $", ascending=False).head(2)
        best = macro.sort_values("% Recuperación económica", ascending=False).head(1)
        if not best.empty:
            row = best.iloc[0]
            alert_items.append(("Mejor resultado", f"{row['Tienda']} · {row['% Recuperación económica']:.1f}% recuperación económica", "#DCFCE7", "#166534"))
        for _, row in worst.iterrows():
            alert_items.append(("Prioridad económica", f"{row['Tienda']} · {row['Pendiente Pzs']:,.0f} pzas · {fmt_money(row['Pendiente $'])}", "#FEF3C7", "#92400E"))
    if opm["Pendiente ubicar"] > 0:
        alert_items.append(("Pendiente operativo", f"{opm['Pendiente ubicar']:,.0f} piezas por ubicar", "#DBEAFE", "#1D4ED8"))
    if alert_items:
        html = '<div class="v253-alert-grid">'
        for title, text, bg, color in alert_items:
            html += f'<div class="v253-alert-card" style="background:{bg};color:{color}"><b>{title}</b><span>{text}</span></div>'
        html += '</div>'
        st.markdown(html, unsafe_allow_html=True)

    st.markdown("### Macro por tiendas")
    if not macro.empty:
        ranked = macro.sort_values(["% Recuperación económica","% Conversión"], ascending=False).copy()
        ranked = ranked.rename(columns={
            "Piezas Recuperadas":"Recup. Pzs",
            "Valor de la Devolución a Precio Neto":"Valor Dev. $",
            "Recuperación $":"Recup. $",
            "% Conversión":"Conv. %",
            "% Recuperación económica":"Recup. %",
            "Pendiente Pzs":"Pend. Pzs",
            "Pendiente $":"Pend. $",
        })
        preferred = ["Tienda","Dev Pzs","Recup. Pzs","Conv. %","Valor Dev. $","Recup. $","Recup. %","Pend. Pzs","Pend. $"]
        ranked = ranked[[c for c in preferred if c in ranked.columns]]
        panel("Ranking ejecutivo", ranked, height=430)
    else:
        st.info("Sin información comercial para el periodo.")
    if not op_table.empty:
        combined_chart(op_table, "Ingreso vs Acondicionado vs Ubicado — últimas 4 semanas")
    summary = {**opm, **recm, **prodm, **routem, "PS Score": score, "Periodo": f"{start.date()} a {end.date()}"}
    _v25_downloads("Centro Ejecutivo", "Resumen integral por alcance autorizado", macro if not macro.empty else op_table, summary, "v25_center", {"Operación":op_table,"Productividad":prod_table,"Recorridos":route_table})


def page_por_dia(op, co):
    op = reliable_operation(op, co); co = normalize_commercial_df(co)
    _v17_title("Operación Diaria", "Ingresos, acondicionado, ubicado, pendientes y avance por tienda.")
    dates=[]
    for frame in (op,co):
        if frame is not None and not frame.empty and "Fecha" in frame: dates += pd.to_datetime(frame["Fecha"],errors="coerce").dropna().tolist()
    default = pd.Timestamp(max(dates)).date() if dates else date.today()
    f1,f2 = st.columns([1,3])
    with f1: selected = st.date_input("Fecha", value=default, key="v25_daily_date")
    stores = authorized_stores(op, co)
    with f2: selected_stores = st.multiselect("Tiendas", stores, default=stores, key="v25_daily_stores")
    start=end=pd.Timestamp(selected)
    table, metrics = _v25_operational_period(op, co, start, end, selected_stores, carryover="previous_day")
    recm, detail = _v25_recovery_period(co, start, end, selected_stores)
    _v25_kpi_cards([
        ("Ingresos",fmt_num(metrics["Piezas ingresadas"]),"Piezas recibidas","#3366CC"),
        ("Acondicionado",fmt_num(metrics["Acondicionado"]),fmt_pct(metrics["% Acondicionado"]),"#7C3AED"),
        ("Ubicado",fmt_num(metrics["Ubicado"]),fmt_pct(metrics["% Ubicado / Ingresos"]),"#E6007E"),
        ("Pend. acondicionar",fmt_num(metrics["Pendiente acondicionar"]),"Ingresos - acondicionado","#F59E0B"),
        ("Pend. ubicar",fmt_num(metrics["Pendiente ubicar"]),"Ingresos - ubicado","#EF4444"),
        ("Conversión",fmt_pct(recm["% Recuperación Piezas"]),"Misma semana ISO","#10B981"),
    ])
    if not table.empty:
        combined_chart(table,"Ingreso vs Acondicionado vs Ubicado", income_column="Total")
        pending = table[[c for c in ["Tienda","Total","Pend. Hab.","Pend. Ub."] if c in table.columns]].copy()
        if not pending.empty:
            fig=go.Figure(); fig.add_scatter(x=pending["Tienda"],y=pending.get("Total",0),name="Ingresos",mode="lines+markers",line=dict(color="#3366CC",width=3));
            if "Pend. Hab." in pending: fig.add_bar(x=pending["Tienda"],y=pending["Pend. Hab."],name="Pendiente acondicionar",marker_color="#F59E0B")
            if "Pend. Ub." in pending: fig.add_bar(x=pending["Tienda"],y=pending["Pend. Ub."],name="Pendiente ubicar",marker_color="#EF4444")
            fig.update_layout(title="Pendientes operativos por tienda",height=420,barmode="group"); st.plotly_chart(fig,width="stretch")
        panel("Detalle diario por tienda",table,height=390)
    summary={**metrics,**recm,"Fecha":str(selected)}
    _v25_downloads("Operación Diaria",f"Fecha: {pd.Timestamp(selected).strftime('%d/%m/%Y')}",table,summary,"v25_daily",{"Recuperación":detail})


def page_semanal(op, co):
    op = reliable_operation(op, co); co=normalize_commercial_df(co)
    _v17_title("Reporte Semanal", "Operación, productividad, recorridos y recuperación cerrados por semana ISO.")
    stores=authorized_stores(op,co); c1,c2=st.columns([2,5]); pairs=available_iso_weeks(op,co)
    if not pairs: st.info("Sin semanas válidas detectadas."); return
    labels=[f"{y}-Semana {w:02d}" for y,w in pairs]
    with c1: label=st.selectbox("Semana ISO",labels,index=len(labels)-1,key="v25_week")
    with c2: selected_stores=st.multiselect("Tiendas",stores,default=stores,key="v25_week_stores")
    year,week=pairs[labels.index(label)]; start,end=_v25_week_bounds(year,week)
    table,opm=_v25_operational_period(op,co,start,end,selected_stores,carryover="previous_sunday")
    recm,detail=_v25_recovery_period(co,start,end,selected_stores)
    prod_table,prodm=_v25_productivity_period(op,start,end,selected_stores)
    route_table,routem=_v25_recorridos_period(op,start,end,selected_stores)
    pstart,pend=start-pd.Timedelta(days=7),end-pd.Timedelta(days=7)
    _,prev_op=_v25_operational_period(op,co,pstart,pend,selected_stores,carryover="previous_sunday")
    prev_rec,_=_v25_recovery_period(co,pstart,pend,selected_stores)
    delta_ing=opm["Piezas ingresadas"]-prev_op["Piezas ingresadas"]
    delta_conv=recm["% Recuperación Piezas"]-prev_rec["% Recuperación Piezas"]
    _v25_kpi_cards([
        ("Piezas ingresadas",fmt_num(opm["Piezas ingresadas"]),f"Δ {delta_ing:+,.0f}","#3366CC"),
        ("Acondicionado",fmt_pct(opm["% Acondicionado"]),fmt_num(opm["Acondicionado"]),"#7C3AED"),
        ("Ubicado",fmt_pct(opm["% Ubicado / Ingresos"]),fmt_num(opm["Ubicado"]),"#E6007E"),
        ("Conversión",fmt_pct(recm["% Recuperación Piezas"]),f"Δ {delta_conv:+.1f} pp","#10B981"),
        ("Recuperación económica",fmt_pct(recm["% Recuperación $"]),fmt_money(recm["Recuperación $"]),"#173B73"),
        ("Productividad",fmt_pct(prodm["% Productividad"]),f"{prodm['Productividad']:,.0f} pzs/día","#F59E0B"),
        ("Recorridos",fmt_pct(routem["% Recorridos"]),f"{routem['Realizados']:,.0f}/{routem['Meta']:,.0f}","#EF4444"),
    ])
    trends=[]
    selected_pos=pairs.index((year,week)); relevant=pairs[max(0,selected_pos-3):selected_pos+1]
    for y,w in relevant:
        ws,we=_v25_week_bounds(y,w); _,om=_v25_operational_period(op,co,ws,we,selected_stores,"none"); rm,_=_v25_recovery_period(co,ws,we,selected_stores); _,pm=_v25_productivity_period(op,ws,we,selected_stores); _,rr=_v25_recorridos_period(op,ws,we,selected_stores)
        trends.append({"Semana":f"{y}-{w:02d}","Ingresos":om["Piezas ingresadas"],"% Acondicionado":om["% Acondicionado"],"% Ubicado":om["% Ubicado / Ingresos"],"% Conversión":rm["% Recuperación Piezas"],"% Recuperación $":rm["% Recuperación $"],"% Productividad":pm["% Productividad"],"% Recorridos":rr["% Recorridos"]})
    trend_df=pd.DataFrame(trends)
    if not trend_df.empty:
        fig=go.Figure();
        for col,color in [("% Conversión","#3366CC"),("% Recuperación $","#E6007E"),("% Productividad","#10B981"),("% Recorridos","#F59E0B")]: fig.add_scatter(x=trend_df["Semana"],y=trend_df[col],mode="lines+markers",name=col,line=dict(color=color,width=3))
        fig.update_layout(title="Tendencia últimas 4 semanas",height=430,yaxis_title="%",hovermode="x unified"); st.plotly_chart(fig,width="stretch")
    macro=_v25_macro(detail)
    if not macro.empty: panel("Top y oportunidades por tienda",macro.sort_values("% Recuperación económica",ascending=False),height=360)
    panel(f"Detalle operativo · Semana {week:02d}",table,height=380)
    summary={**opm,**recm,**prodm,**routem,"Año ISO":year,"Semana ISO":week,"Variación ingresos":delta_ing,"Variación conversión pp":delta_conv}
    _v25_downloads("Reporte Semanal",f"Semana ISO {week:02d}/{year} · {start.strftime('%d/%m')} al {end.strftime('%d/%m/%Y')}",table,summary,"v25_weekly",{"Tendencia 4 semanas":trend_df,"Recuperación":macro,"Productividad":prod_table,"Recorridos":route_table})


def page_mensual(op, co):
    op=reliable_operation(op,co); co=normalize_commercial_df(co); _v17_title("Reporte Mensual","Consolidado mensual que suma resultados semanales cerrados, sin arrastre entre semanas.")
    stores=authorized_stores(op,co); months=set()
    for frame in (op,co):
        if frame is not None and not frame.empty and "Fecha" in frame: months.update(pd.to_datetime(frame["Fecha"],errors="coerce").dropna().dt.to_period("M").astype(str).tolist())
    months=sorted(months)
    if not months: st.info("Sin meses detectados."); return
    c1,c2=st.columns([2,5]);
    with c1: month=st.selectbox("Mes",months,index=len(months)-1,key="v25_month")
    with c2: selected_stores=st.multiselect("Tiendas",stores,default=stores,key="v25_month_stores")
    period=pd.Period(month,freq="M"); start=period.start_time.normalize(); end=period.end_time.normalize()
    table,opm=_v25_operational_period(op,co,start,end,selected_stores,"none"); recm,detail=_v25_recovery_period(co,start,end,selected_stores); prod_table,prodm=_v25_productivity_period(op,start,end,selected_stores); route_table,routem=_v25_recorridos_period(op,start,end,selected_stores,47)
    prev=period-1; _,prev_op=_v25_operational_period(op,co,prev.start_time,prev.end_time,selected_stores,"none"); prev_rec,_=_v25_recovery_period(co,prev.start_time,prev.end_time,selected_stores)
    _v25_kpi_cards([
        ("Ingresos mes",fmt_num(opm["Piezas ingresadas"]),f"Δ {opm['Piezas ingresadas']-prev_op['Piezas ingresadas']:+,.0f}","#3366CC"),
        ("Acondicionado",fmt_pct(opm["% Acondicionado"]),fmt_num(opm["Acondicionado"]),"#7C3AED"),
        ("Ubicado",fmt_pct(opm["% Ubicado / Ingresos"]),fmt_num(opm["Ubicado"]),"#E6007E"),
        ("Conversión mensual",fmt_pct(recm["% Recuperación Piezas"]),f"Δ {recm['% Recuperación Piezas']-prev_rec['% Recuperación Piezas']:+.1f} pp","#10B981"),
        ("Recuperación económica",fmt_pct(recm["% Recuperación $"]),fmt_money(recm["Recuperación $"]),"#173B73"),
        ("Productividad",fmt_pct(prodm["% Productividad"]),f"{prodm['Productividad']:,.0f} pzs/día","#F59E0B"),
        ("Recorridos",fmt_pct(routem["% Recorridos"]),f"{routem['Realizados']:,.0f} realizados","#EF4444"),
    ])
    trend=[]
    for p in [period-2,period-1,period]:
        _,om=_v25_operational_period(op,co,p.start_time,p.end_time,selected_stores,"none"); rm,_=_v25_recovery_period(co,p.start_time,p.end_time,selected_stores); _,pm=_v25_productivity_period(op,p.start_time,p.end_time,selected_stores); _,rr=_v25_recorridos_period(op,p.start_time,p.end_time,selected_stores)
        trend.append({"Mes":str(p),"Ingresos":om["Piezas ingresadas"],"% Acondicionado":om["% Acondicionado"],"% Ubicado":om["% Ubicado / Ingresos"],"% Conversión":rm["% Recuperación Piezas"],"% Recuperación $":rm["% Recuperación $"],"% Productividad":pm["% Productividad"],"% Recorridos":rr["% Recorridos"]})
    trend_df=pd.DataFrame(trend)
    fig=go.Figure();
    for col,color in [("% Conversión","#3366CC"),("% Recuperación $","#E6007E"),("% Productividad","#10B981"),("% Recorridos","#F59E0B")]: fig.add_scatter(x=trend_df["Mes"],y=trend_df[col],mode="lines+markers",name=col,line=dict(color=color,width=3))
    fig.update_layout(title="Comparativo últimos 3 meses",height=430,yaxis_title="%",hovermode="x unified"); st.plotly_chart(fig,width="stretch")
    macro=_v25_macro(detail)
    if not macro.empty:
        heat=macro.pivot_table(index="Tienda",values=["% Conversión","% Recuperación económica"],aggfunc="mean"); st.markdown("### Heatmap de desempeño"); st.dataframe(heat.style.background_gradient(cmap="RdYlGn",vmin=0,vmax=100),width="stretch")
    panel(f"Detalle mensual · {month}",table,height=380)
    summary={**opm,**recm,**prodm,**routem,"Mes":month}
    _v25_downloads("Reporte Mensual",f"Periodo {month}",table,summary,"v25_monthly",{"Comparativo 3 meses":trend_df,"Recuperación":macro,"Productividad":prod_table,"Recorridos":route_table})


def page_productividad(op, co):
    _v17_title("Productividad", "Ranking real por colaborador, metas acumuladas, top y oportunidades.")
    if op is None or op.empty: st.info("Sin información operativa."); return
    dates=pd.to_datetime(op["Fecha"],errors="coerce").dropna(); end=dates.max().normalize(); start=max(dates.min().normalize(),end-pd.Timedelta(days=29)); stores=authorized_stores(op,co)
    c1,c2=st.columns([2,5]);
    with c1: period=st.date_input("Periodo",value=(start.date(),end.date()),key="v25_prod_dates")
    if isinstance(period,(tuple,list)) and len(period)==2: start,end=map(pd.Timestamp,period)
    with c2: selected_stores=st.multiselect("Tiendas",stores,default=stores,key="v25_prod_stores")
    detail,summary=_v25_productivity_period(op,start,end,selected_stores)
    _v25_kpi_cards([("Piezas procesadas",fmt_num(summary["Piezas"]),"Actividades productivas","#3366CC"),("Días trabajados",fmt_num(summary["Días"]),"Suma colaborador-día","#7C3AED"),("Productividad",f"{summary['Productividad']:,.0f}","Piezas por colaborador/día","#E6007E"),("Cumplimiento",fmt_pct(summary["% Productividad"]),"Meta 784 pzs/día","#10B981")])
    if detail.empty: st.info("Sin registros productivos en el periodo."); return
    top=detail.head(3); bottom=detail.tail(3).sort_values("% Cumplimiento")
    l,r=st.columns(2,gap="large");
    with l: panel("Top 3 colaboradores",top,height=240)
    with r: panel("Bottom 3 con actividad",bottom,height=240)
    panel("Ranking completo",detail,height=430)
    _v25_downloads("Productividad",f"{start.strftime('%d/%m/%Y')} al {end.strftime('%d/%m/%Y')}",detail,summary,"v25_productivity",{"Top 3":top,"Bottom 3":bottom})


def page_recorridos(op, co):
    _v17_title("Recorridos", "Cumplimiento semanal y diario con meta configurable de 47 recorridos por tienda.")
    if op is None or op.empty: st.info("Sin información operativa."); return
    pairs=available_iso_weeks(op,co)
    if not pairs: st.info("Sin semanas detectadas."); return
    stores=authorized_stores(op,co); labels=[f"{y}-Semana {w:02d}" for y,w in pairs]; c1,c2=st.columns([2,5])
    with c1: label=st.selectbox("Semana ISO",labels,index=len(labels)-1,key="v25_routes_week")
    with c2: selected_stores=st.multiselect("Tiendas",stores,default=stores,key="v25_routes_stores")
    year,week=pairs[labels.index(label)]; start,end=_v25_week_bounds(year,week); detail,summary=_v25_recorridos_period(op,start,end,selected_stores)
    _v25_kpi_cards([("Meta consolidada",fmt_num(summary["Meta"]),"47 por tienda","#3366CC"),("Realizados",fmt_num(summary["Realizados"]),"Semana seleccionada","#7C3AED"),("Cumplimiento",fmt_pct(summary["% Recorridos"]),"Realizados / meta","#10B981"),("Faltante",fmt_num(summary["Faltante"]),"Meta - realizados","#EF4444")])
    if not detail.empty:
        fig=go.Figure(); ranked=detail.sort_values("% Cumplimiento"); fig.add_bar(y=ranked["Tienda"],x=ranked["% Cumplimiento"],orientation="h",marker_color=np.where(ranked["% Cumplimiento"]>=90,"#10B981",np.where(ranked["% Cumplimiento"]>=80,"#F59E0B","#EF4444")),text=ranked["% Cumplimiento"].map(lambda x:f"{x:.1f}%"),textposition="outside"); fig.add_vline(x=100,line_dash="dash",line_color="#173B73"); fig.update_layout(title="Cumplimiento por tienda",height=max(420,len(ranked)*32),xaxis_title="% Cumplimiento"); st.plotly_chart(fig,width="stretch")
        panel("Detalle de recorridos",detail,height=390)
    _v25_downloads("Recorridos",f"Semana ISO {week:02d}/{year}",detail,summary,"v25_routes")


def page_detalle_tienda_v17(op, co):
    _v17_title("Detalle por Tienda", "Vista integral de operación, recuperación, productividad y recorridos.")
    stores=authorized_stores(op,co)
    if not stores: st.info("Sin tiendas dentro del alcance."); return
    store=st.selectbox("Tienda",stores,key="v25_store_detail"); o=filter_stores(op,[store]); c=filter_stores(co,[store])
    dates=[]
    for frame in (o,c):
        if frame is not None and not frame.empty and "Fecha" in frame: dates+=pd.to_datetime(frame["Fecha"],errors="coerce").dropna().tolist()
    if not dates: st.info("Sin información para la tienda seleccionada."); return
    end=pd.Timestamp(max(dates)).normalize(); start=end-pd.Timedelta(days=27)
    table,opm=_v25_operational_period(o,c,start,end,[store],"none"); recm,detail=_v25_recovery_period(c,start,end,[store]); prod,prodm=_v25_productivity_period(o,start,end,[store]); routes,routem=_v25_recorridos_period(o,start,end,[store]); score,_=_v25_score(opm,recm,prodm,routem)
    _v25_kpi_cards([("Ingresos",fmt_num(opm["Piezas ingresadas"]),"Últimas 4 semanas","#3366CC"),("Acondicionado",fmt_pct(opm["% Acondicionado"]),fmt_num(opm["Acondicionado"]),"#7C3AED"),("Ubicado",fmt_pct(opm["% Ubicado / Ingresos"]),fmt_num(opm["Ubicado"]),"#E6007E"),("Conversión",fmt_pct(recm["% Recuperación Piezas"]),"Misma semana ISO","#10B981"),("Recuperación $",fmt_pct(recm["% Recuperación $"]),fmt_money(recm["Recuperación $"]),"#173B73"),("Productividad",fmt_pct(prodm["% Productividad"]),f"{prodm['Productividad']:,.0f} pzs/día","#F59E0B"),("Recorridos",fmt_pct(routem["% Recorridos"]),f"{routem['Realizados']:,.0f}","#EF4444"),("PS Score",f"{score:.1f}",store,"#173B73")])
    if o is not None and not o.empty:
        split=split_operation(_v25_date_filter(o,start,end)); daily=split.groupby("Fecha",as_index=False)[["Piezas","Habilitadas","Ubicadas"]].sum(); fig=go.Figure();
        for col,color in [("Piezas","#3366CC"),("Habilitadas","#7C3AED"),("Ubicadas","#E6007E")]: fig.add_scatter(x=daily["Fecha"],y=daily[col],mode="lines+markers",name=col,line=dict(color=color,width=3))
        fig.update_layout(title=f"Evolución diaria · {store}",height=420); st.plotly_chart(fig,width="stretch")
    summary={**opm,**recm,**prodm,**routem,"PS Score":score,"Tienda":store}
    _v25_downloads(f"Detalle Tienda {store}",f"{start.strftime('%d/%m/%Y')} al {end.strftime('%d/%m/%Y')}",table,summary,"v25_store",{"Recuperación":detail,"Productividad":prod,"Recorridos":routes})


def page_detalle_colaborador_v17(op, co):
    _v17_title("Detalle por Colaborador", "Productividad, meta acumulada, faltante, recorridos y distribución por actividad.")
    if op is None or op.empty: st.info("Sin información."); return
    name_col="Nombre Real" if "Nombre Real" in op.columns else "Nombre"; names=sorted(op[name_col].dropna().astype(str).unique())
    selected=st.selectbox("Colaborador",names,key="v25_employee"); current=op[op[name_col].astype(str).eq(selected)].copy(); dates=pd.to_datetime(current["Fecha"],errors="coerce").dropna(); start,end=dates.min(),dates.max(); detail,summary=_v25_productivity_period(current,start,end,None)
    split=split_operation(current); act=split.groupby("Actividad",as_index=False)["Piezas"].sum().sort_values("Piezas",ascending=False); total=act["Piezas"].sum(); act["% Distribución"]=act["Piezas"].div(total if total else np.nan).mul(100).fillna(0)
    route_detail,route_summary=_v25_recorridos_period(current,start,end,None)
    row=detail.iloc[0] if not detail.empty else {}
    _v25_kpi_cards([("Piezas procesadas",fmt_num(row.get("Piezas procesadas",0)),selected,"#3366CC"),("Días trabajados",fmt_num(row.get("Días trabajados",0)),"Días con registro","#7C3AED"),("Productividad",f"{row.get('Productividad diaria',0):,.0f}","Meta 784 pzs/día","#E6007E"),("Cumplimiento",fmt_pct(row.get("% Cumplimiento",0)),f"Faltante {row.get('Faltante',0):,.0f}","#10B981"),("Recorridos",fmt_num(route_summary["Realizados"]),fmt_pct(route_summary["% Recorridos"]),"#F59E0B")])
    l,r=st.columns(2,gap="large");
    with l: panel("Distribución por actividad",act,height=360)
    with r:
        daily=split.groupby("Fecha",as_index=False)["Piezas"].sum(); fig=go.Figure(); fig.add_scatter(x=daily["Fecha"],y=daily["Piezas"],mode="lines+markers",line=dict(color="#3366CC",width=3),fill="tozeroy"); fig.update_layout(title="Histórico diario",height=390); st.plotly_chart(fig,width="stretch")
    _v25_downloads(f"Detalle Colaborador {selected}",f"{pd.Timestamp(start).strftime('%d/%m/%Y')} al {pd.Timestamp(end).strftime('%d/%m/%Y')}",detail,{**summary,**route_summary,"Colaborador":selected},"v25_employee",{"Actividades":act,"Histórico":split.sort_values("Fecha",ascending=False)})

# Diseño visual V25 inspirado en los mockups corporativos.
st.markdown('''
<style>
:root{--ps-navy:#173B73;--ps-blue:#3366CC;--ps-pink:#E6007E;--ps-violet:#7C3AED;--ps-green:#10B981;--ps-orange:#F59E0B;--ps-red:#EF4444;--ps-bg:#F4F6F9;}
.stApp{background:linear-gradient(180deg,#F8FAFD 0,#F4F6F9 100%)!important;color:#1F2937;}
.block-container{max-width:1540px!important;padding-top:1rem!important;padding-bottom:2.5rem!important;}
.v21-header-brand{display:flex;align-items:center;gap:14px;font-size:25px;font-weight:900;color:var(--ps-navy);letter-spacing:-.5px}.v21-header-brand img{height:58px!important;max-width:150px!important;object-fit:contain!important}
h1,h2,h3{letter-spacing:-.35px;color:#172B4D}.v25-kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:14px 0 22px}.v25-kpi-card{position:relative;background:#fff;border:1px solid #E2E8F0;border-radius:16px;padding:16px 17px 15px;box-shadow:0 8px 24px rgba(23,59,115,.07);overflow:hidden;min-height:118px}.v25-kpi-card:hover{transform:translateY(-2px);box-shadow:0 14px 32px rgba(23,59,115,.11);transition:.2s}.v25-kpi-accent{position:absolute;left:0;top:0;bottom:0;width:5px}.v25-kpi-label{font-size:12px;font-weight:800;color:#667085;text-transform:uppercase;letter-spacing:.55px}.v25-kpi-value{font-size:28px;font-weight:900;color:#172B4D;margin-top:8px;line-height:1}.v25-kpi-sub{font-size:12px;color:#7B8794;margin-top:9px}.panel-title{font-size:17px!important;color:var(--ps-navy)!important;background:#fff;border:1px solid #E2E8F0;border-bottom:0;border-radius:14px 14px 0 0;padding:13px 16px;margin:0!important}.stPlotlyChart{background:#fff;border:1px solid #E2E8F0;border-radius:16px;padding:8px;box-shadow:0 8px 24px rgba(23,59,115,.05)}div[data-testid="stMetric"]{background:#fff!important;border:1px solid #E2E8F0!important;border-radius:15px!important;box-shadow:0 8px 24px rgba(23,59,115,.06)!important}.stButton>button,.stDownloadButton>button{border-radius:10px!important;font-weight:800!important;min-height:42px!important}.stDownloadButton>button{background:var(--ps-navy)!important;color:white!important;border:0!important}.stDownloadButton>button:hover{background:var(--ps-blue)!important}.stTabs [data-baseweb="tab-list"]{gap:8px;background:#EEF3FA;border-radius:12px;padding:5px}.stTabs [data-baseweb="tab"]{border-radius:9px;padding:8px 15px}.stTabs [aria-selected="true"]{background:white;color:var(--ps-navy);box-shadow:0 3px 10px rgba(23,59,115,.08)}
@media(max-width:1100px){.v25-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:620px){.v25-kpi-grid{grid-template-columns:1fr}.v25-kpi-value{font-size:25px}.block-container{padding-left:.8rem!important;padding-right:.8rem!important}}
</style>
''',unsafe_allow_html=True)


ROUTES = {
    "Centro Ejecutivo": lambda: page_resumen(op_all, co_all),
    "Operación Diaria": lambda: page_por_dia(op_all, co_all),
    "Reporte Semanal": lambda: page_semanal(op_all, co_all),
    "Reporte Mensual": lambda: page_mensual(op_all, co_all),
    "Productividad": lambda: page_productividad(op_all, co_all),
    "Recuperación": lambda: page_recuperacion(op_all, co_all),
    "Recorridos": lambda: page_recorridos(op_all, co_all),
    "Reportes": lambda: page_reportes(op_all, co_all),
    "Detalle por Tienda": lambda: page_detalle_tienda_v17(op_all, co_all),
    "Detalle por Colaborador": lambda: page_detalle_colaborador_v17(op_all, co_all),
    "Histórico de Descargas": page_historico_descargas_v17,
    "Alertas Inteligentes": lambda: page_alertas_inteligentes_v17(op_all, co_all),
    "Perfil de Usuario": page_perfil_usuario_v17,
    "Inteligencia Operativa": lambda: page_inteligencia_operativa_v17(op_all, co_all),
    "Centro de Control": page_centro_control,
    "Administración": page_administracion_v17,
    "Configuración de Metas": page_configuracion_metas_v17,
    "Carga de Excel": page_carga_excel_v17,
    "Diagnóstico del Archivo": lambda: page_diagnostico_archivo_v17(op_all, co_all, diag_df),
}

if page in DATA_PAGES and ACTIVE_FILE.exists() and cache_valid():
    window_notes = {
        "Operación Diaria": "Consulta optimizada: último día disponible.",
        "Centro Ejecutivo": "Consulta optimizada: últimas 4 semanas.",
        "Reporte Semanal": "Consulta optimizada: últimas 4 semanas.",
        "Reporte Mensual": "Consulta optimizada: últimos 3 meses.",
        "Productividad": "Consulta optimizada: últimos 30 días.",
        "Recorridos": "Consulta optimizada: semana más reciente.",
        "Recuperación": "Consulta optimizada: últimas 12 semanas.",
    }
    if page in window_notes:
        st.caption(window_notes[page])

# Marcador de despliegue para confirmar que GitHub/Streamlit usa esta versión.
st.caption("PS Operaciones Ropa · V25.3 · Layout, menú y tablas ajustados")

try:
    route_handler = ROUTES.get(page)
    if route_handler is None:
        st.error(f"La página '{page}' no está registrada.")
        page_resumen(op_all, co_all)
    else:
        route_handler()
except Exception as page_error:
    st.error(f"No fue posible abrir la página: {page}")
    st.exception(page_error)


st.markdown('\n<style>\n:root{--ps-primary:#173B73;--ps-secondary:#3366CC;--ps-pink:#E6007E;--ps-bg:#F4F6F9;--ps-text:#1F2937;--ps-muted:#667085;}\n[data-testid="stSidebar"]{min-width:300px!important;max-width:300px!important;}\n[data-testid="stSidebar"]>div{width:300px!important;}\n[data-testid="stMain"]{min-width:0!important;}\n.block-container{max-width:100%!important;padding-left:2rem!important;padding-right:2rem!important;}\n.v20-header{width:100%!important;left:auto!important;right:auto!important;}\n.v20-user-menu,.v20-user-trigger{min-width:220px!important;max-width:280px!important;white-space:normal!important;}\n[data-testid="stHorizontalBlock"]{width:100%!important;gap:1rem!important;}\n[data-testid="stColumn"]{min-width:0!important;}\n@media(max-width:900px){[data-testid="stSidebar"]{min-width:280px!important;max-width:82vw!important}.block-container{padding-left:1rem!important;padding-right:1rem!important}.ps-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}}\n@media(max-width:520px){.ps-kpi-grid{grid-template-columns:1fr!important}}\n</style>\n', unsafe_allow_html=True)

st.markdown(
    """
    <style>
    /* V25.2: menú lateral realmente plegable y perfil compacto. */
    [data-testid="stSidebar"]{
      transition:transform .22s ease,width .22s ease,min-width .22s ease,max-width .22s ease!important;
    }
    [data-testid="stSidebar"][aria-expanded="false"],
    [data-testid="stSidebar"][data-state="collapsed"]{
      transform:translateX(-100%)!important;
      width:0!important;
      min-width:0!important;
      max-width:0!important;
      overflow:hidden!important;
    }
    [data-testid="stAppViewContainer"]:has([data-testid="stSidebar"][aria-expanded="false"]) [data-testid="stMain"],
    [data-testid="stAppViewContainer"]:has([data-testid="stSidebar"][data-state="collapsed"]) [data-testid="stMain"]{
      margin-left:0!important;
      width:100%!important;
      max-width:100%!important;
    }
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapsedControl"]{
      display:flex!important;
      visibility:visible!important;
      opacity:1!important;
      z-index:2000!important;
    }
    /* El botón de cierre nativo del sidebar debe permanecer visible. */
    [data-testid="stSidebar"] button[kind="header"],
    [data-testid="stSidebar"] [data-testid="stBaseButton-header"]{
      display:flex!important;
      visibility:visible!important;
      opacity:1!important;
    }
    /* Página de perfil: ancho ejecutivo controlado, sin campos estirados. */
    [data-testid="stMainBlockContainer"]:has(.ps-profile-page-marker) > div{
      max-width:980px!important;
      margin-left:auto!important;
      margin-right:auto!important;
    }
    [data-testid="stMainBlockContainer"]:has(.ps-profile-page-marker) [data-testid="stTextInputRootElement"],
    [data-testid="stMainBlockContainer"]:has(.ps-profile-page-marker) [data-baseweb="select"]{
      max-width:100%!important;
    }
    @media(max-width:900px){
      [data-testid="stMainBlockContainer"]:has(.ps-profile-page-marker) > div{max-width:100%!important;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)



st.markdown(
    """
    <style>
    /* V25.3: proporciones estables, encabezado compacto y tablas sin desplazamiento horizontal. */
    .v21-header-brand{min-height:64px!important;gap:12px!important;}
    .v21-header-brand img{width:118px!important;height:64px!important;max-width:118px!important;}
    .v21-header-brand span{font-size:25px!important;white-space:nowrap!important;}
    [data-testid="stPopover"] > button p{white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;font-size:14px!important;}
    .ps-profile-row{grid-template-columns:105px minmax(0,1fr)!important;gap:10px!important;padding:10px 12px!important;font-size:14px!important;}
    .ps-profile-row b{white-space:normal!important;word-break:normal!important;overflow-wrap:break-word!important;line-height:1.35!important;}
    .v20-portal-content > [data-testid="stHorizontalBlock"]{align-items:flex-start!important;}
    .v253-alert-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:8px 0 22px;}
    .v253-alert-card{border-radius:13px;padding:14px 16px;min-height:78px;box-shadow:0 5px 16px rgba(23,59,115,.05);display:flex;flex-direction:column;gap:6px;border:1px solid rgba(23,59,115,.06);}
    .v253-alert-card b{font-size:12px;text-transform:uppercase;letter-spacing:.35px;}
    .v253-alert-card span{font-size:14px;font-weight:700;line-height:1.35;}
    [data-testid="stDataFrame"]{overflow-x:hidden!important;}
    @media(max-width:1100px){.v253-alert-grid{grid-template-columns:repeat(2,minmax(0,1fr));}}
    @media(max-width:650px){.v253-alert-grid{grid-template-columns:1fr;}.v21-header-brand span{font-size:19px!important;}}
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="footer">CONFIDENCIAL | Price Shoes | Operaciones Ropa</div>',
    unsafe_allow_html=True,
)
