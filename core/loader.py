
from __future__ import annotations
import pandas as pd
import numpy as np
from .utils import *

OP_KEYS = ["ACTIVIDAD", "NOMBRE", "NUMERO DE PIEZAS", "PIEZAS", "RECORRIDOS", "HABILITADO", "UBICADO"]
COM_KEYS = ["DEV", "VTA", "VENTA", "COSTO", "MODELO", "ID", "COLOR"]

def classify_sheet(name, df):
    n = norm_text(name)
    text = " ".join([n] + [norm_text(c) for c in df.columns])
    if "PLANTILLA" in n:
        return "plantilla"
    if "RESULTADOS" in n and "PRODUCT" in n:
        return "operacion"
    if any(m in n for m in ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]):
        return "comercial"
    score_op = sum(k in text for k in OP_KEYS)
    score_co = sum(k in text for k in COM_KEYS)
    if score_co > score_op:
        return "comercial"
    if score_op > 0:
        return "operacion"
    return "otra"

def build_nombre_map(sheets):
    mapping = {"ELO": "Eloisa", "ELOISA": "Eloisa", "IVON": "Ivonne", "IVONNE": "Ivonne"}
    for sheet_name, df in sheets.items():
        if "PLANTILLA" not in norm_text(sheet_name) or df.empty:
            continue
        c_nombre = find_col(df, ["Nombre", "Nombre completo", "Colaborador"])
        c_alias = find_col(df, ["Alias", "Usuario", "Nombre corto", "Registro"])
        if c_nombre is None:
            continue
        for _, row in df.iterrows():
            nombre = str(row.get(c_nombre, "")).strip()
            if not nombre or nombre.lower() == "nan":
                continue
            keys = {nombre.split()[0], nombre.split()[0][:3], nombre.split()[0][:4]}
            if c_alias:
                alias = str(row.get(c_alias, "")).strip()
                if alias and alias.lower() != "nan":
                    keys.add(alias)
            for k in keys:
                mapping[norm_text(k)] = nombre
    return mapping

def normalize_operation(df, sheet, nombre_map):
    c_fecha = find_col(df, ["Fecha"])
    c_tienda = best_tienda_col(df)
    c_nombre = find_col(df, ["Nombre", "Usuario", "Colaborador"])
    c_act = find_col(df, ["Actividad Realizada", "Actividad", "Tabla"])
    c_piezas = find_col(df, ["Número de Piezas", "Numero de Piezas", "Piezas", "Cantidad"])
    c_motivo = find_col(df, ["Motivo de ingreso", "Motivo"])
    c_area = find_col(df, ["Área", "Area"])
    c_rec = find_col(df, ["Recorridos", "RECORRIDOS"])
    c_hab = find_col(df, ["Habilitado", "Acondicionado"])
    c_ubi = find_col(df, ["Ubicado", "Ubicadas"])

    out = pd.DataFrame()
    out["Hoja"] = sheet
    out["Fecha"] = pd.to_datetime(df[c_fecha], errors="coerce", dayfirst=True) if c_fecha else pd.NaT
    out["Tienda"] = df[c_tienda].map(canon_tienda) if c_tienda else ""
    out["Nombre Original"] = df[c_nombre].astype(str).str.strip() if c_nombre else ""
    out["Nombre"] = out["Nombre Original"].map(lambda x: nombre_map.get(norm_text(x), x))
    out["Actividad Realizada"] = df[c_act].astype(str).str.strip() if c_act else ""
    out["Motivo de ingreso"] = df[c_motivo].astype(str).str.strip() if c_motivo else ""
    out["Área"] = df[c_area].astype(str).str.strip() if c_area else ""
    out["Número de Piezas"] = to_number(df[c_piezas]) if c_piezas else 0

    act = out["Actividad Realizada"].map(norm_text)
    pzs = out["Número de Piezas"]
    out["Acondicionado"] = to_number(df[c_hab]) if c_hab else np.where(act.str.contains("HABIL|ACONDICION", na=False), pzs, 0)
    out["Ubicado"] = to_number(df[c_ubi]) if c_ubi else np.where(act.str.contains("UBIC", na=False), pzs, 0)
    out["Recorridos"] = to_number(df[c_rec]) if c_rec else np.where(act.str.contains("RECORR", na=False), 1, 0)

    out = out[out["Tienda"].astype(str).str.len() > 0]
    out = out[~out["Tienda"].astype(str).str.isdigit()]
    out["Semana ISO"] = out["Fecha"].dt.isocalendar().week.astype("Int64")
    out["Mes"] = out["Fecha"].dt.strftime("%Y-%m")
    return out

