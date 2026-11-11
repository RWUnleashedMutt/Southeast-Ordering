import pandas as pd
import streamlit as st

from component_stock import COMPONENT_SHEET, inherit_component_stock


def clean_id(val):
    if pd.isna(val):
        return ""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()


@st.cache_data
def load_catalog(file) -> pd.DataFrame:
    dtype_dict = {'GTIN': str, 'SKU': str}
    xl = pd.ExcelFile(file)
    df = xl.parse(0, header=1, dtype=dtype_dict)
    df.columns = df.columns.str.strip()

    # Pack variations (e.g. "8PK") are stocked by a base item and show blank
    # quantities in Square; give them the base item's stock and cost.
    if COMPONENT_SHEET in xl.sheet_names:
        df = inherit_component_stock(
            df, xl.parse(COMPONENT_SHEET, header=1, dtype=str))
    df['SKU'] = df['SKU'].apply(clean_id)
    # Items with no SKU can't be matched to a rule or ordered. Dropping them
    # here stops them all collapsing onto the same "" key (and matching a
    # stray blank-SKU row in a rules sheet).
    df = df[df['SKU'] != ""].reset_index(drop=True)
    if 'GTIN' in df.columns:
        df['GTIN'] = df['GTIN'].astype(str).str.strip()

    # Square sometimes leaves 'Item Name' identical across an item's
    # variations (e.g. a 14oz and 28oz of the same product both show as
    # just "CPT Fresh Field Jerky Bison & Apple") and puts the
    # distinguishing detail in 'Variation Name' instead. Since this app
    # displays/exports by 'Item Name' everywhere, fold the variation in
    # wherever it's present and not already part of the name so the two
    # sizes don't look identical in the UI, HQ transfer sheets, or vendor
    # order exports.
    if 'Item Name' in df.columns and 'Variation Name' in df.columns:
        def _combine_item_variation(row):
            item_name = str(row['Item Name'])
            var_name = row['Variation Name']
            if pd.isna(var_name):
                return item_name
            var_name = str(var_name).strip()
            if not var_name or var_name.lower() == 'nan':
                return item_name
            if var_name.lower() in item_name.lower():
                return item_name
            return f"{item_name} - {var_name}"
        df['Item Name'] = df.apply(_combine_item_variation, axis=1)

    return df
