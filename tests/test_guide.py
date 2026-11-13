# -*- coding: utf-8 -*-
"""互動引導模式與 Windows 啟動器（零網路、零真實爬取）。"""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from hkjobs import cli, guide
from hkjobs.contract import EXIT_OK

ROOT = Path(__file__).resolve().parent.parent


def _run_guide(answers, execute=None):
    out = io.StringIO()
    spy = execute if execute is not None else mock.Mock(return_value=0)
    with mock.patch("builtins.input", side_effect=answers), \
            contextlib.redirect_stdout(out):
        code = guide.run_guide(execute=spy)
    return code, out.getvalue(), spy


class TestGuidedMode(unittest.TestCase):
    def test_full_flow_builds_command_then_executes(self):
        # 2 = gov_hk；其餘用 Enter 走預設；最後一步 Enter = 執行
        code, out, spy = _run_guide(["2", "文員", "", "", "", ""])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(spy.call_count, 1)
        argv = spy.call_args[0][0]
        self.assertEqual(argv[:2], ["search", "--source"])
        self.assertEqual(argv[2], "gov_hk")
        self.assertIn("--pages", argv)
        self.assertEqual(argv[argv.index("--pages") + 1], "1")
        self.assertEqual(argv[argv.index("--keyword") + 1], "文員")
        self.assertIn("python -m hkjobs search --source gov_hk", out)
        self.assertIn("build_dashboard.py", out)

    def test_cancel_does_not_execute(self):
        code, out, spy = _run_guide(["2", "文員", "", "", "", "n"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(spy.call_count, 0)
        self.assertIn("已取消", out)

    def test_all_source_skips_category_question(self):
        # 9 個啟用站 + 第 10 個選項是 --source all
        code, out, spy = _run_guide(["10", "文員", "", "", "n"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("略過職能題", out)
        self.assertEqual(spy.call_count, 0)

    def test_eof_leaves_cleanly(self):
        code, out, spy = _run_guide([EOFError()])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(spy.call_count, 0)
        self.assertIn("已離開", out)

    def test_no_subcommand_enters_guide(self):
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=EOFError()), \
                contextlib.redirect_stdout(out):
            code = cli.main([])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("引導模式", out.getvalue())

    def test_command_display_quotes_spaces(self):
        text = guide.display_command(
            ["search", "--keyword", "data engineer", "--pages", "1"])
        self.assertIn('"data engineer"', text)

    def test_guide_help_is_cp950_clean(self):
        proc = subprocess.run(
            [sys.executable, "-m", "hkjobs", "guide", "--help"],
            cwd=ROOT, capture_output=True,
            env=dict(os.environ, PYTHONIOENCODING="cp950"),
        )
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode("utf-8", "replace"))
        self.assertNotIn(b"UnicodeEncodeError", proc.stderr)

    def test_existing_flags_api_is_unchanged(self):
        """引導模式是新增入口，不得污染既有旗標集合。"""
        import argparse

        from hkjobs.args import add_machine_arguments, add_search_arguments

        parser = argparse.ArgumentParser()
        add_search_arguments(parser, include_output_flags=False)
        add_machine_arguments(parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        for flag in ("--json", "--source", "--pages", "--fill-gaps",
                     "--salary-by", "--out", "--force"):
            self.assertIn(flag, flags)
        self.assertIn("--version", {s for a in cli.build_parser()._actions
                                    for s in a.option_strings})


class TestPostRunHint(unittest.TestCase):
    """引導模式不寫檔：結尾必須先給 --out 存檔指令，再提 HTML 看板。

    2026-11-13 修：舊提示直接叫人跑 build_dashboard.py，新手在空 output/
    會得到 0 筆空看板。這裡全部用注入的 execute，零真實請求。
    """
    def test_hint_gives_save_command_before_dashboard(self):
        code, out, spy = _run_guide(["2", "文員", "", "", "", ""])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(spy.call_count, 1)
        self.assertIn("沒有寫入檔案", out)
        self.assertIn("--out output/文員.json", out)
        self.assertLess(out.index("--out output/"),
                        out.index("build_dashboard.py"))

    def test_hint_command_is_a_valid_search_command(self):
        import shlex

        _, out, _ = _run_guide(["2", "文員", "", "", "", ""])
        line = next(l.strip() for l in out.splitlines()
                    if l.strip().startswith("python -m hkjobs") and "--out" in l)
        argv = shlex.split(line)[3:]      # 去掉 python -m hkjobs
        args = cli.build_parser().parse_args(argv)
        self.assertEqual(args.out, "output/文員.json")
        self.assertEqual(args.pages, 1)
        self.assertEqual(args.keyword, "文員")
        self.assertEqual(args.source, "gov_hk")

    def test_out_name_sanitizes_windows_illegal_chars(self):
        self.assertEqual(guide._out_name("文員"), "output/文員.json")
        self.assertEqual(guide._out_name("data engineer"),
                         "output/data_engineer.json")
        self.assertEqual(guide._out_name('a/b:c*?"<>|'), "output/abc.json")
        self.assertEqual(guide._out_name(""), "output/jobs.json")

    def test_cancel_prints_no_post_run_hint(self):
        _, out, spy = _run_guide(["2", "文員", "", "", "", "n"])
        self.assertEqual(spy.call_count, 0)
        self.assertNotIn("想留一份檔案", out)
        self.assertNotIn("build_dashboard.py", out)

    def test_hint_text_is_cp950_encodable(self):
        _, out, _ = _run_guide(["2", "文員", "", "", "", ""])
        try:
            out.encode("cp950")
        except UnicodeEncodeError as e:
            self.fail(f"引導模式人類輸出必須 cp950 可編碼：{e}")


class TestStartBat(unittest.TestCase):
    def test_launcher_exists_and_is_ascii_only(self):
        path = ROOT / "start.bat"
        self.assertTrue(path.exists())
        raw = path.read_bytes()
        self.assertTrue(all(b < 128 for b in raw),
                        "start.bat 必須全 ASCII，避免 cp950 主控台亂碼")
        text = raw.decode("ascii")
        self.assertIn("-m hkjobs guide", text)
        self.assertIn("requirements.txt", text)
        self.assertIn("chcp 65001", text)

    def test_launcher_checks_python_before_blaming_dependencies(self):
        """沒裝 Python 時要明確請使用者裝 Python，不得誤報「缺套件」。"""
        text = (ROOT / "start.bat").read_text(encoding="ascii")
        for expected in ('"%PY%" --version', "goto :nopython", ":oldpython",
                         "python.org", "Add python.exe to PATH",
                         "Microsoft Store", "Python 3.10+ was not found"):
            self.assertIn(expected, text)
        # 前提檢查必須排在依賴檢查之前，順序一反就會回到原本的誤導訊息
        self.assertLess(text.index('"%PY%" --version'),
                        text.index("import requests, bs4, lxml"))
        self.assertLess(text.index("goto :nopython"),
                        text.index("Project dependencies are missing"))


if __name__ == "__main__":
    unittest.main()
