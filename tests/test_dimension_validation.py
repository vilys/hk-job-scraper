# -*- coding: utf-8 -*-
"""無效篩選值前置驗證（零網路）。

求職者實跑：`--source gov_hk --category 打字員` 只印一行 WARNING、
回傳未過濾的 20 筆且 exit 0，看起來「篩到了」其實完全沒篩。
本輪改為「支援該維度的站收到無效字典值 → exit 2、零請求」；
「該站不支援此維度 → 警告後忽略」是另一條既有規則，必須守住。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import unittest
from unittest import mock

from hkjobs import cli, contract, validation
from hkjobs.capabilities import SOURCES


def _ns(**kw):
    base = dict(source="gov_hk", keyword="", pages=1, days=None,
                district=None, category=None, industry=None, sort=None,
                detail=False, fill_location=False, fill_gaps=False,
                json=False, out=None, force=False, limit=20, no_list=False,
                sort_by=None, salary_by="mid", no_dedup=False, yes=False,
                quiet=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def _silent_run(argv):
    """擋掉真實請求：任何通過驗證的查詢都只回一個空的 ok 來源。"""
    empty = contract.SourceResult("ok_source", "ok", [])
    with mock.patch.object(cli, "_run_one", return_value=empty) as spy:
        code, out, err = _run(argv)
    return code, out, err, spy


class TestInvalidDimensionValue(unittest.TestCase):
    def test_invalid_category_blocked_before_any_request(self):
        code, out, err, spy = _silent_run(
            ["search", "--source", "gov_hk", "--category", "打字員", "--pages", "1"])
        self.assertEqual(code, contract.EXIT_USAGE)
        self.assertIn("打字", err)                    # 候選值
        self.assertIn("--dimension category", err)  # options 查詢命令
        self.assertIn("未過濾結果", err)
        self.assertEqual(spy.call_count, 0, "exit 2 前不得發出任何爬取請求")

    def test_error_text_is_cp950_encodable(self):
        _, _, err, _ = _silent_run(
            ["search", "--source", "gov_hk", "--category", "打字員", "--pages", "1"])
        err.encode("cp950")  # 不應 raise UnicodeEncodeError

    def test_valid_category_passes(self):
        code, _, err, spy = _silent_run(
            ["search", "--source", "gov_hk", "--category", "打字", "--pages", "1"])
        self.assertNotEqual(code, contract.EXIT_USAGE)
        self.assertNotIn("不是 gov_hk 的有效", err)
        self.assertEqual(spy.call_count, 1)

    def test_unsupported_station_keeps_warn_and_ignore(self):
        """moovup 不支援 --category：既有「警告後忽略」行為不得被誤擋。"""
        code, _, err, spy = _silent_run(
            ["search", "--source", "moovup", "--category", "亂七八糟", "--pages", "1"])
        self.assertNotEqual(code, contract.EXIT_USAGE)
        self.assertNotIn("不是 moovup 的有效", err)
        self.assertEqual(spy.call_count, 1)

    def test_days_is_not_a_dictionary_dimension(self):
        """--days 不屬字典維度；moovup 不支援時仍照舊忽略。"""
        code, _, _, spy = _silent_run(
            ["search", "--source", "moovup", "--days", "7", "--pages", "1"])
        self.assertNotEqual(code, contract.EXIT_USAGE)
        self.assertEqual(spy.call_count, 1)

    def test_all_source_rejects_value_invalid_everywhere(self):
        fatal, _ = validation.validate_dimensions(
            _ns(source="all", category="打字員"),
            [(n, i.enabled) for n, i in SOURCES.items()])
        self.assertTrue(fatal)

    def test_all_source_keeps_mixed_dictionary_differences(self):
        """部分站接受、部分站不接受時不能擋下整次 --source all。"""
        fatal, warnings = validation.validate_dimensions(
            _ns(source="all", district="屯門"),
            [(n, i.enabled) for n, i in SOURCES.items()])
        self.assertFalse(fatal)
        self.assertTrue(warnings)

    def test_free_text_dimension_is_not_validated(self):
        fatal, _ = validation.validate_dimensions(
            _ns(source="indeed", district="任意自由文字"), [("indeed", True)])
        self.assertFalse(fatal)

    def test_cjk_district_alias_is_not_a_false_positive(self):
        """scraper 接受「屯門區」這種別名，驗證層不能比它還嚴。"""
        from hkjobs.options import load_dimension

        accepted = validation._accepted_values(load_dimension("gov_hk", "district"))
        for value in ("屯門", "屯門區", "188"):
            with self.subTest(value=value):
                self.assertTrue(validation._is_accepted(value, accepted))

    def test_candidate_uses_fuzzy_match(self):
        from hkjobs.options import load_dimension

        info = load_dimension("gov_hk", "category")
        self.assertIn("打字", validation._candidates("打字員", info))
        self.assertEqual(validation._candidates("完全不相干的字串xyz", info), [])


if __name__ == "__main__":
    unittest.main()
