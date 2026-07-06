
from __future__ import annotations
import re
import unicodedata
import pandas as pd
import numpy as np

PROJECT_TIENDAS = [
    "Iztapalapa", "Vallejo", "Ecatepec", "Toluca", "Arco Norte", "Ixtapaluca",
    "Querétaro", "Centro", "Olivar", "León", "Puebla", "Puebla Sur",
    "Aguascalientes", "Veracruz", "Naucalpan", "Miravalle", "Atemajac"
]

def norm_text(x) -> str:
    s = "" if x is None else str(x).strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s+", " ", s)
    return s.upper()

TIENDA_MAP = {norm_text(t): t for t in PROJECT_TIENDAS}
TIENDA_MAP.update({
    "QUERETARO": "Querétaro",
    "LEON": "León",
    "PUEBLA SUR": "Puebla Sur",
    "ARCO NORTE": "Arco Norte",
})

def canon_tienda(x) -> str:
    s = "" if x is None else str(x).strip()
    if not s or s.upper() == "NAN" or s.isdigit():
        return ""
    n = norm_text(s)
    if n in TIENDA_MAP:
        return TIENDA_MAP[n]
    for k, v in TIENDA_MAP.items():
        if k in n:
            return v
    return s.title()

def exact_col(df, name):
    target = norm_text(name)
    for c in df.columns:
        if norm_text(c) == target:
            return c
    return None

def find_col(df, candidates):
    for cand in candidates:
        c = exact_col(df, cand)
        if c is not None:
            return c
    for c in df.columns:
        nc = norm_text(c)
        if any(norm_text(cand) in nc for cand in candidates):
            return c
    return None

def tienda_candidate_cols(df):
    return [c for c in df.columns if norm_text(c) == "TIENDA" or norm_text(c).startswith("TIENDA.")]

def best_tienda_col(df):
    candidates = tienda_candidate_cols(df)
    if not candidates:
        return find_col(df, ["Tienda", "Sucursal"])

    valid = [norm_text(t) for t in PROJECT_TIENDAS]
    best = candidates[0]
    best_score = -10**9

    for c in candidates:
        s = df[c].astype(str).fillna("").str.strip()
        n = s.map(norm_text)
        numeric_ratio = pd.to_numeric(s, errors="coerce").notna().mean() if len(s) else 1
        store_hits = sum(n.str.contains(v, na=False).sum() for v in valid)
        non_empty = (s != "").sum()
        score = store_hits * 100 + non_empty - numeric_ratio * len(s) * 50
        if score > best_score:
            best_score = score
            best = c

    return best

def to_number(s):
    if isinstance(s, pd.Series):
        ser = s
    else:
        ser = pd.Series(s)
    return pd.to_numeric(
        ser.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .replace({"-": "0", "nan": "0", "None": "0"}),
        errors="coerce"
    ).fillna(0)

def safe_div(a, b):
    try:
        return float(a) / float(b) * 100 if float(b) else 0
    except Exception:
        return 0

def fmt_num(x):
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return "0"

def fmt_pct(x):
    try:
        return f"{float(x):,.1f}%"
    except Exception:
        return "0.0%"

def fmt_money(x):
    try:
        return f"${float(x):,.0f}"
    except Exception:
        return "$0"

def format_table(df):
    if df is None or df.empty:
        return df
    out = df.copy()
    for c in out.columns:
        cname = str(c).lower()
        if str(c).startswith("%"):
            out[c] = out[c].apply(fmt_pct)
        elif pd.api.types.is_numeric_dtype(out[c]) and any(k in cname for k in ["pzs", "piezas", "total", "pend", "muertos", "cajas", "probador", "recolect", "habil", "ubic", "dev", "ingreso", "venta", "recuper"]):
            out[c] = out[c].apply(fmt_num)
    return out
