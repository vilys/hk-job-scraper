# -*- coding: utf-8 -*-
"""聚合平台 v2 第二輪修正回歸測試（零網路）。

對應 2026-11-11 求職者情境 A/B/C 回報：
  P0  gov_hk 詳情頁 DD/MM/YYYY 無法正規化
  P1-A --sort-by salary 改用中位數（可選 min|mid|max）
  P1-B 時薪／日薪換月薪基準需可辨識
  P2-A --fill-gaps 一鍵補齊
  P2-B tools/ 在 cp950 主控台的 --help 不可 crash
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from hkjobs import aggregate, cli, contract
from hkjobs.capabilities import GAP_FILL_ACTIONS, SourceInfo
from job_model import JobRecord

ROOT = Path(__file__).resolve().parent.parent
REF = "2026-11-11T12:00:00+00:00"


def _job(**kw):
    base = dict(job_id="x::1", source="x", title="文員", company="",
                location="", salary="", url="", posted_date="", scraped_at=REF)
    base.update(kw)
    return JobRecord(**base)


def _v2(**kw):
    return aggregate.to_v2(_job(**kw).to_dict())


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------- P0
class TestGovHkDetailDate(unittest.TestCase):
    """勞工處詳情頁 #postedDt 是 DD/MM/YYYY（日在前），不是 MM/DD。"""

    def test_dd_mm_yyyy_is_day_first(self):
        cases = {
            "10/11/2026": "2026-11-10",   # 以 DD/MM 解讀為 11 月 10 日
            "01/02/2026": "2026-02-01",   # 明確以日在前解讀（MM/DD 會變 1 月 2 日）
            "31/12/2026": "2026-12-31",   # 31 不可能當月 → 只能日在前
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(aggregate.parse_date(raw, REF), expected)

    def test_empty_and_invalid_stay_empty(self):
        for raw in ("", "   ", "32/13/2026", "0/0/2026", "29/02/2026", "some day"):
            with self.subTest(raw=raw):
                self.assertEqual(aggregate.parse_date(raw, REF), "")

    def test_unparseable_keeps_raw_in_v2(self):
        j = _v2(posted_date="32/13/2026")
        self.assertEqual(j["posted_date"], "")
        self.assertEqual(j["posted_date_raw"], "32/13/2026")

    def test_mmdd_and_iso_formats_not_regressed(self):
        self.assertEqual(aggregate.parse_date("on 11-10", REF), "2026-11-10")
        self.assertEqual(aggregate.parse_date("2026-11-10", REF), "2026-11-10")
        self.assertEqual(aggregate.parse_date("19h ago", REF), "2026-11-10")
        self.assertEqual(aggregate.parse_date("11 Nov 2026", REF), "2026-11-11")
        self.assertEqual(aggregate.parse_date("2026/11/03", REF), "2026-11-03")

    def test_real_12_gov_hk_detail_rows_all_become_iso(self):
        """output/打字_30天.csv = 上一輪真跑 --detail 的 12 筆（raw 12/12、ISO 0/12）。"""
        path = ROOT / "output" / "打字_30天.csv"
        if not path.exists():
            self.skipTest("缺少真實基準檔 output/打字_30天.csv")
        with path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 12)
        self.assertEqual(sum(1 for r in rows if r["posted_date_raw"]), 12)
        converted = [aggregate.parse_date(r["posted_date_raw"], REF) for r in rows]
        self.assertEqual(sum(1 for d in converted if d), 12)
        for d in converted:
            self.assertRegex(d, r"^\d{4}-\d{2}-\d{2}$")

    def test_gov_hk_no_longer_sinks_in_date_sort(self):
        """離線重播：把 baseline 的 20 筆 gov_hk 補上真實格式後，不應整批排最後。"""
        baseline = ROOT / "output" / "all_baseline.json"
        if not baseline.exists():
            self.skipTest("缺少 output/all_baseline.json")
        envelope = json.loads(baseline.read_text(encoding="utf-8"))
        gov = [j for j in envelope["jobs"] if j["source"] == "gov_hk"]
        self.assertEqual(len(gov), 20)
        for j in gov:
            j["posted_date"] = "10/11/2026"
        results = [
            contract.SourceResult(s["name"], s["status"],
                                  [JobRecord.from_dict(j) for j in envelope["jobs"]
                                   if j["source"] == s["name"]], s["error"])
            for s in envelope["summary"]["sources"]
        ]
        payload = contract.search_payload({}, results, contract.EXIT_OK, sort_by="date")
        jobs = payload["jobs"]
        last_missing = next((i for i, j in enumerate(jobs) if not j["posted_date"]), len(jobs))
        self.assertTrue(any(j["source"] == "gov_hk" for j in jobs[:last_missing]),
                        "gov_hk 不應全部落在無日期區段")


