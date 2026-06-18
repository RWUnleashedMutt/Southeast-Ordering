import streamlit as st
import pandas as pd
import io
import numpy as np
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIG ---
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

SHEET_IDS = {
    'All Vendors': '1W-AGqIXwcqL7clDHad43hFmpPrrXzNUDYC4-dVGpngo',
    "Adored Beast": "1HwOxpAzI_HlntVVfOqxBVAWDy7cznPxxhUqOR5cy6ng",
    "Aroma Paws": "1fTvxu-y3rVpvxkt8elR1bZMECReblLE0zmYQDr1ePPg",
    "Bradley Caldwell": "1eqENDXTdDJVKdos-VUXYNYMNM806rNcDrv63Q654nyc",
    "Butchers Block": "1nDtvvDVu9tAzR2iDB4uMpUG3rcN3Fm_v09WJw3jvbJI",
    "Canine Caviar": "1TJXe9V_aF1A1wm_O9XK_iWJNU119iH3ZBBorUlX_0ss",
    "Colorado Pet Treats": "1U4nQGJvgyPWLST96Y6a4yrgJ2jGGicS6p4f7jesL8p8",
    "Fluff & Tuff": "1nGWM9Lt34e3vpqaETjPeMVsCTKVC9kIEQ3VVx1mEUqY",
    "Front Porch Pets": "1CyW8rNNWzmYH9iqVRgN5iTWCiqgd-cJnrAJGktGS2a0",
    "InClover": "1GJX-rqphRYAHM50HKrXhE3qG3ZUeB9kP0njwcuM56co",
    "Kennel Master": "1YgbCH_UxFZYAKnyJRki1ReNIdgqyUHtPS8gztUbpJaQ",
    "Polka Dog": "1JUFN_ErS6FXUKD9gv_RzccxJplwpEDiaX3Am4LW0shw",
    "SE": "1O6HWGeLgtdScnJ0_pQc8asaSj3-L4pP9vjCvvXa26vQ",
    # Add a line for each vendor
}

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

inv_store_map = {v: k for k, v in store_map.items()}
priority_stores = ['CC', 'CM', 'CVM', 'LB', 'SH']


# --- HELPERS ---
def clean_id(val):
    if pd.isna(val):
        return ""
    return str(int(val)) if isinstance(val, float) and val.is_integer() else str(val)


@st.cache_data
def load_catalog(file) -> pd.DataFrame:
    # Specify GTIN as string to preserve leading zeros
    dtype_dict = {'GTIN': str, 'SKU': str}
    df = pd.read_excel(file, header=1, dtype=dtype_dict)
    df.columns = df.columns.str.strip()
    df['SKU'] = df['SKU'].apply(clean_id)
    if 'GTIN' in df.columns:
        # Keep GTIN as string and just strip whitespace
        df['GTIN'] = df['GTIN'].astype(str).str.strip()
    return df


@st.cache_resource
def get_google_client():
    """Authenticate using Streamlit secrets — works both locally and on Streamlit Cloud."""
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    return gspread.authorize(creds)


@st.cache_data(ttl=3600)  # Cache for one hour
def load_rules_from_sheets(vendor: str) -> pd.DataFrame:
    """Pull the rules matrix for the given vendor from Google Sheets."""
    if vendor not in SHEET_IDS:
        raise ValueError(f"No Sheet ID configured for vendor '{vendor}'.")
    client = get_google_client()
    spreadsheet = client.open_by_key(SHEET_IDS[vendor])
    worksheet = spreadsheet.sheet1
    data = worksheet.get_all_records(value_render_option='UNFORMATTED_VALUE')
    df = pd.DataFrame(data)
    df.columns = df.columns.str.strip()
    df['SKU'] = df['SKU'].apply(clean_id)

    # Coerce columns to the correct types.
    # _DNO columns are treated separately because Google Sheets can return booleans
    # as native bool, integers (0/1), or text strings ('TRUE'/'FALSE') depending on
    # cell formatting. Running pd.to_numeric on text strings produces NaN, which then
    # causes fillna(0) + astype(bool) downstream to flip every 'FALSE' string to True
    # — silently blocking all items from being ordered. The explicit map below handles
    # all three formats safely.
    for col in df.columns:
        if col == 'SKU':
            continue
        if col.endswith('_DNO'):
            df[col] = df[col].map(
                lambda x: str(x).strip().upper() in ('TRUE', '1', 'YES', '1.0')
                if pd.notna(x) else False
            ).astype(bool)
        else:
            converted = pd.to_numeric(df[col], errors='coerce')
            # Only replace if the conversion didn't turn everything to NaN
            # (i.e. the column was actually numeric to begin with)
            if converted.notna().sum() > 0:
                df[col] = converted

    return df


