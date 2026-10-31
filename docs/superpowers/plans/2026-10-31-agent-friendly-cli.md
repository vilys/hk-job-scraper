# hkjobs Agent 友善 CLI — 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改動既有爬蟲與 `python main.py` 行為的前提下，新增可安裝的 `hkjobs` 命令（`search` / `sources` / `options`），提供 `--json` 單一封套輸出、嚴格 exit code、能力矩陣與字典查詢，並附 `AGENTS.md`。

**Architecture:** 薄外掛。新 `hkjobs/` 套件承載 CLI、契約、能力表與字典 adapter；`main.py` 只把 argparse 定義委派到 `hkjobs/args.py`。所有既有模組（`config.py`、`base_scraper.py`、`exporter.py`、`job_model.py`、`scrapers/*`）零改動。`--json` 模式不寫檔，輸出單一 JSON 物件到 stdout，日誌固定 stderr。

**Tech Stack:** Python 3.10+、argparse、json、dataclasses、importlib.resources、unittest、setuptools（扁平佈局）。

**設計文件:** `docs/superpowers/specs/2026-10-31-agent-friendly-cli-design.md`

---

## 前置條件

- 分支：`dev/agent-cli`（由使用者建立；本計畫所有 commit 都在此分支）。
- 工作目錄：repo 根目錄 `hk-job-scraper/`。
- Python：使用 `venv/`。已啟用時用 `python`，未啟用時用 `./venv/Scripts/python.exe`（Windows）。以下指令統一寫 `python`，執行前確認 `python -c "import requests"` 不報錯。
- 既有 32 個測試必須保持全綠：`python -m unittest discover -s tests`。

## 檔案地圖

| 檔案 | 動作 | 責任 |
|---|---|---|
| `hkjobs/__init__.py` | 新增 | `__version__ = "0.1.0"` |
| `hkjobs/args.py` | 新增 | `search` 參數唯一來源（`main.py` 亦使用） |
| `hkjobs/contract.py` | 新增 | 封套、exit code、JSON 輸出、UTF-8 |
| `hkjobs/capabilities.py` | 新增 | 12 站能力表（`sources` 的資料源） |
| `hkjobs/options.py` | 新增 | 18 個字典 → 正規化條目（`options` 的資料源） |
| `hkjobs/cli.py` | 新增 | 子命令分派與三個 handler |
| `hkjobs/__main__.py` | 新增 | `python -m hkjobs` |
| `main.py` | 修改（僅 `build_argparser`） | 委派到 `hkjobs.args` |
| `pyproject.toml` | 新增 | 打包與 `hkjobs` console script |
| `tests/test_cli_contract.py` | 新增 | 契約測試（零網路） |
| `AGENTS.md` | 新增 | agent 操作手冊 |
| `README.md` | 修改 | agent 章節、結構樹、矩陣註記 |
| `.gitignore` | 修改 | 打包產物 |

---

### Task 1: 抽出共用參數定義

**Files:**
- Create: `hkjobs/__init__.py`
- Create: `hkjobs/args.py`
- Modify: `main.py:40-101`（`build_argparser` 整段）
- Test: `tests/test_cli_contract.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_cli_contract.py`：

```python
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
                "-h", "--source", "--keyword", "--pages", "--output", "--detail",
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
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python -m unittest tests.test_cli_contract -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hkjobs'`

- [ ] **Step 3: 建立 `hkjobs/__init__.py`**

```python
"""hkjobs — agent 友善的香港職位搜尋 CLI。"""

__version__ = "0.1.0"
```

- [ ] **Step 4: 建立 `hkjobs/args.py`**

把 `main.py` 現有 `build_argparser` 的旗標逐字搬過來（help 文字、預設值、順序都不改）：

```python
"""hkjobs 命令列參數定義（main.py 與 hkjobs CLI 共用，避免兩套 help 漂移）。"""
from __future__ import annotations

import argparse


def add_search_arguments(
    p: argparse.ArgumentParser, *, include_output_flags: bool = True
) -> None:
    """加入搜尋旗標。文字與預設值必須與舊 main.py 完全一致。"""
    p.add_argument("--source", default="moovup",
                   help="爬蟲來源：moovup | gov_hk | jobsdb | linkedin | indeed | "
                        "recruit | jobmarket | foundit | efc | liepin | zhipin | "
                        "offertoday | all")
    p.add_argument("--keyword", default="",
                   help="搜尋關鍵字（留空 = 不限定關鍵字，僅依地區/類別瀏覽；"
                        "gov_hk 支援，moovup 建議仍給關鍵字）")
    p.add_argument("--pages", type=int, default=3, help="最大翻頁數")
    if include_output_flags:
        p.add_argument("--output", default="json",
                       choices=["json", "csv", "both"], help="輸出格式")
    p.add_argument("--detail", action="store_true",
                   help="同時抓取職位詳情（職責/要求/發佈時間/刊登日期）")
    p.add_argument("--fill-location", action="store_true",
                   help="列表階段補地區：僅 recruit 需要並支援（該站列表頁沒有地區欄）。"
                        "會對每筆多打 1 支輕量 AJAX 請求（25 筆/頁 → 25 支，含節流），故預設關閉。"
                        "若只用 --district 篩選單一地區，recruit 會零請求直接回填，不必開此選項。"
                        "其餘來源（列表已含地區）傳入會警告並忽略。")
    if include_output_flags:
        p.add_argument("--outfile", default=None,
                       help="自訂輸出檔名（不含副檔名）")
    p.add_argument("--district", default=None,
                   help="地區過濾（可逗號分隔多個，JobsDB 僅取第一個）："
                        "gov_hk 用數字 ID / 中文（如 屯門=188）；"
                        "JobsDB 用中文名或 slug（如 荃灣 | tsuen-wan，見 scrapers/jobsdb_districts.json）；"
                        "moovup 用 shortCode；"
                        "LinkedIn 用自由文字（如 Hong Kong | Tsuen Wan，預設 Hong Kong）；"
                        "offertoday 用中文/英文區名或子區名（如 元朗 | 天水圍 | Yuen Long）。"
                        "各站體系獨立，不可混用。")
    p.add_argument("--category", default=None,
                   help="工作種類 / 職能過濾："
                        "gov_hk 用中文名（如 會計 | 文員 | 司機 | 清潔）；"
                        "JobsDB 用中文名或英文或 slug（如 資訊及通訊科技 | Information & Communication "
                        "Technology，見 scrapers/jobsdb_classifications.json）；"
                        "offertoday 用中文/英文職能名（如 資訊科技 | 開發者，見 scrapers/offertoday_categories.json）。"
                        "兩站字典獨立。")
    p.add_argument("--industry", default=None,
                   help="行業過濾：僅 gov_hk 與 JobMarket 與 offertoday 支援"
                        "（gov_hk / JobMarket 用中文名，如 飲食業 | 建造業 | 零售業 | 金融業；"
                        "offertoday 用中英文行業名，如 銀行 | 財務/金融，見 scrapers/offertoday_industries.json；"
                        "注意大類會自動展開為細類）。"
                        "JobsDB 無獨立行業維度（職能分類已涵蓋），傳入會被忽略並提示。")
    p.add_argument("--sort", default=None,
                   choices=["post_dt_desc", "post_dt_asc",
                            "salary_desc", "salary_asc",
                            "yr_exp_asc", "yr_exp_desc",
                            "edu_lvl_asc", "edu_lvl_desc"],
                   help="排序：gov_hk 全選項支援（post_dt_desc=刊登日期新→舊 | "
                        "post_dt_asc=舊→新 | salary_desc/asc=月薪多/少 | "
                        "yr_exp_asc/desc=經驗少/多 | edu_lvl_asc/desc=學歷低/高）。"
                        "JobsDB 與 LinkedIn 僅支援 post_dt_desc（JobsDB 對應 sortmode=ListedDate；"
                        "LinkedIn 對應 sortBy=DD，皆為新→舊），其餘選項為 gov_hk 專有，"
                        "JobsDB / LinkedIn 傳入會警告並回退網站預設排序。"
                        "設 --days 時若未指定 --sort，自動套用 post_dt_desc。")
    p.add_argument("--days", type=int, default=None,
                   help="只保留最近 N 天內刊登的職位："
                        "gov_hk 自動抓詳情取日期；JobsDB 與 LinkedIn 直接用列表相對刊登日過濾（不抓詳情）；"
                        "moovup 不支援（傳入會警告並忽略）；"
                        "offertoday 支援：送站方 publishTime 參數 + 客戶端再篩"
                        "（只有「on MM-DD」格式能算天數，其餘視為過舊淘汰）。"
                        "預設按刊登日期由近至遠排序。")


def build_search_argparser(
    *, description: str, prog: str | None = None
) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description, prog=prog)
    add_search_arguments(p)
    return p


def add_machine_arguments(p: argparse.ArgumentParser) -> None:
    """hkjobs 專屬輸出旗標（舊 main.py 不加入）。"""
    p.add_argument("--json", action="store_true",
                   help="機器模式：stdout 輸出單一 JSON 封套、不寫檔；日誌走 stderr（預設 WARNING）")
    p.add_argument("--out", default=None, metavar="PATH",
                   help="顯式寫檔：.csv 寫職位 CSV（UTF-8 BOM）；其他副檔名寫 JSON"
                        "（--json 時寫完整封套，否則寫職位陣列）")
    p.add_argument("-q", "--quiet", action="store_true", help="日誌只保留 ERROR")
```

