# -*- coding: utf-8 -*-
"""HTML 儀表板對齊 schema v2、日期單一來源、無障礙與 --out（零網路）。

對應「四項改善」的 P2-3。這裡刻意用 `contract.search_payload()` 造出
CLI 真正會寫進 `--out x.json` 的封套，直接驗證「CLI 抓、HTML 讀」這條路，
而不是自己手刻一個長得像 v2 的 dict。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import build_dashboard as bd
from hkjobs import aggregate, contract
from job_model import JobRecord

ROOT = Path(__file__).resolve().parent.parent
REF = "2026-11-11T09:00:00+00:00"          # 固定抓取日，測試不受「今天」影響


def _cli_v2_payload(posted_date="7日前") -> dict:
    """用真正的 CLI 聚合管線產出 schema v2 封套。"""
    rec = JobRecord(
        job_id="gov_hk::1", source="gov_hk", title="文員",
        company="測試公司", location="中環", salary="$15,000 - $18,000（月薪）",
        url="https://example.test/jobs/1", posted_date=posted_date,
        scraped_at=REF, description="處理一般文書工作",
    )
    return contract.search_payload(
        {"source": "gov_hk", "keyword": "文員", "pages": 1},
        [contract.SourceResult(name="gov_hk", status="ok", jobs=[rec])],
        contract.EXIT_OK,
    )


def _write_json(path: Path, obj) -> str:
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return str(path)


class TestReadsV2Envelope(unittest.TestCase):
    def test_cli_v2_envelope_is_not_skipped(self):
        """過去只認職位陣列，CLI 的 --json --out 檔會被當成非職位檔略過。"""
        with tempfile.TemporaryDirectory() as td:
            p = _write_json(Path(td) / "x.json", _cli_v2_payload())
            rows = bd._read_json_jobs(p)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "文員")
            # 只取 jobs[]（v2 專有欄位仍在），不是把整包封套當成一筆職位
            self.assertEqual(rows[0]["posted_date_raw"], "7日前")
            self.assertEqual(rows[0]["posted_date"], "2026-11-04")
            self.assertNotIn("schemaVersion", rows[0])

    def test_v2_envelope_flows_into_collect(self):
        """端對端：CLI 封套 → build_dashboard.collect() → 看得到該職位。"""
        with tempfile.TemporaryDirectory() as td:
            p = _write_json(Path(td) / "x.json", _cli_v2_payload())
            jobs, meta = bd.collect([p])
            self.assertEqual(meta["total"], 1)
            self.assertEqual(meta["raw_rows"], 1)
            self.assertEqual(meta["per_source"], {"gov_hk": 1})
            self.assertEqual(jobs[0]["title"], "文員")
            self.assertEqual(jobs[0]["company"], "測試公司")
            self.assertEqual(jobs[0]["age_days"], 7)
            self.assertNotIn("x.json", meta["files_skipped"])

    def test_v1_job_array_still_read(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_json(Path(td) / "old.json", [
                {"job_id": "a::1", "title": "舊格式職位", "source": "moovup",
                 "posted_date": "2026-11-08", "scraped_at": REF},
            ])
            self.assertEqual(len(bd._read_json_jobs(p)), 1)

    def test_non_job_json_is_skipped(self):
        """地區統計等非職位檔不能被誤算成職位。"""
        with tempfile.TemporaryDirectory() as td:
            p = _write_json(Path(td) / "stats.json",
                            {"districts": [{"name": "中環", "count": 12}]})
            self.assertEqual(bd._read_json_jobs(p), [])

    def test_empty_and_malformed_envelopes_are_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            for i, obj in enumerate([
                {"schemaVersion": 2, "jobs": []},
                {"schemaVersion": 2, "jobs": ["not-a-dict"]},
                {"schemaVersion": 2, "summary": {"total": 0}},
                [1, 2, 3],
            ]):
                p = _write_json(Path(td) / f"e{i}.json", obj)
                self.assertEqual(bd._read_json_jobs(p), [], obj)


class TestDateSingleSource(unittest.TestCase):
    def test_age_uses_scraped_at_not_today(self):
        """舊版用 date.today()，舊存檔會越放越舊；基準必須是抓取日。"""
        rec = {"posted_date_raw": "7日前", "scraped_at": REF}
        self.assertEqual(bd.parse_age_days(rec), 7)
        self.assertEqual(bd._reference_day(REF).isoformat(), "2026-11-11")
        self.assertEqual(bd._reference_day("2026-01-02T00:00:00Z").isoformat(),
                         "2026-01-02")

    def test_legacy_zh_relative_and_days_plus(self):
        """舊 dashboard 自有 parser 的格式，改由 aggregate.parse_date 接手。"""
        self.assertEqual(aggregate.parse_date("7日前", REF), "2026-11-04")
        self.assertEqual(aggregate.parse_date("2個月前", REF), "2026-09-12")
        self.assertEqual(aggregate.parse_date("30d+", REF), "2026-10-12")
        for raw in ("7日前", "2個月前", "30d+"):
            self.assertIsNotNone(
                bd.parse_age_days({"posted_date_raw": raw, "scraped_at": REF}),
                raw)

    def test_v2_raw_date_wins_over_iso_field(self):
        """v2 的 posted_date 已是 ISO；posted_date_raw 存在時仍以原文解析。"""
        rec = {"posted_date_raw": "2個月前", "posted_date": "",
               "scraped_at": REF}
        self.assertEqual(bd.parse_age_days(rec), 60)

    def test_unparseable_date_returns_none(self):
        self.assertIsNone(bd.parse_age_days({"posted_date": ""}))
        self.assertIsNone(bd.parse_age_days({"posted_date": "不詳",
                                             "scraped_at": REF}))

    def test_normalize_writes_iso_posted_date(self):
        n = bd.normalize({"job_id": "a::1", "title": "文員",
                          "posted_date_raw": "7日前", "scraped_at": REF},
                         "x.json")
        self.assertEqual(n["posted_date"], "2026-11-04")
        self.assertEqual(n["age_days"], 7)

    def test_dashboard_has_no_parallel_date_parser(self):
        """避免又養出第二套 regex：日期只由 hkjobs.aggregate 負責。"""
        src = (ROOT / "build_dashboard.py").read_text(encoding="utf-8")
        self.assertIn("from hkjobs import aggregate", src)
        self.assertIn("aggregate.parse_date", src)
        for legacy in ("_REL_EN =", "_REL_CN =", "_UNIT_DAYS_"):
            self.assertNotIn(legacy, src, f"不應再出現舊的平行 parser：{legacy}")


class TestOutPath(unittest.TestCase):
    def test_plain_filename_keeps_output_dir_contract(self):
        self.assertEqual(bd._resolve_out("dashboard.html"),
                         bd.OUTPUT_DIR / "dashboard.html")

    def test_relative_path_with_directory_is_respected(self):
        """舊版會變成 output/output/x.html 後 traceback。"""
        self.assertEqual(bd._resolve_out("output/x.html"),
                        Path("output/x.html"))
        self.assertEqual(bd._resolve_out(str(Path("sub") / "x.html")),
                        Path("sub/x.html"))

    def test_absolute_path_is_respected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "absolute.html"
            self.assertEqual(bd._resolve_out(str(p)), p)

    def test_out_with_directory_writes_successfully(self):
        with tempfile.TemporaryDirectory() as td:
            src = _write_json(Path(td) / "in.json", _cli_v2_payload())
            dest = Path(td) / "nested" / "board.html"
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = bd.main(["--glob", src, "--out", str(dest)])
            self.assertEqual(code, 0)
            self.assertTrue(dest.exists())
            self.assertIn("window.JOBS", dest.read_text(encoding="utf-8"))

    def test_unwritable_out_returns_2_without_traceback(self):
        """路徑錯誤要給可讀訊息，不可丟 traceback 給求職者。"""
        with tempfile.TemporaryDirectory() as td:
            src = _write_json(Path(td) / "in.json", _cli_v2_payload())
            blocker = Path(td) / "blocker"
            blocker.write_text("x", encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(err):
                code = bd.main(["--glob", src,
                                "--out", str(blocker / "x.html")])
            text = err.getvalue()
            self.assertEqual(code, contract.EXIT_USAGE)
            self.assertIn("無法寫入", text)
            self.assertIn("請確認路徑與權限", text)
            self.assertNotIn("Traceback", text)
            self.assertTrue(blocker.is_file())

    def test_help_is_cp950_clean(self):
        proc = subprocess.run(
            [sys.executable, "build_dashboard.py", "--help"],
            cwd=ROOT, capture_output=True,
            env=dict(os.environ, PYTHONIOENCODING="cp950"),
        )
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode("utf-8", "replace"))
        self.assertNotIn(b"UnicodeEncodeError", proc.stderr)


class TestAccessibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as td:
            p = _write_json(Path(td) / "x.json", _cli_v2_payload())
            cls.jobs, cls.meta = bd.collect([p])
        cls.html = bd.build_html(cls.jobs, cls.meta)

    def test_semantic_landmarks_and_headings(self):
        for marker in ('<main class="wrap" id="main">', 'href="#main"',
                       "跳至主要內容", '<h2 class="sr-only">',
                       '<article class="card" role="listitem">',
                       '<h3 class="ttl">', 'role="list"', 'aria-label="職位清單"'):
            self.assertIn(marker, self.html, marker)

    def test_live_region_and_pressed_state(self):
        for marker in ('role="status" aria-live="polite"', 'aria-pressed="false"',
                       'aria-expanded="false"', 'aria-controls="list"'):
            self.assertIn(marker, self.html, marker)
        self.assertIn('setAttribute("aria-pressed"', self.html)
        self.assertIn('setAttribute("aria-expanded"', self.html)

    def test_chips_are_keyboard_reachable_buttons(self):
        self.assertIn('<button type="button" class="chip"', self.html)
        self.assertIn(':focus-visible{outline:3px solid', self.html)
        self.assertIn('class="btn" id="fontBtn"', self.html)

    def test_relative_font_sizes_survive_200_percent_zoom(self):
        for marker in ("--fs:16px", 'data-font="large"]{--fs:20px',
                       "calc(var(--fs) * 1.08)", "overflow-wrap:anywhere",
                       "@media(max-width:640px)", "flex-wrap:wrap"):
            self.assertIn(marker, self.html, marker)

    def test_embedded_data_is_escaped_and_v2_job_present(self):
        self.assertIn("window.JOBS = ", self.html)
        self.assertIn("文員", self.html)
        # 職位描述若含 </script>，內嵌 JSON 必須跳脫，否則會截斷整份 HTML
        escaped = bd._json_safely({"description": "</script><!--x"})
        self.assertNotIn("</script>", escaped)
        self.assertNotIn("<!--", escaped)


class TestEmptyState(unittest.TestCase):
    """兩種「空」：沒資料要教人先抓；有資料被篩選濾光才維持舊提示。

    2026-11-13 修：舊版一律顯示「試著放寬篩選」，空 output/ 的新手會去
    放寬根本不存在的篩選。此處全部離線，不發任何請求。
    """
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as td:
            p = _write_json(Path(td) / "x.json", _cli_v2_payload())
            cls.jobs, cls.meta = bd.collect([p])
            cls.empty_jobs, cls.empty_meta = bd.collect(
                [str(Path(td) / "_no_such_*.json")])
        cls.empty_html = bd.build_html(cls.empty_jobs, cls.empty_meta)
        cls.filled_html = bd.build_html(cls.jobs, cls.meta)

    def test_no_data_page_tells_user_to_fetch_first(self):
        self.assertIn("請先執行", self.empty_html)
        self.assertIn(bd.EMPTY_DATA_COMMAND, self.empty_html)
        self.assertIn("再重新產生看板", self.empty_html)
        self.assertNotIn("放寬篩選", self.empty_html)
        self.assertIn("window.JOBS = [];", self.empty_html)

    def test_filtered_out_page_keeps_original_hint(self):
        self.assertIn("沒有符合條件的職位，試著放寬篩選", self.filled_html)
        self.assertNotIn("請先執行", self.filled_html)
        for html in (self.empty_html, self.filled_html):
            self.assertNotIn("__EMPTY_", html)

    def test_render_branches_on_total_jobs(self):
        self.assertIn("JOBS.length === 0 ? EMPTY_DATA_HTML : EMPTY_FILTER_HTML",
                      self.empty_html)
        self.assertIn('const EMPTY_FILTER_HTML = "";', self.empty_html)
        self.assertIn("const EMPTY_DATA_HTML = ", self.empty_html)

    def test_injected_hint_is_a_valid_html_fragment(self):
        import re

        m = re.search(r"const EMPTY_DATA_HTML = (.*);", self.empty_html)
        frag = json.loads(m.group(1))
        self.assertIn("<code>", frag)
        self.assertIn("</code>", frag)
        self.assertIn('class="empty"', frag)

    def test_empty_page_keeps_accessibility_markers(self):
        for marker in ("--fs:16px", 'data-font="large"]{--fs:20px',
                       'class="btn" id="fontBtn"', ":focus-visible{outline:3px solid",
                       "跳至主要內容", 'role="list"', 'aria-live="polite"',
                       'aria-pressed="false"', "overflow-wrap:anywhere"):
            self.assertIn(marker, self.empty_html, marker)

    def test_console_warns_but_still_writes_empty_dashboard(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "empty.html"
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = bd.main(["--glob", str(Path(td) / "_no_such_*.json"),
                                "--out", str(dest)])
            self.assertEqual(code, contract.EXIT_OK)
            self.assertIn("空看板", out.getvalue())
            self.assertIn(bd.EMPTY_DATA_COMMAND, out.getvalue())
            self.assertIn("請先執行", dest.read_text(encoding="utf-8"))

    def test_empty_console_is_cp950_clean(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "empty.html"
            proc = subprocess.run(
                [sys.executable, "build_dashboard.py",
                 "--glob", "output/_no_such_*.json", "--out", str(dest)],
                cwd=ROOT, capture_output=True,
                env=dict(os.environ, PYTHONIOENCODING="cp950"))
            self.assertEqual(proc.returncode, 0,
                             proc.stderr.decode("cp950", "replace"))
            self.assertNotIn(b"UnicodeEncodeError", proc.stderr)
            self.assertNotIn(b"Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
