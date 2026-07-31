from __future__ import annotations
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from core.settings import APP_NAME, COMPANY

def build_pdf(title, dataframe=None, kpis=None, filters=None, user="", detailed=False):
    buf=BytesIO(); page=landscape(A4) if dataframe is not None and len(dataframe.columns)>8 else A4
    doc=SimpleDocTemplate(buf,pagesize=page,rightMargin=24,leftMargin=24,topMargin=28,bottomMargin=28); styles=getSampleStyleSheet(); story=[Paragraph(COMPANY,styles['Heading2']),Paragraph(APP_NAME,styles['Heading1']),Paragraph(title,styles['Heading2']),Spacer(1,10)]
    if user: story.append(Paragraph(f"Usuario: {user}",styles['Normal']))
    if filters: story.append(Paragraph("Filtros: "+" | ".join(f"{k}: {v}" for k,v in filters.items()),styles['Normal']))
    if kpis:
        data=[[str(k),str(v)] for k,v in kpis.items()]; t=Table(data,colWidths=[180,140]); t.setStyle(TableStyle([('BACKGROUND',(0,0),(0,-1),colors.HexColor('#173B73')),('TEXTCOLOR',(0,0),(0,-1),colors.white),('GRID',(0,0),(-1,-1),.25,colors.grey),('FONTSIZE',(0,0),(-1,-1),8)])); story.extend([Spacer(1,10),t])
    if dataframe is not None and not dataframe.empty:
        df=dataframe.copy(); max_rows=500 if detailed else 100; df=df.head(max_rows); data=[list(map(str,df.columns))]+df.fillna('').astype(str).values.tolist(); widths=[max(45,min(110,700/max(1,len(df.columns))))]*len(df.columns); t=Table(data,repeatRows=1,colWidths=widths); t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#173B73')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.2,colors.HexColor('#D0D5DD')),('FONTSIZE',(0,0),(-1,-1),6.5),('VALIGN',(0,0),(-1,-1),'TOP')])); story.extend([Spacer(1,12),t])
    doc.build(story); return buf.getvalue()
