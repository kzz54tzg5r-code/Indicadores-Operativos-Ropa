"""Configuración central de PS Operaciones Ropa.

Este módulo concentra identidad, versión, colores, rutas y constantes del sistema.
No debe contener contraseñas, tokens ni secretos.
"""
from pathlib import Path

APP_NAME = "PS Operaciones Ropa"
APP_SUBTITLE = "Plataforma Integral de Gestión Operativa"
APP_SLOGAN = "Información confiable. Control total. Decisiones oportunas."
APP_AREA = "Operaciones Ropa"
APP_DIRECTION = "Dirección Ropa"
APP_VERSION = "0.4.0"
APP_BUILD = "2026.07.004"
APP_CACHE_VERSION = "ps-operaciones-ropa-v0.4"

COLOR_PRIMARY = "#10245F"
COLOR_ACCENT = "#EC007C"
COLOR_BACKGROUND = "#F3F6FB"
COLOR_TEXT = "#1F2937"
COLOR_MUTED = "#667085"

DATA_DIR = Path("data")
UPLOAD_DIR = DATA_DIR / "uploads"
CACHE_DIR = DATA_DIR / "cache"
CONFIG_DIR = DATA_DIR / "config"
ASSETS_DIR = Path("assets")
REPORTS_DIR = Path("reports")
ACTIVE_FILE = UPLOAD_DIR / "base_activa.xlsx"
META_FILE = CONFIG_DIR / "metadata.json"
FILE_HISTORY = DATA_DIR / "file_history.json"
DB_FILE = CONFIG_DIR / "usuarios.db"
SESSION_FILE = CONFIG_DIR / "sessions.json"
SESSION_TIMEOUT_HOURS = 8
LOGO_FILE = ASSETS_DIR / "price_shoes_logo.png"

PROJECT_STORES = [
    "Arco Norte", "Ecatepec", "Miravalle", "Puebla Sur", "Vallejo",
]

ROLES = ["OWNER", "ADMIN", "DIRECTOR", "REGIONAL", "TIENDA", "SUPERVISOR", "CONSULTA"]
ROLE_LABELS = {
    "OWNER": "Propietario del Sistema",
    "ADMIN": "Administrador",
    "DIRECTOR": "Director",
    "REGIONAL": "Gerente Regional",
    "TIENDA": "Gerente de Tienda",
    "SUPERVISOR": "Supervisor",
    "CONSULTA": "Consulta",
}

SYSTEM_STATUSES = ["ACTIVE", "READ_ONLY", "MAINTENANCE", "SUSPENDED"]
SYSTEM_STATUS_LABELS = {
    "ACTIVE": "Activo",
    "READ_ONLY": "Solo consulta",
    "MAINTENANCE": "Mantenimiento",
    "SUSPENDED": "Suspendido",
}
