import io
import streamlit as st
import pandas as pd

from ordering import vendor_order_frame, consolidate_vendor_orders
from ui_store_tab import STORE_EDITS_KEY


@st.fragment
def render_consolidated_summary(store_data, date_str, vendor_label):
    """`store_data` is {short_name: compute_store_order(...) result}, computed
    once per store by the caller.

    The summary is built from each store tab's *edited* vendor-order lines
    (kept in session state by render_store_tab), falling back to the computed
    suggestion for any store that has no recorded edits. Because store tabs
    are fragments, edits made in them don't rerun this section by themselves;
    the Refresh button reruns just this fragment to pick up the latest edits.
    """
    st.divider()
    st.subheader("📊 Consolidated Order Summary")
    st.caption(
        "Total items being ordered across all selected stores, matching the "
        "per-store Dry/Frozen tables including your edits. After editing a "
        "store tab, click Refresh to update this summary.")
    st.button("🔄 Refresh summary", key="refresh_consolidated")

    edits = st.session_state.get(STORE_EDITS_KEY, {})
    frames = [
        edits[short_name] if short_name in edits else vendor_order_frame(data)
        for short_name, data in store_data.items()
    ]
    summary = consolidate_vendor_orders(frames)

    if summary.empty:
        st.info("Nothing to order from the vendor across the selected stores.")
        return

    display_summary = summary[[
        'SKU', 'GTIN', 'Item Name', 'Case Pack', 'Order Units',
        'Unit Cost', 'Total Cost'
    ]].rename(columns={
        'Order Units': 'Qty to Order',
        'Total Cost': 'Total $'
    })

    st.dataframe(display_summary, width="stretch", hide_index=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Items", len(summary))
    with col2:
        st.metric("Total Units Ordered", int(summary['Order Units'].sum()))
    with col3:
        st.metric("Total Order Value",
                  f"${summary['Total Cost'].sum():,.2f}")

    st.divider()
    export_summary = summary[[
        'GTIN', 'Item Name', 'Case Pack', 'Order Units'
    ]].rename(columns={'Order Units': 'Order Qty'})

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
        file_name=f"{date_str}_{vendor_label}_CONSOLIDATED_ORDER.xlsx",
        key="dl_consolidated"
    )
