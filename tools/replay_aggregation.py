# -*- coding: utf-8 -*-
"""離線重播：把 `--source all` 的真實 v1 封套餵進現行聚合管線。

用途
----
`--source all` 一次會打九站，速率禮節不允許為了驗證改版而重跑。
本工具讀取**事先存下的真實回應**（`output/all_baseline.json`），
用現行的 `contract.search_payload()` 與 `cli._print_human()` 重算一次，
產出 v2 封套（`output/all.json`）與人類輸出。零網路請求。

⚠️ 這是「離線重播」，不是二次真實爬取。程式管線是真的，資料也是真的，
   但 `generatedAt` 之外的所有職位內容都來自基準檔，不會反映站方最新變動。

用法
----
    python tools/replay_aggregation.py                       # 產出 output/all.json
    python tools/replay_aggregation.py --human --limit 20   # 另印人類模式輸出
    python tools/replay_aggregation.py --sort-by salary     # 改按月薪排序
    python tools/replay_aggregation.py --no-dedup           # 關閉去重
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 直接執行 tools/ 下的腳本時 sys.path[0] 是 tools/，需補上 repo 根目錄
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hkjobs import cli, contract  # noqa: E402
from job_model import JobRecord   # noqa: E402


def _results(envelope: dict) -> list[contract.SourceResult]:
    grouped: dict[str, list[JobRecord]] = {}
    for j in envelope["jobs"]:
        grouped.setdefault(j["source"], []).append(JobRecord.from_dict(j))
    return [
        contract.SourceResult(
            s["name"], s["status"], grouped.get(s["name"], []), s["error"]
        )
        for s in envelope["summary"]["sources"]
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", default="output/all_baseline.json")
    ap.add_argument("--out", default="output/all.json")
    ap.add_argument("--sort-by", choices=["date", "salary"], default="date")
    ap.add_argument("--no-dedup", action="store_true")
    ap.add_argument("--human", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    baseline = ROOT / args.baseline
    envelope = json.loads(baseline.read_text(encoding="utf-8"))
    results = _results(envelope)
    code = contract.exit_code_for(results)
    payload = contract.search_payload(
        envelope["query"], results, code,
        dedup=not args.no_dedup, sort_by=args.sort_by,
    )

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    s = payload["summary"]
    print(f"[離線重播] 讀 {args.baseline} → 寫 {args.out}（零網路請求）")
    print(f"  schemaVersion={payload['schemaVersion']}  "
          f"total={s['total']}  deduped={s['deduped']}  rawTotal={s['rawTotal']}  "
          f"withSalary={s['withSalary']}  sortBy={s['sortBy']}")

    if args.human:
        cli._print_human(
            results, code,
            jobs=payload["jobs"],
            list_limit=args.limit,
            sort_by=args.sort_by,
            deduped=s["deduped"],
            raw_total=s["rawTotal"],
            show_coverage=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
