import streamlit as st
import pandas as pd
import io
import numpy as np
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIG ---
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

SHEET_IDS = {

    'SE': '1O6HWGeLgtdScnJ0_pQc8asaSj3-L4pP9vjCvvXa26vQ',
    'Test': '1w043eKET6T8-Fn5QSKFFkrintQt2p2h3CqDBAr665Bs'
    # Add a line for each vendor
}

# SKUs to completely ignore - add any SKUs here that should be excluded from ordering
IGNORE_SKUS = {
    # 'SKU123',
    # 'SKU456',
}

store_map = {
    'Current Quantity City Market: DTR': 'CM',
    'Current Quantity Crabtree Valley Mall': 'CVM',
    'Current Quantity Crescent Commons': 'CC',
    'Current Quantity Downtown Durham': 'DTD',
    'Current Quantity Front Street': 'MF',
    'Current Quantity Lake Boone': 'LB',
    'Current Quantity Landfall Shopping Center': 'LF',
    'Current Quantity Parkway Plaza': 'PP',
    'Current Quantity Southport - Tidewater': 'SP',
    'Current Quantity Stonehenge Market': 'SH',
    'Current Quantity The Streets at Southpoint': 'SS'
}

inv_store_map = {v: k for k, v in store_map.items()}
priority_stores = ['CC', 'CM', 'CVM', 'LB', 'SH']


# --- HELPERS ---
def clean_id(val):
    if pd.isna(val):
        return ""
    return str(int(val)) if isinstance(val, float) and val.is_integer() else str(val)


@st.cache_data
def load_catalog(file) -> pd.DataFrame:
    # Specify GTIN as string to preserve leading zeros
    dtype_dict = {'GTIN': str, 'SKU': str}
    df = pd.read_excel(file, header=1, dtype=dtype_dict)
    df.columns = df.columns.str.strip()
    df['SKU'] = df['SKU'].apply(clean_id)
    if 'GTIN' in df.columns:
        # Keep GTIN as string and just strip whitespace
        df['GTIN'] = df['GTIN'].astype(str).str.strip()
    return df


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
    return df


# --- APP ---
st.set_page_config(page_title="Inventory & Ordering System", layout="wide")
st.title("📦 Southeast Inventory & Ordering")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Upload Files")
    catalog_file = st.file_uploader(
        "Upload Southeast Catalog (.xlsx)", type=['xlsx'])

    st.divider()
    st.header("2. Vendor")
    selected_vendor = st.selectbox(
        "Select vendor to load rules from Google Sheets:",
        options=["-- Select a Vendor --"] + list(SHEET_IDS.keys())
    )

    load_rules_btn = st.button("📥 Load Rules from Google Sheets")

    st.divider()
    st.header("3. Store Selection")
    selected_stores = st.multiselect(
        "Select stores:", options=list(store_map.values()), default=priority_stores
    )

    st.divider()
    st.header("4. Store Lead Times (Days)")
    store_lead_times = {
        s: st.number_input(
            f"Lead Time: {s}", 0, 30, (1 if s in priority_stores else 7))
        for s in selected_stores
    }

# --- LOAD RULES FROM SHEETS ---
rules_matrix = None

if selected_vendor == "-- Select a Vendor --":
    st.sidebar.info("Please select a vendor to load rules.")
elif load_rules_btn:
    with st.spinner(f"Loading rules matrix for **{selected_vendor}** from Google Sheets..."):
        try:
            rules_matrix = load_rules_from_sheets(selected_vendor)
            st.session_state["rules_matrix"] = rules_matrix
            st.session_state["rules_vendor"] = selected_vendor
            st.sidebar.success(f"✅ Rules loaded: {len(rules_matrix)} SKUs")
        except Exception as e:
            st.sidebar.error(f"❌ Failed to load rules: {e}")
elif "rules_matrix" in st.session_state and st.session_state.get("rules_vendor") == selected_vendor:
    # Keep the already-loaded matrix if vendor hasn't changed
    rules_matrix = st.session_state["rules_matrix"]
    st.sidebar.success(f"✅ Rules loaded: {len(rules_matrix)} SKUs")

