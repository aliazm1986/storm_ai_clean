# STORM-AI Canonical Status and Reconciliation

Updated: 2026-08-30

## Repository authority

- Canonical working tree: `storm_ai_clean`.
- `storm_ai_project-main`: `STALE/LEGACY` reference material only. It is not
  the continuation from which new experiments should be run.
- A new, independent Git repository was initialized at this canonical root on
  2026-08-30 with the `main` branch. It has no commits and no configured
  remote yet; raw data remains excluded from version control.

## Verified stage state

| Stage | Status | Evidence / boundary |
|---|---|---|
| `exp000_data_inventory` | PASS | Recorded inventory and ZIP inspection artifacts. |
| `exp000_ingest` | LEGACY | Historical log/artifacts; naming is not the canonical implementation. |
| `exp001.1` | PASS | Metadata-only inventory identified 8,119 CSV members and five target labels. |
| `exp001.2` | PASS | Five controlled samples, one per satellite; two columns and zero sample parse failures. |
| `exp001.3` | NOT_STARTED | Full raw ZIP is remote; no full audit outputs are present in this workspace. |
| `exp002`–`exp008` | PLANNED | Blocked by the stage gates above and unresolved source metadata. |

The `PASS` claim for substep 1.2 is sample-scoped. It does not establish that
all 8,119 members share the same schema, cadence, timestamp quality, or
missingness.

## Data and time decisions

- Canonical temporal schema: `datetime`, `time`.
- `date` is not a canonical column.
- UTC status: `UTC assumed; source confirmation pending`.
  No timezone conversion or UTC assertion may be made until source
  documentation confirms it.
- The source of `latitude`, `longitude`, and `altitude` is unresolved. Do not
  create or impute those columns from filename guesses.
- Every future model row must have a reproducible unique `id`.
- `requirements.txt` names `pandas` and `numpy` without version pins. This
  reproducibility gap is recorded here; it is not silently expanded or
  rewritten.

## Artifact classification

| Artifact | Current classification | Rule |
|---|---|---|
| `exp000_data_inventory/outputs/sat_density_inspection/satellite_summary_table.csv` | Current inventory | Compact five-satellite summary; row-limited data ranges remain sample-derived. |
| `exp001_sat_density_sample_audit/outputs/samples/substep_1_2_*` | Current sample audit | Valid only for the five selected files. |
| `satellite_sample_summary_all_archives.txt` | Current sample/inventory companion | Five-satellite companion output; not a full schema audit. |
| `satellite_time_summary.csv` (+ Markdown/JSON) | STALE/LEGACY | Older parser grouped file IDs as satellite names. |
| `filename_parse_failures.csv` | STALE/LEGACY | Produced by the older parser; regenerate with the explicit parser. |
| `satellite_sample_summary.txt` | STALE/LEGACY | CHAMP-only/older summary. |
| `exp000_ingest/run_logs.md` | STALE/LEGACY record | Preserve, but use the canonical registry and `exp000_data_inventory` evidence. |

Legacy artifacts are not deleted so paths remain traceable. Their names and
status must be kept visible in reports and they must not support scientific
conclusions.

## Full-audit boundary

Substep 1.3 must inspect the remote `sat_density (1).zip` in two separate
runs: a pilot covering all five satellites plus a deliberately difficult or
unclassified filename, followed only after review by a full run. The local
workspace must not claim pilot/full execution without the corresponding
observed outputs.

The reproducible implementation and its tests are under
`experiments/exp001_sat_density_sample_audit/scripts/` and `tests/`.
