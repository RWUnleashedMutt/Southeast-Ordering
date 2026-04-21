import streamlit as st
import pandas as pd
import io
import numpy as np
from datetime import datetime

# --- CONFIG ---
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

st.set_page_config(page_title="Inventory & Ordering System", layout="wide")
st.title("📦 Southeast Inventory & Ordering")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Upload Files")
    catalog_file = st.file_uploader(
        "Upload Southeast Catalog (.xlsx)", type=['xlsx'])
    st.divider()
    st.header("2. Store Selection")
    selected_stores = st.multiselect("Select stores:", options=list(
        store_map.values()), default=priority_stores)
    st.divider()
    st.header("3. Store Lead Times (Days)")
    store_lead_times = {s: st.number_input(
        f"Lead Time: {s}", 0, 30, (1 if s in priority_stores else 7)) for s in selected_stores}

# --- MAIN APP ---
RULES_FILE_PATH = './Data/Rules/Southeast Rules Matrix.xlsx'

if catalog_file and selected_stores:
    df_master = pd.read_excel(catalog_file, header=1)
    df_master.columns = df_master.columns.str.strip()

    def clean_id(val):
        if pd.isna(val):
            return ""
        return str(int(val)) if isinstance(val, float) and val.is_integer() else str(val)

    df_master['SKU'] = df_master['SKU'].apply(clean_id)
    if 'GTIN' in df_master.columns:
        df_master['GTIN'] = df_master['GTIN'].apply(clean_id)

    rules_matrix = pd.read_excel(RULES_FILE_PATH)
    rules_matrix.columns = rules_matrix.columns.str.strip()
    rules_matrix['SKU'] = rules_matrix['SKU'].apply(clean_id)

    hq_col = 'Current Quantity HQ'
    date_str = datetime.now().strftime("%d-%m-%Y")

    if hq_col not in df_master.columns:
        st.error(f"❌ Missing column: '{hq_col}'")
        st.stop()

    tabs = st.tabs(selected_stores)

    for i, short_name in enumerate(selected_stores):
        long_name = inv_store_map[short_name]
        with tabs[i]:
            if long_name in df_master.columns:
                current_lt = store_lead_times[short_name]

                # Rules prep
                lookup_cols = ['SKU', 'Order In Quantities',
                               f'{short_name}_DNO', f'{short_name}_Min', f'{short_name}_Max']
                valid_lookup = [
                    c for c in lookup_cols if c in rules_matrix.columns]
                store_rules = rules_matrix[valid_lookup].copy().rename(columns={
                    f'{short_name}_DNO': 'DNO', f'{short_name}_Min': 'Min', f'{short_name}_Max': 'Max'
                })

                # Merge
                store_inv = df_master[['SKU', 'GTIN', 'Description', 'Default Unit Cost', long_name, hq_col]].copy(
                ).rename(columns={long_name: 'Current_Inv', hq_col: 'HQ_Qty'})
                data = pd.merge(store_inv, store_rules, on='SKU', how='left')
                data = data.fillna({'DNO': False, 'Order In Quantities': 1, 'Min': 0,
                                   'Max': 0, 'Current_Inv': 0, 'HQ_Qty': 0, 'Default Unit Cost': 0})

                # --- CASE PACK & OVER-MAX LOGIC ---
                data['Effective_Min'] = data['Min'] + (current_lt * 0.2)
                data['Needs_Order'] = (data['Current_Inv'] < data['Effective_Min']) & (
                    data['DNO'] == False)
                data['Units_Needed_To_Max'] = np.where(
                    data['Needs_Order'], data['Max'] - data['Current_Inv'], 0)

                # Total Units (Round up to nearest case pack)
                data['Total_Units'] = np.ceil(np.maximum(
                    data['Units_Needed_To_Max'], 0) / data['Order In Quantities']) * data['Order In Quantities']

                # Order Cases
                data['Order_Cases'] = data['Total_Units'] / \
                    data['Order In Quantities']

                # Split Vendor vs HQ
                is_hq_transfer = (data['Total_Units'] > 0) & (
                    data['HQ_Qty'] > 6)
                data['Vendor_Units'] = np.where(
                    is_hq_transfer, 0, data['Total_Units'])
                data['Vendor_Cases'] = np.where(
                    is_hq_transfer, 0, data['Order_Cases'])
                data['HQ_Transfer_Qty'] = np.where(
                    is_hq_transfer, data['Total_Units'], 0)

                # Summary: Vendor
                order_summary = data[data['Vendor_Units'] > 0][[
                    'SKU', 'GTIN', 'Description', 'Vendor_Cases', 'Order In Quantities', 'Vendor_Units', 'Current_Inv', 'Max', 'Default Unit Cost'
                ]].copy().reset_index(drop=True)

                order_summary.rename(columns={
                    'Vendor_Cases': 'Order (Cases)',
                    'Order In Quantities': 'Case Pack',
                    'Vendor_Units': 'Total Units'
                }, inplace=True)

                # Summary: HQ
                hq_transfer_summary = data[data['HQ_Transfer_Qty'] > 0][[
                    'SKU', 'GTIN', 'Description', 'HQ_Transfer_Qty', 'Current_Inv', 'HQ_Qty'
                ]].copy().reset_index(drop=True)

                # --- UI: VENDOR ORDERS ---
                st.subheader(f"🛒 Vendor Orders: {short_name}")
                if not order_summary.empty:
                    frozen_mask = order_summary['Description'].str.startswith(
                        'FRZN', na=False)
                    for label, df_type in [("📦 Dry Order", order_summary[~frozen_mask]), ("❄️ Frozen Order", order_summary[frozen_mask])]:
                        st.markdown(f"#### {label}")
                        if not df_type.empty:
                            ed_df = st.data_editor(
                                df_type, use_container_width=True, hide_index=True, num_rows="dynamic", key=f"{label}_{short_name}")
                            cost = (ed_df['Total Units'] *
                                    ed_df['Default Unit Cost']).sum()
                            st.metric(f"{label} Cost", f"${cost:,.2f}")

                            # --- CLEAN EXPORT FOR VENDOR ---
                            # Only gtin, description, and order(cases)
                            export_df = ed_df[[
                                'GTIN', 'Description', 'Order (Cases)']].copy()

                            buf = io.BytesIO()
                            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                                export_df.to_excel(
                                    writer, index=False, sheet_name='Vendor_Order')
                                text_fmt = writer.book.add_format(
                                    {'num_format': '@'})
                                writer.sheets['Vendor_Order'].set_column(
                                    'A:A', 20, text_fmt)  # Format GTIN as text
                                writer.sheets['Vendor_Order'].set_column(
                                    'B:B', 40)         # Wide Description

                            st.download_button(f"📥 Download {label}", buf.getvalue(
                            ), file_name=f"{date_str}_{label}_{short_name}.xlsx", key=f"dl_{label}_{short_name}")
                        else:
                            st.write("No items in this category.")
                else:
                    st.success("No vendor order needed.")

                # --- UI: HQ TRANSFERS ---
                st.divider()
                st.subheader(f"🚛 HQ Transfer List: {short_name}")
                if not hq_transfer_summary.empty:
                    ed_hq = st.data_editor(hq_transfer_summary, use_container_width=True,
                                           hide_index=True, num_rows="dynamic", key=f"hq_{short_name}")
                    st.metric("Total Transfer Units",
                              f"{int(ed_hq['HQ_Transfer_Qty'].sum())}")

                    buf_hq = io.BytesIO()
                    with pd.ExcelWriter(buf_hq, engine='xlsxwriter') as writer:
                        ed_hq.to_excel(writer, index=False,
                                       sheet_name='HQ_Transfer')
                        text_fmt = writer.book.add_format({'num_format': '@'})
                        writer.sheets['HQ_Transfer'].set_column(
                            'A:B', 18, text_fmt)
                    st.download_button(f"📥 Download HQ Transfer", buf_hq.getvalue(
                    ), file_name=f"{date_str}_HQ_{short_name}.xlsx", key=f"dl_hq_{short_name}")
                else:
                    st.info("No items for HQ transfer.")

            else:
                st.error(f"Missing column '{long_name}' in Catalog.")

elif not selected_stores:
    st.warning(
        "Please select at least one store in the sidebar to begin processing.")

else:
    # --- INSTRUCTIONS DASHBOARD ---
    st.info("👋 **Welcome! Please upload the Southeast Catalog to begin.**")
    col_inst, col_img = st.columns([1, 1])
    with col_inst:
        st.subheader("📋 Step-by-Step Export Instructions")
        st.markdown("""
        To ensure accurate data processing, please follow these steps to export your Catalog from Square:
        1. **Login to Square Dashboard.**
        2. **Go to Items → Item Library.**
        3. **Filter by Vendor: Southeast Pet.**
        4. **Click Actions → Export Library.**
        5. **Select "Export items matching applied filters".**
        6. **Upload the file here.**
        """)
    with col_img:
        st.subheader("📸 Reference Settings")
        st.image("./Data/Images/Export Example.png",
                 use_container_width=True, caption="Select the 'Filtered' option.")
        st.warning(
            "⚠️ **Note:** Ensure you export the 'Filtered' list, not the entire library, to prevent processing errors.")
