from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

def generate_excel(dataframe, path="po_report.xlsx"):
    wb = Workbook()
    ws = wb.active
    ws.title = "Laporan PO"

    # Header
    headers = list(dataframe.columns)
    ws.append(headers)

    # Style header
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="4F81BD", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")

    # Isi data baris
    for _, row in dataframe.iterrows():
        ws.append(list(row))

    # Format angka
    for col in ["C", "D", "E"]:
        for row in range(2, ws.max_row + 1):
            ws[f"{col}{row}"].number_format = '#,##0'

    wb.save(path)
    return path
