# -*- coding: utf-8 -*-
"""JobsDB GraphQL 搜尋通道測試（零請求、離線）。

所有對外請求都以 mock 擋下：不連網、不啟動瀏覽器、不讀外部快照。
守住四件事：query 形狀安全、回應驗證嚴格、路由只走已驗證維度、
通道失敗一定熔斷並退回既有 Playwright SSR 流程。
"""
from __future__ import annotations

import json
import os
import re
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import requests

from hkjobs.aggregate import parse_date, parse_salary
from job_model import JobRecord
from scrapers.jobsdb import (
    JobsDBGraphQLError,
    JobsDBScraper,
    _GRAPHQL_LISTED_AT,
    _GRAPHQL_PAGE_SIZE,
    build_graphql_query,
    parse_graphql_response,
)

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
VISITOR = "11111111-1111-1111-1111-111111111111"
SESSION = "22222222-2222-2222-2222-222222222222"


def gql_job(**overrides):
    """欄位形狀的精簡重構（不含任何真實快照或外部路徑）。"""
    job = {
        "id": "95858112",
        "title": "AI Agent Engineer",
        "abstract": "Build agents.",
        "advertiser": {"id": "60285505", "name": "Example Bank Limited"},
        "location": {"id": "1000160", "displayName": {"text": "Mong Kok"}},
        "cjs": {
            "workTypes": [{"sourceId": "242", "name": "Full time"}],
            "salary": {"hideSalary": True, "period": "Monthly"},
            "roleTitles": [{"shortId": "agent"}],
        },
        "listedAt": {"dateTimeUtc": "2026-11-12T08:15:07.000Z"},
        "salary": {"min": 40000, "max": 50000, "period": "monthly", "currency": "HKD"},
        "categories": [
            {"id": "6287", "label": "Developers/Programmers"},
            {"id": "6281", "label": "Information & Communication Technology"},
        ],
    }
    job.update(overrides)
    return job


def gql_response(*jobs):
    return {
        "data": {
            "jobSearchV7": {
                "results": {"jobs": list(jobs)},
                "metadata": {"sol": {"totalJobCount": len(jobs)}},
            }
        }
    }


def fake_http(status=200, text="", payload=None):
    """給 _post_graphql 用的假 requests.Response。

    json() 真的去 parse body，才會像 requests.Response 一樣在無效 JSON 上拋
    ValueError（JSONDecodeError 是 ValueError 子類）。
    """
    body = text if text else json.dumps(payload if payload is not None else {})
    return SimpleNamespace(
        status_code=status,
        text=body,
        json=lambda: json.loads(body),
    )


class _EnvMixin(unittest.TestCase):
    """保證每個路由測試都從「GraphQL 開啟」的乾淨環境起跑。"""

    def setUp(self):
        env = patch.dict(os.environ, {"JOBSDB_GRAPHQL": "1"})
        env.start()
        self.addCleanup(env.stop)


class TestBuildQuery(unittest.TestCase):
    def test_shape_and_no_credentials(self):
        q = build_graphql_query(keyword="AI Agent", page=2, listed_at="7d",
                                visitor_id=VISITOR, session_id=SESSION)
        self.assertIn("jobSearchV7(params:", q)
        self.assertIn("page: 2, pageSize: 30", q)
        self.assertIn('text: "AI Agent"', q)
        self.assertIn('sort: "score"', q)
        self.assertIn('listedAt: "7d"', q)
        self.assertIn("metadata { sol }", q)
        self.assertEqual(q.count("{"), q.count("}"))
        self.assertEqual(re.findall(r"__[A-Z_]+__", q), [])
        # 憑證欄位不能出現在 query（sessionId 是匿名 UUID，不是 cookie）
        for banned in ("Cookie:", "Authorization:", "Bearer ", "li_at", "LI_AT"):
            self.assertNotIn(banned, q)

    def test_keyword_is_raw_literal_and_escaped(self):
        q = build_graphql_query(keyword='文員 " clerk\\test', visitor_id=VISITOR,
                                session_id=SESSION)
        self.assertIn("文員", q)
        self.assertNotIn("%", q)              # 不做 URL percent-encode
        self.assertIn('\\"', q)               # 引號已跳脫
        self.assertIn("\\\\", q)              # 反斜線已跳脫
        self.assertEqual(re.findall(r"__[A-Z_]+__", q), [])

    def test_placeholder_in_keyword_is_not_expanded_twice(self):
        q = build_graphql_query(keyword="__PAGE__ __TEXT__", visitor_id=VISITOR,
                                session_id=SESSION)
        self.assertIn('text: "__PAGE__ __TEXT__"', q)
        self.assertIn("page: 1,", q)

    def test_filter_only_when_listed_at_present(self):
        with_flt = build_graphql_query(keyword="data", listed_at="3d")
        without = build_graphql_query(keyword="data")
        self.assertIn('filter: {listedAt: "3d"},', with_flt)
        self.assertNotIn("filter:", without)
        self.assertIn("distanceKms: 2, locale:", without)

    def test_page_and_size_are_clamped(self):
        q = build_graphql_query(keyword="data", page=-5, page_size=999)
        self.assertIn("page: 1, pageSize: 100", q)
        with self.assertRaises(JobsDBGraphQLError):
            build_graphql_query(keyword="data", page="not-a-number")

    def test_page_size_default_matches_ssr(self):
        self.assertEqual(_GRAPHQL_PAGE_SIZE, 30)

    def test_listed_at_mapping(self):
        self.assertEqual(_GRAPHQL_LISTED_AT,
                         {"1": "1d", "3": "3d", "7": "7d", "14": "14d", "31": "30d"})


