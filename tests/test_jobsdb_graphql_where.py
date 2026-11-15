# -*- coding: utf-8 -*-
"""JobsDB 地區下推（GraphQL `where`）測試（零請求、離線）。

背景：2026-11-15 實測 `searchIntent.where: ["Tuen Mun"]` 與
`["Tuen Mun District"]` 回傳完全相同（60 筆、全部屯門），故不需要額外英文對照表；
地名由 `jobsdb_districts.json` 的 slug 推導。字典外地區一律退回瀏覽網址。

守住四件事：query 形狀、地名推導、路由（字典內才下推）、失敗仍能退回 SSR。
"""
from __future__ import annotations

import os
import re
import unittest
from unittest.mock import patch

import requests

from job_model import JobRecord
from scrapers.jobsdb import (
    JobsDBScraper,
    build_graphql_query,
    district_display_name,
)

VISITOR = "11111111-1111-1111-1111-111111111111"
SESSION = "22222222-2222-2222-2222-222222222222"


def _job(gid="95858112", location="Tuen Mun, Tuen Mun District"):
    return {
        "id": gid,
        "title": "Customer Service Officer",
        "abstract": "Handle enquiries.",
        "advertiser": {"id": "1", "name": "Example Ltd"},
        "location": {"id": "9", "displayName": {"text": location}},
        "cjs": {"workTypes": [{"sourceId": "242", "name": "Full time"}],
                "salary": {"hideSalary": False, "period": "Monthly"}},
        "listedAt": {"dateTimeUtc": "2026-11-12T08:15:07.000Z"},
        "salary": {"min": 18000, "max": 22000, "period": "monthly", "currency": "HKD"},
    }


def _response(*jobs):
    return {"data": {"jobSearchV7": {
        "results": {"jobs": list(jobs)},
        "metadata": {"sol": {"totalJobCount": len(jobs)}},
    }}}


def _search_intent(query: str) -> str:
    return [ln.strip() for ln in query.splitlines() if "searchIntent" in ln][0]


class TestBuildQueryWhere(unittest.TestCase):
    def test_where_string_is_rendered(self):
        q = build_graphql_query(keyword="customer services", listed_at="14d",
                                salary_min=17000, where="Tuen Mun",
                                visitor_id=VISITOR, session_id=SESSION)
        line = _search_intent(q)
        self.assertIn('text: "customer services", where: ["Tuen Mun"]', line)
        self.assertIn('filter: {listedAt: "14d", salaryMin: "17000m"}', line)
        self.assertEqual(q.count("{"), q.count("}"))
        self.assertEqual(re.findall(r"__[A-Z_]+?__", q), [])

    def test_where_accepts_list(self):
        q = build_graphql_query(keyword="clerk", where=["Sha Tin", "Tai Po"],
                                visitor_id=VISITOR, session_id=SESSION)
        self.assertIn('where: ["Sha Tin", "Tai Po"]', q)

    def test_where_empty_list_adds_nothing(self):
        q = build_graphql_query(keyword="clerk", where=[],
                                visitor_id=VISITOR, session_id=SESSION)
        self.assertNotIn("where:", q)
        self.assertIn('text: "clerk"}', _search_intent(q))

    def test_no_where_by_default(self):
        q = build_graphql_query(keyword="ai agent", visitor_id=VISITOR,
                                session_id=SESSION)
        self.assertNotIn("where", q)
        self.assertIn("distanceKms: 2, locale:", q)

    def test_where_is_escaped(self):
        q = build_graphql_query(keyword="x", where='A "B" \\ C',
                                visitor_id=VISITOR, session_id=SESSION)
        self.assertIn('\\"B\\"', q)
        self.assertIn("\\\\", q)

    def test_placeholders_adjacent_are_split(self):
        """__TEXT__ 與 __WHERE__ 相鄰時必須各自替換（非貪婪匹配）。"""
        q = build_graphql_query(keyword="k", where="Tuen Mun",
                                visitor_id=VISITOR, session_id=SESSION)
        self.assertNotIn("__TEXT__", q)
        self.assertNotIn("__WHERE__", q)


class TestDistrictName(unittest.TestCase):
    def test_slug_to_display_name(self):
        for slug, expected in (("tuen-mun", "Tuen Mun"),
                               ("tseung-kwan-o", "Tseung Kwan O"),
                               ("causeway-bay", "Causeway Bay"),
                               ("central", "Central")):
            with self.subTest(slug=slug):
                self.assertEqual(district_display_name(slug), expected)

    def test_empty_slug(self):
        self.assertEqual(district_display_name(""), "")


