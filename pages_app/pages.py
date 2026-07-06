
import streamlit as st
import pandas as pd
import plotly.express as px
from core.styles import section
from core.ui import panel, kpis, combined_chart, excel_download
from core.calculations import resumen_ejecutivo, operational_table, productividad, indice_actividades, conversion
from core.pdf import pdf_bytes
from core.utils import fmt_num, fmt_pct, fmt_money, PROJECT_TIENDAS
from core.storage import load_project, save_project, load_users, save_users, save_goals

def download_pdf(title, df=None, resumen=None):
    st.download_button("Descargar PDF", pdf_bytes(title, df, resumen), f"{title.lower().replace(' ', '_')}.pdf", "application/pdf")

def dashboard(ctx):
    op = ctx["op"]
    tiendas = ctx["tiendas"]
    if not op.empty and "Tienda" in op:
        op = op[op["Tienda"].isin(tiendas)]
    res = resumen_ejecutivo(op)
    section("Dashboard Ejecutivo", "Resumen operativo del proyecto.")
    kpis(res)

    table = operational_table(op, tiendas)
    download_pdf("Dashboard Ejecutivo", table, res)
    panel("Resumen por tienda", table, 380)
    combined_chart(table, "Ingresos vs Habilitadas y Ubicadas")

def por_dia(ctx):
    op = ctx["op"]
    tiendas = ctx["tiendas"]
    section("Por Día", "Filtro calendario y tabla por tienda.")

    fechas = sorted(pd.to_datetime(op["Fecha"], errors="coerce").dropna().dt.date.unique().tolist()) if not op.empty and "Fecha" in op else []
    fecha = st.date_input("Fecha", value=fechas[-1] if fechas else pd.Timestamp.today().date())
    d = pd.to_datetime(fecha).normalize()

    filtered = op[pd.to_datetime(op["Fecha"], errors="coerce").dt.normalize() == d] if not op.empty and "Fecha" in op else op
    table = operational_table(filtered, tiendas)
    res = resumen_ejecutivo(filtered)
    kpis(res)
    download_pdf("Reporte Por Día", table, res)
    panel("Tabla por tienda", table, 390)
    combined_chart(table, "Ingresos vs Habilitadas y Ubicadas")
    excel_download(table, "por_dia.xlsx")

def semanal(ctx):
    op = ctx["op"]
    tiendas = ctx["tiendas"]
    section("Reporte Semanal", "Filtro por tienda y semana ISO.")

    c1, c2 = st.columns(2)
    with c1:
        tienda_sel = st.multiselect("Tiendas", tiendas, default=[])
    semanas = sorted(op["Semana ISO"].dropna().astype(int).unique().tolist()) if not op.empty and "Semana ISO" in op else []
    with c2:
        semana_sel = st.multiselect("Semana ISO", semanas, default=semanas[-1:] if semanas else [])

    filtered = op.copy()
    if tienda_sel:
        filtered = filtered[filtered["Tienda"].isin(tienda_sel)]
    if semana_sel:
        filtered = filtered[filtered["Semana ISO"].isin(semana_sel)]

    table = operational_table(filtered, tienda_sel or tiendas)
    res = resumen_ejecutivo(filtered)
    kpis(res)
    download_pdf("Reporte Semanal", table, res)
    panel("Tabla semanal por tienda", table, 390)
    combined_chart(table, "Semanal: Total vs Habilitadas y Ubicadas")

def mensual(ctx):
    op = ctx["op"]
    tiendas = ctx["tiendas"]
    section("Reporte Mensual", "Filtro por tienda y mes.")

    c1, c2 = st.columns(2)
    with c1:
        tienda_sel = st.multiselect("Tiendas", tiendas, default=[], key="mes_t")
    meses = sorted(op["Mes"].dropna().astype(str).unique().tolist()) if not op.empty and "Mes" in op else []
    with c2:
        mes_sel = st.multiselect("Mes", meses, default=meses[-1:] if meses else [])

    filtered = op.copy()
    if tienda_sel:
        filtered = filtered[filtered["Tienda"].isin(tienda_sel)]
    if mes_sel:
        filtered = filtered[filtered["Mes"].isin(mes_sel)]

    table = operational_table(filtered, tienda_sel or tiendas)
    res = resumen_ejecutivo(filtered)
    kpis(res)
    download_pdf("Reporte Mensual", table, res)
    panel("Tabla mensual por tienda", table, 390)
    combined_chart(table, "Mensual: Total vs Habilitadas y Ubicadas")

