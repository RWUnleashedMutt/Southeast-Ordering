import io
import streamlit as st
import numpy as np
import pandas as pd

from config import inv_store_map
from ordering import vendor_order_frame

# Session-state key holding each store tab's latest *edited* vendor order
# lines, so the consolidated summary can reflect what will really be ordered.
STORE_EDITS_KEY = "store_vendor_edits"


def _num(series, default=0):
    return pd.to_numeric(series, errors='coerce').fillna(default)


def _record_vendor_edits(short_name, frames):
    """Remember this store's final (edited) vendor-order lines."""
    cols = ['SKU', 'GTIN', 'Item Name', 'Case Pack', 'Cases',
            'Unit Cost', 'Order Units']
    non_empty = [f for f in frames if f is not None and not f.empty]
    result = (pd.concat(non_empty, ignore_index=True)[cols]
              if non_empty else pd.DataFrame(columns=cols))
    st.session_state.setdefault(STORE_EDITS_KEY, {})[short_name] = result


@st.fragment
def render_store_tab(short_name, data, date_str, hq_threshold):
    """
    Renders the HQ Transfer + Vendor Order UI for one store tab.
    Wrapped in @st.fragment so editing a data_editor or clicking a
    download button in THIS store's tab only reruns this function —
    not the catalog load, rules matrix, other store tabs, or the
    consolidated summary below. `data` is passed in fresh each full
    script run (from compute_store_order), and is only recomputed
    inside this fragment when the fragment itself reruns via one of
    its own widgets.
    """
    # HQ Transfer UI
    st.subheader(f"🚛 HQ Transfer List: {short_name}")
    st.caption(
        f"Items with HQ Stock > {hq_threshold} are suggested here (or your allocation above). "
        f"HQ Qty excludes stock reserved for other events. "
        f"Delete a row or set Qty to 0 to move it to the Vendor Order.")

    hq_display = data[data['Suggested_HQ_Qty'] > 0][[
        'SKU', 'GTIN', 'Item Name', 'Suggested_HQ_Qty', 'Current_Inv',
        'HQ_Qty', 'Max'
    ]].copy()
    hq_display.rename(
        columns={'Suggested_HQ_Qty': 'Transfer_Qty'}, inplace=True)

    ed_hq = st.data_editor(hq_display, width="stretch",
                           hide_index=True, num_rows="dynamic", key=f"hq_ed_{short_name}")

    ed_hq = ed_hq[ed_hq['SKU'].notna()].copy()
    # A blank/invalid quantity (e.g. a freshly added row) counts as 0 and
    # negatives are ignored, rather than silently poisoning the math below.
    ed_hq['Transfer_Qty'] = _num(ed_hq['Transfer_Qty']).clip(lower=0)

    if not ed_hq.empty:
        ed_hq_with_cost = ed_hq.merge(
            data[['SKU', 'Default Unit Cost']].drop_duplicates('SKU'),
            on='SKU', how='left'
        )
        hq_cost = (
            ed_hq_with_cost['Transfer_Qty'] * ed_hq_with_cost['Default Unit Cost']).sum()
        st.metric("🏭 HQ Transfer Cost", f"${hq_cost:,.2f}")

    # If the same SKU appears twice (a row was duplicated), sum the quantities.
    hq_final_map = ed_hq.groupby('SKU')['Transfer_Qty'].sum().to_dict()
    # Local copy: the frame passed in belongs to the caller's full run.
    data = data.copy()
    data['Final_HQ_Qty'] = data['SKU'].map(
        lambda x: hq_final_map.get(x, 0))
    data['Vendor_Units'] = (
        data['Total_Units_Needed'] - data['Final_HQ_Qty']).clip(lower=0)
    data['Vendor_Cases'] = np.ceil(
        data['Vendor_Units'] / data['Order In Quantities']
    )
    data['Order_Units'] = data['Vendor_Cases'] * data['Order In Quantities']

    if not ed_hq.empty:
        st.metric("Total Transfer Units",
                  f"{int(ed_hq['Transfer_Qty'].sum())}")
        buf_hq = io.BytesIO()
        with pd.ExcelWriter(buf_hq, engine='xlsxwriter') as writer:
            workbook = writer.book
            worksheet = workbook.add_worksheet('HQ_Transfer')
            writer.sheets['HQ_Transfer'] = worksheet

            store_header_fmt = workbook.add_format({
                'bold': True,
                'font_size': 14,
                'align': 'left',
                'valign': 'vcenter',
            })
            col_header_fmt = workbook.add_format({
                'bold': True,
                'bg_color': '#D9E1F2',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
            })
            cell_fmt = workbook.add_format({
                'border': 1,
                'valign': 'vcenter',
            })
            text_fmt = workbook.add_format({
                'num_format': '@',
                'border': 1,
                'valign': 'vcenter',
            })

            store_display_name = inv_store_map.get(
                short_name, short_name).replace('Current Quantity ', '')
            worksheet.write(
                0, 0, f"HQ Transfer — {store_display_name}", store_header_fmt)
            worksheet.set_row(0, 22)

            for col_idx, col_name in enumerate(ed_hq.columns):
                worksheet.write(
                    1, col_idx, col_name, col_header_fmt)

            gtin_col_idx = list(ed_hq.columns).index(
                'GTIN') if 'GTIN' in ed_hq.columns else None
            for row_idx, row in enumerate(ed_hq.itertuples(index=False), start=2):
                for col_idx, value in enumerate(row):
                    fmt = text_fmt if col_idx == gtin_col_idx else cell_fmt
                    if pd.isna(value):
                        worksheet.write_blank(
                            row_idx, col_idx, None, fmt)
                    else:
                        worksheet.write(
                            row_idx, col_idx, value, fmt)

            worksheet.set_column('A:A', 12)
            worksheet.set_column('B:B', 20)
            worksheet.set_column('C:C', 40)
            worksheet.set_column('D:F', 14)

        st.download_button(f"📥 Download HQ Transfer", buf_hq.getvalue(),
                           file_name=f"{short_name}_{date_str}_HQ_MinMax_Order.xlsx",
                           key=f"dl_hq_{short_name}")

    st.divider()

    # 5. Vendor Order UI
    # Cost and units are always derived from WHOLE CASES (cases x case pack),
    # because that is what is actually ordered. They are recomputed from the
    # edited "Order (Cases)" column, so changing cases updates cost/units.
    lines = vendor_order_frame(data)
    order_summary = lines[[
        'SKU', 'GTIN', 'Item Name', 'Cases', 'Case Pack', 'Unit Cost'
    ]].rename(columns={'Cases': 'Order (Cases)'})

    edited_frames = []

    if not order_summary.empty:
        frozen_mask = order_summary['Item Name'].str.startswith(
            'FRZN', na=False)

        for label, file_label, df_type in [
            ("📦 Dry Order", "Dry",
             order_summary[~frozen_mask].reset_index(drop=True)),
            ("❄️ Frozen Order", "Frozen",
             order_summary[frozen_mask].reset_index(drop=True))
        ]:
            st.markdown(f"#### {label}")
            if not df_type.empty:
                ed_df = st.data_editor(
                    df_type, width="stretch",
                    hide_index=True, num_rows="dynamic",
                    # Only the case count is meant to be edited; the rest
                    # are reference columns (delete a row to drop an item).
                    disabled=['SKU', 'GTIN', 'Item Name',
                              'Case Pack', 'Unit Cost'],
                    key=f"vend_{label}_{short_name}")

                ed_df = ed_df[ed_df['SKU'].notna()].copy()
                ed_df['Order (Cases)'] = _num(
                    ed_df['Order (Cases)']).clip(lower=0).round()
                ed_df['Case Pack'] = _num(ed_df['Case Pack'], 1).clip(lower=1)
                ed_df['Unit Cost'] = _num(ed_df['Unit Cost'])
                ed_df = ed_df[ed_df['Order (Cases)'] > 0]
                if ed_df.empty:
                    st.write("No items in this category.")
                    continue

                ed_df['Total Units'] = ed_df['Order (Cases)'] * \
                    ed_df['Case Pack']
                cost = (ed_df['Total Units'] * ed_df['Unit Cost']).sum()
                c1, c2 = st.columns(2)
                c1.metric(f"{label} Units", f"{int(ed_df['Total Units'].sum())}")
                c2.metric(f"{label} Cost", f"${cost:,.2f}")

                edited_frames.append(pd.DataFrame({
                    'SKU': ed_df['SKU'],
                    'GTIN': ed_df['GTIN'],
                    'Item Name': ed_df['Item Name'],
                    'Case Pack': ed_df['Case Pack'],
                    'Cases': ed_df['Order (Cases)'],
                    'Unit Cost': ed_df['Unit Cost'],
                    'Order Units': ed_df['Total Units'],
                }))

                export_df = ed_df[[
                    'GTIN', 'Item Name', 'Order (Cases)', 'Case Pack']].copy()
                export_df['Order (Cases)'] = export_df.apply(
                    lambda r: f"{int(r['Order (Cases)'])} case" +
                    ('s' if int(r['Order (Cases)']) != 1 else '')
                    if r['Case Pack'] > 1 else str(int(r['Order (Cases)'])),
                    axis=1
                )
                export_df = export_df.drop(columns=['Case Pack'])
                export_df = export_df.rename(
                    columns={'Order (Cases)': 'Order'})
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
                                   file_name=f"{short_name}_{date_str}_{file_label}.xlsx",
                                   key=f"dl_{label}_{short_name}")
            else:
                st.write("No items in this category.")
    else:
        st.success(
            "No vendor order needed (Items may be covered by HQ).")

    _record_vendor_edits(short_name, edited_frames)
