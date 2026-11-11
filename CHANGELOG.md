# Changelog

## 2.0.0

### Fixed
- Vendor cost/units in store tabs are now computed from whole cases (cases x case pack), so they match the consolidated summary; editing `Order (Cases)` now updates units and cost.
- Consolidated summary now reflects edits made in the store tabs (use the new **Refresh summary** button after editing).
- **Push Allocations** now actually gates allocations: only pushed (snapshotted) values reach the store tabs. Allocations reset when the catalog, HQ threshold, vendors or store selection change.
- A store missing from a vendor's rules sheet (`_DNO` / `_Min` / `_Max`) no longer crashes the page; it orders nothing and shows a warning.
- Blank-SKU rows are dropped from the catalog, rules sheets and reserved-stock sheet so they can't match each other.
- Failure to load the reserved-stock sheet now stops the app unless explicitly overridden, and the Load button refreshes that sheet too.
- Blank or invalid quantities in the editable tables no longer crash the Excel export or silently drop items.

### Changed
- `ordering.py` split into `compute_store_needs` + `apply_hq_suggestions` (needs are computed once per store per run instead of twice); `compute_store_order` still composes them.
- Consolidated filename uses `N_vendors` when more than 3 vendors are selected; the date uses America/New_York.
- Unmatched-SKU console dump no longer filters the catalog once per SKU.
- Vendor table: only `Order (Cases)` is editable.

### Added
- `tests/` pytest suite for the ordering logic, `requirements-dev.txt`, this changelog.
