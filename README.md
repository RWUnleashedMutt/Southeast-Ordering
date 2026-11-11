# Southeast Inventory & Ordering App

A Streamlit app that generates per-store and vendor purchase orders for Southeast Pet, combining a Square catalog export with per-vendor Min/Max/DNO rules stored in Google Sheets — with HQ-to-store transfer suggestions and conflict-aware allocation when HQ stock can't cover every store's need.

## What it does

1. **Load inputs** — upload a Square catalog export (.xlsx) and pick a vendor to pull its Rules Matrix live from Google Sheets.
2. **Compute store orders** — for each selected store, compares current inventory against that store's Min/Max/DNO rules to decide what needs ordering, and how much.
3. **Suggest HQ transfers** — if HQ has more stock than the configured threshold, suggests transferring from HQ instead of ordering from the vendor.
4. **Resolve HQ conflicts** — when multiple stores want more stock than HQ has available for the same SKU, presents an allocation UI so the user manually splits HQ's limited stock across stores; anything not allocated falls back to a full vendor order.
5. **Per-store editing & export** — each store gets its own tab with editable HQ Transfer and Vendor Order (split Dry / Frozen) tables, each downloadable as a formatted Excel file.
6. **Consolidated summary** — rolls up the vendor orders across all selected stores (including your edits in the store tabs) into one combined order with total cost, downloadable as a single Excel file. Click **Refresh summary** after editing a store tab to update it.

## Project layout

| File | Responsibility |
|---|---|
| `main.py` | App entry point: loads inputs, wires the pieces together |
| `ordering.py` | Pure ordering logic (needs, HQ split, allocation conflicts, consolidation) — no Streamlit |
| `catalog.py` | Square catalog loader |
| `google_sheets.py` | Rules Matrix and reserved-stock loaders |
| `ui_sidebar.py`, `ui_allocation.py`, `ui_store_tab.py`, `ui_summary.py` | Streamlit UI sections |
| `config.py` | Sheet IDs and store maps |
| `tests/` | pytest suite for `ordering.py` |

## Requirements

```
streamlit
pandas
numpy
gspread
google-auth
xlsxwriter
openpyxl
tzdata
```

(Exact pinned versions are in `requirements.txt`; test-only packages are in `requirements-dev.txt`.)

## Configuration

### Google Sheets access
Requires a Google service account with Sheets + Drive scopes, configured via Streamlit secrets:

```toml
[gcp_service_account]
type = "service_account"
...
```

### Vendor Rules Matrix sheets
`SHEET_IDS` maps vendor name → Google Sheet ID. Each vendor's sheet (`sheet1`) is expected to contain:
- `SKU`
- `Order In Quantities` (case pack size)
- Per-store columns named `{StoreCode}_DNO`, `{StoreCode}_Min`, `{StoreCode}_Max`

### Store list
`store_map` maps each store's catalog column name (`Current Quantity {Store}`) to its short code (e.g. `CM`, `CVM`, `LB`). `inv_store_map` is the reverse lookup, built automatically. `priority_stores` sets which store codes are pre-selected in the sidebar.

To add/remove a store, update `store_map` — everything else derives from it.

## Catalog file requirements

The uploaded catalog `.xlsx` must:
- Have its header row on the **2nd row** of the sheet (`header=1`).
- Include a `SKU` column and, ideally, a `GTIN` column (both read as text/strings).
- Include a `Current Quantity HQ` column and a `Current Quantity {Store}` column for each store to be processed.
- Include `Item Name` and `Default Unit Cost` columns for cost calculations and display.

The app's welcome screen walks through exporting this from Square: **Items → Item Library → filter by Vendor → Actions → Export Library → "Export items matching applied filters."**

## Ordering logic

For each store/SKU combination:
- **DNO** ("Do Not Order") rows are always skipped.
- SKUs with no match in that vendor's Rules Matrix are also skipped (`Has_Rules_Match` guard) — prevents unmatched SKUs with bad/negative inventory data from accidentally triggering an order.
- If `Order In Quantities == 1`, ordering triggers when `Current_Inv < Max`. Otherwise it triggers when `Current_Inv < Min`.
- Units needed are rounded to the nearest whole case (`Order In Quantities`), with a minimum of 1 case if any units are needed.
- If rounding down would leave the store below its Min, one more case is added.
- If HQ has stock above the configured threshold and the SKU isn't a flagged allocation conflict, the full need is suggested as an HQ transfer instead of a vendor order.
- Vendor orders are always whole cases. **Units and cost are computed from cases × case pack**, so a partial case left after an HQ transfer is costed as the full case, and editing `Order (Cases)` in a store tab updates the units and cost shown.
- If a vendor's rules sheet is missing a store's `_DNO` / `_Min` / `_Max` columns, nothing is ordered for that store and a warning is shown.
- Rows with a blank SKU (in the catalog, the rules sheets or the reserved sheet) are ignored.

### HQ allocation conflicts
Before per-store tabs are shown, the app scans for SKUs where total demand across selected stores exceeds available HQ stock (and HQ stock is above threshold). For each such SKU, the user allocates HQ quantity across the stores that need it via number inputs; unallocated demand automatically reverts to a vendor order for that store.

Allocations only reach the store tabs when you click **Push Allocations**; what you push is snapshotted, so later edits do nothing until you push again, and over-allocated SKUs block the push. Changing the catalog file, HQ threshold, vendors or store selection clears all allocations.

### Per-store tab adjustments
The HQ Transfer table and the Vendor Order tables (Dry/Frozen, split by whether the item name starts with `FRZN`) are `st.data_editor` grids — rows can be deleted or quantities adjusted before download (in the vendor tables only `Order (Cases)` is editable). Each tab is wrapped in `@st.fragment` so edits only rerun that store's section, not the whole app.

## Outputs

All exports are formatted `.xlsx` files (GTIN column forced to text to preserve leading zeros):

| File | Contents |
|---|---|
| `{Store}_{Date}_HQ_{Vendor}.xlsx` | HQ transfer list for one store |
| `{Store}_{Date}_Dry.xlsx` / `{Store}_{Date}_Frozen.xlsx` | Vendor order for one store, split by product type |
| `{Date}_{Vendor}_CONSOLIDATED_ORDER.xlsx` | Combined vendor order across all selected stores (`{Vendor}` becomes e.g. `12_vendors` when more than 3 are selected) |

## Running it

```bash
streamlit run main.py
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

## Notes

- `load_rules_from_sheets()` is cached for 1 hour (`ttl=3600`); the sidebar "Load Rules from Google Sheets" button clears the cache to force a fresh pull. The reserved-stock sheet is refreshed by the same button.
- If the reserved-stock sheet can't be loaded, the app stops with an error unless you tick "Continue anyway without reserved-stock data".
- Rows in the Rules Matrix with `Order In Quantities <= 0` are treated as a data error and halt the app with a clear error message.
- DNO values are coerced from whatever Google Sheets returns (`"TRUE"`, `"1"`, `"YES"`, `1.0`, actual booleans, etc.) into real booleans.
- Unmatched catalog SKUs (no row in that vendor's Rules Matrix) are logged to the console, not shown in the UI.
