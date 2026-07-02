# Rebuilding the Southeast Inventory & Ordering App — Full Tutorial

This is a from-scratch, line-by-line walkthrough of `main.py`. If you lost
every past conversation and the codebase disappeared, this document alone
should let you rebuild the app and understand _why_ every piece exists.

---

## 1. What this app does (big picture)

It's a **Streamlit** web app used internally to generate purchase orders.

1. You upload a **catalog export** from Square (an Excel file) — every SKU
   the business carries from a given vendor, with current on-hand quantity
   at each of 11 stores plus HQ.
2. You load a **rules matrix** from Google Sheets for that vendor — for each
   SKU, it defines per-store `Min`/`Max` stocking levels, a `DNO`
   ("Do Not Order") flag, and an `Order In Quantities` (case pack size).
3. The app compares current inventory to the rules and calculates, per
   store, per SKU: _does this need to be reordered, and how many units?_
4. If HQ has stock, it suggests transferring from HQ instead of buying from
   the vendor — and if multiple stores want the same HQ stock and there
   isn't enough to go around, it gives you a UI to manually split
   ("allocate") HQ stock between stores.
5. It then produces downloadable Excel files: one HQ Transfer file per
   store, one Vendor Order file per store (split into Dry/Frozen), and one
   Consolidated Order file summing vendor orders across every selected
   store.

Everything reruns automatically because that's how Streamlit works: any
widget interaction (a button click, a number input change) re-executes the
whole script top to bottom, using `st.session_state` to remember values
across reruns.

---

## 2. Environment setup

### 2.1 Install dependencies

```bash
pip install streamlit pandas numpy gspread google-auth xlsxwriter openpyxl
```

- `streamlit` — the web app framework.
- `pandas` / `numpy` — data manipulation and vectorized math.
- `gspread` + `google-auth` — read the rules matrix directly out of Google
  Sheets.
- `xlsxwriter` — the Excel engine used when _writing_ `.xlsx` downloads
  (supports cell formatting, which `openpyxl` write-mode does less
  cleanly).
- `openpyxl` — needed by `pandas.read_excel` to _read_ `.xlsx` catalog
  uploads.

### 2.2 Google service account (for `load_rules_from_sheets`)

The app authenticates to Google Sheets with a **service account**, not a
user OAuth flow. You need:

1. A Google Cloud project with the Sheets API and Drive API enabled.
2. A service account, with a downloaded JSON key.
3. Each rules-matrix Google Sheet **shared** with that service account's
   email (found in the JSON key as `client_email`), at least Viewer access.
4. The JSON key contents pasted into Streamlit's secrets file:

`.streamlit/secrets.toml`

```toml
[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "your-bot@your-project.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

On Streamlit Community Cloud, this same TOML content goes into the app's
**Secrets** panel in the dashboard instead of a local file.

### 2.3 Run it

```bash
streamlit run main.py
```

---

## 3. Imports

```python
import streamlit as st
import pandas as pd
import io
import numpy as np
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
```

- `streamlit as st` — every UI element (`st.button`, `st.dataframe`, etc.)
- `pandas as pd` — the DataFrame is the core data structure for the whole
  app: one row per SKU, one column per attribute (inventory, min/max,
  cost...).
- `io` — used to build Excel files **in memory** (`io.BytesIO()`) so they
  can be handed to `st.download_button` without ever touching disk.
- `numpy as np` — vectorized `np.where`, `np.ceil`, `np.floor`, `np.maximum`
  for fast per-row math across the whole DataFrame at once (much faster
  than looping row by row).
- `datetime` — used once, to stamp filenames with today's date.
- `gspread` + `Credentials` — the Google Sheets client library and the
  auth helper for service-account credentials.

---

## 4. Configuration constants

### 4.1 `SCOPES`

```python
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
```

OAuth scopes requested by the service account: read/write Sheets access,
and Drive access (Drive scope is required because `gspread.open_by_key`
resolves the spreadsheet through the Drive API under the hood).

### 4.2 `SHEET_IDS`

```python
SHEET_IDS = {
    "Adored Beast": "1HwOxpAzI...",
    ...
    "SE": "1O6HWGeLgtdScnJ0_pQc8asaSj3-L4pP9vjCvvXa26vQ",
    ...
}
```

A hard-coded mapping of **vendor name → Google Sheet ID** (the long string
in a Sheet's URL between `/d/` and `/edit`). Each sheet is that vendor's
rules matrix. This dictionary also populates the vendor dropdown in the
sidebar — the keys are literally the dropdown options.

> **To add a new vendor:** create/duplicate a rules-matrix sheet, share it
> with the service account email, copy its Sheet ID from the URL, and add
> one `"Vendor Name": "sheet_id"` line here.

### 4.3 `store_map` and `inv_store_map`

```python
store_map = {
    'Current Quantity City Market: DTR': 'CM',
    'Current Quantity Crabtree Valley Mall': 'CVM',
    ...
}
inv_store_map = {v: k for k, v in store_map.items()}
```

- `store_map` maps the **exact column header text** used in the Square
  catalog export (the long human-readable store name, as Square names it)
  to the **short internal code** used everywhere else in the app (`CC`,
  `CM`, etc.).
- `inv_store_map` is the same dictionary flipped around (short code → long
  column name), built with a dict comprehension. It's the one actually used
  most often, because the rest of the app works in short codes (for the
  rules matrix column prefixes like `CC_Min`) but needs to look the right
  long column name up in the catalog DataFrame.

> **If Square renames a store or you open a new location:** add both the
> long name (however Square exports it) and its short code to `store_map`.
> Also add matching `{code}_DNO`, `{code}_Min`, `{code}_Max` columns to
> every vendor's rules-matrix Google Sheet.

### 4.4 `priority_stores`

```python
priority_stores = ['CC', 'CM', 'CVM', 'LB', 'SH']
```

The default pre-checked selection in the "Store Selection" multiselect —
just a convenience default, not a hard restriction. Any store in
`store_map` can be selected.

---

## 5. Helper functions

### 5.1 `clean_id(val)`

```python
def clean_id(val):
    if pd.isna(val):
        return ""
    return str(int(val)) if isinstance(val, float) and val.is_integer() else str(val)
```

Normalizes a SKU (or GTIN) value into a clean string:

- Blank/NaN cell → empty string.
- A float that's actually a whole number (Excel/Sheets often stores IDs
  like `12345` as `12345.0`) → converted through `int()` first, so it
  reads `"12345"` instead of `"12345.0"`.
- Anything else → `str(val)` as-is.

This matters because SKUs need to match **exactly** as strings when the
catalog and the rules matrix are merged later — a mismatch like `"12345"`
vs `"12345.0"` would silently produce zero matches.

### 5.2 `load_catalog(file)`

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

- `@st.cache_data` — Streamlit caches the return value keyed on the input
  arguments (here, the uploaded file's bytes). If you don't touch the
  upload widget, re-running the script (which happens on _every_ Streamlit
  interaction) reuses the cached DataFrame instead of re-parsing the Excel
  file every time.
- `pd.read_excel(file, header=1, dtype=dtype_dict)` — Square's export has
  one throwaway title row above the real header row, hence `header=1`
  (0-indexed: row 1 is the second row). `dtype=dtype_dict` forces `GTIN`
  and `SKU` to be read as strings immediately, so pandas never "helpfully"
  converts a barcode into scientific notation or drops a leading zero.
- `df.columns = df.columns.str.strip()` — removes accidental leading/
  trailing whitespace from column headers (a common Excel export artifact
  that would otherwise break every column lookup like `'Item Name'`).
- `df['SKU'] = df['SKU'].apply(clean_id)` — runs every SKU through the
  normalizer above.
- The `GTIN` block strips whitespace but otherwise leaves it as a string
  (GTIN/barcodes must never become numbers — leading zeros are
  significant).

### 5.3 `get_google_client()`

```python
@st.cache_resource
def get_google_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    return gspread.authorize(creds)
```

- `@st.cache_resource` — unlike `@st.cache_data` (which caches _data_ by
  value), this caches a _live object/connection_ once per app process, so
  you don't re-authenticate with Google on every rerun.
- Reads the service-account JSON out of `st.secrets["gcp_service_account"]`
  (populated from `secrets.toml`, see §2.2), builds `Credentials`, and
  authorizes a `gspread` client with them.

### 5.4 `load_rules_from_sheets(vendor)`

```python
@st.cache_data(ttl=3600)
def load_rules_from_sheets(vendor: str) -> pd.DataFrame:
    if vendor not in SHEET_IDS:
        raise ValueError(f"No Sheet ID configured for vendor '{vendor}'.")
    client = get_google_client()
    spreadsheet = client.open_by_key(SHEET_IDS[vendor])
    worksheet = spreadsheet.sheet1
    data = worksheet.get_all_records(value_render_option='UNFORMATTED_VALUE')
    df = pd.DataFrame(data)
    df.columns = df.columns.str.strip()
    df['SKU'] = df['SKU'].apply(clean_id)
