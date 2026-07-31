"""PS Operaciones Ropa — entrada de producción V24.0.1.

Este archivo fuerza la raíz del proyecto al inicio de ``sys.path`` antes de
importar los paquetes locales. Streamlit Cloud puede ejecutar ``app.py`` con un
contexto de importación diferente y, sin esta protección, no encuentra
``core.bootstrap`` aunque la carpeta ``core`` exista en el repositorio.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
project_root_text = str(PROJECT_ROOT)
if project_root_text not in sys.path:
    sys.path.insert(0, project_root_text)

# Comprobación explícita para entregar un error útil cuando se sube solamente
# app.py y se omiten las carpetas del proyecto.
required_paths = (
    PROJECT_ROOT / "core" / "bootstrap.py",
    PROJECT_ROOT / "core" / "settings.py",
    PROJECT_ROOT / "legacy_app.py",
)
missing = [str(path.relative_to(PROJECT_ROOT)) for path in required_paths if not path.exists()]
if missing:
    raise RuntimeError(
        "La instalación está incompleta. Faltan estos archivos del proyecto: "
        + ", ".join(missing)
        + ". Sube el contenido completo del ZIP a la raíz del repositorio, "
          "incluidas las carpetas core, services, pages_app y assets."
    )

from core.bootstrap import initialize_application

initialize_application()

# Ejecuta la capa compatible en el mismo contexto de Streamlit.
_source = PROJECT_ROOT / "legacy_app.py"
exec(compile(_source.read_text(encoding="utf-8"), str(_source), "exec"), globals(), globals())
