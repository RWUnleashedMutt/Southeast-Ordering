"""Square "stock-by" (component) variations.

Some Square items are sold in several ways — e.g. a base item "FRZN Smalls Cat
Ground Bird Chicken 5oz" that is also sold as a "6 Pack" or "8PK". Square
keeps the inventory on the BASE item; the pack variations show a blank
quantity at every location and have no unit cost. The catalog export lists
which variation is stocked by which base item on its "Component Inventory"
sheet (columns "Stock-by Reference Handle" and "Stock-by Equivalent").

The rules matrix, however, can hold Min/Max/Order-In-Quantities rows on the
pack variation (that's what is ordered from the vendor). So for ordering, a
variation must see its base item's quantities and unit cost; otherwise it
looks permanently out of stock and generates phantom orders.

No Streamlit import here so it can be unit-tested on its own.
"""
import pandas as pd

COMPONENT_SHEET = 'Component Inventory'
STOCK_SOURCE_COL = 'Stock Source SKU'


def clean_component_sheet(comp):
    """Component-sheet headers look like 'Token\\n(locked)'; keep the name."""
    comp = comp.copy()
    comp.columns = (comp.columns.astype(str)
                    .str.replace(r'\s*\n.*$', '', regex=True).str.strip())
    return comp


def inherit_component_stock(items, comp):
    """Return `items` with component variations' blank quantities and unit
    cost filled from the base item they are stocked by.

    - Only blank (NaN) values are filled; real values are never overwritten.
    - Quantities are copied 1:1 (Square reports the base item's stock in the
      base item's units, which is also what the rules matrix Min/Max use).
    - Adds a `Stock Source SKU` column naming the base SKU (blank if none).
    """
    items = items.copy()
    items[STOCK_SOURCE_COL] = ''
    if comp is None or comp.empty:
        return items
    comp = clean_component_sheet(comp)
    needed = {'Token', 'Stock-by Reference Handle'}
    if not needed.issubset(comp.columns) or 'Reference Handle' not in items.columns \
            or 'Token' not in items.columns:
        return items

    children = comp[comp['Stock-by Reference Handle'].notna()].copy()
    children['Stock-by Reference Handle'] = (
        children['Stock-by Reference Handle'].astype(str).str.strip())
    children = children[children['Stock-by Reference Handle'] != '']
    if children.empty:
        return items

    handle_to_pos = {}
    for pos, handle in enumerate(items['Reference Handle'].astype(str).str.strip()):
        # First row wins; a base item's handle is unique in a Square export.
        handle_to_pos.setdefault(handle, pos)
    token_to_pos = {t: p for p, t in enumerate(items['Token'].astype(str))}

    value_cols = [c for c in items.columns
                  if c.startswith('Current Quantity') or c == 'Default Unit Cost']
    sku_col = items.columns.get_loc('SKU')
    source_col = items.columns.get_loc(STOCK_SOURCE_COL)

    for _, child in children.iterrows():
        child_pos = token_to_pos.get(str(child['Token']))
        base_pos = handle_to_pos.get(child['Stock-by Reference Handle'])
        if child_pos is None or base_pos is None or child_pos == base_pos:
            continue
        for col in value_cols:
            col_idx = items.columns.get_loc(col)
            if pd.isna(items.iat[child_pos, col_idx]):
                items.iat[child_pos, col_idx] = items.iat[base_pos, col_idx]
        items.iat[child_pos, source_col] = items.iat[base_pos, sku_col]
    return items
