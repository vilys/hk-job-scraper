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
