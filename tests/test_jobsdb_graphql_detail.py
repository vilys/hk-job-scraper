# -*- coding: utf-8 -*-
"""JobsDB jobDetails 詳情通道測試（零請求、離線）。

所有對外請求與瀏覽器都以 mock 擋下：不連網、不啟動 Playwright、不讀外部快照。
守住五件事：query 形狀（不碰申請問卷）、HTML 正文轉純文字、13 欄契約、
路由失敗一定熔斷並退回既有 Playwright 詳情流程、單一回應過大隻影響該筆。
"""
from __future__ import annotations

import json
import os
import re
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import requests

from hkjobs.aggregate import parse_date, parse_salary
from job_model import JobRecord
from scrapers.jobsdb import (
    JobsDBGraphQLError,
    JobsDBScraper,
    _is_payload_too_large,
    build_job_details_query,
    parse_job_details_response,
)

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
JOB_ID = "95858112"
JOB_URL = f"https://hk.jobsdb.com/job/{JOB_ID}"
HTML_CONTENT = (
    "<p><strong>Key Responsibilities</strong></p>"
    "<ul><li><p>Lead the design of AI-driven features.</p></li>"
    "<li><p>Build &amp; optimise RAG pipelines.</p></li></ul>"
)


def detail_job(**overrides):
    """jobDetails.job 的精簡重構（不含任何真實快照或外部路徑）。"""
    job = {
        "id": JOB_ID,
        "title": "AI Agent Engineer",
        "abstract": "Build agents.",
        "content": HTML_CONTENT,
        "advertiser": {"id": "60285505", "name": "Example Bank Limited"},
        "location": {"label": "Mong Kok"},
        "workTypes": {"label": "Full time"},
        "listedAt": {"dateTimeUtc": "2026-11-12T08:15:07.000Z"},
        "expiresAt": {"dateTimeUtc": "2026-12-12T12:59:59.999Z"},
        "salary": None,
    }
    job.update(overrides)
    return job


def detail_response(job=None, **overrides):
    payload = {"data": {"jobDetails": {"job": detail_job() if job is None else job}}}
    payload.update(overrides)
    return payload


def fake_http(status=200, text="", payload=None):
    """給 _post_graphql 用的假 requests.Response。"""
    body = text if text else json.dumps(payload if payload is not None else {})
    return SimpleNamespace(
        status_code=status,
        text=body,
        json=lambda: json.loads(body),
    )


class TestDetailQueryShape(unittest.TestCase):
    """query 只取公開廣告欄位，不碰申請問卷、不帶任何憑證。"""

    def test_full_query_requests_content(self):
        q = build_job_details_query()
        self.assertIn("content", q)
        self.assertIn("jobDetails(id: $id)", q)
        self.assertIn("$id: ID!", q)

    def test_light_query_drops_content_only(self):
        q = build_job_details_query(light=True)
        self.assertNotIn("content", q)
        self.assertIn("abstract", q)
        self.assertIn("title", q)

    def test_questionnaire_is_never_selected(self):
        for q in (build_job_details_query(), build_job_details_query(light=True)):
            self.assertNotIn("products", q)
            self.assertNotIn("questionnaire", q)
            self.assertNotIn("questions", q)

    def test_no_credential_or_tracking_fields(self):
        q = build_job_details_query()
        self.assertFalse(re.search(r"cookie|authorization|bearer|li_at|visitor|session", q, re.I))

    def test_braces_are_balanced(self):
        for q in (build_job_details_query(), build_job_details_query(light=True)):
            self.assertEqual(q.count("{"), q.count("}"))
            self.assertNotIn("__", q)


