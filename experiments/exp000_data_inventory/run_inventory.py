from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


FILE_ID_RE = re.compile(r"(?P<file_id>-?\d{5})")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            hasher.update(block)
    return hasher.hexdigest()


def classify_file(path: Path) -> str:
    name = path.name.lower()

    if "initial_states" in name:
        return "initial_states"

    if name.startswith("champ_"):
        return "satellite_champ"

    if name.startswith("grace"):
        return "satellite_grace"

    if name.startswith("swarm"):
        return "satellite_swarm"

    if name.startswith("omni2"):
        return "omni2_space_weather"

    if name.startswith("goes"):
        return "goes_space_weather"

    if path.suffix.lower() == ".csv":
        return "unknown_csv"

    return "unknown"


def extract_file_ids(path: Path) -> list[str]:
    return sorted(set(match.group("file_id") for match in FILE_ID_RE.finditer(path.name)))


def inspect_csv(path: Path, max_rows_for_count: int | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "readable_csv": False,
        "n_rows": None,
        "n_columns": None,
        "columns": "",
        "has_timestamp": False,
        "has_density": False,
        "has_latitude_like": False,
        "has_longitude_like": False,
        "has_altitude_like": False,
        "error": "",
    }

    try:
        head = pd.read_csv(path, nrows=5)
        columns = [str(c) for c in head.columns]
        lower_columns = [c.lower() for c in columns]

        result["readable_csv"] = True
        result["n_columns"] = len(columns)
        result["columns"] = "|".join(columns)
        result["has_timestamp"] = "Timestamp" in columns
        result["has_density"] = "Orbit Mean Density (kg/m^3)" in columns
        result["has_latitude_like"] = any("lat" in c for c in lower_columns)
        result["has_longitude_like"] = any("lon" in c for c in lower_columns)
        result["has_altitude_like"] = any(("alt" in c) or ("height" in c) for c in lower_columns)

        if max_rows_for_count is not None:
            n_rows = 0
            for chunk in pd.read_csv(path, chunksize=50_000):
                n_rows += len(chunk)
                if n_rows > max_rows_for_count:
                    result["n_rows"] = f">{max_rows_for_count}"
                    return result
            result["n_rows"] = n_rows

    except Exception as exc:
        result["error"] = repr(exc)

    return result


def scan_data_root(data_root: Path, max_rows_for_count: int | None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for path in sorted(data_root.rglob("*")):
        if not path.is_file():
            continue

        stat = path.stat()
        record: dict[str, Any] = {
            "absolute_path": str(path.resolve()),
            "relative_path": str(path.relative_to(data_root)),
            "file_name": path.name,
            "suffix": path.suffix.lower(),
            "size_bytes": stat.st_size,
            "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
            "file_class": classify_file(path),
            "file_ids_in_name": ";".join(extract_file_ids(path)),
            "sha256": sha256_file(path),
        }

        if path.suffix.lower() == ".csv":
            record.update(inspect_csv(path, max_rows_for_count))
        else:
            record.update(
                {
                    "readable_csv": False,
                    "n_rows": None,
                    "n_columns": None,
                    "columns": "",
                    "has_timestamp": False,
                    "has_density": False,
                    "has_latitude_like": False,
                    "has_longitude_like": False,
                    "has_altitude_like": False,
                    "error": "",
                }
            )

        records.append(record)

    return records


def build_audit(records: list[dict[str, Any]], data_root: Path) -> dict[str, Any]:
    class_counts: dict[str, int] = {}
    file_ids: set[str] = set()

    for record in records:
        file_class = record["file_class"]
        class_counts[file_class] = class_counts.get(file_class, 0) + 1

        for file_id in str(record["file_ids_in_name"]).split(";"):
            if file_id:
                file_ids.add(file_id)

    reasons: list[str] = []
    status = "PASS"

    if len(records) == 0:
        status = "FAIL"
        reasons.append("No files found under DATA_ROOT.")

    if class_counts.get("initial_states", 0) == 0:
        status = "BLOCKED"
        reasons.append("No initial_states file found.")

    satellite_file_count = (
        class_counts.get("satellite_champ", 0)
        + class_counts.get("satellite_grace", 0)
        + class_counts.get("satellite_swarm", 0)
    )

    if satellite_file_count == 0:
        status = "BLOCKED"
        reasons.append("No satellite density/orbit file found.")

    return {
        "experiment_id": "exp000_data_inventory",
        "status": status,
        "created_utc": utc_now(),
        "data_root": str(data_root.resolve()),
        "n_files": len(records),
        "n_unique_file_ids_seen_in_names": len(file_ids),
        "file_class_counts": class_counts,
        "reasons": reasons,
    }


def write_outputs(records: list[dict[str, Any]], audit: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    inventory_path = output_dir / "inventory.csv"
    audit_path = output_dir / "audit_report.json"
    preview_path = output_dir / "human_preview.md"

    pd.DataFrame(records).to_csv(inventory_path, index=False, quoting=csv.QUOTE_MINIMAL)
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    lines = [
        "# exp000_data_inventory",
        "",
        f"Status: `{audit['status']}`",
        f"DATA_ROOT: `{audit['data_root']}`",
        f"Files scanned: `{audit['n_files']}`",
        f"Unique File IDs seen in names: `{audit['n_unique_file_ids_seen_in_names']}`",
        "",
        "## File Classes",
        "",
    ]

    for key, value in sorted(audit["file_class_counts"].items()):
        lines.append(f"- `{key}`: {value}")

    if audit["reasons"]:
        lines.extend(["", "## Gate Reasons", ""])
        for reason in audit["reasons"]:
            lines.append(f"- {reason}")

    lines.extend(["", "## First 20 Files", ""])

    for record in records[:20]:
        lines.append(
            f"- `{record['file_class']}` | `{record['relative_path']}` | "
            f"rows=`{record['n_rows']}` | timestamp=`{record['has_timestamp']}` | "
            f"density=`{record['has_density']}`"
        )

    preview_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory raw STORM-AI data files.")
    parser.add_argument("--data-root", required=True, help="Path to raw STORM-AI data folder.")
    parser.add_argument(
        "--output-dir",
        default="experiments/exp000_data_inventory/outputs",
        help="Output directory.",
    )
    parser.add_argument(
        "--max-rows-for-count",
        type=int,
        default=200000,
        help="Maximum rows to count per CSV. Use -1 to disable row counting.",
    )
    args = parser.parse_args()

    data_root = Path(args.data_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if not data_root.exists():
        raise FileNotFoundError(f"DATA_ROOT does not exist: {data_root}")

    max_rows = None if args.max_rows_for_count < 0 else args.max_rows_for_count

    records = scan_data_root(data_root, max_rows)
    audit = build_audit(records, data_root)
    write_outputs(records, audit, output_dir)

    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
