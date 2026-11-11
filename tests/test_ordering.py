import pandas as pd
import pytest

from config import inv_store_map
from ordering import (
    apply_hq_suggestions,
    compute_store_needs,
    compute_store_order,
    consolidate_vendor_orders,
    get_allocation_candidates,
    missing_rule_columns,
    vendor_order_frame,
)

HQ = 'Available Quantity HQ'
CC_COL = inv_store_map['CC']
CM_COL = inv_store_map['CM']


def catalog(rows):
    """rows: (sku, cc_inv, hq_qty[, cm_inv]) tuples -> catalog-like frame."""
    return pd.DataFrame({
        'SKU': [r[0] for r in rows],
        'GTIN': ['0' + r[0] for r in rows],
        'Item Name': [f'item {r[0]}' for r in rows],
        'Default Unit Cost': [10.0] * len(rows),
        CC_COL: [r[1] for r in rows],
        CM_COL: [r[3] if len(r) > 3 else 0 for r in rows],
        HQ: [r[2] for r in rows],
        'Reserved_Qty': [0] * len(rows),
    })


def rules(rows):
    """rows: (sku, oiq, cc_min, cc_max[, dno]) -> rules matrix for CC."""
    return pd.DataFrame({
        'SKU': [r[0] for r in rows],
        'Order In Quantities': [r[1] for r in rows],
        'CC_Min': [r[2] for r in rows],
        'CC_Max': [r[3] for r in rows],
        'CC_DNO': [r[4] if len(r) > 4 else False for r in rows],
    })


def order(cat, rul, threshold=6, candidates=None, allocations=None):
    return compute_store_order(
        'CC', cat, rul, HQ, threshold, candidates or {}, allocations or {}
    ).set_index('SKU')


# --- needs / rounding -------------------------------------------------------

def test_single_unit_items_order_up_to_max():
    out = order(catalog([('A', 2, 0)]), rules([('A', 1, 1, 5)]))
    assert out.loc['A', 'Total_Units_Needed'] == 3


def test_case_pack_triggers_on_min_and_rounds_to_nearest_case():
    # inv 2 < min 4, need 10 to max 12 -> 10/6 = 1.67 -> 2 cases -> 12 units
    out = order(catalog([('A', 2, 0)]), rules([('A', 6, 4, 12)]))
    assert out.loc['A', 'Total_Units_Needed'] == 12


def test_case_pack_above_min_does_not_order():
    out = order(catalog([('A', 4, 0)]), rules([('A', 6, 4, 12)]))
    assert out.loc['A', 'Total_Units_Needed'] == 0


def test_rounds_to_nearest_case_without_extra_case_when_min_is_met():
    # max 11, oiq 5 -> 11/5 = 2.2 -> 2 cases = 10 units, still >= min 9
    out = order(catalog([('A', 0, 0)]), rules([('A', 5, 9, 11)]))
    assert out.loc['A', 'Total_Units_Needed'] == 10


def test_rounding_down_that_leaves_store_under_min_adds_a_case():
    # max 12, oiq 5 -> 2.4 -> 2 cases = 10 units, but 10 < min 11 -> +1 case
    out = order(catalog([('A', 0, 0)]), rules([('A', 5, 11, 12)]))
    assert out.loc['A', 'Total_Units_Needed'] == 15


def test_dno_is_never_ordered():
    out = order(catalog([('A', 0, 0)]), rules([('A', 1, 1, 5, True)]))
    assert out.loc['A', 'Total_Units_Needed'] == 0


def test_unmatched_sku_with_negative_inventory_does_not_order():
    out = order(catalog([('A', -3, 0), ('B', 0, 0)]), rules([('B', 1, 1, 5)]))
    assert out.loc['A', 'Total_Units_Needed'] == 0
    assert out.loc['B', 'Total_Units_Needed'] == 5


# --- missing rule columns ---------------------------------------------------

def test_missing_store_columns_fail_safe_instead_of_crashing():
    rul = rules([('A', 1, 1, 5)]).drop(columns=['CC_DNO', 'CC_Min', 'CC_Max'])
    out = order(catalog([('A', 0, 0)]), rul)
    assert out.loc['A', 'Total_Units_Needed'] == 0
    assert missing_rule_columns(rul, ['CC', 'CM']) == {
        'CC': ['CC_DNO', 'CC_Min', 'CC_Max'],
        'CM': ['CM_DNO', 'CM_Min', 'CM_Max'],
    }


def test_no_missing_columns_reported_when_present():
    assert missing_rule_columns(rules([('A', 1, 1, 5)]), ['CC']) == {}


