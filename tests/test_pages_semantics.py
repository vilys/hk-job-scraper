"""`--pages` 的語意護欄：頁數不是筆數。

2026-11-15 定案：
- `--pages N` = 最多翻 N 頁；一頁幾筆由站方決定（10–58 不等），
  同一個 N 在 `--source all` 下各站產出不同屬預期。
- JobsDB 的 `pageSize=30`（GraphQL 與 SSR 一致）是這份契約的一部分，
  不得為了減少請求數改成 100 而讓 `--pages` 的產出量靜默放大三倍。

本檔全離線：不發任何請求，也不啟動瀏覽器。
"""

import argparse
import contextlib
import io
import unittest

from base_scraper import BaseScraper
from hkjobs.capabilities import SOURCES, page_budget_text
from hkjobs.cli import build_parser, cmd_search
from job_model import JobRecord
from scrapers.jobsdb import _GRAPHQL_PAGE_SIZE, build_graphql_query


def _job(job_id: str) -> JobRecord:
    return JobRecord(
        job_id=job_id, source="dummy", title=job_id, company="c",
        location="l", salary="", job_type="", industry="", description="",
        requirements="", url="", posted_date="2026-11-15", scraped_at="",
    )


class _CountingPages(BaseScraper):
    """假站：記錄 search() 被呼叫的頁碼，用來驗證「N 頁」的真正含義。"""

    source = "dummy"
    list_has_date = True

    def __init__(self, pages: dict[int, list[JobRecord]]):
        super().__init__()
        self.pages = pages
        self.calls: list[int] = []

    def search(self, keyword, page=1, district=None, category=None,
               industry=None, sort=None):
        self.calls.append(page)
        return self.pages.get(page, [])

    def get_detail(self, job_url):
        return None


class TestPagesMeansPages(unittest.TestCase):
    def test_at_most_n_search_calls(self):
        pages = {1: [_job("a")], 2: [_job("b")], 3: [_job("c")], 4: [_job("d")]}
        s = _CountingPages(pages)
        jobs = s.scrape_all("x", max_pages=3)
        self.assertEqual(s.calls, [1, 2, 3])
        self.assertEqual([j.job_id for j in jobs], ["a", "b", "c"])

    def test_empty_page_stops_earlier(self):
        s = _CountingPages({1: [_job("a")], 2: []})
        jobs = s.scrape_all("x", max_pages=5)
        self.assertEqual(s.calls, [1, 2])
        self.assertEqual([j.job_id for j in jobs], ["a"])

    def test_pages_zero_is_usage_error(self):
        args = build_parser().parse_args(
            ["search", "--source", "jobsdb", "--pages", "0"]
        )
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            code = cmd_search(args)
        self.assertEqual(code, 2)   # 用法錯誤，且在任何請求之前就返回

    def test_help_says_pages_not_results(self):
        parser = build_parser()
        sub = next(a for a in parser._actions
                   if isinstance(a, argparse._SubParsersAction))
        search = sub.choices["search"]
        action = next(a for a in search._actions
                      if "--pages" in a.option_strings)
        help_text = action.help or ""
        self.assertIn("頁數，不是筆數", help_text)
        self.assertIn("--limit", help_text)


class TestPageBudgetText(unittest.TestCase):
    def test_uses_source_page_size(self):
        text = page_budget_text("jobsdb", 3)
        self.assertIn("3 頁", text)
        self.assertIn("30 筆", text)
        self.assertIn("90 筆", text)
        self.assertIn("頁數，不是筆數", text)

    def test_same_pages_different_sources_differ(self):
        self.assertNotEqual(page_budget_text("moovup", 3),
                            page_budget_text("jobsdb", 3))

    def test_linkedin_first_and_following_pages_are_distinct(self):
        # 首頁 58、續頁 10：3 頁上限是 78，不是 3×58=174（高估兩倍會騙人）。
        text = page_budget_text("linkedin", 3)
        self.assertIn("首頁約 58 筆、續頁約 10 筆", text)
        self.assertIn("78 筆", text)
        self.assertIn("58 筆", page_budget_text("linkedin", 1))

    def test_disabled_source_without_page_size_returns_empty(self):
        self.assertEqual(page_budget_text("zhipin", 3), "")
        self.assertEqual(page_budget_text("no-such-source", 3), "")
        self.assertEqual(page_budget_text("jobsdb", 0), "")

    def test_every_enabled_source_has_a_page_size(self):
        for name, info in SOURCES.items():
            if info.enabled:
                with self.subTest(source=name):
                    self.assertGreater(info.per_page, 0)


class TestJobsDBPageSizeIsContract(unittest.TestCase):
    def test_default_transport_page_size_is_30(self):
        q = build_graphql_query(keyword="ai agent", visitor_id="v", session_id="s")
        self.assertIn("pageSize: 30", q)

    def test_capability_per_page_matches_transport(self):
        # 兩者若脫鉤，人類輸出的「上限 N 筆」就會騙人。
        self.assertEqual(_GRAPHQL_PAGE_SIZE, 30)
        self.assertEqual(SOURCES["jobsdb"].per_page, _GRAPHQL_PAGE_SIZE)

    def test_cap_100_is_preserved_but_not_default(self):
        # 站方上限仍是 100（未來若要省請求可以用），但預設必須維持 30。
        q = build_graphql_query(keyword="x", page_size=500,
                                visitor_id="v", session_id="s")
        self.assertIn("pageSize: 100", q)
        q_default = build_graphql_query(keyword="x", visitor_id="v", session_id="s")
        self.assertIn(f"pageSize: {_GRAPHQL_PAGE_SIZE}", q_default)


if __name__ == "__main__":
    unittest.main()
