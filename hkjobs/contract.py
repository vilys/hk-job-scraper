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
