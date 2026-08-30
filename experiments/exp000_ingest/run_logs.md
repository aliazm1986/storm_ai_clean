# Run Logs - exp000_ingest

Execution logs for ingest, inventory, ZIP inspection, and related preprocessing steps.

> **LEGACY/REFERENCE record.** The canonical inventory implementation is
> `experiments/exp000_data_inventory/`. This historical log is retained for
> traceability and must not silently override the canonical registry.

---

## 2026-08-04 - sat_density ZIP satellite inspection

Status: PASS

Summary:

- CSV files: 8119
- Satellites: 5
- Read errors: 0
- Parse failures: 0
- Previous issue: satellite CSV files were hidden inside `sat_density (1).zip`.

| satellite | n_csv_files | start_from_data | end_from_data | status |
|---|---:|---|---|---|
| champ | 2285 | 2000-08-02T04:50:40 | 2010-07-30T13:03:40 | OK |
| grace2 | 2964 | 2002-05-02T03:51:30 | 2016-08-30T18:31:10 | OK |
| grace1 | 117 | 2002-11-10T09:20:00 | 2017-06-05T22:10:00 | OK |
| swarma | 1447 | 2014-01-03T00:00:00 | 2019-12-31T08:10:00 | OK |
| gr-of1 | 1306 | 2018-06-01T09:44:50 | 2020-12-30T18:50:00 | OK |

Note: data-derived time ranges are sample-based because inspection used limited rows per CSV.