- [ ] **Step 5: 修改 `main.py`**

把 `build_argparser` 整段（原 L40–L101）換成：

```python
def build_argparser() -> argparse.ArgumentParser:
    """向後相容的入口；定義集中在 hkjobs.args（與 hkjobs CLI 共用）。"""
    return build_search_argparser(description="香港求職網站自動搜尋程式")
```

在檔案上方 import 區加入：

```python
from hkjobs.args import build_search_argparser  # noqa: E402
```

（放在 `from scrapers import SCRAPERS` 之後，維持現有 `# noqa: E402` 風格。）

- [ ] **Step 6: 執行測試，確認通過**

Run: `python -m unittest tests.test_cli_contract -v`
Expected: 3 tests PASS

Run: `python -m unittest discover -s tests`
Expected: 既有 32 + 3 = 35 tests PASS

Run: `python main.py --help`
Expected: 顯示與改動前相同的參數清單（含 `--source`、`--days`）

- [ ] **Step 7: Commit**

```bash
git add hkjobs/__init__.py hkjobs/args.py main.py tests/test_cli_contract.py
git commit -m "refactor(cli): 抽出共用參數定義，main.py 改為委派 hkjobs.args"
```

---

### Task 2: 契約基礎（封套 / exit code / UTF-8）

**Files:**
- Create: `hkjobs/contract.py`
- Test: `tests/test_cli_contract.py`（追加）

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_cli_contract.py` 追加：

```python
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
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python -m unittest tests.test_cli_contract.TestContract -v`
Expected: FAIL — `ImportError: cannot import name 'contract' from 'hkjobs'`

- [ ] **Step 3: 實作 `hkjobs/contract.py`**

```python
"""JSON 封套、exit code 與 stdout 規則（agent 契約的唯一實作）。"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from job_model import JobRecord

SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_USAGE = 2
EXIT_PARTIAL = 3
EXIT_ALL_FAILED = 4
EXIT_EMPTY = 5

_ERROR_CODES = {
    EXIT_PARTIAL: "partial_failure",
    EXIT_ALL_FAILED: "all_sources_failed",
    EXIT_EMPTY: "no_results",
    EXIT_UNEXPECTED: "unexpected",
}


@dataclass
class SourceResult:
    name: str
    status: str                       # ok | failed | skipped
    jobs: list[JobRecord] = field(default_factory=list)
    error: str | None = None


def configure_io() -> None:
    """統一 stdout/stderr 為 UTF-8，避免 Windows cp950 輸出中文 JSON 失敗。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, OSError):
            pass


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def exit_code_for(results: list[SourceResult]) -> int:
    ok = [r for r in results if r.status == "ok"]
    failed = [r for r in results if r.status == "failed"]
    if failed and not ok:
        return EXIT_ALL_FAILED
    if failed:
        return EXIT_PARTIAL
    total = sum(len(r.jobs) for r in ok)
    return EXIT_OK if total else EXIT_EMPTY


def search_payload(query: dict, results: list[SourceResult], code: int) -> dict:
    jobs = [j.to_dict() for r in results if r.status == "ok" for j in r.jobs]
    summary = {
        "total": len(jobs),
        "withSalary": sum(1 for j in jobs if j.get("salary")),
        "sources": [
            {"name": r.name, "status": r.status, "jobs": len(r.jobs), "error": r.error}
            for r in results
        ],
    }
    if code == EXIT_OK:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "command": "search",
            "generatedAt": now_iso(),
            "query": query,
            "summary": summary,
            "jobs": jobs,
        }

    failed = [r.name for r in results if r.status == "failed"]
    messages = {
        EXIT_PARTIAL: f"部分來源失敗：{', '.join(failed)}",
        EXIT_ALL_FAILED: f"所有來源均失敗：{', '.join(failed)}",
        EXIT_EMPTY: "查詢成功但 0 筆結果",
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "command": "search",
        "generatedAt": now_iso(),
        "error": {
            "code": _ERROR_CODES.get(code, "unexpected"),
            "message": messages.get(code, "未知錯誤"),
        },
        "summary": summary,
        "jobs": jobs,
    }


def emit_json(payload: dict) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python -m unittest tests.test_cli_contract.TestContract -v`
Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add hkjobs/contract.py tests/test_cli_contract.py
git commit -m "feat(cli): 新增 JSON 封套與嚴格 exit code 契約"
```

