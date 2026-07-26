"""Compatibilidad de autenticación para módulos heredados.

La autenticación principal usa SQLite + Argon2id desde app.py.
"""
import streamlit as st


def login():
    return st.session_state.get("user")


def require_login():
    user = login()
    if not user:
        st.error("Inicia sesión desde la pantalla principal de PS Operaciones Ropa.")
        st.stop()
    return user
