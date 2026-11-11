# -*- coding: utf-8 -*-
"""互動引導模式：給不想背旗標、也不想查字典的求職者。

純標準庫 `input()`，零新依賴。這是**新增入口**，不改既有旗標 API，
也不影響 `--json` 契約：引導模式只會組出一般的人類模式 `search` 命令。

設計：
- 站別與職能選項直接來自 `capabilities.SOURCES` 與 `options.load_dimension()`，
  用編號挑選，不必自由打字打錯字典值。
- 選完先印出「完整命令」再執行，使用者可以學起來或直接複製。
- 固定 `--pages 1`（探測量），符合專案速率禮節。
"""
from __future__ import annotations

from typing import Callable

from hkjobs.capabilities import SOURCES
from hkjobs.contract import configure_io, EXIT_OK
from hkjobs.options import load_dimension

MAX_DICT_CHOICES = 12
_MAX_RETRY = 3


def _quote(arg: str) -> str:
    """顯示用的引號（Windows cmd 認雙引號，不認 shlex 的單引號）。"""
    return f'"{arg}"' if " " in arg else arg


def display_command(argv: list[str]) -> str:
    return " ".join(_quote(a) for a in ["python", "-m", "hkjobs", *argv])


def _choose(prompt: str, choices: list[tuple[str, object]],
            default: int = 0):
    """印出編號選項並回傳選中的值；取消／輸入錯誤過多回 None。"""
    print()
    print(prompt)
    for idx, (label, _) in enumerate(choices, 1):
        print(f"  {idx}) {label}")
    for _ in range(_MAX_RETRY):
        try:
            raw = input(f"請輸入編號 [1-{len(choices)}，Enter = {default + 1}，q = 離開]：").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not raw:
            return choices[default][1]
        if raw.lower() in ("q", "quit", "exit"):
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1][1]
        print(f"編號請落在 1-{len(choices)}。")
    print("輸入次數過多，已離開引導。")
    return None


def _free_text(prompt: str, default: str = ""):
    try:
        answer = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return None
    return answer or default


def _station_choices() -> list[tuple[str, str]]:
    rows = [(f"{info.label}（{name}）", name)
            for name, info in SOURCES.items() if info.enabled]
    rows.append(("全部來源 --source all（一次九站，請偶爾使用）", "all"))
    return rows


def _category_choices(source: str) -> list[tuple[str, str]]:
    """職能選項由 options 字典產生；不支援的站回空清單。"""
    if source == "all":
        return []          # 各站字典獨立，不適合在引導裡混用
    info = load_dimension(source, "category")
    if not info or info.get("kind") == "free":
        return []
    values = [v.get("name") for v in info["values"]
              if isinstance(v, dict) and v.get("name")]
    rows = [("不指定職能（預設）", "")]
    rows += [(str(v), str(v)) for v in values[:MAX_DICT_CHOICES]]
    if len(values) > MAX_DICT_CHOICES:
        rows.append(("自行輸入職能（請打完整名稱）", "__free__"))
    return rows


def run_guide(execute: Callable[[list[str]], int] | None = None) -> int:
    """跑一輪問答，回傳 exit code。`execute` 可注入以便零網路測試。"""
    configure_io()
    if execute is None:
        from hkjobs.cli import main as execute  # 延遲 import，避免循環

    print("hk-job-scraper 引導模式：用編號選，不必背旗標。")
    print("為遵守速率禮節，引導模式固定 --pages 1（一次只抓一頁）。")

    source = _choose("一、要搜尋哪一個站？", _station_choices())
    if source is None:
        print("已離開，未發出任何請求。")
        return EXIT_OK

    keyword = _free_text(
        "二、關鍵字（例如 文員；直接 Enter = 不限定）：")
    if keyword is None:
        print("已離開，未發出任何請求。")
        return EXIT_OK

    category = ""
    cat_choices = _category_choices(source)
    if cat_choices:
        picked = _choose(f"三、{source} 的工作種類？（選項來自該站字典）",
                         cat_choices, default=0)
        if picked is None:
            print("已離開，未發出任何請求。")
            return EXIT_OK
        if picked == "__free__":
            typed = _free_text("請輸入完整職能名稱：")
            if typed is None:
                print("已離開，未發出任何請求。")
                return EXIT_OK
            category = typed
        else:
            category = str(picked or "")
        if len([v for v in cat_choices if v[1] not in ("", "__free__")]) \
                == MAX_DICT_CHOICES:
            print(f"（只列前 {MAX_DICT_CHOICES} 個；完整清單："
                  f"hkjobs options --source {source} --dimension category）")
    else:
        print("三、此站沒有可選的職能字典（或為 --source all），略過職能題。")

    days = _choose(
        "四、只要最近幾天刊登的職位？（部分站不支援，會照既有規則警告後忽略）",
        # 0 = 不限定；不能用 None，那是 _choose 的「取消」回傳值。
        [("不限定", 0), ("3 天內", 3), ("7 天內", 7),
         ("14 天內", 14), ("30 天內", 30)], default=0)
    if days is None:
        print("已離開，未發出任何請求。")
        return EXIT_OK

    fill = _choose(
        "五、要不要一鍵補齊公司名／日期／地區缺口？（會多打詳情請求）",
        [("不需要（較省請求）", False),
         ("要（--fill-gaps --yes，執行前仍會列出請求數估算）", True)], default=0)
    if fill is None:
        print("已離開，未發出任何請求。")
        return EXIT_OK

    argv = ["search", "--source", str(source), "--pages", "1"]
    if keyword:
        argv += ["--keyword", keyword]
    if category:
        argv += ["--category", category]
    if days:
        argv += ["--days", str(days)]
    if fill:
        argv += ["--fill-gaps", "--yes"]

    print()
    print("即將執行（可記起來，下次直接貼這一行）：")
    print("  " + display_command(argv))
    answer = _free_text("執行？（Y/n）：", default="y")
    if answer is None or answer.strip().lower() in ("n", "no"):
        print("已取消，未發出任何爬取請求。")
        return EXIT_OK

    code = int(execute(argv))
    print()
    print("看完終端機結果後，也可以執行 python build_dashboard.py 產生 HTML 看板，")
    print("在瀏覽器裡用大字與鍵盤慢慢看（CLI 負責抓，HTML 負責讀）。")
    return code