def productividad_page(ctx):
    op = ctx["op"]
    metas = ctx["metas"]
    section("Productividad", "Top colaboradores e índice de actividades por colaborador.")

    if op.empty:
        st.info("Sin información.")
        return

    data = op.copy()
    data["Fecha"] = pd.to_datetime(data["Fecha"], errors="coerce")
    data = data[data["Fecha"].notna()]
    if data.empty:
        st.info("Sin fechas válidas.")
        return

    c1, c2 = st.columns(2)
    min_date, max_date = data["Fecha"].min().date(), data["Fecha"].max().date()
    with c1:
        periodo = st.date_input("Periodo", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    tiendas = sorted(data["Tienda"].dropna().unique().tolist())
    with c2:
        tienda_sel = st.multiselect("Tienda", tiendas, default=[])

    if isinstance(periodo, tuple):
        inicio, fin = periodo
    else:
        inicio = fin = periodo

    filtered = data[
        (data["Fecha"] >= pd.to_datetime(inicio)) &
        (data["Fecha"] <= pd.to_datetime(fin) + pd.Timedelta(days=1))
    ]

    if tienda_sel:
        filtered = filtered[filtered["Tienda"].isin(tienda_sel)]

    prod = productividad(filtered, metas.get("productividad_diaria", 784))
    idx = indice_actividades(filtered)

    resumen = {
        "Colaboradores": prod["Nombre"].nunique() if not prod.empty else 0,
        "Piezas": fmt_num(prod["Piezas"].sum() if not prod.empty else 0),
        "Productividad prom.": f'{prod["Productividad diaria"].mean():.1f}' if not prod.empty else "0",
    }

    c1, c2, c3 = st.columns(3)
    c1.metric("Colaboradores", resumen["Colaboradores"])
    c2.metric("Piezas", resumen["Piezas"])
    c3.metric("Productividad prom.", resumen["Productividad prom."])

    download_pdf("Productividad", prod, resumen)
    panel("Top colaboradores", prod.head(20), 430)

    if not prod.empty:
        chart = prod.head(15).sort_values("Productividad diaria")
        fig = px.bar(chart, x="Productividad diaria", y="Nombre", orientation="h", text="Productividad diaria")
        fig.update_layout(height=460, dragmode=False, plot_bgcolor="white", paper_bgcolor="white")
        fig.update_xaxes(fixedrange=True)
        fig.update_yaxes(fixedrange=True)
        st.plotly_chart(fig, width="stretch", config={"scrollZoom": False, "displayModeBar": False, "doubleClick": False})

    panel("Índice de actividades por colaborador", idx, 520)
    excel_download(idx, "indice_actividades.xlsx")

def conversion_page(ctx):
    co = ctx["co"]
    section("Conversión", "Todas las tiendas. Misma semana ISO, tienda, modelo y color.")

    if co.empty:
        st.warning("No se detectó información comercial.")
        return

    semanas = sorted(co["Semana ISO"].dropna().astype(int).unique().tolist())
    semana_sel = st.multiselect("Semana ISO", semanas, default=semanas[-1:] if semanas else [])
    filtered = co[co["Semana ISO"].isin(semana_sel)] if semana_sel else co
    detail, summary = conversion(filtered)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Dev Pzs", fmt_num(summary["Dev Pzs"]))
    c2.metric("Conversión Pzs", fmt_num(summary["Conversión Pzs"]))
    c3.metric("Conversión $", fmt_money(summary["Conversión $"]))
    c4.metric("% Conversión", fmt_pct(summary["% Conversión"]))
    c5.metric("Pendiente", fmt_num(summary["Pendiente Pzs"]))

    download_pdf("Conversión Dev Venta", detail, summary)
    panel("Detalle conversión", detail, 430)

def recuperacion(ctx):
    co = ctx["co"]
    section("Recuperación Económica", "Todas las tiendas.")

    if co.empty:
        st.warning("No se detectó información comercial.")
        return

    detail, summary = conversion(co)
    c1, c2, c3 = st.columns(3)
    c1.metric("Recuperación $", fmt_money(summary["Conversión $"]))
    c2.metric("Venta No Convertida $", fmt_money(summary["No Convertido $"]))
    c3.metric("% Conversión", fmt_pct(summary["% Conversión"]))

    download_pdf("Recuperación Económica", detail, summary)
    panel("Detalle económico", detail, 430)

def simple_table(ctx, title, df):
    section(title, "Consulta de información.")
    panel(title, df, 500)

def configuracion(ctx):
    user = ctx["user"]
    metas = ctx["metas"]
    project = load_project()
    section("Configuración", "Tiendas del proyecto, metas y pestañas.")

    if user.get("permiso") != "Administrador":
        st.warning("Sólo administrador.")
        return

    tiendas = st.multiselect("Tiendas del proyecto", PROJECT_TIENDAS, default=project.get("tiendas_proyecto", []))
    metas["productividad_diaria"] = st.number_input("Meta productividad diaria", value=int(metas.get("productividad_diaria", 784)))
    metas["recorridos_semanal"] = st.number_input("Meta recorridos semanal", value=int(metas.get("recorridos_semanal", 47)))
    metas["conversion_meta"] = st.number_input("Meta conversión %", value=float(metas.get("conversion_meta", 90.0)))

    if st.button("Guardar configuración"):
        project["tiendas_proyecto"] = tiendas
        save_project(project)
        save_goals(metas)
        st.success("Guardado.")
        st.rerun()

def usuarios(ctx):
    user = ctx["user"]
    section("Usuarios", "Crear y administrar accesos.")

    if user.get("permiso") != "Administrador":
        st.warning("Sólo administrador.")
        return

    users = load_users()

    with st.form("nuevo_usuario"):
        c1, c2, c3, c4, c5 = st.columns(5)
        nomina = c1.text_input("Nómina/Usuario")
        nombre = c2.text_input("Nombre")
        correo = c3.text_input("Correo")
        permiso = c4.selectbox("Permiso", ["Consulta", "Gerente", "Administrador"])
        password = c5.text_input("Contraseña", type="password")

        if st.form_submit_button("Crear usuario"):
            users.append({"nomina": nomina, "nombre": nombre or nomina, "correo": correo, "permiso": permiso, "password": password, "activo": True})
            save_users(users)
            st.success("Usuario creado.")
            st.rerun()

    view = [{k: v for k, v in u.items() if k != "password"} for u in users]
    edited = st.data_editor(pd.DataFrame(view), hide_index=True, width="stretch", num_rows="dynamic")

    if st.button("Guardar cambios usuarios"):
        old = {u["nomina"]: u for u in users}
        new_users = []
        for _, row in edited.iterrows():
            d = row.to_dict()
            d["password"] = old.get(d.get("nomina"), {}).get("password", "")
            new_users.append(d)
        save_users(new_users)
        st.success("Guardado.")
        st.rerun()
