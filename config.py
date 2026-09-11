"""
全域設定 (Phase 1.4)

所有網站共用的設定集中在此，方便統一管理：
  - 請求間隔（尊重目標網站，避免被封）
  - User-Agent
  - 輸出目錄
  - 各網站的 CSS 選擇器 / API 端點（HTML 結構變動時只改這裡）
"""
from __future__ import annotations

import os
from pathlib import Path

# ---- LinkedIn 登入態 cookie（可選，訪客模式不需要） ----
# 提供自己的 li_at cookie 可解鎖「穩定翻頁」（訪客模式深翻頁會被隨機化/限流）。
# 取得方式：瀏覽器登入 linkedin.com → DevTools → Application → Cookies →
# 複製 li_at 的值，設環境變數 LINKEDIN_LI_AT 後執行本程式。
# 注意：cookie 等同帳號憑證，請勿外洩、僅供個人使用。
LINKEDIN_LI_AT = os.getenv("LINKEDIN_LI_AT", "")

# ---- 路徑 ----
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# ---- 請求行為 ----
# 最低請求間隔（秒）。商業網站 1~3 秒，政府網站 >=2 秒。
REQUEST_DELAY = 1.5
REQUEST_TIMEOUT = 20

# 失敗重試次數
MAX_RETRIES = 3

# ---- 預設請求標頭 ----
# ⚠️⚠️ User-Agent 必須與本機 Chrome 的實際版本一致（2026-09-10 重大修正）
# Cloudflare 會比對 UA 與 Client Hints（`sec-ch-ua`）回報的真實版本。
# 若 UA 寫 Chrome/124 而瀏覽器實為 152，這個落差就是極經典的機器人訊號——
# Indeed 據點正是因此卡在 managed challenge（見 README「🧭 技術筆記（Indeed）」）。
# 故改為**開機自動量測**本機 Chrome 版本，不再寫死，杜絕再次腐化。
_CHROME_VERSION_FALLBACK = "152.0.0.0"   # 偵測失敗時的退路（僅影響 UA 字串，不影響功能）


def _detect_chrome_version() -> str:
    """量測本機 Google Chrome 的完整版本號（如 `152.0.7977.83`）。

    搜尋順序：環境變數 CHROME_UA_VERSION → 常見安裝路徑下的版本目錄。
    找不到則回退 `_CHROME_VERSION_FALLBACK` 並保持程式可運作。
    """
    override = os.getenv("CHROME_UA_VERSION", "").strip()
    if override and override[0].isdigit():
        return override

    import re
    roots: list[Path] = []
    if os.name == "nt":
        for base in (os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                     os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                     os.environ.get("LOCALAPPDATA", "")):
            if base:
                roots.append(Path(base) / "Google" / "Chrome" / "Application")
    else:
        roots.append(Path("/Applications/Google Chrome.app/Contents"))

    pat = re.compile(r"^\d+\.\d+\.\d+\.\d+$")
    best: tuple[int, ...] | None = None
    best_s = ""
    for root in roots:
        try:
            if not root.is_dir():
                continue
            for d in root.iterdir():
                if d.is_dir() and pat.match(d.name):
                    parts = tuple(int(x) for x in d.name.split("."))
                    if best is None or parts > best:
                        best, best_s = parts, d.name
        except OSError:
            continue
    return best_s or _CHROME_VERSION_FALLBACK


CHROME_VERSION = _detect_chrome_version()

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{CHROME_VERSION} Safari/537.36"
    ),
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
}

