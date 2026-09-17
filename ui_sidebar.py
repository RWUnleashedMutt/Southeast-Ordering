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

        # st.expander has no `key` on the Streamlit version this app is
        # pinned to, so its own open/closed state can't persist across the
        # reruns each checkbox click causes. Track it ourselves instead —
        # expanded= is then driven by our own session_state, not the
        # expander's (nonexistent) built-in state.
        st.session_state.setdefault("vendor_list_open", False)
        toggle_label = ("▲ Hide vendor list" if st.session_state["vendor_list_open"]
                        else "▼ Show vendor list")
        if st.button(toggle_label, key="vendor_list_toggle"):
            st.session_state["vendor_list_open"] = not st.session_state["vendor_list_open"]

        with st.expander(f"Vendors ({selected_count} selected)",
                         expanded=st.session_state["vendor_list_open"]):
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

        # Seed each checkbox's initial value once via session_state instead
        # of passing value= on every render — passing both value= and a key
        # that's also written to directly (by the select-all callback above)
        # is what triggers Streamlit's "widget created with a default value
        # but also had its value set via the Session State API" warning.
        for store in store_map.values():
            st.session_state.setdefault(
                f"store_chk_{store}", store in priority_stores)

        selected_stores = [
            store for store in store_map.values()
            if st.checkbox(store, key=f"store_chk_{store}")
        ]

        st.divider()
        st.header("4. HQ Threshold")
        hq_threshold = st.slider(
            "Suggest HQ Transfer if HQ Qty >", 0, 20, 6,
            help="Items with HQ stock exceeding this amount will be suggested for HQ transfer."
        )

    return catalog_file, selected_vendors, load_rules_btn, selected_stores, hq_threshold