```

- `@st.cache_data(ttl=3600)` — same value-caching as before, but expires
  after one hour, so the sheet is re-pulled periodically even if you never
  click the manual refresh button.
- Validates the vendor is a known key in `SHEET_IDS`.
- `client.open_by_key(...)` opens the spreadsheet by its ID; `.sheet1`
  grabs the first tab (the rules matrix is expected to live on tab 1 — the
  "Excluded SKUs" tab, if present, is a second tab and is **not** read
  here).
- `get_all_records(value_render_option='UNFORMATTED_VALUE')` returns each
  row as a `dict` keyed by header, with numbers/booleans returned as their
  raw underlying values rather than Google Sheets' _display_ formatting
  (e.g. you get `6` not `"6.00"`, and a checkbox comes back as `True`/
  `False`, not as a formatted string).
- Builds a DataFrame from those records, strips column-header whitespace,
  and cleans the `SKU` column exactly like the catalog loader does — this
  is what makes the later merge on `SKU` reliable.

```python
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
            if converted.notna().sum() > 0:
                df[col] = converted

    return df
```

This loop type-coerces every column except `SKU`:

- **Columns ending in `_DNO`** (e.g. `CC_DNO`, `SH_DNO` — one per store,
  meaning "Do Not Order at this store"): Google Sheets can hand back a
  checkbox cell as a native Python `bool`, as `0`/`1`, or as the literal
  text `"TRUE"`/`"FALSE"` depending on how the cell was formatted/typed in
  the sheet. The naive approach — `pd.to_numeric` then `.fillna(0).astype(bool)`
  — silently breaks: a text cell `"FALSE"` fails `to_numeric`, becomes
  `NaN`, `fillna(0)` turns it into `0`, and `.astype(bool)` on `0` is
  `False`... **but** a stray/malformed cell or a `"1.0"` text string could
  just as easily collapse the wrong way, and worse, mixed types across
  the column can make `NaN`-driven logic unpredictable in aggregate. The
  explicit `.map(...)` sidesteps all of that: any value whose _stripped,
  uppercased string form_ is one of `'TRUE'`, `'1'`, `'YES'`, `'1.0'` is
  `True`; anything else (including genuinely empty cells, since
  `pd.notna(x)` guards the `NaN` case) is `False`. No ambiguity, and the
  column always ends up as clean native `bool`.
- **Every other column** (e.g. `Order In Quantities`, `CC_Min`, `CC_Max`):
  attempt `pd.to_numeric(..., errors='coerce')`, which turns anything
  non-numeric into `NaN`. The `if converted.notna().sum() > 0:` guard means
  the column is only _replaced_ with the numeric version if at least one
  cell actually converted successfully — this protects genuinely
  text-only columns (like `Item Name`, if it ever showed up here) from
  being nuked into an all-`NaN` column just because none of its values
  happened to look like numbers.

---

## 6. Session state initialization

```python
def init_session_defaults():
    defaults = {
        "rules_vendor": None,
        "rules_matrix": None,
        "hq_allocations": {},
        "current_tab": 0,
        "allocations_submitted": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
```

`st.session_state` is Streamlit's per-browser-session dictionary that
survives across reruns (a normal Python variable would reset to its
initial value on every single interaction). `setdefault` only sets a key
if it doesn't already exist, so calling this function again on a later
rerun never clobbers values the user has already interacted with.

- `rules_vendor` / `rules_matrix` — remembers which vendor's rules are
  currently loaded and the DataFrame itself, so you don't need to re-fetch
  from Google Sheets on every rerun (only on vendor change or button
  click).
- `hq_allocations` — the nested `{sku: {store_code: qty}}` structure that
  stores manual HQ-stock splits (see §9).
- `current_tab` — declared but not actively read anywhere in the current
  version; a placeholder for a future feature.
- `allocations_submitted` — flips to `True` once the user pushes their HQ
  allocation choices, which reveals the Allocation Summary section.

This function is called once near the top of the script, **before**
anything else touches `st.session_state`, so every downstream read is
guaranteed to find a key already present.

---

## 7. Page setup

```python
st.set_page_config(page_title="Inventory & Ordering System", layout="wide")
init_session_defaults()
st.title("📦 Southeast Inventory & Ordering")
```

- `set_page_config` must be the first Streamlit command in the script (or
  Streamlit raises an error). `layout="wide"` uses the full browser width
  instead of a centered narrow column — needed because store tabs and
  allocation grids get wide.
- Initializes session state.
- Renders the page's main title.

---

## 8. Sidebar — inputs

```python
with st.sidebar:
    st.header("1. Upload Files")
    catalog_file = st.file_uploader(
        "Upload Southeast Catalog (.xlsx)", type=['xlsx'])
```

A file-upload widget restricted to `.xlsx`. Returns `None` until a file is
chosen; once chosen, returns a file-like object that `load_catalog()`
reads.

```python
    st.divider()
    st.header("2. Vendor")
    selected_vendor = st.selectbox(
        "Select vendor to load rules from Google Sheets:",
        options=["-- Select a Vendor --"] + list(SHEET_IDS.keys())
    )
```

A dropdown built from `SHEET_IDS`' keys, with a placeholder "unselected"
option prepended so the app can tell "nothing chosen yet" apart from a
real vendor.

```python
    if selected_vendor != st.session_state.get("rules_vendor") and selected_vendor != "-- Select a Vendor --":
        st.session_state.rules_matrix = None
        st.session_state.rules_vendor = None
        st.session_state.hq_allocations = {}
        st.session_state.allocations_submitted = False
```

**Vendor-change guard.** If the dropdown selection no longer matches the
vendor whose rules are currently cached in session state (and it isn't the
placeholder), that means the user just switched vendors — so every piece
of vendor-specific state is wiped: the stale rules matrix, the "which
vendor is loaded" flag, any HQ allocations (which reference SKUs from the
_old_ vendor and would be meaningless/dangerous applied to a new vendor's
SKUs), and the allocation-submitted flag. This forces the user to
explicitly reload rules for the new vendor rather than silently continuing
to compute orders against the wrong rules matrix.

```python
    load_rules_btn = st.button("📥 Load Rules from Google Sheets")
```

A plain button; `st.button` returns `True` only on the exact rerun
triggered by the click, `False` on every other rerun.

```python
    st.divider()
    st.header("3. Store Selection")
    selected_stores = st.multiselect(
        "Select stores:", options=list(store_map.values()), default=priority_stores
    )
```

Lets the user pick which store short-codes to process. Defaults to
`priority_stores`.

```python
    st.divider()
    st.header("4. HQ Threshold")
    hq_threshold = st.slider(
        "Suggest HQ Transfer if HQ Qty >", 0, 20, 6,
        help="Items with HQ stock exceeding this amount will be suggested for HQ transfer."
    )
```

A slider from 0–20, default 6. This is the cutoff used later: a SKU only
gets suggested as an HQ transfer if HQ's on-hand quantity is _strictly
greater than_ this number — the idea being "don't drain HQ down to a
sliver just to avoid a vendor order."

---

## 9. Loading the rules matrix

```python
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
```

Three-way branch, evaluated top to bottom, only one branch runs per rerun:

1. **No vendor picked yet** → just show an info message.
2. **The load button was just clicked** → `load_rules_from_sheets.clear()`
   forcibly evicts the `@st.cache_data(ttl=3600)` cache for that function,
   guaranteeing a _fresh_ pull from Google Sheets even if the hourly TTL
   hasn't expired (useful right after editing the sheet). Then it calls
   the loader inside a `st.spinner` (shows a loading spinner with that
   text while the network call runs), stores the result into session
   state, and shows a success/error message. Any exception (bad Sheet ID,
   network failure, missing `SKU` column, auth failure...) is caught and
   surfaced instead of crashing the app.
3. **Rules were already loaded for this exact vendor on a previous rerun**
   → just restore them from session state instead of hitting the network
   again. This is what makes every _other_ widget interaction (moving the
   HQ threshold slider, editing a data-editor cell, etc.) not re-trigger a
   Google Sheets fetch.

At the end of this block, `rules_matrix` is either `None` (nothing usable
loaded) or a DataFrame ready to use.

---

## 10. Main app — guard and setup

```python
if catalog_file and rules_matrix is not None and selected_stores:
    df_master = load_catalog(catalog_file)
```

The entire rest of the app (hundreds of lines) is gated behind having all
three prerequisites: a catalog file, a loaded rules matrix, and at least
one selected store. `df_master` is the full catalog DataFrame — one row
per SKU, with a column per store's `Current Quantity ...` plus
`Current Quantity HQ`, `GTIN`, `Item Name`, `Default Unit Cost`, `SKU`.

```python
    catalog_skus = set(df_master['SKU'].unique())
    rules_matrix = rules_matrix[rules_matrix['SKU'].isin(catalog_skus)].copy()
```

Restricts the rules matrix down to only the SKUs that actually appear in
_this_ catalog upload — a rules sheet can (and does) contain historical
SKUs no longer in the current Square export; there's no reason to carry
those rows through the rest of the computation.

```python
    invalid_oiq = rules_matrix[rules_matrix['Order In Quantities'] <= 0]
    if not invalid_oiq.empty:
        st.error(
            f"❌ Invalid Order In Quantities found (must be > 0):\n{invalid_oiq[['SKU', 'Order In Quantities']].to_string()}")
        st.stop()
```

A data-quality guard: `Order In Quantities` (the case pack size) is used
as a **divisor** later (`Units_Needed_To_Max / Order In Quantities`). A
zero or negative value there would cause a divide-by-zero or nonsense
result. If any row is invalid, the app prints exactly which SKUs are bad
and calls `st.stop()`, which halts script execution immediately — nothing
below this point runs on this rerun.

```python
    hq_col = 'Current Quantity HQ'
    date_str = datetime.now().strftime("%Y-%m-%d")

    if hq_col not in df_master.columns:
        st.error(f"❌ Missing column: '{hq_col}'")
        st.stop()
```

`hq_col` is the fixed name of HQ's inventory column in the catalog.
`date_str` is today's date as `YYYY-MM-DD`, reused in every export
filename. If the catalog upload is somehow missing the HQ column entirely
(wrong export filter in Square, wrong file), stop with a clear error
rather than crashing deeper in the code with a cryptic `KeyError`.

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
            item_name = df_master[df_master['SKU'] == sku]['Item Name'].iloc[0] if len(
                df_master[df_master['SKU'] == sku]) > 0 else "Unknown"
            print(f"  - {sku}: {item_name}")
        print(f"\nTotal unmatched: {len(unmatched_skus)}\n")
```

Computes how many catalog SKUs successfully matched a rules-matrix row
(`matched`) versus the catalog's total SKU count (`total`), shows that as
a caption in the UI, and — for any catalog SKU with **no** matching rules
row at all — logs each one's SKU + item name to the server console
(`print`, visible in the terminal/logs, not the browser). These unmatched
SKUs are typically discontinued items that were deliberately removed from
the rules matrix (tracked in the "Excluded SKUs" sheet tab — see §16),
but the app doesn't cross-check against that tab yet, so this console log
is currently the only visibility into which SKUs fell out.

---

## 11. `compute_store_order` — the core calculation

This is the single most important function in the app: everything else
just calls it and displays/exports the result. It's defined _inside_ the
`if catalog_file and ...` block (a nested function), which is a deliberate
closure trick — it captures `df_master`'s column names validated above
without needing to re-pass constants like `hq_col`.

```python
    def compute_store_order(store_code, df_master, rules_matrix, hq_col,
                            hq_threshold, allocation_candidates, hq_allocations):
```

Takes: which store to compute for, the catalog, the (already
catalog-filtered) rules matrix, the HQ column name, the HQ threshold from
the sidebar slider, the dict of SKUs with cross-store HQ conflicts (see
§12), and the current manual allocation choices.

### 11.1 Merge catalog + rules for one store

```python
        long_name = inv_store_map[store_code]

        lookup_cols = ['SKU', 'Order In Quantities',
                       f'{store_code}_DNO', f'{store_code}_Min', f'{store_code}_Max']
        valid_lookup = [c for c in lookup_cols if c in rules_matrix.columns]
        store_rules = rules_matrix[valid_lookup].copy().rename(columns={
            f'{store_code}_DNO': 'DNO',
            f'{store_code}_Min': 'Min',
            f'{store_code}_Max': 'Max'
        })
```

Looks up the store's long column name. Builds the list of rules columns
relevant to _this specific store_ — the rules matrix has per-store
columns named like `CC_DNO`, `CC_Min`, `CC_Max`, `CM_DNO`, `CM_Min`, etc.,
so this pulls out just the current store's triplet (plus the
store-agnostic `SKU` and `Order In Quantities`) and renames them to
generic `DNO`/`Min`/`Max` so the rest of the function doesn't need to know
which store it's working on. `valid_lookup` guards against a column being
absent entirely (e.g. a brand-new store not yet added to the rules sheet)
rather than throwing a `KeyError`.

