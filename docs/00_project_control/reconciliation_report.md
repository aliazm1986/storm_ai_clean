# Reconciliation Report — 2026-08-30

This report records the state observed before the documentation/code
reconciliation and the reason for each change. It does not claim that the
remote raw archive audit ran in this workspace.

The Git row below is the pre-change baseline. The current repository state is
recorded in `canonical_status.md`.

## Before-change findings

| Path / item | Observed state | Classification | Reason for action |
|---|---|---|---|
| `README.md` | Said only `exp000_data_inventory` was current and all later work had not started. | STALE documentation | Update to the verified `exp001.1/1.2` state and explicit gates. |
| `docs/03_experiments/experiment_registry.csv` | One row: `exp000` with status `planned`. | STALE registry | Record canonical stage names, PASS/IN_PROGRESS/PLANNED/LEGACY distinctions, and blockers. |
| `experiments/exp001_sat_density_sample_audit/run_logs.md` | Header said `NOT STARTED`, later dated entries documented substep 1.2 PASS; temporal schema used `date`. | Contradictory/stale header | Reconcile current status while preserving dated history; use `datetime`/`time`. |
| `experiments/exp000_data_inventory/` | Contains the canonical inventory code and newer compact five-satellite artifacts. | PASS, with row-limit caveat | Keep as the authoritative inventory source; do not merge with `exp000_ingest`. |
| `experiments/exp000_ingest/run_logs.md` | Historical PASS log with sample-based ranges. | LEGACY/REFERENCE | Label its status so it cannot override the canonical inventory. |
| `satellite_summary_table.csv` | Newer compact five-satellite summary; values read with a row limit. | Current but limited | Cite as inventory evidence only, not full coverage. |
| `satellite_time_summary.csv` | 5,835 rows and old filename grouping behavior. | STALE/LEGACY | Retain and mark unusable for current scientific conclusions. |
| `filename_parse_failures.csv` | Produced by the older parser with many naming failures. | STALE/LEGACY | Retain as diagnostic history; replace logic with explicit parser in substep 1.3. |
| `satellite_sample_summary.txt` | CHAMP-only summary. | STALE/LEGACY | Prefer the all-archives/five-satellite companion. |
| `satellite_sample_summary_all_archives.txt` | Five-satellite sample companion. | Current sample evidence | Keep as a sample-scoped artifact. |
| Git state | No `.git` directory, branch, remote, or commit history in the clean snapshot. | Uninitialized | Initialize a repository/branch only after the requested files are ready; upload requires a remote URL and credentials. |

## Applied policy

No raw ZIP or derived large data file is added to Git. No old output is
deleted or silently renamed. The full audit script accepts explicit paths,
keeps timezone-naive timestamps timezone-naive, and separates interval coverage
overlap from actual timestamp overlap.
