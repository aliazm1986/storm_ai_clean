# STORM-AI Clean Research Repo

This is the canonical, clean, sample-first preprocessing and modeling workspace
for the STORM-AI satellite-density forecasting task. The older
`storm_ai_project-main` tree is retained only as a legacy/reference source; it
is not an executable continuation of this project.

## Current verified state (2026-08-30)

- `exp000_data_inventory`: `PASS` (metadata inventory and ZIP discovery).
- `exp001_sat_density_sample_audit`: `IN_PROGRESS`.
  - substep 1.1: `PASS`
  - substep 1.2: `PASS` (one controlled sample per target satellite)
  - substep 1.3: `NOT_STARTED` (full archive audit is blocked until the remote
    raw ZIP is available).
- `exp002` through `exp008`: `PLANNED`; none has been executed.

The substep 1.2 result is limited to five sampled CSV files. It confirms a
two-column sample schema (`Timestamp` and `Orbit Mean Density (kg/m^3)`),
zero timestamp parse failures in those samples, and approximately ten-minute
cadence. It must not be generalized to all 8,119 CSV members.

## Validation gates

The pipeline is intentionally staged:

1. inventory;
2. controlled sample audit;
3. full schema/time/cadence/duplicate/overlap audit;
4. base time-series table;
5. density/geospatial validation;
6. conditional calibration;
7. space-weather join;
8. physical QC, gap handling, resampling, and final model table.

No cleaning, imputation, merging, resampling, feature engineering, or modeling
may start before the preceding gate is reviewed and accepted. Raw data remains
read-only and is never committed to Git.

## Canonical data decisions

- Canonical temporal fields are `datetime` and `time`; `date` is not a
  canonical output column.
- The source has not yet documented timezone semantics. Until evidence is
  supplied, record: `UTC assumed; source confirmation pending`.
- The source of `latitude`, `longitude`, and `altitude` has not been identified.
  These fields must not be fabricated.
- Every future model row must receive a reproducible unique `id`.

The durable reconciliation record is
`docs/00_project_control/canonical_status.md`. The experiment registry is the
source of truth for stage status.

## Generated artifacts and legacy outputs

Authoritative current sample artifacts are under
`experiments/exp001_sat_density_sample_audit/outputs/samples/`, especially the
`substep_1_2_*` files and `satellite_sample_summary_all_archives.txt`.

The following files are retained for traceability but are `STALE/LEGACY` and
must not be used for scientific conclusions until regenerated:

- `satellite_time_summary.csv` and its Markdown/JSON companions;
- `filename_parse_failures.csv`;
- `satellite_sample_summary.txt`;
- the old `exp000_ingest` log/artifacts when they conflict with the canonical
  `exp000_data_inventory` records.

Their presence does not mean that substep 1.3 or any later experiment ran.

## Reproducibility

Scripts accept input and output paths explicitly. The full archive audit
script is
`experiments/exp001_sat_density_sample_audit/scripts/full_archive_schema_time_audit.py`.
Run it in `pilot` mode first on the remote system, inspect the generated
outputs, and only then run `full` mode. The local workspace intentionally does
not execute the remote full audit.