```python
        extra_cols = ['SKU', 'GTIN', 'Item Name',
                      'Default Unit Cost', long_name, hq_col]
        available_cols = [c for c in extra_cols if c in df_master.columns]
        store_inv = df_master[available_cols].copy().rename(
            columns={long_name: 'Current_Inv', hq_col: 'HQ_Qty'}
        )
```

Pulls the relevant catalog columns for this store — SKU, GTIN, item name,
unit cost, this store's on-hand quantity column, and HQ's on-hand
quantity column — and renames the store-specific column to the generic
`Current_Inv` and HQ's column to `HQ_Qty`.

```python
        data = pd.merge(store_inv, store_rules, on='SKU', how='left')
        data = data.fillna({
            'DNO': 0, 'Order In Quantities': 1, 'Min': 0,
            'Max': 0, 'Current_Inv': 0, 'HQ_Qty': 0, 'Default Unit Cost': 0
        })
        data['DNO'] = data['DNO'].astype(bool)
```

Left-joins catalog rows to rules rows on `SKU`. `how='left'` means every
catalog SKU survives even if it has no matching rule (those unmatched SKUs
from §10). `fillna(...)` gives sane defaults to any resulting `NaN`s from
the unmatched rows: no rule found → treat as not-do-not-order (`DNO=0`), a
safe case pack of `1`, zero `Min`/`Max` (so it never triggers an order —
see next step), and zero for any missing numeric inventory/cost value.
`DNO` is cast to proper boolean afterward (fillna with `0` produces a
float `0.0`/`1.0` column, not bool).

