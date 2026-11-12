"""JSON 封套、exit code 與 stdout 規則（agent 契約的唯一實作）。"""
from __future__ import annotations

import json
import re
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


# Windows 下「被重定向」的 stdin 會用 locale 編碼（cp950）去解 UTF-8 位元組，
# 產生 U+DC80–U+DCFF 的 lone surrogate；這種字串再印到 UTF-8 stdout 就會
# UnicodeEncodeError: surrogates not allowed（引導模式 pipe 中文關鍵字的 crash）。
# 真實 console 走 Unicode API（PEP 528），stdin 本來就是 UTF-8，不需也不該動。
_SURROGATE = re.compile(r"[\udc80-\udcff]")
# 復原原始位元組後的候選解碼順序：UTF-8 優先，再照顧港澳／簡體舊編碼。
_INPUT_DECODE_ORDER = ("utf-8", "cp950", "big5hkscs", "gb18030")


def configure_io() -> None:
    """統一 stdout/stderr 為 UTF-8，並對齊「非互動式」stdin 的輸入編碼。

    輸出面：避免 Windows cp950 主控台印中文 JSON／提示失敗。
    輸入面：管道／檔案導向的 stdin 改用 UTF-8 + surrogateescape；
    **互動式 console（isatty=True）刻意跳過**，不干擾 Windows Unicode API。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, OSError):
            pass
    _configure_stdin()


def _configure_stdin() -> None:
    """只處理被重定向的 stdin；已是 UTF-8 + surrogateescape 時不動。"""
    stdin = sys.stdin
    if stdin is None:
        return
    try:
        if stdin.isatty():
            return
        enc = (getattr(stdin, "encoding", "") or "").lower().replace("_", "-")
        err = (getattr(stdin, "errors", "") or "").lower()
        if enc in ("utf-8", "utf8") and err == "surrogateescape":
            return
        stdin.reconfigure(encoding="utf-8", errors="surrogateescape")
    except (AttributeError, ValueError, OSError, TypeError):
        # StringIO / mock 物件沒有 reconfigure；不動它，read_input 仍會修補文字。
        pass


def repair_stdin_text(text: str) -> str:
    """把 lone surrogate 還原成原始位元組，再用正確編碼重解一次。

    surrogateescape 讓我們能無損取回原始位元組：
    - stdin 仍用 cp950、管道送 UTF-8 → 取回 UTF-8 位元組 → 解成中文；
    - stdin 已用 UTF-8、管道送 cp950（cmd.exe 常見）→ 取回 cp950 位元組 → 解成中文。
    兩條路都收敛到可列印的字串，不再把 surrogate 送進 print()。
    """
    if not text or not _SURROGATE.search(text):
        return text
    enc = getattr(sys.stdin, "encoding", None) or "utf-8"
    try:
        raw = text.encode(enc, "surrogateescape")
    except (UnicodeError, LookupError, TypeError):
        return text
    for candidate in _INPUT_DECODE_ORDER:
        try:
            return raw.decode(candidate)
        except (UnicodeError, LookupError):
            continue
    # 最後手段：至少不留 surrogate，避免再次炸在輸出端。
    return raw.decode("utf-8", "replace")


def read_input(prompt: str = "") -> str:
    """本專案所有 input() 的單一入口，確保引導模式與 --fill-gaps 確認同源。

    EOFError / KeyboardInterrupt 原樣丟給呼叫端（既有取消語意不變）。
    """
    return repair_stdin_text(input(prompt))


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
