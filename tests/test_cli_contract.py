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