---

### Task 3: 能力表（12 站）

**Files:**
- Create: `hkjobs/capabilities.py`
- Test: `tests/test_cli_contract.py`（追加）

- [ ] **Step 1: 寫失敗測試**

追加：

```python
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
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python -m unittest tests.test_cli_contract.TestCapabilities -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hkjobs.capabilities'`

- [ ] **Step 3: 實作 `hkjobs/capabilities.py`**

```python
"""12 站能力矩陣（`hkjobs sources` 的單一資料源）。

可從 scraper class 讀到的欄位（enabled / needs_browser）由契約測試交叉核對；
站方特有資訊（days_mode、sort_values、每頁筆數、needs_chrome）以 README
「各站功能支援矩陣」為準。改動任何據點行為時，必須同步更新本表。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config import delay_for

ALL_SORT_VALUES: tuple[str, ...] = (
    "post_dt_desc", "post_dt_asc",
    "salary_desc", "salary_asc",
    "yr_exp_desc", "yr_exp_asc",
    "edu_lvl_desc", "edu_lvl_asc",
)

_ALL_SORTS = ALL_SORT_VALUES


@dataclass(frozen=True)
class SourceInfo:
    name: str
    label: str
    enabled: bool
    needs_browser: bool
    needs_chrome: bool
    per_page: int
    keyword_required: bool
    days_mode: str                    # server | list | detail | approx | none
    sort_values: tuple[str, ...] = ()
    supports: dict[str, bool] = field(default_factory=dict)
    request_delay: float = 0.0
    notes: str = ""


SOURCES: dict[str, SourceInfo] = {
    "moovup": SourceInfo(
        name="moovup", label="好工速遞", enabled=True,
        needs_browser=True, needs_chrome=False, per_page=12,
        keyword_required=False, days_mode="none", sort_values=(),
        supports={"district": True, "category": False, "industry": False,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("moovup"),
        notes="Cloudflare Turnstile 需 Playwright；列表無公司/日期，--detail 才補；不支援 --days。",
    ),
    "gov_hk": SourceInfo(
        name="gov_hk", label="勞工處", enabled=True,
        needs_browser=False, needs_chrome=False, per_page=20,
        keyword_required=False, days_mode="server", sort_values=_ALL_SORTS,
        supports={"district": True, "category": True, "industry": True,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("gov_hk"),
        notes="ASP.NET SSR；--days 走站方 postedDtFr/To；--sort 8 值全支援。",
    ),
    "jobsdb": SourceInfo(
        name="jobsdb", label="JobsDB", enabled=True,
        needs_browser=True, needs_chrome=False, per_page=20,
        keyword_required=False, days_mode="server", sort_values=("post_dt_desc",),
        supports={"district": True, "category": True, "industry": False,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("jobsdb"),
        notes="列表含相對日期；--days 走站方 daterange（只吃 1/3/7/14/31，本模組向上取整）。",
    ),
    "linkedin": SourceInfo(
        name="linkedin", label="LinkedIn", enabled=True,
        needs_browser=False, needs_chrome=False, per_page=58,
        keyword_required=False, days_mode="server", sort_values=("post_dt_desc",),
        supports={"district": True, "category": False, "industry": False,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("linkedin"),
        notes="訪客模式；首頁 ~58、續頁 ~10；深翻頁可設 LINKEDIN_LI_AT。",
    ),
    "indeed": SourceInfo(
        name="indeed", label="Indeed", enabled=False,
        needs_browser=True, needs_chrome=True, per_page=16,
        keyword_required=True, days_mode="server", sort_values=(),
        supports={"district": True, "category": False, "industry": False,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("indeed"),
        notes="停用（2026-09-11 強制登入牆）；--keyword 必給；需本機 Chrome。",
    ),
    "recruit": SourceInfo(
        name="recruit", label="Recruit", enabled=True,
        needs_browser=True, needs_chrome=False, per_page=25,
        keyword_required=False, days_mode="list", sort_values=_ALL_SORTS,
        supports={"district": True, "category": True, "industry": False,
                  "detail": True, "fillLocation": True},
        request_delay=delay_for("recruit"),
        notes="列表無地區欄；單區篩選零請求回填，多區/未篩選需 --fill-location；asc 排序以站方 desc 近似並警告。",
    ),
    "jobmarket": SourceInfo(
        name="jobmarket", label="JobMarket 求職廣場", enabled=True,
        needs_browser=False, needs_chrome=False, per_page=20,
        keyword_required=False, days_mode="list", sort_values=(),
        supports={"district": True, "category": True, "industry": True,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("jobmarket"),
        notes="純 requests；站方預設大致新→舊（頂部推廣／置頂區塊不排序，偏舊故不影響提早停翻）；無 --sort 參數。",
    ),
    "foundit": SourceInfo(
        name="foundit", label="foundit", enabled=True,
        needs_browser=True, needs_chrome=True, per_page=20,
        keyword_required=False, days_mode="list", sort_values=(),
        supports={"district": True, "category": False, "industry": False,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("foundit"),
        notes="需本機 Google Chrome（內建 Chromium 被 WAF 403）；SEO 瀏覽頁固定排序。",
    ),
    "efc": SourceInfo(
        name="efc", label="eFinancialCareers", enabled=True,
        needs_browser=False, needs_chrome=False, per_page=50,
        keyword_required=False, days_mode="list", sort_values=(),
        supports={"district": True, "category": False, "industry": False,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("efc"),
        notes="純 JSON API；地區僅 3 大區（細分區站方回 0 筆）。",
    ),
    "liepin": SourceInfo(
        name="liepin", label="獵聘", enabled=False,
        needs_browser=True, needs_chrome=True, per_page=40,
        keyword_required=False, days_mode="approx", sort_values=(),
        supports={"district": True, "category": False, "industry": False,
                  "detail": False, "fillLocation": False},
        request_delay=delay_for("liepin"),
        notes="停用；近 N 天以刷新日近似；詳情受驗證碼保護；連 6–7 支請求即觸發 IP 驗證碼。",
    ),
    "zhipin": SourceInfo(
        name="zhipin", label="BOSS直聘", enabled=False,
        needs_browser=True, needs_chrome=True, per_page=0,
        keyword_required=False, days_mode="none", sort_values=(),
        supports={"district": False, "category": False, "industry": False,
                  "detail": False, "fillLocation": False},
        request_delay=delay_for("zhipin"),
        notes="停用；香港不在站方城市體系（港澳台專區 0 張且需登入）。",
    ),
    "offertoday": SourceInfo(
        name="offertoday", label="OfferToday", enabled=True,
        needs_browser=False, needs_chrome=False, per_page=10,
        keyword_required=False, days_mode="server", sort_values=(),
        supports={"district": True, "category": True, "industry": True,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("offertoday"),
        notes="免瀏覽器純 API；每頁上限 10；--days 送 publishTime 並客戶端再篩（只認 on MM-DD）。",
    ),
}
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python -m unittest tests.test_cli_contract.TestCapabilities -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add hkjobs/capabilities.py tests/test_cli_contract.py
git commit -m "feat(cli): 新增 12 站能力矩陣並以契約測試鎖住"
```