def normalize_commercial_long(df, sheet):
    c_dev = find_col(df, ["Dev Pzs", "Dev_pzs", "Devolucion Pzs", "Devolución Pzs"])
    if not c_dev:
        return pd.DataFrame()

    c_fecha = find_col(df, ["Fecha"])
    c_tienda = best_tienda_col(df)
    c_id = find_col(df, ["ID", "Modelo", "ID/Modelo"])
    c_color = find_col(df, ["Color"])
    c_vta = find_col(df, ["Ventas Netas Pzs", "Vta_Pzs", "Venta Pzs"])
    c_imp = find_col(df, ["Venta Neta", "Vta_Imp", "Venta Importe", "Venta Neta en $"])
    c_costo = find_col(df, ["Costo Dev", "Costo_Dev", "Costo"])

    out = pd.DataFrame()
    out["Hoja"] = sheet
    out["Fecha"] = pd.to_datetime(df[c_fecha], errors="coerce", dayfirst=True) if c_fecha else pd.NaT
    out["Tienda"] = df[c_tienda].map(canon_tienda) if c_tienda else ""
    out["ID/Modelo"] = df[c_id].astype(str).str.strip() if c_id else ""
    out["Color"] = df[c_color].astype(str).str.strip() if c_color else ""
    out["Dev_Pzs"] = to_number(df[c_dev])
    out["Vta_Pzs"] = to_number(df[c_vta]) if c_vta else 0
    out["Vta_Imp"] = to_number(df[c_imp]) if c_imp else 0
    out["Costo_Dev"] = to_number(df[c_costo]) if c_costo else 0
    out["Semana ISO"] = out["Fecha"].dt.isocalendar().week.astype("Int64")
    out["Mes"] = out["Fecha"].dt.strftime("%Y-%m")
    return out

def normalize_commercial_wide(df, sheet):
    rows = []
    cols = list(df.columns)
    for idx, col in enumerate(cols):
        n = norm_text(col)
        if "DEV" not in n or "PZS" not in n:
            continue

        fecha = None
        for j in range(idx, max(-1, idx - 6), -1):
            parsed = pd.to_datetime(str(cols[j]), errors="coerce", dayfirst=True)
            if pd.notna(parsed):
                fecha = parsed
                break

        if fecha is None:
            continue

        tmp = pd.DataFrame({
            "Hoja": sheet,
            "Fecha": fecha,
            "Tienda": "",
            "ID/Modelo": "",
            "Color": "",
            "Dev_Pzs": to_number(df[col]),
            "Vta_Pzs": 0,
            "Vta_Imp": 0,
            "Costo_Dev": 0
        })

        for j in range(max(0, idx - 4), min(len(cols), idx + 5)):
            nj = norm_text(cols[j])
            if "VENTA" in nj and "PZS" in nj:
                tmp["Vta_Pzs"] = to_number(df[cols[j]])
            if "VENTA" in nj and ("$" in str(cols[j]) or "IMP" in nj or "NETA EN" in nj):
                tmp["Vta_Imp"] = to_number(df[cols[j]])

        tmp = tmp[tmp["Dev_Pzs"] != 0]
        if not tmp.empty:
            rows.append(tmp)

    if not rows:
        return pd.DataFrame()

    out = pd.concat(rows, ignore_index=True)
    out["Semana ISO"] = out["Fecha"].dt.isocalendar().week.astype("Int64")
    out["Mes"] = out["Fecha"].dt.strftime("%Y-%m")
    return out

def load_excel(path):
    sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
    nombre_map = build_nombre_map(sheets)
    operations, commercials, diagnostics = [], [], []

    for sheet_name, df in sheets.items():
        kind = classify_sheet(sheet_name, df)
        diagnostics.append({
            "Hoja": sheet_name,
            "Tipo": kind,
            "Filas": len(df),
            "Columnas": len(df.columns),
            "Col Tienda detectada": str(best_tienda_col(df)),
            "Candidatas Tienda": ", ".join(map(str, tienda_candidate_cols(df)))
        })

        if kind == "operacion":
            operations.append(normalize_operation(df, sheet_name, nombre_map))
        elif kind == "comercial":
            com = normalize_commercial_long(df, sheet_name)
            if com.empty:
                com = normalize_commercial_wide(df, sheet_name)
            if not com.empty:
                commercials.append(com)

    op = pd.concat(operations, ignore_index=True) if operations else pd.DataFrame()
    co = pd.concat(commercials, ignore_index=True) if commercials else pd.DataFrame()
    return op, co, pd.DataFrame(diagnostics), nombre_map
