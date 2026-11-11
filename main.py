import time

import streamlit as st
import pandas as pd
from datetime import datetime

from catalog import load_catalog
from google_sheets import load_rules_from_sheets, load_reserved_stock
from ordering import (compute_store_needs, apply_hq_suggestions,
                      get_allocation_candidates, missing_rule_columns)
from ui_sidebar import render_sidebar
from ui_allocation import render_allocation_section, reset_allocations
from ui_store_tab import render_store_tab
from ui_summary import render_consolidated_summary
from config import inv_store_map


# --- SESSION STATE INITIALIZATION ---
def init_session_defaults():
    """Initialize all session state defaults upfront."""
    defaults = {
        "rules_vendors": None,
        "rules_matrix": None,
        "rules_dupe_skus": None,
        "hq_allocations": {},
        "applied_allocations": {},
        "alloc_signature": None,
        "store_vendor_edits": {},
        "current_tab": 0,
        "allocations_submitted": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _today_str():
    """Date for export filenames, in the stores' time zone (the server may
    run in UTC)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def _vendor_label(vendors):
    """Short vendor label for filenames ("Select All" would otherwise join
    ~60 names into a filename that is too long to save)."""
    return "+".join(vendors) if len(vendors) <= 3 else f"{len(vendors)}_vendors"


# --- APP ---
st.set_page_config(page_title="Inventory & Ordering System", layout="wide")

init_session_defaults()

st.title("📦 Southeast Inventory & Ordering")

catalog_file, selected_vendors, load_rules_btn, selected_stores, hq_threshold = render_sidebar()

# --- LOAD RULES FROM SHEETS ---
rules_matrix = None
vendor_label = _vendor_label(selected_vendors)

if not selected_vendors:
    st.sidebar.info("Please select at least one vendor to load rules.")
elif load_rules_btn:
    vendor_frames = []
    # The reserved-for-events sheet is cached too; refresh it with the rules
    # so a reservation added this morning is not missed for up to an hour.
    load_reserved_stock.clear()
    with st.spinner(f"Loading rules matrices for {len(selected_vendors)} vendor(s) from Google Sheets..."):
        for i, vendor in enumerate(selected_vendors):
            # Bust only this vendor's cache entry (not every vendor's) so
            # re-clicking Load doesn't re-fetch already-cached vendors —
            # that blanket-clearing was compounding the Sheets API quota
            # errors when many vendors were selected at once.
            load_rules_from_sheets.clear(vendor)
            try:
                vendor_df = load_rules_from_sheets(vendor).copy()
                vendor_df['__vendor__'] = vendor
                vendor_frames.append(vendor_df)
                st.sidebar.success(f"✅ {vendor}: {len(vendor_df)} SKUs")
            except Exception as e:
                st.sidebar.error(f"❌ Failed to load rules for {vendor}: {e}")

            # Pace requests so a large multi-vendor (or "Select All") load
            # doesn't burst past Google's per-minute read quota. Each vendor
            # now costs a single Sheets API read; ~1.5s/vendor keeps
            # sustained throughput well under the ~60 reads/min cap, with
            # headroom for other concurrent app usage sharing the same quota.
            if i < len(selected_vendors) - 1:
                time.sleep(1.5)

    if vendor_frames:
        combined = pd.concat(vendor_frames, ignore_index=True)
        dupe_mask = combined['SKU'].duplicated(keep=False)
        dupe_skus = None
        if dupe_mask.any():
            dupe_cols = [c for c in ['SKU', 'Item Name'] if c in combined.columns]
            dupe_skus = combined.loc[dupe_mask, dupe_cols + ['__vendor__']].groupby(
                dupe_cols, as_index=False
            )['__vendor__'].agg(lambda v: ', '.join(v)).rename(
                columns={'__vendor__': 'Vendors (first wins)'}
            )
            st.sidebar.warning(
                f"⚠️ {len(dupe_skus)} SKU(s) appear under more than one selected "
                f"vendor — keeping the first-selected vendor's rules for those."
            )
        rules_matrix = combined.drop(
            columns='__vendor__').drop_duplicates(subset='SKU', keep='first')
        st.session_state["rules_matrix"] = rules_matrix
        st.session_state["rules_vendors"] = selected_vendors
        st.session_state["rules_dupe_skus"] = dupe_skus
elif st.session_state.get("rules_matrix") is not None and st.session_state.get("rules_vendors") == selected_vendors:
    rules_matrix = st.session_state["rules_matrix"]
    st.sidebar.success(
        f"✅ Rules loaded: {len(rules_matrix)} SKUs across {len(selected_vendors)} vendor(s)")

dupe_skus = st.session_state.get("rules_dupe_skus")
if dupe_skus is not None and not dupe_skus.empty:
    with st.expander(f"⚠️ {len(dupe_skus)} SKU(s) duplicated across selected vendors", expanded=False):
        st.dataframe(dupe_skus, hide_index=True, width="stretch")

# --- MAIN APP ---
if catalog_file and rules_matrix is not None and selected_stores:
    df_master = load_catalog(catalog_file)

    # Allocations belong to one specific catalog / threshold / store set. If
    # any of them changes, the old allocations no longer describe reality.
    catalog_id = getattr(catalog_file, "file_id", None) or (
        catalog_file.name, catalog_file.size)
    alloc_signature = (catalog_id, hq_threshold, tuple(selected_stores))
    if st.session_state.get("alloc_signature") != alloc_signature:
        if st.session_state.get("alloc_signature") is not None:
            reset_allocations()
        st.session_state["alloc_signature"] = alloc_signature

    catalog_skus = set(df_master['SKU'].unique())
    rules_matrix = rules_matrix[rules_matrix['SKU'].isin(catalog_skus)].copy()

    invalid_oiq = rules_matrix[rules_matrix['Order In Quantities'] <= 0]
    if not invalid_oiq.empty:
        st.error(
            f"❌ Invalid Order In Quantities found (must be > 0):\n{invalid_oiq[['SKU', 'Order In Quantities']].to_string()}")
        st.stop()

    hq_col = 'Current Quantity HQ'
    date_str = _today_str()

    if hq_col not in df_master.columns:
        st.error(f"❌ Missing column: '{hq_col}'")
        st.stop()

    try:
        reserved_map = load_reserved_stock()
    except Exception as e:
        st.error(
            f"❌ Could not load the reserved-stock sheet: {e}\n\n"
            f"Without it, stock reserved for other events is NOT excluded, so "
            f"HQ transfers may over-commit HQ inventory.")
        if not st.checkbox(
                "Continue anyway without reserved-stock data",
                key="allow_no_reserved"):
            st.stop()
        reserved_map = {}

    df_master['Reserved_Qty'] = df_master['SKU'].map(
        reserved_map).fillna(0)

    available_hq_col = 'Available Quantity HQ'
    df_master[available_hq_col] = (
        df_master[hq_col] - df_master['Reserved_Qty']).clip(lower=0)

    matched = len(rules_matrix['SKU'].unique())
    total = len(catalog_skus)

    rules_skus = set(rules_matrix['SKU'].unique())
    unmatched_skus = catalog_skus - rules_skus
    unmatched_list = sorted(list(unmatched_skus))

    st.caption(f"✅ Matched {matched} of {total} catalog SKUs to rules.")

    if 'Stock Source SKU' in df_master.columns:
        n_stock_by = int((df_master['Stock Source SKU'] != '').sum())
        if n_stock_by:
            st.caption(
                f"ℹ️ {n_stock_by} pack variations (e.g. 8PK) are stocked by a "
                f"base item, so they use that item's quantities and unit cost.")

    if unmatched_skus:
        # Server-console diagnostics only — never let an encoding quirk in
        # Item Name text (or the terminal's own encoding) crash the app.
        try:
            name_by_sku = dict(zip(df_master['SKU'], df_master['Item Name']))
            print(f"\nWARNING: {len(unmatched_skus)} Unmatched SKUs found:")
            for sku in unmatched_list:
                print(f"  - {sku}: {name_by_sku.get(sku, 'Unknown')}")
            print(f"\nTotal unmatched: {len(unmatched_skus)}\n")
        except UnicodeEncodeError:
            print(f"\nWARNING: {len(unmatched_skus)} unmatched SKUs found (names omitted — non-ASCII console).")

    # A store whose columns are missing from the rules sheet would silently
    # never order; say so instead.
    missing_cols = missing_rule_columns(rules_matrix, selected_stores)
    for store_code, cols in missing_cols.items():
        st.warning(
            f"⚠️ {store_code}: the rules matrix has no {', '.join(cols)} "
            f"column(s), so no items will be ordered for this store.")

    # Each store's needs are computed once per run, then reused for the
    # allocation scan and for the per-store tabs.
    base_data = {
        store_code: compute_store_needs(
            store_code, df_master, rules_matrix, available_hq_col)
        for store_code in selected_stores
        if inv_store_map[store_code] in df_master.columns
    }

    allocation_candidates = get_allocation_candidates(
        df_master, rules_matrix, available_hq_col, selected_stores,
        hq_threshold, base_data=base_data
    )

    render_allocation_section(df_master, allocation_candidates, selected_stores)

    tabs = st.tabs(selected_stores)

    # Only allocations the user has pushed are applied to the store tabs.
    applied_allocations = (
        st.session_state.get("applied_allocations", {})
        if st.session_state.get("allocations_submitted") else {})

    # Kept for the consolidated summary below.
    store_data = {}

    for i, short_name in enumerate(selected_stores):
        long_name = inv_store_map[short_name]
        with tabs[i]:
            if long_name in df_master.columns:
                data = apply_hq_suggestions(
                    base_data[short_name], short_name, hq_threshold,
                    allocation_candidates, applied_allocations
                )
                store_data[short_name] = data

                render_store_tab(short_name, data, date_str, hq_threshold)

            else:
                st.error(f"Missing column '{long_name}' in Catalog.")

    render_consolidated_summary(store_data, date_str, vendor_label)

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
                     width="stretch", caption="Select the 'Filtered' option.")
        except Exception:
            st.warning("Reference image not found.")
elif rules_matrix is None:
    st.warning(
        "⚠️ Please select vendor(s) and click 'Load Rules from Google Sheets' to continue.")
