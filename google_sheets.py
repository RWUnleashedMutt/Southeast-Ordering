import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

from config import SCOPES, SHEET_IDS
from catalog import clean_id


@st.cache_resource
def get_google_client():
    """Authenticate using Streamlit secrets — works both locally and on Streamlit Cloud."""
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    return gspread.authorize(creds)


@st.cache_data(ttl=3600)  # Cache for one hour
def load_rules_from_sheets(vendor: str) -> pd.DataFrame:
    """Pull the rules matrix for the given vendor from Google Sheets."""
    if vendor not in SHEET_IDS:
        raise ValueError(f"No Sheet ID configured for vendor '{vendor}'.")
    client = get_google_client()
    spreadsheet = client.open_by_key(SHEET_IDS[vendor])
    worksheet = spreadsheet.sheet1
    data = worksheet.get_all_records(value_render_option='UNFORMATTED_VALUE')
    df = pd.DataFrame(data)
    df.columns = df.columns.str.strip()
    df['SKU'] = df['SKU'].apply(clean_id)

    for col in df.columns:
        if col == 'SKU':
            continue
        if col.endswith('_DNO'):
            df[col] = df[col].map(
                lambda x: str(x).strip().upper() in ('TRUE', '1', 'YES', '1.0')
                if pd.notna(x) else False
            ).astype(bool)
        else:
            converted = pd.to_numeric(df[col], errors='coerce')
            if converted.notna().sum() > 0:
                df[col] = converted

    return df
