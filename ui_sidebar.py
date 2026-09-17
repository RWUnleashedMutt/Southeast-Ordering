import streamlit as st

from config import SHEET_IDS, store_map, priority_stores


def render_sidebar():
    """Renders the sidebar inputs and returns the values the rest of the
    app needs: (catalog_file, selected_vendors, load_rules_btn,
    selected_stores, hq_threshold)."""
    with st.sidebar:
        st.header("1. Upload Files")
        catalog_file = st.file_uploader(
            "Upload Southeast Catalog (.xlsx)", type=['xlsx'])

        st.divider()
        st.header("2. Vendor(s)")
        st.caption(
            "Selecting more than one combines their rules matrices. If a "
            "SKU appears under more than one checked vendor, the vendor "
            "listed first below wins for that SKU."
        )

        def _apply_select_all():
            val = st.session_state.get("vendor_select_all", False)
            for v in SHEET_IDS.keys():
                st.session_state[f"vendor_chk_{v}"] = val

        st.checkbox("Select All Vendors", key="vendor_select_all",
                    on_change=_apply_select_all)

        selected_count = sum(
            1 for v in SHEET_IDS.keys()
            if st.session_state.get(f"vendor_chk_{v}")
        )
        with st.expander(f"Vendors ({selected_count} selected)",
                         expanded=False, key="vendor_expander"):
            selected_vendors = [
                vendor for vendor in SHEET_IDS.keys()
                if st.checkbox(vendor, key=f"vendor_chk_{vendor}")
            ]

        if sorted(selected_vendors) != sorted(st.session_state.get("rules_vendors") or []):
            st.session_state.rules_matrix = None
            st.session_state.rules_vendors = None
            st.session_state.hq_allocations = {}
            st.session_state.allocations_submitted = False

        load_rules_btn = st.button("📥 Load Rules from Google Sheets")

        st.divider()
        st.header("3. Store Selection")

        def _apply_select_all_stores():
            val = st.session_state.get("store_select_all", False)
            for s in store_map.values():
                st.session_state[f"store_chk_{s}"] = val

        st.checkbox("Select All Stores", key="store_select_all",
                    on_change=_apply_select_all_stores)

        selected_stores = [
            store for store in store_map.values()
            if st.checkbox(store, value=(store in priority_stores),
                           key=f"store_chk_{store}")
        ]

        st.divider()
        st.header("4. HQ Threshold")
        hq_threshold = st.slider(
            "Suggest HQ Transfer if HQ Qty >", 0, 20, 6,
            help="Items with HQ stock exceeding this amount will be suggested for HQ transfer."
        )

    return catalog_file, selected_vendors, load_rules_btn, selected_stores, hq_threshold
