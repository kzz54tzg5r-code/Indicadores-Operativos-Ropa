"""PS Operaciones Ropa — entrada de producción V24.

La implementación histórica se conserva en ``legacy_app.py`` como capa de
compatibilidad mientras los servicios y controles empresariales viven en
módulos independientes. Esto evita eliminar funcionalidad ya operativa.
"""
from core.bootstrap import initialize_application
initialize_application()

# Ejecuta la capa de compatibilidad en el mismo contexto de Streamlit.
from pathlib import Path
_source = Path(__file__).with_name("legacy_app.py")
exec(compile(_source.read_text(encoding="utf-8"), str(_source), "exec"), globals(), globals())
