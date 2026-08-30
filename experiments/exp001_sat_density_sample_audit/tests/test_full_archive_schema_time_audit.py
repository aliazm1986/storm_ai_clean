from __future__ import annotations

import csv
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import full_archive_schema_time_audit as audit  # noqa: E402


def _csv_text(header: str, rows: list[str]) -> str:
    return "\n".join([header, *rows]) + "\n"


class AuditHelpersTests(unittest.TestCase):
    def test_explicit_satellite_parser_covers_five_real_forms(self) -> None:
        names = {
            "champ_-00000-20000802_to_20000805.csv": "champ",
            "grace1-02285-20021110_to_20021113.csv": "grace1",
            "grace2-02358-20020502_to_20020505.csv": "grace2",
            "swarma-06672-20140103_to_20140106.csv": "swarma",
            "gr-of1-04265-20180601_to_20180604.csv": "gr-of1",
        }
        for name, expected in names.items():
            parsed = audit.parse_satellite_filename(name)
            self.assertEqual(parsed["satellite"], expected)
            self.assertEqual(parsed["parse_status"], "parsed")

    def test_unknown_filename_is_not_guessed(self) -> None:
        parsed = audit.parse_satellite_filename("mystery-00001-20200101_to_20200102.csv")
        self.assertEqual(parsed["satellite"], "unclassified")
        self.assertEqual(parsed["parse_status"], "parse_failed")


class MemberAuditTests(unittest.TestCase):
    def _audit_one(self, name: str, text: str) -> dict:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            zip_path = root / "fixture.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(name, text)
            with zipfile.ZipFile(zip_path) as archive:
                info = archive.getinfo(name)
                return audit.audit_member(
                    archive,
                    zip_path,
                    info,
                    encoding="utf-8",
                    chunk_size=2,
                ).record

    def test_valid_two_column_schema(self) -> None:
        record = self._audit_one(
            "champ_-00000-20000802_to_20000805.csv",
            _csv_text(
                "Timestamp,Orbit Mean Density (kg/m^3)",
                [
                    "2000-08-02T00:00:00,1e-12",
                    "2000-08-02T00:10:00,2e-12",
                    "2000-08-02T00:20:00,3e-12",
                ],
            ),
        )
        self.assertEqual(record["file_status"], "PASS")
        self.assertEqual(record["column_count"], 2)
        self.assertEqual(record["row_count"], 3)
        self.assertEqual(record["parse_fail_count"], 0)
        self.assertEqual(record["cadence_median_seconds"], 600.0)
        self.assertEqual(record["timestamp_timezone_status"], "timezone-naive")

    def test_timezone_aware_values_are_not_relabelled_as_naive(self) -> None:
        record = self._audit_one(
            "gr-of1-04265-20180601_to_20180604.csv",
            _csv_text(
                "Timestamp,Orbit Mean Density (kg/m^3)",
                [
                    "2020-01-01T00:00:00+03:30,1",
                    "2020-01-01T00:10:00+03:30,2",
                ],
            ),
        )
        self.assertEqual(record["file_status"], "PASS")
        self.assertEqual(record["timestamp_timezone_status"], "timezone-aware-utc-normalized")
        self.assertIn("+03:30", record["min_timestamp"])

    def test_mixed_timezone_values_are_flagged(self) -> None:
        record = self._audit_one(
            "grace2-02358-20020502_to_20020505.csv",
            _csv_text(
                "Timestamp,Orbit Mean Density (kg/m^3)",
                [
                    "2020-01-01T00:00:00,1",
                    "2020-01-01T00:10:00+00:00,2",
                ],
            ),
        )
        self.assertEqual(record["file_status"], "CHECK")
        self.assertEqual(record["timestamp_timezone_status"], "mixed")
        self.assertEqual(record["error_type"], "mixed_timezone")

    def test_missing_column_is_check(self) -> None:
        record = self._audit_one(
            "grace1-02285-20021110_to_20021113.csv",
            _csv_text("Timestamp,other", ["2000-01-01,1"]),
        )
        self.assertEqual(record["file_status"], "CHECK")
        self.assertEqual(record["error_type"], "missing_required_column")
        self.assertEqual(record["density_column"], "")

    def test_header_only_csv_is_check_not_fatal(self) -> None:
        record = self._audit_one(
            "swarma-06672-20140103_to_20140106.csv",
            "Timestamp,Orbit Mean Density (kg/m^3)\n",
        )
        self.assertEqual(record["file_status"], "CHECK")
        self.assertEqual(record["error_type"], "header_only")
        self.assertEqual(record["row_count"], 0)

    def test_unclassified_filename_requires_review(self) -> None:
        record = self._audit_one(
            "unknown_member.csv",
            _csv_text(
                "Timestamp,Orbit Mean Density (kg/m^3)",
                ["2000-01-01T00:00:00,1"],
            ),
        )
        self.assertEqual(record["satellite"], "unclassified")
        self.assertEqual(record["file_status"], "CHECK")
        self.assertEqual(record["error_type"], "filename_parse_failed")

    def test_parse_duplicate_nonmonotonic_and_density_failures(self) -> None:
        record = self._audit_one(
            "grace2-02358-20020502_to_20020505.csv",
            _csv_text(
                "Timestamp,Orbit Mean Density (kg/m^3)",
                [
                    "bad-time,not-a-number",
                    "2000-01-01T00:10:00,0",
                    "2000-01-01T00:10:00,",
                    "2000-01-01T00:00:00,-1",
                ],
            ),
        )
        self.assertEqual(record["file_status"], "CHECK")
        self.assertEqual(record["parse_fail_count"], 1)
        self.assertEqual(record["duplicate_timestamp_count"], 1)
        self.assertEqual(record["monotonicity_status"], "non_monotonic")
        self.assertEqual(record["density_numeric_fail_count"], 1)
        self.assertEqual(record["density_nan_count"], 1)
        self.assertEqual(record["density_nonpositive_count"], 2)


