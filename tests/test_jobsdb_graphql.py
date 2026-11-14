# -*- coding: utf-8 -*-
"""JobsDB GraphQL 轉 JobRecord 轉接測試（零請求、離線）。

fixture 是欄位形狀的精簡重構，不含任何外部路徑或真實快照。
守三件事：13 欄契約、下游可解析（薪金／日期）、來歷可追溯。
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from hkjobs.aggregate import parse_date, parse_salary
from job_model import JobRecord
from scrapers.jobsdb import JobsDBScraper, record_from_graphql

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


def gql_job(**overrides):
    """最小可用 jobSearchV7 單筆；overrides 可整欄替換。"""
    job = {
        "id": "95858112",
        "title": "AI Agent Engineer",
        "abstract": "Build agents.",
        "advertiser": {"id": "60285505", "name": "Example Bank Limited"},
        "organisation": {"id": "409033", "name": "Example Bank"},
        "location": {"id": "1000160", "displayName": {"text": "Mong Kok"}},
        "workArrangements": [{"id": "1", "label": {"text": "On-site"}}],
        "cjs": {
            "workTypes": [{"sourceId": "242", "name": "Full time"}],
            "salary": {
                "minimum": 4000000, "maximum": 5000000,
                "currency": "HKD", "period": "Monthly", "hideSalary": True,
            },
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


def rec(**overrides):
    return record_from_graphql(gql_job(**overrides), now=NOW)


class TestContract(unittest.TestCase):
    def test_to_dict_is_exactly_13_fields(self):
        self.assertEqual(set(rec().to_dict()), set(JobRecord.FIELDS))
        self.assertEqual(len(rec().to_dict()), 13)

    def test_identity_fields(self):
        r = rec()
        self.assertEqual(r.source, "jobsdb")
        self.assertEqual(r.job_id, "jobsdb_95858112")
        self.assertEqual(r.url, "https://hk.jobsdb.com/job/95858112")

    def test_scraped_at_follows_injected_now(self):
        self.assertEqual(rec().scraped_at, NOW.isoformat())

    def test_raw_never_enters_main_table(self):
        self.assertNotIn("raw", rec().to_dict())

    def test_title_badge_is_stripped(self):
        self.assertEqual(rec(title="AI EngineerNew").title, "AI Engineer")


class TestSalary(unittest.TestCase):
    def test_monthly_range_matches_card_format(self):
        self.assertEqual(rec().salary, "$40,000 – $50,000 per month")

    def test_salary_is_parseable_by_aggregate(self):
        self.assertEqual(parse_salary(rec().salary), (40000, 50000, "month"))

    def test_single_point_salary(self):
        r = rec(salary={"min": 18000, "max": 18000, "period": "monthly", "currency": "HKD"})
        self.assertEqual(r.salary, "$18,000 per month")
        self.assertEqual(parse_salary(r.salary), (18000, 18000, "month"))

    def test_hourly_and_annual_periods(self):
        h = rec(salary={"min": 80, "max": 100, "period": "hourly", "currency": "HKD"})
        self.assertEqual(h.salary, "$80 – $100 per hour")
        self.assertEqual(parse_salary(h.salary)[2], "hour")
        a = rec(salary={"min": 900000, "max": 1100000, "period": "annual", "currency": "HKD"})
        self.assertEqual(a.salary, "$900,000 – $1,100,000 per year")
        self.assertEqual(parse_salary(a.salary)[2], "year")

    def test_unknown_period_does_not_invent_salary(self):
        r = rec(salary={"min": 100, "max": 200, "period": "weekly", "currency": "HKD"})
        self.assertEqual(r.salary, "")
        self.assertEqual(r.raw["graphql"]["salary_period"], "weekly")

    def test_hidden_salary_is_recorded_in_raw(self):
        meta = rec().raw["graphql"]
        self.assertTrue(meta["hide_salary"])
        self.assertEqual(meta["salary_period"], "monthly")
        self.assertEqual(meta["salary_currency"], "HKD")


class TestDate(unittest.TestCase):
    def test_posted_date_is_relative_like_card(self):
        self.assertEqual(rec().posted_date, "2d ago")

    def test_days_since_posted_accepts_output(self):
        scraper = JobsDBScraper.__new__(JobsDBScraper)
        self.assertEqual(scraper.days_since_posted(rec()), 2)

    def test_parse_date_turns_output_into_iso(self):
        r = rec()
        self.assertEqual(parse_date(r.posted_date, r.scraped_at), "2026-11-12")

    def test_exact_utc_is_kept_in_raw(self):
        self.assertEqual(rec().raw["graphql"]["listed_at_utc"],
                         "2026-11-12T08:15:07.000Z")

    def test_recent_and_missing_dates(self):
        just = rec(listedAt={"dateTimeUtc": "2026-11-14T11:59:30.000Z"})
        self.assertEqual(just.posted_date, "Just now")
        self.assertEqual(rec(listedAt={}).posted_date, "")


class TestFields(unittest.TestCase):
    def test_company_falls_back_to_organisation(self):
        self.assertEqual(rec().company, "Example Bank Limited")
        self.assertEqual(rec(advertiser={}).company, "Example Bank")

    def test_industry_takes_parent_category(self):
        self.assertEqual(rec().industry, "Information & Communication Technology")

    def test_job_type_description_location(self):
        r = rec()
        self.assertEqual(r.job_type, "Full time")
        self.assertEqual(r.description, "Build agents.")
        self.assertEqual(r.location, "Mong Kok")

    def test_raw_keeps_secondary_dimensions(self):
        meta = rec().raw["graphql"]
        self.assertEqual(meta["work_arrangements"], ["On-site"])
        self.assertEqual(meta["role_titles"], ["agent"])
        self.assertEqual(meta["advertiser_id"], "60285505")
        self.assertEqual(meta["categories"][0], "Developers/Programmers")


class TestDefensive(unittest.TestCase):
    def test_empty_input_does_not_raise(self):
        r = record_from_graphql({}, now=NOW)
        self.assertEqual(set(r.to_dict()), set(JobRecord.FIELDS))
        self.assertEqual(r.salary, "")
        self.assertEqual(r.posted_date, "")

    def test_non_dict_input_does_not_raise(self):
        self.assertEqual(record_from_graphql(None, now=NOW).source, "jobsdb")

    def test_malformed_nested_values_do_not_raise(self):
        r = record_from_graphql({
            "id": "1", "title": "X", "advertiser": "oops",
            "location": None, "cjs": {"salary": "bad", "workTypes": "bad"},
            "salary": {"min": "abc", "max": None, "period": "monthly"},
            "listedAt": {"dateTimeUtc": "not-a-date"}, "categories": "bad",
            "workArrangements": [None, 3],
        }, now=NOW)
        self.assertEqual(r.salary, "")
        self.assertEqual(r.posted_date, "")
        self.assertEqual(r.job_id, "jobsdb_1")

    def test_zero_salary_is_not_rendered(self):
        r = rec(salary={"min": 0, "max": 0, "period": "monthly", "currency": "HKD"})
        self.assertEqual(r.salary, "")