---

### Task 4: 字典查詢 adapter

**Files:**
- Create: `hkjobs/options.py`
- Test: `tests/test_cli_contract.py`（追加）

- [ ] **Step 1: 寫失敗測試**

追加：

```python
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
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python -m unittest tests.test_cli_contract.TestOptions -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hkjobs.options'`

- [ ] **Step 3: 實作 `hkjobs/options.py`**

```python
"""把 scrapers/*.json 的 5 種結構正規化為統一條目（`hkjobs options` 的資料源）。

⚠️ 只做形狀轉換，不修改字典、不決定值域：值域一律以 JSON 檔實際內容為準。
搜尋時的正規化仍由各站爬蟲自己負責（本模組不參與 --district 解析）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Callable

from hkjobs.capabilities import SOURCES


@dataclass(frozen=True)
class OptionEntry:
    id: str | None
    name: str
    aliases: tuple[str, ...] = ()
    parent_id: str | None = None


def _read(filename: str) -> Any:
    return json.loads((files("scrapers") / filename).read_text(encoding="utf-8"))


def _uniq(items) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return tuple(out)


def _simple_pairs(filename: str):
    return [
        OptionEntry(id=str(r["id"]), name=r.get("name", ""))
        for r in _read(filename)
    ]


def _moovup_district():
    return [
        OptionEntry(
            id=r.get("shortCode"),
            name=r.get("zh", ""),
            aliases=_uniq([r.get("en", ""), r.get("shortCode", "")]),
        )
        for r in _read("moovup_districts.json")
    ]


def _jobsdb_district():
    return [
        OptionEntry(id=r["slug"], name=r["zh"], aliases=_uniq([r["slug"]]))
        for r in _read("jobsdb_districts.json")
    ]


def _jobsdb_category():
    return [
        OptionEntry(
            id=r["slug"],
            name=r.get("zh") or r["name"],
            aliases=_uniq([r.get("name", ""), r["slug"]]),
        )
        for r in _read("jobsdb_classifications.json")
    ]


def _linkedin_district():
    data = _read("linkedin_geo.json")
    reverse: dict[str, list[str]] = {}
    for alias, district in (data.get("aliases") or {}).items():
        reverse.setdefault(district, []).append(alias)
    return [
        OptionEntry(
            id=str(v.get("geoUrn") or ""),
            name=zh_name,
            aliases=_uniq([v.get("en", ""), v.get("displayName", ""),
                           *reverse.get(zh_name, [])]),
        )
        for zh_name, v in (data.get("districts") or {}).items()
    ]


def _recruit_district():
    return [
        OptionEntry(
            id=str(r["id"]),
            name=r.get("zh") or r.get("name", ""),
            aliases=_uniq([*(r.get("aliases") or []), r.get("zh", ""), r.get("name", "")]),
        )
        for r in _read("recruit_districts.json")
    ]


def _recruit_category():
    return [
        OptionEntry(
            id=str(r.get("cat_id") or r["id"]),
            name=r.get("name", ""),
            aliases=_uniq([*(r.get("aliases") or []), r.get("zh", "")]),
        )
        for r in _read("recruit_categories.json")
    ]


def _jobmarket_dimension(filename: str):
    return [
        OptionEntry(
            id=str(r["id"]),
            name=r.get("zh") or r.get("name", ""),
            aliases=_uniq([*(r.get("aliases") or []), r.get("name", "")]),
        )
        for r in _read(filename)
    ]


def _foundit_district():
    return [
        OptionEntry(id=r["id"], name=r.get("name", ""),
                    aliases=_uniq(r.get("aliases") or []))
        for r in _read("foundit_locations.json")["locations"]
    ]


def _efc_district():
    return [
        OptionEntry(
            id=r["id"],
            name=r.get("name_zh") or r.get("name", ""),
            aliases=_uniq([r.get("name", ""), *(r.get("aliases") or [])]),
        )
        for r in _read("efc_geo.json")["locations"]
    ]


def _liepin_district():
    data = _read("liepin_areas.json")
    return [
        OptionEntry(
            id=None,
            name=v.get("zh_hant") or key,
            aliases=_uniq([key, v.get("en", ""), *(v.get("aliases") or [])]),
        )
        for key, v in (data.get("districts") or {}).items()
    ]


def _offertoday_dimension(filename: str, list_key: str):
    out: list[OptionEntry] = []
    for row in _read(filename)[list_key]:
        parent_id = str(row["id"])
        out.append(OptionEntry(
            id=parent_id,
            name=row.get("name", ""),
            aliases=_uniq([row.get("name_en", "")]),
        ))
        for child in row.get("children") or []:
            out.append(OptionEntry(
                id=str(child["id"]),
                name=child.get("name", ""),
                aliases=_uniq([child.get("name_en", "")]),
                parent_id=parent_id,
            ))
    return out


_LOADERS: dict[tuple[str, str], Callable[[], list[OptionEntry]]] = {
    ("moovup", "district"): _moovup_district,
    ("gov_hk", "district"): lambda: _simple_pairs("gov_hk_districts.json"),
    ("gov_hk", "category"): lambda: _simple_pairs("gov_hk_categories.json"),
    ("gov_hk", "industry"): lambda: _simple_pairs("gov_hk_industries.json"),
    ("jobsdb", "district"): _jobsdb_district,
    ("jobsdb", "category"): _jobsdb_category,
    ("linkedin", "district"): _linkedin_district,
    ("recruit", "district"): _recruit_district,
    ("recruit", "category"): _recruit_category,
    ("jobmarket", "district"): lambda: _jobmarket_dimension("jobmarket_districts.json"),
    ("jobmarket", "category"): lambda: _jobmarket_dimension("jobmarket_categories.json"),
    ("jobmarket", "industry"): lambda: _jobmarket_dimension("jobmarket_industries.json"),
    ("foundit", "district"): _foundit_district,
    ("efc", "district"): _efc_district,
    ("liepin", "district"): _liepin_district,
    ("offertoday", "district"): lambda: _offertoday_dimension("offertoday_areas.json", "districts"),
    ("offertoday", "category"): lambda: _offertoday_dimension("offertoday_categories.json", "categories"),
    ("offertoday", "industry"): lambda: _offertoday_dimension("offertoday_industries.json", "industries"),
}

_DIM_META: dict[tuple[str, str], tuple[str, list[str]]] = {
    ("moovup", "district"): ("single", ["zh", "en", "shortCode"]),
    ("gov_hk", "district"): ("single", ["id", "name"]),
    ("gov_hk", "category"): ("single", ["id", "name"]),
    ("gov_hk", "industry"): ("single", ["id", "name"]),
    ("jobsdb", "district"): ("single", ["zh", "slug"]),
    ("jobsdb", "category"): ("single", ["zh", "en", "slug"]),
    ("linkedin", "district"): ("single", ["zh", "en", "alias"]),
    ("recruit", "district"): ("multi", ["id", "en", "zh", "alias"]),
    ("recruit", "category"): ("single", ["id", "en", "zh", "alias"]),
    ("jobmarket", "district"): ("multi", ["id", "zh", "en", "alias"]),
    ("jobmarket", "category"): ("single", ["id", "zh", "en", "alias"]),
    ("jobmarket", "industry"): ("single", ["id", "zh", "en", "alias"]),
    ("foundit", "district"): ("single", ["slug", "en", "zh"]),
    ("efc", "district"): ("single", ["en", "zh"]),
    ("liepin", "district"): ("single", ["zh", "en", "alias"]),
    ("offertoday", "district"): ("multi", ["id", "zh", "en"]),
    ("offertoday", "category"): ("single", ["id", "zh", "en"]),
    ("offertoday", "industry"): ("single", ["id", "zh", "en"]),
}

_FREE_DIMENSIONS = {("indeed", "district")}


def dimension_kinds() -> dict[str, str]:
    """給測試／文件用：列出每個 (source, dimension) 的 kind。"""
    return {f"{s}.{d}": meta[0] for (s, d), meta in _DIM_META.items()}


def load_dimension(source: str, dimension: str) -> dict | None:
    """回傳正規化維度；不支援回 None。"""
    info = SOURCES.get(source)
    if info is None:
        return None
    if dimension == "sort":
        if not info.sort_values:
            return None
        return {"kind": "enum", "values": list(info.sort_values)}
    if not info.supports.get(dimension, False):
        return None
    if (source, dimension) in _FREE_DIMENSIONS:
        return {"kind": "free", "accepts": ["free_text"], "count": 0, "values": []}

    entries = _LOADERS[(source, dimension)]()
    kind, accepts = _DIM_META[(source, dimension)]
    return {
        "kind": kind,
        "accepts": accepts,
        "count": len(entries),
        "values": [
            {
                "id": e.id,
                "name": e.name,
                "aliases": list(e.aliases),
                "parentId": e.parent_id,
            }
            for e in entries
        ],
    }
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python -m unittest tests.test_cli_contract.TestOptions -v`
Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add hkjobs/options.py tests/test_cli_contract.py
git commit -m "feat(cli): 新增字典查詢 adapter 與 options 資料形狀"
```

---

### Task 5: CLI 骨架 + `sources` / `options`

**Files:**
- Create: `hkjobs/cli.py`
- Create: `hkjobs/__main__.py`
- Test: `tests/test_cli_contract.py`（追加）

- [ ] **Step 1: 寫失敗測試**

追加：

```python
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
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python -m unittest tests.test_cli_contract.TestSourcesCommand -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hkjobs.cli'`

