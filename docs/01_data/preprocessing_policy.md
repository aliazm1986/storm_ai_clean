# Preprocessing Policy

## Stage Order

1. Inventory raw files.
2. Select a small sample.
3. Build standard time dataframe.
4. Add density and geospatial fields.
5. Add space-weather fields.
6. Audit satellite/platform identity.
7. Apply calibration only if multiple satellites require it.
8. Apply physical quality control.
9. Apply missingness handling and imputation.
10. Resample or aggregate only after earlier stages pass.

## Rules

- Raw files are read-only.
- Every row in model-building datasets must have an `id`.
- Every sample must preserve `File ID`.
- No full-dataset processing before sample processing passes.
- No cleaning before raw values are inspected.
- No imputation before missingness is measured.
- No satellite mixing before satellite identity is audited.
