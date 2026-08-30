# exp000_data_inventory

Purpose:
Scan the raw data folder and create a human-readable and machine-readable inventory.

This experiment does not:
- clean data
- merge data
- resample data
- impute data
- build model tables

Outputs:
- `outputs/inventory.csv`
- `outputs/audit_report.json`
- `outputs/human_preview.md`

Gate:
Continue only after inspecting the outputs.
