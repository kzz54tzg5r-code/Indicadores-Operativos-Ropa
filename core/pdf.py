
from io import BytesIO
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from .utils import format_table

def pdf_bytes(title, df=None, resumen=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=22, leftMargin=22, topMargin=22, bottomMargin=22)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"<b>{title}</b>", styles["Title"]),
        Paragraph("Operaciones Ropa | Indicadores Operaciones Ropa", styles["Normal"]),
        Spacer(1, 10)
    ]

    if resumen:
        data = [["Indicador", "Valor"]] + [[str(k), str(v)] for k, v in resumen.items()]
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EC007C")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#CBD5E1")),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]))
        story.extend([t, Spacer(1, 10)])

    if df is not None and not df.empty:
        view = format_table(df.head(35))
        data = [list(view.columns)] + view.astype(str).values.tolist()
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#10245F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#CBD5E1")),
            ("FONTSIZE", (0, 0), (-1, -1), 6),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]))
        story.append(t)

    story.extend([Spacer(1, 10), Paragraph("CONFIDENCIAL | Price Shoes | Operaciones Ropa", styles["Normal"])])
    doc.build(story)
    return buffer.getvalue()
