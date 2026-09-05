# -*- coding: utf-8 -*-
"""foundit.hk（原 Monster HK）爬蟲 — 擴充八站 Wave 2。

🌐 站點特性（2026-09-05 逆向，見 README「🧭 技術筆記（foundit 逆向要點）」）：
  - Monster 亞太區 2022 年重整品牌為 foundit；monster.com.hk 301 → www.foundit.hk。
  - **WAF 指紋封鎖**：/search/* 對 Python requests 與 Playwright 內建 Chromium headless
    一律 403 Access Denied；但 **channel="chrome"（系統 Chrome 指紋）headless 可過**。
  - 站方自己的搜尋 API `/home/api/searchResultsPage` 目前回 404（站方故障，
    瀏覽器開 /search/jobs?q= 也拿不到結果）→ **關鍵字搜尋走 SEO 瀏覽頁**：
      /search/<keyword>-jobs[-in-<location>][-<頁碼>]
    這些頁面是**伺服器端渲染**（Chrome 指紋下 SSR 20 張卡/頁），不依賴壞掉的 API。
  - 職位詳情 /job/<slug>-<id> **普通 requests 可達**（WAF 只擋 /search/*），
    內含 ld+json JobPosting（title/datePosted/jobLocation/description/employmentType）。
  - 列表卡有「Posted N hours/days ago」相對日期 → list_has_date=True，--days 瞬時。
  - 純 sitemap 保底：/xmlsitemap/active-jobs-sitemap0.xml.gz（全站 8,799 職位 + lastmod）。
  - --category / --industry / --sort：站方 SEO 瀏覽頁無對應參數 → 警告後忽略。
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from base_scraper import BaseScraper
from config import DEFAULT_HEADERS
from job_model import JobRecord

logger = logging.getLogger(__name__)

_BASE = "https://www.foundit.hk"

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

# ---- 地區字典 ----
_GEO_FILE = Path(__file__).with_name("foundit_locations.json")
_GEO: dict[str, str] = {}


def _load_geo() -> dict[str, str]:
    """別名/名稱 → 地區 slug（foundit 瀏覽頁路徑用）。"""
    global _GEO
    if _GEO:
        return _GEO
    try:
        raw = json.loads(_GEO_FILE.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("[foundit] 地區字典載入失敗：%s", e)
        _GEO = {"hong kong": "hong-kong", "香港": "hong-kong"}
        return _GEO
    mapping: dict[str, str] = {}
    for it in raw.get("locations", []):
        for key in (it.get("name"), it.get("id"), *(it.get("aliases") or [])):
            if key:
                mapping[key.strip().lower()] = it["id"]
    _GEO = mapping
    return _GEO


def _slugify(text: str) -> str:
    """關鍵字 → foundit SEO 路徑 slug（小寫、非英數轉連字號）。"""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# 卡片容器：Tailwind class 組合（含變體前綴用 [class*=] 匹配）
_CARD_SEL = 'div[class*="rounded-2xl"][class*="p-4"]'
_POSTED_RE = re.compile(r"Posted\s+(.+?ago)", re.I)


class FounditScraper(BaseScraper):
    source = "foundit"
    use_browser = True       # /search/* 被指紋 WAF 擋，必須真瀏覽器（channel=chrome）
    list_has_date = True     # 列表卡含「Posted N hours/days ago」相對日期

    def __init__(self, headers: dict | None = None):
        super().__init__(headers)
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": DEFAULT_HEADERS.get(
                    "User-Agent",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    # ---------- 瀏覽器 ----------
    def _ensure_browser(self):
        if self._page is not None:
            return self._page
        if sync_playwright is None:
            raise RuntimeError("需要 playwright：pip install playwright && playwright install chromium")
        self._pw = sync_playwright().start()
        try:
            # ⚠️ 必須用系統 Chrome 指紋；內建 Chromium headless 會被 WAF 403
            self._browser = self._pw.chromium.launch(headless=True, channel="chrome")
        except Exception as e:  # noqa: BLE001
            self._pw.stop()
            self._pw = None
            raise RuntimeError(
                "foundit 需要 Google Chrome（WAF 封鎖 Chromium 指紋）。"
                "請安裝 Google Chrome 後重試。原始錯誤：" + str(e)
            ) from e
        self._context = self._browser.new_context(
            locale="en-US",
            viewport={"width": 1440, "height": 900},
            user_agent=DEFAULT_HEADERS.get(
                "User-Agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            ),
        )
        self._page = self._context.new_page()
        return self._page

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
        if category:
            logger.warning("[foundit] 不支援 --category（站方 SEO 瀏覽頁無職能參數），已忽略")
        if industry:
            logger.warning("[foundit] 不支援 --industry（站方無行業過濾參數），已忽略")
        if sort:
            logger.warning("[foundit] 不支援 --sort（SEO 瀏覽頁固定預設排序），已忽略")

        loc_slug = None
        if district:
            loc_slug = _load_geo().get(district.strip().lower())
            if not loc_slug:
                logger.warning(
                    "[foundit] --district %r 不在 foundit_locations.json 內，已忽略", district
                )

        if keyword:
            slug = _slugify(keyword)
            if not slug:
                logger.warning("[foundit] 關鍵字 %r 無法組成 SEO 路徑，已當作空關鍵字", keyword)
                keyword = ""
        if keyword:
            url = f"{_BASE}/search/{slug}-jobs"
            if loc_slug:
                url += f"-in-{loc_slug}"
            if page > 1:
                url += f"-{page}"
        else:
            url = f"{_BASE}/search/jobs-in-{loc_slug or 'hong-kong'}"
            if page > 1:
                url += f"-{page}"

        pg = self._ensure_browser()
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"[foundit] 開啟 {url} 失敗：{e}") from e
        # SSR 內容於 domcontentloaded 即在 HTML 內；短等讓 hydration 穩定
        pg.wait_for_timeout(3_000)
        html = pg.content()
        low = html.lower()
        if "access denied" in low:
            raise RuntimeError("[foundit] 被 WAF 拒絕（403 Access Denied）")
        return self._parse_listing(html, page)

    def _parse_listing(self, html: str, page: int) -> list[JobRecord]:
        sp = BeautifulSoup(html, "html.parser")
        # 總數（頁面標題：如「2989 Engineer Jobs in Hongkong…」）
        total = None
        if sp.title and sp.title.string:
            m = re.search(r"([\d,]+)\s+Jobs", sp.title.string)
            if m:
                total = int(m.group(1).replace(",", ""))
        records: list[JobRecord] = []
        for card in sp.select(_CARD_SEL):
            h2 = card.select_one("h2.jobCardTitle")
            if not h2:
                continue
            a = card.select_one('a[href*="/job/"]')
            href = a.get("href") if a else None
            if not href:
                continue
            if href.startswith("/"):
                href = _BASE + href
            m = re.search(r"-(\d+)$", href)
            raw_id = m.group(1) if m else href
            company_el = card.select_one("span.jobCardCompany")
            loc_el = card.select_one("div.jobCardLocation")
            text = card.get_text(" | ", strip=True)
            pm = _POSTED_RE.search(text)
            posted_rel = pm.group(1).strip() if pm else ""
            records.append(
                JobRecord(
                    job_id=JobRecord.make_id(self.source, raw_id),
                    source=self.source,
                    title=h2.get_text(" ", strip=True),
                    company=company_el.get_text(" ", strip=True) if company_el else "",
                    location=loc_el.get_text(" ", strip=True) if loc_el else "",
                    salary="",
                    job_type="",
                    industry="",
                    description="",
                    requirements="",
                    url=href,
                    posted_date=posted_rel,  # 相對日期（「2 days ago」），days_since_posted 解析
                )
            )
        logger.info(
            "[foundit] 第 %d 頁回 %d 筆（站方總數：%s）",
            page, len(records), total if total is not None else "?",
        )
        return records

    # ---------- 詳情 ----------
    def get_detail(self, job_url: str) -> JobRecord | None:
        # /job/* 不在 WAF 封鎖範圍，普通 requests 即可（比瀏覽器快很多）
        resp = self._session.get(job_url, timeout=30)
        if resp.status_code == 403:
            # 極少數情況 WAF 連詳情也擋 → 回退瀏覽器
            return self._get_detail_browser(job_url)
        resp.raise_for_status()
        return self._parse_detail(resp.text, job_url)

    def _get_detail_browser(self, job_url: str) -> JobRecord | None:
        pg = self._ensure_browser()
        pg.goto(job_url, wait_until="domcontentloaded", timeout=45_000)
        pg.wait_for_timeout(2_000)
        return self._parse_detail(pg.content(), job_url)

    def _parse_detail(self, html: str, job_url: str) -> JobRecord | None:
        sp = BeautifulSoup(html, "html.parser")
        for tag in sp.find_all("script", type="application/ld+json"):
            try:
                d = json.loads(tag.string or "")
            except Exception:  # noqa: BLE001
                continue
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                return self._record_from_ldjson(d, job_url)
        logger.warning("[foundit] 詳情頁無 JobPosting ld+json：%s", job_url)
        return None

    def _record_from_ldjson(self, d: dict, job_url: str) -> JobRecord:
        desc_html = d.get("description") or ""
        description = BeautifulSoup(desc_html, "html.parser").get_text(" ", strip=True)
        # datePosted 格式為「04-09-2026」（dd-mm-yyyy）
        posted = ""
        raw_dp = d.get("datePosted") or ""
        for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
            try:
                posted = datetime.strptime(raw_dp, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue
        # jobLocation 去除相鄰重複段
        loc_parts: list[str] = []
        jloc = d.get("jobLocation")
        if isinstance(jloc, list):
            jloc = jloc[0] if jloc else {}
        if isinstance(jloc, dict):
            addr = jloc.get("address") or {}
            for p in (addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")):
                if p and p != "NA" and (not loc_parts or loc_parts[-1] != p):
                    loc_parts.append(p)
        # 薪資
        salary = ""
        bs = d.get("baseSalary")
        if isinstance(bs, dict):
            val = bs.get("value") or {}
            lo, hi, cur = val.get("minValue"), val.get("maxValue"), val.get("currency", "")
            if lo and hi:
                salary = f"{lo:,.0f} - {hi:,.0f} {cur}"
            elif lo or hi:
                salary = f"{lo or hi:,.0f} {cur}"
        return JobRecord(
            job_id=self._id_from_url(job_url),
            source=self.source,
            title=(d.get("title") or "").strip(),
            company=((d.get("hiringOrganization") or {}).get("name") or "").strip(),
            location=", ".join(loc_parts),
            salary=salary,
            job_type=d.get("employmentType") or "",
            industry="",
            description=description,
            requirements="",
            url=job_url,
            posted_date=posted,
        )

    def _id_from_url(self, job_url: str) -> str:
        m = re.search(r"-(\d+)$", job_url.split("?")[0])
        return JobRecord.make_id(self.source, m.group(1) if m else job_url)

    # ---------- 日期 ----------
    def days_since_posted(self, job: JobRecord) -> int | None:
        raw = (job.posted_date or "").lower().strip()
        if not raw:
            return None
        # ISO 日期（詳情合併後）
        for fmt in ("%Y-%m-%d",):
            try:
                dt = datetime.strptime(raw, fmt)
                return max(0, (datetime.now(timezone.utc) - dt.replace(tzinfo=timezone.utc)).days)
            except ValueError:
                pass
        # 相對日期：「13 hours ago」/「2 days ago」/「1 month ago」/「30+ days ago」
        m = re.match(r"(\d+)\s*\+?\s*(hour|day|week|month|year)s?\s+ago", raw)
        if not m:
            return None
        n, unit = int(m.group(1)), m.group(2)
        mult = {"hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}[unit]
        return n * mult

    def close(self) -> None:
        if self._browser:
            try:
                self._browser.close()
            except Exception:  # noqa: BLE001
                pass
            self._browser = None
        if self._pw:
            try:
                self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
            self._pw = None
        self._page = None
        self._session.close()
        # 與 other 站一致：留一點緩衝避免瀏覽器進程殘留
        time.sleep(0.2)
