# src/data/cleaning/__init__.py
# =============================================================================
# Cleaning Package
# =============================================================================
# Makes src/data/cleaning/ a Python package.
#
# Exposes the canonical module list so run_all_cleaning.py can
# iterate over them programmatically.
#
# MODULE EXECUTION ORDER (data dependency order):
#   1. clean_sku_master           — no upstream dependencies
#   2. clean_warehouses           — no upstream dependencies
#   3. clean_event_calendar       — no upstream dependencies
#   4. clean_daily_demand         — joins on sku_master for category
#   5. clean_warehouse_costs      — depends on clean warehouses
#   6. clean_starting_inventory   — depends on clean warehouses + sku_master
# =============================================================================

CLEANING_MODULES_IN_ORDER = [
    'clean_sku_master',
    'clean_warehouses',
    'clean_event_calendar',
    'clean_daily_demand',
    'clean_warehouse_costs',
    'clean_starting_inventory',
]
