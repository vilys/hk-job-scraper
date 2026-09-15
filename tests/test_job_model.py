# -*- coding: utf-8 -*-
"""核心資料模型測試（零請求）。

涵蓋 JobRecord 的 id 生成、欄位集合、dict 往返、以及異常 raw 的防禦。
"""
from __future__ import annotations

import unittest

from job_model import JobRecord


def make(job_id: str = "liepin::1", **kw) -> JobRecord:
    """便利建構：預設 source 由 job_id 前綴推導。"""
    return JobRecord(job_id=job_id, source=job_id.split("::")[0], **kw)


class TestJobRecordBasics(unittest.TestCase):
    def test_make_id_format(self):
        self.assertEqual(JobRecord.make_id("liepin", "123"), "liepin::123")

    def test_fields_are_13(self):
        # CSV 欄位數依賴此常數，變動會影響所有既有匯出檔
        self.assertEqual(len(JobRecord.FIELDS), 13)

    def test_dedupe_key_is_job_id(self):
        self.assertEqual(make("a::7").dedupe_key(), "a::7")


class TestToFromDict(unittest.TestCase):
    def test_to_dict_excludes_raw(self):
        d = make(raw={"站方原始": "資料"}).to_dict()
        self.assertNotIn("raw", d)
        self.assertEqual(set(d), set(JobRecord.FIELDS))

    def test_from_dict_ignores_unknown_fields(self):
        j = JobRecord.from_dict({"job_id": "x::1", "source": "x", "不存在的欄位": 1})
        self.assertEqual(j.job_id, "x::1")

    def test_from_dict_repairs_non_dict_raw(self):
        # 既有匯出檔若 raw 被寫成字串，重建時必須安全退化為 {}
        self.assertEqual(JobRecord.from_dict({"job_id": "x::1", "raw": "oops"}).raw, {})

    def test_from_dict_derives_source_when_missing(self):
        """缺 source 時由 job_id 前綴推導，不可拋例外。

        否則 exporter 會把整份既有檔判為損毀 → 備份後清空舊資料。
        """
        self.assertEqual(JobRecord.from_dict({"job_id": "gov_hk::42"}).source, "gov_hk")

    def test_from_dict_survives_empty_job_id(self):
        j = JobRecord.from_dict({})
        self.assertEqual(j.source, "")
        self.assertEqual(j.job_id, "")

    def test_roundtrip_preserves_cjk(self):
        j = make(title="軟件工程師", company="某某科技有限公司")
        self.assertEqual(JobRecord.from_dict(j.to_dict()).title, "軟件工程師")


if __name__ == "__main__":
    unittest.main()
