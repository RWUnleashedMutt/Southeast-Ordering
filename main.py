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
    "HQ Non Southeast Items": "1W-AGqIXwcqL7clDHad43hFmpPrrXzNUDYC4-dVGpngo",
    'Adored Beast': '1HwOxpAzI_HlntVVfOqxBVAWDy7cznPxxhUqOR5cy6ng',
    'Ark Naturals': '1hgs38gm96v_ZansdVJTdr4JEsK-6TTarlbuBIr2V9C0',
    'Aroma Paws': '1fTvxu-y3rVpvxkt8elR1bZMECReblLE0zmYQDr1ePPg',
    'Big Spoon Roasters': '1VlH5VEWqexB4mxd4PsQx9gg3uu8tqyBi_QC01EiDEkQ',
    'Bradley Caldwell': '1eqENDXTdDJVKdos-VUXYNYMNM806rNcDrv63Q654nyc',
    'Brilliant Salmon Oil': '1ZJg6pPEf502MZVGCvuQcxDFHXMhWep0xdyA4xlj92aw',
    'Butchers Block': '1nDtvvDVu9tAzR2iDB4uMpUG3rcN3Fm_v09WJw3jvbJI',
    'Canine Caviar': '1TJXe9V_aF1A1wm_O9XK_iWJNU119iH3ZBBorUlX_0ss',
    'Colorado Pet Treats': '1U4nQGJvgyPWLST96Y6a4yrgJ2jGGicS6p4f7jesL8p8',
    'Comfy Cone': '15SuKA1HiSOZDs78x1ZgQOG0cUXnZ-kBJyKsUG59btQY',
    'Dexy Paws': '1fux791xEUU9shk2kyyFK6B-f6sjJlx3zser-jq9oHYU',
    'Dezi Roo': '1JwTm3gHTLXlGUlOTGQdteNMSIZnQMt6Z2uqE6R4_o_A',
    'Evangers': '1Lg9-ar14KHJDgWjFGqFbhuh-1-OM_BpA3ABIaoWe_gE',
    'Fluff & Tuff': '1nGWM9Lt34e3vpqaETjPeMVsCTKVC9kIEQ3VVx1mEUqY',
    'From The Field': '1wfs8bWVlUwJ1L6O518QkA8uheX0agIeSubnAO0-XYCo',
    'Front Porch Pets': '1CyW8rNNWzmYH9iqVRgN5iTWCiqgd-cJnrAJGktGS2a0',
    'Glacier Peak': '1iLFcfirV-2knXYGDqEE4721DtaRP_KFDgmtO-WsChMo',
    'Go Cat': '1FO0eFavBINXOgHXTiJvhEf9lvYdHQsQEgusJ62RLGrc',
    'Great Lakes': '1ajpaKEq8XR-M_Wu9m_VOhMfmHkjjmOXYfGWENg8j02s',
    'Homeopet': '1O35i1E_1lWxOkTJTvaURW2_qwlVO2YGaoBRfFvcstjE',
    'InClover': '1GJX-rqphRYAHM50HKrXhE3qG3ZUeB9kP0njwcuM56co',
    'Kennel Master': '1YgbCH_UxFZYAKnyJRki1ReNIdgqyUHtPS8gztUbpJaQ',
    'Mountain Dog': '14lPZsNmNS42gnXIh5Kh9nPRVCAep59hwj1Awj4H8v3Q',
    'Multi Pet': '1KjTgp4NCL5EXM7kKUrI-FIfVzvh9UYXBgz3o24RkeXU',
    'Myos': '13wEZ1Y9REyUJwjSRmXT46dZoW9DDUXdNrsw5JFgghHA',
    'Nordic Naturals': '1QvApqLGh0uFcRbbNLkpxcyqMdihM_zrc2cvvJEJ9YEg',
    'PAW': '1pWnAVNS2oRb38Dv1oXR2mwhdQbVCSG2tnUVCM-5SrTo',
    'Petmate': '1uOuHEjbHli6LVMsgDJbrfiuV1B9_QftMMeiqPH_C5bM',
               'Petsafe': '1ZTxuc7mazD40A3q76-G9EDPmI6O5nFLvtRlloo5eWQs',
               'Phillips': '1AyaU_YubXM5Qx88Deo7Nj3OFUBTeIzx4VUXawe_YeWI',
               'Playology': '1crFl1pFzMluFAcUTuMcrTaAJGETtua3iU8L8HIELny8',
               'Polka Dog': '1JUFN_ErS6FXUKD9gv_RzccxJplwpEDiaX3Am4LW0shw',
               'QT Dog': '1__-S-g-FdiuwKFyTZYq7fCJTwN3irMqHfvF99hrMhLY',
               'SE': '1O6HWGeLgtdScnJ0_pQc8asaSj3-L4pP9vjCvvXa26vQ',
               'Trueblue': '1vvMahz0JVn-_mO_Dry5amhebKbc_T_hAzVJYarP8o-U',
               'Tuesdays Natural Dog': '1f_iWF48FflsFBlVkR3P5Sk49Q87Q8Fpl8tklKYKsHtk',
               'Unique': '1Cf40Nm57h2gm_le_0gOV-jHfSpHjJHb6F8-0wP1cA0s',
               'WPO': '1ySBJWhHh9_F_kAD3tvNZNA9ZuPLOAx3xfX_MwqOYCOA',
               'Wild Meadow Farms': '1NOkBS71fYQSOtIs_cwWMGmn0WDJK8YfO51GVyVxaMEg',
               'Winnie Lou': '1sFhwEVHFhAZI9mgVLCy1EFUR3He76ZrJFEJP1BiH2gQ',
               'Zenta': '1x1mH8ldOwNLXOLtf8RXhSHQliOUO9mNZmHtliTpPWKw'
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