class TestGraphQLWhereResolution(unittest.TestCase):
    def setUp(self):
        self.s = JobsDBScraper()

    def test_chinese_name(self):
        self.assertEqual(self.s.graphql_where("屯門"), "Tuen Mun")
        self.assertEqual(self.s.graphql_where("沙田"), "Sha Tin")

    def test_slug_and_english(self):
        self.assertEqual(self.s.graphql_where("tuen-mun"), "Tuen Mun")
        self.assertEqual(self.s.graphql_where("Kwun Tong"), "Kwun Tong")

    def test_multiple_values_takes_first(self):
        with self.assertLogs("scrapers.jobsdb", level="WARNING"):
            self.assertEqual(self.s.graphql_where("屯門, 沙田"), "Tuen Mun")

    def test_unknown_and_empty_return_none(self):
        self.assertIsNone(self.s.graphql_where("火星"))
        self.assertIsNone(self.s.graphql_where("Not A Real Place"))
        self.assertIsNone(self.s.graphql_where(""))
        self.assertIsNone(self.s.graphql_where(None))

    def test_pure_function_no_network(self):
        with patch("requests.post") as post:
            self.s.graphql_where("屯門")
        post.assert_not_called()


class _Router(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"JOBSDB_GRAPHQL": "1"})
        env.start()
        self.addCleanup(env.stop)
        s = JobsDBScraper()
        post_patcher = patch.object(s, "_post_graphql", return_value=_response(_job()))
        browser_patcher = patch.object(s, "_search_browser", return_value=["SSR"])
        post_patcher.start()
        browser_patcher.start()
        self.addCleanup(post_patcher.stop)
        self.addCleanup(browser_patcher.stop)
        self.post = s._post_graphql
        self.browser = s._search_browser
        self.s = s


class TestRouting(_Router):
    def test_known_district_uses_graphql_without_browser(self):
        with patch.object(self.s, "_ensure_browser") as ensure:
            jobs = self.s.search("customer services", district="屯門")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(set(jobs[0].to_dict()), set(JobRecord.FIELDS))
        self.post.assert_called_once()
        self.browser.assert_not_called()
        ensure.assert_not_called()
        self.assertIn('where: ["Tuen Mun"]', self.post.call_args.args[0])
        self.assertFalse(self.s._gql_broken)

    def test_district_combines_with_days_and_salary(self):
        self.s.set_days(14)
        self.s.set_salary_min(17000)
        self.s.search("customer services", district="屯門")
        q = self.post.call_args.args[0]
        self.assertIn('listedAt: "14d"', q)
        self.assertIn('salaryMin: "17000m"', q)
        self.assertIn('where: ["Tuen Mun"]', q)

    def test_district_with_category_still_uses_browser(self):
        self.assertEqual(self.s.search("x", district="屯門", category="資訊及通訊科技"),
                         ["SSR"])
        self.post.assert_not_called()
        self.browser.assert_called_once()

    def test_unknown_district_uses_browser(self):
        self.assertEqual(self.s.search("x", district="火星"), ["SSR"])
        self.post.assert_not_called()
        self.browser.assert_called_once()

    def test_graphql_failure_with_district_falls_back(self):
        self.post.side_effect = requests.Timeout("timeout")
        with self.assertLogs("scrapers.jobsdb", level="WARNING"):
            self.assertEqual(self.s.search("x", district="屯門"), ["SSR"])
        self.assertTrue(self.s._gql_broken)
        self.browser.assert_called_once()

    def test_env_switch_off_ignores_where(self):
        with patch.dict(os.environ, {"JOBSDB_GRAPHQL": "0"}):
            self.assertEqual(self.s.search("x", district="屯門"), ["SSR"])
        self.post.assert_not_called()
        self.browser.assert_called_once()

    def test_broken_channel_does_not_retry_graphql_for_next_page(self):
        self.post.side_effect = requests.Timeout("timeout")
        with self.assertLogs("scrapers.jobsdb", level="WARNING"):
            self.s.search("x", district="屯門", page=1)
            self.s.search("x", district="屯門", page=2)
        self.assertEqual(self.post.call_count, 1)
        self.assertEqual(self.browser.call_count, 2)


class TestSsrUrlUnaffected(unittest.TestCase):
    def test_browser_url_still_carries_district_slug(self):
        """退回瀏覽器時網址仍用 in-<slug>，不因新增 where 而改變。"""
        s = JobsDBScraper()
        url = s._build_url("customer services", "屯門", None, 1)
        self.assertIn("/jobs/in-tuen-mun", url)
        self.assertNotIn("where=", url)


if __name__ == "__main__":
    unittest.main()
