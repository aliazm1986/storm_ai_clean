import argparse
import io
import json
import re
import zipfile
from pathlib import Path

import pandas as pd


PATTERN_UNDERSCORE = re.compile(
    r"^(?P<satellite>[A-Za-z0-9\-]+)_(?P<file_id>-?\d+)-(?P<start>\d{8})_to_(?P<end>\d{8})\.csv$",
    re.IGNORECASE,
)

PATTERN_NO_UNDERSCORE = re.compile(
    r"^(?P<satellite>[A-Za-z0-9\-]+)-(?P<file_id>-?\d+)-(?P<start>\d{8})_to_(?P<end>\d{8})\.csv$",
    re.IGNORECASE,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create one compact satellite-level summary table from sat_density ZIP."
    )
    parser.add_argument(
        "--zip-path",
        required=True,
        help="Path to sat_density ZIP file.",
    )
    parser.add_argument(
        "--output-dir",
        default="experiments/exp000_data_inventory/outputs/sat_density_inspection",
        help="Output directory.",
    )
    parser.add_argument(
        "--row-limit",
        type=int,
        default=50,
        help="Rows to read per CSV. Use -1 to read full files.",
    )
    return parser.parse_args()


def normalize_satellite(value):
    if value is None:
        return "unknown"
    value = str(value).strip().lower().replace(" ", "")
    if value == "":
        return "unknown"
    return value


def parse_filename(member_name):
    base_name = Path(member_name).name

    match = PATTERN_UNDERSCORE.match(base_name)
    if match:
        return {
            "base_name": base_name,
            "satellite": normalize_satellite(match.group("satellite")),
            "file_id": match.group("file_id"),
            "name_start": match.group("start"),
            "name_end": match.group("end"),
            "parse_status": "ok",
            "parse_pattern": "underscore",
        }

    match = PATTERN_NO_UNDERSCORE.match(base_name)
    if match:
        return {
            "base_name": base_name,
            "satellite": normalize_satellite(match.group("satellite")),
            "file_id": match.group("file_id"),
            "name_start": match.group("start"),
            "name_end": match.group("end"),
            "parse_status": "ok",
            "parse_pattern": "no_underscore",
        }

    stem = base_name
    if stem.lower().endswith(".csv"):
        stem = stem[:-4]

    if "_" in stem:
        satellite_guess = stem.split("_", 1)[0]
        return {
            "base_name": base_name,
            "satellite": normalize_satellite(satellite_guess),
            "file_id": None,
            "name_start": None,
            "name_end": None,
            "parse_status": "fallback",
            "parse_pattern": "prefix_before_underscore",
        }

    parts = stem.split("-")
    if len(parts) >= 3:
        satellite_guess = "-".join(parts[:-2])
        return {
            "base_name": base_name,
            "satellite": normalize_satellite(satellite_guess),
            "file_id": None,
            "name_start": None,
            "name_end": None,
            "parse_status": "fallback",
            "parse_pattern": "prefix_before_last_two_dash_parts",
        }

    return {
        "base_name": base_name,
        "satellite": "unknown",
        "file_id": None,
        "name_start": None,
        "name_end": None,
        "parse_status": "failed",
        "parse_pattern": "none",
    }


def read_csv_from_zip(zf, member_name, row_limit):
    with zf.open(member_name) as f:
        raw = f.read()

    for encoding in ["utf-8", "utf-8-sig", "latin-1"]:
        try:
            text = raw.decode(encoding)
            buffer = io.StringIO(text)
            if row_limit == -1:
                return pd.read_csv(buffer)
            return pd.read_csv(buffer, nrows=row_limit)
        except UnicodeDecodeError:
            continue

    text = raw.decode("utf-8", errors="replace")
    buffer = io.StringIO(text)
    if row_limit == -1:
        return pd.read_csv(buffer)
    return pd.read_csv(buffer, nrows=row_limit)


def find_timestamp_column(columns):
    exact_candidates = [
        "timestamp",
        "time",
        "datetime",
        "date_time",
        "utc",
    ]

    lower_map = {}
    for col in columns:
        lower_map[str(col).strip().lower()] = col

    for candidate in exact_candidates:
        if candidate in lower_map:
            return lower_map[candidate]

    for col in columns:
        col_lower = str(col).strip().lower()
        if "time" in col_lower or "date" in col_lower or "utc" in col_lower:
            return col

    return None


