"""JobsDB (hk.jobsdb.com) 爬蟲。

逆向要點（詳見 README「🧭 技術筆記（JobsDB）」）：
- 反爬：Cloudflare。用 Playwright 真瀏覽器共享 cf_clearance，不硬撞。
- 搜尋機制：SSR 頁面  /jobs?keywords=K&page=N ，職位卡片以
  data-automation='normalJob' 渲染（非 GraphQL 列表呼叫，故單頁一次 GET 即可）。
- 翻頁：URL 加  ?page=N （首頁 /jobs?keywords=K 會 301 轉為 /K-jobs，page 參數保留）。
- 詳情頁：/job/<id> ，同樣靠 data-automation 屬性解析。
- 地區 / 分類（職能）：JobsDB 使用自有 slug 體系（與 Moovup / 勞工處 完全獨立）。
  職能瀏覽網址為 /jobs-in-<classification-slug>（如 information-communication-technology），
  地區以 /in-<district-slug> 串接（如 /jobs-in-<職能>/in-<地區>）；字典見
  scrapers/jobsdb_classifications.json / jobsdb_districts.json。--district / --category 已實作；
  --industry 在 JobsDB 無此維度（職能已涵蓋），忽略並提示。
- 排序（--sort）：JobsDB 網站 UI 僅提供兩種排序——「相關性（Relevance，預設，不帶參數）」
  與「刊登日期（Date）」。Date 由網址查詢參數 sortmode 控制：?sortmode=ListedDate = 新→舊
  （已實測：1h→2h→3h 遞增）。故 --sort 在本站只支援 post_dt_desc（對應 ListedDate）；
  其餘選項（post_dt_asc / salary_* / yr_exp_* / edu_lvl_*）為 gov_hk 專有，JobsDB 無對應，
  傳入會警告並回退網站預設（Relevance）。sortmode 可與 keywords/page/地區瀏覽網址共存（站方
  會將 /jobs?keywords=K&page=N&sortmode=ListedDate 301 正規化為 /K-jobs?...，Playwright 自動跟隨）。
- 刊登日為「相對時間」字串（7d ago / 13h ago / Just now），用 days_since_posted() 解析。
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote, urljoin

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover — 允許「只裝 requests」的極簡安裝
    sync_playwright = None

from config import DEFAULT_HEADERS
from job_model import JobRecord
from base_scraper import BaseScraper

logger = logging.getLogger(__name__)

BASE = "https://hk.jobsdb.com"
LIST_URL = BASE + "/jobs"

# ---- JobsDB 自有 slug 字典（與 Moovup / 勞工處 完全獨立，見 README 鐵律） ----
_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_dict(name: str) -> list:
    """讀取 slug 字典。讀取失敗時警告並回空清單（與 gov_hk / moovup / linkedin
    的守護一致），避免字典檔缺損令整個 scrapers 套件 import 失敗、五站全滅。"""
    try:
        with open(os.path.join(_HERE, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning("[jobsdb] 讀取字典 %s 失敗（--category/--district 將不可用）：%s", name, e)
        return []


# 職能（分類）字典：list of {name(英), zh(中), slug}
_CLASSIFICATIONS = _load_dict("jobsdb_classifications.json")
# 地區字典：list of {zh, slug}
_DISTRICTS = _load_dict("jobsdb_districts.json")

_CAT_BY_ZH = {c["zh"]: c["slug"] for c in _CLASSIFICATIONS}
_CAT_BY_EN = {c["name"].lower(): c["slug"] for c in _CLASSIFICATIONS}
_CAT_BY_SLUG = {c["slug"]: c["slug"] for c in _CLASSIFICATIONS}
_DIST_BY_ZH = {d["zh"]: d["slug"] for d in _DISTRICTS}
_DIST_BY_SLUG = {d["slug"]: d["slug"] for d in _DISTRICTS}

# 詳情頁候選 data-automation 選擇器（v1 依實測微調）
_DETAIL_SELECTORS = {
    "title": ["job-detail-title", "jobTitle"],
    "company": ["jobCompany"],
    "location": ["jobLocation", "jobCardLocation"],
    "salary": ["jobSalary"],
    "description": ["jobDescription", "jobShortDescription"],
    "requirements": ["jobRequirements"],
    "classification": ["jobClassification"],
    "subclassification": ["jobSubClassification"],
    "listing_date": ["jobListingDate"],
}


class JobsDBScraper(BaseScraper):
    source = "jobsdb"
    use_browser = True
    list_has_date = True   # 列表頁已含相對刊登日（jobListingDate），--days 不必抓詳情

    def __init__(self, headers: Optional[dict] = None):
        super().__init__(headers)
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._daterange: str = ""      # 站方端日期過濾（daterange=N），由 set_days() 注入

    # ---------- 站方端日期過濾掛載點（base_scraper.scrape_all 呼叫） ----------
    def set_days(self, days: int) -> None:
        """把 --days 下推成 JobsDB 的 `daterange=N`。

        ⚠️ 2026-09-10 逆向：站方側邊欄「Date posted」篩選器只給**五個離散值**
        （連結直接印在頁面上）：
            Today        → daterange=1
            Last 3 days  → daterange=3
            Last 7 days  → daterange=7
            Last 14 days → daterange=14
            Last 30 days → daterange=31   ← 注意是 31 不是 30
        只吃這五個值；送其他數字（如 daterange=10）站方不予理會。
        故取「不小於請求天數的最小合法值」；超過 31 天則不啟用站方端，
        退回客戶端篩選（列表本就含 jobListingDate，不會少抓）。
        """
        try:
            n = int(days)
        except (TypeError, ValueError):
            logger.warning("[jobsdb] --days %r 無法轉為整數，已忽略站方端過濾", days)
            return
        if n <= 0:
            return
        allowed = (1, 3, 7, 14, 31)
        picked = next((v for v in allowed if v >= n), None)
        if picked is None:
            logger.warning(
                "[jobsdb] --days %d 超出站方端上限（daterange 最大 31），"
                "僅由客戶端以列表 jobListingDate 篩選", n)
            return
        if picked != n:
            logger.info("[jobsdb] --days %d 無對應值，向上取整為 daterange=%d", n, picked)
        self._daterange = str(picked)
        logger.info("[jobsdb] 已啟用站方端日期過濾 daterange=%s", self._daterange)

    # ---------- 瀏覽器（共用一個 session，拿 cf clearance） ----------
    def _ensure_browser(self) -> None:
        if self._browser is not None:
            return
        if sync_playwright is None:
            raise RuntimeError(
                "此據點需要 Playwright：pip install playwright && playwright install chromium"
            )
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            user_agent=DEFAULT_HEADERS["User-Agent"] + " zh-HK,zh;q=0.9,en;q=0.8",
            locale="zh-HK",
        )
        self._page = self._context.new_page()
        # 先訪首頁取得 Cloudflare clearance cookie（避免每頁重挑戰）
        try:
            self._page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_timeout(2000)
            logger.info("[jobsdb] 瀏覽器就緒（cf clearance 已取得）")
        except Exception as e:  # noqa: BLE001
            logger.warning("[jobsdb] 首頁預熱失敗（可能仍需挑戰）：%s", e)

    # ---------- slug 解析（JobsDB 自有體系） ----------
    @staticmethod
    def _derive_slug(text: str) -> str:
        """把任意文字推導成 JobsDB 風格 slug：小寫、&→and、去標點、空白→連字號。"""
        s = (text or "").lower().strip()
        s = s.replace("&", "and")
        s = re.sub(r"[^a-z0-9]+", "-", s)
        return s.strip("-")

    def resolve_category(self, value: str | None) -> str | None:
        """職能名（中/英/slug）→ slug。找不到則推導並警告（中文名無法推導，回 None）。"""
        v = (value or "").strip()
        if not v:
            return None
        if v in _CAT_BY_ZH:
            return _CAT_BY_ZH[v]
        if v.lower() in _CAT_BY_EN:
            return _CAT_BY_EN[v.lower()]
        if v in _CAT_BY_SLUG:
            return v
        # 中文名無法由字面推導 slug；英文/混合可嘗試
        if re.search(r"[\u4e00-\u9fff]", v):
            logger.warning("[jobsdb] 職能 %r 不在字典，忽略分類篩選（可用英文或 slug）", v)
            return None
        slug = self._derive_slug(v)
        logger.warning("[jobsdb] 職能 %r 不在字典，推導 slug=%r（未驗證）", v, slug)
        return slug

    def resolve_district(self, value: str | None) -> str | None:
        """地區名（中/英/slug）→ slug。多個以逗號分隔時取第一個並警告。"""
        v = (value or "").strip()
        if not v:
            return None
        parts = [p.strip() for p in v.split(",") if p.strip()]
        if len(parts) > 1:
            logger.warning("[jobsdb] 地區僅支援單一值，取第一個 %r（忽略 %s）",
                           parts[0], parts[1:])
        v = parts[0]
        if v in _DIST_BY_ZH:
            return _DIST_BY_ZH[v]
        if v in _DIST_BY_SLUG:
            return v
        slug = self._derive_slug(v)
        if slug in _DIST_BY_SLUG:
            return slug
        logger.warning("[jobsdb] 地區 %r 不在字典，推導 slug=%r（未驗證，可能導向首頁）", v, slug)
        return slug

    def resolve_sort(self, value: str | None) -> str | None:
        """將 --sort 選項對應到 JobsDB 網址參數 sortmode。

        JobsDB 網站 UI 僅提供「相關性（預設，不帶參數）」與「刊登日期（Date）」兩種排序。
        - post_dt_desc -> "ListedDate"（新→舊，已實測 1h→2h→3h 遞增）
        - 其餘選項（post_dt_asc / salary_* / yr_exp_* / edu_lvl_*）為 gov_hk 專有，
          JobsDB 無對應 UI，警告並回退 None（= 網站預設 Relevance）。
        """
        if not value:
            return None
        if value == "post_dt_desc":
            return "ListedDate"
        logger.warning(
            "[jobsdb] --sort %r 不適用 JobsDB（僅支援 post_dt_desc=按刊登日期新→舊；"
            "salary_*/yr_exp_*/edu_lvl_* 為 gov_hk 專有，post_dt_asc 無對應），"
            "已忽略並改用網站預設排序（相關性）", value)
        return None

    def _build_url(self, keyword: str, district: str | None, category: str | None,
                   page: int, sort: str | None = None) -> str:
        """組出 JobsDB 瀏覽網址：
        - 有職能：/jobs-in-<cat>  [ + /in-<dist> ]  [ ?keywords=K ] [ &page=N ] [ &sortmode=X ]
        - 無職能有地區：/jobs/in-<dist>  [ ?keywords=K ] [ &page=N ] [ &sortmode=X ]
        - 皆無：/jobs  [ ?keywords=K ] [ &page=N ] [ &sortmode=X ]
        翻頁：page>1 才加 page 參數（首頁省略，符合 JobsDB 行為）。
        排序：post_dt_desc -> sortmode=ListedDate（新→舊），其餘忽略（見 resolve_sort）。
        sortmode 與 keywords/page/地區瀏覽網址共存；站方會將 /jobs?keywords=K&... 301 為 /K-jobs?...。
        """
        cat_slug = self.resolve_category(category) if category else None
        dist_slug = self.resolve_district(district) if district else None
        sortmode = self.resolve_sort(sort) if sort else None

        if cat_slug:
            path = f"/jobs-in-{cat_slug}"
            if dist_slug:
                path += f"/in-{dist_slug}"
        elif dist_slug:
            path = f"/jobs/in-{dist_slug}"
        else:
            path = "/jobs"

        params = []
        if keyword:
            params.append(f"keywords={quote(keyword)}")
        if page and page > 1:
            params.append(f"page={page}")
        if sortmode:
            params.append(f"sortmode={sortmode}")
        if self._daterange:
            # 站方端日期過濾（僅 1/3/7/14/31 五個合法值，見 set_days）
            params.append(f"daterange={self._daterange}")
        if params:
            path += "?" + "&".join(params)
        return BASE + path

    # ---------- 搜尋 ----------
    def search(
        self,
        keyword: str,
        page: int = 1,
        district: Optional[str] = None,
        category: Optional[str] = None,
        industry: Optional[str] = None,
        sort: Optional[str] = None,
    ) -> list[JobRecord]:
        self._ensure_browser()
        # JobsDB 無獨立「行業」維度（職能分類已涵蓋行業語意），忽略並提示
        if industry:
            logger.warning(
                "[jobsdb] --industry 不適用 JobsDB（職能分類已涵蓋行業語意），已忽略")
        url = self._build_url(keyword, district, category, page, sort=sort)
        logger.info("[jobsdb] GET %s", url)
        self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        self._page.wait_for_timeout(3000)  # 等 SSR + 客戶端渲染卡片
        cards = self._page.query_selector_all("[data-automation='normalJob']")
        logger.info("[jobsdb] 第 %d 頁卡片數：%d", page, len(cards))
        return [self._parse_card(c) for c in cards]

    @staticmethod
    def _parse_card(card) -> JobRecord:
        def _txt(da: str) -> str:
            el = card.query_selector(f"[data-automation='{da}']")
            return el.inner_text().strip() if el else ""

        def _href(da: str) -> str:
            el = card.query_selector(f"[data-automation='{da}']")
            return el.get_attribute("href") if el else ""

        title = _txt("jobTitle")
        h = _href("jobTitle")
        m = re.search(r"/job/(\d+)", h or "")
        jid = m.group(1) if m else (h or title)
        classification = _txt("jobClassification").strip("() ").strip()
        sub = _txt("jobSubClassification")
        industry = classification or sub
        now = datetime.now().isoformat(timespec="seconds")
        return JobRecord(
            job_id=f"jobsdb_{jid}",
            source="jobsdb",
            title=title,
            company=_txt("jobCompany"),
            location=_txt("jobCardLocation") or _txt("jobLocation"),
            salary=_txt("jobSalary"),
            job_type="",
            description=_txt("jobShortDescription"),
            requirements="",
            url=urljoin(BASE, h) if h else "",
            posted_date=_txt("jobListingDate"),
            scraped_at=now,
            industry=industry,
        )

    # ---------- 詳情（2026-09-08 實測修正 selector） ----------
    # ⚠️ 舊版用的是 jobCompany / jobLocation / jobClassification / jobDescription，
    #    實測頁面上根本不存在這些 data-automation 值 → 只有標題抓得到，其餘全空。
    #    正確對照（實測列舉）：
    #      job-detail-title          → 職位名稱
    #      advertiser-name           → 公司（不是 jobCompany）
    #      job-detail-location       → 地區（不是 jobLocation）
    #      job-detail-classifications→ 職能／行業「細類 (大類)」
    #      job-detail-work-type      → 僱傭類型（Contract/Temp、Full Time…）
    #      jobAdDetails              → 完整描述
    #    薪資無穩定 data-automation（job-detail-add-expected-salary 是「登入查看」提示，
    #    非實際薪資）→ 留空，不硬湊。
    def get_detail(self, job_url: str) -> Optional[JobRecord]:
        self._ensure_browser()
        self._page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
        self._page.wait_for_timeout(2500)

        def _txt(da: str) -> str:
            el = self._page.query_selector(f"[data-automation='{da}']")
            return el.inner_text().strip() if el else ""

        jid = re.search(r"/job/(\d+)", job_url)
        jid = jid.group(1) if jid else job_url
        now = datetime.now().isoformat(timespec="seconds")
        return JobRecord(
            job_id=f"jobsdb_{jid}",
            source="jobsdb",
            title=_txt("job-detail-title") or _txt("jobTitle"),
            company=_txt("advertiser-name"),
            location=_txt("job-detail-location"),
            salary=_txt("job-detail-salary") or _txt("jobSalary"),
            job_type=_txt("job-detail-work-type"),
            description=_txt("jobAdDetails"),
            requirements="",
            url=job_url,
            posted_date=_txt("jobListingDate"),
            scraped_at=now,
            industry=_txt("job-detail-classifications"),
        )

    # ---------- 相對時間解析（"7d ago" -> 7；"13h ago"/"Just now" -> 0） ----------
    def days_since_posted(self, job: JobRecord) -> Optional[int]:
        raw = (job.posted_date or "").strip().lower()
        if not raw:
            return None
        if "just now" in raw or raw == "now":
            return 0
        m = re.match(r"(\d+)\s*([dhms])", raw)
        if not m:
            return None
        n = int(m.group(1))
        unit = m.group(2)
        return 0 if unit in ("h", "m", "s") else n

    def close(self) -> None:
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:  # noqa: BLE001
            pass
        self._browser = self._context = self._page = self._pw = None

    def report(self) -> dict:
        return dict(self._stats)
