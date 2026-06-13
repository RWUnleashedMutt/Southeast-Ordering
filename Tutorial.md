# Southeast Inventory & Ordering System: Complete Beginner's Guide

## What Is This App?

This is a **Streamlit web application** that helps Southeast Pet (a retail pet supply company) manage inventory across 11 store locations. It:

- ✅ Loads product catalogs from Square POS
- ✅ Pulls ordering rules from Google Sheets
- ✅ Calculates what each store needs to order
- ✅ Suggests HQ warehouse transfers when it's more efficient than vendor orders
- ✅ Generates downloadable order files for each store

Think of it as an "smart ordering assistant" that figures out whether it's better to get products from the main warehouse or from vendors.

---

## Part 1: The Setup & Configuration (Lines 1-56)

### What's Happening Here?

This section is like the "instruction manual" for the app. It tells the app:

- What credentials to use (Google Sheets access)
- Which Google Sheets contain the ordering rules for each vendor
- How store names in the catalog map to store codes

### Breaking It Down:

```python
import streamlit as st
import pandas as pd
import io
import numpy as np
```

**These are libraries (tools) the app uses:**

- `streamlit` → Creates the interactive web interface
- `pandas` → Works with data in table format (like Excel)
- `numpy` → Does math on large numbers fast
- `io` → Handles file reading/writing

---

```python
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
```

**What this means:** "Hey Google, we need permission to read Google Sheets and Google Drive."

---

```python
SHEET_IDS = {
    'SE': '1O6HWGeLgtdScnJ0_pQc8asaSj3-L4pP9vjCvvXa26vQ',
    'Canine Caviar': '1TJXe9V_aF1A1wm_O9XK_iWJNU119iH3ZBBorUlX_0ss'
}
```

**What this means:** For each vendor name, store the Google Sheet ID where the ordering rules live. This is like a "phone book" — when you pick "SE" vendor, the app knows exactly which Google Sheet to pull rules from.

---

```python
store_map = {
    'Current Quantity City Market: DTR': 'CM',
    'Current Quantity Crabtree Valley Mall': 'CVM',
    # ... etc
}
```

**What this means:** The catalog file uses long store names (like "Current Quantity City Market: DTR"), but we want to use short codes ("CM") internally. This dictionary translates between them.

For example: `'Current Quantity City Market: DTR'` → becomes → `'CM'`

```python
inv_store_map = {v: k for k, v in store_map.items()}
```

**What this means:** Create the reverse mapping. So now we can also go from `'CM'` back to `'Current Quantity City Market: DTR'`. This is like having a two-way translation dictionary.

```python
priority_stores = ['CC', 'CM', 'CVM', 'LB', 'SH']
```

