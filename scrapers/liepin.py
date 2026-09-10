# -*- coding: utf-8 -*-
"""獵聘 liepin.com 爬蟲 — 擴充八站 Wave 5（受限模組）。

🌐 站點特性（2026-09-05 逆向，見 README「🧭 技術筆記（獵聘）」）：
  - ⚠️ **robots 受限站**：robots.txt 明文 `Disallow: /*?*`（所有帶查詢串的
    路徑一律禁止抓取）。本模組因此標記 _ROBOTS_RESTRICTED，首次實例化時
    發出警告；README 如實揭露。用戶已明確要求「8 個都做」才提供本模組。
  - 香港站不存在：`/hk/` 404。主站為內地求職平台，香港職缺覆蓋未經證實
    （首次樣本疑未按城市過濾）；city=900 是否對應香港**未確認**。
  - 反爬極兇：同一 IP 短時間內 2–3 次自動化請求後即觸發
    `safe.liepin.com/page/liepin/captchaPage_ip_PC`（IP 級驗證碼），
    Playwright + 本機 Chrome 指紋也逃不掉。
  - **資料機制**：搜尋頁 `/zhaopin/?key=<kw>&city=<code>` 是空殼，
    資料由站方 JS 呼叫 `api-c.liepin.com/api/com.liepin.searchfront4c.pc-search-job`
    （POST，flag=1 時回 jobCardList）。瀏覽器**首次**導航偶爾可攔截到該回應。
  - 直接 requests 調用該 API 一律 flag=0（需 secscan 前端令牌）。
  - --days / --detail：列表卡無刊登日期、詳情頁同樣受驗證碼保護 → 不支援。
  - --category / --industry / --sort：不支援（警告後忽略）。
  - 分頁：站方分頁參數未能驗證（觸發驗證碼），僅提供第 1 頁。
"""
from __future__ import annotations

import logging
import time

from base_scraper import BaseScraper
from config import DEFAULT_HEADERS
from job_model import JobRecord

logger = logging.getLogger(__name__)

_BASE = "https://www.liepin.com"

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

# 已知城市碼（僅供 --district 傳入參考；900 是否香港未確認）
_CITY_CODES = {
    "北京": "010", "beijing": "010",
    "上海": "020", "shanghai": "020",
    "廣州": "050020", "guangzhou": "050020",
    "深圳": "050090", "shenzhen": "050090",
    "杭州": "070020", "hangzhou": "070020",
    "香港": "900", "hong kong": "900", "hongkong": "900",
}


class LiepinScraper(BaseScraper):
    source = "liepin"
    use_browser = True
    list_has_date = False
    _ROBOTS_RESTRICTED = True   # robots.txt Disallow: /*?*

    def __init__(self, headers: dict | None = None):
        super().__init__(headers)
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        logger.warning(
            "[liepin] ⚠️ robots 受限：robots.txt 明文 Disallow /*?*（搜尋路徑禁抓）。"
            "此模組為用戶明確要求所提供，請自行評估合規風險。"
        )
        logger.warning(
            "[liepin] ⚠️ 香港職缺覆蓋未證實（香港站不存在），且站方 IP 驗證碼極易觸發；"
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
                "liepin 需要本機 Google Chrome。原始錯誤：" + str(e)
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
        if category:
            logger.warning("[liepin] 不支援 --category，已忽略")
        if industry:
            logger.warning("[liepin] 不支援 --industry，已忽略")
        if sort:
            logger.warning("[liepin] 不支援 --sort，已忽略")
        if page > 1:
            logger.warning(
                "[liepin] 分頁參數未能驗證（站方 IP 驗證碼），僅提供第 1 頁；"
                "--pages > 1 時第 2 頁起回空。"
            )
            return []

        city = ""
        if district:
            city = _CITY_CODES.get(district.strip().lower())
            if not city and district.strip().isdigit():
                city = district.strip()
            if not city:
                logger.warning("[liepin] --district %r 不在已知城市碼內，已忽略", district)

        # 攔截站方自己的搜尋 API 回應
        hits: list[dict] = []

        def on_response(resp):
            u = resp.url
            if "searchfront4c.pc-search-job" in u and "cond-init" not in u:
                try:
                    hits.append(resp.json())
                except Exception:  # noqa: BLE001
                    pass

        pg = self._ensure_browser()
        pg.on("response", on_response)
        from urllib.parse import quote
        url = f"{_BASE}/zhaopin/?key={quote(keyword or '')}"
        if city:
            url += f"&city={city}"
        try:
            resp = pg.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"[liepin] 開啟 {url} 失敗：{e}") from e
        pg.wait_for_timeout(10_000)  # 等 secscan 安全 JS 跑完 + API 回應
        try:
            pg.remove_listener("response", on_response)
        except Exception:  # noqa: BLE001
            pass

        # 驗證碼判定
        if "safe.liepin.com" in pg.url or "captcha" in pg.url:
            logger.warning(
                "[liepin] 觸發站方 IP 驗證碼（safe.liepin.com/captchaPage_ip_PC）→ 回 0 筆。"
                "此為站方反爬行為，非程式故障；建議稍後再試或改用其他據點。"
            )
            return []

        if not hits:
            logger.warning("[liepin] 未攔截到搜尋 API 回應（可能被安全驗證攔下）→ 回 0 筆")
            return []

        records: list[JobRecord] = []
        for d in hits:
            if d.get("flag") != 1:
                continue
            cards = ((d.get("data") or {}).get("data") or {}).get("jobCardList") or []
            for c in cards:
                job = c.get("job") or {}
                comp = c.get("comp") or {}
                job_id = str(job.get("jobId") or "").strip()
                if not job_id:
                    continue
                link = job.get("link") or f"https://www.liepin.com/job/{job_id}.shtml"
                if link.startswith("//"):
                    link = "https:" + link
                records.append(
                    JobRecord(
                        job_id=JobRecord.make_id(self.source, job_id),
                        source=self.source,
                        title=(job.get("title") or "").strip(),
                        company=(comp.get("compName") or "").strip(),
                        location=(job.get("dq") or job.get("city") or "").strip(),
                        salary=(job.get("salary") or "").strip(),
                        job_type="",
                        industry="",
                        description="",
                        requirements="",
                        url=link,
                        posted_date="",
                    )
                )
        logger.info("[liepin] 第 %d 頁取得 %d 筆（含重複回應合併）。", page, len(records))
        return records

    # ---------- 詳情（best-effort；驗證碼高風險） ----------
    def get_detail(self, job_url: str) -> JobRecord | None:
        logger.warning("[liepin] --detail 不支援：詳情頁同受 IP 驗證碼保護，已跳過 %s", job_url)
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
