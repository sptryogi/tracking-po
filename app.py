# app.py
import streamlit as st
import pandas as pd
from datetime import date
from io import BytesIO
from supabase_conn import supabase
from excel_template import create_template_excel, REQUIRED_COLUMNS
from excel_export import generate_excel_bytes
from utils import df_format_for_display, fmt_currency
from zoneinfo import ZoneInfo

JAKARTA = ZoneInfo("Asia/Jakarta")

st.set_page_config(page_title="Sistem Tracking PO & Status Pembayaran", layout="wide")
st.title("📦 Sistem Tracking PO & Status Pembayaran")

# -------- session state for simple page navigation --------
if "page" not in st.session_state:
    st.session_state.page = "dashboard"  # dashboard, input, edit
if "edit_id" not in st.session_state:
    st.session_state.edit_id = None
if "show_import" not in st.session_state:
    st.session_state.show_import = False

# -------- top navigation (buttons) --------
col1, col2, col3, col4, col5 = st.columns([3,1,1,1,1])
with col1:
    st.markdown("## ")
with col2:
    if st.button("🏠 Dashboard"):
        st.session_state.page = "dashboard"
with col3:
    if st.button("➕ Input Form"):
        st.session_state.page = "input"
        st.session_state.edit_id = None
with col4:
    if st.button("📁 Import File"):
        # toggle import uploader visibility
        st.session_state.show_import = not st.session_state.show_import
# with col5:
#     if st.button("✏️ Edit Form"):
#         # to edit user will select a row in dashboard -> we'll set edit_id there
#         st.session_state.page = "dashboard"  # keep in dashboard until user selects record to edit

st.markdown("---")

# -------- helper functions --------
def fetch_all():
    res = supabase.table("po_sales").select("*").order("created_at", desc=True).execute()
    data = res.data or []
    return pd.DataFrame(data)

def check_duplicate_no_po(no_po):
    res = supabase.table("po_sales").select("id").eq("no_po", no_po).limit(1).execute()
    return len(res.data) > 0

def insert_record(rec):
    return supabase.table("po_sales").insert(rec).execute()

def update_record(rec_id, rec):
    return supabase.table("po_sales").update(rec).eq("id", rec_id).execute()

def delete_record(rec_id):
    return supabase.table("po_sales").delete().eq("id", rec_id).execute()

