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
    print(_pad("來源", LABEL_W) + _pad("筆數", 6, align="right") + "  狀態")
    for result in results:
        label = {"ok": "ok", "failed": "失敗", "skipped": "略過"}[result.status]
        extra = f"（{result.error}）" if result.error else ""
        print(
            _pad(result.name, LABEL_W)
            + _pad(str(len(result.jobs)), 6, align="right")
            + f"  {label}{extra}"
        )
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hkjobs", description="香港職位搜尋 CLI（agent 友善）"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sources = sub.add_parser("sources", help="列出據點能力矩陣")
    p_sources.add_argument("--json", action="store_true", help="輸出 JSON")
    p_sources.set_defaults(handler=cmd_sources)

    p_search = sub.add_parser("search", help="搜尋職位（agent 請用 --json）")
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
