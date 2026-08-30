# Substep 1.3 Audit Design

Updated: 2026-08-30

## Existing implementation before reconciliation

The previous `experiments/exp000_data_inventory/inspect_sat_density_satellites.py`
was useful for the initial inventory and for the recorded five-satellite
sample summary. It is not a full substep-1.3 auditor:

- its default `row_limit=50` makes data-derived ranges sample-derived;
- its fallback parser guesses a satellite from a filename prefix and produced
  the known GRACE-FO/file-ID grouping problem;
- it emits neither per-file cadence/duplicate/density-quality fields nor the
  required two-domain overlap table;
- it does not provide a pilot/full execution boundary or a documented
  timezone-key policy.

The historical `satellite_time_summary.csv` and
`filename_parse_failures.csv` are therefore `STALE/LEGACY`.

## Current contract

`experiments/exp001_sat_density_sample_audit/scripts/full_archive_schema_time_audit.py`
is the replacement. It:

1. accepts an explicit ZIP path and output directory;
2. reads CSV members through `zipfile` and pandas chunks without extracting the
   archive;
3. uses explicit known satellite filename forms and reports other names as
   `unclassified`;
4. records the required per-file schema, timestamp, cadence, duplicate,
   density-quality, and error fields;
5. continues after a bad member and records that member's error;
6. writes the five required output artifacts;
7. separates interval coverage overlap from exact timestamp overlap;
8. reports within-satellite file pairs and cross-satellite aggregate pairs;
9. preserves timezone-naive values as naive and only normalizes aware values to
   UTC nanoseconds for comparison.

The pilot selects one deterministic member for each of the five target
satellites. The GRACE-FO (`gr-of1`) member is deliberately included as the
hyphenated/difficult naming case; an unclassified member is added when one is
available. `full` mode is a separate command and must not be run until the
pilot outputs have been reviewed.

## Acceptance boundary

The script's local synthetic tests passing proves only that the implementation
contract works on fixtures. It does not make the remote archive audit PASS.
The experiment remains `substep 1.3: NOT_STARTED` until the remote pilot and
then full output are returned and reviewed.
