"""PS Operaciones Ropa — entrada de producción V24.0.1.

Este archivo fuerza la raíz del proyecto al inicio de ``sys.path`` antes de
importar los paquetes locales. Streamlit Cloud puede ejecutar ``app.py`` con un
contexto de importación diferente y, sin esta protección, no encuentra
``core.bootstrap`` aunque la carpeta ``core`` exista en el repositorio.
"""
from __future__ import annotations

import sys
import time
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

_boot_started = time.perf_counter()
print("[BOOT] app.py iniciado", flush=True)
try:
    initialize_application()
    print(f"[BOOT] bootstrap listo en {time.perf_counter()-_boot_started:.2f}s", flush=True)
except Exception as exc:
    print(f"[BOOT][ERROR] bootstrap: {type(exc).__name__}: {exc}", flush=True)
    raise

# Ejecuta la capa compatible en el mismo contexto de Streamlit.
_source = PROJECT_ROOT / "legacy_app.py"
try:
    print("[BOOT] iniciando legacy_app.py", flush=True)
    _legacy_text = _source.read_text(encoding="utf-8")
    exec(compile(_legacy_text, str(_source), "exec"), globals(), globals())
    print(f"[BOOT] legacy_app.py finalizó en {time.perf_counter()-_boot_started:.2f}s", flush=True)
except Exception as exc:
    print(f"[BOOT][ERROR] legacy_app.py: {type(exc).__name__}: {exc}", flush=True)
    try:
        import streamlit as st
        st.error("No fue posible iniciar PS Operaciones Ropa.")
        st.exception(exc)
        st.stop()
    except Exception:
        raise