class TestParseDetailResponse(unittest.TestCase):
    """回應轉 13 欄 JobRecord：HTML 轉純文字、相對日期、來歷只進 raw。"""

    def test_returns_all_13_fields(self):
        r = parse_job_details_response(detail_response(), job_url=JOB_URL, now=NOW)
        self.assertEqual(set(r.to_dict()), set(JobRecord.FIELDS))
        self.assertEqual(len(r.to_dict()), 13)
        self.assertEqual(r.job_id, f"jobsdb_{JOB_ID}")
        self.assertEqual(r.source, "jobsdb")
        self.assertEqual(r.url, JOB_URL)

    def test_html_content_becomes_plain_text(self):
        r = parse_job_details_response(detail_response(), job_url=JOB_URL, now=NOW)
        self.assertIn("Key Responsibilities", r.description)
        self.assertIn("Build & optimise RAG pipelines", r.description)
        self.assertNotRegex(r.description, r"<[a-zA-Z]+>")
        self.assertNotIn("&amp;", r.description)

    def test_light_response_falls_back_to_abstract(self):
        job = detail_job()
        job.pop("content")
        r = parse_job_details_response(detail_response(job), job_url=JOB_URL, now=NOW)
        self.assertEqual(r.description, "Build agents.")

    def test_posted_date_stays_relative_and_parseable(self):
        r = parse_job_details_response(detail_response(), job_url=JOB_URL, now=NOW)
        self.assertEqual(r.posted_date, "2d ago")
        self.assertEqual(parse_date(r.posted_date, r.scraped_at), "2026-11-12")
        scraper = JobsDBScraper.__new__(JobsDBScraper)
        self.assertEqual(scraper.days_since_posted(r), 2)

    def test_salary_label_is_kept_and_parseable(self):
        job = detail_job(salary={"label": "$50,000 – $60,000 per month"})
        r = parse_job_details_response(detail_response(job), job_url=JOB_URL, now=NOW)
        self.assertEqual(r.salary, "$50,000 – $60,000 per month")
        self.assertEqual(parse_salary(r.salary)[:3], (50000, 60000, "month"))

    def test_core_fields_are_mapped(self):
        r = parse_job_details_response(detail_response(), job_url=JOB_URL, now=NOW)
        self.assertEqual(r.title, "AI Agent Engineer")
        self.assertEqual(r.company, "Example Bank Limited")
        self.assertEqual(r.location, "Mong Kok")
        self.assertEqual(r.job_type, "Full time")
        self.assertEqual(r.industry, "")
        self.assertEqual(r.requirements, "")

    def test_metadata_stays_in_raw_not_main_table(self):
        r = parse_job_details_response(detail_response(), job_url=JOB_URL, now=NOW)
        meta = r.raw["graphql_detail"]
        self.assertEqual(meta["listed_at_utc"], "2026-11-12T08:15:07.000Z")
        self.assertEqual(meta["expires_at_utc"], "2026-12-12T12:59:59.999Z")
        self.assertEqual(meta["content_html_length"], len(HTML_CONTENT))
        self.assertNotIn("expires_at_utc", r.to_dict())

    def test_null_job_details_is_a_single_missing_record(self):
        self.assertIsNone(parse_job_details_response({"data": {"jobDetails": None}}))
        self.assertIsNone(parse_job_details_response({"data": {}}))

    def test_graphql_errors_are_rejected(self):
        with self.assertRaisesRegex(JobsDBGraphQLError, "詳情 GraphQL errors"):
            parse_job_details_response({"errors": [{"message": "Field X not defined"}]})

    def test_malformed_shapes_are_rejected(self):
        for payload in ([], "oops", 42, {"data": {"jobDetails": []}},
                        {"data": {"jobDetails": {"job": "oops"}}}):
            with self.subTest(payload=str(payload)[:30]), \
                    self.assertRaises(JobsDBGraphQLError):
                parse_job_details_response(payload)

    def test_broken_field_types_degrade_safely(self):
        job = detail_job(content=123, advertiser=None, location=[], workTypes="oops",
                         listedAt="bad", expiresAt=None)
        r = parse_job_details_response(detail_response(job), job_url=JOB_URL, now=NOW)
        self.assertEqual(len(r.to_dict()), 13)
        self.assertEqual(r.description, "Build agents.")
        self.assertEqual(r.posted_date, "")

    def test_missing_id_still_returns_13_fields(self):
        job = detail_job(id=None)
        r = parse_job_details_response(detail_response(job), job_url=JOB_URL, now=NOW)
        self.assertEqual(len(r.to_dict()), 13)
        self.assertEqual(r.url, JOB_URL)


class _EnvMixin:
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("JOBSDB_GRAPHQL", None)


