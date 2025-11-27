# excel_template.py
import pandas as pd
from io import BytesIO

# Columns required for upload/import
REQUIRED_COLUMNS = ["no_po", "customer", "total_tagihan", "total_bayar", "tanggal", "jatuh_tempo"]

def create_template_excel():
    # sample empty row for guidance
    sample = {
        "no_po": ["PO-001"],
        "customer": ["PT. Contoh"],
        "total_tagihan": [100000],
        "total_bayar": [50000],
        "tanggal": ["2025-11-27"],
        "jatuh_tempo": ["2025-12-10"]
    }
    df = pd.DataFrame(sample)
    # create Excel in-memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="template")
        writer.sheets["template"].cell(row=1, column=1).value  # ensure created
    output.seek(0)
    return output.getvalue()
