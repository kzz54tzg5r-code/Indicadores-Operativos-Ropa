"""Configuración y rutas del módulo comercial."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data" / "commercial"
SALES_DIR = DATA_ROOT / "ventas"
CAPACITY_DIR = DATA_ROOT / "capacidades"
PDF_DIR = DATA_ROOT / "pdfs"
CACHE_DIR = DATA_ROOT / "cache"
BACKUP_DIR = DATA_ROOT / "backups"
MANIFEST_FILE = DATA_ROOT / "manifest.json"
ACTIONS_FILE = DATA_ROOT / "actions.json"
SNAPSHOTS_FILE = DATA_ROOT / "snapshots.json"

COMMERCIAL_PAGES = (
    "Mi Tienda Comercial",
    "Ventas Comerciales",
    "Sugeridos Comerciales",
    "Modelos Comerciales",
    "Utilidad Comercial",
    "Histórico Comercial",
)

ADMIN_PAGE = "Carga Comercial"

PAGE_LABELS = {
    "Mi Tienda Comercial": "Macro compañía",
    "Ventas Comerciales": "Tiendas",
    "Sugeridos Comerciales": "Sección / Rubro",
    "Modelos Comerciales": "Ubicación / Área",
    "Utilidad Comercial": "Dinero y utilidad",
    "Histórico Comercial": "Mi evolución",
    "Carga Comercial": "Carga PDF",
}

STORE_ALIASES = {
    "IZT": "Iztapalapa",
    "IZTAPALAPA": "Iztapalapa",
    "VALLEJO": "Vallejo",
    "ECATEPEC": "Ecatepec",
    "TOLUCA": "Toluca",
    "ARCO NORTE": "Arco Norte",
    "IXTAPALUCA": "Ixtapaluca",
    "QUERETARO": "Querétaro",
    "CENTRO": "Centro",
    "OLIVAR": "Olivar",
    "OLIVAR DEL CONDE": "Olivar",
    "LEON": "León",
    "PUEBLA": "Puebla",
    "PUEBLA SUR": "Puebla Sur",
    "AGUASCALIENTES": "Aguascalientes",
    "VERACRUZ": "Veracruz",
    "NAUCALPAN": "Naucalpan",
    "MIRAVALLE": "Miravalle",
    "ATEMAJAC": "Atemajac",
}

# Códigos utilizados en los nombres de los reportes semanales, por ejemplo
# AC_QRO_17.08.26.pdf o AC_VALL_17.08.26.pdf. Los códigos se comparan como
# segmentos completos para evitar coincidencias accidentales.
STORE_FILENAME_ALIASES = {
    "PUEBLA_SUR": "Puebla Sur",
    "PUE_SUR": "Puebla Sur",
    "PUE_S": "Puebla Sur",
    "PSUR": "Puebla Sur",
    "PBS": "Puebla Sur",
    "ARCO_NORTE": "Arco Norte",
    "ARCO": "Arco Norte",
    "AGS": "Aguascalientes",
    "ATE": "Atemajac",
    "CEN": "Centro",
    "ECA": "Ecatepec",
    "IXTA": "Ixtapaluca",
    "IXT": "Ixtapaluca",
    "IZT": "Iztapalapa",
    "LEO": "León",
    "MIR": "Miravalle",
    "NAU": "Naucalpan",
    "OLI": "Olivar",
    "PUE": "Puebla",
    "QRO": "Querétaro",
    "QUE": "Querétaro",
    "TOL": "Toluca",
    "VALL": "Vallejo",
    "VAL": "Vallejo",
    "VER": "Veracruz",
}

PROJECT_STORES = tuple(dict.fromkeys(STORE_ALIASES.values()))


def ensure_directories() -> None:
    for path in (DATA_ROOT, SALES_DIR, CAPACITY_DIR, PDF_DIR, CACHE_DIR, BACKUP_DIR):
        path.mkdir(parents=True, exist_ok=True)
