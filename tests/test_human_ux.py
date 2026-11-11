# -*- coding: utf-8 -*-
"""人類模式 UX 回歸測試（零網路）。

對應 2026-11-11 求職者實測回報：
  P0-1 人類模式看不到職位、P2-1 提示矛盾、P2-4 薪金覆蓋率、
  P1-2 --out 無聲覆蓋、P2-5 --pages 0、P2-3 help 無範例、
  P1-1 --days 偷改排序。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from hkjobs import cli
from hkjobs.capabilities import SourceInfo
from hkjobs.contract import EXIT_USAGE, SourceResult
from job_model import JobRecord


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def _info(name="fake"):
    return SourceInfo(
        name=name, label="假站", enabled=True, needs_browser=False,
        needs_chrome=False, per_page=3, keyword_required=False,
        days_mode="list", sort_values=(), supports={}, request_delay=0.0, notes="",
    )


def _jobs():
    return [
        JobRecord(job_id="fake::1", source="fake", title="文員", company="",
                  location="紅磡", salary="$14,000 - $15,500", posted_date=""),
        JobRecord(job_id="fake::2", source="fake", title="資料輸入員",
                  company="", location="銅鑼灣", salary="", posted_date=""),
        JobRecord(job_id="fake::3", source="fake", title="行政助理",
                  company="", location="荃灣", salary="$16,000", posted_date=""),
    ]


class _Ok:
    def __init__(self):
        pass

    def scrape_all(self, **kwargs):
        return _jobs()

    def close(self):
        pass


def _patched(name="fake"):
    return mock.patch.multiple(cli, SOURCES={name: _info(name)}, SCRAPERS={name: _Ok})


class TestHumanJobList(unittest.TestCase):
    """P0-1：不加任何輸出旗標就要看得到職位。"""

    def test_default_lists_jobs_with_title_and_salary(self):
        with _patched():
            code, out, _ = _run(["search", "--source", "fake"])
        self.assertEqual(code, 0)
        self.assertIn("職位清單", out)
        self.assertIn("文員", out)
        self.assertIn("$14,000 - $15,500", out)
        self.assertIn("紅磡", out)
        self.assertIn("標題", out)
        self.assertIn("公司", out)
        self.assertIn("地區", out)
        self.assertIn("薪金", out)
        self.assertIn("刊登日", out)

    def test_empty_cells_show_dash_not_blank(self):
        with _patched():
            _, out, _ = _run(["search", "--source", "fake"])
        # 第 2 筆無薪金、3 筆皆無公司 → 都應顯示 —
        self.assertIn("—", out)

    def test_limit_and_hidden_hint(self):
        with _patched():
            _, out, _ = _run(["search", "--source", "fake", "--limit", "2"])
        self.assertIn("顯示 2 筆 / 共 3 筆", out)
        self.assertIn("另有 1 筆未列出", out)
        self.assertNotIn("行政助理", out)

    def test_limit_zero_prints_all(self):
        with _patched():
            _, out, _ = _run(["search", "--source", "fake", "--limit", "0"])
        self.assertIn("顯示 3 筆 / 共 3 筆", out)
        self.assertIn("行政助理", out)
        self.assertNotIn("另有", out)

    def test_no_list_keeps_summary_only(self):
        with _patched():
            _, out, _ = _run(["search", "--source", "fake", "--no-list"])
        self.assertIn("總計：3 筆", out)
        self.assertNotIn("職位清單", out)
        self.assertNotIn("$14,000", out)

    def test_json_mode_never_prints_human_list(self):
        with _patched():
            code, out, _ = _run(["search", "--source", "fake", "--json"])
        self.assertEqual(code, 0)
        self.assertNotIn("職位清單", out)
        self.assertEqual(json.loads(out)["summary"]["total"], 3)

    def test_truncate_by_display_width(self):
        from hkjobs.cli import _disp_width, _truncate
        s = _truncate("這是一段非常長的中文標題" * 5, 34)
        self.assertLessEqual(_disp_width(s), 34)
        self.assertTrue(s.endswith("…"))


class TestHumanHints(unittest.TestCase):
    """P2-1 / P2-4 / P0-2：提示只講下一步；薪金覆蓋率；公司名說明。"""

    def test_salary_coverage_shown_as_fraction(self):
        with _patched():
            _, out, _ = _run(["search", "--source", "fake"])
        self.assertIn("2/3 筆有薪金", out)

    def test_no_out_shows_next_step(self):
        with _patched():
            _, out, _ = _run(["search", "--source", "fake"])
        self.assertIn("加 --out", out)

    def test_written_out_shows_real_path_only(self):
        with _patched(), tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "result.json")
            _, out, _ = _run(["search", "--source", "fake", "--out", path])
        self.assertIn(f"已儲存 3 筆至 {path}", out)
        self.assertNotIn("加 --out result", out)

    def test_gov_hk_company_hint_when_all_blank(self):
        with _patched("gov_hk"):
            _, out, _ = _run(["search", "--source", "gov_hk"])
        self.assertIn("勞工處列表頁不含公司名", out)
        self.assertIn("--detail", out)

    def test_no_company_hint_when_company_present(self):
        class _WithCompany(_Ok):
            def scrape_all(self, **kwargs):
                jobs = _jobs()
                jobs[0].company = "某公司"
                return jobs

        with mock.patch.multiple(
            cli, SOURCES={"gov_hk": _info("gov_hk")}, SCRAPERS={"gov_hk": _WithCompany}
        ):
            _, out, _ = _run(["search", "--source", "gov_hk"])
        self.assertNotIn("勞工處列表頁不含公司名", out)


class TestOutOverwriteGuard(unittest.TestCase):
    """P1-2：既有檔案不得被無聲覆蓋；且在發請求前就擋下。"""

    def _existing(self, tmp, name="result.csv"):
        path = os.path.join(tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("OLD")
        return path

    def test_second_run_refuses_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._existing(tmp)
            with _patched(), mock.patch.object(cli, "_run_one") as spy:
                code, _, err = _run(["search", "--source", "fake", "--out", path])
            self.assertEqual(code, EXIT_USAGE)
            self.assertIn("檔案已存在", err)
            self.assertIn("--force", err)
            self.assertEqual(spy.call_count, 0, "不應在拒絕寫檔後還發出爬取請求")
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "OLD")

    def test_force_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._existing(tmp)
            with _patched():
                code, _, _ = _run(
                    ["search", "--source", "fake", "--out", path, "--force"]
                )
            self.assertEqual(code, 0)
            with open(path, "rb") as fh:
                self.assertTrue(fh.read().startswith(b"\xef\xbb\xbf"))

    def test_json_mode_contract_unchanged(self):
        # agent 契約：--json --out 仍可覆寫，不需 --force，exit code 不變。
        # 用 .json 副檔名，_write_out 才會寫完整封套（.csv 依副檔名寫 CSV）。
        with tempfile.TemporaryDirectory() as tmp:
            path = self._existing(tmp, "result.json")
            with _patched():
                code, out, _ = _run(
                    ["search", "--source", "fake", "--json", "--out", path]
                )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["summary"]["total"], 3)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["summary"]["total"], 3)

    def test_new_file_needs_no_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "fresh.csv")
            with _patched():
                code, _, _ = _run(["search", "--source", "fake", "--out", path])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(path))


class TestUsageEdges(unittest.TestCase):
    """P2-5 與 P1-1 的 CLI 層語意。"""

    def test_pages_zero_is_usage_error(self):
        with _patched(), mock.patch.object(cli, "_run_one") as spy:
            code, _, err = _run(["search", "--source", "fake", "--pages", "0"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("--pages", err)
        self.assertEqual(spy.call_count, 0)

    def test_days_does_not_change_query_sort(self):
        with _patched():
            code, out, _ = _run(
                ["search", "--source", "fake", "--days", "7", "--json"]
            )
        self.assertEqual(code, 0)
        self.assertIsNone(json.loads(out)["query"]["sort"])

    def test_explicit_sort_still_recorded(self):
        with _patched():
            _, out, _ = _run(
                ["search", "--source", "fake", "--days", "7",
                 "--sort", "post_dt_desc", "--json"]
            )
        self.assertEqual(json.loads(out)["query"]["sort"], "post_dt_desc")

    def test_json_envelope_unchanged_on_human_defaults(self):
        with _patched():
            code, out, _ = _run(["search", "--source", "fake", "--json"])
        payload = json.loads(out)
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(set(payload["jobs"][0]), set(JobRecord.FIELDS))


class TestHelpExamples(unittest.TestCase):
    """P2-3：help 要有範例與預設值。"""

    def test_help_has_examples_and_defaults(self):
        _, out, _ = _run(["search", "--help"])
        self.assertIn("常用範例", out)
        self.assertIn("文員", out)
        self.assertIn("--days 7", out)
        self.assertIn("--out analyst.csv", out)
        self.assertIn("預設 3", out)
        self.assertIn("前 20 筆", out)

    def test_legacy_parser_options_unchanged(self):
        # 新旗標只加在 hkjobs 專屬的 add_machine_arguments，
        # main.py 的參數集合一個都不能多。
        import main
        strings = {s for a in main.build_argparser()._actions for s in a.option_strings}
        self.assertNotIn("--force", strings)
        self.assertNotIn("--limit", strings)
        self.assertNotIn("--no-list", strings)


class TestHumanTableLayout(unittest.TestCase):
    def test_columns_aligned_by_display_width(self):
        import re

        from hkjobs.cli import _disp_width
        with _patched():
            _, out, _ = _run(["search", "--source", "fake"])
        header = next(l for l in out.splitlines() if l.lstrip().startswith("#"))
        rows = [l for l in out.splitlines() if re.match(r"^\s*\d+\s", l)]
        self.assertEqual(len(rows), 3)
        # 所有資料列經 _pad 補齊後，顯示寬度必須一致（CJK 不再擠歪）。
        self.assertEqual({_disp_width(l) for l in rows}, {_disp_width(header)})
        self.assertLessEqual(_disp_width(header), 130)


if __name__ == "__main__":
    unittest.main()
