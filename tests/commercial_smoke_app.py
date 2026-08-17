"""Aplicación mínima usada por la prueba de humo de las vistas comerciales."""

import os

import streamlit as st

from commercial.config import ADMIN_PAGE, COMMERCIAL_PAGES
from commercial.ui import render_commercial_page


pages = [*COMMERCIAL_PAGES, ADMIN_PAGE]
requested_page = st.session_state.pop("nav_request", None)
active_page = requested_page if requested_page in pages else os.environ.get(
    "COMMERCIAL_SMOKE_PAGE", "Resumen Comercial"
)
st.session_state["nav_page"] = active_page

# Reproduce el orden real de legacy_app.py: el selector global existe antes de
# que la vista comercial construya su navegación lateral y superior.
if requested_page in pages or st.session_state.get("project_nav_selector") not in pages:
    st.session_state["project_nav_selector"] = active_page
st.selectbox(
    "Selector global de prueba",
    pages,
    index=pages.index(active_page),
    key="project_nav_selector",
    label_visibility="collapsed",
)

render_commercial_page(
    active_page,
    existing_sales=None,
    is_admin=True,
)
