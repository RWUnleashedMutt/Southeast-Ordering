import numpy as np
import pandas as pd

from component_stock import STOCK_SOURCE_COL, inherit_component_stock


def items():
    return pd.DataFrame({
        'Token': ['T_BASE', 'T_8PK', 'T_OTHER'],
        'Reference Handle': ['#base-', '#base-8pk', '#other-'],
        'SKU': ['29252', 'J652865', '555'],
        'Default Unit Cost': [2.5, np.nan, 9.0],
        'Current Quantity HQ': [10.0, np.nan, 3.0],
        'Current Quantity Lake Boone': [4.0, np.nan, 1.0],
    })


def comp(stock_by='#base-'):
    return pd.DataFrame({
        'Token\n(locked)': ['T_BASE', 'T_8PK'],
        'Reference Handle': ['#base-', '#base-8pk'],
        'Stock-by Reference Handle': [np.nan, stock_by],
        'Stock-by Equivalent': [np.nan, 8.0],
    })


def test_variation_inherits_base_quantities_and_cost():
    out = inherit_component_stock(items(), comp())
    row = out[out['SKU'] == 'J652865'].iloc[0]
    assert row['Current Quantity HQ'] == 10
    assert row['Current Quantity Lake Boone'] == 4
    assert row['Default Unit Cost'] == 2.5
    assert row[STOCK_SOURCE_COL] == '29252'


def test_base_and_unrelated_items_untouched():
    out = inherit_component_stock(items(), comp())
    assert out[out['SKU'] == '29252'].iloc[0][STOCK_SOURCE_COL] == ''
    other = out[out['SKU'] == '555'].iloc[0]
    assert other['Current Quantity HQ'] == 3 and other[STOCK_SOURCE_COL] == ''


def test_real_values_are_never_overwritten():
    it = items()
    it.loc[1, 'Current Quantity Lake Boone'] = 7.0  # variation has its own value
    out = inherit_component_stock(it, comp())
    row = out[out['SKU'] == 'J652865'].iloc[0]
    assert row['Current Quantity Lake Boone'] == 7
    assert row['Current Quantity HQ'] == 10  # still-blank one is filled


def test_unknown_base_handle_is_ignored():
    out = inherit_component_stock(items(), comp(stock_by='#missing-'))
    row = out[out['SKU'] == 'J652865'].iloc[0]
    assert pd.isna(row['Current Quantity HQ']) and row[STOCK_SOURCE_COL] == ''


def test_no_component_sheet_is_a_noop():
    out = inherit_component_stock(items(), None)
    assert out[STOCK_SOURCE_COL].eq('').all()
    assert pd.isna(out.loc[1, 'Current Quantity HQ'])
