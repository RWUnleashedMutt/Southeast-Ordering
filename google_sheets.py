import time

import pandas as pd
import streamlit as st
import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials

from config import SCOPES, SHEET_IDS, RESERVED_STOCK_SHEET_ID
from catalog import clean_id


@st.cache_resource
def get_google_client():
    """Authenticate using Streamlit secrets — works both locally and on Streamlit Cloud."""
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    return gspread.authorize(creds)


def _with_backoff(fn, max_retries=5, base_delay=5, max_delay=60):
    """Run fn() and retry with exponential backoff (capped, so it can wait
    out a full per-minute quota window) on a 429 (rate limit) response —
    so loading several vendors' sheets back-to-back doesn't fail outright
    when Google's per-minute read quota is hit."""
    for attempt in range(max_retries):
        try:
            return fn()
        except APIError as e:
            if e.code != 429 or attempt == max_retries - 1:
                raise
            time.sleep(min(base_delay * (2 ** attempt), max_delay))


# Generous enough to cover any vendor sheet's full data without knowing its
# exact size up front.
_FULL_SHEET_RANGE = 'A1:ZZ5000'


def _fetch_first_sheet(client, sheet_id: str) -> pd.DataFrame:
    """Fetch a spreadsheet's first tab in a SINGLE Sheets API read.

    gspread's usual `open_by_key()` -> `.sheet1` -> `get_all_records()`
    path costs 2 API calls per sheet: `open_by_key` itself eagerly fetches
    sheet metadata in `Spreadsheet.__init__` (just to identify "the first
    tab"), then `get_all_records` fetches values separately. Omitting the
    sheet name from the range defaults to the first tab, so calling the
    underlying HTTP client's `values_get` directly — skipping `Spreadsheet`
    construction entirely — gets the same data in 1 call, halving the
    read-quota cost of loading N vendors.
    """
    response = _with_backoff(lambda: client.http_client.values_get(
        sheet_id, _FULL_SHEET_RANGE,
        params={'valueRenderOption': 'UNFORMATTED_VALUE'}))
    values = response.get('values', [])
    if not values:
        return pd.DataFrame()

    headers = values[0]
    width = len(headers)
    rows = [
        row + [''] * (width - len(row)) if len(row) < width else row[:width]
        for row in values[1:]
    ]
    return pd.DataFrame(rows, columns=headers)


@st.cache_data(ttl=3600)  # Cache for one hour
def load_rules_from_sheets(vendor: str) -> pd.DataFrame:
    """Pull the rules matrix for the given vendor from Google Sheets."""
    if vendor not in SHEET_IDS:
        raise ValueError(f"No Sheet ID configured for vendor '{vendor}'.")
    client = get_google_client()
    df = _fetch_first_sheet(client, SHEET_IDS[vendor])
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


@st.cache_data(ttl=3600)  # Cache for one hour
def load_reserved_stock() -> dict:
    """Pull SKU -> qty reserved for other events from the reserved stock
    sheet (SKU, Item Name, QTY columns), so HQ availability can exclude
    stock that's held back and can't be pulled for stores."""
    client = get_google_client()
    df = _fetch_first_sheet(client, RESERVED_STOCK_SHEET_ID)
    df.columns = df.columns.str.strip()
    df['SKU'] = df['SKU'].apply(clean_id)
    df['QTY'] = pd.to_numeric(df['QTY'], errors='coerce').fillna(0)

    return df.groupby('SKU')['QTY'].sum().to_dict()
