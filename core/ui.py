
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from io import BytesIO
from .utils import format_table

def nav(items):
    if not items:
        items = ["Dashboard"]
    if "page" not in st.session_state or st.session_state.page not in items:
        st.session_state.page = items[0]

    st.markdown('<div class="nav-wrap">', unsafe_allow_html=True)
    c0, c1, c2 = st.columns([0.8, 7.8, 0.8])

    with c0:
        if st.button("◀", key="nav_prev", use_container_width=True):
            i = items.index(st.session_state.page)
            st.session_state.page = items[(i - 1) % len(items)]
            st.rerun()

    with c1:
        selected = st.selectbox("Pestaña", items, index=items.index(st.session_state.page), label_visibility="collapsed", key="nav_select")

    with c2:
        if st.button("▶", key="nav_next", use_container_width=True):
            i = items.index(st.session_state.page)
            st.session_state.page = items[(i + 1) % len(items)]
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    if selected != st.session_state.page:
        st.session_state.page = selected
        st.rerun()

    return st.session_state.page

def panel(title, df=None, height=360, editable=False):
    st.markdown(f'<div class="panel"><div class="panel-title">{title}</div>', unsafe_allow_html=True)
    if df is not None:
        if df.empty:
            st.info("Sin información.")
        elif editable:
            st.data_editor(format_table(df), hide_index=True, width="stretch", height=height, num_rows="dynamic")
        else:
            st.dataframe(format_table(df), hide_index=True, width="stretch", height=height)
    st.markdown("</div>", unsafe_allow_html=True)

def kpis(res):
    cols = st.columns(5)
    vals = [
        ("Ingresos", res.get("Ingresos", 0)),
        ("Habilitado", res.get("Acondicionado", 0)),
        ("Ubicado", res.get("Ubicado", 0)),
        ("Pendiente", res.get("Pendiente", 0)),
        ("% Ubicado", f'{res.get("% Ubicado", 0):.1f}%')
    ]
    for col, (label, value) in zip(cols, vals):
        col.metric(label, f"{value:,.0f}" if isinstance(value, (int, float)) else value)

def combined_chart(df, title):
    if df is None or df.empty:
        st.info("Sin información para graficar.")
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["Tienda"], y=df["Total"], mode="lines+markers+text", name="Total", text=df["Total"], textposition="top center"))
    fig.add_trace(go.Bar(x=df["Tienda"], y=df["Habilitadas"], name="Habilitadas"))
    fig.add_trace(go.Bar(x=df["Tienda"], y=df["Ubicadas"], name="Ubicadas"))
    fig.update_layout(
        title=title,
        barmode="group",
        height=430,
        dragmode=False,
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=10, r=10, t=45, b=95),
        legend=dict(orientation="h", y=1.12)
    )
    fig.update_xaxes(fixedrange=True, tickangle=-45)
    fig.update_yaxes(fixedrange=True, gridcolor="#E5E7EB")
    st.plotly_chart(fig, width="stretch", config={"scrollZoom": False, "displayModeBar": False, "doubleClick": False, "responsive": True})

def excel_download(df, name):
    if df is None or df.empty:
        return
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False)
    st.download_button("Descargar Excel", buffer.getvalue(), name, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