# --- HQ split, whole-case cost ----------------------------------------------

def test_hq_covers_need_when_above_threshold():
    out = order(catalog([('A', 0, 10)]), rules([('A', 1, 1, 5)]), threshold=6)
    assert out.loc['A', 'Suggested_HQ_Qty'] == 5
    assert out.loc['A', 'Order_Units'] == 0


def test_partial_case_after_hq_allocation_is_costed_as_a_whole_case():
    # Need 12 (2 cases of 6). HQ allocation of 5 -> 7 units left -> 2 cases.
    cat = catalog([('A', 0, 8)])
    rul = rules([('A', 6, 4, 12)])
    data = order(cat, rul, candidates={'A': {}}, allocations={'A': {'CC': 5}})
    assert data.loc['A', 'Vendor_Units'] == 7
    assert data.loc['A', 'Vendor_Cases'] == 2
    assert data.loc['A', 'Order_Units'] == 12


def test_allocation_only_applies_to_the_given_store():
    base = compute_store_needs('CC', catalog([('A', 0, 8)]),
                               rules([('A', 1, 1, 5)]), HQ)
    out = apply_hq_suggestions(
        base, 'CC', 6, {'A': {}}, {'A': {'CM': 3, 'CC': 2}}).set_index('SKU')
    assert out.loc['A', 'Suggested_HQ_Qty'] == 2
    assert out.loc['A', 'Vendor_Units'] == 3


def test_apply_hq_suggestions_does_not_mutate_base():
    base = compute_store_needs('CC', catalog([('A', 0, 10)]),
                               rules([('A', 1, 1, 5)]), HQ)
    before = base.copy()
    apply_hq_suggestions(base, 'CC', 6, {}, {})
    pd.testing.assert_frame_equal(base, before)


# --- allocation candidates ---------------------------------------------------

def test_conflict_detected_when_stores_need_more_than_hq_has():
    cat = catalog([('A', 0, 8, 0)])
    rul = rules([('A', 1, 1, 6)])
    rul['CM_DNO'] = False
    rul['CM_Min'] = 1
    rul['CM_Max'] = 6
    cands = get_allocation_candidates(cat, rul, HQ, ['CC', 'CM'], 6)
    assert set(cands) == {'A'}
    assert cands['A']['hq_qty'] == 8
    assert set(cands['A']['stores']) == {'CC', 'CM'}
    assert cands['A']['demand_map']['CC']['demand'] == 6


def test_no_conflict_when_hq_at_or_below_threshold():
    cat = catalog([('A', 0, 5, 0)])
    rul = rules([('A', 1, 1, 6)])
    rul['CM_DNO'], rul['CM_Min'], rul['CM_Max'] = False, 1, 6
    assert get_allocation_candidates(cat, rul, HQ, ['CC', 'CM'], 6) == {}


def test_shared_base_data_gives_same_candidates():
    cat = catalog([('A', 0, 8, 0)])
    rul = rules([('A', 1, 1, 6)])
    rul['CM_DNO'], rul['CM_Min'], rul['CM_Max'] = False, 1, 6
    base = {s: compute_store_needs(s, cat, rul, HQ) for s in ['CC', 'CM']}
    assert (get_allocation_candidates(cat, rul, HQ, ['CC', 'CM'], 6, base_data=base)
            == get_allocation_candidates(cat, rul, HQ, ['CC', 'CM'], 6))


# --- consolidation -----------------------------------------------------------

def test_consolidation_sums_whole_cases_across_stores_and_costs_them():
    cat = catalog([('A', 0, 0, 0)])
    rul = rules([('A', 6, 4, 12)])
    rul['CM_DNO'], rul['CM_Min'], rul['CM_Max'] = False, 4, 12
    frames = [
        vendor_order_frame(compute_store_order(s, cat, rul, HQ, 6, {}, {}))
        for s in ['CC', 'CM']
    ]
    summary = consolidate_vendor_orders(frames)
    assert list(summary['SKU']) == ['A']
    assert summary.loc[0, 'Order Units'] == 24
    assert summary.loc[0, 'Total Cost'] == 240


def test_consolidation_with_nothing_to_order_is_empty():
    assert consolidate_vendor_orders([]).empty
    assert consolidate_vendor_orders([pd.DataFrame()]).empty


# --- blank SKU handling (needs streamlit because catalog.py imports it) ------

def test_clean_id_strips_and_blanks():
    pytest.importorskip("streamlit")
    from catalog import clean_id
    assert clean_id(None) == ""
    assert clean_id(float('nan')) == ""
    assert clean_id(12.0) == "12"
    assert clean_id("  ABC ") == "ABC"