# --- APP ---
st.set_page_config(page_title="Inventory & Ordering System", layout="wide")
st.title("📦 Southeast Inventory & Ordering")

# --- SIDEBAR ---
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

    st.divider()
    st.header("5. Store Lead Times (Days)")
    store_lead_times = {
        s: st.number_input(
            f"Lead Time: {s}", 0, 30, (1 if s in priority_stores else 7))
        for s in selected_stores
    }

# --- LOAD RULES FROM SHEETS ---
rules_matrix = None

# If the vendor changed, clear the old cached matrix so the user must reload
if "rules_vendor" in st.session_state and st.session_state["rules_vendor"] != selected_vendor:
    st.session_state.pop("rules_matrix", None)
    st.session_state.pop("rules_vendor", None)

if selected_vendor == "-- Select a Vendor --":
    st.sidebar.info("Please select a vendor to load rules.")
elif load_rules_btn:
    load_rules_from_sheets.clear()  # Force fresh pull — bypasses TTL cache
    with st.spinner(f"Loading rules matrix for **{selected_vendor}** from Google Sheets..."):
        try:
            rules_matrix = load_rules_from_sheets(selected_vendor)
            st.session_state["rules_matrix"] = rules_matrix
            st.session_state["rules_vendor"] = selected_vendor
            st.sidebar.success(f"✅ Rules loaded: {len(rules_matrix)} SKUs")
        except Exception as e:
            st.sidebar.error(f"❌ Failed to load rules: {e}")
elif "rules_matrix" in st.session_state and st.session_state.get("rules_vendor") == selected_vendor:
    # Restore already-loaded matrix if vendor hasn't changed
    rules_matrix = st.session_state["rules_matrix"]
    st.sidebar.success(f"✅ Rules loaded: {len(rules_matrix)} SKUs")

