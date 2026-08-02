"""Indeed (hk.indeed.com) 爬蟲。

逆向要點（詳見 README「🧭 技術筆記（Indeed）」）：
- 反爬：Cloudflare「Just a moment...」挑戰頁。plain requests → 403；
  用 Playwright headless Chromium 可過（約 4 秒自動通過，輪詢 job_seen_beacon 出現）。
  全程共用同一 BrowserContext，先取 cf_clearance 再翻頁（不重建不重挑戰）。
- 搜尋機制：SSR + 客戶端渲染。搜尋網址
  https://hk.indeed.com/jobs?q=KEYWORD&l=LOCATION&start=N （start 步長 10，首頁不加）。
- 職位卡：.job_seen_beacon（每頁 ~16 張，表格佈局）。
  標題 a.jcs-JobTitle（含 data-jk 屬性 = 職位 ID，如 7b8620949d7f8b54）；
  公司 span[data-testid='company-name']；地點 div[data-testid='text-location']；
  薪資為卡片內文文字（如「$18,000 - $30,000 a month」），無專屬元素，以正則抓取。
- 刊登日：列表卡可見 HTML（inner_text）不含日期，但 Indeed 在內嵌的
  mosaic provider JSON（window.mosaic.providerData["mosaic-provider-jobcards"]）
  中為每個職位提供 pubDate（毫秒戳）。故在 search() 解析卡片後，直接從
  page.content() 抽 pubDate→jk 對照表，寫入 posted_date（折算為「N day ago」）。
  list_has_date 設為 True，--days 篩選**無需**逐張點擊詳情（瞬時完成）。
- 詳情頁：viewjob?jk=<id> 直連會**重觸發 Cloudflare（40s 仍被擋）**；
  但從搜尋頁「點擊職位連結」開側面板（SPA）則不重觸發（cf_clearance 沿用），
  2~3 秒內載入，詳情 HTML 含 datePublished 毫秒戳與 age:"X days ago"。
  故 get_detail() 實作為「在當前搜尋頁點擊對應卡片」而非直連 viewjob。
- 地區：Indeed 用 l= 自由文字（與 Moovup 的 shortCode、勞工處數字 ID、JobsDB 的 slug 完全獨立）。
  --district 直接作為 l= 文字（預設 Hong Kong）；LinkedIn 的 18 區字典不適用於此。
- 不支援：--category / --industry（Indeed HK 搜尋無對應乾淨維度，傳入忽略並提示）；
  --sort（Indeed 排序需登入態 facet，訪客模式忽略並提示）。
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from base_scraper import BaseScraper
from config import DEFAULT_HEADERS
from job_model import JobRecord

logger = logging.getLogger(__name__)

BASE = "https://hk.indeed.com"
SEARCH_URL = BASE + "/jobs"
DETAIL_URL = BASE + "/viewjob"

# 日期單位 → 天數倍率（用於 age 文字與 timestamp 計算）
_DATE_UNIT_DAYS = {"hour": 0, "day": 1, "week": 7, "month": 30}


class IndeedScraper(BaseScraper):
    source = "indeed"
    use_browser = True
    # 列表內嵌 mosaic provider JSON 含 pubDate（毫秒戳），search() 解析後寫入
    # posted_date（折算「N day ago」），故 --days 篩選無需抓詳情（瞬時）。
    list_has_date = True

    def __init__(self, headers: Optional[dict] = None):
        super().__init__(headers)
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._last_search_url = None   # 供 get_detail 點擊失敗時重新 goto

    # ---------- 瀏覽器（共用一個 session） ----------
    def _ensure_browser(self) -> None:
        if self._browser is not None:
            return
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            user_agent=DEFAULT_HEADERS["User-Agent"],
            locale="en-US",
        )
        self._page = self._context.new_page()
        logger.info("[indeed] 瀏覽器就緒（首次訪問搜尋頁時取得 cf clearance）")

    # ---------- 網址組裝（Indeed 自有體系） ----------
    @staticmethod
    def _location_of(district: Optional[str]) -> str:
        """--district 直接作為 Indeed l= 自由文字；預設 Hong Kong。"""
        v = (district or "").strip()
        return v or "Hong Kong"

    @staticmethod
    def _build_url(keyword: str, district: Optional[str], page: int) -> str:
        loc = IndeedScraper._location_of(district)
        params = [f"q={quote(keyword)}" if keyword else "",
                  f"l={quote(loc)}"]
        if page and page > 1:
            params.append(f"start={(page - 1) * 10}")   # 每頁 10 筆
        params = [p for p in params if p]
        return SEARCH_URL + "?" + "&".join(params)

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
        # Indeed 無職能/行業/排序（訪客）對應維度，忽略並提示（跨站隔離：不影響他站）
        if category:
            logger.warning("[indeed] --category 不適用 Indeed（無對應維度），已忽略")
        if industry:
            logger.warning("[indeed] --industry 不適用 Indeed（無對應維度），已忽略")
        if sort:
            logger.warning(
                "[indeed] --sort 不適用 Indeed 訪客模式（排序需登入態 facet），已忽略")

        url = self._build_url(keyword, district, page)
        self._last_search_url = url   # 供 get_detail 點擊失敗時重新 goto
        logger.info("[indeed] GET %s", url)
        self._page.goto(url, wait_until="domcontentloaded", timeout=45000)

        # 輪詢等待 Cloudflare 過關 + 職位卡渲染（最多 ~45 秒）
        beacons = []
        for _ in range(15):
            time.sleep(3)
            beacons = self._page.query_selector_all(".job_seen_beacon")
            if beacons:
                break
        if not beacons:
            logger.warning("[indeed] 第 %d 頁無職位卡（可能被 Cloudflare 擋或已無結果）", page)
            return []

        records = [self._parse_card(b) for b in beacons]
        # 從內嵌 mosaic provider JSON 抽 pubDate→jk，寫入 posted_date（--days 用，瞬時）
        try:
            html = self._page.content()
            date_map = self._build_pubdate_map(html)
            if date_map:
                for rec in records:
                    jk = self._jk_from_url(rec.url)
                    if jk and jk in date_map:
                        rec.posted_date = self._pubdate_to_rel(date_map[jk])
                logger.info("[indeed] 第 %d 頁已從內嵌 JSON 取得 %d/%d 筆刊登日",
                            page, sum(1 for r in records if r.posted_date), len(records))
        except Exception as e:  # noqa: BLE001
            logger.warning("[indeed] 內嵌刊登日解析失敗（--days 將退化为抓詳情）：%s", e)

        logger.info("[indeed] 第 %d 頁卡片數：%d", page, len(records))
        return records

    # ---------- 內嵌刊登日（mosaic provider pubDate） ----------
    @staticmethod
    def _build_pubdate_map(html: str) -> dict:
        """從 page.content() 抽 pubDate（毫秒戳）→ jk 對照表。

        Indeed 把每個職位的 pubDate 放在內嵌的 mosaic provider JSON 裡，
        與 jobKey 位於同一職位物件（前後 ~9KB 範圍內）。以 pubDate 位置為錨點，
        往前掃描最近的一個 jobKey / jk=，即為該職位的 jk。
        """
        pubs = [m.start() for m in re.finditer(r'"pubDate":(\d{13})', html)]
        out = {}
        for pos in pubs:
            window = html[max(0, pos - 9000):pos]
            jks = re.findall(r'"jobKey":"([a-f0-9]{16,32})"', window)
            jk2 = re.findall(r'jk=([a-f0-9]{16,32})', window)
            jk = jks[-1] if jks else (jk2[-1] if jk2 else None)
            if not jk:
                continue
            mm = re.search(r'"pubDate":(\d{13})', html[pos:pos + 30])
            if mm:
                out[jk] = int(mm.group(1))
        return out

    @staticmethod
    def _pubdate_to_rel(pubdate_ms: int) -> str:
        """pubDate 毫秒戳 → 'N day ago'（與 days_since_posted 解析相容）。"""
        diff = time.time() * 1000 - pubdate_ms
        if diff < 0:
            diff = 0
        days = int(diff // 86400000)
        return f"{days} day ago"

    @staticmethod
    def _parse_card(card) -> JobRecord:
        title_el = card.query_selector("a.jcs-JobTitle")
        title = ""
        jk = None
        if title_el:
            span = title_el.query_selector("span")
            title = span.inner_text().strip() if span else title_el.inner_text().strip()
            jk = title_el.get_attribute("data-jk")
        co_el = card.query_selector("span[data-testid='company-name']")
        company = co_el.inner_text().strip() if co_el else ""
        loc_el = card.query_selector("div[data-testid='text-location']")
        location = loc_el.inner_text().strip() if loc_el else ""

        # 薪資：卡片內文文字（如「$18,000 - $30,000 a month」），正則抓取
        salary = ""
        full = card.inner_text()
        m = re.search(r"\$[\d,]+(?:\s*-\s*\$[\d,]+)?\s*(?:a\s+month|per\s+hour|a\s+year|per\s+month|per\s+annum)?", full)
        if m and "$" in m.group(0):
            salary = m.group(0).strip()

        now = datetime.now().isoformat(timespec="seconds")
        url = f"{DETAIL_URL}?jk={jk}" if jk else ""
        return JobRecord(
            job_id=JobRecord.make_id("indeed", jk) if jk else JobRecord.make_id("indeed", title),
            source="indeed",
            title=title,
            company=company,
            location=location,
            salary=salary,
            job_type="",
            industry="",
            description="",
            requirements="",
            url=url,
            posted_date="",   # search() 隨後從內嵌 pubDate 補寫
            scraped_at=now,
        )

    # ---------- 詳情（點擊開側面板，避開 viewjob 直連的 CF） ----------
    def get_detail(self, job_url: str) -> Optional[JobRecord]:
        self._ensure_browser()
        jk = self._jk_from_url(job_url)
        if not jk:
            return None

        # 嘗試在當前搜尋頁點擊對應卡片（不重觸發 CF）。
        # 用 JS element.click() 直接派發點擊事件，繞過「面板遮住卡片導致
        # Playwright .click() 判定 element is not visible」的問題，避免逐張 re-goto。
        if self._page.query_selector(f'a[data-jk="{jk}"]'):
            try:
                self._js_click_card(jk)
                self._page.wait_for_selector(
                    "#jobDescriptionText, .jobsearch-jobDescriptionText", timeout=15000)
                html = self._page.content()
                posted = self._extract_date(html)
                description = self._extract_description(html)
                if posted or description:
                    return self._build_detail_record(jk, posted, description, job_url)
            except Exception as e:  # noqa: BLE001
                logger.warning("[indeed] 點擊開詳情失敗（%s），重新 goto 搜尋頁再點", e)

        # 回退：重新 goto 搜尋頁（cf_clearance 已種，很快），再 JS 點該卡。
        if self._last_search_url:
            try:
                self._page.goto(self._last_search_url, wait_until="domcontentloaded", timeout=30000)
                for _ in range(15):
                    time.sleep(3)
                    if self._page.query_selector_all(".job_seen_beacon"):
                        break
                if self._page.query_selector(f'a[data-jk="{jk}"]'):
                    self._js_click_card(jk)
                    self._page.wait_for_selector(
                        "#jobDescriptionText, .jobsearch-jobDescriptionText", timeout=15000)
                    html = self._page.content()
                    posted = self._extract_date(html)
                    description = self._extract_description(html)
                    return self._build_detail_record(jk, posted, description, job_url)
            except Exception as e:  # noqa: BLE001
                logger.warning("[indeed] 重新 goto 後點擊仍失敗 %s：%s", job_url, e)

        # 最後回退：直連 viewjob（可能觸發 CF，盡力而為）
        try:
            self._page.goto(f"{DETAIL_URL}?jk={jk}", wait_until="domcontentloaded", timeout=30000)
            for _ in range(10):
                time.sleep(3)
                if "jobDescriptionText" in self._page.content():
                    break
            html = self._page.content()
            posted = self._extract_date(html)
            description = self._extract_description(html)
        except Exception as e:  # noqa: BLE001
            logger.warning("[indeed] 直連 viewjob 失敗 %s：%s", job_url, e)
        return self._build_detail_record(jk, posted, description, job_url)

    # ---------- 詳情輔助 ----------
    def _js_click_card(self, jk: str) -> None:
        """以 JS element.click() 直接派發點擊，觸發 Indeed SPA 開側面板。
        比 Playwright .click() 更穩健：不受面板遮罩造成的 visibility 判定影響。"""
        self._page.evaluate(
            """(jk) => {
                const el = document.querySelector('a[data-jk="' + jk + '"]');
                if (el) el.click();
            }""", jk)

    @staticmethod
    def _jk_from_url(url: str) -> Optional[str]:
        m = re.search(r"jk=([a-f0-9]{16,32})", url or "")
        return m.group(1) if m else None

    @staticmethod
    def _extract_date(html: str) -> str:
        """從詳情 HTML 抓刊登日：優先 age 文字（'10 days ago'），
        回退 datePublished 毫秒戳轉相對。"""
        m = re.search(r"(?:Employer\s*Active|Posted|Active)\s+(\d+)\s*(day|hour|week|month)s?\s+ago", html)
        if m:
            return f"{m.group(1)} {m.group(2)} ago"
        ts = re.search(r'"datePublished"\s*:\s*(\d{13})', html)
        if ts:
            try:
                ms = int(ts.group(1))
                days = (time.time() * 1000 - ms) / 86400000
                if days < 1:
                    return "0 day ago"
                return f"{int(days)} day ago"
            except Exception:  # noqa: BLE001
                pass
        return ""

    @staticmethod
    def _extract_description(html: str) -> str:
        m = re.search(r'id="jobDescriptionText"[^>]*>(.*?)</div>', html, re.S)
        if m:
            raw = m.group(1)
            # 去標籤
            text = re.sub(r"<[^>]+>", " ", raw)
            return re.sub(r"\s+", " ", text).strip()
        return ""

    @staticmethod
    def _build_detail_record(jk: str, posted: str, description: str, url: str) -> JobRecord:
        now = datetime.now().isoformat(timespec="seconds")
        return JobRecord(
            job_id=JobRecord.make_id("indeed", jk),
            source="indeed",
            title="",
            company="",
            location="",
            salary="",
            job_type="",
            industry="",
            description=description,
            requirements="",
            url=url,
            posted_date=posted,
            scraped_at=now,
        )

    # ---------- 相對時間解析（'10 days ago' -> 10；'0 day ago' -> 0） ----------
    def days_since_posted(self, job: JobRecord) -> Optional[int]:
        raw = (job.posted_date or "").strip().lower()
        if not raw:
            return None
        m = re.search(r"(\d+)\s*(hour|day|week|month)s?", raw)
        if not m:
            return None
        n = int(m.group(1))
        unit = m.group(2)
        return 0 if unit == "hour" else n * _DATE_UNIT_DAYS.get(unit, 1)

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
