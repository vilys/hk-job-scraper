# -*- coding: utf-8 -*-
"""回歸：爬取失敗不得偽裝成「查無結果」；gov_hk 詳情須帶回標題。

對應 2026-10-31 實測發現的兩個 bug：
  1. 搜尋頁全數失敗時 scrape_all() 回傳空 list，CLI 判為 exit 5 / no_results。
  2. GovHkScraper.get_detail() 建構 JobRecord 時漏填 title，標題永遠是空字串。
"""
from __future__ import annotations

import argparse
import unittest
from unittest.mock import patch

from base_scraper import BaseScraper
from hkjobs import cli
from hkjobs.contract import EXIT_ALL_FAILED, SourceResult, exit_code_for
from job_model import JobRecord


class _BoomScraper(BaseScraper):
    """每一頁都失敗的假據點，用來重現 JobsDB 缺 Playwright 的情境。"""
    source = "boom"

    def search(self, *args, **kwargs):
        raise RuntimeError("此據點需要 Playwright")

    def get_detail(self, job_url):
        return None

    def close(self):
        pass


class _FlakyScraper(BaseScraper):
    """第 1 頁成功、第 2 頁失敗：已抓到的資料不能被丟掉。"""
    source = "flaky"

    def search(self, keyword, page=1, *args, **kwargs):
        if page == 1:
            return [JobRecord(job_id="flaky_1", source="flaky", title="存活的職位")]
        raise RuntimeError("第 2 頁壞了")

    def get_detail(self, job_url):
        return None

    def close(self):
        pass


def _args() -> argparse.Namespace:
    """_run_one 會讀到的全部欄位。"""
    return argparse.Namespace(
        keyword="", pages=1, district=None, category=None, industry=None,
        sort=None, days=None, detail=False, fill_location=False,
    )


class TestFailureContract(unittest.TestCase):
    def test_all_pages_failed_raises_instead_of_empty_list(self):
        s = _BoomScraper()
        with patch("base_scraper.time.sleep"), self.assertRaises(RuntimeError) as cm:
            s.scrape_all(keyword="", max_pages=1)
        self.assertIn("Playwright", str(cm.exception))
        self.assertIn("Playwright", s.last_error)

    def test_cli_marks_source_failed(self):
        with patch.dict(cli.SCRAPERS, {"boom": _BoomScraper}), \
             patch("base_scraper.time.sleep"):
            result = cli._run_one("boom", _args())
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.jobs, [])
        self.assertIn("Playwright", result.error)

    def test_failed_source_yields_exit_4_not_5(self):
        results = [SourceResult("boom", "failed", [], "Playwright")]
        self.assertEqual(exit_code_for(results), EXIT_ALL_FAILED)

    def test_partial_success_keeps_jobs(self):
        s = _FlakyScraper()
        with patch("base_scraper.time.sleep"):
            jobs = s.scrape_all(keyword="", max_pages=2)
        self.assertEqual([j.title for j in jobs], ["存活的職位"])
        self.assertIsNotNone(s.last_error)  # 失敗仍被記錄，只是不覆寫既有成果

    def test_successful_run_has_no_last_error(self):
        class _GoodScraper(_FlakyScraper):
            def search(self, keyword, page=1, *args, **kwargs):
                return [JobRecord(job_id=f"g_{page}", source="good", title="OK")]

        s = _GoodScraper()
        with patch("base_scraper.time.sleep"):
            s.scrape_all(keyword="", max_pages=1)
        self.assertIsNone(s.last_error)


class TestGovHkDetailTitle(unittest.TestCase):
    def _detail(self, html: str) -> JobRecord:
        from scrapers.gov_hk import GovHkScraper
        s = GovHkScraper()
        response = type("Response", (), {"text": html})()
        with patch.object(s.session, "get", return_value=response):
            return s.get_detail("https://example.invalid/job")

    def test_parses_title_from_jobTitle(self):
        html = (
            '<html><body>'
            '<span id="jobTitle">律師行文員</span>'
            '<span id="empName">江炳滔律師事務所</span>'
            '<span id="postedDt">06/11/2026</span>'
            '</body></html>'
        )
        job = self._detail(html)
        self.assertEqual(job.title, "律師行文員")
        self.assertEqual(job.company, "江炳滔律師事務所")
        self.assertEqual(job.posted_date, "06/11/2026")

    def test_missing_title_is_empty_not_crash(self):
        job = self._detail("<html><body><span id='empName'>X</span></body></html>")
        self.assertEqual(job.title, "")


if __name__ == "__main__":
    unittest.main()