# -------- IMPORT UPLOADER (tunnel/expander) --------
if st.session_state.show_import:
    with st.expander("Import Excel — klik untuk buka / tutup", expanded=True):
        st.markdown("Gunakan template Excel yang tersedia. Jika kolom tidak sesuai, import akan gagal.")
        # download template
        template_bytes = create_template_excel()
        st.download_button("📥 Download Template Excel", template_bytes, file_name="template_po.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        uploaded = st.file_uploader("Upload file Excel (.xlsx)", type=["xlsx"])
        if uploaded:
            try:
                df_upload = pd.read_excel(uploaded)
            except Exception as e:
                st.error(f"Gagal membaca file: {e}")
                df_upload = None

            if df_upload is not None:
                # validate columns (case-insensitive)
                cols_lower = [c.lower().strip() for c in df_upload.columns]
                mapping = {}
                for c in df_upload.columns:
                    mapping[c] = c.lower().strip()
                missing = [c for c in REQUIRED_COLUMNS if c not in cols_lower]
                if missing:
                    st.error(f"Format kolom tidak sesuai. Kolom yg wajib: {REQUIRED_COLUMNS}. Kolom yang hilang: {missing}")
                else:
                    # normalize column names to required names
                    # map existing columns to required lowercase names
                    df_norm = df_upload.copy()
                    rename_map = {}
                    for c in df_upload.columns:
                        key = c.lower().strip()
                        if key in REQUIRED_COLUMNS:
                            rename_map[c] = key
                    df_norm = df_norm.rename(columns=rename_map)
                    # fill missing optional columns
                    for c in REQUIRED_COLUMNS:
                        if c not in df_norm.columns:
                            df_norm[c] = None

                    # compute sisa & status
                    df_norm["total_tagihan"] = pd.to_numeric(df_norm["total_tagihan"], errors="coerce").fillna(0)
                    df_norm["total_bayar"] = pd.to_numeric(df_norm["total_bayar"], errors="coerce").fillna(0)
                    df_norm["sisa"] = df_norm["total_tagihan"] - df_norm["total_bayar"]
                    df_norm["status"] = df_norm["sisa"].apply(lambda x: "Lunas" if x <= 0 else "Belum Lunas")
                    # created_at will be set by supabase (server) if configured; otherwise set now in UTC
                    df_norm["created_at"] = pd.Timestamp.utcnow().isoformat()

                    # check duplicates
                    duplicates = []
                    to_insert = []
                    for _, row in df_norm.iterrows():
                        no_po = str(row["no_po"]).strip()
                        if not no_po:
                            duplicates.append((no_po, "no_po kosong"))
                            continue
                        # check supabase existing
                        exists = supabase.table("po_sales").select("id").eq("no_po", no_po).limit(1).execute()
                        if exists.data and len(exists.data) > 0:
                            duplicates.append((no_po, "sudah ada"))
                        else:
                            rec = {
                                "no_po": no_po,
                                "customer": row.get("customer"),
                                "total_tagihan": float(row.get("total_tagihan", 0)),
                                "total_bayar": float(row.get("total_bayar", 0)),
                                "sisa": float(row.get("sisa", 0)),
                                "status": row.get("status"),
                                "tanggal": str(row.get("tanggal")) if not pd.isna(row.get("tanggal")) else None,
                                "jatuh_tempo": str(row.get("jatuh_tempo")) if not pd.isna(row.get("jatuh_tempo")) else None,
                                "created_at": row.get("created_at")
                            }
                            to_insert.append(rec)

                    if duplicates:
                        st.error("Beberapa baris tidak diimport karena duplikat atau error pada no_po:")
                        for d in duplicates[:50]:
                            st.write(f"- {d[0]}: {d[1]}")
                        if len(duplicates) > 50:
                            st.write(f"...dan {len(duplicates)-50} lagi")
                    if to_insert:
                        # batch insert
                        res = supabase.table("po_sales").insert(to_insert).execute()
                        if res.data is None:
                            st.error("Gagal import data.")
                        else:
                            st.success(f"Berhasil memasukkan {len(to_insert)} record.")
                            st.session_state.page = "dashboard"
                            st.rerun()

            # end uploaded handling

# -------- PAGES: Dashboard / Input / Edit --------
if st.session_state.page == "input" and st.session_state.edit_id is None:
    # Input manual form
    st.header("Form Input PO Manual")
    with st.form("form_po_manual"):
        no_po = st.text_input("Nomor PO")
        customer = st.text_input("Nama Customer")
        total_tagihan = st.number_input("Total Tagihan", min_value=0.0, step=1000.0)
        total_bayar = st.number_input("Total Bayar", min_value=0.0, step=1000.0)
        tanggal = st.date_input("Tanggal Transaksi", value=date.today())
        jatuh_tempo = st.date_input("Jatuh Tempo", value=date.today())
        submitted = st.form_submit_button("Simpan")

    if submitted:
        no_po_str = str(no_po).strip()
        if not no_po_str:
            st.error("Nomor PO wajib diisi.")
        else:
            # duplicate check
            exists = supabase.table("po_sales").select("id").eq("no_po", no_po_str).limit(1).execute()
            if exists.data and len(exists.data) > 0:
                st.error("no_po sudah ada silahkan tekan tombol edit untuk mengubah")
            else:
                sisa = float(total_tagihan) - float(total_bayar)
                status = "Lunas" if sisa <= 0 else "Belum Lunas"
                rec = {
                    "no_po": no_po_str,
                    "customer": customer,
                    "total_tagihan": total_tagihan,
                    "total_bayar": total_bayar,
                    "sisa": sisa,
                    "status": status,
                    "tanggal": str(tanggal),
                    "jatuh_tempo": str(jatuh_tempo),
                    "created_at": pd.Timestamp.now(tz=JAKARTA).isoformat()
                }
                res = supabase.table("po_sales").insert(rec).execute()
                if res.data is None:
                    st.error("Gagal menyimpan data PO.")
                else:
                    st.success("Data PO berhasil disimpan!")
                    st.session_state.page = "dashboard"
                    st.rerun()

# Dashboard page
if st.session_state.page == "dashboard":
    st.header("Dashboard PO")

    # fetch data
    df = fetch_all()
    if df.empty:
        st.info("Belum ada data PO.")
    else:
        # filters: status, bulan, tanggal range
        c1, c2, c3, c4 = st.columns([1,1,2,2])
        with c1:
            status_filter = st.selectbox("Filter Status", options=["Semua", "Lunas", "Belum Lunas"], index=0)
        with c2:
            month_filter = st.selectbox("Filter Bulan", options=["Semua"] + [f"{m:02d}" for m in range(1,13)], index=0)
        with c3:
            start_date = st.date_input("Dari Tanggal", value=pd.to_datetime(df["tanggal"]).min().date() if "tanggal" in df.columns else date.today())
        with c4:
            end_date = st.date_input("Sampai Tanggal", value=pd.to_datetime(df["tanggal"]).max().date() if "tanggal" in df.columns else date.today())

        df["tanggal"] = pd.to_datetime(df["tanggal"], errors="coerce")
        # filtering
        mask = pd.Series([True]*len(df))
        if status_filter != "Semua":
            mask = mask & (df["status"] == status_filter)
        if month_filter != "Semua":
            mask = mask & (df["tanggal"].dt.month == int(month_filter))
        if start_date:
            mask = mask & (df["tanggal"].dt.date >= start_date)
        if end_date:
            mask = mask & (df["tanggal"].dt.date <= end_date)
        df_filtered = df[mask].reset_index(drop=True)

        # summary cards
        total_po = len(df_filtered)
        total_tagihan_sum = df_filtered["total_tagihan"].astype(float).sum() if "total_tagihan" in df_filtered.columns else 0
        outstanding_sum = df_filtered["sisa"].astype(float).sum() if "sisa" in df_filtered.columns else 0

        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Jumlah PO (hasil filter)", total_po)
        sc2.metric("Total Tagihan", fmt_currency(total_tagihan_sum))
        sc3.metric("Total Outstanding (Sisa)", fmt_currency(outstanding_sum))

        # chart: total per day (based on tanggal)
        # try:
        #     chart_df = df_filtered.copy()
        #     chart_df["tanggal_day"] = chart_df["tanggal"].dt.date
        #     # chart_agg = chart_df.groupby("tanggal_day").agg({"total_tagihan":"sum"}).reset_index()
        #     # st.line_chart(chart_agg.rename(columns={"tanggal_day":"index"}).set_index("index")["total_tagihan"])
        #     chart_agg = chart_df.groupby("tanggal_day", dropna=True)["total_tagihan"].sum().reset_index()
        #     chart_agg = chart_agg.sort_values("tanggal_day")
        #     st.line_chart(
        #         chart_agg.set_index("tanggal_day")["total_tagihan"]
        #     )
        # except Exception:
        #     st.write("Chart tidak tersedia karena data tanggal kurang lengkap.")
        # chart: Bar chart per day (Tagihan, Bayar, Sisa)
        try:
            chart_df = df_filtered.copy()
            chart_df["tanggal_day"] = chart_df["tanggal"].dt.date
            
            # Group by tanggal dan ambil sum untuk 3 kolom
            chart_agg = chart_df.groupby("tanggal_day", dropna=True)[
                ["total_tagihan", "total_bayar", "sisa"]
            ].sum().reset_index()
            
            chart_agg = chart_agg.sort_values("tanggal_day")
            
            st.markdown("#### Grafik Keuangan Harian")
            # Menampilkan Bar Chart
            # Urutan warna di list color=[] harus sesuai urutan kolom di data (Tagihan, Bayar, Sisa)
            # Biru (#29b5e8), Hijau (#28a745), Kuning (#ffc107)
            st.bar_chart(
                data=chart_agg.set_index("tanggal_day"),
                y=["total_tagihan", "total_bayar", "sisa"],
                color=["#29b5e8", "#28a745", "#ffc107"] 
            )
        except Exception as e:
            st.write(f"Chart tidak tersedia: {e}")

        # show table with highlight
        from pandas.io.formats.style import Styler
        display_df = df_format_for_display(df_filtered)
        # add action column (edit/delete)
        display_df = display_df.reset_index(drop=True)

        # show as interactive table with action buttons per row (use st.table + select by index)
        st.markdown("#### Tabel PO (klik baris index untuk pilih record → gunakan tombol Edit / Hapus)")
        # show small table
        def highlight_status(row):
            if row["status"] == "Lunas":
                return ['background-color: #b2f2bb'] * len(row)
            elif row["status"] == "Belum Lunas":
                return ['background-color: #fff3bf'] * len(row)
            elif row["jatuh_tempo"] and pd.to_datetime(row["jatuh_tempo"]) < pd.Timestamp.now().tz_localize(None):
                return ['background-color: #ffc9c9'] * len(row)
            return [''] * len(row)
        
        st.dataframe(display_df.style.apply(highlight_status, axis=1), use_container_width=True)

        # selection
        sel = st.text_input("Masukkan id (kolom `id`) dari record untuk Edit / Hapus, atau kosongkan")
        # Provide guidance: show id column
        st.caption("Untuk melihat kolom `id`, periksa tabel di atas (kolom id). Gunakan id tersebut untuk edit/hapus.")

        col_edit, col_del, col_refresh, col_download = st.columns(4)
        with col_edit:
            if st.button("✏️ Edit Record"):
                if not sel:
                    st.warning("Masukkan id record yang ingin diedit.")
                else:
                    try:
                        rec_id = int(sel)
                        res = supabase.table("po_sales").select("*").eq("id", rec_id).limit(1).execute()
                        if res.data and len(res.data) > 0:
                            st.session_state.edit_id = rec_id
                            st.session_state.page = "input"
                            # prefill values by putting in session_state
                            # rec = res.data[0]
                            # st.session_state.prefill = rec
                            st.rerun()
                        else:
                            st.error("Record tidak ditemukan.")
                    except Exception:
                        st.error("id harus berupa angka integer.")
        with col_del:
            confirm = st.checkbox("Centang untuk konfirmasi hapus")
            if st.button("🗑️ Hapus Record"):
                if not sel:
                    st.warning("Masukkan id record yang ingin dihapus.")
                elif not confirm:
                    st.warning("Silakan centang konfirmasi hapus.")
                else:
                    try:
                        rec_id = int(sel)
                        resp = delete_record(rec_id)
                        if resp.data is None:
                            st.error("Gagal menghapus data.")
                        else:
                            st.success("Record berhasil dihapus.")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
        with col_refresh:
            if st.button("🔄 Refresh Data"):
                st.rerun()
        with col_download:
            if st.button("📥 Download Laporan Excel"):
                bytes_x = generate_excel_bytes(df_filtered)
                st.download_button("Download File Excel", bytes_x, file_name="Laporan_PO.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# Edit flow: if edit_id set and page input
if st.session_state.page == "input" and st.session_state.edit_id:
    # load existing record
    rec_id = st.session_state.edit_id
    res = supabase.table("po_sales").select("*").eq("id", rec_id).limit(1).execute()
    if not res.data or len(res.data) == 0:
        st.error("Record untuk diedit tidak ditemukan.")
    else:
        rec = res.data[0]
        st.header(f"Edit Record id={rec_id}")
        with st.form("form_edit"):
            no_po = st.text_input("Nomor PO", value=rec.get("no_po",""))
            customer = st.text_input("Nama Customer", value=rec.get("customer",""))
            total_tagihan = st.number_input("Total Tagihan", value=float(rec.get("total_tagihan") or 0), step=1000.0)
            total_bayar = st.number_input("Total Bayar", value=float(rec.get("total_bayar") or 0), step=1000.0)
            tanggal = st.date_input("Tanggal Transaksi", value=pd.to_datetime(rec.get("tanggal")).date() if rec.get("tanggal") else date.today())
            jatuh_tempo = st.date_input("Jatuh Tempo", value=pd.to_datetime(rec.get("jatuh_tempo")).date() if rec.get("jatuh_tempo") else date.today())
            submitted = st.form_submit_button("Simpan Perubahan")
        if submitted:
            sisa = float(total_tagihan) - float(total_bayar)
            status = "Lunas" if sisa <= 0 else "Belum Lunas"
            
            # Flag penanda apakah boleh lanjut update
            proceed_update = True

            # 1. Cek Validasi: Jika No PO berubah, pastikan tidak duplikat
            if no_po != rec.get("no_po"):
                check = supabase.table("po_sales").select("id").eq("no_po", no_po).limit(1).execute()
                if check.data and len(check.data) > 0:
                    st.error("no_po sudah ada silahkan gunakan nomor lain atau edit record yang ada.")
                    proceed_update = False
            
            # 2. Jika validasi aman, lakukan update
            if proceed_update:
                update = {
                    "no_po": no_po,
                    "customer": customer,
                    "total_tagihan": total_tagihan,
                    "total_bayar": total_bayar,
                    "sisa": sisa,
                    "status": status,
                    "tanggal": str(tanggal),
                    "jatuh_tempo": str(jatuh_tempo)
                }
                resp = update_record(rec_id, update)
                if resp.data is None:
                    st.error("Gagal update data.")
                else:
                    st.success("Record berhasil diupdate.")
                    st.session_state.edit_id = None
                    st.session_state.page = "dashboard"
                    st.rerun()
            # sisa = float(total_tagihan) - float(total_bayar)
            # status = "Lunas" if sisa <= 0 else "Belum Lunas"
            # # if no_po changed, check duplicate (exclude current id)
            # if no_po != rec.get("no_po"):
            #     check = supabase.table("po_sales").select("id").eq("no_po", no_po).limit(1).execute()
            #     if check.data and len(check.data)>0:
            #         st.error("no_po sudah ada silahkan gunakan nomor lain atau edit record yang ada.")
            #     else:
            #         update = {
            #             "no_po": no_po,
            #             "customer": customer,
            #             "total_tagihan": total_tagihan,
            #             "total_bayar": total_bayar,
            #             "sisa": sisa,
            #             "status": status,
            #             "tanggal": str(tanggal),
            #             "jatuh_tempo": str(jatuh_tempo)
            #         }
            #         resp = update_record(rec_id, update)
            #         if resp.data is None:
            #             st.error("Gagal update data.")
            #         else:
            #             st.success("Record berhasil diupdate.")
            #             st.session_state.edit_id = None
            #             st.session_state.page = "dashboard"
            #             st.rerun()

# If we came from pressing edit via dashboard selection earlier but earlier page logic didn't catch:
# if "prefill" in st.session_state and st.session_state.page == "input" and st.session_state.edit_id is None:
#     # prefill: user pressed Edit earlier, set edit_id and values
#     pre = st.session_state.pop("prefill")
#     st.session_state.edit_id = pre.get("id")
#     st.rerun()
