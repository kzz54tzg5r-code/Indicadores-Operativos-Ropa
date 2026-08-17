"""Módulo de Ventas y Análisis Comercial de PS Operaciones Ropa.

La interfaz se carga de forma diferida para que los analizadores de archivos se
puedan usar también en tareas de validación y mantenimiento sin iniciar
Streamlit ni Plotly.
"""

__all__ = ["render_commercial_page", "render_commercial_sidebar"]


def __getattr__(name: str):
    if name in __all__:
        from .ui import render_commercial_page, render_commercial_sidebar

        return {
            "render_commercial_page": render_commercial_page,
            "render_commercial_sidebar": render_commercial_sidebar,
        }[name]
    raise AttributeError(name)
