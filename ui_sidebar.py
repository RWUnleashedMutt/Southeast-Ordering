import streamlit as st

from config import SHEET_IDS, store_map, priority_stores


def render_sidebar():
    """Renders the sidebar inputs and returns the values the rest of the
    app needs: (catalog_file, selected_vendor, load_rules_btn,
    selected_stores, hq_threshold)."""
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

        if selected_vendor != st.session_state.get("rules_vendor") and selected_vendor != "-- Select a Vendor --":
            st.session_state.rules_matrix = None
            st.session_state.rules_vendor = None
            st.session_state.hq_allocations = {}
            st.session_state.allocations_submitted = False

        load_rules_btn = st.button("📥 Load Rules from Google Sheets")

        st.divider()
        st.header("3. Store Selection")
        selected_stores = st.multiselect(
            "Select stores:", options=list(store_map.values()), default=priority_stores
        )

        st.divider()
        st.header("4. HQ Threshold")
        hq_threshold = st.slider(
            "Suggest HQ Transfer if HQ Qty >", 0, 20, 6,
            help="Items with HQ stock exceeding this amount will be suggested for HQ transfer."
        )

    return catalog_file, selected_vendor, load_rules_btn, selected_stores, hq_threshold
