"""
爬蟲基類 (Phase 1.3)

定義所有網站爬蟲共用的介面與通用邏輯：
  - search(keyword, page, district, category, industry) -> list[JobRecord]  單頁搜尋結果
  - get_detail(job_url)   -> JobRecord         抓取詳情頁
  - scrape_all(keyword, max_pages, district, category, industry) -> list[JobRecord]  自動翻頁彙整

通用邏輯包含：請求間隔、失敗重試、logging、增量匯出鉤子。
"""
from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Iterable

from config import DEFAULT_HEADERS, MAX_RETRIES, delay_for
from exporter import export
from job_model import JobRecord

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    # 子類必須設定
    source: str = ""            # 來源名稱，例如 "moovup"
    use_browser: bool = False   # 是否需要 Playwright 真瀏覽器
    # 列表頁是否已內含可解析的刊登日期（JobsDB 是；gov_hk / moovup 否）。
    # 若為 True，--days 篩選可直接用列表資料，不必為了取日期而逐筆抓詳情頁。
    list_has_date: bool = False

    def __init__(self, headers: dict | None = None):
        self.headers = dict(DEFAULT_HEADERS)
        if headers:
            self.headers.update(headers)
        self.session = None      # 由子類（requests / playwright）自行管理
        self._stats = {"success": 0, "failed": 0, "skipped": 0}
        self._warned_fill_location = False   # --fill-location 不支援時只警告一次

    # ---------- 通用工具 ----------
    def _sleep(self, extra: float = 0.0) -> None:
        """尊重目標網站的請求間隔（帶少許隨機抖動，更像真人）。"""
        base = delay_for(self.source)
        time.sleep(base + extra + random.uniform(0, 0.5))

    def _with_retry(self, func, *args, **kwargs):
        """通用重試：網路錯誤重試 MAX_RETRIES 次，指數退避。"""
        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:  # noqa: BLE001
                last_err = e
                wait = 2 ** attempt
                logger.warning(
                    "[%s] 第 %d 次嘗試失敗：%s（%d 秒後重試）",
                    self.source, attempt, e, wait,
                )
                time.sleep(wait)
        self._stats["failed"] += 1
        logger.error("[%s] 已重試 %d 次仍失敗，放棄。", self.source, MAX_RETRIES)
        raise last_err

    # ---------- 抽象介面 ----------
    @abstractmethod
    def search(
        self,
        keyword: str,
        page: int = 1,
        district: str | None = None,
        category: str | None = None,
        industry: str | None = None,
        sort: str | None = None,
    ) -> list[JobRecord]:
        """回傳單頁搜尋結果（JobRecord 清單）。

        district / category / industry / sort 皆為可選過濾 / 排序條件，
        各來源依自身能力決定是否支援（不支援者忽略即可）。
        """
        raise NotImplementedError

    @abstractmethod
    def get_detail(self, job_url: str) -> JobRecord | None:
        """抓取單筆職位詳情，回傳補齊欄位後的 JobRecord。"""
        raise NotImplementedError

    # ---------- 通用流程 ----------
    def scrape_all(
        self,
        keyword: str,
        max_pages: int = 5,
        district: str | None = None,
        *,
        category: str | None = None,
        industry: str | None = None,
        sort: str | None = None,
        days: int | None = None,
        with_detail: bool = False,
        fill_location: bool = False,
        output: str | None = None,
        fmt: str = "json",
    ) -> list[JobRecord]:
        """自動翻頁彙整，可選是否抓詳情、是否匯出檔案。

        Args:
            keyword:      搜尋關鍵字
            max_pages:    最大翻頁數
            district:     地區過濾（依來源而定）
            category:     工作種類 / 職位類別過濾（依來源而定）
            industry:     行業過濾（依來源而定）
            sort:         排序方式（依來源而定，如 gov_hk 的 post_dt_desc）
            days:         只保留最近 N 天內刊登的職位（需抓詳情以取得日期）
            with_detail:  True 時對每筆結果再抓詳情頁
            fill_location: True 時對列表結果補地區（僅實作了 `fill_locations()` 的
                           來源支援，如 recruit；其餘來源警告後忽略，不中斷）
            output:       輸出檔案路徑（None 表示不匯出）
            fmt:          json / csv / both
        """
        # 按日期篩選：若列表頁已含日期（list_has_date），直接以列表資料過濾；
        # 否則必須抓詳情以取得 posted_date。預設按刊登日期由近至遠排序。
        if days is not None:
            if not self.list_has_date:
                with_detail = True
            if sort is None:
                sort = "post_dt_desc"

        all_jobs: list[JobRecord] = []
        for page in range(1, max_pages + 1):
            try:
                jobs = self._with_retry(
                    self.search, keyword, page, district,
                    category=category, industry=industry, sort=sort,
                )
            except Exception as e:  # noqa: BLE001
                logger.error("[%s] 搜尋第 %d 頁失敗：%s", self.source, page, e)
                break

            if not jobs:
                logger.info("[%s] 第 %d 頁無結果，停止翻頁。", self.source, page)
                break

            logger.info("[%s] 第 %d 頁取得 %d 筆。", self.source, page, len(jobs))
            self._stats["success"] += len(jobs)

            # 列表補地區：僅有實作 fill_locations() 的來源支援（目前 recruit）；
            # 其餘來源警告一次後忽略，絕不中斷——跨站隔離鐵律。
            if fill_location:
                if hasattr(self, "fill_locations"):
                    try:
                        self.fill_locations(jobs)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("[%s] 補地區失敗：%s", self.source, e)
                elif not self._warned_fill_location:
                    logger.warning(
                        "[%s] 不支援 --fill-location（此來源列表已含地區，或無補充機制），"
                        "已忽略", self.source)
                    self._warned_fill_location = True

            if with_detail:
                for j in jobs:
                    if j.url:
                        try:
                            det = self._with_retry(self.get_detail, j.url)
                            if det:
                                # 合併詳情（保留 list 層級已抓到的欄位）
                                for k in JobRecord.FIELDS:
                                    if not getattr(j, k) and getattr(det, k):
                                        setattr(j, k, getattr(det, k))
                                j.scraped_at = det.scraped_at
                        except Exception as e:  # noqa: BLE001
                            logger.warning("[%s] 詳情失敗 %s：%s", self.source, j.url, e)
                        self._sleep()

            # 按刊登日期篩選（近 N 天內）
            if days is not None:
                kept = [j for j in jobs if self._within_days(j, days)]
                dropped = len(jobs) - len(kept)
                if dropped:
                    logger.info(
                        "[%s] 已過濾 %d 筆超過 %d 天的職位。", self.source, dropped, days
                    )
                jobs = kept
                if not jobs:
                    logger.info(
                        "[%s] 本頁已無 %d 天內的職位，停止翻頁。", self.source, days
                    )
                    break

            all_jobs.extend(jobs)
            self._sleep()

        if output:
            export(all_jobs, output, fmt=fmt, incremental=True)

        logger.info(
            "[%s] 完成：成功 %d / 失敗 %d / 跳過 %d，共 %d 筆。",
            self.source, self._stats["success"], self._stats["failed"],
            self._stats["skipped"], len(all_jobs),
        )
        return all_jobs

    # ---------- 日期篩選輔助 ----------
    def _within_days(self, job: JobRecord, days: int) -> bool:
        """判斷職位是否為最近 days 天內刊登。無法判定日期者視為不符合。"""
        age = self.days_since_posted(job)
        return age is not None and age <= days

    def days_since_posted(self, job: JobRecord) -> int | None:
        """回傳職位距今天數；子類可覆寫以解析各自日期格式，無法判定回傳 None。"""
        return None

    def report(self) -> dict:
        return dict(self._stats)

    # ---------- 資源釋放 ----------
    def close(self) -> None:
        """釋放資源。預設無資源可釋；持有 requests.Session / Playwright 的子類覆寫此方法。

        （main.py 以 finally: scraper.close() 收尾；此基礎實作確保任何子類
        未覆寫時也不會 AttributeError。）"""

    def __enter__(self) -> "BaseScraper":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