def inspect_member(zf, member_name, row_limit):
    parsed = parse_filename(member_name)

    record = {
        "member_name": member_name,
        "base_name": parsed["base_name"],
        "satellite": parsed["satellite"],
        "file_id": parsed["file_id"],
        "name_start": parsed["name_start"],
        "name_end": parsed["name_end"],
        "parse_status": parsed["parse_status"],
        "parse_pattern": parsed["parse_pattern"],
        "read_status": "not_attempted",
        "rows_read": 0,
        "timestamp_column": None,
        "timestamp_min": None,
        "timestamp_max": None,
        "error_message": None,
    }

    if not member_name.lower().endswith(".csv"):
        record["read_status"] = "skipped_non_csv"
        return record

    try:
        df = read_csv_from_zip(
            zf=zf,
            member_name=member_name,
            row_limit=row_limit,
        )

        record["read_status"] = "ok"
        record["rows_read"] = int(len(df))

        timestamp_column = find_timestamp_column(list(df.columns))
        record["timestamp_column"] = timestamp_column

        if timestamp_column is not None:
            ts = pd.to_datetime(df[timestamp_column], errors="coerce")
            ts = ts.dropna()

            if not ts.empty:
                record["timestamp_min"] = ts.min().isoformat()
                record["timestamp_max"] = ts.max().isoformat()

    except Exception as exc:
        record["read_status"] = "error"
        record["error_message"] = f"{type(exc).__name__}: {exc}"

    return record


def build_summary(file_df):
    csv_df = file_df[file_df["member_name"].str.lower().str.endswith(".csv")].copy()

    if csv_df.empty:
        return pd.DataFrame(
            columns=[
                "satellite",
                "n_csv_files",
                "n_read_ok",
                "n_read_error",
                "n_parse_ok",
                "n_parse_fallback",
                "n_parse_failed",
                "rows_read_total",
                "start_from_data",
                "end_from_data",
                "start_from_filename",
                "end_from_filename",
                "duration_days_from_data",
                "status",
            ]
        )

    csv_df["timestamp_min_dt"] = pd.to_datetime(
        csv_df["timestamp_min"],
        errors="coerce",
    )
    csv_df["timestamp_max_dt"] = pd.to_datetime(
        csv_df["timestamp_max"],
        errors="coerce",
    )

    csv_df["name_start_dt"] = pd.to_datetime(
        csv_df["name_start"],
        format="%Y%m%d",
        errors="coerce",
    )
    csv_df["name_end_dt"] = pd.to_datetime(
        csv_df["name_end"],
        format="%Y%m%d",
        errors="coerce",
    )

    rows = []

    for satellite, group in csv_df.groupby("satellite", dropna=False):
        n_csv_files = int(len(group))
        n_read_ok = int((group["read_status"] == "ok").sum())
        n_read_error = int((group["read_status"] == "error").sum())
        n_parse_ok = int((group["parse_status"] == "ok").sum())
        n_parse_fallback = int((group["parse_status"] == "fallback").sum())
        n_parse_failed = int((group["parse_status"] == "failed").sum())
        rows_read_total = int(group["rows_read"].sum())

        start_data = group["timestamp_min_dt"].min()
        end_data = group["timestamp_max_dt"].max()

        start_name = group["name_start_dt"].min()
        end_name = group["name_end_dt"].max()

        duration_days = None
        if pd.notna(start_data) and pd.notna(end_data):
            duration_days = round(
                (end_data - start_data).total_seconds() / 86400.0,
                3,
            )

        if n_parse_failed > 0:
            status = "CHECK_PARSE"
        elif n_read_error > 0:
            status = "CHECK_READ"
        elif n_parse_fallback > 0:
            status = "OK_WITH_FALLBACK"
        else:
            status = "OK"

        rows.append(
            {
                "satellite": satellite,
                "n_csv_files": n_csv_files,
                "n_read_ok": n_read_ok,
                "n_read_error": n_read_error,
                "n_parse_ok": n_parse_ok,
                "n_parse_fallback": n_parse_fallback,
                "n_parse_failed": n_parse_failed,
                "rows_read_total": rows_read_total,
                "start_from_data": start_data.isoformat() if pd.notna(start_data) else "",
                "end_from_data": end_data.isoformat() if pd.notna(end_data) else "",
                "start_from_filename": start_name.date().isoformat() if pd.notna(start_name) else "",
                "end_from_filename": end_name.date().isoformat() if pd.notna(end_name) else "",
                "duration_days_from_data": duration_days,
                "status": status,
            }
        )

    summary_df = pd.DataFrame(rows)

    summary_df = summary_df.sort_values(
        by=["start_from_data", "satellite"],
        ascending=[True, True],
        na_position="last",
    ).reset_index(drop=True)

    return summary_df