class TestParseResponse(unittest.TestCase):
    def test_success_is_13_fields_and_downstream_parsable(self):
        recs = parse_graphql_response(gql_response(gql_job()), now=NOW)
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(set(r.to_dict()), set(JobRecord.FIELDS))
        self.assertEqual(len(r.to_dict()), 13)
        self.assertEqual(r.job_id, "jobsdb_95858112")
        self.assertEqual(parse_salary(r.salary)[:3], (40000, 50000, "month"))
        self.assertEqual(parse_date(r.posted_date, r.scraped_at), "2026-11-12")
        scraper = JobsDBScraper.__new__(JobsDBScraper)
        self.assertEqual(scraper.days_since_posted(r), 2)

    def test_hide_salary_flag_stays_in_raw_only(self):
        r = parse_graphql_response(gql_response(gql_job()), now=NOW)[0]
        self.assertTrue(r.raw["graphql"]["hide_salary"])
        self.assertNotIn("hide_salary", r.to_dict())
        self.assertEqual(len(r.to_dict()), 13)

    def test_hidden_salary_value_still_fills_main_salary_field(self):
        """合規事實固化：旗標只在 raw，薪資數值仍進 13 欄主表並會被輸出。

        這條防止文件再次寫成「只放 raw／不張揚雇主未顯示的值」——
        那句話對旗標成立，對薪資數值不成立。
        """
        r = parse_graphql_response(gql_response(gql_job()), now=NOW)[0]
        self.assertTrue(r.raw["graphql"]["hide_salary"])
        self.assertNotIn("hide_salary", r.to_dict())
        self.assertTrue(r.salary, "hideSalary=true 不應清空主表 salary")
        self.assertEqual(parse_salary(r.salary)[:3], (40000, 50000, "month"))

    def test_errors_are_rejected(self):
        with self.assertRaises(JobsDBGraphQLError) as cm:
            parse_graphql_response({"errors": [{"message": "Field X is not defined"}]})
        self.assertIn("schema", str(cm.exception))

    def test_missing_or_malformed_jobs_are_rejected(self):
        for payload in ({}, {"data": {}}, {"data": {"jobSearchV7": {"results": {}}}},
                        {"data": {"jobSearchV7": {"results": {"jobs": "oops"}}}}, []):
            with self.subTest(payload=payload), self.assertRaises(JobsDBGraphQLError):
                parse_graphql_response(payload)

    def test_empty_jobs_is_legal_not_an_error(self):
        self.assertEqual(parse_graphql_response(gql_response()), [])

    def test_bad_single_job_does_not_break_batch(self):
        recs = parse_graphql_response(
            gql_response(gql_job(), None, {"id": "1", "salary": "bad"}), now=NOW)
        self.assertEqual(len(recs), 3)
        self.assertTrue(all(set(r.to_dict()) == set(JobRecord.FIELDS) for r in recs))


class TestPostGraphQL(unittest.TestCase):
    """_post_graphql 本身：零憑證 headers、挑戰頁與非 JSON 都要擋。"""

    def _post(self, fake):
        s = JobsDBScraper()
        with patch("scrapers.jobsdb.requests.post", return_value=fake) as post:
            result = s._post_graphql("query { jobSearchV7 }")
        return result, post

    def test_headers_carry_no_credentials(self):
        _, post = self._post(fake_http(payload=gql_response()))
        kw = post.call_args.kwargs
        self.assertEqual(post.call_args.args[0], "https://hk.jobsdb.com/graphql")
        self.assertEqual(kw["json"], {"query": "query { jobSearchV7 }"})
        h = kw["headers"]
        self.assertEqual(h["Content-Type"], "application/json")
        self.assertEqual(h["Origin"], "https://hk.jobsdb.com")
        self.assertNotIn("Cookie", h)
        self.assertNotIn("Authorization", h)

    def test_non_200_is_rejected(self):
        with self.assertRaisesRegex(JobsDBGraphQLError, "HTTP 429"):
            self._post(fake_http(status=429, text="too many"))

    def test_cloudflare_html_is_rejected(self):
        for text in ("<!DOCTYPE html><title>Just a moment...</title>",
                     "<html><body>Just a moment</body></html>"):
            with self.subTest(text=text[:30]), self.assertRaises(JobsDBGraphQLError):
                self._post(fake_http(text=text))

    def test_invalid_json_is_rejected(self):
        with self.assertRaisesRegex(JobsDBGraphQLError, "不是有效 JSON"):
            self._post(fake_http(text="not json at all"))


