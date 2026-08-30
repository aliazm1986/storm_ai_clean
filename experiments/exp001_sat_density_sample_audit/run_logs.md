# Run Logs - exp001_sat_density_sample_audit

## Purpose
Inspect representative samples from all five satellites before any cleaning,
resampling, averaging, gap filling, merging, or calibration.

## Execution policy
- Status: IN_PROGRESS
- Run and inspect one substep at a time.
- Do not continue until the previous output is reviewed and approved.
- Start with small representative samples.
- Do not modify the raw ZIP or source CSV files.

## Required audit
1. Identify the actual schema of each satellite.
2. Record the source timestamp timezone status. UTC is not confirmed by source
   documentation yet.
3. Identify density, latitude, longitude, and altitude columns without
   fabricating fields whose source is unknown.
4. Record physical units and missing-value conventions.
5. Compare schemas, units, and sampling intervals across satellites.
6. Determine whether cross-satellite calibration is required.

## Proposed base table
| order | column | definition |
|---:|---|---|
| 1 | id | Unique and reproducible row identifier |
| 2 | satellite | Satellite or mission identifier |
| 3 | datetime | Canonical timestamp value; timezone semantics must be recorded |
| 4 | time | Canonical time representation derived only after timestamp policy is accepted |
| 5 | density | Thermospheric density; source unit must be verified |
| 6 | latitude | Latitude; coordinate frame and unit must be verified |
| 7 | longitude | Longitude; range and coordinate frame must be verified |
| 8 | altitude | Satellite altitude; reference and unit must be verified |

## Time policy
The canonical base table will use exactly two temporal columns:
- `datetime`
- `time`

`date` is not a canonical output column. A combined timestamp may be generated
internally for validation, sorting, duplicate detection, joins, and indexing.
Until source documentation is supplied, record the status as:
`UTC assumed; source confirmation pending`.

## Current state
- ZIP inspection: PASS
- Number of CSV files: 8119
- Number of satellites: 5
- Substep 1.1: PASS
- Substep 1.2: PASS
- Substep 1.3: NOT_STARTED (remote raw archive not available in this workspace)
- Cleaning: PROHIBITED at this stage
- Resampling and averaging: PROHIBITED at this stage
- Calibration decision: PENDING
- [2026-08-10 11:34:44] Substep 1.2 START: controlled one-file-per-satellite sample audit.
- [2026-08-10 11:34:44] Source archive: D:\Azami_data\Phase1\sat_density\sat_density (1).zip
- [2026-08-10 11:34:44] Output directory: D:\storm_ai_clean\experiments\exp001_sat_density_sample_audit\outputs\samples
- [2026-08-10 11:34:45] CSV entries discovered in ZIP: 8119
- [2026-08-10 11:34:45] Selected sample for satellite=champ : champ_-00000-20000802_to_20000805.csv
- [2026-08-10 11:34:45] Selected sample for satellite=grace1 : grace1-02285-20021110_to_20021113.csv
- [2026-08-10 11:34:46] Selected sample for satellite=grace2 : grace2-02358-20020502_to_20020505.csv
- [2026-08-10 11:34:46] Selected sample for satellite=swarma : swarma-06672-20140103_to_20140106.csv
- [2026-08-10 11:34:46] Selected sample for satellite=gr-of1 : gr-of1-04265-20180601_to_20180604.csv
- [2026-08-10 11:34:46] Wrote sample manifest: D:\storm_ai_clean\experiments\exp001_sat_density_sample_audit\outputs\samples\substep_1_2_sample_manifest.csv
- [2026-08-10 11:34:46] Wrote column summary: D:\storm_ai_clean\experiments\exp001_sat_density_sample_audit\outputs\samples\substep_1_2_column_summary.csv
- [2026-08-10 11:34:46] Wrote row summary: D:\storm_ai_clean\experiments\exp001_sat_density_sample_audit\outputs\samples\substep_1_2_row_summary.csv
- [2026-08-10 11:34:46] Wrote sample previews: D:\storm_ai_clean\experiments\exp001_sat_density_sample_audit\outputs\samples\substep_1_2_sample_previews.txt
- [2026-08-10 11:34:46] Substep 1.2 END: selected=5 missing=0
--------------------------
## Substep 1.2 — Controlled one-file-per-satellite sample audit

Status: PASS

Observed facts:
- One CSV sample was selected for each target satellite: champ, grace1, grace2, swarma, gr-of1.
- All five selected samples have status=selected.
- matched_count values:
  - champ: 2285
  - grace1: 117
  - grace2: 2964
  - swarma: 1447
  - gr-of1: 1306
- All five samples have the same two-column schema:
  - Timestamp
  - Orbit Mean Density (kg/m^3)
- Time detection mode was single_timestamp_column for all samples.
- Detected time column was Timestamp for all samples.
- parse_fail_count was 0 for all samples.
- Sample row counts were 432 or 433 rows.

Interpretation:
- The controlled samples confirm that the target satellite CSV files are readable and have a consistent basic schema at the sample level.
- The row count pattern is consistent with approximately 10-minute cadence over roughly three days.
- This does not yet prove that all 8119 CSV files share the same schema or cadence.

Artifacts:
- outputs/samples/substep_1_2_sample_manifest.csv
- outputs/samples/substep_1_2_column_summary.csv
- outputs/samples/substep_1_2_row_summary.csv
- outputs/samples/substep_1_2_sample_previews.txt

Boundary:
- No cleaning, resampling, merging, feature engineering, or unit conversion was performed.
#------------
Substep 1.1: PASS
Metadata-only archive inventory identified all five satellites.

Substep 1.2: PASS
Controlled one-file-per-satellite sample audit confirmed readable files, consistent two-column schema, valid timestamp parsing, and plausible row counts.
#-------------

## Reconciliation note — 2026-08-30

The historical header above originally said `NOT STARTED`; it is preserved in
the dated execution history but the current experiment status is
`IN_PROGRESS`. The five-satellite sample artifacts are authoritative for
substep 1.2 only. `satellite_time_summary.csv`,
`filename_parse_failures.csv`, and `satellite_sample_summary.txt` are retained
as `STALE/LEGACY` outputs and must not be used for current scientific
conclusions. The compact `satellite_summary_table.csv` and
`satellite_sample_summary_all_archives.txt` are the newer inventory/sample
artifacts, but their data-derived ranges were produced with a row limit and
are not a full-archive time audit.

The next gate is substep 1.3. It must run on the remote raw ZIP, first in
pilot mode and then in full mode after the pilot output is reviewed. Required
outputs are not present in this local snapshot, so substep 1.3 is not
complete.
