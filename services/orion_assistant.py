# -*- coding: utf-8 -*-
"""ORION - asistente virtual basado exclusivamente en datos calculados del portal.

La IA nunca recibe la base cruda completa. Recibe únicamente un paquete de
métricas/tablas agregadas generado por el motor de PS Operaciones Ropa.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def infer_intent(question: str) -> str:
    q = (question or "").lower()
    if any(x in q for x in ("productividad", "colaborador", "persona", "ranking de personal", "top colabor")):
        return "productividad"
    if any(x in q for x in ("recorrido", "recorridos")):
        return "recorridos"
    if any(x in q for x in ("recuper", "conversion", "conversión", "devol", "pendiente $", "pendiente econom")):
        return "recuperacion"
    if any(x in q for x in ("acondicion", "habilit", "ubicad", "ingres", "muertos", "cajas", "probador", "pendiente por ubicar", "operacion", "operación")):
        return "operacion"
    if any(x in q for x in ("score", "prioridad", "prioridades", "alerta", "riesgo", "atencion", "atención", "resumen")):
        return "ejecutivo"
    return "general"


def infer_period(question: str, latest_date, pd_module):
    """Devuelve (inicio, fin, etiqueta) usando lenguaje natural básico en español."""
    pd = pd_module
    latest = pd.Timestamp(latest_date).normalize()
    q = (question or "").lower()

    # Semana ISO explícita: semana 28 / semana 28 de 2026
    m = re.search(r"semana\s*(\d{1,2})(?:\s*(?:de|del)?\s*(20\d{2}))?", q)
    if m:
        week = int(m.group(1)); year = int(m.group(2) or latest.isocalendar().year)
        try:
            start = pd.Timestamp.fromisocalendar(year, week, 1).normalize()
            return start, start + pd.Timedelta(days=6), f"Semana {week:02d} de {year}"
        except Exception:
            pass

    # Mes por nombre, con año opcional.
    for name, number in MONTHS_ES.items():
        if name in q:
            ym = re.search(rf"{name}\s*(?:de|del)?\s*(20\d{{2}})?", q)
            year = int(ym.group(1)) if ym and ym.group(1) else latest.year
            p = pd.Period(f"{year}-{number:02d}", freq="M")
            return p.start_time.normalize(), p.end_time.normalize(), f"{name.capitalize()} {year}"

    if "hoy" in q or "día de hoy" in q or "dia de hoy" in q:
        return latest, latest, latest.strftime("%d/%m/%Y")
    if "ayer" in q:
        d = latest - pd.Timedelta(days=1)
        return d, d, d.strftime("%d/%m/%Y")
    if "semana actual" in q or "esta semana" in q or "semana en curso" in q:
        start = latest - pd.Timedelta(days=latest.weekday())
        return start, start + pd.Timedelta(days=6), f"Semana {latest.isocalendar().week:02d} de {latest.isocalendar().year}"
    if "mes actual" in q or "este mes" in q or "mes en curso" in q:
        p = latest.to_period("M")
        return p.start_time.normalize(), p.end_time.normalize(), p.strftime("%Y-%m")

    # Fecha dd/mm/yyyy o yyyy-mm-dd
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", q)
    if m:
        d = pd.Timestamp(year=int(m.group(3)), month=int(m.group(2)), day=int(m.group(1)))
        return d, d, d.strftime("%d/%m/%Y")
    m = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", q)
    if m:
        d = pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=int(m.group(3)))
        return d, d, d.strftime("%d/%m/%Y")

    # Default: mes de la última fecha real.
    p = latest.to_period("M")
    return p.start_time.normalize(), p.end_time.normalize(), p.strftime("%Y-%m")


def detect_stores(question: str, stores: list[str]) -> list[str]:
    q = (question or "").lower()
    found = [s for s in stores if s and s.lower() in q]
    return found


def compact_records(df, columns: list[str], limit: int = 20):
    if df is None or getattr(df, "empty", True):
        return []
    use = [c for c in columns if c in df.columns]
    if not use:
        return []
    out = df[use].head(limit).copy()
    for c in out.columns:
        try:
            out[c] = out[c].where(out[c].notna(), None)
        except Exception:
            pass
    return out.to_dict(orient="records")


def deterministic_answer(question: str, evidence: dict[str, Any]) -> str:
    intent = evidence.get("intent", "general")
    period = evidence.get("period_label", "periodo consultado")
    stores = evidence.get("stores_label", "alcance autorizado")
    k = evidence.get("kpis", {})
    ranking = evidence.get("ranking", [])
    prod = evidence.get("productivity", [])
    routes = evidence.get("routes", [])

    if not evidence.get("has_data"):
        return f"No encontré información disponible para {period} dentro de {stores}. No voy a estimar ni inventar datos."

    if intent == "recuperacion":
        base = (
            f"Para {period}, la conversión es {k.get('conversion', 0):.1f}% y la recuperación económica "
            f"es {k.get('recuperacion_economica', 0):.1f}%, equivalente a ${k.get('recuperacion_pesos', 0):,.0f}."
        )
        if ranking:
            r = ranking[0]
            base += f" La tienda con mejor recuperación económica en la tabla consultada es {r.get('Tienda', 'N/D')} con {float(r.get('Recup. %', r.get('% Recuperación económica', 0)) or 0):.1f}%."
        return base

    if intent == "operacion":
        text = (
            f"Para {period}, se registran {k.get('piezas_ingresadas', 0):,.0f} piezas ingresadas, "
            f"{k.get('acondicionadas', 0):,.0f} acondicionadas y {k.get('ubicadas', 0):,.0f} ubicadas. "
            f"El pendiente por ubicar es {k.get('pendiente_ubicar', 0):,.0f} piezas."
        )
        ops = evidence.get("operation", [])
        if ops:
            top = sorted(ops, key=lambda r: float(r.get("Pend. Ub.", 0) or 0), reverse=True)[:3]
            top = [r for r in top if float(r.get("Pend. Ub.", 0) or 0) > 0]
            if top:
                text += " Mayores pendientes: " + "; ".join(f"{r.get('Tienda')}: {float(r.get('Pend. Ub.',0) or 0):,.0f} pzas" for r in top) + "."
        return text

    if intent == "productividad":
        if prod:
            top = prod[0]
            name = top.get("Nombre Real") or top.get("Colaborador") or top.get("Nombre") or "N/D"
            return (
                f"Para {period}, la productividad promedio es {k.get('productividad', 0):,.0f} pzs/día "
                f"({k.get('productividad_pct', 0):.1f}% de la meta). El mejor registro visible es {name} "
                f"de {top.get('Tienda', 'N/D')}."
            )
        return f"Para {period}, la productividad promedio es {k.get('productividad', 0):,.0f} pzs/día ({k.get('productividad_pct', 0):.1f}% de la meta)."

    if intent == "recorridos":
        return (
            f"Para {period}, se realizaron {k.get('recorridos_realizados', 0):,.0f} recorridos de una meta de "
            f"{k.get('recorridos_meta', 0):,.0f}, con {k.get('recorridos_pct', 0):.1f}% de cumplimiento."
        )

    return (
        f"Resumen de {period}: {k.get('piezas_ingresadas', 0):,.0f} piezas ingresadas; "
        f"conversión {k.get('conversion', 0):.1f}%; recuperación económica {k.get('recuperacion_economica', 0):.1f}%; "
        f"productividad {k.get('productividad', 0):,.0f} pzs/día; recorridos {k.get('recorridos_pct', 0):.1f}%; "
        f"PS Score {k.get('ps_score', 0):.1f}."
    )


def _extract_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"].strip()
    texts = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") in ("output_text", "text") and content.get("text"):
                texts.append(str(content["text"]))
    return "\n".join(texts).strip()


def ask_openai(question: str, evidence: dict[str, Any], api_key: str, model: str = "gpt-5-mini", feedback_context: list[dict[str, Any]] | None = None, timeout: int = 45) -> str:
    """Usa Responses API. Solo recibe evidencia agregada; store=false por privacidad."""
    if not api_key:
        raise ValueError("OPENAI_API_KEY no configurada")
    feedback_context = feedback_context or []
    instructions = (
        "Eres ORION, asistente operativo de PS Operaciones Ropa. Responde en español ejecutivo y claro. "
        "REGLA CRÍTICA: usa EXCLUSIVAMENTE la evidencia JSON proporcionada. No inventes cifras, causas ni hechos. "
        "Si la evidencia no permite responder algo, dilo explícitamente. Diferencia hechos de recomendaciones. "
        "Los cálculos de KPI ya vienen hechos por el motor del sistema; no los recalcules con supuestos. "
        "Cuando recomiendes acciones, vincúlalas con un dato concreto y usa frases como 'sugiero' o 'podría'. "
        "No menciones que recibiste JSON. Mantén la respuesta compacta, salvo que el usuario pida detalle."
    )
    prompt = {
        "pregunta": question,
        "evidencia_calculada": evidence,
        "retroalimentacion_previa_relevante": feedback_context[-5:],
    }
    body = {
        "model": model,
        "store": False,
        "instructions": instructions,
        "input": json.dumps(prompt, ensure_ascii=False, default=str),
    }
    req = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:600]
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"No fue posible conectar con OpenAI API: {exc.reason}") from exc
    text = _extract_output_text(payload)
    if not text:
        raise RuntimeError("OpenAI API no devolvió texto utilizable")
    return text


def load_feedback(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except Exception:
        return []
    return rows[-200:]


def save_feedback(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"timestamp": datetime.utcnow().isoformat() + "Z", **payload}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
