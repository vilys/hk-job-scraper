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

import json
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
        self._date_map: dict[str, str] = {}   # {jk: 'N day ago'}，最近一次 search 的刊登日
        self._detail_fail_streak = 0          # 連續點不開詳情面板的次數（熔斷用）
        self._warned_detail_break = False
        self._fromage: str = ""               # 站方端日期過濾（fromage=N），由 set_days() 注入

    # ---------- 瀏覽器（共用一個 session） ----------
    def _ensure_browser(self) -> None:
        if self._browser is not None:
            return
        self._pw = sync_playwright().start()
        # ⚠️ 必須用本機 Google Chrome（channel="chrome"），不能用內建 Chromium。
        # 2026-09-08 實測：內建 Chromium 指紋被 Cloudflare 攔下（標題 "Just a moment..."、
        # 內文 "Additional Verification Required" / Ray ID），且輪詢 45s 都不會過關；
        # 改 chrome channel 後立即正常（beacon 16 張）。與 foundit 是同一類型的坑。
        try:
            self._browser = self._pw.chromium.launch(channel="chrome", headless=True)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[indeed] 本機 Google Chrome 不可用（%s），退回內建 Chromium——"
                "極可能被 Cloudflare 擋下而回 0 筆", e)
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

    def _build_url(self, keyword: str, district: Optional[str], page: int) -> str:
        loc = self._location_of(district)
        params = [f"q={quote(keyword)}" if keyword else "",
                  f"l={quote(loc)}"]
        if page and page > 1:
            params.append(f"start={(page - 1) * 10}")   # 每頁 10 筆
        if self._fromage:
            # 站方端日期過濾：fromage=N 讓 Indeed 只回傳 N 天內的職缺
            params.append(f"fromage={self._fromage}")
        params = [p for p in params if p]
        return SEARCH_URL + "?" + "&".join(params)

    # ---------- 站方端日期過濾掛載點（base_scraper.scrape_all 呼叫） ----------
    def set_days(self, days: int) -> None:
        """把 --days 下推成 Indeed 的 `fromage=N`（站方端只回傳 N 天內的職缺）。

        客戶端仍會以內嵌 mosaic 的 `formattedRelativeTime` 二度篩選（雙保險），
        但站方端先篩過可避免「一整頁都是幾十天前的舊職缺、濾完剩沒幾筆」。"""
        try:
            n = int(days)
        except (TypeError, ValueError):
            logger.warning("[indeed] --days %r 無法轉為整數，已忽略站方端過濾", days)
            return
        if n <= 0:
            return
        self._fromage = str(n)
        logger.info("[indeed] 已啟用站方端日期過濾 fromage=%s（%d 天內）", self._fromage, n)

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
        # 2026-09-08 實測：Indeed 空關鍵字（q=）+ 地區的搜尋，站方會回
        # `headerMsg: "The search ... did not match any jobs."` / `originalResultCount: 0`
        # → 這是站方行為，不是爬蟲故障；明確警告，避免被誤判為「卡住 / 壞掉」。
        if not (keyword or "").strip():
            logger.warning(
                "[indeed] 未給 --keyword：Indeed 空關鍵字搜尋站方一律回 0 筆"
                "（did not match any jobs），請指定關鍵字")
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
            self._date_map = self._build_date_map(html)
            if self._date_map:
                for rec in records:
                    jk = self._jk_from_url(rec.url)
                    if jk and jk in self._date_map:
                        rec.posted_date = self._date_map[jk]
                logger.info("[indeed] 第 %d 頁已從內嵌 JSON 取得 %d/%d 筆刊登日",
                            page, sum(1 for r in records if r.posted_date), len(records))
            else:
                logger.warning("[indeed] 第 %d 頁未能解析內嵌刊登日（--days 將無資料可篩）", page)
        except Exception as e:  # noqa: BLE001
            logger.warning("[indeed] 內嵌刊登日解析失敗（--days 將退化为抓詳情）：%s", e)

        logger.info("[indeed] 第 %d 頁卡片數：%d", page, len(records))
        # 卡片出現後再緩一口氣：Indeed 是 SPA，DOM 渲染與事件綁定有時間差，
        # 立刻點擊有機會點不開側面板（實測 CLI 首筆常 timeout，程式化呼叫卻正常）。
        time.sleep(1.5)
        return records

    # ---------- 內嵌刊登日（mosaic provider 職位陣列） ----------
    # ⚠️ 2026-09-08 修正（原實作有 bug）：
    #   1. 職位物件裡的鍵是 **jobkey（全小寫 k）**；`jobKey`（大寫 K）是
    #      mouseDownHandlerOption 裡的另一份追蹤用值，拿它配對會張冠李戴。
    #   2. `pubDate` 是**雇主 feed 的原始刊登日**，長期未更新的職缺會是數年前
    #      （實測 947～2811 天前），**不可當作刊登日**。
    #   正確做法：以站方顯示的 `formattedRelativeTime`（如 "3 days ago"）為準；
    #   若它是 "30+ days ago"（站方只給下限），改用 `createDate`（Indeed 建檔時間）
    #   折算天數，比 pubDate 可靠得多。
    @staticmethod
    def _extract_results_json(html: str) -> list:
        """取出內嵌的 mosaic 職位陣列（`"results":[...]`），失敗回空 list。

        用 JSONDecoder.raw_decode 由 `[` 起掃，能正確處理字串內的括號，
        比手動數括號穩健。
        """
        i = html.find('"results":[')
        if i < 0:
            return []
        start = html.index("[", i)
        try:
            arr, _ = json.JSONDecoder().raw_decode(html[start:start + 4_000_000])
        except Exception:  # noqa: BLE001
            return []
        return arr if isinstance(arr, list) else []

    @staticmethod
    def _norm_rel(text: str) -> str:
        """相對時間文字 → 統一格式「N day ago」（與 days_since_posted 相容）。"""
        s = (text or "").strip().lower()
        if not s:
            return ""
        if any(k in s for k in ("just posted", "today", "just now", "posted today")):
            return "0 day ago"
        m = re.search(r"(\d+)\s*\+?\s*(hour|day|week|month)s?", s)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            return "0 day ago" if unit == "hour" else f"{n * _DATE_UNIT_DAYS.get(unit, 1)} day ago"
        return s

    @classmethod
    def _rel_from_result(cls, r: dict) -> str:
        """單筆職位物件 → 刊登日相對文字。"""
        rel = str(r.get("formattedRelativeTime") or "").strip()
        # "30+ days ago" 只是下限 → 改用 createDate 折算
        if rel and "30+" not in rel:
            return cls._norm_rel(rel)
        now_ms = time.time() * 1000
        for key in ("createDate", "pubDate"):
            ts = r.get(key)
            if isinstance(ts, (int, float)) and ts > 0:
                return f"{int(max(0, now_ms - ts) // 86400000)} day ago"
        return cls._norm_rel(rel)

    @classmethod
    def _build_date_map(cls, html: str) -> dict:
        """{jobkey: 'N day ago'} 對照表（供 --days 篩選）。"""
        out: dict[str, str] = {}
        for r in cls._extract_results_json(html):
            if not isinstance(r, dict):
                continue
            jk = r.get("jobkey") or r.get("jobKey")
            if not jk:
                continue
            rel = cls._rel_from_result(r)
            if rel:
                out[str(jk)] = rel
        return out

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
        """外層：只負責計時（供排查「--detail 很慢」時定位瓶頸）。"""
        t0 = time.time()
        try:
            return self._get_detail(job_url)
        finally:
            logger.info("[indeed] get_detail 耗時 %.1fs：%s", time.time() - t0, job_url)

    def _get_detail(self, job_url: str) -> Optional[JobRecord]:
        self._ensure_browser()
        jk = self._jk_from_url(job_url)
        if not jk:
            return None

        # 🐢 熔斷（2026-09-08 實測）：一旦連續 2 筆點不開面板，就不再操作頁面。
        # 實測若不熔斷，第 7 筆失敗觸發整頁重載後，之後每筆都退化成 ~50s
        # （重載後再也點不開，又掉進 viewjob 直連），16 筆的 --detail 要跑 9 分鐘，
        # 最後只剩 1 筆——既慢又對站方不友善。熔斷後保留已取得的刊登日，只丟描述。
        if self._detail_fail_streak >= 2:
            if not self._warned_detail_break:
                logger.warning(
                    "[indeed] 已連續 %d 筆點不開詳情面板，停止抓取後續描述"
                    "（刊登日照常保留）", self._detail_fail_streak)
                self._warned_detail_break = True
            return self._build_detail_record(jk, self._date_map.get(jk, ""), "", job_url)

        # 卡片連結不存在（廣告 / 佔位卡，實測有 jk=890abcdef0123456 這種）→
        # 直接跳過，不整頁重載。
        if not self._page.query_selector(f'a[data-jk="{jk}"]'):
            logger.warning("[indeed] 頁面上找不到卡片連結 %s（可能為廣告/佔位卡），跳過", jk)
            self._detail_fail_streak += 1
            return self._build_detail_record(jk, self._date_map.get(jk, ""), "", job_url)

        # 主要路徑：在當前搜尋頁點擊對應卡片（不重觸發 CF）。
        # 用 JS element.click() 直接派發點擊事件，繞過「面板遮住卡片導致
        # Playwright .click() 判定 element is not visible」的問題。
        if self._open_card(jk):
            posted, description = self._read_detail(jk)
            if not (posted or description):
                # 面板開了但內容還沒渲染：原地再讀一次即可，
                # 千萬別掉進「整頁重載」——那才是把 --detail 拖到分鐘級的元凶。
                time.sleep(1.0)
                posted, description = self._read_detail(jk)
            if posted or description:
                self._detail_fail_streak = 0
            else:
                self._detail_fail_streak += 1
            return self._build_detail_record(jk, posted, description, job_url)
        self._detail_fail_streak += 1

        # 回退（僅限「當前頁根本不是搜尋結果頁」時，例如單獨呼叫 get_detail）：
        # 重新 goto 搜尋頁一次，再點該卡。
        if self._last_search_url and not self._page.query_selector_all(".job_seen_beacon"):
            try:
                self._page.goto(self._last_search_url, wait_until="domcontentloaded", timeout=30000)
                for _ in range(10):          # 最多 ~20s（原為 15×3s=45s，太重）
                    time.sleep(2)
                    if self._page.query_selector_all(".job_seen_beacon"):
                        break
                time.sleep(1.5)              # 等 SPA 綁定事件（同上）
                if self._page.query_selector(f'a[data-jk="{jk}"]') and self._open_card(jk):
                    posted, description = self._read_detail(jk)
                    if posted or description:
                        self._detail_fail_streak = 0
                    return self._build_detail_record(jk, posted, description, job_url)
            except Exception as e:  # noqa: BLE001
                logger.warning("[indeed] 重新 goto 後點擊仍失敗 %s：%s", job_url, e)

        # ⚠️ 不再直連 viewjob：實測會重觸發 Cloudflare，拿不到內容又拖慢流程。
        return self._build_detail_record(jk, self._date_map.get(jk, ""), "", job_url)

    # ---------- 詳情輔助 ----------
    def _open_card(self, jk: str, timeout: int = 8000) -> bool:
        """點擊卡片開側面板；失敗重試一次再放棄。

        實測：DOM 剛出現就點擊，有機會點不開（SPA 事件尚未綁定），
        故第一次失敗先等一下再點一次，兩次都不開才交回 get_detail 走回退。
        """
        for attempt in (1, 2):
            self._js_click_card(jk)
            try:
                self._page.wait_for_selector(
                    "#jobDescriptionText, .jobsearch-jobDescriptionText", timeout=timeout)
                return True
            except Exception:  # noqa: BLE001
                if attempt == 1:
                    logger.warning("[indeed] 第 1 次點擊未開面板（%s），重試一次", jk)
                    time.sleep(1.5)
        return False

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
        """從詳情 HTML 抓刊登日。

        ⚠️ 必須優先匹配站方的「Posted / Date posted」字樣。實測「Employer Active
        1 day ago」是**雇主活躍度**而非刊登日，會把 30+ 天的職缺誤報成 1 天內，
        因此只當最後回退。
        """
        m = re.search(r"(?:Date\s*Posted|Posted)\s*[·:\-]?\s*(\d+)\s*(day|hour|week|month)s?\s+ago",
                      html, re.I)
        if m:
            return f"{m.group(1)} {m.group(2).lower()} ago"
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
        m = re.search(r"(\d+)\s*(day|hour|week|month)s?\s+ago", html, re.I)
        if m:
            return f"{m.group(1)} {m.group(2).lower()} ago"
        return ""

    @staticmethod
    def _extract_description(html: str) -> str:
        """純 HTML 回退：從 id="jobDescriptionText" 起做 div 巢狀配對後去標籤。

        ⚠️ 不能用 `(.*?)</div>`——描述內含巢狀 div／ul，非貪婪只會抓到第一層
        （實測整段描述只剩 "Client Description"）。
        """
        m = re.search(r'id="jobDescriptionText"[^>]*>', html)
        if not m:
            return ""
        start = m.end()
        depth, i = 1, start
        tag_re = re.compile(r"</?div\b", re.I)
        while i < len(html):
            t = tag_re.search(html, i)
            if not t:
                i = len(html)
                break
            depth += -1 if t.group(0).startswith("</") else 1
            if depth == 0:          # 遇到配對的結尾 div → 切在它之前
                i = t.start()
                break
            i = t.end()
        raw = html[start:i]
        text = re.sub(r"<[^>]+>", " ", raw)
        return re.sub(r"\s+", " ", text).strip()

    def _read_description(self, html: str = "") -> str:
        """優先用 DOM inner_text（最準），失敗才退回 HTML 正則。"""
        for sel in ("#jobDescriptionText", ".jobsearch-jobDescriptionText"):
            el = self._page.query_selector(sel)
            if not el:
                continue
            try:
                t = (el.inner_text() or "").strip()
            except Exception:  # noqa: BLE001
                t = ""
            if t:
                return re.sub(r"\s+", " ", t)
        return self._extract_description(html or self._page.content())

    def _read_detail(self, jk: str) -> tuple[str, str]:
        """回傳 (posted_date, description)；刊登日優先用 search 時的對照表。"""
        html = self._page.content()
        posted = self._date_map.get(jk) or self._extract_date(html)
        return posted, self._read_description(html)

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
