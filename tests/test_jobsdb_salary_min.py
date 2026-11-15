# -*- coding: utf-8 -*-
"""JobsDB `--salary-min` 站方端下推與客戶端兜底（零請求、離線）。

守住四件事：
  1. GraphQL filter 形狀：`salaryMin:"<N>m"`，可與 `listedAt` 共存且只有一個 filter；
  2. SSR fallback：`salaryrange=<N>-&salarytype=monthly`，與 daterange/keywords 共存；
  3. 沒有站方端參數的來源，由 BaseScraper 客戶端兜底真實生效（不做「假成功」）；
  4. CLI 透傳、`query.salaryMin` 回顯、非法值在 parse 階段擋下。

所有對外請求一律用 mock 擋下：不連網、不啟動瀏覽器、不讀外部快照。
"""
from __future__ import annotations

import io
import json
import os
import re
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from base_scraper import BaseScraper
from hkjobs import cli
from hkjobs.args import build_search_argparser
from hkjobs.capabilities import SourceInfo
from job_model import JobRecord
from scrapers.jobsdb import (
    JobsDBScraper,
    build_graphql_query,
    graphql_salary_min,
)


def make_job(job_id="j1", salary="", posted_date="1d ago", source="jobsdb"):
    """最小 13 欄 JobRecord；只填與薪金篩選有關的欄位。"""
    return JobRecord(
        job_id=job_id,
        source=source,
        title="Engineer",
        company="Example Ltd",
        location="Hong Kong",
        salary=salary,
        job_type="Full time",
        industry="IT",
        description="",
        requirements="",
        url=f"https://example.test/job/{job_id}",
        posted_date=posted_date,
        scraped_at="2026-11-15T00:00:00",
    )


class TestGraphqlSalaryMin(unittest.TestCase):
    def test_positive_integer_becomes_monthly_literal(self):
        self.assertEqual(graphql_salary_min(17000), "17000m")
        self.assertEqual(graphql_salary_min("25000"), "25000m")

    def test_invalid_values_yield_empty(self):
        for value in (0, None, -1, "", "abc", [], {}):
            with self.subTest(value=value):
                self.assertEqual(graphql_salary_min(value), "")

    def test_float_truncates_to_int(self):
        self.assertEqual(graphql_salary_min(17000.9), "17000m")

    def test_suffix_is_monthly_only(self):
        # 只有 monthly 有離線實證；不可偷偷改成 h（hourly）或 a（annual）。
        self.assertTrue(graphql_salary_min(1).endswith("m"))


class TestBuildQueryWithSalaryMin(unittest.TestCase):
    def _query(self, **kwargs):
        kwargs.setdefault("keyword", "ai agent")
        kwargs.setdefault("visitor_id", "11111111-1111-1111-1111-111111111111")
        kwargs.setdefault("session_id", "22222222-2222-2222-2222-222222222222")
        return build_graphql_query(**kwargs)

    def test_salary_min_only(self):
        q = self._query(salary_min=17000)
        self.assertIn('filter: {salaryMin: "17000m"}', q)
        # jobs 選擇集本身有 `listedAt { dateTimeUtc }`；這裡只檢查 filter 內沒有
        # 日期條件（filter 的寫法帶冒號）。
        self.assertNotIn("listedAt:", q)
        self.assertEqual(q.count("{"), q.count("}"))
        self.assertEqual(re.findall(r"__[A-Z_]+__", q), [])

    def test_listed_at_and_salary_min_share_one_filter(self):
        q = self._query(listed_at="7d", salary_min=17000)
        self.assertIn('filter: {listedAt: "7d", salaryMin: "17000m"}', q)
        self.assertEqual(q.count("filter:"), 1)
        self.assertEqual(q.count("{"), q.count("}"))

    def test_no_salary_min_keeps_existing_shape(self):
        q = self._query(listed_at="7d")
        self.assertIn('filter: {listedAt: "7d"}', q)
        self.assertNotIn("salaryMin", q)

    def test_zero_or_none_means_no_filter(self):
        for value in (0, None):
            with self.subTest(value=value):
                q = self._query(salary_min=value)
                self.assertNotIn("filter:", q)
                self.assertNotIn("salaryMin", q)

    def test_bad_value_does_not_break_query(self):
        q = self._query(salary_min="not-a-number")
        self.assertNotIn("salaryMin", q)
        self.assertEqual(q.count("{"), q.count("}"))

    def test_no_credentials_in_query(self):
        q = self._query(salary_min=17000)
        for banned in ("Cookie", "Authorization", "Bearer", "li_at"):
            self.assertNotIn(banned, q)


