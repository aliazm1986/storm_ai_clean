# substep_1_2_controlled_sample_audit.ps1
# Purpose:
#   Controlled sample audit for STORM-AI satellite density CSV archive.
#   Extract exactly one CSV file per target satellite and inspect raw structure.
#
# Scope:
#   - No cleaning
#   - No resampling
#   - No merging
#   - No feature engineering
#   - No unit conversion
#
# Expected archive:
#   D:\Azami_data\Phase1\sat_density\sat_density (1).zip

$ErrorActionPreference = "Stop"

# -----------------------------
# Configuration
# -----------------------------

$ZipPath = "D:\Azami_data\Phase1\sat_density\sat_density (1).zip"

$ExperimentRoot = "D:\storm_ai_clean\experiments\exp001_sat_density_sample_audit"
$OutputRoot = Join-Path $ExperimentRoot "outputs\samples"
$TempExtractRoot = Join-Path $OutputRoot "_temp_extracted_samples"

$SampleManifestPath = Join-Path $OutputRoot "substep_1_2_sample_manifest.csv"
$ColumnSummaryPath = Join-Path $OutputRoot "substep_1_2_column_summary.csv"
$RowSummaryPath = Join-Path $OutputRoot "substep_1_2_row_summary.csv"
$PreviewTextPath = Join-Path $OutputRoot "substep_1_2_sample_previews.txt"
$RunLogPath = Join-Path $ExperimentRoot "run_logs.md"

$TargetSatellites = @(
    "champ",
    "grace1",
    "grace2",
    "swarma",
    "gr-of1"
)

# Filename matching policy:
# We keep this intentionally conservative and transparent.
# Each target satellite is matched against the ZIP entry filename.
$SatellitePatterns = @{
    "champ"  = "(?i)(^|[/\\])champ[_\-]"
    "grace1" = "(?i)(^|[/\\])grace1[_\-]"
    "grace2" = "(?i)(^|[/\\])grace2[_\-]"
    "swarma" = "(?i)(^|[/\\])swarma[_\-]"
    "gr-of1" = "(?i)(^|[/\\])gr-of1[_\-]"
}

# -----------------------------
# Helpers
# -----------------------------

function Ensure-Directory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Write-Log {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $RunLogPath -Value "- [$Timestamp] $Message"
}

function Get-SafeFileName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $Safe = $Name -replace "[:*?""<>|]", "_"
    $Safe = $Safe -replace "[/\\]", "__"
    return $Safe
}

function Try-Get-DateTimeColumnInfo {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Rows
    )

    $Result = [ordered]@{
        detected_time_mode = ""
        detected_time_columns = ""
        min_timestamp = ""
        max_timestamp = ""
        parse_ok_count = 0
        parse_fail_count = 0
    }

    if ($Rows.Count -eq 0) {
        $Result.detected_time_mode = "no_rows"
        return [PSCustomObject]$Result
    }

    $ColumnNames = $Rows[0].PSObject.Properties.Name

    $DateLikeColumns = @()
    $TimeLikeColumns = @()
    $TimestampLikeColumns = @()

    foreach ($ColumnName in $ColumnNames) {
        if ($ColumnName -match "(?i)^(timestamp|datetime|date_time|utc|epoch)$") {
            $TimestampLikeColumns += $ColumnName
        }
        elseif ($ColumnName -match "(?i)date") {
            $DateLikeColumns += $ColumnName
        }
        elseif ($ColumnName -match "(?i)time") {
            $TimeLikeColumns += $ColumnName
        }
    }

    $ParsedTimes = New-Object System.Collections.Generic.List[datetime]
    $ParseFailCount = 0

    if ($TimestampLikeColumns.Count -gt 0) {
        $Col = $TimestampLikeColumns[0]
        $Result.detected_time_mode = "single_timestamp_column"
        $Result.detected_time_columns = $Col

        foreach ($Row in $Rows) {
            $RawValue = [string]$Row.$Col
            if ([string]::IsNullOrWhiteSpace($RawValue)) {
                $ParseFailCount += 1
                continue
            }

            $Parsed = [datetime]::MinValue
            if ([datetime]::TryParse($RawValue, [ref]$Parsed)) {
                $ParsedTimes.Add($Parsed)
            }
            else {
                $ParseFailCount += 1
            }
        }
    }
    elseif (($DateLikeColumns.Count -gt 0) -and ($TimeLikeColumns.Count -gt 0)) {
        $DateCol = $DateLikeColumns[0]
        $TimeCol = $TimeLikeColumns[0]

        $Result.detected_time_mode = "date_plus_time_columns"
        $Result.detected_time_columns = "$DateCol + $TimeCol"

        foreach ($Row in $Rows) {
            $RawValue = ([string]$Row.$DateCol) + " " + ([string]$Row.$TimeCol)
            if ([string]::IsNullOrWhiteSpace($RawValue)) {
                $ParseFailCount += 1
                continue
            }

            $Parsed = [datetime]::MinValue
            if ([datetime]::TryParse($RawValue, [ref]$Parsed)) {
                $ParsedTimes.Add($Parsed)
            }
            else {
                $ParseFailCount += 1
            }
        }
    }
    else {
        $Result.detected_time_mode = "no_obvious_time_column"
        $Result.detected_time_columns = ""
        $Result.parse_fail_count = $Rows.Count
        return [PSCustomObject]$Result
    }

    $Result.parse_ok_count = $ParsedTimes.Count
    $Result.parse_fail_count = $ParseFailCount

    if ($ParsedTimes.Count -gt 0) {
        $SortedTimes = $ParsedTimes | Sort-Object
        $Result.min_timestamp = $SortedTimes[0].ToString("yyyy-MM-ddTHH:mm:ss")
        $Result.max_timestamp = $SortedTimes[$SortedTimes.Count - 1].ToString("yyyy-MM-ddTHH:mm:ss")
    }

    return [PSCustomObject]$Result
}

