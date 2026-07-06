
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import json

CONFIG = Path("config")
UPLOAD = Path("data/uploads")
ACTIVE_FILE = UPLOAD / "base_activa.xlsx"

CONFIG.mkdir(parents=True, exist_ok=True)
UPLOAD.mkdir(parents=True, exist_ok=True)

def read_json(name, default):
    p = CONFIG / name
    if not p.exists():
        p.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default

def write_json(name, data):
    (CONFIG / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def load_users():
    return read_json("usuarios.json", [{"nomina":"admin","nombre":"Administrador","correo":"","permiso":"Administrador","password":"admin123","activo":True}])

def save_users(users):
    write_json("usuarios.json", users)

def load_project():
    return read_json("proyecto.json", {
        "nombre": "Indicadores Operaciones Ropa",
        "subtitulo": "Plataforma Ejecutiva de Recuperación de Mercancía",
        "tiendas_proyecto": ["Arco Norte", "Ecatepec", "Miravalle", "Puebla Sur", "Vallejo"],
        "pestanas": ["Dashboard", "Por Día", "Reporte Semanal", "Reporte Mensual", "Conversión", "Recuperación Económica", "Productividad", "Recorridos", "Rankings", "Macro", "Diagnóstico", "Configuración", "Usuarios"]
    })

def save_project(data):
    write_json("proyecto.json", data)

def load_goals():
    return read_json("metas.json", {"productividad_diaria": 784, "recorridos_semanal": 47, "conversion_meta": 90.0})

def save_goals(data):
    write_json("metas.json", data)

def save_uploaded_file(uploaded_file):
    with open(ACTIVE_FILE, "wb") as f:
        f.write(uploaded_file.getbuffer())
    write_json("metadata.json", {"archivo": uploaded_file.name, "fecha_carga": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

def get_metadata():
    return read_json("metadata.json", {})

def delete_active_file():
    if ACTIVE_FILE.exists():
        ACTIVE_FILE.unlink()