class TestDetailRouting(_EnvMixin, unittest.TestCase):
    """成功不碰瀏覽器；失敗熔斷本輪；413 只影響單筆。"""

    def _scraper(self):
        return JobsDBScraper()

    def test_success_never_touches_browser(self):
        s = self._scraper()
        with patch.object(s, "_post_graphql", return_value=detail_response()) as post, \
                patch.object(s, "_get_detail_browser",
                             side_effect=AssertionError("不應退回瀏覽器")), \
                patch.object(s, "_ensure_browser",
                             side_effect=AssertionError("不應啟動 Playwright")):
            r = s.get_detail(JOB_URL)
        self.assertEqual(r.job_id, f"jobsdb_{JOB_ID}")
        self.assertEqual(post.call_count, 1)
        self.assertFalse(s._gql_detail_broken)
        self.assertEqual(post.call_args.kwargs["variables"], {"id": JOB_ID})

    def test_disabled_by_env_var(self):
        s = self._scraper()
        with patch.dict(os.environ, {"JOBSDB_GRAPHQL": "0"}), \
                patch.object(s, "_post_graphql",
                             side_effect=AssertionError("不應發 GraphQL")), \
                patch.object(s, "_get_detail_browser", return_value="BROWSER") as browser:
            self.assertEqual(s.get_detail(JOB_URL), "BROWSER")
        browser.assert_called_once_with(JOB_URL)

    def test_missing_job_id_goes_to_browser(self):
        s = self._scraper()
        with patch.object(s, "_post_graphql",
                          side_effect=AssertionError("不應發 GraphQL")), \
                patch.object(s, "_get_detail_browser", return_value="BROWSER") as browser:
            self.assertEqual(s.get_detail("https://hk.jobsdb.com/jobs?keywords=x"), "BROWSER")
        browser.assert_called_once()

    def test_channel_failure_breaks_circuit_for_this_run(self):
        s = self._scraper()
        with patch.object(s, "_post_graphql",
                          side_effect=JobsDBGraphQLError("schema 改版")), \
                patch.object(s, "_get_detail_browser", return_value="BROWSER") as browser:
            self.assertEqual(s.get_detail(JOB_URL), "BROWSER")
            self.assertEqual(s.get_detail(JOB_URL), "BROWSER")
        self.assertTrue(s._gql_detail_broken)
        self.assertEqual(browser.call_count, 2)

    def test_network_exception_also_breaks_circuit(self):
        s = self._scraper()
        with patch.object(s, "_post_graphql", side_effect=requests.Timeout("timeout")), \
                patch.object(s, "_get_detail_browser", return_value="BROWSER"):
            self.assertEqual(s.get_detail(JOB_URL), "BROWSER")
        self.assertTrue(s._gql_detail_broken)

    def test_search_circuit_does_not_disable_detail_channel(self):
        s = self._scraper()
        s._gql_broken = True
        with patch.object(s, "_post_graphql", return_value=detail_response()), \
                patch.object(s, "_get_detail_browser",
                             side_effect=AssertionError("不應退回瀏覽器")):
            self.assertEqual(s.get_detail(JOB_URL).job_id, f"jobsdb_{JOB_ID}")

    def test_payload_too_large_retries_light_without_breaking_circuit(self):
        s = self._scraper()
        light = detail_response(detail_job(content=None))
        with patch.object(s, "_post_graphql",
                          side_effect=[JobsDBGraphQLError("HTTP 413"), light]) as post, \
                patch.object(s, "_get_detail_browser",
                             side_effect=AssertionError("不應退回瀏覽器")):
            r = s.get_detail(JOB_URL)
        self.assertEqual(post.call_count, 2)
        self.assertIn("content", post.call_args_list[0].args[0])
        self.assertNotIn("content", post.call_args_list[1].args[0])
        self.assertEqual(r.description, "Build agents.")
        self.assertFalse(s._gql_detail_broken)

    def test_light_retry_failure_still_breaks_circuit(self):
        s = self._scraper()
        with patch.object(s, "_post_graphql",
                          side_effect=[JobsDBGraphQLError("HTTP 413"),
                                       JobsDBGraphQLError("HTTP 500")]), \
                patch.object(s, "_get_detail_browser", return_value="BROWSER"):
            self.assertEqual(s.get_detail(JOB_URL), "BROWSER")
        self.assertTrue(s._gql_detail_broken)

    def test_null_detail_returns_none_without_browser(self):
        s = self._scraper()
        with patch.object(s, "_post_graphql",
                          return_value={"data": {"jobDetails": None}}), \
                patch.object(s, "_get_detail_browser",
                             side_effect=AssertionError("不應退回瀏覽器")):
            self.assertIsNone(s.get_detail(JOB_URL))
        self.assertFalse(s._gql_detail_broken)

    def test_payload_too_large_detector_is_narrow(self):
        self.assertTrue(_is_payload_too_large(RuntimeError("HTTP 413")))
        self.assertTrue(_is_payload_too_large(RuntimeError("Payload Too Large")))
        self.assertFalse(_is_payload_too_large(RuntimeError("HTTP 429")))
        self.assertFalse(_is_payload_too_large(RuntimeError("schema 改版")))