def write_markdown(summary_df, output_path):
    lines = []
    lines.append("# Satellite Summary Table")
    lines.append("")
    lines.append("Compact one-row-per-satellite inventory.")
    lines.append("")

    if summary_df.empty:
        lines.append("No CSV satellite files found.")
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return

    columns = [
        "satellite",
        "n_csv_files",
        "n_read_ok",
        "n_read_error",
        "n_parse_ok",
        "n_parse_fallback",
        "n_parse_failed",
        "rows_read_total",
        "start_from_data",
        "end_from_data",
        "start_from_filename",
        "end_from_filename",
        "duration_days_from_data",
        "status",
    ]

    lines.append("| " + " | ".join(columns) + " |")
    lines.append("|" + "|".join(["---"] * len(columns)) + "|")

    for _, row in summary_df.iterrows():
        values = []
        for col in columns:
            value = row[col]
            if pd.isna(value):
                value = ""
            values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def print_console_table(summary_df):
    print("")
    print("SATELLITE SUMMARY")
    print("=================")

    if summary_df.empty:
        print("No records found.")
        print("")
        return

    display_cols = [
        "satellite",
        "n_csv_files",
        "start_from_data",
        "end_from_data",
        "status",
    ]

    print(summary_df[display_cols].to_string(index=False, max_colwidth=32))
    print("")


def main():
    args = parse_args()

    zip_path = Path(args.zip_path)
    output_dir = Path(args.output_dir)

    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP file does not exist: {zip_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    records = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        members = [
            member
            for member in zf.namelist()
            if member and not member.endswith("/")
        ]

        for member_name in members:
            record = inspect_member(
                zf=zf,
                member_name=member_name,
                row_limit=args.row_limit,
            )
            records.append(record)

    file_df = pd.DataFrame(records)
    summary_df = build_summary(file_df)

    file_inventory_path = output_dir / "satellite_parse_audit.csv"
    summary_csv_path = output_dir / "satellite_summary_table.csv"
    summary_md_path = output_dir / "satellite_summary_table.md"
    run_summary_path = output_dir / "run_summary.json"

    file_df.to_csv(file_inventory_path, index=False)
    summary_df.to_csv(summary_csv_path, index=False)
    write_markdown(summary_df, summary_md_path)

    n_csv_members = int(file_df["member_name"].str.lower().str.endswith(".csv").sum())
    n_read_error = int((file_df["read_status"] == "error").sum())
    n_parse_failed = int((file_df["parse_status"] == "failed").sum())

    run_summary = {
        "status": "PASS" if n_read_error == 0 and n_parse_failed == 0 else "CHECK",
        "zip_path": str(zip_path),
        "output_dir": str(output_dir),
        "row_limit": args.row_limit,
        "n_members_total": int(len(file_df)),
        "n_csv_members": n_csv_members,
        "n_satellites": int(summary_df["satellite"].nunique()) if not summary_df.empty else 0,
        "n_read_error": n_read_error,
        "n_parse_failed": n_parse_failed,
        "outputs": {
            "satellite_summary_table_csv": str(summary_csv_path),
            "satellite_summary_table_md": str(summary_md_path),
            "satellite_parse_audit_csv": str(file_inventory_path),
            "run_summary_json": str(run_summary_path),
        },
    }

    run_summary_path.write_text(
        json.dumps(run_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print_console_table(summary_df)
    print(json.dumps(run_summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