- [ ] **Step 3: 實作 `hkjobs/cli.py`（本任務只含 sources / options）**

```python
"""hkjobs 命令列入口（agent 友善）。"""
from __future__ import annotations

import argparse
import logging
import sys

from hkjobs import __version__
from hkjobs.capabilities import SOURCES
from hkjobs.contract import (
    EXIT_OK,
    EXIT_UNEXPECTED,
    EXIT_USAGE,
    SCHEMA_VERSION,
    configure_io,
    emit_json,
    now_iso,
)
from hkjobs.options import load_dimension

logger = logging.getLogger("hkjobs")


def _setup_logging(*, quiet: bool, json_mode: bool) -> None:
    level = logging.ERROR if quiet else (logging.WARNING if json_mode else logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
        force=True,
    )


def _usage_error(message: str) -> int:
    print(f"hkjobs: error: {message}", file=sys.stderr)
    return EXIT_USAGE


def _sources_rows() -> list[dict]:
    rows: list[dict] = []
    for name, info in SOURCES.items():
        counts = {}
        for dim in ("district", "category", "industry"):
            loaded = load_dimension(name, dim)
            counts[dim] = loaded["count"] if loaded and loaded.get("kind") != "free" else 0
        rows.append({
            "name": info.name,
            "label": info.label,
            "enabled": info.enabled,
            "needsBrowser": info.needs_browser,
            "needsChrome": info.needs_chrome,
            "perPage": info.per_page,
            "keywordRequired": info.keyword_required,
            "daysMode": info.days_mode,
            "sortValues": list(info.sort_values),
            "supports": dict(info.supports),
            "valueCounts": counts,
            "requestDelaySeconds": info.request_delay,
            "notes": info.notes,
        })
    return rows


def _print_sources_table(rows: list[dict]) -> None:
    print(f"{'來源':<14}{'代號':<12}{'啟用':<6}{'瀏覽器':<8}{'每頁':>5}  支援維度 / 近N天")
    print("-" * 86)
    for r in rows:
        dims = [k for k in ("district", "category", "industry") if r["supports"][k]]
        print(
            f"{r['label']:<14}{r['name']:<12}{'是' if r['enabled'] else '否':<6}"
            f"{'需' if r['needsBrowser'] else '—':<8}{r['perPage']:>5}  "
            f"{'/'.join(dims) or '—'} / {r['daysMode']}"
        )
    print("\n提示：加 --json 取得完整矩陣；有效值用 hkjobs options --source <站> --json")


def _print_options(payload: dict) -> None:
    for dim, data in payload["dimensions"].items():
        print(f"\n## {dim}")
        if data is None:
            print("  （此據點不支援）")
            continue
        if data["kind"] == "enum":
            for value in data["values"]:
                print(f"  {value}")
            continue
        if data["kind"] == "free":
            print("  （自由文字，無字典）")
            continue
        for entry in data["values"]:
            prefix = "    ↳ " if entry["parentId"] else "  "
            extra = f"  ← {', '.join(entry['aliases'])}" if entry["aliases"] else ""
            print(f"{prefix}{entry['name']} [{entry['id']}]{extra}")


def cmd_sources(args: argparse.Namespace) -> int:
    _setup_logging(quiet=False, json_mode=args.json)
    rows = _sources_rows()
    if args.json:
        emit_json({
            "schemaVersion": SCHEMA_VERSION,
            "command": "sources",
            "generatedAt": now_iso(),
            "sources": rows,
            "presets": {"all": [n for n, i in SOURCES.items() if i.enabled]},
        })
    else:
        _print_sources_table(rows)
    return EXIT_OK


def cmd_options(args: argparse.Namespace) -> int:
    _setup_logging(quiet=False, json_mode=args.json)
    if args.source not in SOURCES:
        return _usage_error(
            f"未知來源：{args.source}（可選：{', '.join(SOURCES)}；不接受 all）"
        )
    dims = [args.dimension] if args.dimension else [
        "district", "category", "industry", "sort",
    ]
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "command": "options",
        "source": args.source,
        "generatedAt": now_iso(),
        "dimensions": {dim: load_dimension(args.source, dim) for dim in dims},
    }
    if args.json:
        emit_json(payload)
    else:
        _print_options(payload)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hkjobs", description="香港職位搜尋 CLI（agent 友善）"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sources = sub.add_parser("sources", help="列出據點能力矩陣")
    p_sources.add_argument("--json", action="store_true", help="輸出 JSON")
    p_sources.set_defaults(handler=cmd_sources)

    p_options = sub.add_parser("options", help="列出據點的有效參數值（地區/職能/行業/排序）")
    p_options.add_argument("--source", required=True, help="據點名稱（不接受 all）")
    p_options.add_argument(
        "--dimension",
        choices=["district", "category", "industry", "sort"],
        default=None,
        help="只列某一維度；預設全部",
    )
    p_options.add_argument("--json", action="store_true", help="輸出 JSON")
    p_options.set_defaults(handler=cmd_options)

    return parser


def main(argv: list[str] | None = None) -> int:
    configure_io()
    raw = list(sys.argv[1:] if argv is None else argv)
    want_json = "--json" in raw
    try:
        args = build_parser().parse_args(raw)
        return int(args.handler(args))
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception as exc:  # noqa: BLE001
        logger.exception("未預期錯誤：%s", exc)
        if want_json:
            command = raw[0] if raw and raw[0] in {"search", "sources", "options"} else None
            emit_json({
                "schemaVersion": SCHEMA_VERSION,
                "command": command,
                "error": {"code": "unexpected", "message": str(exc)},
            })
        return EXIT_UNEXPECTED
```