# --- MAIN APP ---
if catalog_file and rules_matrix is not None and selected_stores:
    df_master = load_catalog(catalog_file)

    # Filter rules to only SKUs present in the catalog
    catalog_skus = set(df_master['SKU'].unique())
    rules_matrix = rules_matrix[rules_matrix['SKU'].isin(catalog_skus)].copy()

    hq_col = 'Current Quantity HQ'
    date_str = datetime.now().strftime("%Y-%m-%d")

    if hq_col not in df_master.columns:
        st.error(f"❌ Missing column: '{hq_col}'")
        st.stop()

    matched = len(rules_matrix['SKU'].unique())
    total = len(catalog_skus)

    # Find SKUs that didn't match
    rules_skus = set(rules_matrix['SKU'].unique())
    unmatched_skus = catalog_skus - rules_skus
    unmatched_list = sorted(list(unmatched_skus))

    st.caption(f"✅ Matched {matched} of {total} catalog SKUs to rules.")

    # Log unmatched SKUs to console
    if unmatched_skus:
        print(f"\n⚠️  WARNING: {len(unmatched_skus)} Unmatched SKUs found:")
        for sku in unmatched_list:
            item_name = df_master[df_master['SKU'] == sku]['Item Name'].iloc[0] if len(
                df_master[df_master['SKU'] == sku]) > 0 else "Unknown"
            print(f"  - {sku}: {item_name}")
        print(f"\nTotal unmatched: {len(unmatched_skus)}\n")

    # --- PRE-ALLOCATION LOGIC (OPTIMIZED) ---
    # Build allocation candidates with vectorized operations
    @st.cache_data(ttl=3600)
    def get_allocation_candidates(vendor_name, selected_stores_tuple, hq_threshold):
        """Identify items with HQ allocation conflicts (demand > supply)."""
        allocation_candidates = {}

        # Scan each store's needs once
        store_needs_map = {}
        for store_code in selected_stores_tuple:
            long_name = inv_store_map[store_code]
            current_lt = store_lead_times[store_code]

            lookup_cols = ['SKU', 'Order In Quantities',
                           f'{store_code}_DNO', f'{store_code}_Min', f'{store_code}_Max']
            valid_lookup = [
                c for c in lookup_cols if c in rules_matrix.columns]
            store_rules = rules_matrix[valid_lookup].copy().rename(columns={
                f'{store_code}_DNO': 'DNO',
                f'{store_code}_Min': 'Min',
                f'{store_code}_Max': 'Max'
            })

            store_inv = df_master[['SKU', long_name, hq_col]].copy().rename(
                columns={long_name: 'Current_Inv', hq_col: 'HQ_Qty'}
            )

            data = pd.merge(store_inv, store_rules, on='SKU', how='left')
            data = data.fillna({
                'DNO': 0, 'Order In Quantities': 1, 'Min': 0, 'Max': 0, 'Current_Inv': 0, 'HQ_Qty': 0
            })
            data['DNO'] = data['DNO'].astype(bool)

            data['Effective_Min'] = data['Min'] + (current_lt * 0.2)
            data['Needs_Order'] = np.where(
                data['Order In Quantities'] == 1,
                (data['Current_Inv'] < data['Max']),
                (data['Current_Inv'] < data['Effective_Min'])
            )
            data['Needs_Order'] = data['Needs_Order'] & (data['DNO'] == False)
            data['Units_Needed_To_Max'] = np.where(
                data['Needs_Order'],
                np.maximum(data['Max'] - data['Current_Inv'], 0),
                0
            )
            # Round to Order In Quantities (case packs) like per-store logic does
            data['Units_Needed'] = np.ceil(
                data['Units_Needed_To_Max'] / data['Order In Quantities']
            ) * data['Order In Quantities']
            data['Units_Needed'] = data['Units_Needed'].fillna(0)

            store_needs_map[store_code] = data[data['Units_Needed'] > 0][
                ['SKU', 'Units_Needed', 'Current_Inv', 'HQ_Qty']
            ].copy()

        # Consolidate demand across stores (vectorized)
        sku_demand_list = []
        for store_code, needs_df in store_needs_map.items():
            needs_df['Store'] = store_code
            sku_demand_list.append(needs_df)

        if not sku_demand_list:
            return {}

        combined = pd.concat(sku_demand_list, ignore_index=True)

        # Group by SKU to find items with conflicts
        sku_groups = combined.groupby('SKU').agg({
            'Units_Needed': 'sum',
            'HQ_Qty': 'first',
            'Store': 'count'
        }).rename(columns={'Store': 'Store_Count'})

        # Filter: only items where demand > hq_qty AND hq_qty > threshold (actual conflict to resolve)
        conflicts = sku_groups[(sku_groups['Units_Needed'] > sku_groups['HQ_Qty']) & (
            sku_groups['HQ_Qty'] > hq_threshold)]

        # Build allocation candidates with demand map
        for sku in conflicts.index:
            sku_data = combined[combined['SKU'] == sku]
            demand_map = {}
            for _, row in sku_data.iterrows():
                demand_map[row['Store']] = {
                    'demand': int(row['Units_Needed']),
                    'current_inv': int(row['Current_Inv'])
                }

            allocation_candidates[sku] = {
                'stores': list(sku_data['Store'].unique()),
                'hq_qty': int(sku_data['HQ_Qty'].iloc[0]),
                'demand_map': demand_map,
                'oiq': int(sku_data['Order In Quantities'].iloc[0]) if 'Order In Quantities' in sku_data.columns else 1
            }

        return allocation_candidates

    # Call optimized function with hashable inputs
    allocation_candidates = get_allocation_candidates(
        selected_vendor,
        tuple(selected_stores),
        hq_threshold
    )

    # Show pre-allocation UI if there are candidates
    if allocation_candidates:
        st.divider()
        st.subheader("⚙️ HQ Allocation (Insufficient Stock)")
        st.caption(
            "Items below have more demand than HQ can supply. Allocate HQ qty to stores; unallocated stores will order from vendors.")

        # Build allocation UI
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
        st.dataframe(alloc_df, use_container_width=True, hide_index=True)

        # Initialize session state for allocations
        if "hq_allocations" not in st.session_state:
            st.session_state.hq_allocations = {}

        st.write("**Allocate HQ Qty by Store:**")

        # Build allocation inputs and track totals dynamically
        for sku in sorted(allocation_candidates.keys()):
            info = allocation_candidates[sku]
            item_name = df_master[df_master['SKU'] == sku]['Item Name'].iloc[0] if len(
                df_master[df_master['SKU'] == sku]) > 0 else "Unknown"
            hq_available = int(info['hq_qty'])
            oiq = int(info['oiq'])
            demand_map = info.get('demand_map', {})

            st.markdown(f"**{sku}** — {item_name} (Case Pack: {oiq})")

            alloc_cols = st.columns(len(selected_stores) + 1)

            # Calculate total allocated for this SKU
            total_allocated = 0
            for col_idx, store_code in enumerate(selected_stores):
                if store_code in info['stores']:
                    with alloc_cols[col_idx]:
                        key = f"alloc_{sku}_{store_code}"
                        if key not in st.session_state.hq_allocations:
                            st.session_state.hq_allocations[key] = 0

                        # Ensure hq_available is positive before using as max_value
                        max_alloc = max(int(hq_available), 0)

                        allocated = st.number_input(
                            f"{store_code}", 0, max_alloc, 0, step=oiq, key=key
                        )
                        st.session_state.hq_allocations[key] = allocated
                        total_allocated += allocated

                        # Show current inventory and demand in small text
                        store_demand_info = demand_map.get(store_code, {})
                        current_inv = int(
                            store_demand_info.get('current_inv', 0))
                        demand = int(store_demand_info.get('demand', 0))
                        st.caption(f"Has: {current_inv} | Needs: {demand}")

            # Show remaining in last column
            remaining = hq_available - total_allocated
            with alloc_cols[-1]:
                st.metric(
                    "Remaining",
                    remaining,
                    delta=f"of {hq_available}",
                    delta_color="inverse" if remaining >= 0 else "off"
                )

            # Warn if over-allocated
            if remaining < 0:
                st.error(
                    f"⚠️ Over-allocated by {abs(remaining)} units for SKU {sku}")

            st.divider()

        st.info(
            "👆 Manually allocate HQ qty to stores. Unallocated stores will automatically order from vendors.")

    tabs = st.tabs(selected_stores)

    for i, short_name in enumerate(selected_stores):
        long_name = inv_store_map[short_name]
        with tabs[i]:
            if long_name in df_master.columns:
                current_lt = store_lead_times[short_name]

                # 1. Rules & Merge
                lookup_cols = ['SKU', 'Order In Quantities',
                               f'{short_name}_DNO', f'{short_name}_Min', f'{short_name}_Max']
                valid_lookup = [
                    c for c in lookup_cols if c in rules_matrix.columns]
                store_rules = rules_matrix[valid_lookup].copy().rename(columns={
                    f'{short_name}_DNO': 'DNO',
                    f'{short_name}_Min': 'Min',
                    f'{short_name}_Max': 'Max'
                })

                store_inv = df_master[[
                    'SKU', 'GTIN', 'Item Name', 'Default Unit Cost', long_name, hq_col
                ]].copy().rename(columns={long_name: 'Current_Inv', hq_col: 'HQ_Qty'})

                data = pd.merge(store_inv, store_rules, on='SKU', how='left')
                data = data.fillna({
                    'DNO': 0, 'Order In Quantities': 1, 'Min': 0,
                    'Max': 0, 'Current_Inv': 0, 'HQ_Qty': 0, 'Default Unit Cost': 0
                })
                data['DNO'] = data['DNO'].astype(bool)

                # 2. Split Trigger Logic
                data['Effective_Min'] = data['Min'] + (current_lt * 0.2)
                data['Needs_Order'] = np.where(
                    data['Order In Quantities'] == 1,
                    (data['Current_Inv'] < data['Max']),
                    (data['Current_Inv'] < data['Effective_Min'])
                )
                data['Needs_Order'] = data['Needs_Order'] & (
                    data['DNO'] == False)
                data['Units_Needed_To_Max'] = np.where(
                    data['Needs_Order'], data['Max'] - data['Current_Inv'], 0
                )
                data['Total_Units_Needed'] = np.ceil(
                    np.maximum(data['Units_Needed_To_Max'], 0) /
                    data['Order In Quantities']
                ) * data['Order In Quantities']

                # 3. HQ Transfer UI with allocation awareness
                st.subheader(f"🚛 HQ Transfer List: {short_name}")
                st.caption(
                    f"Items with HQ Stock > {hq_threshold} are suggested here (or your allocation above). Delete a row or set Qty to 0 to move it to the Vendor Order.")

                # Apply user allocation if it exists
                data['Allocated_HQ'] = data['SKU'].apply(
                    lambda sku: st.session_state.hq_allocations.get(
                        f"alloc_{sku}_{short_name}", 0)
                    if "hq_allocations" in st.session_state else 0
                )

                # Use allocated amount if specified, otherwise use suggested amount
                data['Suggested_HQ_Qty'] = np.where(
                    (data['Total_Units_Needed'] > 0) & (
                        data['Allocated_HQ'] > 0),
                    data['Allocated_HQ'],
                    np.where(
                        (data['Total_Units_Needed'] > 0) & (
                            data['HQ_Qty'] > hq_threshold),
                        data['Total_Units_Needed'], 0
                    )
                )

                hq_display = data[data['Suggested_HQ_Qty'] > 0][[
                    'SKU', 'GTIN', 'Item Name', 'Suggested_HQ_Qty', 'Current_Inv', 'HQ_Qty'
                ]].copy()
                hq_display.rename(
                    columns={'Suggested_HQ_Qty': 'Transfer_Qty'}, inplace=True)

                ed_hq = st.data_editor(hq_display, use_container_width=True,
                                       hide_index=True, num_rows="dynamic", key=f"hq_ed_{short_name}")

                # Display HQ Transfer Cost
                if not ed_hq.empty:
                    # Merge with original data to get unit cost
                    ed_hq_with_cost = ed_hq.merge(
                        data[['SKU', 'Default Unit Cost']], on='SKU', how='left'
                    )
                    hq_cost = (
                        ed_hq_with_cost['Transfer_Qty'] * ed_hq_with_cost['Default Unit Cost']).sum()
                    st.metric("🏭 HQ Transfer Cost", f"${hq_cost:,.2f}")

                # 4. Vendor Remainder
                hq_final_map = ed_hq.set_index('SKU')['Transfer_Qty'].to_dict()
                data['Final_HQ_Qty'] = data['SKU'].map(
                    lambda x: hq_final_map.get(x, 0))
                data['Vendor_Units'] = (
                    data['Total_Units_Needed'] - data['Final_HQ_Qty']).clip(lower=0)
                data['Vendor_Cases'] = np.ceil(
                    data['Vendor_Units'] / data['Order In Quantities']
                )

                if not ed_hq.empty:
                    st.metric("Total Transfer Units",
                              f"{int(ed_hq['Transfer_Qty'].sum())}")
                    buf_hq = io.BytesIO()
                    with pd.ExcelWriter(buf_hq, engine='xlsxwriter') as writer:
                        ed_hq.to_excel(writer, index=False,
                                       sheet_name='HQ_Transfer')
                        # Format GTIN column as text to preserve leading zeros
                        text_fmt = writer.book.add_format({'num_format': '@'})
                        writer.sheets['HQ_Transfer'].set_column(
                            'B:B', 20, text_fmt)
                    st.download_button(f"📥 Download HQ Transfer", buf_hq.getvalue(),
                                       file_name=f"{date_str}_{selected_vendor}_HQ_{short_name}.xlsx",
                                       key=f"dl_hq_{short_name}")

                st.divider()

                # 5. Vendor Order UI
                st.subheader(f"🛒 Vendor Orders: {short_name}")
                order_summary = data[data['Vendor_Units'] > 0][[
                    'SKU', 'GTIN', 'Item Name', 'Vendor_Cases', 'Order In Quantities',
                    'Vendor_Units', 'Current_Inv', 'Max', 'Default Unit Cost'
                ]].copy().reset_index(drop=True)
                order_summary.rename(columns={
                    'Vendor_Cases': 'Order (Cases)',
                    'Order In Quantities': 'Case Pack',
                    'Vendor_Units': 'Total Units'
                }, inplace=True)

                if not order_summary.empty:
                    frozen_mask = order_summary['Item Name'].str.startswith(
                        'FRZN', na=False)

                    for label, df_type in [
                        ("📦 Dry Order", order_summary[~frozen_mask]),
                        ("❄️ Frozen Order", order_summary[frozen_mask])
                    ]:
                        st.markdown(f"#### {label}")
                        if not df_type.empty:
                            ed_df = st.data_editor(df_type, use_container_width=True,
                                                   hide_index=True, num_rows="dynamic",
                                                   key=f"vend_{label}_{short_name}")
                            cost = (ed_df['Total Units'] *
                                    ed_df['Default Unit Cost']).sum()
                            st.metric(f"{label} Cost", f"${cost:,.2f}")

                            export_df = ed_df[[
                                'GTIN', 'Item Name', 'Order (Cases)']].copy()
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
                                               file_name=f"{date_str}_{label}_{short_name}.xlsx",
                                               key=f"dl_{label}_{short_name}")
                        else:
                            st.write("No items in this category.")
                else:
                    st.success(
                        "No vendor order needed (Items may be covered by HQ).")
            else:
                st.error(f"Missing column '{long_name}' in Catalog.")

    # --- CONSOLIDATED SUMMARY & DOWNLOAD ---
    st.divider()
    st.subheader("📊 Consolidated Order Summary")
    st.caption("Total items being ordered across all stores (vendor + HQ)")

    # Aggregate all orders across stores
    all_orders = []

    for i, short_name in enumerate(selected_stores):
        long_name = inv_store_map[short_name]
        if long_name in df_master.columns:
            current_lt = store_lead_times[short_name]

            # Rebuild store data (same as tabs)
            lookup_cols = ['SKU', 'Order In Quantities',
                           f'{short_name}_DNO', f'{short_name}_Min', f'{short_name}_Max']
            valid_lookup = [
                c for c in lookup_cols if c in rules_matrix.columns]
            store_rules = rules_matrix[valid_lookup].copy().rename(columns={
                f'{short_name}_DNO': 'DNO',
                f'{short_name}_Min': 'Min',
                f'{short_name}_Max': 'Max'
            })

            store_inv = df_master[[
                'SKU', 'GTIN', 'Item Name', 'Default Unit Cost', long_name, hq_col
            ]].copy().rename(columns={long_name: 'Current_Inv', hq_col: 'HQ_Qty'})

            data = pd.merge(store_inv, store_rules, on='SKU', how='left')
            data = data.fillna({
                'DNO': 0, 'Order In Quantities': 1, 'Min': 0,
                'Max': 0, 'Current_Inv': 0, 'HQ_Qty': 0, 'Default Unit Cost': 0
            })
            data['DNO'] = data['DNO'].astype(bool)

            data['Effective_Min'] = data['Min'] + (current_lt * 0.2)
            data['Needs_Order'] = np.where(
                data['Order In Quantities'] == 1,
                (data['Current_Inv'] < data['Max']),
                (data['Current_Inv'] < data['Effective_Min'])
            )
            data['Needs_Order'] = data['Needs_Order'] & (data['DNO'] == False)
            data['Units_Needed_To_Max'] = np.where(
                data['Needs_Order'], data['Max'] - data['Current_Inv'], 0
            )
            data['Total_Units_Needed'] = np.ceil(
                np.maximum(data['Units_Needed_To_Max'], 0) /
                data['Order In Quantities']
            ) * data['Order In Quantities']

            # Apply allocation if exists
            data['Allocated_HQ'] = data['SKU'].apply(
                lambda sku: st.session_state.hq_allocations.get(
                    f"alloc_{sku}_{short_name}", 0)
                if "hq_allocations" in st.session_state else 0
            )

            data['Suggested_HQ_Qty'] = np.where(
                (data['Total_Units_Needed'] > 0) & (data['Allocated_HQ'] > 0),
                data['Allocated_HQ'],
                np.where(
                    (data['Total_Units_Needed'] > 0) & (
                        data['HQ_Qty'] > hq_threshold),
                    data['Total_Units_Needed'], 0
                )
            )

            # Vendor orders
            data['Vendor_Units'] = (
                data['Total_Units_Needed'] - data['Suggested_HQ_Qty']).clip(lower=0)
            data['Vendor_Cases'] = np.ceil(
                data['Vendor_Units'] / data['Order In Quantities']
            )

            # Collect all orders (both vendor and HQ)
            order_items = data[data['Total_Units_Needed'] > 0][[
                'SKU', 'GTIN', 'Item Name', 'Order In Quantities', 'Vendor_Cases', 'Suggested_HQ_Qty', 'Default Unit Cost'
            ]].copy()
            order_items['Store'] = short_name
            order_items['Vendor_Units'] = order_items['Vendor_Cases'] * \
                order_items['Order In Quantities']
            order_items['HQ_Units'] = order_items['Suggested_HQ_Qty']

            all_orders.append(order_items)

    if all_orders:
        combined_orders = pd.concat(all_orders, ignore_index=True)

        # Aggregate by SKU
        summary = combined_orders.groupby('SKU').agg({
            'GTIN': 'first',
            'Item Name': 'first',
            'Order In Quantities': 'first',
            'Vendor_Units': 'sum',
            'HQ_Units': 'sum',
            'Default Unit Cost': 'first'
        }).reset_index()

        # Filter to only items with vendor orders (exclude HQ-only items)
        summary = summary[summary['Vendor_Units'] > 0].copy()

        summary['Total_Units'] = summary['Vendor_Units']
        summary['Total_Cost'] = summary['Total_Units'] * \
            summary['Default Unit Cost']

        # Display summary
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

        # Metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Items", len(summary))
        with col2:
            st.metric("Total Units Ordered", int(summary['Total_Units'].sum()))
        with col3:
            st.metric("Total Order Value",
                      f"${summary['Total_Cost'].sum():,.2f}")

        # Download consolidated file (vendor orders only)
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
            # Format GTIN column as text
            text_fmt = writer.book.add_format({'num_format': '@'})
            writer.sheets['Consolidated_Order'].set_column('A:A', 20, text_fmt)
            writer.sheets['Consolidated_Order'].set_column('B:B', 40)

        st.download_button(
            "📥 Download Consolidated Order Summary",
            buf.getvalue(),
            file_name=f"{date_str}_{selected_vendor}_CONSOLIDATED_ORDER.xlsx",
            key="dl_consolidated"
        )

# --- WELCOME / MISSING FILES STATE ---
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
            st.image("./Data/Images/Export Example.png",
                     use_container_width=True, caption="Select the 'Filtered' option.")
        except:
            st.warning("Reference image not found.")
elif rules_matrix is None:
    st.warning(
        "⚠️ Please select a vendor and click 'Load Rules from Google Sheets' to continue.")