class TestSearchRouting(_EnvMixin):
    """只在已驗證維度上走 GraphQL；其餘一律既有 Playwright SSR。"""

    def _scraper(self, data=None):
        s = JobsDBScraper()
        payload = data if data is not None else gql_response(gql_job())
        post = patch.object(s, "_post_graphql", return_value=payload)
        browser = patch.object(s, "_search_browser", return_value=["SSR"])
        post.start()
        browser.start()
        self.addCleanup(post.stop)
        self.addCleanup(browser.stop)
        return s, s._post_graphql, s._search_browser

    def test_default_uses_graphql_and_never_starts_browser(self):
        s, post, browser = self._scraper()
        with patch.object(s, "_ensure_browser") as ensure:
            jobs = s.search("ai agent")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(set(jobs[0].to_dict()), set(JobRecord.FIELDS))
        post.assert_called_once()
        browser.assert_not_called()
        ensure.assert_not_called()
        self.assertFalse(s._gql_broken)

    def test_env_switch_off_goes_straight_to_browser(self):
        s, post, browser = self._scraper()
        with patch.dict(os.environ, {"JOBSDB_GRAPHQL": "0"}):
            self.assertEqual(s.search("ai agent"), ["SSR"])
        post.assert_not_called()
        browser.assert_called_once()
        self.assertFalse(s._gql_broken)

    def test_category_sort_go_to_browser(self):
        for kwargs in ({"category": "資訊及通訊科技"}, {"sort": "post_dt_desc"}):
            with self.subTest(kwargs=kwargs):
                s, post, browser = self._scraper()
                self.assertEqual(s.search("ai agent", **kwargs), ["SSR"])
                post.assert_not_called()
                browser.assert_called_once()

    def test_unknown_district_goes_to_browser(self):
        """字典外地區不下推（不拿猜出來的地名去試站方）。"""
        s, post, browser = self._scraper()
        self.assertEqual(s.search("ai agent", district="火星"), ["SSR"])
        post.assert_not_called()
        browser.assert_called_once()

    def test_industry_warning_still_emitted_on_graphql_path(self):
        s, _, _ = self._scraper()
        with self.assertLogs("scrapers.jobsdb", level="WARNING") as logs:
            s.search("ai agent", industry="金融")
        self.assertIn("--industry 不適用 JobsDB", "\n".join(logs.output))

    def test_set_days_is_pushed_as_listed_at(self):
        for days, expected in ((7, '"7d"'), (30, '"30d"'), (10, '"14d"'),
                               (1, '"1d"'), (3, '"3d"'), (14, '"14d"')):
            with self.subTest(days=days):
                s, post, _ = self._scraper()
                s.set_days(days)
                s.search("ai agent")
                self.assertIn(f"listedAt: {expected}", post.call_args.args[0])

    def test_days_over_31_does_not_push_filter(self):
        s, post, _ = self._scraper()
        s.set_days(60)
        s.search("ai agent")
        self.assertNotIn("filter:", post.call_args.args[0])

    def test_each_page_gets_fresh_anonymous_uuids(self):
        s, post, _ = self._scraper()
        s.search("ai agent", page=1)
        first = post.call_args.args[0]
        s.search("ai agent", page=2)
        second = post.call_args.args[0]
        pat = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        ids1, ids2 = re.findall(pat, first), re.findall(pat, second)
        self.assertEqual(len(ids1), 2)
        self.assertEqual(len(ids2), 2)
        self.assertFalse(set(ids1) & set(ids2))
        self.assertNotIn(VISITOR, first + second)


