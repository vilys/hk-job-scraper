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
    # 站方是否保證列表按刊登日期「新→舊」。只有保證時，--days 才能在某頁全數過期時
    # 提早停翻（後面的頁只會更舊）。回傳順序依相關性 / 推薦 / 固定 SEO 的站點為 False，
    # 否則會靜默漏抓：某頁剛好沒有 10 天內的職位，不代表後面幾頁也沒有。
    list_sorted_desc: bool = False
    # 站方的「預設排序」本身是否即新→舊（不需顯式 --sort）。
    # 只有這類站點能在 --days 且未指定 --sort 時照樣提早停翻；
    # 其餘站點 --days 不再自動改排序（見下方 date_sorted），相關性順序下不可早停。
    list_default_sorted_desc: bool = False
    # 詳情頁可覆寫 list 層級同名欄位的白名單（opt-in，預設空）。
    # 既有政策是「list 層級優先、detail 只補空欄位」；只有詳情值確實更完整
    # 且據點顯式宣告時才覆寫，其餘據點行為完全不變。
    detail_replace_fields: frozenset[str] = frozenset()
    # 模組是否可預設執行。--source all 只跑 enabled 的站；
    # 已判定不可行（登入牆 / 無香港職缺）或具 IP 封鎖風險的站設 False，
    # 仍可用 --source <name> 單獨指定。
    enabled: bool = True

    def __init__(self, headers: dict | None = None):
        self.headers = dict(DEFAULT_HEADERS)
        if headers:
            self.headers.update(headers)
        self.session = None      # 由子類（requests / playwright）自行管理
        self._stats = {"success": 0, "failed": 0, "skipped": 0}
        self._warned_fill_location = False   # --fill-location 不支援時只警告一次
        self.last_error: str | None = None   # 最近一次搜尋頁失敗原因（供呼叫端判定 status=failed）

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

    def _start_playwright(self):
        """啟動 sync Playwright，並確保失敗時不留半啟動狀態。

        若前一次 start() 成功但 launch() 失敗（例如瀏覽器未安裝），殘留的 driver
        會讓下一次 start() 拋出「Sync API inside the asyncio loop」——真實原因
        （Executable doesn't exist）因此被蓋掉。這裡先收掉舊的再重開。
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "此據點需要 Playwright：pip install playwright && playwright install chromium"
            ) from e
        old = getattr(self, "_pw", None)
        if old is not None:
            try:
                old.stop()
            except Exception:  # noqa: BLE001
                pass
            self._pw = None
        self._pw = sync_playwright().start()
        return self._pw

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
        # 每次 scrape_all 都是獨立的一輪，先清掉上一輪的失敗記號
        self.last_error = None

        # 站方端日期過濾掛載點：有實作 set_days() 的來源可把 --days 直接下推到搜尋請求
        # （linkedin 的 f_TPR、gov_hk 的 criteria.postedDtFr/To…）。
        # ⚠️ 必須在下方 with_detail 判斷「之前」執行：否則 list_has_date=False 的來源
        # （如 gov_hk）會先被強制成「逐筆抓詳情取日期」，站方端過濾就白做了。
        # 其餘來源沒有此方法 → 整段跳過，行為完全不變（跨站隔離鐵律）。
        if days is not None and hasattr(self, "set_days"):
            try:
                self.set_days(days)
            except Exception as e:  # noqa: BLE001
                logger.warning("[%s] 站方端日期過濾設定失敗：%s", self.source, e)

        # 按日期篩選：若列表頁已含日期（list_has_date），直接以列表資料過濾；
        # 否則必須抓詳情以取得 posted_date。
        # ⚠️ --days 只做「日期過濾」，不再自動把排序改成 post_dt_desc：
        # 那會讓 JobsDB 的 analyst 搜尋被「1 分鐘前刊登」的 Dealer／會計淹沒。
        # 想按日期排，請明確指定 --sort post_dt_desc。
        if days is not None and not self.list_has_date:
            with_detail = True
        date_sorted = (
            sort == "post_dt_desc"
            or (sort is None and self.list_default_sorted_desc)
        )

        all_jobs: list[JobRecord] = []
        for page in range(1, max_pages + 1):
            try:
                jobs = self._with_retry(
                    self.search, keyword, page, district,
                    category=category, industry=industry, sort=sort,
                )
            except Exception as e:  # noqa: BLE001
                self.last_error = f"搜尋第 {page} 頁失敗：{e}"
                logger.error("[%s] %s", self.source, self.last_error)
                break

            if not jobs:
                logger.info("[%s] 第 %d 頁無結果，停止翻頁。", self.source, page)
                break

            logger.info("[%s] 第 %d 頁取得 %d 筆。", self.source, page, len(jobs))

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
                                # 合併詳情：預設保留 list 層級已抓到的欄位、
                                # detail 只補空；白名單內的欄位在詳情值較完整時覆寫。
                                for k in JobRecord.FIELDS:
                                    new_val = getattr(det, k)
                                    if not new_val:
                                        continue
                                    old_val = getattr(j, k)
                                    if not old_val:
                                        setattr(j, k, new_val)
                                    elif (k in self.detail_replace_fields
                                          and len(str(new_val)) > len(str(old_val))):
                                        setattr(j, k, new_val)
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
                    # 只有「站方保證新→舊」且本次確實是日期排序時，後面的頁才必然更舊。
                    # 未指定 --sort 時不可再假定 post_dt_desc（見上方 date_sorted）。
                    sorted_desc = self.list_sorted_desc and date_sorted
                    if sorted_desc:
                        logger.info(
                            "[%s] 本頁已無 %d 天內的職位，停止翻頁。", self.source, days
                        )
                        break
                    logger.info(
                        "[%s] 本頁無 %d 天內的職位，但站方不保證日期排序，繼續翻頁。",
                        self.source, days,
                    )

            all_jobs.extend(jobs)
            self._stats["success"] += len(jobs)   # 只計入通過篩選、實際保留的筆數
            self._sleep()

        # 全數頁面失敗時不得偽裝成「查無結果」：向呼叫端拋出，讓 hkjobs CLI 的
        # _run_one 標記 status=failed（exit 4 / all_sources_failed）。
        # 已有成功資料則保留部分結果，只在 stderr 留下錯誤，不改既有行為。
        if self.last_error and not all_jobs:
            raise RuntimeError(self.last_error)

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
