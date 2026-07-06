
import streamlit as st
from .storage import load_users

def login():
    st.sidebar.markdown("## 🔐 Acceso")

    if st.session_state.get("user"):
        u = st.session_state.user
        st.sidebar.success(u.get("nombre", u.get("nomina", "")))
        st.sidebar.caption(u.get("permiso", "Consulta"))
        if st.sidebar.button("Cerrar sesión", use_container_width=True):
            st.session_state.pop("user", None)
            st.rerun()
        return u

    nom = st.sidebar.text_input("Nómina / Usuario")
    pwd = st.sidebar.text_input("Contraseña", type="password")

    if st.sidebar.button("Iniciar sesión", type="primary", use_container_width=True):
        for u in load_users():
            if u.get("activo", True) and str(u.get("nomina", "")).strip() == nom.strip() and str(u.get("password", "")) == pwd:
                st.session_state.user = u
                st.rerun()
        st.sidebar.error("Usuario o contraseña incorrectos.")

    return None

def require_login():
    user = login()
    if not user:
        st.markdown("""
        <div style="max-width:720px;margin:9vh auto;background:white;border:1px solid #d9e2f0;border-radius:24px;padding:34px;box-shadow:0 18px 45px rgba(16,36,95,.10)">
            <h1 style="color:#10245F;margin:0">Acceso al Sistema</h1>
            <p style="color:#64748B;font-weight:600">Indicadores Operaciones Ropa</p>
            <div style="background:#EEF5FF;border:1px solid #DBEAFE;border-radius:16px;padding:16px;color:#10245F;font-weight:800">
                Para visualizar la información, inicia sesión con un usuario autorizado.
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.stop()
    return user