class TestSetSalaryMin(unittest.TestCase):
    def test_sets_positive_value(self):
        s = JobsDBScraper()
        s.set_salary_min(17000)
        self.assertEqual(s._salary_min, 17000)

    def test_zero_and_negative_reset_to_off(self):
        s = JobsDBScraper()
        s.set_salary_min(17000)
        s.set_salary_min(0)
        self.assertEqual(s._salary_min, 0)
        s.set_salary_min(17000)
        s.set_salary_min(-5)
        self.assertEqual(s._salary_min, 0)

    def test_bad_value_warns_and_keeps_previous_state(self):
        s = JobsDBScraper()
        s.set_salary_min(17000)
        with self.assertLogs("scrapers.jobsdb", level="WARNING"):
            s.set_salary_min("abc")
        self.assertEqual(s._salary_min, 17000)


class TestBrowserUrlFilter(unittest.TestCase):
    def test_salary_only(self):
        s = JobsDBScraper()
        s.set_salary_min(17000)
        url = s._build_url("", None, None, 1)
        self.assertIn("salaryrange=17000-", url)
        self.assertIn("salarytype=monthly", url)

    def test_coexists_with_days_keyword_page_and_sort(self):
        s = JobsDBScraper()
        s.set_days(7)
        s.set_salary_min(17000)
        url = s._build_url("ai agent", None, None, 2, sort="post_dt_desc")
        for part in (
            "keywords=ai%20agent",
            "page=2",
            "sortmode=ListedDate",
            "daterange=7",
            "salaryrange=17000-",
            "salarytype=monthly",
        ):
            with self.subTest(part=part):
                self.assertIn(part, url)

    def test_without_salary_min_url_is_unchanged(self):
        s = JobsDBScraper()
        s.set_days(7)
        url = s._build_url("ai agent", None, None, 1)
        self.assertNotIn("salaryrange", url)
        self.assertNotIn("salarytype", url)


class TestSearchGraphqlPayload(unittest.TestCase):
    def _captured_query(self, scraper):
        seen = {}

        def fake_post(query, variables=None):
            seen["query"] = query
            return {"data": {"jobSearchV7": {"results": {"jobs": []}}}}

        with patch.dict(os.environ, {"JOBSDB_GRAPHQL": "1"}), \
                patch.object(scraper, "_post_graphql", side_effect=fake_post):
            scraper.search("ai agent", page=1)
        return seen["query"]

    def test_salary_min_reaches_graphql(self):
        s = JobsDBScraper()
        s.set_salary_min(17000)
        q = self._captured_query(s)
        self.assertIn('salaryMin: "17000m"', q)

    def test_without_salary_min_query_has_no_salary_filter(self):
        s = JobsDBScraper()
        q = self._captured_query(s)
        self.assertNotIn("salaryMin", q)

    def test_channel_failure_falls_back_with_salaryrange(self):
        s = JobsDBScraper()
        s.set_salary_min(17000)
        captured = {}

        def fake_browser(keyword, page, district, category, sort=None):
            captured["url"] = s._build_url(keyword, district, category, page, sort=sort)
            return []

        with patch.dict(os.environ, {"JOBSDB_GRAPHQL": "1"}), \
                patch.object(s, "_post_graphql", side_effect=RuntimeError("boom")), \
                patch.object(s, "_search_browser", side_effect=fake_browser):
            s.search("ai agent", page=1)

        self.assertTrue(s._gql_broken)
        self.assertIn("salaryrange=17000-", captured["url"])