class OverlapTests(unittest.TestCase):
    def _audit_pair(self, left_rows: list[str], right_rows: list[str]):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            zip_path = root / "fixture.zip"
            files = {
                "champ_-00000-20000802_to_20000805.csv": _csv_text(
                    "Timestamp,Orbit Mean Density (kg/m^3)", left_rows
                ),
                "champ_-00001-20000802_to_20000805.csv": _csv_text(
                    "Timestamp,Orbit Mean Density (kg/m^3)", right_rows
                ),
            }
            with zipfile.ZipFile(zip_path, "w") as archive:
                for name, text in files.items():
                    archive.writestr(name, text)
            with zipfile.ZipFile(zip_path) as archive:
                audits = [
                    audit.audit_member(
                        archive,
                        zip_path,
                        archive.getinfo(name),
                        encoding="utf-8",
                        chunk_size=10,
                    )
                    for name in sorted(files)
                ]
            return audit.within_satellite_overlaps(audits)

    def test_interval_overlap_without_actual_timestamp_overlap(self) -> None:
        rows = self._audit_pair(
            ["2000-01-01T00:00:00,1", "2000-01-01T00:20:00,1"],
            ["2000-01-01T00:10:00,1", "2000-01-01T00:30:00,1"],
        )
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["interval_overlap"])
        self.assertEqual(rows[0]["actual_timestamp_overlap_count"], 0)

    def test_actual_timestamp_overlap(self) -> None:
        rows = self._audit_pair(
            ["2000-01-01T00:00:00,1", "2000-01-01T00:10:00,1"],
            ["2000-01-01T00:10:00,1", "2000-01-01T00:20:00,1"],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["actual_timestamp_overlap_count"], 1)


class EndToEndTests(unittest.TestCase):
    def test_pilot_writes_required_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            zip_path = root / "fixture.zip"
            entries = {
                "champ_-00000-20000802_to_20000805.csv": _csv_text(
                    "Timestamp,Orbit Mean Density (kg/m^3)", ["2000-01-01,1"]
                ),
                "grace1-02285-20021110_to_20021113.csv": _csv_text(
                    "Timestamp,Orbit Mean Density (kg/m^3)", ["2000-01-01,1"]
                ),
                "grace2-02358-20020502_to_20020505.csv": _csv_text(
                    "Timestamp,Orbit Mean Density (kg/m^3)", ["2000-01-01,1"]
                ),
                "swarma-06672-20140103_to_20140106.csv": _csv_text(
                    "Timestamp,Orbit Mean Density (kg/m^3)", ["2000-01-01,1"]
                ),
                "gr-of1-04265-20180601_to_20180604.csv": _csv_text(
                    "Timestamp,Orbit Mean Density (kg/m^3)", ["2000-01-01,1"]
                ),
                "difficult_name.csv": _csv_text(
                    "Timestamp,Orbit Mean Density (kg/m^3)", ["2000-01-01,1"]
                ),
            }
            with zipfile.ZipFile(zip_path, "w") as archive:
                for name, text in entries.items():
                    archive.writestr(name, text)
            output_dir = root / "out"
            summary = audit.run_audit(zip_path, output_dir, mode="pilot", chunk_size=2)
            self.assertEqual(summary["n_csv_members_selected"], 6)
            for name in (
                "full_file_schema_time_audit.csv",
                "satellite_summary.csv",
                "satellite_overlap_pairs.csv",
                "audit_run_summary.json",
                "audit_run_log.md",
            ):
                self.assertTrue((output_dir / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