建立 `hkjobs/__main__.py`：

```python
"""python -m hkjobs。"""
import sys

from hkjobs.cli import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python -m unittest tests.test_cli_contract.TestSourcesCommand tests.test_cli_contract.TestOptionsCommand -v`
Expected: 5 tests PASS

Run: `python -m hkjobs sources --json`
Expected: 印出 12 站 JSON，exit 0

- [ ] **Step 5: Commit**

```bash
git add hkjobs/cli.py hkjobs/__main__.py tests/test_cli_contract.py
git commit -m "feat(cli): 新增 hkjobs 骨架與 sources/options 子命令"
```

---

### Task 6: `search` 子命令（JSON 封套 / exit code / --out）

**Files:**
- Modify: `hkjobs/cli.py`（加入 search 相關 import、handler、子命令）
- Test: `tests/test_cli_contract.py`（追加）

- [ ] **Step 1: 寫失敗測試**

追加：

```python
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
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python -m unittest tests.test_cli_contract.TestSearchCommand -v`
Expected: FAIL — `AttributeError: module 'hkjobs.cli' has no attribute 'cmd_search'`

- [ ] **Step 3: 在 `hkjobs/cli.py` 加入 search**

import 區加入：

```python
from pathlib import Path

from exporter import export_csv
from hkjobs.args import add_machine_arguments, add_search_arguments
from hkjobs.contract import (
    EXIT_ALL_FAILED,
    EXIT_EMPTY,
    EXIT_PARTIAL,
    SourceResult,
    exit_code_for,
    search_payload,
)
from scrapers import SCRAPERS
```

在 `cmd_sources` 之後加入：

```python
def _run_one(source: str, args: argparse.Namespace) -> SourceResult:
    logger.info("==== 開始爬取來源：%s ====", source)
    scraper = None
    try:
        scraper = SCRAPERS[source]()
        jobs = scraper.scrape_all(
            keyword=args.keyword,
            max_pages=args.pages,
            district=args.district,
            category=args.category,
            industry=args.industry,
            sort=args.sort,
            days=args.days,
            with_detail=args.detail,
            fill_location=args.fill_location,
            output=None,
            fmt="json",
        )
        logger.info("[%s] 取得 %d 筆職位。", source, len(jobs))
        return SourceResult(source, "ok", jobs)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] 執行失敗：%s", source, exc)
        return SourceResult(source, "failed", [], str(exc))
    finally:
        if scraper is not None:
            scraper.close()


def _print_human(results: list[SourceResult], code: int) -> None:
    print(f"{'來源':<14}{'筆數':>6}  狀態")
    for result in results:
        label = {"ok": "ok", "failed": "失敗", "skipped": "略過"}[result.status]
        extra = f"（{result.error}）" if result.error else ""
        print(f"{result.name:<14}{len(result.jobs):>6}  {label}{extra}")
    total = sum(len(r.jobs) for r in results if r.status == "ok")
    with_salary = sum(
        1 for r in results if r.status == "ok" for j in r.jobs if j.salary
    )
    print(f"\n總計：{total} 筆（{with_salary} 筆有薪資）")
    if code == EXIT_EMPTY:
        print("提示：0 筆結果。可放寬 --days、換 --keyword，或先跑 hkjobs sources 確認支援度。")
    elif code in (EXIT_PARTIAL, EXIT_ALL_FAILED):
        print("提示：有來源失敗。可稍後重試，或先跑 hkjobs sources 確認據點狀態。")
    print("提示：加 --json 取得機器可讀 JSON；加 --out result.json 儲存結果。")


def _write_out(path: Path, payload: dict, results: list[SourceResult], *, json_mode: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".csv":
        jobs = [j for r in results if r.status == "ok" for j in r.jobs]
        export_csv(jobs, str(path), incremental=False)
        return
    data = payload if json_mode else payload["jobs"]
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def cmd_search(args: argparse.Namespace) -> int:
    _setup_logging(quiet=args.quiet, json_mode=args.json)
    if args.source != "all" and args.source not in SOURCES:
        return _usage_error(
            f"未知來源：{args.source}（可選：{', '.join(SOURCES)}, all）"
        )

    plan = (
        [(name, info.enabled) for name, info in SOURCES.items()]
        if args.source == "all"
        else [(args.source, True)]
    )
    results: list[SourceResult] = []
    for name, enabled in plan:
        if not enabled:
            logger.warning("[%s] 停用，略過（可用 --source %s 單獨執行）", name, name)
            results.append(SourceResult(name, "skipped"))
            continue
        results.append(_run_one(name, args))

    effective_sort = args.sort or ("post_dt_desc" if args.days is not None else None)
    query = {
        "source": args.source,
        "keyword": args.keyword,
        "pages": args.pages,
        "days": args.days,
        "district": args.district,
        "category": args.category,
        "industry": args.industry,
        "sort": effective_sort,
        "detail": bool(args.detail),
        "fillLocation": bool(args.fill_location),
    }
    code = exit_code_for(results)
    payload = search_payload(query, results, code)

    if args.out:
        _write_out(Path(args.out), payload, results, json_mode=args.json)
    if args.json:
        emit_json(payload)
    else:
        _print_human(results, code)
    return code
```

