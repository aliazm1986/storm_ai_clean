# Remote commands for substep 1.3

Run these commands in the remote VS Code terminal that can access the raw ZIP.
Replace only the two path variables. Do not add the ZIP or extracted CSVs to
Git.

```powershell
$Project = "C:\path\to\storm_ai_clean"
$Zip = "C:\path\to\sat_density (1).zip"
$Audit = Join-Path $Project "experiments\exp001_sat_density_sample_audit\scripts\full_archive_schema_time_audit.py"
$PilotOut = Join-Path $Project "experiments\exp001_sat_density_sample_audit\outputs\substep_1_3_pilot"

Set-Location $Project
python --version
python -c "import pandas, numpy; print('pandas', pandas.__version__); print('numpy', numpy.__version__)"
Get-FileHash -Algorithm SHA256 -LiteralPath $Zip
Get-Item -LiteralPath $Zip | Select-Object FullName,Length

python $Audit pilot --zip-path $Zip --output-dir $PilotOut
Get-Content -LiteralPath (Join-Path $PilotOut "audit_run_log.md")
Import-Csv -LiteralPath (Join-Path $PilotOut "full_file_schema_time_audit.csv") |
  Format-Table satellite,archive_member,file_status,column_count,row_count,
  parse_fail_count,monotonicity_status,cadence_median_seconds,
  density_numeric_fail_count,density_nan_count,density_nonpositive_count
Get-Content -LiteralPath (Join-Path $PilotOut "audit_run_summary.json")
```

Stop after the pilot and return the five output files plus the terminal summary
for review. The pilot must contain all five target satellites and a difficult
name (`gr-of1` is the deterministic difficult case; an unclassified member is
also selected when present).

Only after pilot review is explicitly accepted:

```powershell
$FullOut = Join-Path $Project "experiments\exp001_sat_density_sample_audit\outputs\substep_1_3_full"
python $Audit full --zip-path $Zip --output-dir $FullOut
Get-Content -LiteralPath (Join-Path $FullOut "audit_run_log.md")
Get-Content -LiteralPath (Join-Path $FullOut "audit_run_summary.json")
```

The full run is successful only if all discovered CSV members are audited and
the resulting files are inspected. Do not update the registry to
`substep 1.3: PASS` from the command's existence or exit code alone.