### 11.2 Decide which rows need ordering

```python
        data['Effective_Min'] = data['Min']
        data['Needs_Order'] = np.where(
            data['Order In Quantities'] == 1,
            (data['Current_Inv'] < data['Max']),
            (data['Current_Inv'] < data['Effective_Min'])
        )
        data['Needs_Order'] = data['Needs_Order'] & (data['DNO'] == False)
```

`Effective_Min` is just `Min` aliased (kept as a separate name for
readability further down, and so the understock safety-net logic later
reads clearly). The reorder trigger has **two different rules depending
on case pack size**:

- If `Order In Quantities == 1` (item is orderable as a single unit, no
  case-pack constraint) → reorder whenever current stock is below `Max`
  (i.e. top off to `Max` any time you're not already full).
- Otherwise (item comes in case packs > 1) → only reorder when current
  stock has actually dropped _below `Min`_ — you don't want to trigger a
  full-case reorder just because you're one unit under `Max`; you wait
  until you're genuinely low.

Then `DNO` (Do Not Order) rows are forced to `False` regardless of the
above — a manual "never auto-order this SKU at this store" override.

```python
        data['Units_Needed_To_Max'] = np.where(
            data['Needs_Order'],
            np.maximum(data['Max'] - data['Current_Inv'], 0),
            0
        )
```

For rows that need ordering, the raw unit shortfall is `Max - Current_Inv`
(clamped to never go negative via `np.maximum(..., 0)` — a defensive
guard in case of weird data). Rows that don't need ordering get `0`.

### 11.3 Round the unit shortfall up to whole cases

```python
        raw_cases = data['Units_Needed_To_Max'] / data['Order In Quantities']
        rounded_cases = np.floor(raw_cases + 0.5)  # round-half-up
        rounded_cases = np.where(
            (data['Units_Needed_To_Max'] > 0) & (rounded_cases < 1),
            1, rounded_cases
        )
        data['Total_Units_Needed'] = rounded_cases * \
            data['Order In Quantities']
```

You can't order a fraction of a case — this converts the raw unit
shortfall into whole cases.

- `raw_cases` — how many cases the raw shortfall represents, as a
  (possibly fractional) number.
- `np.floor(raw_cases + 0.5)` — the classic **round-half-up** trick.
  Adding `0.5` then flooring rounds `2.4 → 2`, `2.5 → 3`, `2.6 → 3`. This
  intentionally replaced an earlier "always round up" (`np.ceil`) approach:
  ceiling would round `2.01` cases up to `3`, over-ordering; round-half-up
  only rounds up once you're genuinely closer to the next case.
- The next `np.where` is a **floor of 1 case**: if there _was_ a real
  shortfall (`Units_Needed_To_Max > 0`) but round-half-up rounded it all
  the way down to `0` cases (e.g. needing 2 units at a 12-pack — `2/12 =
0.167`, rounds to `0`), force it up to `1` case anyway. An order was
  triggered; ordering _zero_ would silently defeat the whole reorder
  logic.
- `Total_Units_Needed` — the final whole-case unit quantity: rounded cases
  × case size.

### 11.4 Understock safety net

```python
        would_understock = data['Needs_Order'] & (
            (data['Current_Inv'] + data['Total_Units_Needed']
             ) < data['Effective_Min']
        )
        data['Total_Units_Needed'] = np.where(
            would_understock,
            data['Total_Units_Needed'] + data['Order In Quantities'],
            data['Total_Units_Needed']
        )
```

Round-half-up can occasionally round **down** to the _nearest_ case even
though that lands you below `Min` once the order arrives — for example a
narrow `Min=10`/`Max=11` window on a case pack of 12: any triggered order
rounds down to a single case that overshoots `Max`, so this particular
example wouldn't trip it, but tighter combinations of `Min`/`Max` relative
to case size can. This block explicitly checks: for any row that needed an
order, would `Current_Inv + Total_Units_Needed` (i.e. stock _after_ the
order arrives) still land below `Effective_Min`? If so, bump the order up
by exactly one more case. This is a deliberate correctness guarantee: an
order is never allowed to leave a store below its stated minimum. It's
especially important given tight Min/Max windows are an intentional
business choice for slow-moving SKUs kept in stock only for new
customers — those SKUs must never be shorted by a rounding artifact.

### 11.5 HQ allocation awareness

```python
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
```

- `Allocated_HQ` — for each row, look up whether the user manually
  allocated any HQ stock to _this_ store for _this_ SKU (from the nested
  `hq_allocations` dict — see §9/§12). Defaults to `0` if nothing was
  allocated.
- `Is_Allocation_Candidate` — flags whether this SKU is one where store
  demand exceeds HQ supply across the whole selected-store set (computed
  separately in `get_allocation_candidates`, §12) — meaning it _requires_
  manual allocation rather than automatic HQ transfer.
- `Suggested_HQ_Qty` — the actual HQ transfer suggestion, nested logic:
  - If there's a real need (`Total_Units_Needed > 0`) **and** the user
    manually allocated some HQ stock to this store for this SKU → use that
    manual allocation number, full stop (manual choice always wins).
  - Otherwise, if there's a real need **and** HQ has more than the
    threshold on hand **and** this SKU is _not_ a contested
    allocation-candidate SKU (i.e. no cross-store conflict, so it's safe
    to auto-suggest) → suggest transferring the _entire_ need from HQ.
  - Otherwise → `0` (no HQ suggestion; the store will need to order the
    full amount from the vendor, subject to further edits in the UI).

### 11.6 Vendor remainder

```python
        data['Vendor_Units'] = (
            data['Total_Units_Needed'] - data['Suggested_HQ_Qty']
        ).clip(lower=0)
        data['Vendor_Cases'] = np.ceil(
            data['Vendor_Units'] / data['Order In Quantities']
        )

        return data
```

Whatever isn't covered by the HQ suggestion has to come from the vendor:
`Vendor_Units = Total_Units_Needed - Suggested_HQ_Qty`, clamped to never
go negative. `Vendor_Cases` converts that back into whole cases — here
`np.ceil` (always round _up_) is intentionally used rather than
round-half-up, because at this point you're computing an actual purchase
order quantity from a partial remainder (after HQ covers part of the
need), and under-ordering the remainder would leave the store short; you
always want at least enough cases to cover the full leftover unit amount.

The function returns the fully computed `data` DataFrame — this return
value is what every downstream section of the app (allocation candidate
detection, the per-store tabs, the consolidated summary) consumes.

---

## 12. `get_allocation_candidates` — finding HQ conflicts

```python
    def get_allocation_candidates(df_master, rules_matrix, hq_col,
                                  selected_stores, hq_threshold):
        store_needs_list = []

        for store_code in selected_stores:
            long_name = inv_store_map[store_code]
            if long_name not in df_master.columns:
                continue

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
```

Runs `compute_store_order` for **every selected store**, but crucially
with `allocation_candidates={}` and `hq_allocations={}` — a "raw demand"
pass that ignores any HQ suggestion/allocation logic entirely, so it
reflects pure need before any HQ stock has been mentally spoken for. For
each store, keeps only the rows that actually need ordering, tags each row
with which store it came from, and collects them into a list.

Note: this function is called once per store _inside_ this loop, and it's
called again later per store for the actual tabs — that's `O(stores)`
duplicate work, accepted as a simplicity/correctness tradeoff (correctness
via `get_allocation_candidates` taking explicit arguments — see the note
below — was prioritized over micro-optimizing away the recomputation).

```python
        if not store_needs_list:
            return {}

        combined = pd.concat(store_needs_list, ignore_index=True)

        sku_groups = combined.groupby('SKU').agg({
            'Units_Needed': 'sum',
            'HQ_Qty': 'first',
            'Store': 'count'
        }).rename(columns={'Store': 'Store_Count'})
```

Stacks every store's need-rows into one DataFrame, then groups by SKU:
total units needed _summed across all stores_ that need it, HQ's on-hand
quantity (same for every row of a given SKU, so `'first'` is fine), and a
count of how many stores need it.

```python
        conflicts = sku_groups[
            (sku_groups['Units_Needed'] > sku_groups['HQ_Qty']) &
            (sku_groups['HQ_Qty'] > hq_threshold)
        ]
```

A SKU is a genuine **conflict** — requiring a human to decide who gets
what — only if: total combined demand across stores exceeds what HQ
actually has (`Units_Needed > HQ_Qty`), **and** HQ has more than the
threshold in the first place (`HQ_Qty > hq_threshold` — if HQ barely has
any stock, there's no point offering a transfer at all; every store just
orders from the vendor as normal).

```python
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
```

For each conflicting SKU, builds a rich info dict used entirely by the
allocation UI (§13):

- `demand_map` — per-store `{demand, current_inv}` so the UI can show "Has:
  X | Needs: Y" beside each store's allocation input.
- `stores` — the list of stores that actually need this SKU (so the UI
  only shows inputs for relevant stores, not every selected store).
- `hq_qty` — total HQ stock available to split.
- `oiq` — case pack size, used as the input's step size.

> **Why "explicit arguments" matters:** this function takes
> `df_master`, `rules_matrix`, `selected_stores`, `hq_threshold` as real
> parameters rather than silently reading global/session variables. That
> means if it's ever wrapped in `@st.cache_data`, Streamlit's cache key is
> based on the _actual content_ passed in — changing the HQ threshold
> slider or catalog produces a different cache key and a fresh
> recomputation, instead of silently returning a stale cached result keyed
> on the wrong (or no) inputs.

---

## 13. The HQ Allocation UI

Only rendered `if allocation_candidates:` — i.e. only when at least one
SKU has a genuine cross-store HQ conflict.

```python
    if allocation_candidates:
        st.divider()
        st.subheader("⚙️ HQ Allocation (Insufficient Stock)")
        st.caption(
            "Items below have more demand than HQ can supply. Allocate HQ qty to stores; unallocated stores will order from vendors.")
```

Section header + explanation.

```python
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
                'SKU': sku, 'Item Name': item_name,
                'HQ Available': hq_available, 'Total Demand': int(total_demand),
                'Shortage': int(shortage),
                'Stores Needing': ', '.join(info['stores'])
            })

        alloc_df = pd.DataFrame(allocation_data)
        st.dataframe(alloc_df, width='stretch', hide_index=True)
```

Builds and displays a **read-only overview table**: one row per
conflicting SKU, showing item name, HQ's available quantity, total demand
summed across stores, the resulting shortage, and which stores are asking
for it. Purely informational — the actual input widgets come next.

```python
        if "hq_allocations" not in st.session_state:
            st.session_state.hq_allocations = {}
        for sku in allocation_candidates:
            if sku not in st.session_state.hq_allocations:
                st.session_state.hq_allocations[sku] = {}
```

Defensive initialization: guarantees every candidate SKU has at least an
empty dict ready in `st.session_state.hq_allocations`, even the very first
time it's encountered.

```python
        st.write("**Allocate HQ Qty by Store:**")
        st.info(
            "👆 \"Remaining\" updates live as you type. Once everything looks "
            "right, click **Push Allocations** to apply it to the store tabs below.")
```

### 13.1 `@st.fragment` for live updates

```python
        @st.fragment
        def render_allocation_inputs():
            ...
        render_allocation_inputs()
```

`st.fragment` is a Streamlit decorator that turns a function into an
independently-rerunning unit: interacting with a widget **inside** the
fragment only reruns the fragment's code, not the entire script from the
top. This is a deliberate performance/UX choice — without it, typing into
one allocation number input would re-run the _entire_ app: reload the
catalog handling, recompute every store tab, rebuild every Excel buffer,
etc., on every keystroke. Wrapping just the allocation-input rendering in
a fragment means "Remaining" recalculates live as you adjust numbers
without that overhead, and without needing an explicit form-submit click
just to see updated math.

(Earlier iterations of this app used `st.form` here instead — batching all
inputs and requiring an explicit Submit before anything recalculated. The
fragment approach was adopted specifically so "Remaining" feels live; the
tradeoff, discussed and deliberately accepted, is that a full-script rerun
is still needed afterward via `st.rerun()` to propagate the final
allocation into the store tabs, which live outside the fragment.)

### 13.2 Rendering each conflicting SKU's inputs

```python
            for sku in sorted(allocation_candidates.keys()):
                info = allocation_candidates[sku]
                item_name = ...
                hq_available = int(info['hq_qty'])
                oiq = int(info['oiq'])
                demand_map = info.get('demand_map', {})

                st.markdown(f"**{sku}** — {item_name} (Case Pack: {oiq})")
```

For each conflicting SKU (alphabetically sorted for a stable order), shows
a bolded header line with the SKU, item name, and case pack size for
context.

```python
                relevant_stores = [
                    s for s in selected_stores if s in info['stores']]
                cards_per_row = 4

                total_allocated = 0
                for row_start in range(0, len(relevant_stores), cards_per_row):
                    row_stores = relevant_stores[row_start:row_start + cards_per_row]
                    row_cols = st.columns(cards_per_row)
                    for col, store_code in zip(row_cols, row_stores):
```

Only stores that actually need this SKU (`relevant_stores`) get an input —
no point cluttering the UI with a store that isn't in the conflict.
`cards_per_row = 4` wraps the inputs into rows of (at most) 4 columns each
(handles SKUs needed by more than 4 stores gracefully, e.g. all 11).

```python
                        with col:
                            if store_code not in st.session_state.hq_allocations[sku]:
                                st.session_state.hq_allocations[sku][store_code] = 0

                            store_demand_info = demand_map.get(store_code, {})
                            current_inv = int(store_demand_info.get('current_inv', 0))
                            demand = int(store_demand_info.get('demand', 0))

                            max_alloc = max(min(int(hq_available), demand), 0)

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
```

For each store's input:

- Ensures a `0` default exists in the nested session-state dict.
- Looks up this store's actual demand and current inventory for this SKU.
- `max_alloc = max(min(hq_available, demand), 0)` — the input's ceiling is
  the **smaller** of (a) how much HQ has overall, and (b) how much _this
  particular store_ actually needs. This deliberately prevents allocating
  more stock to a store than it's asking for, even if HQ has plenty left
  over — surplus HQ stock beyond what's needed should stay at HQ, not be
  force-pushed to whichever store's input you touch first.
- If a previously-stored allocation value now exceeds a freshly
  recalculated `max_alloc` (e.g. because another store's allocation
  changed and tightened the ceiling), it's clamped down immediately —
  otherwise Streamlit would raise an error passing `value > max_value`
  into `st.number_input`.
- `st.number_input(..., step=oiq, ...)` — the up/down stepper moves in
  whole-case increments, matching how the store would actually receive
  stock.
- `width="stretch"` — the widget fills its column rather than a fixed
  pixel width, so it doesn't leave odd gaps when columns resize.
- Writes the (possibly user-changed) value back into session state and
  accumulates a running per-SKU total.

```python
                            st.markdown(
                                f"<div style='font-size:14px; width:100%; "
                                f"margin-top:-6px;'>Has: <b>{current_inv}</b>"
                                f" &nbsp;|&nbsp; Needs: <b>{demand}</b></div>",
                                unsafe_allow_html=True
                            )
```

A small raw-HTML caption directly under each input showing that store's
current on-hand and demand, for context while deciding how much to
allocate. `unsafe_allow_html=True` is required because Streamlit escapes
HTML in `st.markdown` by default; this is safe here because the content is
entirely built from already-validated numeric values, not arbitrary user
or external input.

```python
                    if row_start + cards_per_row < len(relevant_stores):
                        st.markdown(
                            "<div style='margin-top:14px;'></div>", unsafe_allow_html=True)
```

Adds a little vertical breathing room between wrapped rows, only when
there _is_ another row coming (avoids a trailing gap after the last row).

```python
                remaining = hq_available - total_allocated
                rem_col = st.columns([3, 1])[1]
                with rem_col:
                    st.metric(
                        "Remaining", remaining,
                        delta=f"of {hq_available}",
                        delta_color="inverse" if remaining >= 0 else "off"
                    )

                if remaining < 0:
                    st.error(
                        f"⚠️ Over-allocated by {abs(remaining)} units for SKU {sku}")

                st.divider()
```

After all of this SKU's store inputs, shows a `st.metric` "Remaining"
counter (`hq_available - total_allocated`), right-aligned via a `[3, 1]`
column split. `delta_color="inverse"` colors the delta red when positive
and green when negative for _this specific metric semantics_
(`"inverse"` just flips Streamlit's default green-is-up coloring — here
it's used so a _large remaining amount_ doesn't read as alarmingly red).
If the store inputs somehow still sum past `hq_available` (shouldn't
normally happen given the `max_alloc` clamp, but is a defensive
double-check), shows an explicit error. A divider closes out this SKU's
block before starting the next one.

### 13.3 Push button and over-allocation guard

```python
            over_allocated_skus = []
            for sku in sorted(allocation_candidates.keys()):
                info = allocation_candidates[sku]
                hq_available = int(info['hq_qty'])
                total_allocated = sum(
                    st.session_state.hq_allocations.get(sku, {}).get(store_code, 0)
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

            pushed = st.button(
                "🚀 Push Allocations", width="stretch",
                disabled=bool(over_allocated_skus)
            )
            if pushed and not over_allocated_skus:
                st.session_state.allocations_submitted = True
                st.rerun()
```

A second, independent re-check across _all_ candidate SKUs (not just the
one currently being rendered) for any over-allocation, building a list of
offending SKUs. If any exist, shows a consolidated error message and
**disables** the Push button (`disabled=bool(over_allocated_skus)`). This
disabling is safe specifically _because_ this all lives inside an
`@st.fragment` — since the fragment reruns on every input change, the
disabled state is always freshly recalculated; there's no risk of a stuck
button reflecting stale data (which was a real risk with the previous
`st.form`-based version, since a form only recalculates on submit).

When actually pushed (and nothing is over-allocated): flips
`allocations_submitted` to `True`, then calls `st.rerun()` — an explicit
**full-script rerun** (its default scope, as opposed to the fragment's
local rerun) so that the store tabs and consolidated summary below, which
live _outside_ this fragment and therefore wouldn't otherwise see the new
allocation values, pick them up immediately.

---

## 14. Allocation Summary (post-push)

```python
        if st.session_state.get("allocations_submitted"):
            st.divider()
            st.subheader("📋 Allocation Summary")

            summary_rows = []
            any_unassigned = False

            for sku in sorted(allocation_candidates.keys()):
                info = allocation_candidates[sku]
                hq_available = int(info['hq_qty'])
                allocated_by_store = {
                    store_code: st.session_state.hq_allocations.get(sku, {}).get(store_code, 0)
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
                    'SKU': sku, 'HQ Available': hq_available,
                    'Total Allocated': total_allocated, 'Unassigned': unassigned,
                    'Stores Getting 0 (→ Full Vendor Order)': ', '.join(skipped_stores) if skipped_stores else '—'
                })

            summary_df = pd.DataFrame(summary_rows)
            st.dataframe(summary_df, width='stretch', hide_index=True)
```

Once allocations have been pushed at least once, builds a summary table:
per SKU, how much HQ stock is available, how much was actually allocated,
how much is left unassigned, and which needing stores got _zero_
allocation (meaning they'll fall through to a full vendor order for that
SKU, per §11.5's `Suggested_HQ_Qty` logic).

```python
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
```

An explicit nudge: if any HQ stock is sitting unassigned, warn the user
before they go download files, since that means some stores will place a
vendor order for stock HQ could have covered — nothing about this is
silent or automatic.

---

## 15. Per-store tabs

```python
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
```

`st.tabs` creates one clickable tab per selected store code. Inside each
tab, `compute_store_order` is called **again** — this time with the real
`allocation_candidates` and the live `hq_allocations` from session state,
so `Suggested_HQ_Qty` reflects any manual allocations actually pushed.

### 15.1 HQ Transfer section

```python
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
```

Filters `data` down to just the rows that have a positive HQ suggestion,
picks the columns relevant to a human reviewing a transfer list, and
renders it as an **editable** table (`st.data_editor`). `num_rows="dynamic"`
lets the user delete rows entirely (e.g. "actually don't transfer this
one, I'll vendor-order it instead") — deleting a row here effectively
zeroes it out for the vendor-remainder calculation below, since the
remainder math is keyed by `ed_hq`'s SKUs, not the original `data`. The
`key=f"hq_ed_{short_name}"` gives each store's editor its own isolated
state, since `st.data_editor` widgets need unique keys to not collide
across tabs.

```python
                if not ed_hq.empty:
                    ed_hq_with_cost = ed_hq.merge(
                        data[['SKU', 'Default Unit Cost']], on='SKU', how='left'
                    )
                    hq_cost = (
                        ed_hq_with_cost['Transfer_Qty'] * ed_hq_with_cost['Default Unit Cost']).sum()
                    st.metric("🏭 HQ Transfer Cost", f"${hq_cost:,.2f}")
```

Re-joins unit cost back onto the (possibly user-edited) transfer table and
shows the total dollar value of the HQ transfer as a metric.

```python
                hq_final_map = ed_hq.set_index('SKU')['Transfer_Qty'].to_dict()
                data['Final_HQ_Qty'] = data['SKU'].map(
                    lambda x: hq_final_map.get(x, 0))
                data['Vendor_Units'] = (
                    data['Total_Units_Needed'] - data['Final_HQ_Qty']).clip(lower=0)
                data['Vendor_Cases'] = np.ceil(
                    data['Vendor_Units'] / data['Order In Quantities']
                )
```

**This is the key link between the editable HQ table and the vendor
order.** It builds a `SKU → Transfer_Qty` lookup straight from whatever
the user currently has in the editor (`ed_hq`, post-edit — including any
deleted rows, which simply won't be in this map and thus default to `0`
via `.get(x, 0)`), maps that onto `data` as `Final_HQ_Qty`, and
**recomputes** `Vendor_Units`/`Vendor_Cases` against that final, possibly
user-adjusted number rather than the original `Suggested_HQ_Qty`. This is
what makes "delete a row or set Qty to 0 to move it to the Vendor Order"
(the caption above) actually true — editing the HQ table live shifts the
remainder into the vendor order table below.

```python
                if not ed_hq.empty:
                    st.metric("Total Transfer Units", f"{int(ed_hq['Transfer_Qty'].sum())}")
                    buf_hq = io.BytesIO()
                    with pd.ExcelWriter(buf_hq, engine='xlsxwriter') as writer:
                        workbook = writer.book
                        worksheet = workbook.add_worksheet('HQ_Transfer')
                        writer.sheets['HQ_Transfer'] = worksheet
```

Starts building the downloadable HQ Transfer Excel file for this store.
`io.BytesIO()` is an in-memory binary buffer — the file is built entirely
in RAM, never written to disk, then handed straight to a download button.
`pd.ExcelWriter(..., engine='xlsxwriter')` opens that buffer as an Excel
workbook using the `xlsxwriter` engine specifically because it supports
rich cell formatting (fonts, borders, colors) that this section relies on.
A worksheet named `'HQ_Transfer'` is added manually (rather than via
`df.to_excel`) because the layout needs a custom title row above the
normal header row.

```python
                        store_header_fmt = workbook.add_format({
                            'bold': True, 'font_size': 14, 'align': 'left', 'valign': 'vcenter',
                        })
                        col_header_fmt = workbook.add_format({
                            'bold': True, 'bg_color': '#D9E1F2', 'border': 1,
                            'align': 'center', 'valign': 'vcenter',
                        })
                        cell_fmt = workbook.add_format({'border': 1, 'valign': 'vcenter'})
                        text_fmt = workbook.add_format({'num_format': '@', 'border': 1, 'valign': 'vcenter'})
```

Four reusable cell format objects: a large bold format for the store-name
title row, a bold-with-light-blue-background-and-border format for column
headers, a plain bordered format for ordinary data cells, and a
bordered-and-_text-formatted_ (`'num_format': '@'`) format specifically
for the GTIN column — forcing Excel to treat GTIN values as text so it
never auto-converts a long barcode into scientific notation or strips
leading zeros, exactly mirroring the string-preservation logic already
applied when the catalog was first loaded (§5.2).

```python
                        store_display_name = inv_store_map.get(
                            short_name, short_name).replace('Current Quantity ', '')
                        worksheet.write(
                            0, 0, f"HQ Transfer — {store_display_name}", store_header_fmt)
                        worksheet.set_row(0, 22)
```

Row 0 (the very first row of the sheet) gets a human-readable title like
"HQ Transfer — Crescent Commons" (stripping the `"Current Quantity "`
prefix off the long store-map name for display purposes), styled with the
bold large format, with the row height bumped to 22 so it doesn't look
cramped.

```python
                        for col_idx, col_name in enumerate(ed_hq.columns):
                            worksheet.write(1, col_idx, col_name, col_header_fmt)
```

Row 1 gets the actual column headers (`SKU`, `GTIN`, `Item Name`,
`Transfer_Qty`, `Current_Inv`, `HQ_Qty` — whatever `ed_hq`'s columns
currently are), styled with the blue header format.

```python
                        gtin_col_idx = list(ed_hq.columns).index(
                            'GTIN') if 'GTIN' in ed_hq.columns else None
                        for row_idx, row in enumerate(ed_hq.itertuples(index=False), start=2):
                            for col_idx, value in enumerate(row):
                                fmt = text_fmt if col_idx == gtin_col_idx else cell_fmt
                                worksheet.write(row_idx, col_idx, value, fmt)
```

Finds which column index is `GTIN` (so it can be given the text format
instead of the plain one), then writes every data row starting at row
index 2 (below the title and header rows). `itertuples(index=False)`
iterates rows as lightweight tuples (faster than `.iterrows()`, and
`index=False` skips including the DataFrame's row index as a spurious
first value).

```python
                        worksheet.set_column('A:A', 12)   # SKU
                        worksheet.set_column('B:B', 20)   # GTIN
                        worksheet.set_column('C:C', 40)   # Item Name
                        worksheet.set_column('D:F', 14)   # Qty columns
```

Explicit column widths so the exported file is readable immediately
without the recipient having to manually widen every column.

```python
                    st.download_button(f"📥 Download HQ Transfer", buf_hq.getvalue(),
                                       file_name=f"{short_name}_{date_str}_HQ_{selected_vendor}.xlsx",
                                       key=f"dl_hq_{short_name}")
```

`with pd.ExcelWriter(...) as writer:` closes automatically at the end of
the `with` block, finalizing the workbook into `buf_hq`. `buf_hq.getvalue()`
extracts the raw bytes, handed to `st.download_button`. The filename
pattern is `{store_code}_{date}_HQ_{vendor}.xlsx` — **store code leads**,
per the filename-restructuring convention used throughout this app, so
files sort/group by store when dropped into a folder together, and no
emoji ends up embedded in a filename (which can cause encoding issues on
some systems).

### 15.2 Vendor Order section

```python
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
```

Filters `data` down to rows that still need a vendor order (after the HQ
editor recalculation above), selects the relevant columns, and renames
several to more human-friendly display labels.

```python
                if not order_summary.empty:
                    frozen_mask = order_summary['Item Name'].str.startswith(
                        'FRZN', na=False)

                    for label, file_label, df_type in [
                        ("📦 Dry Order", "Dry", order_summary[~frozen_mask]),
                        ("❄️ Frozen Order", "Frozen", order_summary[frozen_mask])
                    ]:
```

Splits the vendor order into two sub-orders — Dry and Frozen — based on
whether the item name starts with the literal prefix `"FRZN"` (a naming
convention baked into how frozen SKUs are labeled in the catalog).
`na=False` treats any missing/`NaN` item name as "not frozen" rather than
raising. `label` is the emoji-decorated on-screen heading; `file_label` is
the clean plain-string version (`"Dry"` / `"Frozen"`) used in the actual
downloaded filename — this split exists specifically so exported
filenames stay clean strings without emoji, while the in-app UI can still
show the friendlier emoji heading.

```python
                        st.markdown(f"#### {label}")
                        if not df_type.empty:
                            ed_df = st.data_editor(df_type, use_container_width=True,
                                                   hide_index=True, num_rows="dynamic",
                                                   key=f"vend_{label}_{short_name}")
                            cost = (ed_df['Total Units'] *
                                    ed_df['Default Unit Cost']).sum()
                            st.metric(f"{label} Cost", f"${cost:,.2f}")
```

Each sub-order (Dry, then Frozen) gets its own editable table (again
letting the user delete/adjust rows before exporting) and a cost metric
computed off whatever's currently in the editor.

```python
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
```

Builds the actual exported column set: `GTIN`, `Item Name`, the order
quantity, and (temporarily) `Case Pack` — kept only long enough to decide
formatting. The `.apply(..., axis=1)` row-by-row transform is the
**inline case labeling** feature: for any item whose case pack is greater
than 1, the order quantity is rendered as a string like `"3 cases"` or
`"1 case"` (correct singular/plural via the ternary on the exact count);
for single-unit items (`Case Pack == 1`), it's just the bare integer as a
string (e.g. `"5"`), since "case" language would be misleading for a
per-unit item. `Case Pack` is then dropped (it was only needed to decide
the formatting, not to be shown in the final file) and the column is
renamed from the internal `'Order (Cases)'` label to the simpler,
vendor-facing `'Order'` header.

```python
                            buf = io.BytesIO()
                            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                                export_df.to_excel(
                                    writer, index=False, sheet_name='Vendor_Order')
                                text_fmt = writer.book.add_format({'num_format': '@'})
                                writer.sheets['Vendor_Order'].set_column('A:A', 20, text_fmt)
                                writer.sheets['Vendor_Order'].set_column('B:B', 40)
```

Unlike the HQ Transfer sheet (built manually cell-by-cell for the custom
title row), the Vendor Order sheet is simpler: `export_df.to_excel(...)`
writes it directly with a normal header row at the top. Column A (`GTIN`)
is set to text format for the same barcode-preservation reason as before;
column B (`Item Name`) just gets a wider width for readability.

```python
                            st.download_button(f"📥 Download {label}", buf.getvalue(),
                                               file_name=f"{short_name}_{date_str}_{file_label}.xlsx",
                                               key=f"dl_{label}_{short_name}")
                        else:
                            st.write("No items in this category.")
                else:
                    st.success(
                        "No vendor order needed (Items may be covered by HQ).")
```

Download button with filename `{store_code}_{date}_{Dry|Frozen}.xlsx` —
again store-code-first, clean plain-text category name, no emoji. If a
particular sub-order (Dry or Frozen) has no rows, shows a plain message
instead of an empty table/download. If the store needs _no_ vendor order
at all (fully covered by HQ or nothing to reorder), shows a success
message instead of the whole section.

```python
            else:
                st.error(f"Missing column '{long_name}' in Catalog.")
```

If this store's expected column simply isn't present in the uploaded
catalog at all (e.g. store not included in this particular Square export),
shows an error in that store's tab rather than crashing.

---

## 16. Consolidated Order Summary

```python
    st.divider()
    st.subheader("📊 Consolidated Order Summary")
    st.caption("Total items being ordered across all stores (vendor + HQ)")

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
```

Runs `compute_store_order` **once more, per store** (third time this
function has been called for each store across the whole script —
accepted redundancy for simplicity/correctness, as noted in §12) to
rebuild a fresh order table per store, this time collecting every store
with a real need into a list of small per-store DataFrames tagged with a
`Store` column. Note this reads `Suggested_HQ_Qty` here, **not** the
per-tab-edited `Final_HQ_Qty` — meaning the consolidated summary reflects
the _system-suggested_ HQ split, not any row-level edits a user made
inside a specific store tab's data editor. That's a meaningful distinction
worth remembering if the consolidated numbers ever look slightly different
from what you'd expect after manually editing a tab.

```python
    if all_orders:
        combined_orders = pd.concat(all_orders, ignore_index=True)

        summary = combined_orders.groupby('SKU').agg({
            'GTIN': 'first', 'Item Name': 'first', 'Order In Quantities': 'first',
            'Vendor_Units': 'sum', 'HQ_Units': 'sum', 'Default Unit Cost': 'first'
        }).reset_index()

        summary = summary[summary['Vendor_Units'] > 0].copy()

        summary['Total_Units'] = summary['Vendor_Units']
        summary['Total_Cost'] = summary['Total_Units'] * summary['Default Unit Cost']
```

Stacks every store's order rows together, then groups by `SKU` — summing
`Vendor_Units` and `HQ_Units` **across all selected stores** for that SKU
(so if three stores each need 2 cases of the same item, this shows the
combined 6). `GTIN`/`Item Name`/`Order In Quantities`/`Default Unit Cost`
are assumed identical across stores for the same SKU, so `'first'` is
sufficient. Filters down to only SKUs with a nonzero _vendor_ total
(`summary['Vendor_Units'] > 0`) — this consolidated download is
specifically a **vendor purchase order**, so SKUs fully covered by HQ
transfers (zero vendor units) are intentionally excluded. `Total_Units`
and `Total_Cost` are then just aliases/derived columns for display.

```python
        display_summary = summary[[
            'SKU', 'GTIN', 'Item Name', 'Order In Quantities', 'Total_Units', 'Default Unit Cost', 'Total_Cost'
        ]].copy().rename(columns={
            'Order In Quantities': 'Case Pack', 'Default Unit Cost': 'Unit Cost',
            'Total_Units': 'Qty to Order', 'Total_Cost': 'Total $'
        })

        st.dataframe(display_summary, use_container_width=True, hide_index=True)
```

A friendlier-labeled, read-only preview table shown directly in the app.

```python
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Items", len(summary))
        with col2:
            st.metric("Total Units Ordered", int(summary['Total_Units'].sum()))
        with col3:
            st.metric("Total Order Value", f"${summary['Total_Cost'].sum():,.2f}")
```

Three side-by-side headline metrics: how many distinct SKUs are being
ordered from the vendor, total unit count across all of them, and total
dollar value of the whole vendor order — a quick sanity check before
placing a real purchase order.

```python
        st.divider()
        export_summary = summary[[
            'GTIN', 'Item Name', 'Order In Quantities', 'Vendor_Units'
        ]].copy().rename(columns={
            'Order In Quantities': 'Case Pack', 'Vendor_Units': 'Order Qty'
        })

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
            file_name=f"{date_str}_{selected_vendor}_CONSOLIDATED_ORDER.xlsx",
            key="dl_consolidated"
        )
```

Builds and offers the final downloadable file: one combined vendor order
across every selected store, with GTIN, item name, case pack, and total
order quantity. Note this file's naming pattern is
`{date}_{vendor}_CONSOLIDATED_ORDER.xlsx` — date-first here rather than
store-code-first, which makes sense since this file isn't scoped to a
single store the way the per-store exports are.

---

## 17. Welcome / empty states

```python
elif not selected_stores:
    st.warning("Please select at least one store in the sidebar to begin processing.")
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
    st.warning("⚠️ Please select a vendor and click 'Load Rules from Google Sheets' to continue.")
```

These are the `elif` branches on the _outermost_ `if catalog_file and
rules_matrix is not None and selected_stores:` from §10 — they cover every
way the three prerequisites can be incomplete, each with a targeted,
helpful message instead of a blank page:

- No store selected → warning telling you to pick one.
- No catalog uploaded → a full onboarding block with numbered
  step-by-step instructions for pulling the correct export out of Square
  (Items → Item Library → filter by vendor → Export Library → filtered
  export), plus a reference screenshot loaded from a local image file. The
  `try`/`except` around `st.image` prevents a missing image file from
  crashing the whole welcome screen — it just shows a plain warning
  instead if the file isn't found. **Note:** this relies on a local file
  at `./Data/Images/Export Example.png` relative to wherever `streamlit
run` is launched from — if you rebuild this project fresh, recreate that
  `Data/Images/` folder alongside `main.py` and drop a reference
  screenshot in it (or update the path).
- Catalog uploaded and store(s) selected, but rules matrix not loaded yet
  → warning pointing at the vendor dropdown + load button.

---

## 18. Data flow summary (mental model)

```
Square export (.xlsx)              Google Sheet (per vendor)
        │                                   │
        ▼                                   ▼
  load_catalog() ──────────┐        load_rules_from_sheets()
  (df_master)               │                │
        │                   │                ▼
        │             (filtered to catalog SKUs)
        │                   │                │
        └─────────────┬─────┴────────────────┘
                       ▼
            compute_store_order(store)
              per-store merge + rules:
              Needs_Order → Total_Units_Needed
              (round-half-up, floor of 1 case,
               understock safety net)
                       │
        ┌──────────────┼───────────────────┐
        ▼                                   ▼
get_allocation_candidates()      Suggested_HQ_Qty / Vendor_Units
  (cross-store HQ conflicts)      (per store, per SKU)
        │                                   │
        ▼                                   ▼
 Allocation UI (fragment)          Store tabs:
  → hq_allocations{sku}{store}      - HQ Transfer editor + .xlsx
        │                            - Vendor Order (Dry/Frozen)
        └───────────────►             editors + .xlsx each
                                              │
                                              ▼
                                 Consolidated Order Summary
                                  (all stores combined) + .xlsx
```

Everything ultimately traces back to one function,
`compute_store_order`, called with different `hq_allocations` /
`allocation_candidates` inputs at different points in the script, always
returning the same shape of DataFrame that every UI section and export
downstream consumes identically.

---

## 19. Known open items (as of this version)

- The **"Excluded SKUs"** sheet tab (second tab on each vendor's rules
  Google Sheet) documents intentionally-discontinued SKUs, but `main.py`
  only ever reads `.sheet1` — it never opens or validates against that
  tab. Unmatched catalog SKUs are currently only surfaced via a
  server-console `print` (§10), not cross-checked against that documented
  exclusion list. A natural next feature: read the Excluded SKUs tab in
  `load_rules_from_sheets` (or a sibling function) and, for any unmatched
  SKU, report explicitly whether it was intentionally excluded or is a
  genuinely new/unrecognized item worth investigating.
- `current_tab` in session state is initialized but not currently read by
  any widget — a placeholder for a possible future "remember which store
  tab was open" feature.

---

## 20. Local dev workflow reminder

Because this Claude Project treats uploaded files as **read-only**, any
edit to `main.py` made in a session here must be **downloaded** from
`/mnt/user-data/outputs/main.py` and manually used to replace your local
copy — there is no auto-sync back into the project. After replacing the
local file, restart `streamlit run main.py` (or let Streamlit's
auto-reload pick up the change) and re-test against real catalog/rules
data before moving on to the next change, per the test-before-proceed
discipline used throughout this project's history.
