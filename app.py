
from pathlib import Path
import streamlit as st
from core.styles import apply_styles, header
from core.auth import require_login
from core.storage import ACTIVE_FILE, save_uploaded_file, get_metadata, delete_active_file, load_project, load_goals
from core.loader import load_excel
from core.ui import nav
from pages_app import pages

st.set_page_config(page_title="Indicadores Operaciones Ropa", page_icon="📊", layout="wide")

apply_styles()
user = require_login()
project = load_project()

st.sidebar.divider()
st.sidebar.markdown("## 📁 Archivo")

metadata = get_metadata()
if ACTIVE_FILE.exists():
    st.sidebar.success("Archivo cargado")
    st.sidebar.caption(metadata.get("archivo", ""))
else:
    st.sidebar.warning("Sin archivo")

if user.get("permiso") == "Administrador":
    uploaded = st.sidebar.file_uploader("Cargar Excel", type=["xlsx"])
    if uploaded and st.sidebar.button("Procesar archivo", type="primary", use_container_width=True):
        save_uploaded_file(uploaded)
        st.cache_data.clear()
        st.rerun()

    if ACTIVE_FILE.exists() and st.sidebar.button("Borrar archivo", use_container_width=True):
        delete_active_file()
        st.cache_data.clear()
        st.rerun()

header(user, project)

if not ACTIVE_FILE.exists():
    st.warning("Carga el archivo Excel desde el panel lateral.")
    st.stop()

@st.cache_data(show_spinner=False)
def cached_load(path, mtime):
    return load_excel(path)

op, co, diag, nombre_map = cached_load(str(ACTIVE_FILE), ACTIVE_FILE.stat().st_mtime)

metas = load_goals()
items = project.get("pestanas", ["Dashboard", "Por Día", "Reporte Semanal", "Reporte Mensual", "Conversión", "Recuperación Económica", "Productividad", "Recorridos", "Rankings", "Macro", "Diagnóstico", "Configuración", "Usuarios"])
page = nav(items)

ctx = {
    "op": op,
    "co": co,
    "diag": diag,
    "nombre_map": nombre_map,
    "tiendas": project.get("tiendas_proyecto", []),
    "metas": metas,
    "user": user,
}

if page == "Dashboard":
    pages.dashboard(ctx)
elif page == "Por Día":
    pages.por_dia(ctx)
elif page == "Reporte Semanal":
    pages.semanal(ctx)
elif page == "Reporte Mensual":
    pages.mensual(ctx)
elif page == "Conversión":
    pages.conversion_page(ctx)
elif page == "Recuperación Económica":
    pages.recuperacion(ctx)
elif page == "Productividad":
    pages.productividad_page(ctx)
elif page == "Recorridos":
    pages.simple_table(ctx, "Recorridos", op)
elif page == "Rankings":
    pages.simple_table(ctx, "Rankings", op)
elif page == "Macro":
    pages.simple_table(ctx, "Macro", op)
elif page == "Diagnóstico":
    pages.simple_table(ctx, "Diagnóstico", diag)
elif page == "Configuración":
    pages.configuracion(ctx)
elif page == "Usuarios":
    pages.usuarios(ctx)

st.markdown("---")
st.caption("CONFIDENCIAL | Price Shoes | Operaciones Ropa")
