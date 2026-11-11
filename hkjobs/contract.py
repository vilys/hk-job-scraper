"""JSON 封套、exit code 與 stdout 規則（agent 契約的唯一實作）。"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from hkjobs import aggregate
from job_model import JobRecord

# v2（2026-11-11）：jobs 新增 salary_min/max/period、posted_date_raw、sources、urls；
# summary 新增 deduped / sortBy / sources[].coverage；posted_date 一律 ISO。
# exit code、其餘欄位與命令不變，見 AGENTS.md 的新舊欄位對照表。
SCHEMA_VERSION = 2

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


def search_payload(
    query: dict,
    results: list[SourceResult],
    code: int,
    *,
    dedup: bool = True,
    sort_by: str | None = None,
    salary_by: str = "mid",
) -> dict:
    """組出 schema v2 封套。

    聚合管線：v1 dict → 正規化 → 去重 → 跨站排序 → summary。
    `rawTotal` 讓呼叫端能直接查核 `total + deduped == rawTotal`。
    `salary_by` 只在 `sort_by == "salary"` 時生效並寫入 `query.salaryBy`。
    """
    v1 = [j.to_dict() for r in results if r.status == "ok" for j in r.jobs]
    raw_total = len(v1)
    jobs = [aggregate.to_v2(j) for j in v1]
    if dedup:
        jobs, deduped = aggregate.deduplicate(jobs)
    else:
        deduped = 0
    if sort_by:
        jobs = aggregate.sort_jobs(jobs, sort_by, salary_by=salary_by)

    source_rows = []
    for r in results:
        row = {
            "name": r.name,
            "status": r.status,
            "jobs": len(r.jobs),
            "error": r.error,
        }
        if r.status == "ok":
            row["coverage"] = aggregate.coverage(
                [aggregate.to_v2(j.to_dict()) for j in r.jobs]
            )
        source_rows.append(row)

    summary = {
        "total": len(jobs),
        "rawTotal": raw_total,
        "deduped": deduped,
        "withSalary": sum(1 for j in jobs if aggregate.has_numeric_salary(j)),
        "sortBy": sort_by,
        "sources": source_rows,
    }
    envelope_query = {**query, "sortBy": sort_by, "dedup": dedup}
    if sort_by == "salary":
        # 只在薪金排序時多這一個鍵；date／不排序的封套與上一版逐鍵相同。
        envelope_query["salaryBy"] = salary_by
    envelope = {
        "schemaVersion": SCHEMA_VERSION,
        "command": "search",
        "generatedAt": now_iso(),
        "query": envelope_query,
        "summary": summary,
        "jobs": jobs,
    }
    if code == EXIT_OK:
        return envelope

    failed = [r.name for r in results if r.status == "failed"]
    messages = {
        EXIT_PARTIAL: f"部分來源失敗：{', '.join(failed)}",
        EXIT_ALL_FAILED: f"所有來源均失敗：{', '.join(failed)}",
        EXIT_EMPTY: "查詢成功但 0 筆結果",
    }
    envelope["error"] = {
        "code": _ERROR_CODES.get(code, "unexpected"),
        "message": messages.get(code, "未知錯誤"),
    }
    return envelope


def emit_json(payload: dict) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
