import streamlit as st
import pandas as pd


def render_allocation_section(df_master, allocation_candidates, selected_stores):
    """Renders the whole HQ Allocation UI: the conflicts table, the
    per-SKU allocation inputs, the Push Allocations button, and (once
    pushed) the allocation summary. No-op if there are no conflicts."""
    if not allocation_candidates:
        return

    st.divider()
    st.subheader("⚙️ HQ Allocation (Insufficient Stock)")
    st.caption(
        "Items below have more demand than HQ can supply. Allocate HQ qty to stores; unallocated stores will order from vendors.")

    allocation_data = []
    for sku in sorted(allocation_candidates.keys()):
        info = allocation_candidates[sku]
        item_name = df_master[df_master['SKU'] == sku]['Item Name'].iloc[0] if len(
            df_master[df_master['SKU'] == sku]) > 0 else "Unknown"
        hq_available = int(info['hq_qty'])
        total_demand = sum(d['demand']
                           for d in info['demand_map'].values())
        shortage = total_demand - hq_available
        allocation_data.append({
            'SKU': sku,
            'Item Name': item_name,
            'HQ Available': hq_available,
            'Total Demand': int(total_demand),
            'Shortage': int(shortage),
            'Stores Needing': ', '.join(info['stores'])
        })

    alloc_df = pd.DataFrame(allocation_data)
    st.dataframe(alloc_df, width='stretch', hide_index=True)

    if "hq_allocations" not in st.session_state:
        st.session_state.hq_allocations = {}

    for sku in allocation_candidates:
        if sku not in st.session_state.hq_allocations:
            st.session_state.hq_allocations[sku] = {}

    st.write("**Allocate HQ Qty by Store:**")
    st.info(
        "👆 \"Remaining\" updates live as you type. Once everything looks "
        "right, click **Push Allocations** to apply it to the store tabs below.")

    render_allocation_inputs(df_master, allocation_candidates, selected_stores)

    if st.session_state.get("allocations_submitted"):
        _render_allocation_summary(allocation_candidates, selected_stores)


