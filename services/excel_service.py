from io import BytesIO
import pandas as pd
def build_excel(sheets: dict[str,pd.DataFrame], metadata=None):
    out=BytesIO()
    with pd.ExcelWriter(out,engine="openpyxl") as writer:
        if metadata: pd.DataFrame(list(metadata.items()),columns=["Campo","Valor"]).to_excel(writer,sheet_name="Información",index=False)
        for name,df in sheets.items(): df.to_excel(writer,sheet_name=str(name)[:31],index=False)
    return out.getvalue()