**What this means:** These 5 stores are prioritized and show up selected by default. (Maybe they're bigger stores or need faster reordering.)

---

## Part 2: Helper Functions (Lines 59-91)

### What Are These?

Small reusable tools that the app calls when it needs to do specific jobs. Think of them as shortcuts.

---

### Function 1: `clean_id()`

```python
def clean_id(val):
    if pd.isna(val):
        return ""
    return str(int(val)) if isinstance(val, float) and val.is_integer() else str(val)
```

**What it does:** Cleans up SKU and GTIN numbers that might be messy.

**Example:**

- Input: `12345.0` (a number with a decimal)
- Output: `"12345"` (a clean text string without the decimal)
- Input: Empty/missing value
- Output: `""` (empty string)

**Why?** SKUs and GTINs should always be text strings to preserve leading zeros (like "00123" not "123").

---

### Function 2: `load_catalog()`

```python
@st.cache_data
def load_catalog(file) -> pd.DataFrame:
    dtype_dict = {'GTIN': str, 'SKU': str}
    df = pd.read_excel(file, header=1, dtype=dtype_dict)
    df.columns = df.columns.str.strip()
    df['SKU'] = df['SKU'].apply(clean_id)
    if 'GTIN' in df.columns:
        df['GTIN'] = df['GTIN'].astype(str).str.strip()
    return df
```

**What it does:** Reads an Excel file and prepares it for use.

**Step by step:**

1. `@st.cache_data` — "Remember this data so we don't have to reload it every time"
2. `pd.read_excel(file, header=1)` — Read the Excel file (header in row 2, since row 1 might be headers)
3. `dtype_dict = {'GTIN': str, 'SKU': str}` — Tell pandas to treat SKU and GTIN as text, not numbers
4. `df.columns = df.columns.str.strip()` — Remove extra spaces from column names
5. `df['SKU'] = df['SKU'].apply(clean_id)` — Use our `clean_id()` function on every SKU
6. Return the cleaned data

**Returns:** A pandas DataFrame (think: a clean Excel spreadsheet in memory)

---

### Function 3: `get_google_client()`

```python
@st.cache_resource
def get_google_client():
    """Authenticate using Streamlit secrets — works both locally and on Streamlit Cloud."""
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    return gspread.authorize(creds)
```

**What it does:** Connects to Google Sheets using credentials stored securely in Streamlit Secrets.

**Why secure?** Never hardcode passwords or API keys in code. Streamlit Secrets keeps them safe.

**Returns:** An authorized Google client (ready to read/write Google Sheets)

---

### Function 4: `load_rules_from_sheets()`

```python
@st.cache_data(ttl=3600)  # Cache for one hour
def load_rules_from_sheets(vendor: str) -> pd.DataFrame:
```

**What it does:** Pulls the ordering rules matrix for a specific vendor from Google Sheets.

**Key parts:**

```python
if vendor not in SHEET_IDS:
    raise ValueError(f"No Sheet ID configured for vendor '{vendor}'.")
```

**= "Does this vendor exist in our config? If not, stop and show an error."**

```python
spreadsheet = client.open_by_key(SHEET_IDS[vendor])
worksheet = spreadsheet.sheet1
data = worksheet.get_all_records(value_render_option='UNFORMATTED_VALUE')
```

**= "Open the Google Sheet for this vendor and get all the data as a list of records."**

```python
for col in df.columns:
    if col.endswith('_DNO'):
        df[col] = df[col].map(
            lambda x: str(x).strip().upper() in ('TRUE', '1', 'YES', '1.0')
            if pd.notna(x) else False
        ).astype(bool)
```

**This is the tricky part:** Google Sheets can send back boolean values (TRUE/FALSE) in different formats:

- As actual booleans: `True` / `False`
- As numbers: `1` / `0`
- As text strings: `"TRUE"` / `"FALSE"`

This code handles all three safely. If the value is "TRUE", "1", "YES", or "1.0" (in any format), convert to `True`. Otherwise, `False`.

**Why is this important?** If you don't handle this correctly, you accidentally order items you shouldn't, or skip items you should order!

---

## Part 3: The Main App (Lines 94+)

### Setting Up the Page

```python
st.set_page_config(page_title="Inventory & Ordering System", layout="wide")
st.title("📦 Southeast Inventory & Ordering")
```

**What this does:** Sets the browser tab title and puts a big emoji header at the top.

---

### The Sidebar: Where Users Give Instructions

```python
with st.sidebar:
    st.header("1. Upload Files")
    catalog_file = st.file_uploader(
        "Upload Southeast Catalog (.xlsx)", type=['xlsx'])
```

**What this does:** Creates a file uploader in the sidebar. Users pick their Excel catalog file here.

**The sidebar is divided into 5 sections:**

#### Section 1: Upload Catalog

- User picks the Square catalog export file

#### Section 2: Select Vendor

```python
selected_vendor = st.selectbox(
    "Select vendor to load rules from Google Sheets:",
    options=["-- Select a Vendor --"] + list(SHEET_IDS.keys())
)
```

- Dropdown showing all vendors from `SHEET_IDS`
- User picks one, then clicks "Load Rules"

#### Section 3: Select Stores

```python
selected_stores = st.multiselect(
    "Select stores:", options=list(store_map.values()), default=priority_stores
)
```

- User can check multiple stores to process
- Priority stores are pre-selected

#### Section 4: HQ Threshold

```python
hq_threshold = st.slider("Suggest HQ Transfer if HQ Qty >", 0, 20, 6)
```

- If HQ has more than 6 units of something, suggest transferring it to stores instead of ordering from vendors
- User can adjust this slider

#### Section 5: Lead Times

```python
store_lead_times = {
    s: st.number_input(
        f"Lead Time: {s}", 0, 30, (1 if s in priority_stores else 7))
    for s in selected_stores
}
```

- For each selected store, ask: "How many days does it take to get stock from vendors?"
- Priority stores default to 1 day, others to 7 days
- This affects when we should reorder (if lead time is 7 days, reorder sooner)

---

## Part 4: Loading Rules from Google Sheets (Lines 176-201)

```python
if selected_vendor == "-- Select a Vendor --":
    st.sidebar.info("Please select a vendor to load rules.")
```

**= "If no vendor is picked, show a helpful message."**

```python
elif load_rules_btn:
    load_rules_from_sheets.clear()  # Force fresh pull — bypasses TTL cache
```

**= "User clicked the Load button. Get fresh data (don't use old cached data)."**

```python
with st.spinner(f"Loading rules matrix for **{selected_vendor}** from Google Sheets..."):
    try:
        rules_matrix = load_rules_from_sheets(selected_vendor)
        st.session_state["rules_matrix"] = rules_matrix
        st.session_state["rules_vendor"] = selected_vendor
        st.sidebar.success(f"✅ Rules loaded: {len(rules_matrix)} SKUs")
    except Exception as e:
        st.sidebar.error(f"❌ Failed to load rules: {e}")
```

**What this does:**

1. Show a loading spinner while retrieving data
2. Call our `load_rules_from_sheets()` function
3. Save the results in `st.session_state` (memory for this user session)
4. Show success or error message

**The `elif ... elif` pattern:**

- If no vendor: show message
- Else if Load button pressed: load new rules
- Else if we already loaded rules for this vendor: use the cached version (skip reloading)

---

## Part 5: Main Processing Logic (Lines 209+)

### Only Run If We Have Everything

```python
if catalog_file and rules_matrix is not None and selected_stores:
```

**= "Only proceed if the user uploaded a catalog, loaded rules, AND selected stores."**

---

### Filter Rules to Catalog SKUs

```python
df_master = load_catalog(catalog_file)
catalog_skus = set(df_master['SKU'].unique())
rules_matrix = rules_matrix[rules_matrix['SKU'].isin(catalog_skus)].copy()
```

**What this does:**

1. Load the catalog
2. Get all unique SKUs from the catalog
3. Filter the rules matrix to only include SKUs that exist in the catalog

**Why?** The rules matrix might have 5,000 SKUs, but we're only ordering from 500. Don't process the rest.

---

### Match Checking

```python
matched = len(rules_matrix['SKU'].unique())
total = len(catalog_skus)
rules_skus = set(rules_matrix['SKU'].unique())
unmatched_skus = catalog_skus - rules_skus
unmatched_list = sorted(list(unmatched_skus))

st.caption(f"✅ Matched {matched} of {total} catalog SKUs to rules.")

if unmatched_skus:
    print(f"\n⚠️  WARNING: {len(unmatched_skus)} Unmatched SKUs found:")
    for sku in unmatched_list:
        item_name = df_master[df_master['SKU'] == sku]['Item Name'].iloc[0]
        print(f"  - {sku}: {item_name}")
```

**What this does:** Tells you which products in the catalog don't have ordering rules. This might be:

- New products that need rules added
- Discontinued products still in the catalog
- Test/placeholder products

---

## Part 6: The "Clever" Part - HQ Allocation Logic (Lines 239-315)

### What Problem Does This Solve?

**Scenario:**

- Store A needs 20 units of Dog Food
- Store B needs 15 units of Dog Food
- Total demand: 35 units
- HQ only has 30 units
- **Problem:** We can't satisfy everyone!

**Solution:** Let the user manually allocate the 30 units across stores, and the remaining 5 units come from vendors.

### The Code:

```python
allocation_candidates = get_allocation_candidates(
    selected_vendor,
    tuple(selected_stores),
    hq_threshold
)
```

This function finds all SKUs where:

- Multiple stores need them
- HQ quantity is > threshold (worth considering)
- Total demand > HQ supply (actual conflict)

```python
if allocation_candidates:
    st.subheader("⚙️ HQ Allocation (Insufficient Stock)")
    st.caption("Items below have more demand than HQ can supply...")
```

**Shows a table of conflicts:**

| SKU   | Item Name | HQ Available | Total Demand | Shortage | Stores Needing |
| ----- | --------- | ------------ | ------------ | -------- | -------------- |
| 12345 | Dog Food  | 30           | 35           | 5        | CM, CC, LB     |

Then for each SKU, it creates number inputs:

```python
for store_code in selected_stores:
    if store_code in info['stores']:
        allocated = st.number_input(
            f"{store_code}", 0, max_alloc, 0, step=oiq, key=key
        )
```

**User sees:**

```
SKU 12345 — Dog Food (Case Pack: 5)
CM: [input field]  Has: 10 | Needs: 20
CC: [input field]  Has: 5  | Needs: 15
LB: [input field]  Has: 8  | Needs: 10
Remaining: [shows how much is left to allocate]
```

**User types in:** CM: 15, CC: 10, LB: 5
**App calculates:** Remaining: 0 (perfect!)
**What happens:** Each store gets their allocation from HQ, and any shortage comes from vendors.

---

## Part 7: Store-by-Store Ordering (Lines 317+)

### Create Tabs for Each Store

```python
tabs = st.tabs(selected_stores)

for i, short_name in enumerate(selected_stores):
    long_name = inv_store_map[short_name]
    with tabs[i]:
```

**What this does:** Creates a separate tab for each store. User clicks "CM" tab to see City Market's orders.

---

### Inside Each Tab: The Data Pipeline

#### Step 1: Get Store Rules & Inventory

```python
lookup_cols = ['SKU', 'Order In Quantities',
               f'{short_name}_DNO', f'{short_name}_Min', f'{short_name}_Max']
store_rules = rules_matrix[valid_lookup].copy()
```

**= Pull rules specific to this store (CM_Min, CM_Max, CM_DNO, etc.)**

```python
store_inv = df_master[[
    'SKU', 'GTIN', 'Item Name', 'Default Unit Cost', long_name, hq_col
]].copy()
```

**= Pull current inventory and HQ quantities from the catalog**

```python
data = pd.merge(store_inv, store_rules, on='SKU', how='left')
```

**= Join the inventory and rules together by SKU (like a VLOOKUP in Excel)**

---

#### Step 2: Rename & Fill Missing Values

```python
data = data.fillna({
    'DNO': 0, 'Order In Quantities': 1, 'Min': 0,
    'Max': 0, 'Current_Inv': 0, 'HQ_Qty': 0, 'Default Unit Cost': 0
})
```

**= If any values are missing, fill them with sensible defaults:**

- DNO missing? Default to 0 (order normally)
- Current inventory missing? Default to 0 (assume out of stock)
- Min missing? Default to 0 (no minimum)

```python
data['DNO'] = data['DNO'].astype(bool)
```

**= Convert DNO to True/False boolean (so comparisons work correctly)**

---

#### Step 3: Calculate "Needs Order" Status

```python
data['Effective_Min'] = data['Min'] + (current_lt * 0.2)
```

**= Adjust the minimum based on lead time**

**Example:**

- Min = 20 units
- Lead time = 7 days
- Effective_Min = 20 + (7 \* 0.2) = 20 + 1.4 = 21.4 units

**Why?** If it takes 7 days to get stock, we should reorder sooner (at a higher level). This buffer prevents stockouts.

```python
data['Needs_Order'] = np.where(
    data['Order In Quantities'] == 1,
    (data['Current_Inv'] < data['Max']),
    (data['Current_Inv'] < data['Effective_Min'])
)
```

**= Two different logic paths:**

**Path 1:** If "Order In Quantities" is 1 (special trigger logic)

- Order when: Current inventory < Max
- Example: Always keep between 0 and 100 units

**Path 2:** Normal perpetual logic

- Order when: Current inventory < Effective_Min
- Example: Order when you fall below 20 units (adjusted for lead time)

```python
data['Needs_Order'] = data['Needs_Order'] & (data['DNO'] == False)
```

**= AND: Never order if DNO is True (even if below minimum)**

---

#### Step 4: Calculate Quantities

```python
data['Units_Needed_To_Max'] = np.where(
    data['Needs_Order'], data['Max'] - data['Current_Inv'], 0
)
```

**= How many units to order to reach Max?**

**Example:**

- Max = 50, Current = 30
- Units_Needed_To_Max = 50 - 30 = 20 units

```python
data['Total_Units_Needed'] = np.ceil(
    np.maximum(data['Units_Needed_To_Max'], 0) / data['Order In Quantities']
) * data['Order In Quantities']
```

**= Round up to case pack sizes**

**Example:**

- Units_Needed = 20
- Order In Quantities = 12 (case pack size)
- Calculation: ceil(20 / 12) = ceil(1.67) = 2 cases
- 2 cases \* 12 = 24 units (order 24, not 20)

**Why?** You can't order partial cases. Always round up to full cases.

---

### HQ Transfer vs. Vendor Order

```python
data['Allocated_HQ'] = data['SKU'].apply(
    lambda sku: st.session_state.hq_allocations.get(
        f"alloc_{sku}_{short_name}", 0)
    if "hq_allocations" in st.session_state else 0
)
```

**= Did the user allocate HQ stock to this store? If so, use that amount.**

```python
data['Suggested_HQ_Qty'] = np.where(
    (data['Total_Units_Needed'] > 0) & (data['Allocated_HQ'] > 0),
    data['Allocated_HQ'],
    np.where(
        (data['Total_Units_Needed'] > 0) & (data['HQ_Qty'] > hq_threshold),
        data['Total_Units_Needed'], 0
    )
)
```

**= Logic:**

1. If user allocated HQ stock, use their allocation
2. Else if we need to order AND HQ has more than threshold, suggest from HQ
3. Else, nothing from HQ

```python
data['Vendor_Units'] = (
    data['Total_Units_Needed'] - data['Suggested_HQ_Qty']).clip(lower=0)
```

**= Whatever we couldn't get from HQ, order from vendors**

**Example:**

- Total needed: 50
- Allocated from HQ: 30
- Vendor order: 50 - 30 = 20 units

---

### User Edits HQ Transfer (Data Editor)

```python
ed_hq = st.data_editor(hq_display, use_container_width=True,
                       hide_index=True, num_rows="dynamic", key=f"hq_ed_{short_name}")
```

**= Show an editable table of HQ transfers. User can:**

- Delete rows (don't transfer this item)
- Change quantities (transfer more/less)
- Add new rows (transfer additional items)

```python
hq_final_map = ed_hq.set_index('SKU')['Transfer_Qty'].to_dict()
data['Final_HQ_Qty'] = data['SKU'].map(lambda x: hq_final_map.get(x, 0))
```

**= After user edits, update the final HQ quantities**

---

### Vendor Order Display

```python
order_summary = data[data['Vendor_Units'] > 0]
frozen_mask = order_summary['Item Name'].str.startswith('FRZN', na=False)

for label, df_type in [
    ("📦 Dry Order", order_summary[~frozen_mask]),
    ("❄️ Frozen Order", order_summary[frozen_mask])
]:
```

**= Split orders into two groups:**

- **Dry:** Products that don't start with "FRZN"
- **Frozen:** Products that start with "FRZN"

**Why?** Frozen items might need different handling (separate shipping, refrigeration, etc.)

```python
ed_df = st.data_editor(df_type, use_container_width=True,
                       hide_index=True, num_rows="dynamic",
                       key=f"vend_{label}_{short_name}")
```

**= Show editable table. User can adjust quantities if needed.**

```python
cost = (ed_df['Total Units'] * ed_df['Default Unit Cost']).sum()
st.metric(f"{label} Cost", f"${cost:,.2f}")
```

**= Calculate and display the total cost of this order segment**

---

### Download Files

```python
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
    export_df.to_excel(writer, index=False, sheet_name='Vendor_Order')
    text_fmt = writer.book.add_format({'num_format': '@'})
    writer.sheets['Vendor_Order'].set_column('A:A', 20, text_fmt)
```

**= Create an Excel file in memory with the order**

```python
st.download_button(f"📥 Download {label}", buf.getvalue(),
                   file_name=f"{date_str}_{label}_{short_name}.xlsx",
                   key=f"dl_{label}_{short_name}")
```

**= Show a download button. User clicks, gets Excel file**

---

## Part 8: Consolidated Summary (Lines 611+)

### Pull Everything Together

```python
all_orders = []

for i, short_name in enumerate(selected_stores):
    # ... rebuild store data (same calculations as tabs)
    # ... collect all orders
    all_orders.append(order_items)

if all_orders:
    combined_orders = pd.concat(all_orders, ignore_index=True)
```

**= Loop through all stores and collect their orders into one big dataframe**

```python
summary = combined_orders.groupby('SKU').agg({
    'GTIN': 'first',
    'Item Name': 'first',
    'Order In Quantities': 'first',
    'Vendor_Units': 'sum',
    'HQ_Units': 'sum',
    'Default Unit Cost': 'first'
}).reset_index()
```

**= Group by SKU and sum across all stores**

**Example:**

- Store CM ordering 20 units of SKU 12345
- Store CC ordering 15 units of SKU 12345
- Summary: SKU 12345 needs 35 units total

```python
summary = summary[summary['Vendor_Units'] > 0].copy()
```

**= Only show items that have vendor orders (exclude HQ-only items)**

```python
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Items", len(summary))
with col2:
    st.metric("Total Units Ordered", int(summary['Total_Units'].sum()))
with col3:
    st.metric("Total Order Value", f"${summary['Total_Cost'].sum():,.2f}")
```

**= Show 3 key metrics in a row**

```python
st.download_button(
    "📥 Download Consolidated Order Summary",
    buf.getvalue(),
    file_name=f"{date_str}_{selected_vendor}_CONSOLIDATED_ORDER.xlsx"
)
```

**= Final download button with all vendor orders combined**

---

## Part 9: Welcome State (Lines 750+)

### What If User Hasn't Done Everything Yet?

```python
elif not selected_stores:
    st.warning("Please select at least one store in the sidebar to begin processing.")
elif not catalog_file:
    st.info("👋 **Welcome! Please upload the Southeast Catalog to begin.**")
```

**= Show helpful instructions for each scenario**

```python
st.markdown("""
1. **Login to Square Dashboard.**
2. **Go to Items → Item Library.**
3. **Filter by Vendor: Southeast Pet.**
4. **Click Actions → Export Library.**
5. **Select "Export items matching applied filters".**
6. **Upload the file here.**
""")
```

**= Step-by-step guide for exporting from Square**

---

## Data Flow Summary

Here's how data moves through the app:

```
┌─────────────────────────────────────────────────────────┐
│ User Actions (Sidebar)                                   │
│  1. Upload Catalog File                                 │
│  2. Select Vendor                                       │
│  3. Click "Load Rules from Google Sheets"              │
│  4. Select Stores                                       │
│  5. Adjust Lead Times & HQ Threshold                   │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │ Load Catalog (load_catalog)  │
        │ Read Excel file, clean SKUs  │
        └──────────┬───────────────────┘
                   │
        ┌──────────┴───────────────────┐
        │ Load Rules (load_rules...)    │
        │ Pull from Google Sheets      │
        └──────────┬───────────────────┘
                   │
                   ▼
        ┌──────────────────────────────┐
        │ Find HQ Allocation Conflicts │
        │ (get_allocation_candidates)  │
        └──────────┬───────────────────┘
                   │
        ┌──────────┴────────────────────────────┐
        │ User Allocates HQ Stock (if needed)   │
        └──────────┬────────────────────────────┘
                   │
                   ▼
    ┌──────────────────────────────────────────┐
    │ For Each Store:                          │
    │ 1. Calculate what needs ordering         │
    │ 2. Decide HQ vs Vendor                   │
    │ 3. Generate order tables                 │
    │ 4. Allow user edits                      │
    │ 5. Provide download buttons              │
    └──────────┬─────────────────────────────┘
               │
               ▼
    ┌──────────────────────────────────────────┐
    │ Consolidated Summary                     │
    │ Combine all store orders                 │
    │ Show totals & final download             │
    └──────────────────────────────────────────┘
```

---

## Key Concepts Explained

### What Is Caching?

```python
@st.cache_data
def load_catalog(file):
    ...
```

**Problem:** If we load the catalog every time the user interacts with the app, it's slow.

**Solution:** Load once, save the result in memory. If user uploads the same file again, just use the saved version.

**Note:** When the file changes, the cache automatically refreshes.

---

### What Is Session State?

```python
st.session_state["rules_matrix"] = rules_matrix
```

**Problem:** When a user does something (clicks a button, types in a field), Streamlit re-runs the entire script from top to bottom. Variables get reset.

**Solution:** Use `st.session_state` to save data that persists across button clicks and interactions within a single user's session.

**Example:**

1. User clicks "Load Rules" button
2. App loads and saves in `st.session_state`
3. User later changes the store selection
4. App re-runs, but the old rules are still in `st.session_state`, so we don't reload

---

### What Is Vectorization?

```python
data['Needs_Order'] = np.where(
    data['Order In Quantities'] == 1,
    (data['Current_Inv'] < data['Max']),
    (data['Current_Inv'] < data['Effective_Min'])
)
```

**Non-vectorized (slow):**

```python
for i in range(len(data)):
    if data.loc[i, 'Order In Quantities'] == 1:
        data.loc[i, 'Needs_Order'] = data.loc[i, 'Current_Inv'] < data.loc[i, 'Max']
    else:
        data.loc[i, 'Needs_Order'] = data.loc[i, 'Current_Inv'] < data.loc[i, 'Effective_Min']
```

**Vectorized (fast):**

```python
data['Needs_Order'] = np.where(...)  # All rows at once
```

**Why it matters:** With 5,000 SKUs, vectorized is 100x faster than looping.

---

### What Is a Lambda Function?

```python
data['SKU'] = data['SKU'].apply(clean_id)
```

Is shorthand for:

```python
data['SKU'] = data['SKU'].apply(lambda val: clean_id(val))
```

**What it means:** "For each value in the SKU column, call clean_id on it."

---

### What Is Merge / Join?

```python
data = pd.merge(store_inv, store_rules, on='SKU', how='left')
```

**Think of it like Excel VLOOKUP:**

**store_inv:**

```
SKU    Current_Inv
12345  30
12346  50
```

**store_rules:**

```
SKU    Min   Max
12345  10    100
12346  20    75
```

**After merge:**

```
SKU    Current_Inv  Min  Max
12345  30          10   100
12346  50          20   75
```

**How='left'** means: Keep all rows from the left table (store_inv), even if they don't match in store_rules.

---

## Troubleshooting Guide

### "No Sheet ID configured for vendor 'XYZ'"

**Problem:** You selected a vendor that's not in the `SHEET_IDS` dictionary.
**Fix:** Add the vendor to `SHEET_IDS`:

```python
SHEET_IDS = {
    'SE': '...',
    'Canine Caviar': '...',
    'New Vendor': '1234567890'  # Add this line
}
```

---

### "Unmatched SKUs found"

**Problem:** Some SKUs in the catalog don't have ordering rules.
**Fix:** Either:

1. Add the SKUs to the Google Sheets rules matrix, OR
2. These are old/test products — remove from catalog or ignore

---

### "Over-allocated by X units"

**Problem:** You allocated more HQ stock than available in the allocation UI.
**Fix:** Reduce allocations so the "Remaining" column shows 0 or positive.

---

### "TypeError: Cannot unpack non-iterable NoneType object"

**Problem:** Usually means the file upload or sheet loading failed.
**Fix:**

1. Check that you uploaded an Excel file (not CSV)
2. Check that the vendor sheet ID is correct and accessible
3. Try uploading the file again

---

## Summary

This app is essentially:

1. **Input:** User uploads a catalog, picks stores, picks a vendor
2. **Processing:**
   - Load ordering rules from Google Sheets
   - Calculate what each store needs
   - Decide whether to get from HQ or vendors
   - Handle conflicts (when HQ can't supply everyone)
3. **Output:**
   - Editable order tables per store
   - Downloadable Excel files
   - Consolidated summary across all stores

The magic is in the **clever calculations** that decide when to reorder, how much to order, and whether HQ or vendors are the better source.
