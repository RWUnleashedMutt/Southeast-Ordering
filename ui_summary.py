import io
import streamlit as st
import pandas as pd

from config import inv_store_map
from ordering import compute_store_order


def render_consolidated_summary(df_master, rules_matrix, hq_col, hq_threshold, selected_stores,
                                allocation_candidates, hq_allocations, date_str, selected_vendor):
    st.divider()
    st.subheader("📊 Consolidated Order Summary")
    st.caption("Total items being ordered across all stores (vendor + HQ)")

    all_orders = []

    for short_name in selected_stores:
        long_name = inv_store_map[short_name]
        if long_name not in df_master.columns:
            continue

        data = compute_store_order(
            short_name, df_master, rules_matrix, hq_col,
            hq_threshold, allocation_candidates, hq_allocations
        )

        order_items = data[data['Total_Units_Needed'] > 0][[
            'SKU', 'GTIN', 'Item Name', 'Order In Quantities',
            'Vendor_Cases', 'Suggested_HQ_Qty', 'Default Unit Cost'
        ]].copy()
        order_items['Store'] = short_name
        order_items['Vendor_Units'] = order_items['Vendor_Cases'] * \
            order_items['Order In Quantities']
        order_items['HQ_Units'] = order_items['Suggested_HQ_Qty']

        all_orders.append(order_items)

    if not all_orders:
        return

    combined_orders = pd.concat(all_orders, ignore_index=True)

    summary = combined_orders.groupby('SKU').agg({
        'GTIN': 'first',
        'Item Name': 'first',
        'Order In Quantities': 'first',
        'Vendor_Units': 'sum',
        'HQ_Units': 'sum',
        'Default Unit Cost': 'first'
    }).reset_index()

    summary = summary[summary['Vendor_Units'] > 0].copy()

    summary['Total_Units'] = summary['Vendor_Units']
    summary['Total_Cost'] = summary['Total_Units'] * \
        summary['Default Unit Cost']

    display_summary = summary[[
        'SKU', 'GTIN', 'Item Name', 'Order In Quantities', 'Total_Units', 'Default Unit Cost', 'Total_Cost'
    ]].copy().rename(columns={
        'Order In Quantities': 'Case Pack',
        'Default Unit Cost': 'Unit Cost',
        'Total_Units': 'Qty to Order',
        'Total_Cost': 'Total $'
    })

    st.dataframe(display_summary,
                 use_container_width=True, hide_index=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Items", len(summary))
    with col2:
        st.metric("Total Units Ordered", int(summary['Total_Units'].sum()))
    with col3:
        st.metric("Total Order Value",
                  f"${summary['Total_Cost'].sum():,.2f}")

    st.divider()
    export_summary = summary[[
        'GTIN', 'Item Name', 'Order In Quantities', 'Vendor_Units'
    ]].copy().rename(columns={
        'Order In Quantities': 'Case Pack',
        'Vendor_Units': 'Order Qty'
    })

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        export_summary.to_excel(
            writer, index=False, sheet_name='Consolidated_Order')
        text_fmt = writer.book.add_format({'num_format': '@'})
        writer.sheets['Consolidated_Order'].set_column('A:A', 20, text_fmt)
        writer.sheets['Consolidated_Order'].set_column('B:B', 40)

    st.download_button(
        "📥 Download Consolidated Order Summary",
        buf.getvalue(),
        file_name=f"{date_str}_{selected_vendor}_CONSOLIDATED_ORDER.xlsx",
        key="dl_consolidated"
    )
