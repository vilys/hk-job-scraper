"""
统一职位数据模型 (Phase 1.1)

每個網站爬蟲最終都應產出 JobRecord 物件，欄位標準化，
方便後續匯出 JSON / CSV 與跨網站合併去重。
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class JobRecord:
    # ---- 標準欄位（依規劃書定義）----
    job_id: str                 # 唯一識別（來源網站 + 原始 ID）
    source: str                 # 來源網站名稱
    title: str = ""             # 職位名稱
    company: str = ""           # 公司名稱
    location: str = ""          # 工作地點
    salary: str = ""            # 薪資範圍（原始文字）
    job_type: str = ""
    industry: str = ""           # 所屬行業（勞工處 detail 頁「行業 :」標籤）
    description: str = ""       # 職位描述
    requirements: str = ""      # 要求條件
    url: str = ""               # 職位詳情連結
    posted_date: str = ""       # 發佈日期
    scraped_at: str = field(    # 抓取時間（ISO 格式）
        default_factory=lambda: _dt.datetime.now(_dt.timezone.utc).isoformat()
    )

    # ---- 保留原始資料的彈性欄位 ----
    raw: dict[str, Any] = field(default_factory=dict)

    # 欄位順序（匯出 CSV / JSON 時保持一致）
    FIELDS: tuple[str, ...] = (
        "job_id", "source", "title", "company", "location",
        "salary", "job_type", "industry", "description", "requirements",
        "url", "posted_date", "scraped_at",
    )

    def to_dict(self) -> dict[str, Any]:
        """匯出為 dict（僅標準欄位，raw 不進入主表）。"""
        return {k: getattr(self, k) for k in self.FIELDS}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JobRecord":
        """從 dict 重建（忽略未知欄位，raw 單獨保留）。"""
        known = {k: d[k] for k in cls.FIELDS if k in d}
        raw = d.get("raw", {})
        if not isinstance(raw, dict):
            raw = {}
        return cls(**known, raw=raw)

    def dedupe_key(self) -> str:
        """去重鍵：以 job_id 為準。"""
        return self.job_id

    @staticmethod
    def make_id(source: str, original_id: str) -> str:
        """產生標準 job_id：source::original_id。"""
        return f"{source}::{original_id}"


# 向後相容的別名（部分舊程式碼可能用 JobPosting）
JobPosting = JobRecord
