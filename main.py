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
    selected_stores = st.multiselect(
        "Select stores for ordering:",
        options=list(store_map.values()),
        default=priority_stores
    )

    st.divider()

    st.header("3. Store Lead Times (Days)")
    store_lead_times = {}
    for short_name in selected_stores:
        default_val = 1 if short_name in priority_stores else 7
        store_lead_times[short_name] = st.number_input(
            f"Lead Time: {short_name}",
            min_value=0, max_value=30, value=default_val
        )

# --- MAIN APP ---
RULES_FILE_PATH = './Data/Rules/Southeast Rules Matrix.xlsx'

if catalog_file and selected_stores:
    # 1. Load and Clean Data
    df_master = pd.read_excel(catalog_file, header=1)
    df_master.columns = df_master.columns.str.strip()

    # Helper function to clean SKU/GTIN from .0 decimals
    def clean_id(val):
        if pd.isna(val):
            return ""
        # If it's a float like 123.0, convert to int then str
        if isinstance(val, float) and val.is_integer():
            return str(int(val))
        return str(val)

    # Apply the clean ID function
    df_master['SKU'] = df_master['SKU'].apply(clean_id)
    if 'GTIN' in df_master.columns:
        df_master['GTIN'] = df_master['GTIN'].apply(clean_id)

    rules_matrix = pd.read_excel(RULES_FILE_PATH)
    rules_matrix.columns = rules_matrix.columns.str.strip()
    rules_matrix['SKU'] = rules_matrix['SKU'].apply(clean_id)

    st.header(f"Order Processing")

    hq_col = 'Current Quantity HQ'
    date_str = datetime.now().strftime("%d-%m-%Y")

    if hq_col not in df_master.columns:
        st.error(f"❌ Missing column: '{hq_col}' in catalog.")
        st.stop()

    tabs = st.tabs(selected_stores)

    for i, short_name in enumerate(selected_stores):
        long_name = inv_store_map[short_name]

        with tabs[i]:
            if long_name in df_master.columns:
                current_lt = store_lead_times[short_name]

                # Prepare Rules
                lookup_cols = [
                    'SKU', 'Order_Qty', f'{short_name}_DNO', f'{short_name}_Min', f'{short_name}_Max']
                valid_lookup = [
                    c for c in lookup_cols if c in rules_matrix.columns]
                store_rules = rules_matrix[valid_lookup].copy().rename(columns={
                    f'{short_name}_DNO': 'DNO', f'{short_name}_Min': 'Min', f'{short_name}_Max': 'Max'
                })

                # Merge Data
                store_inv = df_master[['SKU', 'GTIN', 'Description', 'Default Unit Cost', long_name, hq_col]].copy(
                ).rename(columns={long_name: 'Current_Inv', hq_col: 'HQ_Qty'})

                data = pd.merge(store_inv, store_rules, on='SKU', how='left')
                data = data.fillna({'DNO': False, 'Order_Qty': 1, 'Min': 0, 'Max': 0,
                                   'Current_Inv': 0, 'HQ_Qty': 0, 'Default Unit Cost': 0})

                # 2. Logic
                data['Effective_Min'] = data['Min'] + (current_lt * 0.2)
                data['Needs_Order'] = (data['Current_Inv'] < data['Effective_Min']) & (
                    data['DNO'] == False)
                data['Gap_To_Max'] = np.where(
                    data['Needs_Order'], data['Max'] - data['Current_Inv'], 0)
                raw_order = np.ceil(np.maximum(
                    data['Gap_To_Max'], 0) / data['Order_Qty']) * data['Order_Qty']

                # Split Vendor vs HQ
                data['Order'] = np.where(data['HQ_Qty'] > 6, 0, raw_order)
                data['HQ_Transfer_Qty'] = np.where(
                    (raw_order > 0) & (data['HQ_Qty'] > 6), raw_order, 0)

                # 3. Create Summaries
                order_summary = data[data['Order'] > 0][[
                    'SKU', 'GTIN', 'Description', 'Order', 'Current_Inv', 'Min', 'Max', 'Default Unit Cost'
                ]].copy().reset_index(drop=True)

                hq_transfer_summary = data[data['HQ_Transfer_Qty'] > 0][[
                    'SKU', 'GTIN', 'Description', 'HQ_Transfer_Qty', 'Current_Inv', 'HQ_Qty'
                ]].copy().reset_index(drop=True)

                # --- UI SECTION 1: VENDOR ORDER ---
                st.subheader(f"🛒 Vendor Order List: {short_name}")
                if not order_summary.empty:
                    edited_vendor_df = st.data_editor(
                        order_summary,
                        use_container_width=True,
                        hide_index=True,
                        key=f"ed_v_{short_name}",
                        column_config={
                            "SKU": st.column_config.TextColumn("SKU"),
                            "GTIN": st.column_config.TextColumn("GTIN"),
                            "Order": st.column_config.NumberColumn("Order Amount", min_value=0, step=1),
                            "Min": st.column_config.NumberColumn("Min", disabled=True),
                            "Max": st.column_config.NumberColumn("Max", disabled=True),
                            "Current_Inv": st.column_config.NumberColumn("Current Inv", disabled=True),
                            "Default Unit Cost": st.column_config.NumberColumn("Unit Cost", format="$%.2f", disabled=True)
                        }
                    )
                    v_total = (
                        edited_vendor_df['Order'] * edited_vendor_df['Default Unit Cost']).sum()
                    st.metric("Vendor Order Cost", f"${v_total:,.2f}")

                    buf1 = io.BytesIO()
                    with pd.ExcelWriter(buf1, engine='xlsxwriter') as writer:
                        edited_vendor_df.to_excel(
                            writer, index=False, sheet_name='Vendor_Order')
                        text_fmt = writer.book.add_format({'num_format': '@'})
                        writer.sheets['Vendor_Order'].set_column(
                            'A:B', 18, text_fmt)

                    st.download_button(f"📥 Download Vendor Order ({short_name})", buf1.getvalue(),
                                       file_name=f"{date_str}_Vendor_Order_{short_name}.xlsx", key=f"dl_v_{short_name}")
                else:
                    st.success("No vendor order needed.")

                st.divider()

                # --- UI SECTION 2: HQ TRANSFER ---
                st.subheader(f"🚛 HQ Transfer List: {short_name}")
                if not hq_transfer_summary.empty:
                    edited_hq_df = st.data_editor(
                        hq_transfer_summary,
                        use_container_width=True,
                        hide_index=True,
                        key=f"ed_h_{short_name}",
                        column_config={
                            "SKU": st.column_config.TextColumn("SKU"),
                            "GTIN": st.column_config.TextColumn("GTIN"),
                            "HQ_Transfer_Qty": st.column_config.NumberColumn("Transfer Amount", min_value=0, step=1),
                            "HQ_Qty": st.column_config.NumberColumn("Available at HQ", disabled=True)
                        }
                    )
                    st.metric("Total Items to Transfer",
                              f"{int(edited_hq_df['HQ_Transfer_Qty'].sum())}")

                    buf2 = io.BytesIO()
                    with pd.ExcelWriter(buf2, engine='xlsxwriter') as writer:
                        edited_hq_df.to_excel(
                            writer, index=False, sheet_name='HQ_Transfer')
                        text_fmt = writer.book.add_format({'num_format': '@'})
                        writer.sheets['HQ_Transfer'].set_column(
                            'A:B', 18, text_fmt)

                    st.download_button(f"📥 Download HQ Transfer ({short_name})", buf2.getvalue(),
                                       file_name=f"{date_str}_HQ_Transfer_{short_name}.xlsx", key=f"dl_h_{short_name}")
                else:
                    st.info("No items available for transfer from HQ.")

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
        
        1. **Login to Square:** Open the [Square Dashboard](https://app.squareup.com/dashboard).
        2. **Navigate to Library:** Go to **Items & Services** → **Items** → **Item Library**.
        3. **Apply Filter:** Click the **Filters** button next to the search bar and set the **Vendor** to **Southeast Pet**.
        4. **Initiate Export:** Click the **Actions** button in the top-right corner and select **Export Library**.
        5. **Critical Selection:** In the pop-up window, ensure you select **"Export items matching applied filters"**.
        6. **Upload:** Once downloaded, upload the `.xlsx` file using the sidebar on the left.
        """)

    with col_img:
        st.subheader("📸 Reference Settings")
        st.image("./Data/Images/Export Example.png", use_container_width=True,
                 caption="Select the 'Filtered' option as shown above.")
        st.warning(
            "⚠️ **Note:** Ensure you export the 'Filtered' list, not the entire library, to prevent processing errors.")
