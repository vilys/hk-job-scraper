"""hkjobs 命令列入口（agent 友善）。"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import unicodedata
from pathlib import Path

from exporter import export_csv
from hkjobs import __version__
from hkjobs.args import add_machine_arguments, add_search_arguments
from hkjobs.capabilities import SOURCES
from hkjobs.contract import (
    EXIT_ALL_FAILED,
    EXIT_EMPTY,
    EXIT_OK,
    EXIT_PARTIAL,
    EXIT_UNEXPECTED,
    EXIT_USAGE,
    SCHEMA_VERSION,
    SourceResult,
    configure_io,
    emit_json,
    exit_code_for,
    now_iso,
    search_payload,
)
from hkjobs.options import load_dimension
from scrapers import SCRAPERS

logger = logging.getLogger("hkjobs")

# 表格欄寬下限（實際寬度依內容動態計算，見 `_print_sources_table`）
LABEL_W = 14
NAME_W = 12
ENABLED_W = 6
BROWSER_W = 8
PERPAGE_W = 5


def _disp_width(text: str) -> int:
    """字串在終端上的顯示寬度：全形／寬字元算 2、組合字元算 0。

    Python 的 `str.ljust` 按**字元數**補空格，遇到中文只補 1 格，
    實際卻佔 2 格 → 欄位錯位（`JobMarket 求職廣場jobmarket`）。
    """
    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def _pad(text: str, width: int, *, align: str = "left") -> str:
    """依顯示寬度補齊到 `width` 欄（右對齊用於數字欄）。"""
    gap = max(0, width - _disp_width(text))
    return (" " * gap + text) if align == "right" else (text + " " * gap)


def _truncate(text: str, width: int) -> str:
    """依顯示寬度截斷並補省略號，避免長標題把整張表格擠歪。"""
    if _disp_width(text) <= width:
        return text
    out = ""
    for ch in text:
        if _disp_width(out + ch) > width - 1:
            break
        out += ch
    return out + "…"


# 人類模式職位清單的欄寬（顯示寬度，CJK 算 2）
JOB_COLUMNS = (
    ("#", 3, "right"),
    ("標題", 34, "left"),
    ("公司", 20, "left"),
    ("地區", 14, "left"),
    ("薪金", 28, "left"),
    ("刊登日", 11, "left"),
)


def _print_jobs_table(jobs: list, *, limit: int) -> int:
    """印出職位清單，回傳「未列出」的筆數。

    `limit <= 0` 表示全部列出。欄位固定為標題／公司／地區／薪金／刊登日，
    空值一律顯示 `—`，不讓求職者誤以為是程式壞了。
    """
    shown = jobs if limit <= 0 else jobs[:limit]
    hidden = len(jobs) - len(shown)
    header = "  ".join(_pad(name, w, align=align) for name, w, align in JOB_COLUMNS)
    print(f"\n職位清單（顯示 {len(shown)} 筆 / 共 {len(jobs)} 筆）")
    print(header)
    print("-" * _disp_width(header))
    for idx, j in enumerate(shown, 1):
        cells = (
            str(idx),
            (j.title or "").strip() or "—",
            (j.company or "").strip() or "—",
            (j.location or "").strip() or "—",
            (j.salary or "").strip() or "—",
            (j.posted_date or "").strip() or "—",
        )
        print("  ".join(
            _pad(_truncate(cell, w), w, align=align)
            for cell, (_, w, align) in zip(cells, JOB_COLUMNS)
        ))
    return hidden


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
    # 欄寬取「表頭與所有內容的最大顯示寬度」；寫死寬度遇到超長站名必破版
    label_w = max([LABEL_W] + [_disp_width(r["label"]) for r in rows])
    name_w = max([NAME_W] + [_disp_width(r["name"]) for r in rows])

    header = (
        _pad("來源", label_w) + " " + _pad("代號", name_w) + " "
        + _pad("啟用", ENABLED_W) + " " + _pad("瀏覽器", BROWSER_W) + " "
        + _pad("每頁", PERPAGE_W, align="right") + "  支援維度 / 近N天"
    )
    print(header)
    print("-" * _disp_width(header))
    for r in rows:
        dims = [k for k in ("district", "category", "industry") if r["supports"][k]]
        print(
            _pad(r["label"], label_w) + " " + _pad(r["name"], name_w) + " "
            + _pad("是" if r["enabled"] else "否", ENABLED_W) + " "
            + _pad("需" if r["needsBrowser"] else "—", BROWSER_W) + " "
            + _pad(str(r["perPage"]), PERPAGE_W, align="right")
            + f"  {'/'.join(dims) or '—'} / {r['daysMode']}"
        )
    print("\n提示：加 --json 取得完整矩陣與各站備註；有效值用 hkjobs options --source <站> --json")
    print("備註：JobsDB 列表薪金常缺；勞工處列表無公司名（需 --detail）。")


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
        # 爬蟲失敗已是預期內的路徑（會轉成 status=failed / exit 4），
        # 用 error 而非 exception：錯誤全文已在 SourceResult.error，stderr 不必再噴 traceback。
        logger.error("[%s] 執行失敗：%s", source, exc)
        return SourceResult(source, "failed", [], str(exc))
    finally:
        if scraper is not None:
            scraper.close()


def _print_human(
    results: list[SourceResult],
    code: int,
    *,
    out_path: str | None = None,
    list_limit: int = 20,
    no_list: bool = False,
) -> None:
    """人類模式輸出：來源摘要 + 職位清單 + 下一步提示。

    提示只講「下一步」，不重複已完成的事：已寫檔就顯示實際路徑，
    列滿了就告訴使用者怎麼拿到剩下的，而不是又叫他去加 --out。
    """
    print(_pad("來源", LABEL_W) + _pad("筆數", 6, align="right") + "  狀態")
    for result in results:
        label = {"ok": "ok", "failed": "失敗", "skipped": "略過"}[result.status]
        extra = f"（{result.error}）" if result.error else ""
        print(
            _pad(result.name, LABEL_W)
            + _pad(str(len(result.jobs)), 6, align="right")
            + f"  {label}{extra}"
        )
    jobs = [j for r in results if r.status == "ok" for j in r.jobs]
    total = len(jobs)
    with_salary = sum(1 for j in jobs if j.salary)
    salary_note = f"{with_salary}/{total} 筆有薪金" if total else "0 筆"
    print(f"\n總計：{total} 筆（{salary_note}）")

    hidden = 0
    if not no_list and jobs:
        hidden = _print_jobs_table(jobs, limit=list_limit)
        # 勞工處列表頁沒有僱主欄位（實測 2026-11-11）；空公司名要說清楚，
        # 否則求職者會以為爬蟲壞了。
        if any(r.name == "gov_hk" and r.status == "ok" for r in results) \
                and not any(j.company for j in jobs):
            print("提示：勞工處列表頁不含公司名，公司欄為 —；加 --detail 才會補齊"
                  "（每筆多 1 支請求，請斟酌量）。")
        if hidden:
            print(f"另有 {hidden} 筆未列出：用 --limit 0 全部印出，"
                  "或加 --out result.csv 存成檔案。")

    if out_path:
        print(f"\n已儲存 {total} 筆至 {out_path}")
        print("提示：加 --json 取得機器可讀 JSON；換條件再跑一次即可比較。")
    else:
        print("\n提示：加 --json 取得機器可讀 JSON；加 --out result.csv 儲存結果。")

    if code == EXIT_EMPTY:
        print("提示：0 筆結果。可放寬 --days、換 --keyword，或先跑 hkjobs sources 確認支援度。")
    elif code in (EXIT_PARTIAL, EXIT_ALL_FAILED):
        print("提示：有來源失敗。可稍後重試，或先跑 hkjobs sources 確認據點狀態。")


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
    # --pages 0 原本會跑出「0 筆結果 / exit 5」，那是把用法錯誤偽裝成查無結果。
    if args.pages < 1:
        return _usage_error("--pages 必須 ≥ 1（探測請用 1；0 不是「不翻頁」）")
    # 覆蓋保護必須在發出任何請求之前：爬完才發現不能寫，等於白打一站的請求。
    # --json 是既有 agent 契約，維持原行為（不加 --force 也能覆寫）。
    if args.out and not args.json and not args.force and Path(args.out).exists():
        return _usage_error(
            f"檔案已存在：{args.out}。為避免蓋掉舊清單，請加 --force 覆寫，"
            "或換一個 --out 路徑。"
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

    # --days 只做日期過濾，不再偷偷改成刊登日期排序（會淹沒相關性）。
    # query.sort 忠實反映「實際送給站方的排序」，沒有就是 null。
    effective_sort = args.sort
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
        _print_human(
            results, code,
            out_path=args.out,
            list_limit=args.limit,
            no_list=args.no_list,
        )
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hkjobs", description="香港職位搜尋 CLI（agent 友善）"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sources = sub.add_parser("sources", help="列出據點能力矩陣")
    p_sources.add_argument("--json", action="store_true", help="輸出 JSON")
    p_sources.set_defaults(handler=cmd_sources)

    p_search = sub.add_parser(
        "search",
        help="搜尋職位（agent 請用 --json）",
        description="搜尋香港職位；不加任何輸出旗標就會直接列出職位清單。",
        epilog=(
            "常用範例：\n"
            "  hkjobs search --source gov_hk --keyword 文員 --days 7 --pages 1\n"
            "  hkjobs search --source jobsdb --keyword analyst --pages 1 --out analyst.csv\n"
            "  hkjobs search --source linkedin --keyword \"data engineer\" --json\n\n"
            "預設值：來源 moovup、關鍵字空、3 頁、列出前 20 筆、不寫檔、不抓詳情。\n"
            "探測請用 --pages 1；檔案已存在時加 --force 才會覆寫。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_search_arguments(p_search, include_output_flags=False)
    add_machine_arguments(p_search)
    p_search.set_defaults(handler=cmd_search)

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