class _SalaryStub(BaseScraper):
    """假站：用來驗證客戶端兜底與掛載點的跨站隔離。"""

    source = "dummy"
    list_has_date = True

    def __init__(self, pages, *, with_hook=False, hook_raises=False):
        super().__init__()
        self.pages = pages
        self.visited = []
        self.hook_values = []
        self._hook_raises = hook_raises
        if with_hook:
            # 實例屬性遮蔽方法，模擬「有實作 set_salary_min 的來源」。
            self.set_salary_min = self._hook

    def _hook(self, value):
        if self._hook_raises:
            raise RuntimeError("hook boom")
        self.hook_values.append(value)

    def search(self, keyword, page=1, district=None, category=None,
               industry=None, sort=None):
        self.visited.append(page)
        return self.pages.get(page, [])

    def get_detail(self, job_url):
        return None

    def _sleep(self, extra: float = 0.0) -> None:
        pass


class TestClientFallback(unittest.TestCase):
    def _pages(self):
        return {1: [
            make_job("high", "$20,000 per month", source="dummy"),
            make_job("low", "$15,000 per month", source="dummy"),
            make_job("hourly_low", "$45 per hour", source="dummy"),
            make_job("hourly_high", "$120 per hour", source="dummy"),
            make_job("unknown", "Negotiable", source="dummy"),
            make_job("range_low", "$15,000 – $20,000 per month", source="dummy"),
        ]}

    def test_keeps_ranges_that_can_reach_the_floor(self):
        s = _SalaryStub(self._pages())
        jobs = s.scrape_all("x", max_pages=1, salary_min=17000)
        # 判定用「區間上限」與站方 salaryMin 對齊：
        # 20,000 單點保留；時薪 120 × 176 = 21,120 保留；
        # 15,000 單點（上限 15,000）排除；時薪 45 → 7,920 排除；
        # $15,000–$20,000 的上限 20,000 達標 → 保留（站方 202 筆實測有此類）；
        # Negotiable 無法判斷 → 排除。
        self.assertEqual([j.job_id for j in jobs],
                         ["high", "hourly_high", "range_low"])

    def test_none_keeps_everything(self):
        s = _SalaryStub(self._pages())
        jobs = s.scrape_all("x", max_pages=1)
        self.assertEqual(len(jobs), 6)

    def test_hook_is_called_when_present(self):
        s = _SalaryStub(self._pages(), with_hook=True)
        s.scrape_all("x", max_pages=1, salary_min=17000)
        self.assertEqual(s.hook_values, [17000])

    def test_no_hook_is_not_an_error(self):
        s = _SalaryStub(self._pages())
        jobs = s.scrape_all("x", max_pages=1, salary_min=17000)
        self.assertTrue(jobs)

    def test_hook_failure_does_not_abort_scrape(self):
        s = _SalaryStub(self._pages(), with_hook=True, hook_raises=True)
        with self.assertLogs("base_scraper", level="WARNING"):
            jobs = s.scrape_all("x", max_pages=1, salary_min=17000)
        self.assertEqual([j.job_id for j in jobs],
                         ["high", "hourly_high", "range_low"])

    def test_empty_page_after_salary_filter_keeps_paging(self):
        pages = {
            1: [make_job("low", "$10,000 per month", source="dummy")],
            2: [make_job("high", "$30,000 per month", source="dummy")],
        }
        s = _SalaryStub(pages)
        jobs = s.scrape_all("x", max_pages=2, salary_min=17000)
        self.assertEqual(s.visited, [1, 2])
        self.assertEqual([j.job_id for j in jobs], ["high"])

    def test_success_counts_only_kept(self):
        s = _SalaryStub(self._pages())
        s.scrape_all("x", max_pages=1, salary_min=17000)
        self.assertEqual(s.report()["success"], 3)


