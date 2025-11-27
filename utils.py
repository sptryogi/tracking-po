# utils.py
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

JAKARTA = ZoneInfo("Asia/Jakarta")

def fmt_currency(x):
    # Format numeric as 100.000 (no decimals). Handles nan.
    try:
        return f"{int(x):,}".replace(",", ".")
    except:
        return x

def df_format_for_display(df):
    # Create a copy that formats currency columns and created_at tz
    df2 = df.copy()
    for col in ["total_tagihan", "total_bayar", "sisa"]:
        if col in df2.columns:
            df2[col] = df2[col].fillna(0).apply(fmt_currency)
    # created_at timezone convert (assume stored as UTC in supabase)
    if "created_at" in df2.columns:
        df2["created_at"] = pd.to_datetime(df2["created_at"], utc=True, errors="coerce").dt.tz_convert(JAKARTA)
        df2["created_at"] = df2["created_at"].dt.strftime("%Y-%m-%d %H:%M:%S")
    # tanggal / jatuh_tempo format
    for dcol in ["tanggal", "jatuh_tempo"]:
        if dcol in df2.columns:
            df2[dcol] = pd.to_datetime(df2[dcol], errors="coerce").dt.strftime("%Y-%m-%d")
    return df2
