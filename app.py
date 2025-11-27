import streamlit as st
import pandas as pd
from datetime import date
from supabase_conn import supabase
from excel_export import generate_excel

st.set_page_config(page_title="Sistem Tracking PO", layout="wide")

st.title("📦 Sistem Tracking PO & Status Pembayaran")

# ========================
# 1️⃣ FORM INPUT MANUAL
# ========================
st.subheader("Input PO Manual")

with st.form("form_po"):
    no_po = st.text_input("Nomor PO")
    customer = st.text_input("Nama Customer")
    total_tagihan = st.number_input("Total Tagihan", min_value=0.0)
    total_bayar = st.number_input("Total Bayar", min_value=0.0)
    tanggal = st.date_input("Tanggal Transaksi", value=date.today())
    jatuh_tempo = st.date_input("Jatuh Tempo")

    submitted = st.form_submit_button("Simpan")

if submitted:
    sisa = total_tagihan - total_bayar
    status = "Lunas" if sisa <= 0 else "Belum Lunas"

    supabase.table("po_sales").insert({
        "no_po": no_po,
        "customer": customer,
        "total_tagihan": total_tagihan,
        "total_bayar": total_bayar,
        "sisa": sisa,
        "status": status,
        "tanggal": str(tanggal),
        "jatuh_tempo": str(jatuh_tempo),
    }).execute()

    st.success("Data PO berhasil disimpan!")

# ========================
# 2️⃣ IMPORT EXCEL
# ========================
st.subheader("Import dari File Excel")

file = st.file_uploader("Upload File Excel", type=["xlsx"])

if file:
    df_import = pd.read_excel(file)

    # Pastikan kolom wajib ada
    required = ["no_po", "customer", "total_tagihan", "total_bayar", "tanggal", "jatuh_tempo"]
    if not all(col in df_import.columns for col in required):
        st.error("Kolom Excel tidak sesuai format!")
    else:
        # Proses status & sisa secara otomatis
        df_import["sisa"] = df_import["total_tagihan"] - df_import["total_bayar"]
        df_import["status"] = df_import["sisa"].apply(lambda x: "Lunas" if x <= 0 else "Belum Lunas")

        # Kirim ke Supabase
        supabase.table("po_sales").insert(df_import.to_dict(orient="records")).execute()

        st.success("Import berhasil!")

# ========================
# 3️⃣ DASHBOARD
# ========================
st.subheader("Dashboard PO")

data = supabase.table("po_sales").select("*").execute()
df = pd.DataFrame(data.data)

if not df.empty:
    # Tambah warna status
    def highlight_status(row):
        color = '#9AFF9A' if row["status"] == "Lunas" else '#FFF59D'
        return [f'background-color: {color}'] * len(row)

    st.dataframe(df.style.apply(highlight_status, axis=1))

    # Download excel
    if st.button("Download Laporan Excel"):
        path = generate_excel(df)
        with open(path, "rb") as f:
            st.download_button("Download File Excel", f, file_name="Laporan_PO.xlsx")
else:
    st.info("Belum ada data PO.")
