# -*- coding: utf-8 -*-
"""Windows cp950 管道輸入中文不應讓引導模式崩潰（零網路、零爬取）。

對應 2026-11-12 用戶端覆核：`configure_io()` 原本只處理 stdout/stderr，
被重定向的 stdin 仍用 cp950 去解 UTF-8 位元組，產生 lone surrogate；
之後把關鍵字 print 到 UTF-8 stdout 就 `UnicodeEncodeError: surrogates not allowed`。

本檔全部用 subprocess 管道或 mock，不會發出任何爬取請求。
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hkjobs import cli, contract

ROOT = Path(__file__).resolve().parent.parent

# 2 = 勞工處、文員 = 關鍵字、其餘選預設、n = 取消（與用戶端重現指令一致）
UTF8_ANSWERS = b"2\n\xe6\x96\x87\xe5\x93\xa1\n1\n1\n1\nn\n"
# cmd.exe 的 `echo 文員 | hkjobs` 會送 cp950 位元組，方向相反也要能還原
CP950_ANSWERS = b"2\n" + "文員".encode("cp950") + b"\n1\n1\n1\nn\n"


def _run_guide(data: bytes, overrides: dict[str, str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("PYTHONIOENCODING", None)
    env.update(overrides)
    return subprocess.run(
        [sys.executable, "-m", "hkjobs"],
        input=data, cwd=ROOT, capture_output=True, env=env, timeout=30,
    )


def _assert_clean_guide(tc: unittest.TestCase, proc: subprocess.CompletedProcess):
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    combined = out + err
    tc.assertEqual(proc.returncode, 0, combined)
    tc.assertIn("--keyword 文員", out, combined)
    tc.assertIn("已取消，未發出任何爬取請求", out, combined)
    for bad in ("Traceback", "UnicodeEncodeError", "surrogates not allowed",
                "未預期錯誤"):
        tc.assertNotIn(bad, combined)


class TestPipedStdinEncoding(unittest.TestCase):
    def test_windows_cp950_default_with_utf8_keyword(self):
        """驗收 1：未設 PYTHONIOENCODING、UTF-8 mode 關閉，等同 Windows cp950。"""
        _assert_clean_guide(self, _run_guide(UTF8_ANSWERS, {
            "PYTHONUTF8": "0",
            "PYTHONCOERCECLOCALE": "0",
            "LC_ALL": "C",
            "LANG": "C",
        }))

    def test_explicit_cp950_stdin_with_utf8_keyword(self):
        """任何平台都能強迫 stdin 走 cp950，守住 reconfigure 這條路。"""
        _assert_clean_guide(self, _run_guide(
            UTF8_ANSWERS, {"PYTHONIOENCODING": "cp950"}))

    def test_cmd_style_cp950_encoded_keyword(self):
        """反向情境：stdin 已是 UTF-8，但管道送 cp950 位元組 → 修補要還原中文。"""
        _assert_clean_guide(self, _run_guide(
            CP950_ANSWERS, {"PYTHONIOENCODING": "cp950"}))

    def test_control_group_utf8_everywhere(self):
        """對照組：原本就正常的環境不能被改壞。"""
        _assert_clean_guide(self, _run_guide(
            UTF8_ANSWERS, {"PYTHONIOENCODING": "utf-8"}))


class TestRepairHelpers(unittest.TestCase):
    def test_repair_utf8_bytes_misread_as_cp950(self):
        bad = "\udce6\udc96\udc87\udce5\udc93\udca1"
        with mock.patch.object(sys, "stdin", SimpleNamespace(encoding="cp950")):
            self.assertEqual(contract.repair_stdin_text(bad), "文員")

    def test_repair_cp950_bytes_misread_as_utf8(self):
        raw = "文員".encode("cp950")
        bad = "".join(chr(0xDC00 + b) for b in raw)
        with mock.patch.object(sys, "stdin", SimpleNamespace(encoding="utf-8")):
            self.assertEqual(contract.repair_stdin_text(bad), "文員")

    def test_clean_text_is_untouched_and_no_surrogate_survives(self):
        for text in ("", "2", "n", "y", "文員", "--source all"):
            self.assertEqual(contract.repair_stdin_text(text), text)
        with mock.patch.object(sys, "stdin", SimpleNamespace(encoding="utf-8")):
            repaired = contract.repair_stdin_text("不\udcff可")
        self.assertIsNone(re.search(r"[\udc80-\udcff]", repaired))

    def test_read_input_repairs_and_preserves_eof(self):
        with mock.patch("builtins.input", return_value="\udce6\udc96\udc87"), \
                mock.patch.object(sys, "stdin", SimpleNamespace(encoding="cp950")):
            self.assertEqual(contract.read_input("關鍵字："), "文")
        with mock.patch("builtins.input", side_effect=EOFError()):
            with self.assertRaises(EOFError):
                contract.read_input("繼續？")


class TestConsoleStdinPolicy(unittest.TestCase):
    def test_interactive_console_stdin_is_never_touched(self):
        """驗收 3 的程式面保證：真實 console 走 Unicode API，一個位元組都不改。"""
        class _Console:
            @staticmethod
            def isatty():
                return True

            @staticmethod
            def reconfigure(**_kw):
                raise AssertionError("不該 reconfigure 互動式 console stdin")

        sink = io.StringIO()
        with mock.patch.object(sys, "stdin", _Console()), \
                mock.patch.object(sys, "stdout", sink), \
                mock.patch.object(sys, "stderr", sink):
            contract.configure_io()  # 不應丟出 AssertionError

    def test_redirected_stdin_is_reconfigured(self):
        class _Pipe:
            encoding = "cp950"
            errors = "strict"

            @staticmethod
            def isatty():
                return False

            def reconfigure(self, **kw):
                self.encoding = kw["encoding"]
                self.errors = kw["errors"]

        pipe = _Pipe()
        sink = io.StringIO()
        with mock.patch.object(sys, "stdin", pipe), \
                mock.patch.object(sys, "stdout", sink), \
                mock.patch.object(sys, "stderr", sink):
            contract.configure_io()
        self.assertEqual(pipe.encoding, "utf-8")
        self.assertEqual(pipe.errors, "surrogateescape")

    def test_fill_gaps_confirm_uses_the_same_input_path(self):
        """--fill-gaps 的 y/N 確認與引導模式同源，不再有落單的 raw input()。"""
        args = SimpleNamespace(json=False, yes=False)
        with mock.patch("hkjobs.cli.read_input", return_value="n") as spy, \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            result = cli._announce_gap_fill(args, [], 0)
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(result, contract.EXIT_USAGE)

    def test_no_raw_input_left_in_cli_or_guide(self):
        """靜態守住：兩個模組的程式碼不得再有 `= input(...)` 呼叫。"""
        raw_call = re.compile(r"=\s*input\(")
        for rel in ("hkjobs/cli.py", "hkjobs/guide.py"):
            for lineno, line in enumerate(
                    (ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                self.assertIsNone(raw_call.search(line),
                                  f"{rel}:{lineno} 仍用 raw input()：{line.strip()}")


if __name__ == "__main__":
    unittest.main()
