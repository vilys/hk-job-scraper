# -*- coding: utf-8 -*-
"""BOSS直聘 zhipin.com 爬蟲 — 擴充八站 Wave 5（受限模組）。

🌐 站點特性（2026-09-05 逆向，見 README「🧭 技術筆記（BOSS直聘）」）：
  - ⚠️ **robots 受限站**：robots.txt 明文 `Disallow: /*?query=*` 且點名禁
    `Jobuispider`。本模組因此標記 _ROBOTS_RESTRICTED，首次實例化時警告；
    README 如實揭露。用戶已明確要求「8 個都做」才提供本模組。
  - 香港站不存在：`/hk/` 404；主站無香港城市（home 頁無香港字樣）。
  - **全站安全驗證**：普通 requests 與 Playwright（含本機 Chrome 指紋）
    開任何路徑一律落在「安全验证 - BOSS直聘」頁（需人機互動），無法取得職位資料。
  - 搜尋網址格式（站方 Web 版）：`/web/geek/job?query=<kw>&city=<code>`；
    職位卡 `.job-card-wrapper`（.job-name / .company-name / .job-area / .salary）。
    以上選擇器為公開資料，實際取用時先過安全驗證頁判定。
  - --district / --category / --industry / --sort / --days / --detail：不支援
    （警告後忽略）；--pages > 1 時第 2 頁起回空（分頁依賴查詢串 = robots 禁區）。
"""
from __future__ import annotations

import logging
import re
import time
from urllib.parse import quote

from bs4 import BeautifulSoup

from base_scraper import BaseScraper
from config import DEFAULT_HEADERS
from job_model import JobRecord

logger = logging.getLogger(__name__)

_BASE = "https://www.zhipin.com"

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


class ZhipinScraper(BaseScraper):
    source = "zhipin"
    use_browser = True
    list_has_date = False
    # 港澳台專區 0 張職位卡 + 登入牆：模組保留，但不納入 --source all。
    enabled = False
    _ROBOTS_RESTRICTED = True   # robots.txt Disallow: /*?query=*

    def __init__(self, headers: dict | None = None):
        super().__init__(headers)
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        logger.warning(
            "[zhipin] ⚠️ robots 受限：robots.txt 明文 Disallow /*?query=* 並點名禁"
            " Jobuispider。此模組為用戶明確要求所提供，請自行評估合規風險。"
        )
        logger.warning(
            "[zhipin] ⚠️ 站方全站安全驗證（人機互動）極可能攔下自動化存取；"
            "若回 0 筆屬預期行為（非程式故障）。"
        )

    # ---------- 瀏覽器 ----------
    def _ensure_browser(self):
        if self._page is not None:
            return self._page
        if sync_playwright is None:
            raise RuntimeError("需要 playwright：pip install playwright && playwright install chromium")
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=True, channel="chrome")
        except Exception as e:  # noqa: BLE001
            self._pw.stop()
            self._pw = None
            raise RuntimeError(
                "zhipin 需要本機 Google Chrome。原始錯誤：" + str(e)
            ) from e
        self._context = self._browser.new_context(
            locale="zh-CN",
            viewport={"width": 1440, "height": 900},
            user_agent=DEFAULT_HEADERS["User-Agent"],
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
        if district:
            logger.warning("[zhipin] 不支援 --district（香港城市未在站方體系內），已忽略")
        if category:
            logger.warning("[zhipin] 不支援 --category，已忽略")
        if industry:
            logger.warning("[zhipin] 不支援 --industry，已忽略")
        if sort:
            logger.warning("[zhipin] 不支援 --sort，已忽略")
        if page > 1:
            logger.warning(
                "[zhipin] 分頁依賴查詢串（robots 禁區）且未能驗證，僅提供第 1 頁；"
                "--pages > 1 時第 2 頁起回空。"
            )
            return []

        url = f"{_BASE}/web/geek/job?query={quote(keyword or '')}"
        pg = self._ensure_browser()
        try:
            resp = pg.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"[zhipin] 開啟 {url} 失敗：{e}") from e
        pg.wait_for_timeout(8_000)

        html = pg.content()
        title = (pg.title() or "")
        if "安全验证" in title or "安全验证" in html or "安全验证" in (resp.headers.get("x-redirect") or ""):
            logger.warning(
                "[zhipin] 落在站方「安全验证」頁（需人機互動）→ 回 0 筆。"
                "此為站方反爬行為，非程式故障。"
            )
            return []

        return self._parse_listing(html, page)

    def _parse_listing(self, html: str, page: int) -> list[JobRecord]:
        sp = BeautifulSoup(html, "html.parser")
        records: list[JobRecord] = []
        for card in sp.select(".job-card-wrapper"):
            a = card.select_one(".job-name") or card.select_one("a[ka]")
            if not a:
                continue
            href = a.get("href") or ""
            if href.startswith("/"):
                href = _BASE + href
            m = re.search(r"/job_detail/([A-Za-z0-9]+)\.html", href)
            raw_id = m.group(1) if m else href
            company_el = card.select_one(".company-name")
            area_el = card.select_one(".job-area")
            salary_el = card.select_one(".salary")
            records.append(
                JobRecord(
                    job_id=JobRecord.make_id(self.source, raw_id),
                    source=self.source,
                    title=a.get_text(" ", strip=True),
                    company=company_el.get_text(" ", strip=True) if company_el else "",
                    location=area_el.get_text(" ", strip=True) if area_el else "",
                    salary=salary_el.get_text(" ", strip=True) if salary_el else "",
                    job_type="",
                    industry="",
                    description="",
                    requirements="",
                    url=href,
                    posted_date="",
                )
            )
        if records:
            logger.info("[zhipin] 第 %d 頁取得 %d 筆。", page, len(records))
        return records

    # ---------- 詳情（best-effort） ----------
    def get_detail(self, job_url: str) -> JobRecord | None:
        logger.warning("[zhipin] --detail 不支援：詳情頁同受安全驗證保護，已跳過 %s", job_url)
        return None

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
        time.sleep(0.2)