@st.fragment
def render_sku_allocation(sku, info, selected_stores, df_master):
    """
    Renders the allocation inputs for ONE SKU. Wrapped in its own
    @st.fragment so editing a number_input for this SKU only
    reruns this SKU's block — not every other SKU's inputs in
    the allocation list. Called from render_allocation_inputs().
    """
    item_name = df_master[df_master['SKU'] == sku]['Item Name'].iloc[0] if len(
        df_master[df_master['SKU'] == sku]) > 0 else "Unknown"
    hq_available = int(info['hq_qty'])
    oiq = int(info['oiq'])
    demand_map = info.get('demand_map', {})

    st.markdown(f"**{sku}** — {item_name} (Case Pack: {oiq})")

    relevant_stores = [
        s for s in selected_stores if s in info['stores']]
    cards_per_row = 4

    total_allocated = 0
    for row_start in range(0, len(relevant_stores), cards_per_row):
        row_stores = relevant_stores[row_start:row_start + cards_per_row]
        row_cols = st.columns(cards_per_row)
        for col, store_code in zip(row_cols, row_stores):
            with col:
                if store_code not in st.session_state.hq_allocations[sku]:
                    st.session_state.hq_allocations[sku][store_code] = 0

                store_demand_info = demand_map.get(store_code, {})
                current_inv = int(
                    store_demand_info.get('current_inv', 0))
                demand = int(store_demand_info.get('demand', 0))

                max_alloc = max(
                    min(int(hq_available), demand), 0)

                if st.session_state.hq_allocations[sku][store_code] > max_alloc:
                    st.session_state.hq_allocations[sku][store_code] = max_alloc

                allocated = st.number_input(
                    f"{store_code}", 0, max_alloc,
                    value=st.session_state.hq_allocations[sku][store_code],
                    step=oiq,
                    key=f"alloc_{sku}_{store_code}",
                    width="stretch"
                )
                st.session_state.hq_allocations[sku][store_code] = allocated
                total_allocated += allocated

                st.markdown(
                    f"<div style='font-size:14px; width:100%; "
                    f"margin-top:-6px;'>Has: <b>{current_inv}</b>"
                    f" &nbsp;|&nbsp; Needs: <b>{demand}</b></div>",
                    unsafe_allow_html=True
                )

        if row_start + cards_per_row < len(relevant_stores):
            st.markdown(
                "<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

    remaining = hq_available - total_allocated
    rem_col = st.columns([3, 1])[1]
    with rem_col:
        st.metric(
            "Remaining",
            remaining,
            delta=f"of {hq_available}",
            delta_color="inverse" if remaining >= 0 else "off"
        )

    if remaining < 0:
        st.error(
            f"⚠️ Over-allocated by {abs(remaining)} units for SKU {sku}")

    st.divider()


@st.fragment
def render_allocation_inputs(df_master, allocation_candidates, selected_stores):
    for sku in sorted(allocation_candidates.keys()):
        info = allocation_candidates[sku]
        render_sku_allocation(sku, info, selected_stores, df_master)

    # NOTE: this scan (and the button below) only re-executes when
    # THIS outer fragment reruns. Since the number_inputs now live
    # in nested per-SKU fragments, editing one won't rerun this
    # outer fragment — so we can't proactively keep a `disabled=`
    # flag in sync with live edits. Instead we validate fresh from
    # session_state at the moment the button itself is clicked
    # (a click on a widget in THIS fragment does rerun it), and
    # show the error only on an invalid click rather than trying
    # to track it continuously.
    pushed = st.button("🚀 Push Allocations", width="stretch")
    if pushed:
        over_allocated_skus = []
        for sku in sorted(allocation_candidates.keys()):
            info = allocation_candidates[sku]
            hq_available = int(info['hq_qty'])
            total_allocated = sum(
                st.session_state.hq_allocations.get(
                    sku, {}).get(store_code, 0)
                for store_code in selected_stores
                if store_code in info['stores']
            )
            if total_allocated > hq_available:
                over_allocated_skus.append(sku)

        if over_allocated_skus:
            st.error(
                f"❌ Cannot push — {len(over_allocated_skus)} SKU(s) are over-allocated: "
                f"{', '.join(over_allocated_skus)}. Reduce quantities before pushing."
            )
        else:
            st.session_state.allocations_submitted = True
            st.rerun()


def _render_allocation_summary(allocation_candidates, selected_stores):
    st.divider()
    st.subheader("📋 Allocation Summary")

    summary_rows = []
    any_unassigned = False

    for sku in sorted(allocation_candidates.keys()):
        info = allocation_candidates[sku]
        hq_available = int(info['hq_qty'])
        allocated_by_store = {
            store_code: st.session_state.hq_allocations.get(
                sku, {}).get(store_code, 0)
            for store_code in selected_stores
            if store_code in info['stores']
        }
        total_allocated = sum(allocated_by_store.values())
        unassigned = hq_available - total_allocated

        skipped_stores = [
            s for s in info['stores']
            if allocated_by_store.get(s, 0) == 0
        ]

        if unassigned > 0:
            any_unassigned = True

        summary_rows.append({
            'SKU': sku,
            'HQ Available': hq_available,
            'Total Allocated': total_allocated,
            'Unassigned': unassigned,
            'Stores Getting 0 (→ Full Vendor Order)': ', '.join(skipped_stores) if skipped_stores else '—'
        })

    summary_df = pd.DataFrame(summary_rows)
    st.dataframe(summary_df, width='stretch', hide_index=True)

    if any_unassigned:
        st.warning(
            "⚠️ Some HQ stock above is unassigned. Stores listed in the last column "
            "received no allocation and will order their full need from the vendor instead, "
            "even though HQ has stock available. If this isn't intentional, scroll up and "
            "allocate before generating downloads."
        )
    else:
        st.success(
            "✅ All available HQ stock has been assigned across stores.")
