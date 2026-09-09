"""LinkedIn (www.linkedin.com) 爬蟲。

技術特點（詳見 README「🧭 技術筆記（LinkedIn 逆向要點）」）：
- **訪客模式即可抓**：職位搜尋結果為伺服器渲染 HTML（無須登入、無須 Playwright）。
  關鍵字搜尋 /jobs/search/?keywords=K&location=Hong%20Kong 直接回傳 ~25–60 張職位卡。
- **免登入詳情 API**：單筆職位詳情可用
  https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/<id> 取得（含完整 description）。
- **翻頁策略（2026-09-09 實測改版）**：
  - 第 1 頁走 `/jobs/search/`（一次可取數十張卡，CP 值最高，行為與舊版一致）；
  - 第 2 頁起改走訪客分頁端點 `/jobs-guest/jobs/api/seeMoreJobPostings/search`
    （`start` 為索引、每頁固定 **10** 張），可突破訪客 ~60 筆天花板——實測
    `start=10` / `20` 回傳的卡皆落在首頁結果池之外。
    ⚠️ 訪客結果會「漂移」：同一 start 每次取樣可能不同（實測 `start=25` 曾整頁落回
    首頁池），故仍以 job_id 去重累積，整頁皆已見即停止翻頁。
- **站方端日期過濾**：`--days` 會下推為 `f_TPR=r<秒數>`（經 base_scraper 的 `set_days()`
  掛載點），讓 LinkedIn 只回傳該時間窗內的職缺；未帶時會混入一年以上的舊職缺。
- **反爬與限制**：LinkedIn 對訪客模式有速率上限，故本爬蟲：
  (1) 請求間隔拉高到 3 秒（config.SITE_CONFIG['linkedin']）；
  (2) 跨頁用 job_id 去重，整頁皆為已見職位即停止翻頁（避免無限迴圈）；
  (3) 提供 li_at cookie（config.LINKEDIN_LI_AT / 環境變數）可解鎖最穩定翻頁（登入態）。
- **地區**：LinkedIn 的 location 是「自由文字」，與 Moovup 的 shortCode、勞工處數字 ID、
  JobsDB 的 slug 三者皆不同，不可混用。本爬蟲已逆向出香港 18 區字典
  (scrapers/linkedin_geo.json，含中文區名 / 英文 / geoUrn / 別名)。
  ⚠️ **重要發現**：訪客模式下 `geoUrn=<數字>` 參數**無效**（實測回傳非目標區、甚至美國職位），
  故一律走 `location=<英文區名>` 自由文字（英文如 "Yuen Long" 命中較穩，LinkedIn 顯示「N jobs in Yuen Long」）。
  `--district` 命中字典時自動翻譯成標準英文區名（中文「元朗」→"Yuen Long"；別名「旺角」→"Yau Tsim Mong"）；
  未命中則原樣作 location 文字（best-effort）。字典裡的 geoUrn 僅供登入態（li_at）參考、未驗證。
- **不支援維度**：--category（職能）/ --industry 在 LinkedIn 簡易搜尋無乾淨對應，警告並忽略
  （如需可用 LinkedIn 的 f_F / f_E 等編碼，留待後續）。--sort 僅支援 post_dt_desc
  （對應網址 sortBy=DD = 最新），其餘選項為 gov_hk 專有，忽略並提示。
- 刊登日為相對時間（"4 days ago" / "1 week ago" / "2 hours ago"），用 days_since_posted() 解析。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from base_scraper import BaseScraper
from config import LINKEDIN_LI_AT, REQUEST_TIMEOUT, SELECTORS
from job_model import JobRecord

logger = logging.getLogger(__name__)

BASE = "https://www.linkedin.com"
SEARCH_URL = BASE + "/jobs/search/"
# 訪客專用分頁端點（無須登入）：/jobs/search/?start=N 在訪客身分下會被隨機化/AB，
# 深翻頁不可靠；此端點是 LinkedIn 給搜尋引擎與訪客用的，start 為索引、每頁固定 10 張，
# 且卡片 <time datetime="YYYY-MM-DD"> 帶絕對刊登日。詳見 README 技術筆記。
GUEST_SEARCH_URL = BASE + "/jobs-guest/jobs/api/seeMoreJobPostings/search"
GUEST_PAGE_SIZE = 10
DETAIL_API = BASE + "/jobs-guest/jobs/api/jobPosting/"

# LinkedIn 相對刊登日單位 → 天數倍率
_DATE_UNIT_DAYS = {"hour": 0, "day": 1, "week": 7, "month": 30}

SELECT = SELECTORS.get("linkedin", {})

# 香港 18 區 geoUrn 字典（由 jobs-guest/api/typeaheadHits 逆向取得，2026-07-30）
_GEO_PATH = Path(__file__).parent / "linkedin_geo.json"
_GEO: dict = {}
try:
    _GEO = json.loads(_GEO_PATH.read_text(encoding="utf-8"))
except Exception as _e:  # pragma: no cover
    logger.warning("[linkedin] 無法載入 linkedin_geo.json：%s", _e)
_GEO_DISTRICTS: dict = _GEO.get("districts", {})
_GEO_ALIASES: dict = _GEO.get("aliases", {})


class LinkedInScraper(BaseScraper):
    source = "linkedin"
    use_browser = False
    list_has_date = True   # 列表卡已含相對刊登日（time），--days 不必抓詳情

    def __init__(self, headers: dict | None = None):
        super().__init__(headers)
        # LinkedIn 強制英文語系：確保刊登日為 "4 days ago" 格式（便於 days_since_posted 解析），
        # 地點也會是 "Hong Kong, Hong Kong SAR" 而非中文本地化，解析更穩定。
        # 必須同時覆寫 self.headers（search/get_detail 會以 self.headers 作為每次請求的標頭，
        # 其優先權高於 session.headers，故僅設 session 層不夠）。
        self.headers["Accept-Language"] = "en-US,en;q=0.9"
        self.session = requests.Session()
        self.session.headers["Accept-Language"] = "en-US,en;q=0.9"
        # 登入態 cookie（可選）：有了它翻頁才穩定
        if LINKEDIN_LI_AT:
            self.session.headers["Cookie"] = f"li_at={LINKEDIN_LI_AT}"
            logger.info("[linkedin] 已載入 li_at cookie（登入態，翻頁較穩定）")
        else:
            logger.info("[linkedin] 未提供 li_at cookie，使用訪客模式（深翻頁可能受限）")
        # 跨頁去重：記錄已見 job_id，整頁皆已見即停止翻頁
        self._seen: set[str] = set()
        # 站方端日期過濾（f_TPR），由 base_scraper 的 set_days() 掛載點注入
        self._f_tpr: str = ""

    # ---------- 站方端日期過濾掛載點（base_scraper.scrape_all 呼叫） ----------
    def set_days(self, days: int) -> None:
        """把 --days 下推成 LinkedIn 的 f_TPR（站方端過濾），省下客戶端丟棄的請求。

        f_TPR 格式為 r + 秒數：r86400=24h、r604800=7 天、r2592000=30 天。
        實測（2026-09-09）：帶 f_TPR=r604800 時回傳卡片全數落於 7 天內；
        未帶時會混入一年以上的舊職缺（如 2025-04-30）。"""
        try:
            n = int(days)
        except (TypeError, ValueError):
            logger.warning("[linkedin] --days %r 無法轉為整數，已忽略站方端過濾", days)
            return
        if n <= 0:
            return
        self._f_tpr = f"r{n * 86400}"
        logger.info("[linkedin] 已啟用站方端日期過濾 f_TPR=%s（%d 天內）", self._f_tpr, n)

    # ---------- 參數解析（LinkedIn 自有體系） ----------
    @staticmethod
    def _location_of(district: str | None) -> str:
        """--district -> LinkedIn location 自由文字（英文）。
        命中 18 區字典 / 別名 / 英文名時回標準英文區名（LinkedIn 用 location= 文字解析，
        英文名如 'Yuen Long' 命中較穩）；未命中則原樣回傳（best-effort）。預設 Hong Kong。

        ⚠️ 重要：訪客模式下 `geoUrn=<數字>` 參數**無效**（實測回傳非目標區、甚至美國職位），
        故本爬蟲一律走 `location=<英文文字>`——這在訪客模式才是有效機制。
        字典裡的 geoUrn 僅供登入態（li_at）參考，未驗證、不使用。"""
        v = (district or "").strip()
        if not v:
            return "Hong Kong"
        # 中文區名 -> 標準英文（如 元朗 -> Yuen Long）
        if v in _GEO_DISTRICTS:
            return _GEO_DISTRICTS[v].get("en") or v
        # 別名 -> 所屬區 -> 英文（如 旺角 -> 油尖旺 -> Yau Tsim Mong）
        alias = _GEO_ALIASES.get(v)
        if alias and alias in _GEO_DISTRICTS:
            return _GEO_DISTRICTS[alias].get("en") or v
        # 英文名不分大小寫比對 -> 回標準 en（如 "tsuen wan" -> Tsuen Wan）
        low = v.lower()
        for d in _GEO_DISTRICTS.values():
            if d.get("en", "").lower() == low:
                return d.get("en") or v
        # 未命中字典：原樣回傳（LinkedIn 可能仍能解析，best-effort）
        return v

    @staticmethod
    def _resolve_geo(district: str | None) -> str | None:
        """回傳 geoUrn（僅供參考；訪客模式不使用，見 _location_of 說明）。"""
        v = (district or "").strip()
        if not v:
            return None
        if v in _GEO_DISTRICTS:
            return _GEO_DISTRICTS[v]["geoUrn"]
        alias = _GEO_ALIASES.get(v)
        if alias and alias in _GEO_DISTRICTS:
            return _GEO_DISTRICTS[alias]["geoUrn"]
        low = v.lower()
        for d in _GEO_DISTRICTS.values():
            if d.get("en", "").lower() == low:
                return d["geoUrn"]
        return None

    @staticmethod
    def _resolve_sort(sort: str | None) -> str | None:
        """post_dt_desc -> sortBy=DD（最新）。其餘選項為 gov_hk 專有，忽略。"""
        if not sort:
            return None
        if sort == "post_dt_desc":
            return "DD"
        logger.warning(
            "[linkedin] --sort %r 不適用 LinkedIn（僅支援 post_dt_desc=最新優先，"
            "對應 sortBy=DD）；其餘選項為 gov_hk 專有，已忽略（使用網站預設排序）", sort)
        return None

    def _build_url(self, keyword: str, district: str | None, page: int,
                   sort: str | None) -> str:
        # 訪客模式：location= 英文文字（geoUrn 在訪客模式無效，見 _location_of）
        location = self._location_of(district)
        params = [
            f"keywords={quote(keyword)}" if keyword else "",
            f"location={quote(location)}",
        ]
        sortmode = self._resolve_sort(sort)
        if sortmode:
            params.append(f"sortBy={sortmode}")
        if self._f_tpr:
            params.append(f"f_TPR={self._f_tpr}")
        params = [p for p in params if p]

        if page <= 1:
            # 首頁走 /jobs/search/：一次可取數十張卡（實測空關鍵字約 59 張），CP 值最高
            return SEARCH_URL + "?" + "&".join(params + ["start=0"])
        # 第 2 頁起改走訪客分頁端點：/jobs/search/?start=N 在訪客身分下會被隨機化，
        # 而此端點每頁固定 10 張、start 為索引，可持續吐出新卡（實測 start=10/20 皆為
        # 首頁結果池以外的職缺）。靠 _seen 去重累積，突破訪客 ~60 筆天花板。
        start = (page - 1) * GUEST_PAGE_SIZE
        # ⚠️ 實測（2026-09-09）：帶相同 f_TPR + sortBy 時，此端點與首頁是同一個結果池，
        # 若 start 從 10 起算會整頁落在首頁已取的 58 筆內、被去重擋掉而停止翻頁。
        # 故 start 一律從「已累積筆數」接著往下走，才能真正翻到首頁以外的職缺。
        start = max(start, len(self._seen))
        return GUEST_SEARCH_URL + "?" + "&".join(params + [f"start={start}"])

    # ---------- 搜尋 ----------
    def search(
        self,
        keyword: str,
        page: int = 1,
        district: str | None = None,
        category: str | None = None,
        industry: str | None = None,
        sort: str | None = None,
    ) -> list[JobRecord]:
        # LinkedIn 簡易搜尋無 category / industry 維度
        if category:
            logger.warning("[linkedin] --category 不適用 LinkedIn 簡易搜尋，已忽略")
        if industry:
            logger.warning("[linkedin] --industry 不適用 LinkedIn 簡易搜尋，已忽略")

        url = self._build_url(keyword, district, page, sort)
        logger.info("[linkedin] GET %s", url)
        r = self.session.get(url, headers=self.headers, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.error("[linkedin] 搜尋頁 HTTP %d（可能被限流/挑戰）", r.status_code)
            return []
        soup = BeautifulSoup(r.text, "lxml")

        jobs: list[JobRecord] = []
        cards = soup.select(SELECT.get("result_list", ".jobs-search__results-list li"))
        if not cards:
            # 訪客分頁端點回傳的是裸 HTML 片段（無 .jobs-search__results-list 外層容器），
            # 退回直接取所有 li，卡片內部結構與 /jobs/search/ 完全相同。
            cards = soup.select("li")
        for li in cards:
            link = li.select_one(SELECT.get("card_link", "a.base-card__full-link"))
            if not link:
                continue
            href = link.get("href") or ""
            m = re.search(r"/jobs/view/.*-(\d+)", href)
            if not m:
                continue
            jid = m.group(1)
            job_id = JobRecord.make_id("linkedin", jid)

            title = self._txt(li, SELECT.get("title", ".base-search-card__title"))
            company = self._txt(li, SELECT.get("company", ".base-search-card__subtitle"))
            # 地點：優先用 .job-search-card__location，否則取 metadata 第一行
            loc = self._txt(li, SELECT.get("location", ".job-search-card__location"))
            if not loc:
                meta = self._txt(li, SELECT.get("metadata", ".base-search-card__metadata"))
                if meta:
                    loc = meta.split("\n")[0].strip()
            posted = self._posted_of(li)
            abs_url = urljoin(BASE, href) if href else ""

            now = datetime.now().isoformat(timespec="seconds")
            jobs.append(JobRecord(
                job_id=job_id,
                source="linkedin",
                title=title,
                company=company,
                location=loc,
                salary="",   # 訪客卡通常不含薪資
                job_type="",
                description="",
                requirements="",
                url=abs_url,
                posted_date=posted,
                scraped_at=now,
            ))

        # 跨頁去重：只回傳尚未見過的職位；若整頁皆已見（且非首頁）則回空，讓 base 停止翻頁
        new_jobs = [j for j in jobs if j.job_id not in self._seen]
        self._seen.update(j.job_id for j in jobs)
        if not new_jobs and page > 1:
            logger.info("[linkedin] 第 %d 頁無新職位，停止翻頁。", page)
            return []
        return new_jobs

    @staticmethod
    def _txt(scope, sel: str) -> str:
        el = scope.select_one(sel)
        return el.get_text(" ", strip=True) if el else ""

    @staticmethod
    def _posted_of(scope) -> str:
        """刊登日：優先用 <time datetime="YYYY-MM-DD"> 的絕對日期（訪客分頁端點提供，
        且較精確——相對時間會把 3 小時與 23 小時都當成同一天），
        否則退回卡片上的相對時間文字（"4 days ago"）。"""
        tm = scope.select_one("time")
        if tm is None:
            return ""
        dt = (tm.get("datetime") or "").strip()
        return dt or tm.get_text(" ", strip=True)

    # ---------- 詳情（免登入 guest API） ----------
    def get_detail(self, job_url: str) -> Optional[JobRecord]:
        m = re.search(r"/jobs/view/.*-(\d+)", job_url)
        if not m:
            logger.warning("[linkedin] 無法從網址解析職位 ID：%s", job_url)
            return None
        jid = m.group(1)
        api = DETAIL_API + jid
        logger.info("[linkedin] GET detail %s", api)
        r = self.session.get(api, headers=self.headers, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.error("[linkedin] 詳情 API HTTP %d", r.status_code)
            return None
        soup = BeautifulSoup(r.text, "lxml")

        title = self._txt(soup, SELECT.get("detail_title", ".top-card-layout__title"))
        company = self._txt(soup, SELECT.get("detail_company", ".topcard__flavor"))
        location = self._txt(soup, SELECT.get("detail_location", ".topcard__flavor--bullet"))
        # 選擇器清單：容忍 "," 與 ", " 兩種分隔（避免 config 字串微調令解析整串失效）
        _desc_sel = SELECT.get("detail_description",
                               ".description__text, .show-more-less-html__markup")
        desc_parts = [self._txt(soup, s) for s in (p.strip() for p in _desc_sel.split(",")) if s]
        description = "\n".join(p for p in desc_parts if p)
        # 刊登日：從詳情頂部文字抓相對時間
        posted = ""
        top = soup.select_one(".top-card-layout__card")
        if top:
            tm = re.search(r"(\d+)\s*(hour|day|week|month)s?\s+ago",
                           top.get_text(" ", strip=True), re.I)
            if tm:
                posted = tm.group(0)

        now = datetime.now().isoformat(timespec="seconds")
        return JobRecord(
            job_id=JobRecord.make_id("linkedin", jid),
            source="linkedin",
            title=title,
            company=company,
            location=location,
            salary="",
            description=description,
            requirements="",
            url=job_url,
            posted_date=posted,
            scraped_at=now,
        )

    # ---------- 相對時間解析（"4 days ago" -> 4；"2 hours ago" -> 0） ----------
    # 支援英文（預設）與中文（zh-HK 本地化備援）單位。
    _CN_UNIT_DAYS = {"小時": 0, "時": 0, "天": 1, "日": 1,
                     "週": 7, "周": 7, "個月": 30, "月": 30}

    def days_since_posted(self, job: JobRecord) -> Optional[int]:
        raw = (job.posted_date or "").strip().lower()
        if not raw:
            return None
        if "just now" in raw or "剛剛" in raw or "最近" in raw:
            return 0
        # 絕對日期（訪客分頁端點 / 首頁 <time datetime>）：YYYY-MM-DD
        # ⚠️ 必須用 group(0)（完整匹配）而非 group(1)——後者只是「年」，
        #    會讓 strptime("2026", "%Y-%m-%d") 拋錯、56 筆以上職缺被誤判為逾期。
        # 不加結尾錨點，以容忍 ISO 帶時間格式（2026-09-07T12:34:56Z）。
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
        if m:
            try:
                d = datetime.strptime(m.group(0), "%Y-%m-%d")
            except ValueError:
                return None
            return max(0, (datetime.now() - d).days)
        # 英文單位
        m = re.search(r"(\d+)\s*(hour|day|week|month)s?", raw)
        if m:
            n = int(m.group(1))
            mult = _DATE_UNIT_DAYS.get(m.group(2), None)
            if mult is None:
                return None
            return 0 if mult == 0 else n * mult
        # 中文單位（如 "4 天前" / "3 個月前" / "2 週前"）
        m = re.search(r"(\d+)\s*(小時|時|天|日|週|周|個月|月)", raw)
        if m:
            n = int(m.group(1))
            mult = self._CN_UNIT_DAYS.get(m.group(2), None)
            if mult is None:
                return None
            return 0 if mult == 0 else n * mult
        return None

    def close(self) -> None:
        if self.session:
            self.session.close()