# ---- 各網站選擇器 / 端點設定 ----
# 結構變動時只需調整此處，爬蟲邏輯不必改。
SELECTORS = {
    "moovup": {
        # 搜尋頁（SPA，結果由前端 API 提供；此處為 DOM 備用解析用選擇器）
        "result_card": "a.job-card, .job-list__item, [data-test='job-card']",
        "title": ".job-card__title, .job-title",
        "company": ".job-card__company, .company-name",
        "location": ".job-card__location, .location",
        "salary": ".job-card__salary, .salary",
        "job_type": ".job-card__type, .job-type",
        "detail_url": "a.job-card",
        # 詳情頁
        "detail_description": ".job-detail__description, .description",
        "detail_requirements": ".job-detail__requirements, .requirements",
        "detail_posted": ".job-detail__date, .posted-date",
    },
    "gov_hk": {
        # 搜尋結果列表：每筆職位卡片
        "result_card": "div.row.item[data-jobcard]",
        "title": "div.d-flex.justify-content-between > div:first-child",
        "salary": ".icon_salary",
        "location": ".icon_address",
        "job_id": "input[id^='ord_no_']",
        "detail_url_attr": "data-jobcard",
        # 詳情頁 (jobCard) 用穩定 id 標識
        "detail_company": "#empName",
        "detail_location": "#locDesc",
        "detail_description": "#jobRemark",
        "detail_requirements": "#eduRemark",
    },
    "jobsdb": {},
    "linkedin": {
        # 搜尋結果列表容器內的職位卡（li）
        "result_list": ".jobs-search__results-list li",
        # 職位卡內的關鍵子元素（訪客模式）
        "card_link": "a.base-card__full-link",
        "title": ".base-search-card__title",
        "company": ".base-search-card__subtitle",
        "location": ".job-search-card__location",
        "metadata": ".base-search-card__metadata",   # 含 地點 + 刊登日（換行分隔）
        "date": "time",
        # 免登入詳情 API（jobs-guest/jobs/api/jobPosting/<id>）的選擇器
        "detail_title": ".top-card-layout__title",
        "detail_company": ".topcard__flavor",
        "detail_location": ".topcard__flavor--bullet",
        "detail_description": ".description__text, .show-more-less-html__markup",
    },
    "indeed": {},
    "recruit": {},
}

# 各網站專屬設定（如 API base、需要 Playwright 等）
SITE_CONFIG = {
    "moovup": {
        "base_url": "https://moovup.com",
        "api_base": "https://api.moovup.com/v2",
        "search_url": "https://moovup.com/hk/find-jobs/",
        "needs_browser": True,   # Cloudflare Turnstile，需 Playwright 真瀏覽器
        "request_delay": 1.5,
    },
    "gov_hk": {
        "needs_browser": False,
        "request_delay": 2.0,
    },
    "jobsdb": {"needs_browser": True, "request_delay": 2.0},
    # 訪客模式對速率敏感（429 / 登入牆），且第 2 頁起每頁僅 10 張卡（翻頁請求數較多），
    # 故間隔拉高到 5 秒以符合爬蟲禮節（「不要太狠、一步一步、不要被封」）。
    "linkedin": {"needs_browser": False, "request_delay": 5.0,
                 "supports_logged_out": True},
    "indeed": {"needs_browser": True, "request_delay": 3.0},
    # ASP.NET WebForms：翻頁須在真瀏覽器內執行 __doPostBack，故 needs_browser
    "recruit": {"needs_browser": True, "request_delay": 2.0},
    "jobmarket": {"request_delay": 1.5},
    "foundit": {"needs_browser": True, "request_delay": 2.0},
    "efc": {"request_delay": 1.5},
    # Wave 5 受限站：反爬極兇 + robots 限制，間隔拉長（行為保守）
    # ⚠️ 獵聘反爬極兇：2026-09-11 實測連續第 6–7 支請求即觸發 safe.liepin.com
    # IP 驗證碼。間隔由 5s 拉到 8s，且每次執行建議 --pages 1～2 為宜。
    "liepin": {"needs_browser": True, "request_delay": 8.0},
    "zhipin": {"needs_browser": True, "request_delay": 5.0},
    # OfferToday（原 HKGoodJobs）：免瀏覽器，純 JSON API；
    # 但為表禮節（推薦池 API 較敏感）間隔拉到 3 秒
    "offertoday": {"needs_browser": False, "request_delay": 3.0},
}


def site_cfg(source: str) -> dict:
    return SITE_CONFIG.get(source, {})


def delay_for(source: str) -> float:
    return float(site_cfg(source).get("request_delay", REQUEST_DELAY))