# ---------------------------------------------------------------- P1-A
class TestSalarySortByMedian(unittest.TestCase):
    """求職者實測：14K-27K（上限 27000）不該排在 18K-24K 前面。"""

    def setUp(self):
        self.jobs = [
            _v2(job_id="x::1", title="廣區間", salary="$14K-27K/月", url="u1"),
            _v2(job_id="x::2", title="高底薪", salary="$18,000 - $24,000 （月薪）", url="u2"),
            _v2(job_id="x::3", title="單點", salary="$20K", url="u3"),
            _v2(job_id="x::4", title="面議", salary="Competitive", url="u4"),
        ]

    def test_mid_is_default_and_orders_by_median(self):
        out = aggregate.sort_jobs(self.jobs, "salary")
        self.assertEqual([j["title"] for j in out],
                         ["高底薪", "廣區間", "單點", "面議"])
        self.assertEqual(aggregate.salary_sort_value(out[0]), 21000)
        self.assertEqual(aggregate.salary_sort_value(out[1]), 20500)

    def test_min_and_max_still_available(self):
        self.assertEqual(
            [j["title"] for j in aggregate.sort_jobs(self.jobs, "salary", salary_by="max")],
            ["廣區間", "高底薪", "單點", "面議"])
        self.assertEqual(
            [j["title"] for j in aggregate.sort_jobs(self.jobs, "salary", salary_by="min")],
            ["單點", "高底薪", "廣區間", "面議"])

    def test_invalid_salary_by_raises(self):
        with self.assertRaises(ValueError):
            aggregate.sort_jobs(self.jobs, "salary", salary_by="nope")

    def test_nothing_dropped_and_unknown_date_sort_unchanged(self):
        for by in ("min", "mid", "max"):
            self.assertEqual(len(aggregate.sort_jobs(self.jobs, "salary", salary_by=by)), 4)
        self.assertEqual(aggregate.sort_label("date"), "刊登日期（新→舊）")

    def test_human_output_states_the_basis(self):
        results = [contract.SourceResult("x", "ok", [
            _job(job_id="x::1", title="廣區間", salary="$14K-27K/月", url="u1"),
            _job(job_id="x::2", title="高底薪", salary="$18,000 - $24,000 （月薪）", url="u2"),
        ])]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli._print_human(results, contract.EXIT_OK, jobs=self.jobs[:2],
                             sort_by="salary", salary_by="mid", list_limit=2)
        self.assertIn("月薪中位數 (min+max)/2", out.getvalue())

    def test_replay_and_payload_record_salary_by(self):
        results = [contract.SourceResult("x", "ok", [
            _job(job_id="x::1", title="A", salary="$14K-27K/月", url="u1"),
        ])]
        p = contract.search_payload({}, results, contract.EXIT_OK,
                                    sort_by="salary", salary_by="max")
        self.assertEqual(p["query"]["salaryBy"], "max")
        self.assertEqual(p["summary"]["sortBy"], "salary")
        p_date = contract.search_payload({}, results, contract.EXIT_OK, sort_by="date")
        self.assertNotIn("salaryBy", p_date["query"])


