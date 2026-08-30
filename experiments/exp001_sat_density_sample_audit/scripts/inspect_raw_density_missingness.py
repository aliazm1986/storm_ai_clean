#!/usr/bin/env python3
"""Inspect missing density positions directly inside the raw STORM-AI ZIP."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

TIMESTAMP_CANDIDATES = ("timestamp", "datetime", "date_time", "time", "utc", "date")
DENSITY_CANDIDATES = (
    "orbit mean density (kg/m^3)",
    "orbit mean density (kg/mÂ³)",
    "orbit_mean_density",
    "density",
)
CHUNK_SIZE = 50_000


def find_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {column.strip().lower(): column for column in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_member(zf: zipfile.ZipFile, member: str) -> dict[str, Any] | None:
    with zf.open(member, "r") as stream:
        header = pd.read_csv(stream, nrows=0)
        columns = [str(column) for column in header.columns]
    density_col = find_column(columns, DENSITY_CANDIDATES)
    timestamp_col = find_column(columns, TIMESTAMP_CANDIDATES)
    if density_col is None:
        return {
            "archive_member": member, "timestamp_column": timestamp_col or "",
            "density_column": "", "row_count": 0, "missing_density_count": 0,
            "missing_fraction": "", "leading_missing_count": "",
            "interior_missing_count": "", "trailing_missing_count": "",
            "all_density_missing": False, "longest_missing_run": "",
            "first_missing_timestamp": "", "last_missing_timestamp": "",
            "status": "CHECK", "error_type": "missing_density_column",
            "error_message": "No recognized density column.",
        }

    total = missing = 0
    first_valid = last_valid = None
    longest_run = current_run = 0
    first_missing_timestamp = last_missing_timestamp = ""
    row_index = 0
    with zf.open(member, "r") as stream:
        reader = pd.read_csv(stream, chunksize=CHUNK_SIZE)
        for frame in reader:
            values = frame[density_col]
            missing_mask = values.isna() | values.astype(str).str.strip().eq("")
            for offset, is_missing in enumerate(missing_mask.tolist()):
                index = row_index + offset
                total += 1
                if is_missing:
                    missing += 1
                    current_run += 1
                    longest_run = max(longest_run, current_run)
                    if timestamp_col:
                        value = frame.iloc[offset][timestamp_col]
                        if not pd.isna(value):
                            stamp = pd.Timestamp(value).isoformat()
                            first_missing_timestamp = first_missing_timestamp or stamp
                            last_missing_timestamp = stamp
                else:
                    current_run = 0
                    if first_valid is None:
                        first_valid = index
                    last_valid = index
            row_index += len(frame)

    if not missing:
        return None
    leading = first_valid if first_valid is not None else total
    trailing = (total - 1 - last_valid) if last_valid is not None else 0
    interior = missing - leading - trailing
    return {
        "archive_member": member, "timestamp_column": timestamp_col or "",
        "density_column": density_col, "row_count": total,
        "missing_density_count": missing,
        "missing_fraction": missing / total if total else "",
        "leading_missing_count": leading, "interior_missing_count": interior,
        "trailing_missing_count": trailing, "all_density_missing": first_valid is None,
        "longest_missing_run": longest_run,
        "first_missing_timestamp": first_missing_timestamp,
        "last_missing_timestamp": last_missing_timestamp,
        "status": "CHECK", "error_type": "density_missing",
        "error_message": "Missing density positions classified from raw CSV rows.",
    }


def run(zip_path: Path, output_dir: Path) -> dict[str, Any]:
    started = datetime.now().astimezone().isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(zip_path) as zf:
        members = sorted(
            info.filename for info in zf.infolist()
            if not info.is_dir() and info.filename.lower().endswith(".csv")
        )
        for index, member in enumerate(members, start=1):
            result = inspect_member(zf, member)
            if result is not None:
                rows.append(result)
            if index % 500 == 0:
                print(f"scanned_csv_members={index}/{len(members)}")

    rows.sort(key=lambda row: row["archive_member"])
    detail = output_dir / "density_missingness_raw_by_file.csv"
    columns = [
        "archive_member", "timestamp_column", "density_column", "row_count",
        "missing_density_count", "missing_fraction", "leading_missing_count",
        "interior_missing_count", "trailing_missing_count", "all_density_missing",
        "longest_missing_run", "first_missing_timestamp", "last_missing_timestamp",
        "status", "error_type", "error_message",
    ]
    with detail.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    by_position = defaultdict(lambda: {"files": 0, "values": 0})
    for row in rows:
        for position in ("leading", "interior", "trailing"):
            count = int(row[f"{position}_missing_count"])
            if count:
                by_position[position]["files"] += 1
                by_position[position]["values"] += count

    summary = {
        "status": "CHECK" if rows else "PASS",
        "zip_path": str(zip_path), "zip_sha256": sha256(zip_path),
        "csv_members_scanned": len(members),
        "files_with_missing_density": len(rows),
        "missing_density_values": sum(int(row["missing_density_count"]) for row in rows),
        "position_summary": dict(by_position),
        "all_density_missing_files": sum(bool(row["all_density_missing"]) for row in rows),
        "started_at": started, "finished_at": datetime.now().astimezone().isoformat(),
        "python_version": platform.python_version(),
    }
    summary_path = output_dir / "density_missingness_raw_summary.json"
    summary["outputs"] = {
        "density_missingness_raw_by_file.csv": str(detail),
        "density_missingness_raw_report.md": str(output_dir / "density_missingness_raw_report.md"),
        "density_missingness_raw_summary.json": str(summary_path),
        "density_missingness_raw_run_log.md": str(output_dir / "density_missingness_raw_run_log.md"),
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    report = [
        "# Raw density missingness report", "",
        f"- Status: `{summary['status']}`",
        f"- CSV members scanned: `{summary['csv_members_scanned']}`",
        f"- Files with missing density: `{summary['files_with_missing_density']}`",
        f"- Missing density values: `{summary['missing_density_values']}`", "",
        "## Position classification", "",
        "| Position | Affected files | Missing values |",
        "|---|---:|---:|",
    ]
    for position in ("leading", "interior", "trailing"):
        item = by_position[position]
        report.append(f"| `{position}` | {item['files']} | {item['values']} |")
    report.extend([
        "", "- `leading`: before the first valid density.",
        "- `interior`: between valid density values.",
        "- `trailing`: after the last valid density.",
        "- Raw ZIP members were read-only; no imputation or deletion was performed.",
    ])
    (output_dir / "density_missingness_raw_report.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )
    log = [
        "# Raw density missingness run log", "",
        f"- Started: `{summary['started_at']}`",
        f"- Finished: `{summary['finished_at']}`",
        f"- ZIP: `{zip_path}`", f"- ZIP SHA-256: `{summary['zip_sha256']}`",
        f"- CSV members scanned: `{summary['csv_members_scanned']}`",
        f"- Files with missing density: `{summary['files_with_missing_density']}`",
        f"- Missing density values: `{summary['missing_density_values']}`", "",
        "The raw ZIP was not modified. No imputation, deletion, or resampling was performed.",
        "", "## Outputs", "",
    ]
    log.extend(f"- `{path}`" for path in summary["outputs"].values())
    (output_dir / "density_missingness_raw_run_log.md").write_text(
        "\n".join(log) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip-path", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if not args.zip_path.is_file():
        raise SystemExit(f"ZIP not found: {args.zip_path}")
    summary = run(args.zip_path, args.output_dir)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
