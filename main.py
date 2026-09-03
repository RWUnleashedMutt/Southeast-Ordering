import streamlit as st
from datetime import datetime

from catalog import load_catalog
from google_sheets import load_rules_from_sheets
from ordering import compute_store_order, get_allocation_candidates
from ui_sidebar import render_sidebar
from ui_allocation import render_allocation_section
from ui_store_tab import render_store_tab
from ui_summary import render_consolidated_summary
from config import inv_store_map


# --- SESSION STATE INITIALIZATION ---
def init_session_defaults():
    """Initialize all session state defaults upfront."""
    defaults = {
        "rules_vendor": None,
        "rules_matrix": None,
        "hq_allocations": {},
        "current_tab": 0,
        "allocations_submitted": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


# --- APP ---
st.set_page_config(page_title="Inventory & Ordering System", layout="wide")

init_session_defaults()

st.title("📦 Southeast Inventory & Ordering")

catalog_file, selected_vendor, load_rules_btn, selected_stores, hq_threshold = render_sidebar()

# --- LOAD RULES FROM SHEETS ---
rules_matrix = None

if selected_vendor == "-- Select a Vendor --":
    st.sidebar.info("Please select a vendor to load rules.")
elif load_rules_btn:
    load_rules_from_sheets.clear()
    with st.spinner(f"Loading rules matrix for **{selected_vendor}** from Google Sheets..."):
        try:
            rules_matrix = load_rules_from_sheets(selected_vendor)
            st.session_state["rules_matrix"] = rules_matrix
            st.session_state["rules_vendor"] = selected_vendor
            st.sidebar.success(f"✅ Rules loaded: {len(rules_matrix)} SKUs")
        except Exception as e:
            st.sidebar.error(f"❌ Failed to load rules: {e}")
elif st.session_state.get("rules_matrix") is not None and st.session_state.get("rules_vendor") == selected_vendor:
    rules_matrix = st.session_state["rules_matrix"]
    st.sidebar.success(f"✅ Rules loaded: {len(rules_matrix)} SKUs")

# --- MAIN APP ---
if catalog_file and rules_matrix is not None and selected_stores:
    df_master = load_catalog(catalog_file)

    catalog_skus = set(df_master['SKU'].unique())
    rules_matrix = rules_matrix[rules_matrix['SKU'].isin(catalog_skus)].copy()

    invalid_oiq = rules_matrix[rules_matrix['Order In Quantities'] <= 0]
    if not invalid_oiq.empty:
        st.error(
            f"❌ Invalid Order In Quantities found (must be > 0):\n{invalid_oiq[['SKU', 'Order In Quantities']].to_string()}")
        st.stop()

    hq_col = 'Current Quantity HQ'
    date_str = datetime.now().strftime("%Y-%m-%d")

    if hq_col not in df_master.columns:
        st.error(f"❌ Missing column: '{hq_col}'")
        st.stop()

    matched = len(rules_matrix['SKU'].unique())
    total = len(catalog_skus)

    rules_skus = set(rules_matrix['SKU'].unique())
    unmatched_skus = catalog_skus - rules_skus
    unmatched_list = sorted(list(unmatched_skus))

    st.caption(f"✅ Matched {matched} of {total} catalog SKUs to rules.")

    if unmatched_skus:
        # Server-console diagnostics only — never let an encoding quirk in
        # Item Name text (or the terminal's own encoding) crash the app.
        try:
            print(f"\nWARNING: {len(unmatched_skus)} Unmatched SKUs found:")
            for sku in unmatched_list:
                item_name = df_master[df_master['SKU'] == sku]['Item Name'].iloc[0] if len(
                    df_master[df_master['SKU'] == sku]) > 0 else "Unknown"
                print(f"  - {sku}: {item_name}")
            print(f"\nTotal unmatched: {len(unmatched_skus)}\n")
        except UnicodeEncodeError:
            print(f"\nWARNING: {len(unmatched_skus)} unmatched SKUs found (names omitted — non-ASCII console).")

    allocation_candidates = get_allocation_candidates(
        df_master, rules_matrix, hq_col, selected_stores, hq_threshold
    )

    render_allocation_section(df_master, allocation_candidates, selected_stores)

    tabs = st.tabs(selected_stores)

    for i, short_name in enumerate(selected_stores):
        long_name = inv_store_map[short_name]
        with tabs[i]:
            if long_name in df_master.columns:
                data = compute_store_order(
                    short_name, df_master, rules_matrix, hq_col,
                    hq_threshold, allocation_candidates,
                    st.session_state.get("hq_allocations", {})
                )

                render_store_tab(short_name, long_name, data,
                                 selected_vendor, date_str, hq_threshold)

            else:
                st.error(f"Missing column '{long_name}' in Catalog.")

    render_consolidated_summary(
        df_master, rules_matrix, hq_col, hq_threshold, selected_stores,
        allocation_candidates, st.session_state.get("hq_allocations", {}),
        date_str, selected_vendor
    )

elif not selected_stores:
    st.warning(
        "Please select at least one store in the sidebar to begin processing.")
elif not catalog_file:
    st.info("👋 **Welcome! Please upload the Southeast Catalog to begin.**")
    col_inst, col_img = st.columns([1, 1])
    with col_inst:
        st.subheader("📋 Step-by-Step Export Instructions")
        st.markdown("""
        1. **Login to Square Dashboard.**
        2. **Go to Items → Item Library.**
        3. **Filter by Vendor: Southeast Pet.**
        4. **Click Actions → Export Library.**
        5. **Select "Export items matching applied filters".**
        6. **Upload the file here.**
        """)
    with col_img:
        st.subheader("📸 Reference Settings")
        try:
            st.image("./assets/Export Example.png",
                     use_container_width=True, caption="Select the 'Filtered' option.")
        except:
            st.warning("Reference image not found.")
elif rules_matrix is None:
    st.warning(
        "⚠️ Please select a vendor and click 'Load Rules from Google Sheets' to continue.")
