# -*- coding: utf-8 -*-
"""匯出與去重測試（零請求，使用暫存目錄）。

鎖定三件不容回退的事：
  1. 增量寫入依 job_id 去重（後到的覆蓋）
  2. CSV 必須帶 UTF-8 BOM（Excel 讀繁中）、且恰 13 欄
  3. 既有檔損毀時要先備份 .corrupt.bak，不能靜默清空舊資料
     （2026-08-19 修復的行為，見 output/optimization_report.md）
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
import unittest

import exporter
from job_model import JobRecord


def make(job_id: str, **kw) -> JobRecord:
    return JobRecord(job_id=job_id, source=job_id.split("::")[0], **kw)


class TestDedupe(unittest.TestCase):
    def test_same_id_kept_once_and_latest_wins(self):
        jobs = [make("a::1", title="舊"), make("a::1", title="新"), make("a::2")]
        out = {j.job_id: j.title for j in exporter._dedupe(jobs)}
        self.assertEqual(len(out), 2)
        self.assertEqual(out["a::1"], "新")


class TestExportJson(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="hkj_test_")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_incremental_merges_and_dedupes(self):
        path = os.path.join(self.dir, "t.json")
        first = exporter.export_json([make("a::1"), make("a::2")], path)
        second = exporter.export_json([make("a::2"), make("a::3")], path)
        self.assertEqual(first, 2)
        self.assertEqual(second, 3)
        with open(path, encoding="utf-8") as f:
            ids = {d["job_id"] for d in json.load(f)}
        self.assertEqual(ids, {"a::1", "a::2", "a::3"})

    def test_non_incremental_overwrites(self):
        path = os.path.join(self.dir, "t.json")
        exporter.export_json([make("a::1"), make("a::2")], path)
        total = exporter.export_json([make("b::9")], path, incremental=False)
        self.assertEqual(total, 1)

    def test_corrupt_existing_file_is_backed_up_not_silently_dropped(self):
        path = os.path.join(self.dir, "bad.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{ 這不是合法的 json ")
        total = exporter.export_json([make("a::9")], path)
        self.assertEqual(total, 1)
        self.assertTrue(os.path.exists(path + ".corrupt.bak"),
                        "損毀檔必須先備份，否則舊資料會靜默消失")


class TestExportCsv(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="hkj_test_")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_has_utf8_bom(self):
        path = os.path.join(self.dir, "t.csv")
        exporter.export_csv([make("a::1", title="會計")], path)
        with open(path, "rb") as f:
            self.assertEqual(f.read(3), b"\xef\xbb\xbf")

    def test_header_is_exactly_13_fields(self):
        path = os.path.join(self.dir, "t.csv")
        exporter.export_csv([make("a::1")], path)
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(list(rows[0]), list(JobRecord.FIELDS))

    def test_incremental_dedupe(self):
        path = os.path.join(self.dir, "t.csv")
        exporter.export_csv([make("a::1"), make("a::2")], path)
        total = exporter.export_csv([make("a::2"), make("a::3")], path)
        self.assertEqual(total, 3)


if __name__ == "__main__":
    unittest.main()