# ---------------------------------------------------------------- P1-B
class TestConvertedSalaryIsVisible(unittest.TestCase):
    """時薪／日薪換成的月薪是估算，人類清單要能與原生月薪區分。"""

    def test_period_conversion_matches_documented_basis(self):
        self.assertEqual(aggregate.parse_salary("$50 - $60 （時薪）"),
                         (8800, 10560, "hour"))
        self.assertEqual(aggregate.parse_salary("$400 （日薪）"), (8800, 8800, "day"))
        self.assertEqual(aggregate.PERIOD_TO_MONTH["hour"], 8 * 22)
        self.assertEqual(aggregate.PERIOD_TO_MONTH["day"], 22)

    def test_converted_cell_is_marked_and_month_cell_is_not(self):
        hourly = _v2(salary="$50 - $60 （時薪）")
        monthly = _v2(salary="$14,000 - $15,000 （月薪）")
        self.assertIn("約$8,800-10,560/月", cli._salary_cell(hourly))
        self.assertIn("原時薪 $50 - $60", cli._salary_cell(hourly))
        self.assertEqual(cli._salary_cell(monthly), "$14,000 - $15,000 （月薪）")
        self.assertNotIn("約", cli._salary_cell(monthly))

    def test_single_point_and_unknown_salary(self):
        self.assertEqual(cli._salary_cell(_v2(salary="$400 （日薪）")),
                         "約$8,800/月 (原日薪 $400)")
        self.assertEqual(cli._salary_cell(_v2(salary="Competitive")), "Competitive")
        self.assertEqual(cli._salary_cell(_v2(salary="")), "—")

    def test_human_table_prints_conversion_basis(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli._print_jobs_table([_v2(salary="$50 - $60 （時薪）")], limit=1)
        text = out.getvalue()
        self.assertIn("約$8,800-10,560/月", text)
        self.assertIn("每日 8 小時", text)
        self.assertIn("22 個工作日", text)
        self.assertIn("非實際月薪", text)

    def test_no_basis_line_without_converted_rows(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli._print_jobs_table([_v2(salary="$15K/月")], limit=1)
        self.assertNotIn("非實際月薪", out.getvalue())


# ------------------------------------------- 用戶端覆核：薪金欄截斷單位詞
class TestSalaryUnitSurvivesTruncation(unittest.TestCase):
    """長原文被 36 格截斷時，單位詞（時薪／日薪／年薪）必須仍可見。

    求職者實測（修正前）：`約$10,560-11,440/月 (原 $60 - $65 …` 看不出怎麼算糧。
    顯示層把單位詞移到原文之前，截斷時先犧牲數字尾段而非單位。
    """

    WIDTH = 36

    def test_long_hourly_raw_keeps_unit_after_truncation(self):
        cell = cli._salary_cell(_v2(salary="$60 - $65 （時薪）"))
        truncated = cli._truncate(cell, self.WIDTH)
        self.assertGreater(cli._disp_width(cell), self.WIDTH, "這筆必須真的被截斷")
        self.assertIn("時薪", truncated)
        self.assertIn("約", truncated)

    def test_all_periods_and_long_raws_keep_unit(self):
        cases = {
            "$65 - $100 （時薪）": "時薪",
            "$400 - $500 （日薪）": "日薪",
            "$200,000 - $250,000 （年薪）": "年薪",
            "$50-60/小時": "時薪",   # 非全形括號寫法，靠前置單位詞標明
        }
        for raw, unit in cases.items():
            with self.subTest(raw=raw):
                cell = cli._salary_cell(_v2(salary=raw))
                truncated = cli._truncate(cell, self.WIDTH)
                self.assertIn(unit, truncated)
                self.assertLessEqual(cli._disp_width(truncated), self.WIDTH)

    def test_human_table_row_shows_the_unit(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli._print_jobs_table([_v2(salary="$60 - $65 （時薪）")], limit=1)
        self.assertIn("原時薪", out.getvalue())

    def test_short_raw_has_no_duplicated_unit(self):
        cell = cli._salary_cell(_v2(salary="$80 （時薪）"))
        self.assertEqual(cell, "約$14,080/月 (原時薪 $80)")
        self.assertEqual(cell.count("時薪"), 1)

    def test_display_change_does_not_touch_payload_contract(self):
        """只改人類輸出：salary 原文、19 個 jobs[] 欄位、schemaVersion 全不變。"""
        raw = "$60 - $65 （時薪）"
        job = _v2(salary=raw)
        before = dict(job)
        cli._salary_cell(job)
        self.assertEqual(job, before, "_salary_cell 不得改動傳入的 job")
        payload = contract.search_payload(
            {}, [contract.SourceResult("x", "ok", [_job(salary=raw)])],
            contract.EXIT_OK,
        )
        v2job = payload["jobs"][0]
        self.assertEqual(payload["schemaVersion"], 2)
        self.assertEqual(len(v2job), 19)
        self.assertEqual(v2job["salary"], raw)
        self.assertEqual(v2job["salary_period"], "hour")
        self.assertEqual((v2job["salary_min"], v2job["salary_max"]), (10560, 11440))

    def test_cell_is_cp950_encodable(self):
        for raw in ("$60 - $65 （時薪）", "$400 （日薪）", "$200,000 （年薪）"):
            with self.subTest(raw=raw):
                cli._salary_cell(_v2(salary=raw)).encode("cp950")


# ---------------------------------------------------------------- P2-A
_GAP_CALLS: dict[str, dict] = {}


def _gap_info(name, per_page):
    return SourceInfo(name=name, label=name, enabled=True, needs_browser=False,
                      needs_chrome=False, per_page=per_page, keyword_required=False,
                      days_mode="list", sort_values=(), supports={},
                      request_delay=0.0, notes="")


class _GapBase:
    name = ""

    def scrape_all(self, **kw):
        _GAP_CALLS[self.name] = kw
        detail, fill = kw.get("with_detail"), kw.get("fill_location")
        company = "某公司" if (self.name == "gov_hk" and detail) else ""
        posted = ("10/11/2026" if self.name == "gov_hk" else "11 Nov 2026") \
            if (self.name in ("gov_hk", "moovup") and detail) else ""
        location = "中環" if (self.name == "recruit" and fill) else ""
        return [JobRecord(job_id=f"{self.name}::1", source=self.name,
                          title="文員", company=company, location=location,
                          salary="$15K", url=f"u-{self.name}", posted_date=posted)]

    def close(self):
        pass


def _gap_patch():
    infos = {n: _gap_info(n, p) for n, p in
             (("moovup", 12), ("gov_hk", 20), ("recruit", 25), ("jobsdb", 30))}
    registry = {n: type("S_" + n, (_GapBase,), {"name": n}) for n in infos}
    return mock.patch.multiple(cli, SOURCES=infos, SCRAPERS=registry)


class TestFillGaps(unittest.TestCase):
    def setUp(self):
        _GAP_CALLS.clear()

    def test_estimate_before_requests_and_cancel_is_free(self):
        with _gap_patch(), mock.patch.object(cli, "_run_one") as spy, \
                mock.patch("builtins.input", return_value="n"):
            code, out, err = _run(["search", "--source", "all", "--pages", "1",
                                   "--fill-gaps"])
        self.assertEqual(code, contract.EXIT_USAGE)
        self.assertIn("約 57 支請求", out)
        self.assertIn("moovup", out)
        self.assertIn("約 20 支", out)
        self.assertIn("略過 1 站（jobsdb）", out)
        self.assertEqual(spy.call_count, 0, "取消後不應發出任何請求")

    def test_yes_applies_flags_per_source_and_records_query(self):
        with _gap_patch():
            code, out, err = _run(["search", "--source", "all", "--pages", "1",
                                   "--fill-gaps", "--yes", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)          # stdout 必須仍是單一封套
        self.assertTrue(payload["query"]["fillGaps"])
        self.assertIn("約 57 支請求", err)  # 公告走 stderr
        self.assertTrue(_GAP_CALLS["gov_hk"]["with_detail"])
        self.assertTrue(_GAP_CALLS["moovup"]["with_detail"])
        self.assertTrue(_GAP_CALLS["recruit"]["fill_location"])
        self.assertFalse(_GAP_CALLS["jobsdb"]["with_detail"])
        self.assertFalse(_GAP_CALLS["jobsdb"]["fill_location"])

    def test_json_skips_interactive_confirmation(self):
        with _gap_patch(), mock.patch("builtins.input", side_effect=AssertionError("不該問")):
            code, out, _ = _run(["search", "--source", "all", "--pages", "1",
                                 "--fill-gaps", "--json"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["query"]["fillGaps"])

    def test_coverage_gaps_actually_close(self):
        with _gap_patch():
            _, plain, _ = _run(["search", "--source", "all", "--pages", "1", "--json"])
            _, filled, _ = _run(["search", "--source", "all", "--pages", "1",
                                 "--fill-gaps", "--yes", "--json"])
        before = {s["name"]: s["coverage"] for s in json.loads(plain)["summary"]["sources"]}
        after = {s["name"]: s["coverage"] for s in json.loads(filled)["summary"]["sources"]}
        self.assertEqual(before["gov_hk"]["company"], 0)
        self.assertEqual(after["gov_hk"]["company"], 1)
        self.assertEqual(after["gov_hk"]["date"], 1)   # DD/MM/YYYY 也一併正規化
        self.assertEqual(before["moovup"]["date"], 0)
        self.assertEqual(after["moovup"]["date"], 1)
        self.assertEqual(before["recruit"]["location"], 0)
        self.assertEqual(after["recruit"]["location"], 1)

    def test_already_given_flags_are_not_double_counted(self):
        with _gap_patch(), mock.patch("builtins.input", return_value="n"):
            _, out, _ = _run(["search", "--source", "all", "--pages", "1",
                              "--fill-gaps", "--detail"])
        self.assertIn("約 25 支請求", out)   # 只剩 recruit
        self.assertIn("旗標已給，不額外計", out)

    def test_recruit_single_district_is_zero_requests(self):
        with _gap_patch(), mock.patch("builtins.input", return_value="n"):
            _, out, _ = _run(["search", "--source", "all", "--pages", "1",
                              "--fill-gaps", "--district", "中環"])
        self.assertIn("約 32 支請求", out)   # 12 + 20 + 0

    def test_without_flag_query_is_false_and_no_announcement(self):
        with _gap_patch():
            code, out, err = _run(["search", "--source", "all", "--pages", "1", "--json"])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(out)["query"]["fillGaps"])
        self.assertNotIn("--fill-gaps 將補齊", err)
        self.assertFalse(any(k.get("with_detail") for k in _GAP_CALLS.values()))


# ---------------------------------------------------------------- P2-B
class TestToolHelpOnCp950(unittest.TestCase):
    """Windows cp950 主控台：--help 不能因 ⚠️ 之類的字元直接 crash。"""

    def _env(self):
        return dict(os.environ, PYTHONIOENCODING="cp950")

    def test_replay_help_is_clean(self):
        proc = subprocess.run(
            [sys.executable, "tools/replay_aggregation.py", "--help"],
            cwd=ROOT, capture_output=True, env=self._env(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertNotIn(b"UnicodeEncodeError", proc.stderr)
        text = proc.stdout.decode("utf-8", "replace")
        self.assertIn("離線重播", text)
        self.assertIn("--salary-by", text)

    def test_hkjobs_search_help_is_clean(self):
        proc = subprocess.run(
            [sys.executable, "-m", "hkjobs", "search", "--help"],
            cwd=ROOT, capture_output=True, env=self._env(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertNotIn(b"UnicodeEncodeError", proc.stderr)
        text = proc.stdout.decode("utf-8", "replace")
        self.assertIn("--fill-gaps", text)
        self.assertIn("--salary-by", text)

    def test_main_py_help_is_clean(self):
        # main.py 沒有 configure_io()，共用 args.py 的 help 文字必須本身可編碼。
        proc = subprocess.run(
            [sys.executable, "main.py", "--help"],
            cwd=ROOT, capture_output=True, env=self._env(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertNotIn(b"UnicodeEncodeError", proc.stderr)

    def test_all_tool_docstrings_are_cp950_encodable(self):
        import ast

        for path in sorted((ROOT / "tools").glob("*.py")):
            with self.subTest(script=path.name):
                doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
                doc.encode("cp950")   # 不應 raise UnicodeEncodeError

    def test_probe_scripts_protect_both_streams(self):
        for name in ("_probe_li_guest.py", "_probe_liepin.py",
                     "probe_offertoday.py", "probe_ot_cold.py"):
            with self.subTest(script=name):
                text = (ROOT / "tools" / name).read_text(encoding="utf-8")
                self.assertIn("sys.stdout, sys.stderr", text)
                self.assertIn('reconfigure(encoding="utf-8")', text)


if __name__ == "__main__":
    unittest.main()