class TestPostGraphQLVariables(unittest.TestCase):
    """_post_graphql 的 variables 只給 jobDetails，既有 jobSearchV7 payload 不變。"""

    def test_search_call_still_sends_query_only(self):
        s = JobsDBScraper()
        with patch("scrapers.jobsdb.requests.post",
                   return_value=fake_http(payload={"data": {}})) as post:
            s._post_graphql("query { jobSearchV7 }")
        self.assertEqual(post.call_args.kwargs["json"], {"query": "query { jobSearchV7 }"})

    def test_detail_call_sends_variables_and_no_credentials(self):
        s = JobsDBScraper()
        with patch("scrapers.jobsdb.requests.post",
                   return_value=fake_http(payload={"data": {}})) as post:
            s._post_graphql(build_job_details_query(), variables={"id": JOB_ID})
        kw = post.call_args.kwargs
        self.assertEqual(kw["json"]["variables"], {"id": JOB_ID})
        self.assertEqual(set(kw["json"]), {"query", "variables"})
        self.assertNotIn("Cookie", kw["headers"])
        self.assertNotIn("Authorization", kw["headers"])


class TestDetailMergePolicy(unittest.TestCase):
    """白名單 opt-in：只有 JobsDB 覆寫 description，其餘 11 站零行為變化。"""

    def _records(self, list_description, detail_description):
        detail = parse_job_details_response(detail_response(), job_url=JOB_URL, now=NOW)
        detail.description = detail_description
        listed = JobRecord(**{**detail.to_dict(), "description": list_description})
        return listed, detail

    def test_base_default_is_empty(self):
        from base_scraper import BaseScraper
        self.assertEqual(BaseScraper.detail_replace_fields, frozenset())

    def test_only_jobsdb_opts_in(self):
        from scrapers import SCRAPERS
        for name, cls in SCRAPERS.items():
            with self.subTest(name=name):
                expected = (frozenset({"description"}) if name == "jobsdb"
                            else frozenset())
                self.assertEqual(cls.detail_replace_fields, expected)

    def test_full_jd_replaces_list_abstract(self):
        listed, detail = self._records("Build agents.", "A" * 3000)
        s = JobsDBScraper()
        with patch.object(s, "search", return_value=[listed]), \
                patch.object(s, "get_detail", return_value=detail), \
                patch.object(s, "_sleep"):
            out = s.scrape_all("x", max_pages=1, with_detail=True)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].description, "A" * 3000)

    def test_shorter_detail_does_not_replace_list_value(self):
        listed, detail = self._records("A" * 500, "short")
        s = JobsDBScraper()
        with patch.object(s, "search", return_value=[listed]), \
                patch.object(s, "get_detail", return_value=detail), \
                patch.object(s, "_sleep"):
            out = s.scrape_all("x", max_pages=1, with_detail=True)
        self.assertEqual(out[0].description, "A" * 500)

    def test_other_sources_keep_list_value(self):
        from scrapers import SCRAPERS
        gov = SCRAPERS["gov_hk"]()
        listed, detail = self._records("list value", "A" * 3000)
        with patch.object(gov, "search", return_value=[listed]), \
                patch.object(gov, "get_detail", return_value=detail), \
                patch.object(gov, "_sleep"):
            out = gov.scrape_all("x", max_pages=1, with_detail=True)
        self.assertEqual(out[0].description, "list value")


if __name__ == "__main__":
    unittest.main()
