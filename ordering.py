import pandas as pd
import numpy as np

from config import inv_store_map


def compute_store_order(store_code, df_master, rules_matrix, hq_col,
                        hq_threshold, allocation_candidates, hq_allocations):
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

    has_rules_match = store_inv['SKU'].isin(set(store_rules['SKU']))

    data = pd.merge(store_inv, store_rules, on='SKU', how='left')
    data = data.fillna({
        'DNO': 0, 'Order In Quantities': 1, 'Min': 0,
        'Max': 0, 'Current_Inv': 0, 'HQ_Qty': 0, 'Default Unit Cost': 0
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


def get_allocation_candidates(df_master, rules_matrix, hq_col,
                              selected_stores, hq_threshold):
    """Find SKUs where combined store demand exceeds HQ stock, so the UI
    can ask the user how to split limited HQ inventory across stores."""
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
