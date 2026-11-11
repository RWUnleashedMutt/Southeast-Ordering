import pandas as pd
import numpy as np

from config import inv_store_map

# Defaults used when a vendor's rules sheet has no column for a store
# (new store, renamed header, ...). Max=0 / Min=0 means "never triggers an
# order", so a missing column fails safe instead of crashing the page.
_RULE_DEFAULTS = {'DNO': False, 'Min': 0, 'Max': 0}


def missing_rule_columns(rules_matrix, store_codes):
    """Return {store_code: [missing column names]} for stores whose
    `{store}_DNO / _Min / _Max` columns are absent from the rules matrix,
    so the UI can warn about them instead of silently never ordering."""
    missing = {}
    for store_code in store_codes:
        cols = [f'{store_code}_{suffix}' for suffix in ('DNO', 'Min', 'Max')]
        absent = [c for c in cols if c not in rules_matrix.columns]
        if absent:
            missing[store_code] = absent
    return missing


def compute_store_needs(store_code, df_master, rules_matrix, hq_col):
    """Step 1: what does this store need, before any HQ transfer or
    allocation is considered? Independent of hq_threshold, allocations and
    allocation candidates, so it can be computed once per store per run and
    shared by get_allocation_candidates() and apply_hq_suggestions()."""
    long_name = inv_store_map[store_code]

    lookup_cols = ['SKU', 'Order In Quantities',
                   f'{store_code}_DNO', f'{store_code}_Min', f'{store_code}_Max']
    valid_lookup = [c for c in lookup_cols if c in rules_matrix.columns]
    store_rules = rules_matrix[valid_lookup].copy().rename(columns={
        f'{store_code}_DNO': 'DNO',
        f'{store_code}_Min': 'Min',
        f'{store_code}_Max': 'Max'
    })
    for col, default in _RULE_DEFAULTS.items():
        if col not in store_rules.columns:
            store_rules[col] = default

    extra_cols = ['SKU', 'GTIN', 'Item Name',
                  'Default Unit Cost', long_name, hq_col, 'Reserved_Qty']
    available_cols = [c for c in extra_cols if c in df_master.columns]
    store_inv = df_master[available_cols].copy().rename(
        columns={long_name: 'Current_Inv', hq_col: 'HQ_Qty'}
    )

    has_rules_match = store_inv['SKU'].isin(set(store_rules['SKU']))

    data = pd.merge(store_inv, store_rules, on='SKU', how='left')
    data = data.fillna({
        'DNO': 0, 'Order In Quantities': 1, 'Min': 0,
        'Max': 0, 'Current_Inv': 0, 'HQ_Qty': 0, 'Default Unit Cost': 0,
        'Reserved_Qty': 0
    })
    data['DNO'] = data['DNO'].astype(bool)
    data['Has_Rules_Match'] = has_rules_match.values

    data['Effective_Min'] = data['Min']
    data['Needs_Order'] = np.where(
        data['Order In Quantities'] == 1,
        (data['Current_Inv'] < data['Max']),
        (data['Current_Inv'] < data['Effective_Min'])
    )
    data['Needs_Order'] = data['Needs_Order'] & (
        data['DNO'] == False) & data['Has_Rules_Match']
    data['Units_Needed_To_Max'] = np.where(
        data['Needs_Order'],
        np.maximum(data['Max'] - data['Current_Inv'], 0),
        0
    )
    raw_cases = data['Units_Needed_To_Max'] / data['Order In Quantities']
    rounded_cases = np.floor(raw_cases + 0.5)
    rounded_cases = np.where(
        (data['Units_Needed_To_Max'] > 0) & (rounded_cases < 1),
        1, rounded_cases
    )
    data['Total_Units_Needed'] = rounded_cases * \
        data['Order In Quantities']

    would_understock = data['Needs_Order'] & (
        (data['Current_Inv'] + data['Total_Units_Needed']
         ) < data['Effective_Min']
    )
    data['Total_Units_Needed'] = np.where(
        would_understock,
        data['Total_Units_Needed'] + data['Order In Quantities'],
        data['Total_Units_Needed']
    )
    return data


def apply_hq_suggestions(base_data, store_code, hq_threshold,
                         allocation_candidates, hq_allocations):
    """Step 2: split each need between an HQ transfer and a vendor order,
    using the user's pushed allocations and the HQ threshold. Returns a new
    frame; `base_data` is not modified."""
    data = base_data.copy()

    alloc_map = {
        sku: per_store.get(store_code, 0)
        for sku, per_store in hq_allocations.items()
    }
    data['Allocated_HQ'] = data['SKU'].map(alloc_map).fillna(0)
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
    # What is actually ordered: whole cases. This (not Vendor_Units, which
    # can be a partial case) is what cost must be based on.
    data['Order_Units'] = data['Vendor_Cases'] * data['Order In Quantities']
    return data


def compute_store_order(store_code, df_master, rules_matrix, hq_col,
                        hq_threshold, allocation_candidates, hq_allocations):
    base = compute_store_needs(store_code, df_master, rules_matrix, hq_col)
    return apply_hq_suggestions(
        base, store_code, hq_threshold, allocation_candidates, hq_allocations)


def get_allocation_candidates(df_master, rules_matrix, hq_col,
                              selected_stores, hq_threshold, base_data=None):
    """Find SKUs where combined store demand exceeds HQ stock, so the UI
    can ask the user how to split limited HQ inventory across stores.

    `base_data` ({store_code: compute_store_needs() result}) can be passed
    in to avoid recomputing each store's needs."""
    store_needs_list = []

    for store_code in selected_stores:
        long_name = inv_store_map[store_code]
        if long_name not in df_master.columns:
            continue

        if base_data is not None and store_code in base_data:
            data = base_data[store_code]
        else:
            data = compute_store_needs(
                store_code, df_master, rules_matrix, hq_col)
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


def vendor_order_frame(data):
    """Default vendor-order lines for one store, straight from the computed
    data (no manual edits). Columns: SKU, GTIN, Item Name, Case Pack, Cases,
    Unit Cost, Order Units. Used as the fallback for the consolidated
    summary and as the base for the editable vendor tables."""
    lines = data[data['Order_Units'] > 0]
    return pd.DataFrame({
        'SKU': lines['SKU'],
        'GTIN': lines['GTIN'] if 'GTIN' in lines.columns else '',
        'Item Name': lines['Item Name'],
        'Case Pack': lines['Order In Quantities'],
        'Cases': lines['Vendor_Cases'],
        'Unit Cost': lines['Default Unit Cost'],
        'Order Units': lines['Order_Units'],
    }).reset_index(drop=True)


def consolidate_vendor_orders(order_frames):
    """Combine per-store vendor-order frames (see vendor_order_frame) into
    one order per SKU: units summed across stores, cost from whole cases."""
    frames = [f for f in order_frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame(columns=[
            'SKU', 'GTIN', 'Item Name', 'Case Pack',
            'Order Units', 'Unit Cost', 'Total Cost'])
    combined = pd.concat(frames, ignore_index=True)
    summary = combined.groupby('SKU', as_index=False).agg({
        'GTIN': 'first',
        'Item Name': 'first',
        'Case Pack': 'first',
        'Order Units': 'sum',
        'Unit Cost': 'first',
    })
    summary = summary[summary['Order Units'] > 0].copy()
    summary['Total Cost'] = summary['Order Units'] * summary['Unit Cost']
    return summary.reset_index(drop=True)