# -----------------------------
# Preflight
# -----------------------------

Ensure-Directory -Path $ExperimentRoot
Ensure-Directory -Path $OutputRoot
Ensure-Directory -Path $TempExtractRoot

if (-not (Test-Path -LiteralPath $ZipPath)) {
    throw "ZIP archive not found: $ZipPath"
}

if (-not (Test-Path -LiteralPath $RunLogPath)) {
    New-Item -ItemType File -Path $RunLogPath | Out-Null
}

Write-Log "Substep 1.2 START: controlled one-file-per-satellite sample audit."
Write-Log "Source archive: $ZipPath"
Write-Log "Output directory: $OutputRoot"

# -----------------------------
# Load ZIP entries
# -----------------------------

Add-Type -AssemblyName System.IO.Compression.FileSystem

$Zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)

try {
    $CsvEntries = $Zip.Entries | Where-Object {
        $_.FullName -match "\.csv$" -and $_.Length -gt 0
    }

    Write-Log "CSV entries discovered in ZIP: $($CsvEntries.Count)"

    $ManifestRows = New-Object System.Collections.Generic.List[object]
    $ColumnRows = New-Object System.Collections.Generic.List[object]
    $RowSummaryRows = New-Object System.Collections.Generic.List[object]

    Set-Content -LiteralPath $PreviewTextPath -Value "Substep 1.2 controlled sample previews`r`n"

    foreach ($Satellite in $TargetSatellites) {
        $Pattern = $SatellitePatterns[$Satellite]

        $Matches = $CsvEntries | Where-Object {
            $_.FullName -match $Pattern
        } | Sort-Object FullName

        if ($Matches.Count -eq 0) {
            Write-Log "WARNING: no CSV match found for satellite=$Satellite using pattern=$Pattern"

            $ManifestRows.Add([PSCustomObject]@{
                satellite = $Satellite
                status = "missing"
                zip_entry = ""
                extracted_path = ""
                zip_entry_size_bytes = ""
                matched_count = 0
            })

            continue
        }

        $SelectedEntry = $Matches[0]
        $SafeName = Get-SafeFileName -Name $SelectedEntry.FullName
        $ExtractedPath = Join-Path $TempExtractRoot $SafeName

        if (Test-Path -LiteralPath $ExtractedPath) {
            Remove-Item -LiteralPath $ExtractedPath -Force
        }

        [System.IO.Compression.ZipFileExtensions]::ExtractToFile($SelectedEntry, $ExtractedPath)

        Write-Log "Selected sample for satellite=$Satellite : $($SelectedEntry.FullName)"

        $Rows = Import-Csv -LiteralPath $ExtractedPath
        $RowCount = @($Rows).Count

        $ColumnNames = @()
        if ($RowCount -gt 0) {
            $ColumnNames = $Rows[0].PSObject.Properties.Name
        }

        $TimeInfo = Try-Get-DateTimeColumnInfo -Rows @($Rows)

        $ManifestRows.Add([PSCustomObject]@{
            satellite = $Satellite
            status = "selected"
            zip_entry = $SelectedEntry.FullName
            extracted_path = $ExtractedPath
            zip_entry_size_bytes = $SelectedEntry.Length
            matched_count = $Matches.Count
        })

        $ColumnRows.Add([PSCustomObject]@{
            satellite = $Satellite
            zip_entry = $SelectedEntry.FullName
            n_columns = $ColumnNames.Count
            columns_pipe_separated = ($ColumnNames -join "|")
        })

        $RowSummaryRows.Add([PSCustomObject]@{
            satellite = $Satellite
            zip_entry = $SelectedEntry.FullName
            n_rows = $RowCount
            detected_time_mode = $TimeInfo.detected_time_mode
            detected_time_columns = $TimeInfo.detected_time_columns
            min_timestamp = $TimeInfo.min_timestamp
            max_timestamp = $TimeInfo.max_timestamp
            parse_ok_count = $TimeInfo.parse_ok_count
            parse_fail_count = $TimeInfo.parse_fail_count
        })

        Add-Content -LiteralPath $PreviewTextPath -Value ""
        Add-Content -LiteralPath $PreviewTextPath -Value "============================================================"
        Add-Content -LiteralPath $PreviewTextPath -Value "Satellite: $Satellite"
        Add-Content -LiteralPath $PreviewTextPath -Value "ZIP entry: $($SelectedEntry.FullName)"
        Add-Content -LiteralPath $PreviewTextPath -Value "Extracted path: $ExtractedPath"
        Add-Content -LiteralPath $PreviewTextPath -Value "Matched CSV count for satellite: $($Matches.Count)"
        Add-Content -LiteralPath $PreviewTextPath -Value "Rows in selected sample: $RowCount"
        Add-Content -LiteralPath $PreviewTextPath -Value "Columns: $($ColumnNames -join ', ')"
        Add-Content -LiteralPath $PreviewTextPath -Value "Detected time mode: $($TimeInfo.detected_time_mode)"
        Add-Content -LiteralPath $PreviewTextPath -Value "Detected time columns: $($TimeInfo.detected_time_columns)"
        Add-Content -LiteralPath $PreviewTextPath -Value "Min timestamp: $($TimeInfo.min_timestamp)"
        Add-Content -LiteralPath $PreviewTextPath -Value "Max timestamp: $($TimeInfo.max_timestamp)"
        Add-Content -LiteralPath $PreviewTextPath -Value ""
        Add-Content -LiteralPath $PreviewTextPath -Value "First 5 rows:"

        $PreviewRows = @($Rows | Select-Object -First 5)
        if ($PreviewRows.Count -gt 0) {
            $PreviewText = $PreviewRows | Format-Table -AutoSize | Out-String -Width 300
            Add-Content -LiteralPath $PreviewTextPath -Value $PreviewText
        }
        else {
            Add-Content -LiteralPath $PreviewTextPath -Value "[No rows found in selected sample]"
        }
    }

    $ManifestRows | Export-Csv -LiteralPath $SampleManifestPath -NoTypeInformation -Encoding UTF8
    $ColumnRows | Export-Csv -LiteralPath $ColumnSummaryPath -NoTypeInformation -Encoding UTF8
    $RowSummaryRows | Export-Csv -LiteralPath $RowSummaryPath -NoTypeInformation -Encoding UTF8

    Write-Log "Wrote sample manifest: $SampleManifestPath"
    Write-Log "Wrote column summary: $ColumnSummaryPath"
    Write-Log "Wrote row summary: $RowSummaryPath"
    Write-Log "Wrote sample previews: $PreviewTextPath"

    $SelectedCount = ($ManifestRows | Where-Object { $_.status -eq "selected" }).Count
    $MissingCount = ($ManifestRows | Where-Object { $_.status -eq "missing" }).Count

    Write-Log "Substep 1.2 END: selected=$SelectedCount missing=$MissingCount"

    Write-Host ""
    Write-Host "Substep 1.2 completed."
    Write-Host "Selected samples: $SelectedCount"
    Write-Host "Missing satellites: $MissingCount"
    Write-Host ""
    Write-Host "Outputs:"
    Write-Host "  $SampleManifestPath"
    Write-Host "  $ColumnSummaryPath"
    Write-Host "  $RowSummaryPath"
    Write-Host "  $PreviewTextPath"
    Write-Host "  $RunLogPath"
}
finally {
    if ($null -ne $Zip) {
        $Zip.Dispose()
    }
}
