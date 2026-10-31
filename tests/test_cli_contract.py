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


import contextlib

from hkjobs import cli


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class TestSourcesCommand(unittest.TestCase):
    def test_sources_json(self):
        code, out, _ = run_cli(["sources", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["command"], "sources")
        self.assertEqual(len(payload["sources"]), 12)
        self.assertEqual(
            payload["presets"]["all"],
            [n for n, i in SOURCES.items() if i.enabled],
        )
        gov = next(s for s in payload["sources"] if s["name"] == "gov_hk")
        self.assertEqual(gov["valueCounts"], {"district": 27, "category": 29, "industry": 27})
        self.assertEqual(gov["daysMode"], "server")
        self.assertFalse(gov["needsBrowser"])

    def test_sources_human(self):
        code, out, _ = run_cli(["sources"])
        self.assertEqual(code, 0)
        self.assertIn("勞工處", out)

    def test_sources_human_columns_aligned(self):
        """CJK 全形字要按「顯示寬度」補齊；按字元數補會讓中文站名擠歪表格。"""
        import re

        from hkjobs.cli import _disp_width

        code, out, _ = run_cli(["sources"])
        self.assertEqual(code, 0)

        starts = set()
        # 只認「維度欄的開頭」：district/category/industry 的整段組合（或 —）後面接 " / "
        dims = r"(?:(?:district|category|industry)(?:/(?:district|category|industry))*|—) / "
        for line in out.splitlines():
            match = re.search(dims, line)
            if match:
                starts.add(_disp_width(line[:match.start()]))
        self.assertEqual(len(starts), 1, f"維度欄起點不一致：{starts}")
        # 標籤剛好頂滿欄寬時，兩欄會黏成一串（修正前的症狀）
        self.assertNotIn("求職廣場jobmarket", out)
        self.assertNotIn("eFinancialCareersefc", out)

    def test_disp_width_counts_fullwidth_as_two(self):
        from hkjobs.cli import _disp_width

        self.assertEqual(_disp_width("abc"), 3)
        self.assertEqual(_disp_width("求職"), 4)
        self.assertEqual(_disp_width("Job Market"), 10)


class TestOptionsCommand(unittest.TestCase):
    def test_options_json_dimension(self):
        code, out, _ = run_cli(
            ["options", "--source", "jobsdb", "--dimension", "district", "--json"]
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["source"], "jobsdb")
        self.assertEqual(payload["dimensions"]["district"]["count"], 40)

    def test_options_unsupported_is_null(self):
        code, out, _ = run_cli(
            ["options", "--source", "jobsdb", "--dimension", "industry", "--json"]
        )
        self.assertEqual(code, 0)
        self.assertIsNone(json.loads(out)["dimensions"]["industry"])

    def test_options_rejects_all(self):
        code, _, err = run_cli(["options", "--source", "all"])
        self.assertEqual(code, 2)
        self.assertIn("未知來源", err)


import os
import tempfile
from unittest import mock

from hkjobs.capabilities import SourceInfo
from scrapers import SCRAPERS  # noqa: F811  （Task 3 已 import，此行供 clarity）


def _fake_info(name="fake", enabled=True):
    return SourceInfo(
        name=name, label="Fake", enabled=enabled, needs_browser=False,
        needs_chrome=False, per_page=1, keyword_required=False,
        days_mode="list", sort_values=(), supports={}, request_delay=0.0, notes="",
    )


class _OkScraper:
    def __init__(self):
        pass

    def scrape_all(self, **kwargs):
        return [JobRecord(job_id="fake::1", source="fake", title="工程師", salary="20000")]

    def close(self):
        pass


class _EmptyScraper(_OkScraper):
    def scrape_all(self, **kwargs):
        return []


class _FailScraper(_OkScraper):
    def scrape_all(self, **kwargs):
        raise RuntimeError("HTTP 403")


class TestSearchCommand(unittest.TestCase):
    def _patched(self, infos, registry):
        return mock.patch.multiple(cli, SOURCES=infos, SCRAPERS=registry)

    def test_success_envelope(self):
        with self._patched({"fake": _fake_info()}, {"fake": _OkScraper}):
            code, out, _ = run_cli(["search", "--source", "fake", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["summary"]["sources"][0]["status"], "ok")
        self.assertEqual(set(payload["jobs"][0]), set(JobRecord.FIELDS))
        self.assertNotIn("error", payload)
        self.assertEqual(payload["query"]["sort"], None)

    def test_no_results(self):
        with self._patched({"fake": _fake_info()}, {"fake": _EmptyScraper}):
            code, out, _ = run_cli(["search", "--source", "fake", "--json"])
        self.assertEqual(code, 5)
        self.assertEqual(json.loads(out)["error"]["code"], "no_results")

    def test_partial_failure(self):
        infos = {"good": _fake_info("good"), "bad": _fake_info("bad")}
        registry = {"good": _OkScraper, "bad": _FailScraper}
        with self._patched(infos, registry):
            code, out, _ = run_cli(["search", "--source", "all", "--json"])
        self.assertEqual(code, 3)
        payload = json.loads(out)
        self.assertEqual(payload["error"]["code"], "partial_failure")
        self.assertEqual(
            [s["status"] for s in payload["summary"]["sources"]], ["ok", "failed"]
        )

    def test_all_failed(self):
        infos = {"bad": _fake_info("bad")}
        with self._patched(infos, {"bad": _FailScraper}):
            code, out, _ = run_cli(["search", "--source", "bad", "--json"])
        self.assertEqual(code, 4)
        self.assertEqual(json.loads(out)["error"]["code"], "all_sources_failed")

    def test_skipped_source_reported(self):
        infos = {"off": _fake_info("off", enabled=False)}
        with self._patched(infos, {"off": _OkScraper}):
            code, out, _ = run_cli(["search", "--source", "all", "--json"])
        self.assertEqual(code, 5)
        payload = json.loads(out)
        self.assertEqual(payload["summary"]["sources"][0]["status"], "skipped")

    def test_unknown_source(self):
        with self._patched({"fake": _fake_info()}, {"fake": _OkScraper}):
            code, _, err = run_cli(["search", "--source", "nope", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("未知來源", err)

    def test_json_writes_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            os.chdir(tmp)
            try:
                with self._patched({"fake": _fake_info()}, {"fake": _OkScraper}):
                    code, _, _ = run_cli(["search", "--source", "fake", "--json"])
                self.assertEqual(code, 0)
                self.assertEqual(os.listdir(tmp), [])
            finally:
                os.chdir(old)

    def test_out_json_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "result.json")
            with self._patched({"fake": _fake_info()}, {"fake": _OkScraper}):
                code, out, _ = run_cli(
                    ["search", "--source", "fake", "--json", "--out", path]
                )
            self.assertEqual(code, 0)
            with open(path, encoding="utf-8") as fh:
                saved = json.load(fh)
            self.assertEqual(saved, json.loads(out))

    def test_out_csv_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "result.csv")
            with self._patched({"fake": _fake_info()}, {"fake": _OkScraper}):
                code, _, _ = run_cli(["search", "--source", "fake", "--out", path])
            self.assertEqual(code, 0)
            with open(path, "rb") as fh:
                raw = fh.read()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            self.assertIn(b"job_id", raw)
            self.assertIn("工程師".encode("utf-8"), raw)

    def test_unexpected_error_envelope(self):
        with mock.patch.object(cli, "cmd_search", side_effect=RuntimeError("boom")):
            code, out, _ = run_cli(["search", "--source", "fake", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["error"]["code"], "unexpected")


import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestPackaging(unittest.TestCase):
    def test_pyproject_declares_entry_point(self):
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn('hkjobs = "hkjobs.cli:main"', text)
        self.assertIn('scrapers = ["*.json"]', text)


class TestModuleEntry(unittest.TestCase):
    def test_python_m_hkjobs_utf8(self):
        proc = subprocess.run(
            [sys.executable, "-m", "hkjobs", "sources", "--json"],
            cwd=ROOT,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        payload = json.loads(proc.stdout.decode("utf-8"))
        self.assertEqual(len(payload["sources"]), 12)
        self.assertTrue(any(s["label"] == "勞工處" for s in payload["sources"]))
