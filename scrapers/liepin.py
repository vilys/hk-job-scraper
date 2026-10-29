# -*- coding: utf-8 -*-
"""獵聘 liepin.com 爬蟲 — 香港據點（2026-09-11 重做）。

🌐 站點特性（2026-09-11 逆向，見 README「🧭 技術筆記（獵聘）」）：
  - ⚠️ **robots 狀態（如實揭露）**：`www.liepin.com/robots.txt` 明文
    `Disallow: /*?*`（所有帶查詢串的路徑禁抓），本模組的搜尋網址帶查詢串 → 屬禁區。
    但實際職缺資料由**另一台主機** `api-c.liepin.com` 供應，而該主機
    **沒有 robots.txt（404）**，按 RFC 9309 表示未設任何限制。
    本模組仍標記 `_ROBOTS_RESTRICTED` 並於實例化時警告，請自行評估合規風險。
  - ✅ **香港覆蓋已證實**：城市體系 `320 = 香港`（`330` 澳門 / `340` 台灣）。
    實測 `?city=320&dq=320` 回傳 42 張卡、40 張在香港，含真實港區
    （湾仔区 / 油尖旺区 / 观塘区 / 沙田区 / 元朗区…），站方 `totalCounts` ≈ 800。
  - ⭐ **關鍵陷阱：`city` 與 `dq` 必須同時給**。只給 `city=320` 時前端仍把 `dq`
    填成 `410`（全国），結果完全沒過濾（實測與 `city=050020` 廣州結果一模一樣，
    `totalCounts` 都是 807）。兩個都給 320 才生效。
  - **資料機制**：搜尋頁 `/zhaopin/?...` 是空殼，資料由站方 JS POST
    `api-c.liepin.com/api/com.liepin.searchfront4c.pc-search-job`。
    ⚠️ **直接 requests / 瀏覽器內 fetch 呼叫該 API 一律失敗**
    （`flag=0, code=-1400「出错了（400）」，缺 secscan 前端令牌）。
    唯一可行路徑：讓**頁面自己的 JS** 發出請求，我們只攔截回應。
  - **網址參數會被前端讀進 payload**：實測 `key` / `city` / `dq` 皆會正確帶入
    `mainSearchPcConditionForm`，故直接用網址篩選即可，不必改寫請求。
  - **欄位來源**：`jobCardList[].job` 提供 `jobId` / `title` / `dq`（地區）/
    `salary` / `link` / `refreshTime`（`YYYYMMDDHHMMSS`）/
    `requireWorkYears` / `requireEduLevel` / `labels`；公司名在 `comp.compName`。
  - ⚠️ `refreshTime` 是**刷新時間**而非刊登時間（站方未給刊登日），
    故 `--days` 以此近似，README 已標註。
  - ⚠️ 站方只到城市層級（香港 = 320），**無分區碼**；分區名出現在 `dq` 字串
    （如「香港-观塘区」），故 `--district` 以客戶端字串比對篩選（見 liepin_areas.json）。
  - `--detail`：詳情頁受保護且高風險，不支援（警告後跳過）。
  - `--category` / `--industry` / `--sort`：不支援（警告後忽略）。
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from base_scraper import BaseScraper
from config import DEFAULT_HEADERS
from job_model import JobRecord

logger = logging.getLogger(__name__)

_BASE = "https://www.liepin.com"
_SEARCH_URL = _BASE + "/zhaopin/"

# 香港城市碼（獵聘字典：320 香港 / 330 澳門 / 340 台灣；410 = 全国「不過濾」）
_CITY_CODE = "320"
_ALL_COUNTRY = "410"

_HERE = os.path.dirname(os.path.abspath(__file__))
_AREAS_FILE = os.path.join(_HERE, "liepin_areas.json")

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


def _norm(s: str) -> str:
    """地區名正規化：去空白、轉小寫、去掉結尾的「区 / 區」。"""
    s = (s or "").strip().lower()
    return s[:-1] if s.endswith(("区", "區")) else s


def _load_areas() -> dict:
    """載入獵聘專屬地區字典（失敗時回傳空字典，不中斷其他站）。"""
    try:
        with open(_AREAS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning("[liepin] 地區字典載入失敗（%s），--district 將僅支援城市層級", e)
        return {}


class LiepinScraper(BaseScraper):
    source = "liepin"
    use_browser = True
    # robots 禁抓 + 連 6–7 支請求即觸發 IP 驗證碼：不納入 --source all，
    # 避免一次全站抓取就把使用者 IP 打進驗證碼牆。
    enabled = False
    list_has_date = True        # 列表含 refreshTime，可客戶端篩選 --days
    _ROBOTS_RESTRICTED = True   # www 帶查詢串路徑屬 robots 禁區（資料實由 api-c 供應）

    def __init__(self, headers: Optional[dict] = None):
        super().__init__(headers)
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._areas = _load_areas()
        logger.warning(
            "[liepin] ⚠️ robots 狀態：www.liepin.com/robots.txt 載明 Disallow /*?*"
            "（帶查詢串路徑禁抓），本模組搜尋網址帶查詢串；"
            "惟職缺資料實由 api-c.liepin.com 供應，該主機無 robots.txt（404）。"
            "請自行評估合規風險。"
        )

    # ---------- 地區解析 ----------
    def _resolve_district(self, district: Optional[str]) -> tuple[str, list[str]]:
        """回傳 (城市碼, 分區關鍵字清單)。

        香港為主的爬蟲：未指定 / 無法辨識時一律回香港（320），不猜測。
        分區關鍵字用於客戶端比對 `dq` 字串（獵聘無分區碼）。
        """
        if not district or not district.strip():
            return _CITY_CODE, []
        raw = district.strip()
        low = raw.lower()

        # 城市層級
        for name, meta in (self._areas.get("city") or {}).items():
            if raw == name or low in [a.lower() for a in meta.get("aliases", [])]:
                return str(meta.get("code", _CITY_CODE)), []

        # 分區層級（香港 18 區）。比對前先正規化：去掉「区/區」後綴並轉小寫，
        # 讓「观塘」「觀塘」「观塘区」「觀塘區」四種寫法都命中同一區。
        target = _norm(raw)
        for liepin_name, meta in (self._areas.get("districts") or {}).items():
            cands = [liepin_name, meta.get("zh_hant", ""), meta.get("en", "")]
            cands += meta.get("aliases", [])
            if target in {_norm(c) for c in cands if c}:
                return _CITY_CODE, [liepin_name]

        logger.warning(
            "[liepin] --district %r 不在獵聘香港地區字典內（僅支援香港 18 區 / 澳門 / 台灣），"
            "已忽略並回退「全香港」", raw,
        )
        return _CITY_CODE, []

    # ---------- 瀏覽器 ----------
    def _ensure_browser(self):
        if self._page is not None:
            return self._page
        if sync_playwright is None:
            raise RuntimeError("需要 playwright：pip install playwright && playwright install chromium")
        self._pw = self._start_playwright()
        try:
            self._browser = self._pw.chromium.launch(headless=True, channel="chrome")
        except Exception as e:  # noqa: BLE001
            self._pw.stop()
            self._pw = None
            raise RuntimeError("liepin 需要本機 Google Chrome。原始錯誤：" + str(e)) from e
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
        keyword: str = "",
        page: int = 1,
        district: Optional[str] = None,
        category: Optional[str] = None,
        industry: Optional[str] = None,
        sort: Optional[str] = None,
    ) -> list[JobRecord]:
        if category:
            logger.warning("[liepin] 不支援 --category，已忽略")
        if industry:
            logger.warning("[liepin] 不支援 --industry，已忽略")
        if sort:
            logger.warning("[liepin] 不支援 --sort，已忽略")

        city_code, district_keys = self._resolve_district(district)

        # ⭐ city 與 dq 必須同時給，否則站方不過濾（實測 totalCounts 恆為 807）
        params = [
            f"key={quote(keyword)}" if keyword else "",
            f"city={city_code}",
            f"dq={city_code}",
            f"currentPage={max(0, page - 1)}",
        ]
        url = _SEARCH_URL + "?" + "&".join(p for p in params if p)

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
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"[liepin] 開啟 {url} 失敗：{e}") from e
        pg.wait_for_timeout(10_000)   # 等 secscan 安全 JS 跑完 + API 回應
        try:
            pg.remove_listener("response", on_response)
        except Exception:  # noqa: BLE001
            pass

        # ⭐ 判讀關卡：優先用「標題」判讀（實測驗證碼頁 title = '安全中心-验证码'），
        #    因為跳轉時序不定——有時 5s 內就跳走，有時 10s 後才跳，只看 URL 會漏判。
        try:
            title = pg.title() or ""
        except Exception:  # noqa: BLE001
            title = ""
        if "safe.liepin.com" in pg.url or "captcha" in pg.url.lower() or "验证码" in title:
            logger.warning(
                "[liepin] 觸發站方驗證碼（safe.liepin.com）→ 回 0 筆。"
                "此為站方反爬行為，非程式故障；建議稍後再試。URL=%s ｜標題=%r",
                pg.url[:120], title[:60],
            )
            return []
        if not hits:
            logger.warning(
                "[liepin] 未攔截到搜尋 API 回應 → 回 0 筆。"
                "最終 URL=%s ｜標題=%r ｜可能原因：安全驗證 / 站方改版 / 等待不足。"
                "請執行 `python tools/_probe_liepin.py` 聽診（會列出所有 api 請求與頁面卡片數）",
                pg.url[:120], title[:60],
            )
            return []

        records: list[JobRecord] = []
        dropped_non_hk = 0
        dropped_district = 0
        for d in hits:
            if d.get("flag") != 1:
                continue
            pagination = (d.get("data") or {}).get("pagination") or {}
            if page == 1 and pagination.get("totalCounts"):
                logger.info("[liepin] 站方回報總數 %s 筆", pagination.get("totalCounts"))
            cards = ((d.get("data") or {}).get("data") or {}).get("jobCardList") or []
            for c in cards:
                job = c.get("job") or {}
                comp = c.get("comp") or {}
                job_id = str(job.get("jobId") or "").strip()
                if not job_id:
                    continue
                loc = (job.get("dq") or "").strip()

                # 只保留目標城市（站方偶爾混入外地職缺，實測 42 張中約 2 張）
                if not loc.startswith(("香港", "澳門", "澳门", "台灣", "台湾")):
                    dropped_non_hk += 1
                    continue
                # 分區篩選（客戶端字串比對；獵聘無分區碼）
                if district_keys and not any(k in loc for k in district_keys):
                    dropped_district += 1
                    continue

                link = job.get("link") or f"{_BASE}/job/19{job_id}.shtml"
                if link.startswith("//"):
                    link = "https:" + link

                posted = self._refresh_to_date(job.get("refreshTime"))
                labels = job.get("labels") or []
                extra = " / ".join(
                    x for x in (job.get("requireWorkYears"), job.get("requireEduLevel")) if x
                )

                records.append(
                    JobRecord(
                        job_id=JobRecord.make_id(self.source, job_id),
                        source=self.source,
                        title=(job.get("title") or "").strip(),
                        company=(comp.get("compName") or "").strip(),
                        location=loc,
                        salary=(job.get("salary") or "").strip(),
                        job_type="",
                        industry=(comp.get("compIndustry") or "").strip(),
                        description=extra,
                        requirements="、".join(str(x) for x in labels if x),
                        url=link,
                        posted_date=posted,
                    )
                )

        if dropped_non_hk:
            logger.info("[liepin] 已剔除 %d 筆非目標城市職缺（站方混入）", dropped_non_hk)
        if dropped_district:
            logger.info("[liepin] 分區篩選剔除 %d 筆", dropped_district)
        logger.info("[liepin] 第 %d 頁取得 %d 筆。", page, len(records))
        return records

    # ---------- 日期 ----------
    @staticmethod
    def _refresh_to_date(refresh: Optional[str]) -> str:
        """`refreshTime`（YYYYMMDDHHMMSS）→ `YYYY-MM-DD`；無法解析回空字串。"""
        s = (refresh or "").strip()
        if len(s) < 8 or not s[:8].isdigit():
            return ""
        try:
            return datetime.strptime(s[:8], "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            return ""

    def days_since_posted(self, job: JobRecord) -> Optional[int]:
        """以 refreshTime 轉換出的日期計算天數（⚠️ 刷新日非刊登日）。"""
        raw = (job.posted_date or "").strip()
        if not raw:
            return None
        try:
            d = datetime.strptime(raw[:10], "%Y-%m-%d")
        except ValueError:
            return None
        return max(0, (datetime.now() - d).days)

    # ---------- 詳情 ----------
    def get_detail(self, job_url: str) -> Optional[JobRecord]:
        logger.warning("[liepin] --detail 不支援：詳情頁受站方保護且高風險，已跳過 %s", job_url)
        return None

    # ---------- 資源釋放 ----------
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