class TestFallback(_EnvMixin):
    """通道失敗 → 熔斷本輪 → 退回 SSR，且不再重撞 GraphQL。"""

    def _scraper(self, *, side_effect=None, data=None):
        s = JobsDBScraper()
        kw = {"side_effect": side_effect} if side_effect is not None else {
            "return_value": data if data is not None else {}}
        post = patch.object(s, "_post_graphql", **kw)
        browser = patch.object(s, "_search_browser", return_value=["SSR"])
        post.start()
        browser.start()
        self.addCleanup(post.stop)
        self.addCleanup(browser.stop)
        return s, s._post_graphql, s._search_browser

    def test_errors_payload_falls_back_and_breaks(self):
        s, post, browser = self._scraper(
            data={"errors": [{"message": "schema changed"}]})
        with self.assertLogs("scrapers.jobsdb", level="WARNING"):
            self.assertEqual(s.search("ai agent"), ["SSR"])
        self.assertTrue(s._gql_broken)
        post.assert_called_once()
        browser.assert_called_once()

    def test_request_exception_falls_back(self):
        s, _, browser = self._scraper(side_effect=requests.Timeout("timeout"))
        with self.assertLogs("scrapers.jobsdb", level="WARNING"):
            self.assertEqual(s.search("ai agent"), ["SSR"])
        self.assertTrue(s._gql_broken)
        browser.assert_called_once()

    def test_cloudflare_error_falls_back(self):
        s, _, _ = self._scraper(
            side_effect=JobsDBGraphQLError("回應為 Cloudflare 挑戰頁（HTML）"))
        with self.assertLogs("scrapers.jobsdb", level="WARNING"):
            self.assertEqual(s.search("ai agent"), ["SSR"])
        self.assertTrue(s._gql_broken)

    def test_malformed_response_falls_back(self):
        s, _, browser = self._scraper(data={"data": {}})
        with self.assertLogs("scrapers.jobsdb", level="WARNING"):
            self.assertEqual(s.search("ai agent"), ["SSR"])
        browser.assert_called_once()
        self.assertTrue(s._gql_broken)

    def test_circuit_break_skips_graphql_on_next_page(self):
        s, post, browser = self._scraper(side_effect=requests.ConnectionError("offline"))
        with self.assertLogs("scrapers.jobsdb", level="WARNING"):
            self.assertEqual(s.search("ai agent", page=1), ["SSR"])
        self.assertEqual(s.search("ai agent", page=2), ["SSR"])
        post.assert_called_once()          # 第二頁完全沒再打 GraphQL
        self.assertEqual(browser.call_count, 2)

    def test_empty_jobs_does_not_fall_back(self):
        s = JobsDBScraper()
        with patch.object(s, "_post_graphql", return_value=gql_response()), \
             patch.object(s, "_search_browser", return_value=["SSR"]) as browser:
            self.assertEqual(s.search("ai agent"), [])
            browser.assert_not_called()
        self.assertFalse(s._gql_broken)


class TestUnchangedAndEndToEnd(_EnvMixin):
    def test_existing_url_builder_and_days_are_untouched(self):
        s = JobsDBScraper()
        url = s._build_url("data", "荃灣", "資訊及通訊科技", 2, sort="post_dt_desc")
        self.assertIn("/jobs-in-", url)
        self.assertIn("/in-", url)
        self.assertIn("keywords=data", url)
        self.assertIn("page=2", url)
        self.assertIn("sortmode=ListedDate", url)
        s.set_days(7)
        self.assertIn("daterange=7", s._build_url("data", None, None, 1))

    def test_scrape_all_end_to_end_offline(self):
        """用 30 筆內嵌資料跑一次 scrape_all，驗證分頁／日期／薪金全鏈路。"""
        fresh = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        jobs = [gql_job(id=str(900000 + i), listedAt={"dateTimeUtc": fresh})
                for i in range(30)]
        s = JobsDBScraper()
        with patch.object(s, "_post_graphql", return_value=gql_response(*jobs)) as post, \
             patch.object(s, "_search_browser",
                          side_effect=AssertionError("不應退回瀏覽器")), \
             patch.object(s, "_sleep"):
            out = s.scrape_all("ai agent", max_pages=1, days=7)
        self.assertEqual(len(out), 30)
        self.assertEqual(len({r.job_id for r in out}), 30)
        self.assertTrue(all(set(r.to_dict()) == set(JobRecord.FIELDS) for r in out))
        self.assertTrue(all(r.salary for r in out))
        self.assertTrue(all(s._within_days(r, 7) for r in out))
        post.assert_called_once()
        self.assertIn('listedAt: "7d"', post.call_args.args[0])

    def test_scrape_all_stays_clean_when_graphql_breaks(self):
        s = JobsDBScraper()
        with patch.object(s, "_post_graphql", side_effect=requests.Timeout("timeout")), \
             patch.object(s, "_search_browser", return_value=[]), \
             patch.object(s, "_sleep"), \
             self.assertLogs("scrapers.jobsdb", level="WARNING"):
            self.assertEqual(s.scrape_all("ai agent", max_pages=1), [])
        self.assertTrue(s._gql_broken)


if __name__ == "__main__":
    unittest.main()