# --- SESSION STATE INITIALIZATION ---
def init_session_defaults():
    """Initialize all session state defaults upfront."""
    defaults = {
        "rules_vendor": None,
        "rules_matrix": None,
        "hq_allocations": {},  # Structure: {sku: {store_code: qty}}
        "current_tab": 0,  # Track which store tab user is viewing
        "allocations_submitted": False,  # Track if allocations have been locked in
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


# --- APP ---
st.set_page_config(page_title="Inventory & Ordering System", layout="wide")

# Initialize session state FIRST (before any state access)
init_session_defaults()

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

    # **Clear state when vendor changes**
    if selected_vendor != st.session_state.get("rules_vendor") and selected_vendor != "-- Select a Vendor --":
        st.session_state.rules_matrix = None
        st.session_state.rules_vendor = None
        st.session_state.hq_allocations = {}  # Clear orphaned allocations
        st.session_state.allocations_submitted = False  # Reset allocation submission

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

# --- LOAD RULES FROM SHEETS ---
rules_matrix = None

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
elif st.session_state.get("rules_matrix") is not None and st.session_state.get("rules_vendor") == selected_vendor:
    # Restore already-loaded matrix if vendor hasn't changed
    rules_matrix = st.session_state["rules_matrix"]
    st.sidebar.success(f"✅ Rules loaded: {len(rules_matrix)} SKUs")

# --- MAIN APP ---
if catalog_file and rules_matrix is not None and selected_stores:
    df_master = load_catalog(catalog_file)

    # Filter rules to only SKUs present in the catalog
    catalog_skus = set(df_master['SKU'].unique())
    rules_matrix = rules_matrix[rules_matrix['SKU'].isin(catalog_skus)].copy()

    # Validate Order In Quantities (OIQ) to prevent division by zero
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

    # --- CORE ORDER CALCULATION ---
    def compute_store_order(store_code, df_master, rules_matrix, hq_col,
                            hq_threshold, allocation_candidates, hq_allocations):
        """
        Single source of truth for all order calculations.
        Returns a fully computed DataFrame for one store with columns:
          SKU, GTIN, Item Name, Default Unit Cost, Current_Inv, HQ_Qty,
          Order In Quantities, Min, Max, DNO,
          Total_Units_Needed, Allocated_HQ, Is_Allocation_Candidate,
          Suggested_HQ_Qty, Vendor_Units, Vendor_Cases
        """
        long_name = inv_store_map[store_code]

        lookup_cols = ['SKU', 'Order In Quantities',
                       f'{store_code}_DNO', f'{store_code}_Min', f'{store_code}_Max']
        valid_lookup = [c for c in lookup_cols if c in rules_matrix.columns]
        store_rules = rules_matrix[valid_lookup].copy().rename(columns={
            f'{store_code}_DNO': 'DNO',
            f'{store_code}_Min': 'Min',
            f'{store_code}_Max': 'Max'
        })

        extra_cols = ['SKU', 'GTIN', 'Item Name',
                      'Default Unit Cost', long_name, hq_col]
        available_cols = [c for c in extra_cols if c in df_master.columns]
        store_inv = df_master[available_cols].copy().rename(
            columns={long_name: 'Current_Inv', hq_col: 'HQ_Qty'}
        )

        data = pd.merge(store_inv, store_rules, on='SKU', how='left')
        data = data.fillna({
            'DNO': 0, 'Order In Quantities': 1, 'Min': 0,
            'Max': 0, 'Current_Inv': 0, 'HQ_Qty': 0, 'Default Unit Cost': 0
        })
        data['DNO'] = data['DNO'].astype(bool)

        # Order trigger logic
        data['Effective_Min'] = data['Min']
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
        # Round to the nearest whole case rather than always rounding up —
        # e.g. needing 25 units at a 12-pack lands on 2 cases (24, close to
        # Max) instead of 3 cases (36, well past Max). Still guarantees at
        # least 1 case whenever an order is actually triggered, so small
        # Min/Max windows relative to case size (intentional low-velocity
        # SKUs) behave exactly as before.
        raw_cases = data['Units_Needed_To_Max'] / data['Order In Quantities']
        rounded_cases = np.floor(raw_cases + 0.5)  # round-half-up
        rounded_cases = np.where(
            (data['Units_Needed_To_Max'] > 0) & (rounded_cases < 1),
            1, rounded_cases
        )
        data['Total_Units_Needed'] = rounded_cases * \
            data['Order In Quantities']

        # Safety net: rounding to the nearest case can occasionally round
        # DOWN in a way that, combined with a narrow Min/Max window, leaves
        # post-order stock below Min. Never let that happen — bump up one
        # more case if the rounded order wouldn't clear Min.
        would_understock = data['Needs_Order'] & (
            (data['Current_Inv'] + data['Total_Units_Needed']
             ) < data['Effective_Min']
        )
        data['Total_Units_Needed'] = np.where(
            would_understock,
            data['Total_Units_Needed'] + data['Order In Quantities'],
            data['Total_Units_Needed']
        )

        # HQ allocation awareness
        data['Allocated_HQ'] = data['SKU'].apply(
            lambda sku: hq_allocations.get(sku, {}).get(store_code, 0)
        )
        data['Is_Allocation_Candidate'] = data['SKU'].isin(
            allocation_candidates.keys())

        data['Suggested_HQ_Qty'] = np.where(
            (data['Total_Units_Needed'] > 0) & (data['Allocated_HQ'] > 0),
            data['Allocated_HQ'],
            np.where(
                (data['Total_Units_Needed'] > 0) &
                (data['HQ_Qty'] > hq_threshold) &
                (~data['Is_Allocation_Candidate']),
                data['Total_Units_Needed'], 0
            )
        )

        data['Vendor_Units'] = (
            data['Total_Units_Needed'] - data['Suggested_HQ_Qty']
        ).clip(lower=0)
        data['Vendor_Cases'] = np.ceil(
            data['Vendor_Units'] / data['Order In Quantities']
        )

        return data

    # --- PRE-ALLOCATION: FIND HQ CONFLICT SKUS ---
    def get_allocation_candidates(df_master, rules_matrix, hq_col,
                                  selected_stores, hq_threshold):
        """
        Identify SKUs where total store demand exceeds HQ supply.
        Accepts data as arguments so caching is based on actual content.
        """
        store_needs_list = []

        for store_code in selected_stores:
            long_name = inv_store_map[store_code]
            if long_name not in df_master.columns:
                continue

            # Use compute_store_order with empty allocations to get raw demand
            data = compute_store_order(
                store_code, df_master, rules_matrix, hq_col,
                hq_threshold, allocation_candidates={}, hq_allocations={}
            )
            needs = data[data['Total_Units_Needed'] > 0][
                ['SKU', 'Total_Units_Needed', 'Current_Inv',
                    'HQ_Qty', 'Order In Quantities']
            ].copy()
            needs['Store'] = store_code
            needs.rename(
                columns={'Total_Units_Needed': 'Units_Needed'}, inplace=True)
            store_needs_list.append(needs)

        if not store_needs_list:
            return {}

        combined = pd.concat(store_needs_list, ignore_index=True)

        sku_groups = combined.groupby('SKU').agg({
            'Units_Needed': 'sum',
            'HQ_Qty': 'first',
            'Store': 'count'
        }).rename(columns={'Store': 'Store_Count'})

        # Conflict = total demand exceeds HQ supply AND HQ has meaningful stock
        conflicts = sku_groups[
            (sku_groups['Units_Needed'] > sku_groups['HQ_Qty']) &
            (sku_groups['HQ_Qty'] > hq_threshold)
        ]

        allocation_candidates = {}
        for sku in conflicts.index:
            sku_data = combined[combined['SKU'] == sku]
            demand_map = {
                row['Store']: {
                    'demand': int(row['Units_Needed']),
                    'current_inv': int(row['Current_Inv'])
                }
                for _, row in sku_data.iterrows()
            }
            allocation_candidates[sku] = {
                'stores': list(sku_data['Store'].unique()),
                'hq_qty': int(sku_data['HQ_Qty'].iloc[0]),
                'demand_map': demand_map,
                'oiq': int(sku_data['Order In Quantities'].iloc[0])
                if 'Order In Quantities' in sku_data.columns else 1
            }

        return allocation_candidates

    allocation_candidates = get_allocation_candidates(
        df_master, rules_matrix, hq_col, selected_stores, hq_threshold
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
        st.dataframe(alloc_df, width='stretch', hide_index=True)

        # Initialize session state for allocations
        if "hq_allocations" not in st.session_state:
            st.session_state.hq_allocations = {}

        # Ensure all SKUs in candidates have a store dict
        for sku in allocation_candidates:
            if sku not in st.session_state.hq_allocations:
                st.session_state.hq_allocations[sku] = {}

        st.write("**Allocate HQ Qty by Store:**")
        st.info(
            "👆 \"Remaining\" updates live as you type. Once everything looks "
            "right, click **Push Allocations** to apply it to the store tabs below.")

        # Use a fragment so editing an allocation only reruns this section —
        # not the full catalog/rules/store-tab pipeline — and "Remaining"
        # updates live as you type instead of waiting for a submit.
        @st.fragment
        def render_allocation_inputs():
            # Build allocation inputs and track totals dynamically
            for sku in sorted(allocation_candidates.keys()):
                info = allocation_candidates[sku]
                item_name = df_master[df_master['SKU'] == sku]['Item Name'].iloc[0] if len(
                    df_master[df_master['SKU'] == sku]) > 0 else "Unknown"
                hq_available = int(info['hq_qty'])
                oiq = int(info['oiq'])
                demand_map = info.get('demand_map', {})

                st.markdown(f"**{sku}** — {item_name} (Case Pack: {oiq})")

                # Only the stores that actually need this SKU get an input.
                # The input stretches to fill its column instead of a fixed
                # pixel width, so it no longer leaves a gap before the next
                # store — the column itself is already comfortably wide
                # enough (page is in wide mode, 4 per row) to keep the
                # native +/- stepper arrows visible.
                relevant_stores = [
                    s for s in selected_stores if s in info['stores']]
                cards_per_row = 4

                total_allocated = 0
                for row_start in range(0, len(relevant_stores), cards_per_row):
                    row_stores = relevant_stores[row_start:row_start + cards_per_row]
                    row_cols = st.columns(cards_per_row)
                    for col, store_code in zip(row_cols, row_stores):
                        with col:
                            # **Use nested structure: allocs[sku][store_code]**
                            if store_code not in st.session_state.hq_allocations[sku]:
                                st.session_state.hq_allocations[sku][store_code] = 0

                            # Look up demand first so the input can't be
                            # incremented past what this store actually
                            # needs — no reason to push more HQ stock at a
                            # store than it's asking for, even if HQ has
                            # more available overall.
                            store_demand_info = demand_map.get(store_code, {})
                            current_inv = int(
                                store_demand_info.get('current_inv', 0))
                            demand = int(store_demand_info.get('demand', 0))

                            max_alloc = max(
                                min(int(hq_available), demand), 0)

                            # Clamp any previously-stored value down to the
                            # new tighter max so Streamlit doesn't error on
                            # value > max_value
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

                            # Has/Needs directly under its own input, filling
                            # the same width so it lines up with the box
                            # above it rather than trailing off to one side
                            st.markdown(
                                f"<div style='font-size:14px; width:100%; "
                                f"margin-top:-6px;'>Has: <b>{current_inv}</b>"
                                f" &nbsp;|&nbsp; Needs: <b>{demand}</b></div>",
                                unsafe_allow_html=True
                            )

                    # Breathing room between wrapped rows for SKUs with
                    # more stores than fit in one row
                    if row_start + cards_per_row < len(relevant_stores):
                        st.markdown(
                            "<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

                # Show remaining on its own row below all store inputs —
                # this recalculates live now, no submit needed to see it
                remaining = hq_available - total_allocated
                rem_col = st.columns([3, 1])[1]
                with rem_col:
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

            # Track whether any SKU is over-allocated
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

            # Disabling this is safe here (unlike the old form_submit_button):
            # a fragment reruns itself on every number_input edit, so the
            # disabled state is always recalculated fresh — no stuck/frozen
            # button like the form version had.
            pushed = st.button(
                "🚀 Push Allocations",
                width="stretch",
                disabled=bool(over_allocated_skus)
            )
            if pushed and not over_allocated_skus:
                st.session_state.allocations_submitted = True
                # Full-app rerun (st.rerun's default scope) so the HQ
                # Transfer / Vendor Order / Consolidated Summary sections
                # below — which live outside this fragment — pick up the
                # new allocations immediately.
                st.rerun()

        render_allocation_inputs()

        # --- ALLOCATION CONFIRMATION SUMMARY ---
        # Shown after submit so nothing about unassigned HQ stock is silent.
        if st.session_state.get("allocations_submitted"):
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

                # Stores with demand that received nothing
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

                # HQ Transfer UI
                st.subheader(f"🚛 HQ Transfer List: {short_name}")
                st.caption(
                    f"Items with HQ Stock > {hq_threshold} are suggested here (or your allocation above). Delete a row or set Qty to 0 to move it to the Vendor Order.")

                hq_display = data[data['Suggested_HQ_Qty'] > 0][[
                    'SKU', 'GTIN', 'Item Name', 'Suggested_HQ_Qty', 'Current_Inv', 'HQ_Qty'
                ]].copy()
                hq_display.rename(
                    columns={'Suggested_HQ_Qty': 'Transfer_Qty'}, inplace=True)

                ed_hq = st.data_editor(hq_display, use_container_width=True,
                                       hide_index=True, num_rows="dynamic", key=f"hq_ed_{short_name}")

                # Rows added via the dynamic editor start out entirely blank
                # (NaN in every column) until the person fills them in. NaN
                # breaks int()/xlsxwriter/etc. downstream, so drop any row
                # that's missing its SKU before doing anything else with it.
                ed_hq = ed_hq[ed_hq['SKU'].notna()].copy()

                # Display HQ Transfer Cost
                if not ed_hq.empty:
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
                        workbook = writer.book
                        worksheet = workbook.add_worksheet('HQ_Transfer')
                        writer.sheets['HQ_Transfer'] = worksheet

                        # --- Formats ---
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

                        # --- Row 0: Store name header ---
                        store_display_name = inv_store_map.get(
                            short_name, short_name).replace('Current Quantity ', '')
                        worksheet.write(
                            0, 0, f"HQ Transfer — {store_display_name}", store_header_fmt)
                        worksheet.set_row(0, 22)

                        # --- Row 1: Column headers ---
                        for col_idx, col_name in enumerate(ed_hq.columns):
                            worksheet.write(
                                1, col_idx, col_name, col_header_fmt)

                        # --- Rows 2+: Data with borders ---
                        gtin_col_idx = list(ed_hq.columns).index(
                            'GTIN') if 'GTIN' in ed_hq.columns else None
                        for row_idx, row in enumerate(ed_hq.itertuples(index=False), start=2):
                            for col_idx, value in enumerate(row):
                                fmt = text_fmt if col_idx == gtin_col_idx else cell_fmt
                                # Blank rows added via the dynamic data_editor
                                # can still leave individual cells (not just
                                # SKU) as NaN — xlsxwriter's write_number()
                                # rejects NaN/inf outright, so route those
                                # through write_blank() instead of write().
                                if pd.isna(value):
                                    worksheet.write_blank(
                                        row_idx, col_idx, None, fmt)
                                else:
                                    worksheet.write(
                                        row_idx, col_idx, value, fmt)

                        # --- Column widths ---
                        worksheet.set_column('A:A', 12)   # SKU
                        worksheet.set_column('B:B', 20)   # GTIN
                        worksheet.set_column('C:C', 40)   # Item Name
                        worksheet.set_column('D:F', 14)   # Qty columns

                    st.download_button(f"📥 Download HQ Transfer", buf_hq.getvalue(),
                                       file_name=f"{short_name}_{date_str}_HQ_{selected_vendor}.xlsx",
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

                    for label, file_label, df_type in [
                        ("📦 Dry Order", "Dry", order_summary[~frozen_mask]),
                        ("❄️ Frozen Order", "Frozen",
                         order_summary[frozen_mask])
                    ]:
                        st.markdown(f"#### {label}")
                        if not df_type.empty:
                            ed_df = st.data_editor(df_type, use_container_width=True,
                                                   hide_index=True, num_rows="dynamic",
                                                   key=f"vend_{label}_{short_name}")

                            # Same NaN guard as the HQ editor above — a
                            # freshly-added blank row must be dropped before
                            # any int()/formatting/cost math touches it.
                            ed_df = ed_df[ed_df['SKU'].notna()].copy()
                            if ed_df.empty:
                                st.write("No items in this category.")
                                continue

                            cost = (ed_df['Total Units'] *
                                    ed_df['Default Unit Cost']).sum()
                            st.metric(f"{label} Cost", f"${cost:,.2f}")

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
            else:
                st.error(f"Missing column '{long_name}' in Catalog.")

    # --- CONSOLIDATED SUMMARY & DOWNLOAD ---
    st.divider()
    st.subheader("📊 Consolidated Order Summary")
    st.caption("Total items being ordered across all stores (vendor + HQ)")

    # Aggregate all orders across stores — reuse compute_store_order, no duplicate logic
    all_orders = []

    for short_name in selected_stores:
        long_name = inv_store_map[short_name]
        if long_name not in df_master.columns:
            continue

        data = compute_store_order(
            short_name, df_master, rules_matrix, hq_col,
            hq_threshold, allocation_candidates,
            st.session_state.get("hq_allocations", {})
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
