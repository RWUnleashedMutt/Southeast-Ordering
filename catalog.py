import pandas as pd
import streamlit as st


def clean_id(val):
    if pd.isna(val):
        return ""
    return str(int(val)) if isinstance(val, float) and val.is_integer() else str(val)


@st.cache_data
def load_catalog(file) -> pd.DataFrame:
    dtype_dict = {'GTIN': str, 'SKU': str}
    df = pd.read_excel(file, header=1, dtype=dtype_dict)
    df.columns = df.columns.str.strip()
    df['SKU'] = df['SKU'].apply(clean_id)
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
