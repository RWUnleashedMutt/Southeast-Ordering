import streamlit as st
import pandas as pd
import io
import numpy as np

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

priority_stores = ['CC', 'CM', 'CVM', 'LB', 'SH']

st.set_page_config(page_title="Inventory & Ordering System", layout="wide")
st.title("📦 Southeast Inventory & Ordering")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Upload Files")
    catalog_file = st.file_uploader("Upload Southeast Catalog", type=['xlsx'])

    st.divider()

    st.header("2. Store Lead Times (Days)")
    store_lead_times = {}
    for short_name in store_map.values():
        default_val = 1 if short_name in priority_stores else 7
        store_lead_times[short_name] = st.number_input(
            f"Lead Time: {short_name}",
            min_value=0, max_value=30, value=default_val
        )

# --- MAIN APP ---
RULES_FILE_PATH = './Data/Rules/Southeast Rules Matrix.xlsx'
if catalog_file:
    df_master = pd.read_excel(catalog_file, header=1, dtype={
                              'SKU': str, 'GTIN': str, 'Description': str})

    rules_matrix = pd.read_excel(RULES_FILE_PATH, dtype={
                                 'SKU': str, 'GTIN': str})

    st.header("3. Store Order Sheets")

    tabs = st.tabs(list(store_map.values()))

    for i, (long_name, short_name) in enumerate(store_map.items()):
        with tabs[i]:
            if long_name in df_master.columns:
                current_lt = store_lead_times[short_name]

                # 1. Prepare Base Data
                lookup_cols = [
                    'SKU', 'Order_Qty', f'{short_name}_DNO', f'{short_name}_Min', f'{short_name}_Max']
                valid_lookup = [
                    c for c in lookup_cols if c in rules_matrix.columns]
                store_rules = rules_matrix[valid_lookup].copy().rename(columns={
                    f'{short_name}_DNO': 'DNO', f'{short_name}_Min': 'Min', f'{short_name}_Max': 'Max'
                })

                store_inv = df_master[['SKU', 'GTIN', 'Description', 'Default Unit Cost', long_name]].copy(
                ).rename(columns={long_name: 'Current_Inv'})
                data = pd.merge(store_inv, store_rules, on='SKU', how='left')
                data = data.fillna({'DNO': False, 'Order_Qty': 1, 'Min': 0,
                                   'Max': 0, 'Current_Inv': 0, 'Default Unit Cost': 0})

                # 2. Initial Order Calculation
                data['Effective_Min'] = data['Min'] + (current_lt * 0.2)
                data['Needs_Order'] = (data['Current_Inv'] < data['Effective_Min']) & (
                    data['DNO'] == False)
                data['Gap_To_Max'] = np.where(
                    data['Needs_Order'], data['Max'] - data['Current_Inv'], 0)
                data['Order'] = np.ceil(np.maximum(
                    data['Gap_To_Max'], 0) / data['Order_Qty']) * data['Order_Qty']

                # 3. Filter for Display
                order_summary = data[data['Order'] > 0][[
                    'SKU', 'GTIN', 'Description', 'Order',
                    'Current_Inv', 'Effective_Min', 'Min', 'Max',
                    'Default Unit Cost'
                ]].copy()

               # 4. DATA EDITOR
                # .reset_index(drop=True) ensures a range index (0, 1, 2...)
                # This allows hide_index=True to work with num_rows="dynamic"
                display_df = order_summary.reset_index(drop=True)

                edited_df = st.data_editor(
                    display_df,
                    width="stretch",           # Replaced use_container_width=True
                    hide_index=True,           # Now works because of reset_index above
                    num_rows="dynamic",
                    key=f"editor_{short_name}",
                    column_config={
                        "Order": st.column_config.NumberColumn("Order", min_value=0, step=1, required=True),
                        "Default Unit Cost": st.column_config.NumberColumn("Unit Cost", format="$%.2f", disabled=True),
                        "SKU": st.column_config.TextColumn("SKU"),
                        "GTIN": st.column_config.TextColumn("GTIN")
                    }
                )

                # 5. REACTIVE CALCULATION
                # This ensures that even if 'Order' changed, the cost follows
                edited_df['Line_Cost'] = edited_df['Order'] * \
                    edited_df['Default Unit Cost']

                total_cost = edited_df['Line_Cost'].sum()

                # Display metrics based on the EDITED data
                m1, m2 = st.columns(2)
                m1.metric("Final Order Total", f"${total_cost:,.2f}")
                m2.info(
                    "👆 Edit the 'Order' column above; the total will update once you click out of the cell.")

                # 6. DOWNLOAD BUTTON
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    # Move Line_Cost to the end for the final file
                    edited_df.to_excel(writer, index=False,
                                       sheet_name='Order_Report')
                    workbook = writer.book
                    worksheet = writer.sheets['Order_Report']
                    money_fmt = workbook.add_format(
                        {'num_format': '$#,##0.00'})
                    text_fmt = workbook.add_format({'num_format': '@'})
                    worksheet.set_column('A:B', 15, text_fmt)
                    worksheet.set_column('C:C', 40)
                    # Formatting Unit Cost and the new Line Cost
                    worksheet.set_column('I:J', 14, money_fmt)

                st.download_button(
                    label=f"💾 Download Edited {short_name} Order",
                    data=buffer.getvalue(),
                    file_name=f"Order_Sheet_{short_name}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_btn_{short_name}"
                )
            else:
                st.error(f"Missing column '{long_name}' in Catalog.")
else:
    st.info("Upload your Catalog and Matrix files in the sidebar.")