# --- MAIN APP ---
if catalog_file and rules_matrix is not None and selected_stores:
    df_master = load_catalog(catalog_file)

    # Filter rules to only SKUs present in the catalog
    catalog_skus = set(df_master['SKU'].unique())
    rules_matrix = rules_matrix[rules_matrix['SKU'].isin(catalog_skus)].copy()

    # Remove any SKUs in the ignore list
    rules_matrix = rules_matrix[~rules_matrix['SKU'].isin(IGNORE_SKUS)].copy()

    hq_col = 'Current Quantity HQ'
    date_str = datetime.now().strftime("%Y-%m-%d")

    if hq_col not in df_master.columns:
        st.error(f"❌ Missing column: '{hq_col}'")
        st.stop()

    matched = len(rules_matrix['SKU'].unique())
    total = len(catalog_skus)

    # Find SKUs that didn't match
    rules_skus = set(rules_matrix['SKU'].unique())
    unmatched_skus = catalog_skus - rules_skus
    unmatched_list = sorted(list(unmatched_skus))

    st.caption(f"✅ Matched {matched} of {total} catalog SKUs to rules.")

    # Log unmatched SKUs to console
    if unmatched_skus:
        print(f"\n⚠️  WARNING: {len(unmatched_skus)} Unmatched SKUs found:")
        for sku in unmatched_list:
            item_name = df_master[df_master['SKU'] == sku]['Item Name'].iloc[0] if len(
                df_master[df_master['SKU'] == sku]) > 0 else "Unknown"
            print(f"  - {sku}: {item_name}")
        print(f"\nTotal unmatched: {len(unmatched_skus)}\n")

    tabs = st.tabs(selected_stores)

    for i, short_name in enumerate(selected_stores):
        long_name = inv_store_map[short_name]
        with tabs[i]:
            if long_name in df_master.columns:
                current_lt = store_lead_times[short_name]

                # 1. Rules & Merge
                lookup_cols = ['SKU', 'Order In Quantities',
                               f'{short_name}_DNO', f'{short_name}_Min', f'{short_name}_Max']
                valid_lookup = [
                    c for c in lookup_cols if c in rules_matrix.columns]
                store_rules = rules_matrix[valid_lookup].copy().rename(columns={
                    f'{short_name}_DNO': 'DNO',
                    f'{short_name}_Min': 'Min',
                    f'{short_name}_Max': 'Max'
                })

                store_inv = df_master[[
                    'SKU', 'GTIN', 'Item Name', 'Default Unit Cost', long_name, hq_col
                ]].copy().rename(columns={long_name: 'Current_Inv', hq_col: 'HQ_Qty'})

                data = pd.merge(store_inv, store_rules, on='SKU', how='left')
                data = data.fillna({
                    'DNO': False, 'Order In Quantities': 1, 'Min': 0,
                    'Max': 0, 'Current_Inv': 0, 'HQ_Qty': 0, 'Default Unit Cost': 0
                })

                # 2. Split Trigger Logic
                data['Effective_Min'] = data['Min'] + (current_lt * 0.2)
                data['Needs_Order'] = np.where(
                    data['Order In Quantities'] == 1,
                    (data['Current_Inv'] < data['Max']),
                    (data['Current_Inv'] < data['Effective_Min'])
                )
                data['Needs_Order'] = data['Needs_Order'] & (
                    data['DNO'] == False)
                data['Units_Needed_To_Max'] = np.where(
                    data['Needs_Order'], data['Max'] - data['Current_Inv'], 0
                )
                data['Total_Units_Needed'] = np.ceil(
                    np.maximum(data['Units_Needed_To_Max'], 0) /
                    data['Order In Quantities']
                ) * data['Order In Quantities']

                # 3. HQ Transfer UI
                st.subheader(f"🚛 HQ Transfer List: {short_name}")
                st.caption(
                    "Items with HQ Stock > 6 are suggested here. Delete a row or set Qty to 0 to move it to the Vendor Order.")

                data['Suggested_HQ_Qty'] = np.where(
                    (data['Total_Units_Needed'] > 0) & (data['HQ_Qty'] > 6),
                    data['Total_Units_Needed'], 0
                )

                hq_display = data[data['Suggested_HQ_Qty'] > 0][[
                    'SKU', 'GTIN', 'Item Name', 'Suggested_HQ_Qty', 'Current_Inv', 'HQ_Qty'
                ]].copy()
                hq_display.rename(
                    columns={'Suggested_HQ_Qty': 'Transfer_Qty'}, inplace=True)

                ed_hq = st.data_editor(hq_display, use_container_width=True,
                                       hide_index=True, num_rows="dynamic", key=f"hq_ed_{short_name}")

                # Display HQ Transfer Cost
                if not ed_hq.empty:
                    # Merge with original data to get unit cost
                    ed_hq_with_cost = ed_hq.merge(
                        data[['SKU', 'Default Unit Cost']], on='SKU', how='left'
                    )
                    hq_cost = (
                        ed_hq_with_cost['Transfer_Qty'] * ed_hq_with_cost['Default Unit Cost']).sum()
                    st.metric("🏭 HQ Transfer Cost", f"${hq_cost:,.2f}")

                # 4. Vendor Remainder
                hq_final_map = ed_hq.set_index('SKU')['Transfer_Qty'].to_dict()
                data['Final_HQ_Qty'] = data['SKU'].map(
                    lambda x: hq_final_map.get(x, 0))
                data['Vendor_Units'] = (
                    data['Total_Units_Needed'] - data['Final_HQ_Qty']).clip(lower=0)
                data['Vendor_Cases'] = data['Vendor_Units'] / \
                    data['Order In Quantities']

                if not ed_hq.empty:
                    st.metric("Total Transfer Units",
                              f"{int(ed_hq['Transfer_Qty'].sum())}")
                    buf_hq = io.BytesIO()
                    with pd.ExcelWriter(buf_hq, engine='xlsxwriter') as writer:
                        ed_hq.to_excel(writer, index=False,
                                       sheet_name='HQ_Transfer')
                        # Format GTIN column as text to preserve leading zeros
                        text_fmt = writer.book.add_format({'num_format': '@'})
                        writer.sheets['HQ_Transfer'].set_column(
                            'B:B', 20, text_fmt)
                    st.download_button(f"📥 Download HQ Transfer", buf_hq.getvalue(),
                                       file_name=f"{date_str}_HQ_{short_name}.xlsx",
                                       key=f"dl_hq_{short_name}")

                st.divider()

                # 5. Vendor Order UI
                st.subheader(f"🛒 Vendor Orders: {short_name}")
                order_summary = data[data['Vendor_Units'] > 0][[
                    'SKU', 'GTIN', 'Item Name', 'Vendor_Cases', 'Order In Quantities',
                    'Vendor_Units', 'Current_Inv', 'Max', 'Default Unit Cost'
                ]].copy().reset_index(drop=True)
                order_summary.rename(columns={
                    'Vendor_Cases': 'Order (Cases)',
                    'Order In Quantities': 'Case Pack',
                    'Vendor_Units': 'Total Units'
                }, inplace=True)

                if not order_summary.empty:
                    frozen_mask = order_summary['Item Name'].str.startswith(
                        'FRZN', na=False)

                    for label, df_type in [
                        ("📦 Dry Order", order_summary[~frozen_mask]),
                        ("❄️ Frozen Order", order_summary[frozen_mask])
                    ]:
                        st.markdown(f"#### {label}")
                        if not df_type.empty:
                            ed_df = st.data_editor(df_type, use_container_width=True,
                                                   hide_index=True, num_rows="dynamic",
                                                   key=f"vend_{label}_{short_name}")
                            cost = (ed_df['Total Units'] *
                                    ed_df['Default Unit Cost']).sum()
                            st.metric(f"{label} Cost", f"${cost:,.2f}")

                            export_df = ed_df[[
                                'GTIN', 'Item Name', 'Order (Cases)']].copy()
                            buf = io.BytesIO()
                            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                                export_df.to_excel(
                                    writer, index=False, sheet_name='Vendor_Order')
                                text_fmt = writer.book.add_format(
                                    {'num_format': '@'})
                                writer.sheets['Vendor_Order'].set_column(
                                    'A:A', 20, text_fmt)
                                writer.sheets['Vendor_Order'].set_column(
                                    'B:B', 40)
                            st.download_button(f"📥 Download {label}", buf.getvalue(),
                                               file_name=f"{date_str}_{label}_{short_name}.xlsx",
                                               key=f"dl_{label}_{short_name}")
                        else:
                            st.write("No items in this category.")
                else:
                    st.success(
                        "No vendor order needed (Items may be covered by HQ).")
            else:
                st.error(f"Missing column '{long_name}' in Catalog.")

# --- WELCOME / MISSING FILES STATE ---
elif not selected_stores:
    st.warning(
        "Please select at least one store in the sidebar to begin processing.")
elif not catalog_file:
    st.info("👋 **Welcome! Please upload the Southeast Catalog to begin.**")
    col_inst, col_img = st.columns([1, 1])
    with col_inst:
        st.subheader("📋 Step-by-Step Export Instructions")
        st.markdown("""
        1. **Login to Square Dashboard.**
        2. **Go to Items → Item Library.**
        3. **Filter by Vendor: Southeast Pet.**
        4. **Click Actions → Export Library.**
        5. **Select "Export items matching applied filters".**
        6. **Upload the file here.**
        """)
    with col_img:
        st.subheader("📸 Reference Settings")
        try:
            st.image("./Data/Images/Export Example.png",
                     use_container_width=True, caption="Select the 'Filtered' option.")
        except:
            st.warning("Reference image not found.")
elif rules_matrix is None:
    st.warning(
        "⚠️ Please select a vendor and click 'Load Rules from Google Sheets' to continue.")
