
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

BLUE = "#10245F"
PINK = "#EC007C"

def apply_styles():
    st.markdown(f"""
    <style>
    .stApp {{ background:#F4F7FB; }}
    .block-container {{ max-width:100% !important; padding:0 1.4rem 2rem !important; }}
    section[data-testid="stSidebar"] {{ background:white; border-right:1px solid #D9E2F0; }}
    .top-header {{
        background:white; border-bottom:4px solid {PINK}; margin:0 -1.4rem 0 -1.4rem;
        padding:14px 24px; display:grid; grid-template-columns:140px 1fr 400px; gap:20px; align-items:center;
    }}
    .logo-fallback {{ color:{BLUE}; font-weight:950; font-size:25px; line-height:.9; text-align:center; }}
    .header-title {{ border-left:4px solid {PINK}; padding-left:20px; }}
    .header-title .small {{ color:{PINK}; font-weight:900; letter-spacing:4px; font-size:11px; }}
    .header-title .big {{ color:{BLUE}; font-weight:900; font-size:28px; line-height:1; }}
    .header-title .sub {{ color:#64748B; font-weight:650; font-size:13px; margin-top:3px; }}
    .header-card {{ background:#F8FAFC; border:1px solid #D9E2F0; border-radius:12px; padding:9px 12px; }}
    .header-card label {{ display:block; font-size:10px; color:#64748B; font-weight:900; letter-spacing:1px; }}
    .header-card div {{ color:{BLUE}; font-size:14px; font-weight:900; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .nav-wrap {{ background:{BLUE}; border-top:4px solid {PINK}; margin:0 -1.4rem 16px; padding:8px 18px; }}
    .nav-wrap button {{ background:#142E73 !important; color:white !important; min-height:38px !important; }}
    .nav-wrap div[data-baseweb="select"] > div {{ background:#142E73 !important; color:white !important; min-height:38px !important; border:1px solid rgba(255,255,255,.25) !important; }}
    .nav-wrap div[data-baseweb="select"] * {{ color:white !important; font-weight:850 !important; }}
    .section-title {{ color:#111827; font-size:25px; font-weight:900; margin:10px 0 4px; }}
    .section-subtitle {{ color:#64748B; font-size:13px; margin-bottom:15px; }}
    div[data-testid="stMetric"] {{ background:white; border:1px solid #D9E2F0; border-radius:16px; padding:14px; box-shadow:0 8px 20px rgba(16,36,95,.06); }}
    div[data-testid="stMetricValue"] {{ font-size:26px !important; color:#1F2937 !important; font-weight:800 !important; }}
    .panel {{ background:white; border:1px solid #D9E2F0; border-radius:16px; padding:16px; box-shadow:0 8px 20px rgba(16,36,95,.05); margin-bottom:18px; }}
    .panel-title {{ color:{BLUE}; font-size:16px; font-weight:900; margin-bottom:12px; }}
    div[data-testid="stDataFrame"] [role="columnheader"], div[data-testid="stDataEditor"] [role="columnheader"] {{ background:{BLUE} !important; color:white !important; font-weight:800 !important; }}
    div[data-testid="stDataFrame"] [role="columnheader"] *, div[data-testid="stDataEditor"] [role="columnheader"] * {{ color:white !important; fill:white !important; }}
    .stPlotlyChart {{ touch-action: pan-y !important; }}
    @media (max-width:900px) {{
        .top-header {{ grid-template-columns:90px 1fr; }}
        .header-controls {{ display:none !important; }}
    }}
    </style>
    """, unsafe_allow_html=True)

def header(user, project):
    now = datetime.now(ZoneInfo("America/Mexico_City"))
    title = project.get("nombre", "Indicadores Operaciones Ropa")
    sub = project.get("subtitulo", "Plataforma Ejecutiva de Recuperación de Mercancía")
    st.markdown(f"""
    <div class="top-header">
        <div class="logo-fallback">Price<br>Shoes</div>
        <div class="header-title">
            <div class="small">OPERACIONES ROPA</div>
            <div class="big">{title}</div>
            <div class="sub">{sub}</div>
        </div>
        <div class="header-controls" style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            <div class="header-card"><label>Fecha</label><div>📅 {now.strftime("%d/%m/%Y")}</div></div>
            <div class="header-card"><label>Usuario</label><div>{user.get("nombre","")}</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def section(title, subtitle=""):
    st.markdown(f'<div class="section-title">{title}</div><div class="section-subtitle">{subtitle}</div>', unsafe_allow_html=True)
