"""Configuración central de PS Operaciones Ropa V24 Producción."""
from pathlib import Path
APP_NAME = "PS Operaciones Ropa"
COMPANY = "Price Shoes"
AREA = "Operaciones Ropa"
DIRECTION = "Ropa"
APP_VERSION = "V54"
APP_BUILD = "Experiencia móvil ejecutiva iOS/Android"
APP_SUBTITLE = "Plataforma Integral de Gestión Operativa"
APP_OBJECTIVE = "Información y decisiones al alcance de la mano, con control, trazabilidad y fluidez operativa."
COLORS = {
    "primary": "#173B73", "secondary": "#3366CC", "pink": "#E6007E",
    "background": "#F4F6F9", "card": "#FFFFFF", "text": "#1F2937", "muted": "#667085",
}
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
CACHE_DIR = DATA_DIR / "cache"
CONFIG_DIR = DATA_DIR / "config"
REPORTS_DIR = DATA_DIR / "reports"
LOG_DIR = DATA_DIR / "logs"
BACKUP_DIR = DATA_DIR / "backups"
ASSETS_DIR = BASE_DIR / "assets"
LOGO_FILE = ASSETS_DIR / "price_shoes_logo.png"
ACTIVE_FILE = UPLOAD_DIR / "base_activa.xlsx"
DB_FILE = CONFIG_DIR / "ps_operaciones.db"
AUDIT_FILE = LOG_DIR / "audit.jsonl"
SESSION_TIMEOUT_MINUTES = 480
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 30
ROLES = ("OWNER","ADMIN","DIRECTOR","REGIONAL","TIENDA","SUPERVISOR","CONSULTA")
SCOPES = ("COMPANY","REGION","STORE","TEAM")
SYSTEM_STATES = ("ACTIVE","READ_ONLY","MAINTENANCE","SUSPENDED","DEMO")
DEFAULT_GOALS = {
    "productividad_diaria": 784.0,
    "recorridos_lunes": 5, "recorridos_martes": 5, "recorridos_miercoles": 5,
    "recorridos_jueves": 8, "recorridos_viernes": 8, "recorridos_sabado": 8,
    "recorridos_domingo": 8, "recorridos_semanal": 47,
    "conversion": 90.0, "recuperacion": 90.0,
    "score_conversion": 0.30, "score_recuperacion": 0.25,
    "score_productividad": 0.20, "score_recorridos": 0.15,
    "score_pendientes": 0.10,
}

# -----------------------------------------------------------------------------
# Compatibilidad con la aplicación heredada V21
# -----------------------------------------------------------------------------
APP_SLOGAN = APP_OBJECTIVE
APP_AREA = AREA
APP_DIRECTION = DIRECTION
APP_CACHE_VERSION = "v54.0.0-pdf-commercial-data"
COLOR_PRIMARY = COLORS["primary"]
COLOR_ACCENT = COLORS["pink"]
COLOR_BACKGROUND = COLORS["background"]
META_FILE = CONFIG_DIR / "active_file_meta.json"
FILE_HISTORY = CONFIG_DIR / "file_history.json"
SESSION_FILE = CONFIG_DIR / "sessions.json"
SESSION_TIMEOUT_HOURS = max(1, SESSION_TIMEOUT_MINUTES // 60)
PROJECT_STORES = (
    "Iztapalapa", "Vallejo", "Ecatepec", "Toluca", "Arco Norte",
    "Ixtapaluca", "Querétaro", "Centro", "Olivar", "León", "Puebla",
    "Puebla Sur", "Aguascalientes", "Veracruz", "Naucalpan", "Miravalle",
    "Atemajac",
)
ROLE_LABELS = {
    "OWNER": "Propietario del Sistema",
    "ADMIN": "Administrador",
    "DIRECTOR": "Director",
    "REGIONAL": "Regional",
    "TIENDA": "Tienda",
    "SUPERVISOR": "Supervisor",
    "CONSULTA": "Consulta",
}
SYSTEM_STATUSES = SYSTEM_STATES
SYSTEM_STATUS_LABELS = {
    "ACTIVE": "Activo",
    "READ_ONLY": "Solo lectura",
    "MAINTENANCE": "Mantenimiento",
    "SUSPENDED": "Suspendido",
    "DEMO": "Demostración",
}
PROCESS_STATUS_FILE = CONFIG_DIR / "process_status.json"
PROCESS_LOCK_FILE = CONFIG_DIR / "process.lock"
PROCESS_LOG_FILE = LOG_DIR / "process_error.log"
