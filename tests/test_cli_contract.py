"""hkjobs CLI 契約測試（零網路）。"""
from __future__ import annotations

import unittest

import main


class TestLegacyParser(unittest.TestCase):
    def test_shared_args_module_exists(self):
        from hkjobs.args import build_search_argparser

        parser = build_search_argparser(description="x")
        strings = {s for a in parser._actions for s in a.option_strings}
        self.assertIn("--source", strings)
        self.assertIn("--days", strings)

    def test_legacy_options_unchanged(self):
        parser = main.build_argparser()
        strings = {s for a in parser._actions for s in a.option_strings}
        self.assertEqual(
            strings,
            {
                "-h", "--help", "--source", "--keyword", "--pages", "--output", "--detail",
                "--fill-location", "--outfile", "--district", "--category",
                "--industry", "--sort", "--days",
            },
        )

    def test_legacy_defaults_unchanged(self):
        parser = main.build_argparser()
        self.assertEqual(
            vars(parser.parse_args([])),
            {
                "source": "moovup", "keyword": "", "pages": 3, "output": "json",
                "detail": False, "fill_location": False, "outfile": None,
                "district": None, "category": None, "industry": None,
                "sort": None, "days": None,
            },
        )


import io
import json
from contextlib import redirect_stdout

from hkjobs import contract
from job_model import JobRecord


class TestContract(unittest.TestCase):
    def _job(self, salary=""):
        return JobRecord(job_id="fake::1", source="fake", title="工程師", salary=salary)

    def test_exit_code_ok(self):
        results = [contract.SourceResult("a", "ok", [self._job()])]
        self.assertEqual(contract.exit_code_for(results), contract.EXIT_OK)

    def test_exit_code_empty(self):
        results = [contract.SourceResult("a", "ok", [])]
        self.assertEqual(contract.exit_code_for(results), contract.EXIT_EMPTY)

    def test_exit_code_partial(self):
        results = [
            contract.SourceResult("a", "ok", [self._job()]),
            contract.SourceResult("b", "failed", [], "HTTP 403"),
        ]
        self.assertEqual(contract.exit_code_for(results), contract.EXIT_PARTIAL)

    def test_exit_code_all_failed(self):
        results = [contract.SourceResult("a", "failed", [], "boom")]
        self.assertEqual(contract.exit_code_for(results), contract.EXIT_ALL_FAILED)

    def test_search_payload_shape(self):
        results = [
            contract.SourceResult("a", "ok", [self._job("20000")]),
            contract.SourceResult("b", "failed", [], "HTTP 403"),
            contract.SourceResult("c", "skipped"),
        ]
        code = contract.exit_code_for(results)
        self.assertEqual(code, contract.EXIT_PARTIAL)
        payload = contract.search_payload({"source": "all"}, results, code)
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["command"], "search")
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["summary"]["withSalary"], 1)
        self.assertEqual(
            [s["status"] for s in payload["summary"]["sources"]],
            ["ok", "failed", "skipped"],
        )
        self.assertEqual(payload["error"]["code"], "partial_failure")
        self.assertEqual(set(payload["jobs"][0]), set(JobRecord.FIELDS))

    def test_search_payload_no_error_on_success(self):
        results = [contract.SourceResult("a", "ok", [self._job()])]
        payload = contract.search_payload({"source": "a"}, results, contract.EXIT_OK)
        self.assertNotIn("error", payload)

    def test_emit_json_keeps_chinese(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            contract.emit_json({"t": "勞工處"})
        self.assertIn("勞工處", buf.getvalue())
        self.assertEqual(json.loads(buf.getvalue()), {"t": "勞工處"})


from hkjobs.capabilities import ALL_SORT_VALUES, SOURCES
from scrapers import SCRAPERS


class TestCapabilities(unittest.TestCase):
    def test_sources_cover_registry(self):
        self.assertEqual(set(SOURCES), set(SCRAPERS))

    def test_flags_match_scraper_classes(self):
        for name, cls in SCRAPERS.items():
            info = SOURCES[name]
            self.assertEqual(info.enabled, cls.enabled, name)
            self.assertEqual(info.needs_browser, cls.use_browser, name)

    def test_values_are_valid(self):
        allowed = {"server", "list", "detail", "approx", "none"}
        for name, info in SOURCES.items():
            self.assertIn(info.days_mode, allowed, name)
            self.assertTrue(set(info.sort_values) <= set(ALL_SORT_VALUES), name)
            self.assertGreaterEqual(info.per_page, 0, name)

    def test_enabled_preset_order(self):
        expected = [
            "moovup", "gov_hk", "jobsdb", "linkedin", "recruit",
            "jobmarket", "foundit", "efc", "offertoday",
        ]
        self.assertEqual([n for n, i in SOURCES.items() if i.enabled], expected)


from hkjobs.options import load_dimension


class TestOptions(unittest.TestCase):
    def test_jobsdb_district(self):
        dim = load_dimension("jobsdb", "district")
        self.assertEqual(dim["count"], 40)
        entry = next(e for e in dim["values"] if e["name"] == "荃灣")
        self.assertEqual(entry["id"], "tsuen-wan")
        self.assertIn("tsuen-wan", entry["aliases"])

    def test_gov_hk_category(self):
        dim = load_dimension("gov_hk", "category")
        self.assertTrue(any(e["name"] == "會計" for e in dim["values"]))

    def test_offertoday_nested(self):
        dim = load_dimension("offertoday", "category")
        parent = next(e for e in dim["values"] if e["id"] == "101000")
        self.assertEqual(parent["name"], "會計")
        child = next(e for e in dim["values"] if e["id"] == "101000c101001")
        self.assertEqual(child["parentId"], "101000")

    def test_counts(self):
        self.assertEqual(load_dimension("recruit", "district")["count"], 94)
        self.assertEqual(load_dimension("jobmarket", "industry")["count"], 30)
        self.assertEqual(load_dimension("efc", "district")["count"], 3)
        self.assertEqual(load_dimension("linkedin", "district")["count"], 20)
        self.assertEqual(load_dimension("liepin", "district")["count"], 18)

    def test_moovup_shortcode(self):
        dim = load_dimension("moovup", "district")
        entry = next(e for e in dim["values"] if e["id"] == "000011")
        self.assertEqual(entry["name"], "香港仔")

    def test_free_and_unsupported(self):
        self.assertEqual(load_dimension("indeed", "district")["kind"], "free")
        self.assertIsNone(load_dimension("jobsdb", "industry"))
        self.assertIsNone(load_dimension("zhipin", "district"))
        self.assertIsNone(load_dimension("moovup", "sort"))
        self.assertEqual(load_dimension("gov_hk", "sort")["kind"], "enum")

    def test_supports_flag_matches_loader(self):
        for name, info in SOURCES.items():
            for dim in ("district", "category", "industry"):
                loaded = load_dimension(name, dim)
                self.assertEqual(
                    loaded is not None, info.supports.get(dim, False), f"{name}.{dim}"
                )
            self.assertEqual(
                load_dimension(name, "sort") is not None,
                bool(info.sort_values),
                f"{name}.sort",
            )
