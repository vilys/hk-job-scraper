# -*- coding: utf-8 -*-
"""聚合平台 schema v2 回歸測試（零網路）。

對應 2026-11-11 求職者實測回報：
  P0-A 薪金／日期正規化、P0-B 跨站排序、P1-A 去重、
  P1-B eFC 預設香港、P2-A 各站完整度。
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from hkjobs import aggregate, cli, contract
from hkjobs.capabilities import SourceInfo
from job_model import JobRecord

REF = "2026-11-11T12:21:00+00:00"


def _job(**kw):
    base = dict(job_id="x::1", source="x", title="文員", company="",
                location="", salary="", url="", posted_date="", scraped_at=REF)
    base.update(kw)
    return JobRecord(**base)


def _v2(**kw):
    return aggregate.to_v2(_job(**kw).to_dict())


# ---------------------------------------------------------------- P0-A 薪金
class TestSalaryParsing(unittest.TestCase):
    def test_k_unit_and_ranges(self):
        cases = [
            ("$15K/月", (15000, 15000, "month")),
            ("$11K-13K/月", (11000, 13000, "month")),
            ("$13K-14K/M", (13000, 14000, "month")),
            ("$15.5K - $16.5K", (15500, 16500, "month")),
            ("$13,000 - $14,000 （月薪）", (13000, 14000, "month")),
            ("$16,617 – $23,000 per month", (16617, 23000, "month")),
            ("$15K - $17K", (15000, 17000, "month")),
            ("$13,000 （月薪）", (13000, 13000, "month")),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(aggregate.parse_salary(raw), expected)

    def test_periods_converted_to_monthly(self):
        # 時薪 ×176（8h × 22 日）、日薪 ×22、年薪 ÷12
        self.assertEqual(aggregate.parse_salary("$60/hour"), (10560, 10560, "hour"))
        self.assertEqual(aggregate.parse_salary("$45-50/小時"), (7920, 8800, "hour"))
        self.assertEqual(aggregate.parse_salary("$800/day"), (17600, 17600, "day"))
        self.assertEqual(aggregate.parse_salary("$300,000 per annum"),
                         (25000, 25000, "year"))

    def test_negotiable_is_not_a_number(self):
        for raw in ("TBD", "Competitive", "Negotiable", "面議", "議價", "", "—"):
            with self.subTest(raw=raw):
                self.assertEqual(aggregate.parse_salary(raw), (None, None, None))
                self.assertFalse(aggregate.has_numeric_salary({"salary": raw}))

    def test_with_salary_counts_only_digits(self):
        results = [contract.SourceResult("a", "ok", [
            _job(salary="$15K/月"), _job(salary="TBD"), _job(salary="Competitive"),
        ])]
        payload = contract.search_payload({}, results, contract.EXIT_OK, dedup=False)
        self.assertEqual(payload["summary"]["withSalary"], 1)
        self.assertEqual(sum(1 for j in payload["jobs"]
                             if re.search(r"\d", j["salary"])), 1)


# ---------------------------------------------------------------- P0-A 日期
class TestDateParsing(unittest.TestCase):
    def test_six_real_formats_all_become_iso(self):
        cases = [
            "19h ago", "2026-10-24", "1 hrs ago", "11 Nov 2026",
            "23 hours ago", "Posted 3 months ago", "13d ago",
            "Updated on 10-23", "Updated within 3 months", "04 Nov 2026",
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                out = aggregate.parse_date(raw, REF)
                self.assertRegex(out, r"^\d{4}-\d{2}-\d{2}$")

    def test_minutes_and_article_forms_seen_in_real_data(self):
        # 2026-11-11 baseline 實測：jobsdb `49m ago`、foundit `an hour ago` / `a day ago`
        self.assertEqual(aggregate.parse_date("49m ago", REF), "2026-11-11")
        self.assertEqual(aggregate.parse_date("46m ago", REF), "2026-11-11")
        self.assertEqual(aggregate.parse_date("an hour ago", REF), "2026-11-11")
        self.assertEqual(aggregate.parse_date("a day ago", REF), "2026-11-10")

    def test_relative_uses_scraped_at_not_now(self):
        self.assertEqual(aggregate.parse_date("19h ago", REF), "2026-11-10")
        self.assertEqual(aggregate.parse_date("13d ago", REF), "2026-10-29")
        self.assertEqual(aggregate.parse_date("2 hrs ago", REF), "2026-11-11")

    def test_months_ago_is_reasonable(self):
        self.assertEqual(aggregate.parse_date("Posted 3 months ago", REF), "2026-08-13")

    def test_mmdd_year_rollover(self):
        self.assertEqual(aggregate.parse_date("Updated on 10-23", REF), "2026-10-23")
        self.assertEqual(aggregate.parse_date("Posted on 12-01", REF), "2025-12-01")

    def test_unparseable_returns_empty_and_raw_is_kept(self):
        j = _v2(posted_date="some day")
        self.assertEqual(j["posted_date"], "")
        self.assertEqual(j["posted_date_raw"], "some day")


# ---------------------------------------------------------------- schema v2
class TestSchemaV2(unittest.TestCase):
    def test_version_and_new_fields(self):
        self.assertEqual(contract.SCHEMA_VERSION, 2)
        j = _v2(salary="$15K - $17K", posted_date="19h ago")
        for key in aggregate.V2_EXTRA_FIELDS:
            self.assertIn(key, j)
        self.assertEqual(j["salary_min"], 15000)
        self.assertEqual(j["posted_date"], "2026-11-10")
        self.assertEqual(j["posted_date_raw"], "19h ago")
        self.assertEqual(j["sources"], ["x"])

    def test_csv_has_19_columns_and_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.csv")
            fields = aggregate.csv_fields(JobRecord.FIELDS)
            self.assertEqual(len(fields), 19)
            aggregate.write_csv([_v2(salary="$15K")], __import__("pathlib").Path(path), fields)
            with open(path, "rb") as fh:
                self.assertTrue(fh.read().startswith(b"\xef\xbb\xbf"))
            with open(path, encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["salary_min"], "15000")


# ---------------------------------------------------------------- P0-B 排序
class TestCrossSourceSort(unittest.TestCase):
    def setUp(self):
        self.jobs = [
            _v2(job_id="a::1", source="a", title="舊", posted_date="2026-10-01",
                salary="$10K", url="u1"),
            _v2(job_id="a::2", source="a", title="新", posted_date="2026-11-11",
                salary="$30K", url="u2"),
            _v2(job_id="b::1", source="b", title="中", posted_date="2026-11-05",
                salary="$20K", url="u3"),
            _v2(job_id="b::2", source="b", title="無日期", posted_date="",
                salary="", url="u4"),
        ]

    def test_date_is_not_source_blocked(self):
        out = aggregate.sort_jobs(self.jobs, "date")
        self.assertEqual([j["title"] for j in out], ["新", "中", "舊", "無日期"])
        self.assertEqual([j["source"] for j in out][:3], ["a", "b", "a"])

    def test_salary_desc_and_missing_last(self):
        out = aggregate.sort_jobs(self.jobs, "salary")
        self.assertEqual([j["salary_max"] for j in out[:3]], [30000, 20000, 10000])
        self.assertIsNone(out[-1]["salary_max"])

    def test_nothing_is_dropped(self):
        for by in ("date", "salary", None):
            self.assertEqual(len(aggregate.sort_jobs(self.jobs, by)), len(self.jobs))

    def test_all_defaults_to_date_single_source_does_not_sort(self):
        jobs = [
            _job(job_id="a::1", source="a", title="A", posted_date="", url="u1"),
            _job(job_id="a::2", source="a", title="B", posted_date="", url="u2"),
        ]
        payload_all = contract.search_payload(
            {}, [contract.SourceResult("a", "ok", jobs)], contract.EXIT_OK,
            sort_by="date")
        payload_one = contract.search_payload(
            {}, [contract.SourceResult("a", "ok", jobs)], contract.EXIT_OK,
            sort_by=None)
        self.assertEqual(payload_all["summary"]["sortBy"], "date")
        self.assertIsNone(payload_one["summary"]["sortBy"])


# ---------------------------------------------------------------- P1-A 去重
class TestDeduplication(unittest.TestCase):
    def test_same_url_merges(self):
        jobs = [_v2(url="same", title="A"), _v2(url="same", title="B")]
        out, n = aggregate.deduplicate(jobs)
        self.assertEqual((len(out), n), (1, 1))

    def test_same_title_and_company_merges_across_sources(self):
        jobs = [
            _v2(source="recruit", title="Procurement Clerk", company="High Win",
                url="u1"),
            _v2(source="jobmarket", title="procurement clerk", company="HIGH WIN",
                url="u2"),
        ]
        out, n = aggregate.deduplicate(jobs)
        self.assertEqual((len(out), n), (1, 1))
        self.assertEqual(out[0]["sources"], ["recruit", "jobmarket"])
        self.assertEqual(out[0]["urls"], ["u1", "u2"])

    def test_four_identical_become_one(self):
        jobs = [_v2(source="jobmarket", title="會計助理文員 (全職)",
                    company="Hung Fai", url=f"u{i}") for i in range(4)]
        out, n = aggregate.deduplicate(jobs)
        self.assertEqual(len(out), 1)
        self.assertEqual(n, 3)
        self.assertEqual(out[0]["sources"], ["jobmarket"])
        self.assertEqual(len(out[0]["urls"]), 4)

    def test_empty_company_uses_url_only(self):
        jobs = [_v2(title="文員", company="", url="u1"),
                _v2(title="文員", company="", url="u2")]
        out, n = aggregate.deduplicate(jobs)
        self.assertEqual((len(out), n), (2, 0))

    def test_total_plus_deduped_equals_raw(self):
        jobs = [
            _v2(source="a", title="X", company="C", url="u1"),
            _v2(source="a", title="X", company="C", url="u1"),
            _v2(source="b", title="Y", company="D", url="u2"),
        ]
        results = [contract.SourceResult("a", "ok", [
            _job(job_id="a::1", source="a", title="X", company="C", url="u1"),
            _job(job_id="a::2", source="a", title="X", company="C", url="u1"),
        ]), contract.SourceResult("b", "ok", [
            _job(job_id="b::1", source="b", title="Y", company="D", url="u2"),
        ])]
        payload = contract.search_payload({}, results, contract.EXIT_OK)
        s = payload["summary"]
        self.assertEqual(s["total"] + s["deduped"], s["rawTotal"])
        off = contract.search_payload({}, results, contract.EXIT_OK, dedup=False)
        self.assertEqual(off["summary"]["deduped"], 0)
        self.assertEqual(off["summary"]["total"], s["rawTotal"])


# ---------------------------------------------------------------- P1-B eFC
class TestEfcDefaultDistrict(unittest.TestCase):
    """不發請求：攔截 session.get，只看送出去的 params。"""

    def _params(self, district=None):
        from scrapers.efc import EfcScraper

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"data": [], "meta": {}}

        captured = {}

        def fake_get(url, params=None, timeout=None):
            captured.update(params or {})
            return _Resp()

        s = EfcScraper()
        s._session.get = fake_get
        try:
            s.search("analyst", page=1, district=district)
        finally:
            s.close()
        return captured

    def test_no_district_defaults_hong_kong(self):
        self.assertEqual(self._params().get("location"), "Hong Kong")

    def test_explicit_district_is_honoured(self):
        self.assertEqual(self._params("Kowloon").get("location"), "Kowloon")

    def test_unknown_district_falls_back_to_hong_kong(self):
        self.assertEqual(self._params("Atlantis").get("location"), "Hong Kong")


# ---------------------------------------------------------------- P2-A 完整度
class TestCoverage(unittest.TestCase):
    def _results(self):
        return [contract.SourceResult("a", "ok", [
            _job(job_id="a::1", source="a", title="A", company="C", location="HK",
                 salary="$15K", posted_date="2026-11-11", url="u1"),
            _job(job_id="a::2", source="a", title="B", company="", location="",
                 salary="TBD", posted_date="", url="u2"),
        ]), contract.SourceResult("off", "skipped")]

    def test_coverage_object_only_for_ok(self):
        payload = contract.search_payload({}, self._results(), contract.EXIT_OK)
        rows = payload["summary"]["sources"]
        self.assertEqual(rows[0]["coverage"],
                         {"jobs": 2, "company": 1, "salary": 1,
                          "location": 1, "date": 1})
        self.assertNotIn("coverage", rows[1])

    def test_human_coverage_table(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli._print_coverage_table(self._results())
        text = out.getvalue()
        self.assertIn("各站欄位完整度", text)
        self.assertIn("1/2", text)

    def test_advice_for_known_gaps(self):
        results = [contract.SourceResult("recruit", "ok", [
            _job(source="recruit", title="A", location="", url="u1")])]
        lines = aggregate.coverage_advice(results)
        self.assertTrue(any("--fill-location" in x for x in lines))


# ---------------------------------------------------------------- CLI 整合
def _info(name):
    return SourceInfo(
        name=name, label=name, enabled=True, needs_browser=False,
        needs_chrome=False, per_page=3, keyword_required=False,
        days_mode="list", sort_values=(), supports={}, request_delay=0.0, notes="",
    )


class _SrcA:
    def __init__(self):
        pass

    def scrape_all(self, **kwargs):
        return [
            _job(job_id="a::1", source="a", title="高薪", company="C1",
                 salary="$30K", posted_date="2026-11-11", url="u1"),
            _job(job_id="a::2", source="a", title="重複", company="C2",
                 salary="$10K", posted_date="2026-11-01", url="u2"),
        ]

    def close(self):
        pass


class _SrcB:
    def __init__(self):
        pass

    def scrape_all(self, **kwargs):
        return [
            _job(job_id="b::1", source="b", title="重複", company="C2",
                 salary="$10K", posted_date="2026-10-20", url="u3"),
            _job(job_id="b::2", source="b", title="無薪金", company="C3",
                 salary="TBD", posted_date="", url="u4"),
        ]

    def close(self):
        pass


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def _patched():
    return mock.patch.multiple(
        cli, SOURCES={"a": _info("a"), "b": _info("b")},
        SCRAPERS={"a": _SrcA, "b": _SrcB},
    )


class TestCliAggregation(unittest.TestCase):
    def test_all_dedup_and_sort(self):
        with _patched():
            code, out, _ = _run(["search", "--source", "all", "--json"])
        self.assertEqual(code, 0)
        p = json.loads(out)
        s = p["summary"]
        self.assertEqual(p["schemaVersion"], 2)
        self.assertEqual(s["rawTotal"], 4)
        self.assertEqual(s["total"] + s["deduped"], 4)
        self.assertEqual(s["deduped"], 1)
        self.assertEqual(s["sortBy"], "date")
        self.assertEqual(s["withSalary"], 2)  # TBD 不算
        dup = next(j for j in p["jobs"] if j["title"] == "重複")
        self.assertEqual(dup["sources"], ["a", "b"])
        self.assertEqual(dup["urls"], ["u2", "u3"])
        self.assertTrue(all(
            re.match(r"^\d{4}-\d{2}-\d{2}$", j["posted_date"])
            for j in p["jobs"] if j["posted_date"]))

    def test_no_dedup_keeps_raw_count(self):
        with _patched():
            _, out, _ = _run(["search", "--source", "all", "--json", "--no-dedup"])
        s = json.loads(out)["summary"]
        self.assertEqual(s["deduped"], 0)
        self.assertEqual(s["total"], 4)

    def test_sort_by_salary(self):
        with _patched():
            _, out, _ = _run(
                ["search", "--source", "all", "--json", "--sort-by", "salary"])
        p = json.loads(out)
        vals = [j["salary_max"] for j in p["jobs"] if j["salary_max"] is not None]
        self.assertEqual(vals, sorted(vals, reverse=True))
        self.assertIsNone(p["jobs"][-1]["salary_max"])

    def test_human_shows_sort_and_coverage(self):
        with _patched():
            code, out, _ = _run(["search", "--source", "all", "--limit", "0"])
        self.assertEqual(code, 0)
        self.assertIn("排序依據：刊登日期（新→舊）", out)
        self.assertIn("各站欄位完整度", out)
        self.assertIn("去重：合併 1 筆", out)
        self.assertIn("2/3 筆有薪金", out)

    def test_single_source_keeps_relevance_order(self):
        with _patched():
            _, out, _ = _run(["search", "--source", "a", "--json"])
        p = json.loads(out)
        self.assertIsNone(p["summary"]["sortBy"])
        self.assertEqual([j["title"] for j in p["jobs"]], ["高薪", "重複"])


if __name__ == "__main__":
    unittest.main()