def run_cli(argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(argv)
    return code, out.getvalue()


def _fake_info(name="fake", enabled=True):
    return SourceInfo(
        name=name, label="Fake", enabled=enabled, needs_browser=False,
        needs_chrome=False, per_page=1, keyword_required=False,
        days_mode="list", sort_values=(), supports={}, request_delay=0.0, notes="",
    )


class _RecordingScraper:
    calls = []

    def __init__(self):
        pass

    def scrape_all(self, **kwargs):
        type(self).calls.append(kwargs)
        return [JobRecord(
            job_id="fake::1", source="fake", title="工程師",
            company="Example Ltd", salary="20000", posted_date="2026-11-10",
        )]

    def close(self):
        pass


class TestCliWiring(unittest.TestCase):
    def setUp(self):
        _RecordingScraper.calls = []

    def test_parser_accepts_positive_integer(self):
        p = build_search_argparser(description="x")
        self.assertEqual(p.parse_args(["--salary-min", "17000"]).salary_min, 17000)

    def test_parser_default_is_none(self):
        p = build_search_argparser(description="x")
        self.assertIsNone(p.parse_args([]).salary_min)

    def test_parser_rejects_zero_negative_and_text(self):
        p = build_search_argparser(description="x")
        for bad in ("0", "-5", "abc"):
            with self.subTest(bad=bad), self.assertRaises(SystemExit) as cm:
                p.parse_args(["--salary-min", bad])
            self.assertEqual(cm.exception.code, 2)

    def test_query_echoes_salary_min_without_bumping_schema(self):
        with patch.multiple(cli, SOURCES={"fake": _fake_info()},
                            SCRAPERS={"fake": _RecordingScraper}):
            code, out = run_cli(
                ["search", "--source", "fake", "--salary-min", "17000", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["query"]["salaryMin"], 17000)
        self.assertEqual(payload["schemaVersion"], 2)
        self.assertEqual(set(payload["jobs"][0]),
                         set(JobRecord.FIELDS) | set(cli.aggregate.V2_EXTRA_FIELDS))

    def test_salary_min_reaches_scraper(self):
        with patch.multiple(cli, SOURCES={"fake": _fake_info()},
                            SCRAPERS={"fake": _RecordingScraper}):
            run_cli(["search", "--source", "fake", "--salary-min", "17000", "--json"])
        self.assertEqual(_RecordingScraper.calls[-1]["salary_min"], 17000)

    def test_human_mode_prints_salary_floor_note(self):
        with patch.multiple(cli, SOURCES={"fake": _fake_info()},
                            SCRAPERS={"fake": _RecordingScraper}):
            code, out = run_cli(
                ["search", "--source", "fake", "--salary-min", "17000", "--no-list"])
        self.assertEqual(code, 0)
        self.assertIn("薪金下限", out)
        self.assertIn("17,000", out)


class TestScrapeAllEndToEnd(unittest.TestCase):
    """一條鏈：scrape_all(salary_min) → set_salary_min → GraphQL → 解析 → 兜底。"""

    @staticmethod
    def _page(job_id, salary):
        return {"data": {"jobSearchV7": {"results": {"jobs": [{
            "id": job_id,
            "title": f"Job {job_id}",
            "salary": salary,
            "listedAt": {"dateTimeUtc": "2026-11-14T00:00:00.000Z"},
        }]}}}}

    def test_three_pages_are_pushed_and_filtered(self):
        s = JobsDBScraper()
        pages = {
            1: self._page("1", {"min": 20000, "max": 25000, "period": "monthly"}),
            2: self._page("2", {"min": 10000, "max": 12000, "period": "monthly"}),
            3: self._page("3", {"min": 15000, "max": 18000, "period": "monthly"}),
        }
        queries = []

        def fake_post(query, variables=None):
            page = int(re.search(r"page: (\d+)", query).group(1))
            queries.append(query)
            return pages[page]

        with patch.dict(os.environ, {"JOBSDB_GRAPHQL": "1"}), \
                patch.object(s, "_post_graphql", side_effect=fake_post), \
                patch.object(s, "_sleep", return_value=None):
            jobs = s.scrape_all("ai agent", max_pages=3, days=7, salary_min=17000)

        self.assertEqual(len(queries), 3)
        for q in queries:
            self.assertIn('salaryMin: "17000m"', q)
            self.assertIn('listedAt: "7d"', q)
        # 第 2 頁上限 12,000 < 17,000 → 排除；第 3 頁上限 18,000 → 保留。
        self.assertEqual([j.job_id for j in jobs], ["jobsdb_1", "jobsdb_3"])
        self.assertEqual(s._stats["success"], 2)
        self.assertEqual(set(jobs[0].to_dict()), set(JobRecord.FIELDS))


class TestLegacyEntry(unittest.TestCase):
    def test_legacy_parser_also_accepts_salary_min(self):
        import main

        p = main.build_argparser()
        self.assertEqual(p.parse_args(["--salary-min", "17000"]).salary_min, 17000)


if __name__ == "__main__":
    unittest.main()
