# -*- coding: utf-8 -*-
"""跨站契約測試（零請求）。

鎖定 2026-10-29 修復的四件事，避免回退成「不報錯但結果錯」：
  1. Recruit 的 --sort 每個 CLI 選項都必須對應到站方選項（先前 asc 靜默塌陷）
  2. --source all 不得執行已停用來源
  3. list_sorted_desc=False 的站，--days 不可因某頁全數過期就提早停翻
  4. 匯出必須是原子寫入（不留半檔、不留 .tmp）
"""
from __future__ import annotations

import os
import tempfile
import unittest

import exporter
from base_scraper import BaseScraper
from job_model import JobRecord
from scrapers import SCRAPERS
from scrapers.jobsdb import strip_new_badge
from scrapers.recruit import resolve_sort

CLI_SORTS = (
    "post_dt_desc", "post_dt_asc",
    "salary_desc", "salary_asc",
    "yr_exp_asc", "yr_exp_desc",
    "edu_lvl_asc", "edu_lvl_desc",
)


class TestRecruitSortContract(unittest.TestCase):
    def test_every_cli_option_maps_to_a_site_value(self):
        for opt in CLI_SORTS:
            with self.subTest(sort=opt):
                self.assertTrue(resolve_sort(opt), f"{opt} 未對應到站方選項")

    def test_desc_and_asc_differ_only_by_a_warning(self):
        for asc, desc in (("post_dt_asc", "post_dt_desc"), ("salary_asc", "salary_desc")):
            with self.subTest(sort=asc):
                with self.assertLogs("scrapers.recruit", level="WARNING") as cm:
                    asc_val = resolve_sort(asc)
                self.assertEqual(asc_val, resolve_sort(desc))
                self.assertTrue(any("無對應方向" in m for m in cm.output))

    def test_unknown_sort_is_rejected_loudly(self):
        with self.assertLogs("scrapers.recruit", level="WARNING"):
            self.assertEqual(resolve_sort("relevance"), "")


class TestJobsDBTitleBadge(unittest.TestCase):
    """JobsDB 把「New」徽章直接拼進標題文字（2026-10-31 實測：無子元素、無偽元素）。"""

    def test_strips_badge_glued_to_title(self):
        self.assertEqual(
            strip_new_badge("Infrastructure ArchitectNew"),
            "Infrastructure Architect",
        )
        self.assertEqual(
            strip_new_badge("Senior Full Stack Software EngineerNew"),
            "Senior Full Stack Software Engineer",
        )

    def test_keeps_legitimate_word_new(self):
        for title in ("Brand New", "New", "New Media Designer", ""):
            with self.subTest(title=title):
                self.assertEqual(strip_new_badge(title), title)


class TestSourceRegistry(unittest.TestCase):
    def test_known_dead_sources_are_disabled(self):
        for name in ("indeed", "liepin", "zhipin"):
            with self.subTest(source=name):
                self.assertFalse(SCRAPERS[name].enabled)

    def test_pipeline_sources_are_enabled(self):
        for name in ("moovup", "gov_hk", "jobsdb", "linkedin", "recruit",
                     "jobmarket", "foundit", "efc", "offertoday"):
            with self.subTest(source=name):
                self.assertTrue(SCRAPERS[name].enabled)


class _Paged(BaseScraper):
    """假站：第 1 頁全是過期職位、第 2 頁有新鮮職位。"""

    source = "dummy"
    list_has_date = True

    def __init__(self, sorted_desc: bool):
        super().__init__()
        self.list_sorted_desc = sorted_desc
        self.pages = {
            1: [JobRecord(job_id="dummy::1", source="dummy", title="old")],
            2: [JobRecord(job_id="dummy::2", source="dummy", title="new")],
        }
        self.visited: list[int] = []

    def search(self, keyword, page=1, district=None, category=None,
               industry=None, sort=None):
        self.visited.append(page)
        return self.pages.get(page, [])

    def get_detail(self, job_url):
        return None

    def days_since_posted(self, job):
        return 1 if job.title == "new" else 99

    def _sleep(self, extra: float = 0.0) -> None:
        pass


class TestDaysEarlyStop(unittest.TestCase):
    def test_unsorted_site_keeps_paging(self):
        s = _Paged(sorted_desc=False)
        jobs = s.scrape_all("x", max_pages=2, days=10)
        self.assertEqual(s.visited, [1, 2])
        self.assertEqual([j.job_id for j in jobs], ["dummy::2"])

    def test_sorted_desc_site_stops_early(self):
        s = _Paged(sorted_desc=True)
        jobs = s.scrape_all("x", max_pages=3, days=10)
        self.assertEqual(s.visited, [1])
        self.assertEqual(jobs, [])

    def test_success_counts_only_kept(self):
        s = _Paged(sorted_desc=False)
        s.scrape_all("x", max_pages=2, days=10)
        self.assertEqual(s.report()["success"], 1)


class TestAtomicExport(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        for f in os.listdir(self.dir):
            os.remove(os.path.join(self.dir, f))
        os.rmdir(self.dir)

    def test_no_tmp_left_behind(self):
        path = os.path.join(self.dir, "out.json")
        exporter.export_json(
            [JobRecord(job_id="a::1", source="a", title="t")], path, incremental=False)
        self.assertEqual(os.listdir(self.dir), ["out.json"])

    def test_existing_file_intact_when_write_fails(self):
        path = os.path.join(self.dir, "out.json")
        exporter.export_json(
            [JobRecord(job_id="a::1", source="a", title="keep")], path, incremental=False)
        with open(path, encoding="utf-8") as f:
            before = f.read()

        class Boom(Exception):
            pass

        def bad_writer(f):
            f.write("[")
            raise Boom()

        with self.assertRaises(Boom):
            exporter._atomic_write(path, bad_writer, encoding="utf-8")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(os.listdir(self.dir), ["out.json"])


if __name__ == "__main__":
    unittest.main()
