import pandas as pd
import os

# Get user input for Vendor
Vendor = input('Input Vendor: (Ex: Southeast)')

# --- CONFIG ---
CATALOG_PATH = './Data/Catalog/southeast catalog.xlsx'
RULES_MATRIX_PATH = f'./Data/Rules/{Vendor} Rules Matrix.xlsx'

store_map = {
    'Current Quantity City Market: DTR': 'CM',
    'Current Quantity Crabtree Valley Mall': 'CVM',
    'Current Quantity Crescent Commons': 'CC',
    'Current Quantity Downtown Durham': 'DTD',
    'Current Quantity Front Street': 'MF',
    'Current Quantity Lake Boone': 'LB',
    'Current Quantity Landfall Shopping Center': 'LF',
    'Current Quantity Parkway Plaza': 'PP',
    'Current Quantity Southport - Tidewater': 'SP',
    'Current Quantity Stonehenge Market': 'SH',
    'Current Quantity The Streets at Southpoint': 'SS'
}


def sync_rules_matrix():
    # 1. Load SKUs and Descriptions from catalog
    # Note: Using header=1 as per your catalog format
    catalog = pd.read_excel(CATALOG_PATH, header=1, usecols=[
                            'SKU', 'Description', 'Reporting Category'],
                            dtype={'SKU': str, 'Description': str})
    catalog = catalog.dropna(subset=['SKU']).drop_duplicates(subset=['SKU'])

    # 2. Define the columns we need for every store
    # UPDATED: 'Order In Quantities' replaces 'Order_Qty'
    matrix_columns = ['SKU', 'Description',
                      'Reporting Category', 'Order In Quantities']

    for code in store_map.values():
        matrix_columns.extend([f'{code}_DNO', f'{code}_Min', f'{code}_Max'])

    # 3. Load or Create Matrix
    if os.path.exists(RULES_MATRIX_PATH):
        rules_df = pd.read_excel(RULES_MATRIX_PATH, dtype={'SKU': str})

        # MIGRATION LOGIC: Rename old column if it exists in the Excel file
        if 'Order_Qty' in rules_df.columns:
            rules_df = rules_df.rename(
                columns={'Order_Qty': 'Order In Quantities'})

        # Refresh descriptions/categories from catalog to keep them synced
        rules_df = rules_df.drop(
            columns=['Description', 'Reporting Category'], errors='ignore')
        rules_df = pd.merge(
            rules_df, catalog[['SKU', 'Description', 'Reporting Category']], on='SKU', how='left')

        # Ensure our new column name exists, if not, default to 1
        if 'Order In Quantities' not in rules_df.columns:
            rules_df['Order In Quantities'] = 1
    else:
        # Create brand new matrix from catalog
        rules_df = catalog.copy()
        rules_df['Order In Quantities'] = 1  # Initialize all to 1

    # 4. Ensure all store columns exist with default values
    for code in store_map.values():
        if f'{code}_DNO' not in rules_df.columns:
            rules_df[f'{code}_DNO'] = False
        if f'{code}_Min' not in rules_df.columns:
            rules_df[f'{code}_Min'] = 1
        if f'{code}_Max' not in rules_df.columns:
            rules_df[f'{code}_Max'] = 2

    # 5. Add any brand new SKUs found in catalog
    existing_skus = set(rules_df['SKU'].tolist())
    new_items = catalog[~catalog['SKU'].isin(existing_skus)].copy()

    if not new_items.empty:
        new_items['Order In Quantities'] = 1  # New items default to 1
        for code in store_map.values():
            new_items[f'{code}_DNO'] = False
            new_items[f'{code}_Min'] = 1
            new_items[f'{code}_Max'] = 2
        rules_df = pd.concat([rules_df, new_items], ignore_index=True)

    # 6. Final Column Sort & Save
    # We filter matrix_columns to ensure we don't grab columns that don't exist
    final_cols = [c for c in matrix_columns if c in rules_df.columns]
    rules_df = rules_df[final_cols]

    rules_df.to_excel(RULES_MATRIX_PATH, index=False)
    print(f"Success! Matrix updated at {RULES_MATRIX_PATH}")


if __name__ == "__main__":
    sync_rules_matrix()