在 `build_parser()` 內、`p_options` 之前加入：

```python
    p_search = sub.add_parser("search", help="搜尋職位（agent 請用 --json）")
    add_search_arguments(p_search, include_output_flags=False)
    add_machine_arguments(p_search)
    p_search.set_defaults(handler=cmd_search)
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python -m unittest tests.test_cli_contract.TestSearchCommand -v`
Expected: 10 tests PASS

Run: `python -m unittest discover -s tests`
Expected: 既有 32 + 新測試全綠

- [ ] **Step 5: Commit**

```bash
git add hkjobs/cli.py tests/test_cli_contract.py
git commit -m "feat(cli): search 支援 --json 封套、嚴格 exit code 與 --out"
```

---

### Task 7: 打包與安裝驗證

**Files:**
- Create: `pyproject.toml`
- Modify: `.gitignore`
- Test: `tests/test_cli_contract.py`（追加）

- [ ] **Step 1: 寫失敗測試**

追加：

```python
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
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python -m unittest tests.test_cli_contract.TestPackaging -v`
Expected: FAIL — `FileNotFoundError: .../pyproject.toml`（`TestModuleEntry` 因 Task 5 已建 `__main__.py`，此時應已 PASS）

- [ ] **Step 3: 建立 `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "hk-job-scraper"
description = "香港求職網站自動搜尋與職位匯出（agent 友善 CLI）"
readme = "README.md"
requires-python = ">=3.10"
license = { file = "LICENSE" }
dynamic = ["version"]
dependencies = [
    "requests>=2.31",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
]

[project.optional-dependencies]
browser = ["playwright>=1.40"]

[project.scripts]
hkjobs = "hkjobs.cli:main"

[tool.setuptools]
py-modules = ["config", "base_scraper", "exporter", "job_model"]
packages = ["hkjobs", "scrapers"]

[tool.setuptools.package-data]
scrapers = ["*.json"]

[tool.setuptools.dynamic]
version = { attr = "hkjobs.__version__" }
```

- [ ] **Step 4: 更新 `.gitignore`**

在 `# ---- 工具 / AI 暫存 ----` 之前加入：

```gitignore

# ---- 打包產物 ----
build/
dist/
*.egg-info/
```

- [ ] **Step 5: 執行測試，確認通過**

Run: `python -m unittest tests.test_cli_contract.TestPackaging tests.test_cli_contract.TestModuleEntry -v`
Expected: 2 tests PASS

- [ ] **Step 6: 實機安裝驗證（非測試）**

```bash
./venv/Scripts/python.exe -m pip install -e .
./venv/Scripts/hkjobs.exe --version
```

Expected: `hkjobs 0.1.0`

在 repo 外執行（路徑依你的 venv 位置調整）：

```bash
cd /c/Users/user
"/c/Users/user/Documents/Qoder/2026-10-28/fc0f348d/hk-job-scraper/venv/Scripts/hkjobs.exe" sources --json
```

Expected: 12 站 JSON；證明不依賴 cwd。

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore tests/test_cli_contract.py
git commit -m "build(pkg): 新增 pyproject 與 hkjobs console script"
```

---

### Task 8: 文件（AGENTS.md / README）與最終驗收

**Files:**
- Create: `AGENTS.md`
- Modify: `README.md`（3 處）
- Test: 全套測試 + 實機 smoke

- [ ] **Step 1: 建立 `AGENTS.md`**

```markdown
# AGENTS.md — 給 AI agent 與程式呼叫者

本專案是香港職位搜尋器（12 個模組、9 座預設啟用據點），輸出統一的 `JobRecord`。
本文件是**機器契約**；人類安裝與各站逆向筆記見 `README.md`。
舊入口 `python main.py` 仍可使用，但**沒有** `--json`、嚴格 exit code 與能力查詢。

## 安裝

```bash
pipx install .        # 推薦：隔離環境，取得 hkjobs 命令
pip install -e .      # 開發用
```

不需安裝時，在 repo 根目錄可用 `python -m hkjobs`。
需要瀏覽器的據點另外安裝：`pip install ".[browser]" && playwright install chromium`。
部分據點另需本機 Google Chrome（看 `sources` 的 `needsChrome`）。

## 探索流程（請照順序，不要硬編碼）

1. `hkjobs sources --json` — 據點清單、啟用狀態、支援維度、每頁筆數、`daysMode`（`--days` 成本）。
2. `hkjobs options --source <據點> --json` — 該站有效的地區/職能/行業/排序值（含 `id` 與 `aliases`）。
3. `hkjobs search --source <據點> --keyword <詞> --json` — 結果在 stdout。

```bash
hkjobs sources --json | jq '.presets.all'
hkjobs options --source jobsdb --dimension district --json | jq '.dimensions.district.values[] | select(.name=="荃灣")'
hkjobs search --source jobsdb --keyword data --days 7 --pages 1 --json | jq '.summary'
```

## 命令

- `hkjobs search`：參數同 `python main.py`（`--source/--keyword/--pages/--days/--district/--category/--industry/--sort/--detail/--fill-location`），另有：
  - `--json`：stdout 只輸出單一 JSON 封套；**不寫檔**；日誌走 stderr（預設 WARNING）。
  - `--out PATH`：顯式寫檔；`.csv` 寫職位 CSV（UTF-8 BOM），其他副檔名寫 JSON（`--json` 時為完整封套）。
  - `-q`：日誌只留 ERROR。
- `hkjobs sources [--json]`：能力矩陣。
- `hkjobs options --source <站> [--dimension district|category|industry|sort] [--json]`：有效值。

## 輸出契約（schemaVersion = 1）

成功：

```json
{"schemaVersion":1,"command":"search","generatedAt":"…","query":{…},
 "summary":{"total":37,"withSalary":12,
   "sources":[{"name":"jobsdb","status":"ok","jobs":37,"error":null}]},
 "jobs":[{"job_id":"jobsdb::123","source":"jobsdb","title":"…","company":"…",
          "location":"…","salary":"…","job_type":"…","industry":"…",
          "description":"…","requirements":"…","url":"…",
          "posted_date":"…","scraped_at":"…"}]}
```

失敗（exit ≠ 0 時）：

```json
{"schemaVersion":1,"command":"search","generatedAt":"…",
 "error":{"code":"partial_failure","message":"部分來源失敗：jobsdb"},
 "summary":{…},"jobs":[…]}
```

`code` ∈ `partial_failure` / `all_sources_failed` / `no_results` / `unexpected`。

## exit code

