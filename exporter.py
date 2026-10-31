"""
輸出模組 (Phase 1.2)

提供兩種匯出格式：
  - export_json(jobs, filepath)   輸出為 JSON 陣列
  - export_csv(jobs, filepath)    輸出為 CSV（UTF-8 with BOM，Excel 相容）

並支援「增量寫入」：新資料附加到現有檔案，依 job_id 自動去重。
"""
from __future__ import annotations

import csv
import json
import logging
import os
from typing import Iterable

from job_model import JobRecord

logger = logging.getLogger(__name__)


def _ensure_dir(filepath: str) -> None:
    d = os.path.dirname(os.path.abspath(filepath))
    if d:
        os.makedirs(d, exist_ok=True)


def _atomic_write(filepath: str, writer, *, encoding: str, newline: str | None = None) -> None:
    """先寫 <path>.tmp 再 os.replace，避免中途中斷留下半個檔。

    增量模式會先讀回既有檔；直接覆寫時若中途失敗，舊資料就沒了，下次讀到半個
    JSON 還會被判定毀損而備份。原子替換保證檔案只會是「舊的」或「新的」。
    """
    tmp = f"{filepath}.tmp"
    try:
        with open(tmp, "w", encoding=encoding, newline=newline) as f:
            writer(f)
        os.replace(tmp, filepath)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _dedupe(jobs: Iterable[JobRecord]) -> list[JobRecord]:
    seen: dict[str, JobRecord] = {}
    for j in jobs:
        seen[j.dedupe_key()] = j  # 後到的覆蓋，保留最新抓取
    return list(seen.values())


def _backup_corrupt(filepath: str) -> None:
    """既有檔讀取失敗時，把它搬到 <path>.corrupt.bak 保存，避免增量覆寫令舊資料靜默消失。"""
    try:
        os.replace(filepath, filepath + ".corrupt.bak")
        logger.warning("原檔已備份至 %s.corrupt.bak（將以本輪新資料重建）", filepath)
    except OSError as be:  # 連備份都失敗才退回舊行為（直接覆寫）
        logger.warning("備份失敗（%s），將直接覆寫：%s", be, filepath)


def _load_existing_json(filepath: str) -> list[JobRecord]:
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [JobRecord.from_dict(d) for d in data]
    except Exception as e:  # noqa: BLE001
        logger.warning("讀取既有 JSON 失敗：%s", e)
        _backup_corrupt(filepath)
        return []


def _load_existing_csv(filepath: str) -> list[JobRecord]:
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            return [JobRecord.from_dict(row) for row in reader]
    except Exception as e:  # noqa: BLE001
        logger.warning("讀取既有 CSV 失敗：%s", e)
        _backup_corrupt(filepath)
        return []


def export_json(
    jobs: Iterable[JobRecord],
    filepath: str,
    *,
    incremental: bool = True,
) -> int:
    """匯出 JSON。incremental=True 時與既有檔案合併去重。

    Returns: 寫入的職位總數（去重後）。
    """
    _ensure_dir(filepath)
    if incremental:
        jobs = _dedupe(list(_load_existing_json(filepath)) + list(jobs))
    else:
        jobs = _dedupe(jobs)

    _atomic_write(
        filepath,
        lambda f: json.dump([j.to_dict() for j in jobs], f, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("已匯出 %d 筆職位 -> %s", len(jobs), filepath)
    return len(jobs)


def export_csv(
    jobs: Iterable[JobRecord],
    filepath: str,
    *,
    incremental: bool = True,
) -> int:
    """匯出 CSV（UTF-8 with BOM）。incremental=True 時合併去重。"""
    _ensure_dir(filepath)
    if incremental:
        jobs = _dedupe(list(_load_existing_csv(filepath)) + list(jobs))
    else:
        jobs = _dedupe(jobs)

    fields = list(JobRecord.FIELDS)

    def _dump(f) -> None:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for j in jobs:
            writer.writerow(j.to_dict())

    # BOM 讓 Excel 正確辨識 UTF-8 繁體中文
    _atomic_write(filepath, _dump, encoding="utf-8-sig", newline="")
    logger.info("已匯出 %d 筆職位 -> %s", len(jobs), filepath)
    return len(jobs)


def export(
    jobs: Iterable[JobRecord],
    filepath: str,
    *,
    fmt: str = "json",
    incremental: bool = True,
) -> int:
    """統一入口：fmt ∈ {json, csv, both}。"""
    fmt = (fmt or "json").lower()
    total = 0
    if fmt in ("json", "both"):
        total = export_json(jobs, filepath, incremental=incremental)
    if fmt in ("csv", "both"):
        base, _ = os.path.splitext(filepath)
        csv_path = base + ".csv"
        total = export_csv(jobs, csv_path, incremental=incremental)
    return total
