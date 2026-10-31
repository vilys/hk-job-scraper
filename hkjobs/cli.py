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
