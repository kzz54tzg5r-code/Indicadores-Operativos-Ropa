"""Aplicación mínima usada por la prueba de humo de las vistas comerciales."""

import os

from commercial.ui import render_commercial_page


render_commercial_page(
    os.environ.get("COMMERCIAL_SMOKE_PAGE", "Resumen Comercial"),
    existing_sales=None,
    is_admin=True,
)