| 值 | 意義 | 建議動作 |
|---|---|---|
| 0 | 成功且 ≥1 筆 | 使用結果 |
| 2 | 參數／用法錯誤（**無 JSON 封套**，看 stderr） | 修正參數 |
| 3 | 部分來源失敗 | 讀 `summary.sources`，可重試失敗站 |
| 4 | 全部來源失敗 | 稍後重試；先跑 `sources` 檢查 |
| 5 | 成功但 0 筆 | 放寬 `--days`／換關鍵字／先查 `options` |
| 1 | 未預期錯誤（bug） | 回報並附 stderr |

優先序：`1 > 4 > 3 > 5 > 0`。

## 速率禮節（必須遵守）

- 一次只跑一個來源，**不要並行**同一站，也不要同時啟動多個 `hkjobs`。
- `--source all` 會依序跑 9 站；僅供便利使用，**勿用於巡檢**。需要多站時分批（每批 ≤5 站、批間休息 ≥30 秒）。
- 首次探測用 `--pages 1`；確認結果再增加。
- 站方請求間隔已寫死在 1.5–8 秒（見 `sources` 的 `requestDelaySeconds`），不要嘗試繞過。
- 被擋一次往往要等數天；寧可慢，不要猛。

## 安全與隱私

- `LINKEDIN_LI_AT` 等同 LinkedIn 帳號憑證：不得輸出、寫入日誌、提交或貼到對話中。
- 爬取結果可能含個資與聯絡方式；不要公開上傳未經處理的原始輸出。
- 不要為了驗證而讀取或列印 `~/.git-credentials`、環境變數中的 token。

## 修改本專案時

- 新增／變更據點行為，必須同步更新：`hkjobs/capabilities.py`、README 的「各站功能支援矩陣」與該站技術筆記。
- 各站功能彼此隔離；不支援的參數一律警告後忽略，不得報錯中斷或影響他站。
- 執行 `python -m unittest discover -s tests`（零網路）必須全綠。
```

- [ ] **Step 2: 更新 `README.md`（3 處）**

(1) 在「其他常見用法」code block 之後、「🐢 爬蟲禮節」之前插入：

```markdown
> 🤖 **給 AI agent／程式呼叫**：`pip install -e .`（或 `pipx install .`）後可用 `hkjobs` 命令。
> 探索順序：`hkjobs sources --json` → `hkjobs options --source <站> --json` → `hkjobs search ... --json`。
> 完整機器契約（JSON 封套、exit code、速率禮節）見 [`AGENTS.md`](AGENTS.md)。舊 `python main.py` 用法完全不變。
```

(2) 在 `## 📖 完整命令列參數` 之前插入新章節：

```markdown
## 🤖 給 AI agent／程式呼叫（hkjobs）

```bash
pip install -e .        # 或 pipx install .
hkjobs sources --json   # 12 站能力矩陣（啟用/瀏覽器/每頁/支援維度/近 N 天機制）
hkjobs options --source jobsdb --json          # 該站有效地區/職能/行業/排序值
hkjobs search --source jobsdb --keyword data --days 7 --json   # 結果只印 stdout，不寫檔
hkjobs search --source gov_hk --keyword 會計 --out result.json # 要存檔才加 --out
```

| 命令 | 用途 |
|---|---|
| `hkjobs search` | 搜尋；`--json` 輸出單一封套、日誌走 stderr、預設零寫檔 |
| `hkjobs sources` | 能力矩陣（機器可讀版支援矩陣） |
| `hkjobs options` | 字典值查詢（地區／職能／行業／排序，含別名與 ID） |

- `--json` 的 exit code：`0` 成功、`2` 參數錯、`3` 部分失敗、`4` 全失敗、`5` 零結果、`1` 未預期。
- `--out` 依副檔名：`.csv` 寫 CSV（UTF-8 BOM），其他寫 JSON。
- 完整契約與 agent 注意事項：見 [`AGENTS.md`](AGENTS.md)。
```

(3) 在「📁 專案結構」樹中加入（依字母位置）：

```
├── pyproject.toml          # 打包與 hkjobs console script
├── AGENTS.md               # 給 AI agent／程式呼叫的機器契約
├── hkjobs/                 # agent 友善 CLI（search / sources / options）
│   ├── cli.py              # 子命令分派
│   ├── args.py             # 搜尋參數（main.py 共用）
│   ├── capabilities.py     # 12 站能力矩陣
│   ├── options.py          # 字典查詢 adapter
│   └── contract.py         # JSON 封套與 exit code
```

並在「📊 各站功能支援矩陣」表格下方加一行：

```markdown
> 🤖 機器可讀版本：`hkjobs sources --json`（能力表由 `hkjobs/capabilities.py` 提供，與本表同步維護）。
```

- [ ] **Step 3: 全套測試**

Run: `python -m unittest discover -s tests -v`
Expected: 既有 32 + 新契約測試 38（合計 70）全綠

- [ ] **Step 4: 舊行為回歸（實機）**

```bash
python main.py --source gov_hk --keyword 會計 --pages 1
```

Expected: 與改動前相同——日誌格式、`output/gov_hk_會計.json`、exit code 0。

- [ ] **Step 5: 新命令實機 smoke（低負載）**

```bash
python -m hkjobs search --source gov_hk --keyword 會計 --pages 1 --json
```

Expected: stdout 為單一 JSON；`summary.total > 0`；stderr 只有日誌；不產生新檔。

```bash
python -m hkjobs search --source gov_hk --keyword 會計 --pages 1 --json --out output/smoke.json
python -c "import json;print(json.load(open('output/smoke.json',encoding='utf-8'))['summary'])"
```

Expected: `output/smoke.json` 可解析、內容與 stdout 一致（`output/` 已被 gitignore）。

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md README.md
git commit -m "docs(agent): 新增 AGENTS.md 與 README agent 章節"
```

---

## 驗收清單（Definition of Done）

- [ ] `hkjobs search|sources|options` 可用，`--json` 契約與 spec §6 一致
- [ ] exit code 0/1/2/3/4/5 皆有測試覆蓋
- [ ] `sources --json` 覆蓋 12 站，`enabled`/`needsBrowser` 與 scraper class 一致
- [ ] `options` 對所有支援組合可產出，抽樣值（tsuen-wan／會計／101000／000011／Hong Kong）正確
- [ ] `python main.py` 參數、預設值、輸出檔、exit 0 與改動前一致
- [ ] 既有 32 測試 + 新契約測試全綠
- [ ] `pip install -e .` 後可在 repo 外使用 `hkjobs`
- [ ] `AGENTS.md`、README 新章節與結構樹完成
- [ ] 無新增執行期依賴、無搬檔、未改動 14 個爬蟲模組

## 風險備忘

- 若 `github` 上既有 `main.py` 的 help 文字與本計畫不同（未來變更），以「搬移不重寫」為準，不可用本計畫文字覆蓋新內容。
- `export_csv` 預設增量合併；`--out` 必須傳 `incremental=False`，否則會混入舊檔資料。
- `logging.basicConfig(force=True)` 會覆蓋 import `main` 時建立的 handler，這是刻意行為。
