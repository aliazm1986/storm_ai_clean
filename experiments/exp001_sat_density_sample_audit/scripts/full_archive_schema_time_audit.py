#!/usr/bin/env python3
"""Member-level schema/time audit for the STORM-AI density ZIP."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import platform
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


TARGET_SATELLITES = ("champ", "grace1", "grace2", "swarma", "gr-of1")
CSV_SUFFIX = ".csv"
CHUNK_SIZE = 50_000
SATELLITE_ALIASES = {
    "champ": "champ",
    "grace1": "grace1",
    "grace2": "grace2",
    "swarma": "swarma",
    "swarm-a": "swarma",
    "swarm_a": "swarma",
    "gr-of1": "gr-of1",
    "grace-fo1": "gr-of1",
    "gracefo1": "gr-of1",
}
TIMESTAMP_CANDIDATES = ("timestamp", "datetime", "date_time", "time", "utc", "date")
DENSITY_CANDIDATES = (
    "orbit mean density (kg/m^3)",
    "orbit mean density (kg/m³)",
    "orbit_mean_density",
    "density",
)
_FILENAME_PATTERN = re.compile(
    r"^(?P<satellite>champ|grace1|grace2|swarma|swarm-a|swarm_a|"
    r"gr-of1|grace-fo1|gracefo1)(?:_|-)"
    r"(?P<file_id>-?\d+)-(?P<start>\d{8})_to_(?P<end>\d{8})\.csv$",
    re.IGNORECASE,
)

AUDIT_COLUMNS = [
    "file_path", "archive_member", "satellite", "file_size_bytes", "header_status",
    "column_names", "column_count", "row_count", "timestamp_column", "density_column",
    "parse_fail_count", "min_timestamp", "max_timestamp", "monotonicity_status",
    "duplicate_timestamp_count", "cadence_median_seconds", "cadence_min_seconds",
    "cadence_max_seconds", "density_numeric_fail_count", "density_nan_count",
    "density_nonpositive_count", "density_min", "density_max", "file_status",
    "error_type", "error_message", "timestamp_timezone_status",
    "timestamp_missing_count", "encoding_used",
]
OVERLAP_COLUMNS = [
    "pair_scope", "left_satellite", "right_satellite", "left_archive_member",
    "right_archive_member", "interval_overlap", "interval_overlap_start",
    "interval_overlap_end", "interval_overlap_seconds",
    "actual_timestamp_overlap_count", "actual_overlap_start", "actual_overlap_end",
    "timestamp_key_policy", "actual_overlap_method",
]
SATELLITE_INTERVAL_COLUMNS = [
    "left_satellite", "right_satellite", "timestamp_kind",
    "overlap_start", "overlap_end", "overlap_seconds", "overlap_days",
    "contributing_file_pair_count", "exact_timestamp_overlap_count",
]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def normalize_satellite(value: str | None) -> str:
    return SATELLITE_ALIASES.get(str(value).strip().lower(), "unclassified") if value else "unclassified"


def parse_satellite_filename(member_name: str) -> dict[str, Any]:
    """Parse explicit known forms; unknown names are never guessed."""
    base = Path(member_name).name
    match = _FILENAME_PATTERN.fullmatch(base)
    if match:
        return {
            "satellite": normalize_satellite(match.group("satellite")),
            "file_id": match.group("file_id"),
            "name_start": match.group("start"),
            "name_end": match.group("end"),
            "parse_status": "parsed",
            "parse_pattern": "explicit_known_satellite",
        }
    return {"satellite": "unclassified", "parse_status": "parse_failed", "parse_pattern": "none"}


def find_column(columns: Sequence[Any], candidates: Sequence[str]) -> Any | None:
    lower = {str(column).strip().lower(): column for column in columns}
    for candidate in candidates:
        if candidate in lower:
            return lower[candidate]
    return None


def _timestamp_key(value: Any) -> tuple[str, int] | None:
    try:
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            return None
        if timestamp.tzinfo is None:
            return "timezone-naive", int(timestamp.value)
        return "timezone-aware-utc-normalized", int(timestamp.tz_convert("UTC").value)
    except (TypeError, ValueError, OverflowError):
        return None


def _display_key(kind: str, number: int) -> str:
    timestamp = pd.Timestamp(number, unit="ns")
    if kind == "timezone-aware-utc-normalized":
        timestamp = timestamp.tz_localize("UTC")
    return timestamp.isoformat()


def _timestamp_display(value: Any) -> str:
    try:
        timestamp = pd.Timestamp(value)
        return "" if pd.isna(timestamp) else timestamp.isoformat()
    except (TypeError, ValueError, OverflowError):
        return ""


def _read_chunks(zf: zipfile.ZipFile, member: str, encoding: str, chunk_size: int):
    errors: list[Exception] = []
    candidates = [encoding] + [item for item in ("utf-8-sig", "utf-8", "latin-1") if item != encoding]
    for candidate in candidates:
        stream = zf.open(member, "r")
        try:
            # Read only the header first.  Re-opening the member for the
            # chunks avoids losing the first data chunk and handles
            # header-only CSVs without treating StopIteration as a fatal error.
            header = pd.read_csv(stream, nrows=0, encoding=candidate)
            columns = [str(column) for column in header.columns]
            stream.close()
            stream = zf.open(member, "r")
            reader = pd.read_csv(stream, chunksize=chunk_size, encoding=candidate)

            def iterator():
                try:
                    yield from reader
                finally:
                    stream.close()

            return columns, iterator(), candidate
        except Exception as exc:
            errors.append(exc)
            stream.close()
    raise errors[-1]


def _empty_record(zip_path: Path, info: zipfile.ZipInfo, satellite: str) -> dict[str, Any]:
    return {
        "file_path": str(zip_path), "archive_member": info.filename, "satellite": satellite,
        "file_size_bytes": info.file_size, "header_status": "not_read", "column_names": "[]",
        "column_count": 0, "row_count": 0, "timestamp_column": "", "density_column": "",
        "parse_fail_count": 0, "min_timestamp": "", "max_timestamp": "",
        "monotonicity_status": "not_evaluated", "duplicate_timestamp_count": 0,
        "cadence_median_seconds": "", "cadence_min_seconds": "", "cadence_max_seconds": "",
        "density_numeric_fail_count": 0, "density_nan_count": 0, "density_nonpositive_count": 0,
        "density_min": "", "density_max": "", "file_status": "NOT_STARTED",
        "error_type": "", "error_message": "", "timestamp_timezone_status": "no-valid-timestamps",
        "timestamp_missing_count": 0, "encoding_used": "",
    }


class FileAudit:
    def __init__(self, record: dict[str, Any], keys: dict[str, np.ndarray] | None = None):
        self.record = record
        self.keys = keys or {}


def audit_member(zf: zipfile.ZipFile, zip_path: Path, info: zipfile.ZipInfo, *, encoding: str, chunk_size: int) -> FileAudit:
    parsed = parse_satellite_filename(info.filename)
    record = _empty_record(zip_path, info, parsed["satellite"])
    if not info.filename.lower().endswith(CSV_SUFFIX):
        record.update(header_status="non_csv", file_status="SKIPPED_NON_CSV")
        return FileAudit(record)
    timestamp_by_kind: dict[str, list[int]] = defaultdict(list)
    source_order: list[tuple[str, int, str]] = []
    density_values: list[float] = []
    parse_fail = density_fail = density_nan = density_nonpositive = timestamp_missing = 0
    row_count = 0
    try:
        columns, frames, chosen_encoding = _read_chunks(zf, info.filename, encoding, chunk_size)
        record.update(header_status="valid" if columns else "empty", column_names=_json(columns), column_count=len(columns), encoding_used=chosen_encoding)
        time_col, density_col = find_column(columns, TIMESTAMP_CANDIDATES), find_column(columns, DENSITY_CANDIDATES)
        record.update(timestamp_column="" if time_col is None else str(time_col), density_column="" if density_col is None else str(density_col))
        for frame in frames:
            row_count += len(frame)
            if time_col is not None:
                for raw in frame[time_col].tolist():
                    if pd.isna(raw) or str(raw).strip() == "":
                        timestamp_missing += 1
                        continue
                    try:
                        timestamp = pd.Timestamp(raw)
                    except (TypeError, ValueError, OverflowError):
                        timestamp = pd.NaT
                    key = _timestamp_key(timestamp)
                    if key is None:
                        parse_fail += 1
                    else:
                        kind, number = key
                        timestamp_by_kind[kind].append(number)
                        source_order.append((kind, number, timestamp.isoformat()))
            if density_col is not None:
                raw_density = frame[density_col]
                numeric = pd.to_numeric(raw_density, errors="coerce")
                missing = raw_density.isna() | raw_density.astype(str).str.strip().eq("")
                density_nan += int(missing.sum())
                density_fail += int((numeric.isna() & ~missing).sum())
                valid = numeric.dropna()
                density_nonpositive += int((valid <= 0).sum())
                density_values.extend(float(value) for value in valid.tolist())
        record["row_count"] = row_count
        record["parse_fail_count"] = parse_fail
        record["timestamp_missing_count"] = timestamp_missing
        record["density_numeric_fail_count"] = density_fail
        record["density_nan_count"] = density_nan
        record["density_nonpositive_count"] = density_nonpositive
        if row_count == 0:
            record.update(
                file_status="CHECK",
                error_type="header_only",
                error_message="CSV header was readable but contained no data rows.",
            )
            return FileAudit(
                record,
                {
                    kind: np.unique(np.asarray(values, dtype=np.int64))
                    for kind, values in timestamp_by_kind.items()
                },
            )
        timestamp_kinds = set()
        if source_order:
            kinds = {kind for kind, _, _ in source_order}
            timestamp_kinds = kinds
            record["timestamp_timezone_status"] = next(iter(kinds)) if len(kinds) == 1 else "mixed"
            numbers = [
                number
                for kind, number, _ in source_order
                if kind == next(iter(kinds))
            ] if len(kinds) == 1 else []
            if len(kinds) == 1:
                keyed_displays = [
                    (number, display)
                    for kind, number, display in source_order
                ]
                # Preserve the source offset in the per-file min/max output.
                # UTC normalization is restricted to actual-overlap keys.
                record["min_timestamp"] = min(
                    keyed_displays, key=lambda item: item[0]
                )[1]
                record["max_timestamp"] = max(
                    keyed_displays, key=lambda item: item[0]
                )[1]
            deltas = np.diff(numbers).astype(float) / 1_000_000_000.0 if len(numbers) > 1 else np.array([])
            record["duplicate_timestamp_count"] = int(len(numbers) - len(set(numbers)))
            if len(numbers) < 2:
                record["monotonicity_status"] = "insufficient_points"
            else:
                record["monotonicity_status"] = (
                    "strictly_increasing"
                    if np.all(deltas > 0)
                    else (
                        "non_monotonic"
                        if np.any(deltas < 0)
                        else "non_decreasing_with_duplicates"
                    )
                )
            if len(deltas):
                record["cadence_median_seconds"] = float(np.median(deltas))
                record["cadence_min_seconds"] = float(np.min(deltas))
                record["cadence_max_seconds"] = float(np.max(deltas))
        if density_values:
            record["density_min"], record["density_max"] = min(density_values), max(density_values)
        required_ok = time_col is not None and density_col is not None
        issues = (
            parsed["parse_status"] != "parsed"
            or not required_ok
            or parse_fail
            or timestamp_missing
            or len(timestamp_kinds) > 1
            or density_fail
            or density_nan
            or density_nonpositive
        )
        record["file_status"] = "CHECK" if issues else "PASS"
        if parsed["parse_status"] != "parsed" and not record["error_type"]:
            record.update(
                error_type="filename_parse_failed",
                error_message="Filename did not match an explicit known satellite pattern.",
            )
        elif len(timestamp_kinds) > 1 and not record["error_type"]:
            record.update(
                error_type="mixed_timezone",
                error_message=(
                    "Timestamp values contain both timezone-naive and "
                    "timezone-aware forms; no implicit conversion was applied."
                ),
            )
        elif timestamp_missing and not record["error_type"]:
            record.update(
                error_type="missing_timestamp_value",
                error_message=f"{timestamp_missing} timestamp value(s) were empty.",
            )
        elif parse_fail and not record["error_type"]:
            record.update(
                error_type="timestamp_parse_failed",
                error_message=f"{parse_fail} timestamp value(s) could not be parsed.",
            )
        elif density_fail and not record["error_type"]:
            record.update(
                error_type="density_numeric_failed",
                error_message=f"{density_fail} density value(s) were non-numeric.",
            )
        elif density_nan and not record["error_type"]:
            record.update(
                error_type="density_missing",
                error_message=f"{density_nan} density value(s) were empty.",
            )
        elif density_nonpositive and not record["error_type"]:
            record.update(
                error_type="density_nonpositive",
                error_message=(
                    f"{density_nonpositive} density value(s) were zero or negative."
                ),
            )
        if not required_ok:
            missing = []
            if time_col is None: missing.append("timestamp")
            if density_col is None: missing.append("density")
            record.update(error_type="missing_required_column", error_message="Missing required column(s): " + ", ".join(missing))
    except pd.errors.EmptyDataError as exc:
        record.update(header_status="empty", file_status="CHECK", error_type=type(exc).__name__, error_message=str(exc))
    except Exception as exc:
        record.update(file_status="ERROR", error_type=type(exc).__name__, error_message=str(exc))
    return FileAudit(record, {kind: np.unique(np.asarray(values, dtype=np.int64)) for kind, values in timestamp_by_kind.items()})


def _interval(item: FileAudit) -> tuple[str, int, int] | None:
    # Never place naive and aware timestamps on one invented timeline.
    if len(item.keys) != 1:
        return None
    kind = sorted(item.keys)[0]
    values = item.keys[kind]
    return kind, int(values[0]), int(values[-1])


def _interval_overlap(left: FileAudit, right: FileAudit):
    a, b = _interval(left), _interval(right)
    if not a or not b or a[0] != b[0]:
        return False, "", "", 0.0
    start, end = max(a[1], b[1]), min(a[2], b[2])
    if start > end:
        return False, "", "", 0.0
    return True, _display_key(a[0], start), _display_key(a[0], end), (end - start) / 1e9


def _actual_overlap(left: FileAudit, right: FileAudit):
    count, values = 0, []
    for kind in set(left.keys) & set(right.keys):
        common = np.intersect1d(left.keys[kind], right.keys[kind], assume_unique=True)
        count += int(common.size)
        if common.size:
            values.extend((_display_key(kind, int(common[0])), _display_key(kind, int(common[-1]))))
    return count, (min(values) if values else ""), (max(values) if values else "")


def _overlap_row(scope: str, left: FileAudit, right: FileAudit, method: str) -> dict[str, Any] | None:
    interval, start, end, seconds = _interval_overlap(left, right)
    if not interval:
        return None
    count, actual_start, actual_end = _actual_overlap(left, right)
    return {
        "pair_scope": scope, "left_satellite": left.record["satellite"], "right_satellite": right.record["satellite"],
        "left_archive_member": left.record["archive_member"], "right_archive_member": right.record["archive_member"],
        "interval_overlap": True, "interval_overlap_start": start, "interval_overlap_end": end,
        "interval_overlap_seconds": seconds, "actual_timestamp_overlap_count": count,
        "actual_overlap_start": actual_start, "actual_overlap_end": actual_end,
        "timestamp_key_policy": "naive keys separate; aware keys normalized to UTC for comparison only",
        "actual_overlap_method": method,
    }


def within_satellite_overlaps(audits: Sequence[FileAudit]) -> list[dict[str, Any]]:
    rows = []
    groups: dict[str, list[FileAudit]] = defaultdict(list)
    for item in audits:
        if item.record["satellite"] != "unclassified": groups[item.record["satellite"]].append(item)
    for satellite, members in groups.items():
        ordered = sorted(members, key=lambda item: (_interval(item)[1] if _interval(item) else np.iinfo(np.int64).max, item.record["archive_member"]))
        for index, left in enumerate(ordered):
            left_interval = _interval(left)
            if not left_interval: continue
            for right in ordered[index + 1:]:
                right_interval = _interval(right)
                if not right_interval or right_interval[0] != left_interval[0]: continue
                if right_interval[1] > left_interval[2]: break
                row = _overlap_row("within-satellite-file-pair", left, right, "file-level exact-key intersection")
                if row: rows.append(row)
    return rows


def cross_satellite_overlaps(audits: Sequence[FileAudit]) -> list[dict[str, Any]]:
    aggregates: dict[str, FileAudit] = {}
    groups: dict[str, list[FileAudit]] = defaultdict(list)
    for item in audits:
        if item.record["satellite"] != "unclassified": groups[item.record["satellite"]].append(item)
    for satellite, members in groups.items():
        keys: dict[str, np.ndarray] = {}
        for kind in {kind for item in members for kind in item.keys}:
            arrays = [item.keys[kind] for item in members if kind in item.keys]
            if arrays: keys[kind] = np.unique(np.concatenate(arrays))
        aggregates[satellite] = FileAudit({"satellite": satellite, "archive_member": f"<aggregate:{satellite}>"}, keys)
    rows = []
    for left_satellite, right_satellite in itertools.combinations(sorted(aggregates), 2):
        row = _overlap_row("cross-satellite-pair", aggregates[left_satellite], aggregates[right_satellite], "satellite-level union exact-key intersection")
        if row: rows.append(row)
    return rows


def cross_satellite_interval_overlaps(audits: Sequence[FileAudit]) -> list[dict[str, Any]]:
    """Return merged calendar intervals where two satellites have coverage.

    This is deliberately interval-based: calibration windows need overlapping
    coverage even when the two satellites sampled at slightly different
    timestamps. Exact timestamp intersections remain reported separately.
    """
    groups: dict[str, list[FileAudit]] = defaultdict(list)
    for item in audits:
        if item.record["satellite"] != "unclassified" and _interval(item):
            groups[item.record["satellite"]].append(item)
    rows: list[dict[str, Any]] = []
    for left_satellite, right_satellite in itertools.combinations(sorted(groups), 2):
        intersections: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
        for left in groups[left_satellite]:
            left_interval = _interval(left)
            if not left_interval:
                continue
            for right in groups[right_satellite]:
                right_interval = _interval(right)
                if not right_interval or left_interval[0] != right_interval[0]:
                    continue
                start, end = max(left_interval[1], right_interval[1]), min(left_interval[2], right_interval[2])
                if start <= end:
                    intersections[left_interval[0]].append((start, end, 1))
        for kind, values in intersections.items():
            merged: list[list[int]] = []
            for start, end, count in sorted(values):
                if merged and start <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], end)
                    merged[-1][2] += count
                else:
                    merged.append([start, end, count])
            for start, end, pair_count in merged:
                rows.append({
                    "left_satellite": left_satellite,
                    "right_satellite": right_satellite,
                    "timestamp_kind": kind,
                    "overlap_start": _display_key(kind, start),
                    "overlap_end": _display_key(kind, end),
                    "overlap_seconds": (end - start) / 1e9,
                    "overlap_days": (end - start) / 86_400e9,
                    "contributing_file_pair_count": pair_count,
                    "exact_timestamp_overlap_count": "",
                })
    return sorted(rows, key=lambda row: (row["left_satellite"], row["right_satellite"], row["overlap_start"]))


def _write_human_overlap_report(path: Path, interval_rows: Sequence[Mapping[str, Any]],
                                 exact_rows: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]):
    lines = [
        "# Cross-satellite overlap report",
        "",
        f"- Mode: `{summary['mode']}`",
        f"- ZIP SHA-256: `{summary['zip_sha256']}`",
        f"- CSV files audited: `{summary['n_files_audited']}`",
        "",
        "This report identifies calendar coverage intervals shared by two satellites.",
        "It is the primary human-readable input for selecting calibration windows.",
        "An interval overlap does not imply identical timestamps; exact timestamp",
        "intersections are listed separately.",
        "",
        "## Shared coverage intervals",
        "",
        "| Pair | Time basis | Start | End | Days | File-pair contributions |",
        "|---|---|---|---|---:|---:|",
    ]
    if interval_rows:
        for row in interval_rows:
            lines.append(
                f"| `{row['left_satellite']} + {row['right_satellite']}` | "
                f"`{row['timestamp_kind']}` | `{row['overlap_start']}` | "
                f"`{row['overlap_end']}` | {float(row['overlap_days']):.6f} | "
                f"{row['contributing_file_pair_count']} |"
            )
    else:
        lines.append("| No cross-satellite interval overlap found |  |  |  |  |  |")
    lines.extend([
        "",
        "## Exact timestamp intersections (summary)",
        "",
        "| Pair | Exact shared timestamps | First | Last |",
        "|---|---:|---|---|",
    ])
    exact_cross = [row for row in exact_rows if row["pair_scope"] == "cross-satellite-pair"]
    if exact_cross:
        for row in exact_cross:
            lines.append(
                f"| `{row['left_satellite']} + {row['right_satellite']}` | "
                f"{row['actual_timestamp_overlap_count']} | "
                f"`{row['actual_overlap_start'] or 'none'}` | "
                f"`{row['actual_overlap_end'] or 'none'}` |"
            )
    else:
        lines.append("| No exact timestamp intersections reported |  |  |  |")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "- Use shared coverage intervals to choose candidate calibration windows.",
        "- Use exact timestamp counts to decide whether direct timestamp pairing is possible.",
        "- Check `timestamp_kind`: timezone-naive and timezone-aware timelines are never mixed.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def aggregate_satellites(audits: Sequence[FileAudit]) -> list[dict[str, Any]]:
    groups: dict[str, list[FileAudit]] = defaultdict(list)
    for item in audits: groups[item.record["satellite"]].append(item)
    rows = []
    for satellite, members in sorted(groups.items()):
        intervals = [_interval(item) for item in members if _interval(item)]
        interval_kinds = {item[0] for item in intervals}
        cadences = [float(item.record["cadence_median_seconds"]) for item in members if item.record["cadence_median_seconds"] != ""]
        union = {kind: np.unique(np.concatenate([item.keys[kind] for item in members if kind in item.keys])) for kind in {kind for item in members for kind in item.keys}}
        rows.append({
            "satellite": satellite, "n_files": len(members),
            "n_pass": sum(item.record["file_status"] == "PASS" for item in members),
            "n_check": sum(item.record["file_status"] == "CHECK" for item in members),
            "n_error": sum(item.record["file_status"] == "ERROR" for item in members),
            "row_count_total": sum(int(item.record["row_count"]) for item in members),
            "parse_fail_count_total": sum(int(item.record["parse_fail_count"]) for item in members),
            "duplicate_timestamp_count_total": sum(int(item.record["duplicate_timestamp_count"]) for item in members),
            "timestamp_timezone_statuses": _json(sorted({item.record["timestamp_timezone_status"] for item in members})),
            "schema_signatures": _json(sorted({item.record["column_names"] for item in members})),
            "min_timestamp": (
                _display_key(next(iter(interval_kinds)), min(item[1] for item in intervals))
                if len(interval_kinds) == 1 else ""
            ),
            "max_timestamp": (
                _display_key(next(iter(interval_kinds)), max(item[2] for item in intervals))
                if len(interval_kinds) == 1 else ""
            ),
            "unique_timestamp_count": sum(len(values) for values in union.values()),
            "cadence_median_seconds_median": float(np.median(cadences)) if cadences else "",
            "status": "PASS" if members and all(item.record["file_status"] == "PASS" for item in members) else "CHECK",
        })
    return rows


def select_members_for_pilot(csv_members: Sequence[str], max_files: int | None = None):
    selected, log = [], []
    ordered = sorted(csv_members)
    for satellite in TARGET_SATELLITES:
        candidates = [member for member in ordered if parse_satellite_filename(member)["satellite"] == satellite]
        if candidates:
            reason = f"first_member_for_{satellite}"
            if satellite == "gr-of1":
                reason += "; difficult_hyphenated_grace_fo_name"
            selected.append(candidates[0]); log.append({"member": candidates[0], "reason": reason})
    difficult = [member for member in ordered if parse_satellite_filename(member)["satellite"] == "unclassified"]
    if difficult:
        selected.append(difficult[0]); log.append({"member": difficult[0], "reason": "unclassified_or_difficult_name"})
    required_count = len(TARGET_SATELLITES)
    if max_files is not None and max_files < required_count:
        raise ValueError(
            f"--max-files must be at least {required_count} "
            "so the pilot covers every target satellite."
        )
    if max_files and len(selected) > max_files:
        selected = selected[:max_files]; log = [entry for entry in log if entry["member"] in selected]
    return selected, log


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()


def _versions() -> dict[str, str]:
    result = {}
    for package in ("pandas", "numpy"):
        try: result[package] = importlib_metadata.version(package)
        except importlib_metadata.PackageNotFoundError: result[package] = "not-installed"
    return result


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows: writer.writerow({column: row.get(column, "") for column in columns})


def run_audit(zip_path: Path, output_dir: Path, *, mode: str, max_files: int | None = None, encoding: str = "utf-8", chunk_size: int = CHUNK_SIZE) -> dict[str, Any]:
    if not zip_path.exists(): raise FileNotFoundError(zip_path)
    if mode == "full" and max_files is not None: raise ValueError("--max-files is pilot-only")
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now().astimezone().isoformat()
    with zipfile.ZipFile(zip_path) as zf:
        infos = [info for info in zf.infolist() if not info.is_dir()]
        csv_infos = [info for info in infos if info.filename.lower().endswith(CSV_SUFFIX)]
        if mode == "pilot":
            names, selection = select_members_for_pilot([info.filename for info in csv_infos], max_files)
            selected_names = set(names)
            selected = [info for info in csv_infos if info.filename in selected_names]
        else:
            selection, selected = [], csv_infos
        audits = [audit_member(zf, zip_path, info, encoding=encoding, chunk_size=chunk_size) for info in sorted(selected, key=lambda item: item.filename)]
    rows = [item.record for item in audits]
    _write_csv(output_dir / "full_file_schema_time_audit.csv", rows, AUDIT_COLUMNS)
    satellite_rows = aggregate_satellites(audits)
    _write_csv(output_dir / "satellite_summary.csv", satellite_rows, [
        "satellite", "n_files", "n_pass", "n_check", "n_error", "row_count_total",
        "parse_fail_count_total", "duplicate_timestamp_count_total", "timestamp_timezone_statuses",
        "schema_signatures", "min_timestamp", "max_timestamp", "unique_timestamp_count",
        "cadence_median_seconds_median", "status",
    ])
    overlap_rows = within_satellite_overlaps(audits) + cross_satellite_overlaps(audits)
    _write_csv(output_dir / "satellite_overlap_pairs.csv", overlap_rows, OVERLAP_COLUMNS)
    interval_rows = cross_satellite_interval_overlaps(audits)
    _write_csv(output_dir / "satellite_overlap_intervals.csv", interval_rows, SATELLITE_INTERVAL_COLUMNS)
    n_pass = sum(item.record["file_status"] == "PASS" for item in audits)
    n_check = sum(item.record["file_status"] == "CHECK" for item in audits)
    n_error = sum(item.record["file_status"] == "ERROR" for item in audits)
    selected_satellites = {item.record["satellite"] for item in audits}
    missing_target_satellites = [
        satellite for satellite in TARGET_SATELLITES if satellite not in selected_satellites
    ]
    difficult_selected = any(
        item.record["satellite"] == "unclassified"
        or Path(item.record["archive_member"]).name.lower().startswith("gr-of1-")
        for item in audits
    )
    summary = {
        "status": (
            "PASS"
            if n_error == 0
            and n_check == 0
            and len(audits) == len(selected)
            and not missing_target_satellites
            else "CHECK"
        ),
        "mode": mode, "zip_path": str(zip_path), "output_dir": str(output_dir),
        "zip_size_bytes": zip_path.stat().st_size, "zip_sha256": _sha256(zip_path),
        "n_members_discovered": len(infos), "n_csv_members_discovered": len(csv_infos),
        "n_csv_members_selected": len(selected), "n_files_audited": len(audits),
        "n_pass": n_pass, "n_check": n_check, "n_error": n_error,
        "n_unclassified": sum(item.record["satellite"] == "unclassified" for item in audits),
        "missing_target_satellites": missing_target_satellites,
        "difficult_filename_selected": difficult_selected,
        "n_overlap_rows": len(overlap_rows),
        "n_within_satellite_overlap_rows": sum(row["pair_scope"] == "within-satellite-file-pair" for row in overlap_rows),
        "n_cross_satellite_overlap_rows": sum(row["pair_scope"] == "cross-satellite-pair" for row in overlap_rows),
        "python_version": platform.python_version(), "platform": platform.platform(),
        "library_versions": _versions(), "selection": selection,
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(),
        "timestamp_key_policy": "timezone-naive keys remain separate; timezone-aware keys normalize to UTC for comparison only",
        "outputs": {name: str(output_dir / name) for name in (
            "full_file_schema_time_audit.csv", "satellite_summary.csv",
            "satellite_overlap_pairs.csv", "satellite_overlap_intervals.csv",
            "satellite_overlap_report.md", "audit_run_summary.json", "audit_run_log.md"
        )},
    }
    (output_dir / "audit_run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    log = [
        "# Substep 1.3 Full Archive Schema/Time Audit", "", f"- Status: `{summary['status']}`",
        f"- Mode: `{mode}`", f"- ZIP SHA-256: `{summary['zip_sha256']}`",
        f"- ZIP size (bytes): `{summary['zip_size_bytes']}`",
        f"- CSV discovered/selected: `{len(csv_infos)}/{len(selected)}`",
        f"- PASS/CHECK/ERROR: `{n_pass}/{n_check}/{n_error}`", "",
        f"- Missing target satellites: `{', '.join(missing_target_satellites) if missing_target_satellites else 'none'}`",
        f"- Difficult filename selected: `{difficult_selected}`",
        f"- Started: `{summary['started_at']}`",
        f"- Finished: `{summary['finished_at']}`",
        f"- Python: `{summary['python_version']}`",
        f"- Libraries: `{_json(summary['library_versions'])}`", "",
        "## Selection", "",
    ]
    log.extend(f"- `{entry['member']}` — {entry['reason']}" for entry in selection)
    _write_human_overlap_report(output_dir / "satellite_overlap_report.md", interval_rows, overlap_rows, summary)
    log.extend(["", "## Methodology", "", "- Interval overlap uses `[max(min_A,min_B), min(max_A,max_B)]`.",
                "- Actual overlap uses exact nanosecond keys; naive and aware keys are never conflated.",
                "- Within-satellite overlap uses a sorted interval sweep; cross-satellite exact overlap uses per-satellite timestamp unions.",
                "- Cross-satellite calibration windows use merged intersections of per-file coverage intervals.",
                "- A pilot is not evidence for the untested archive.", "", "## Outputs", ""])
    log.extend(f"- `{path}`" for path in summary["outputs"].values())
    (output_dir / "audit_run_log.md").write_text("\n".join(log) + "\n", encoding="utf-8")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit STORM-AI ZIP CSV members.")
    parser.add_argument("mode", choices=("pilot", "full"))
    parser.add_argument("--zip-path", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--encoding", default="utf-8")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    args = parser.parse_args(argv)
    try:
        summary = run_audit(args.zip_path, args.output_dir, mode=args.mode, max_files=args.max_files, encoding=args.encoding, chunk_size=args.chunk_size)
    except Exception as exc:
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
