"""
Moovup 好工速遞爬蟲 (Phase 3)

技術特點
--------
Moovup 使用 Nuxt.js SSR，職位結果由前端透過 GraphQL 端點取得：
    POST https://api.moovup.com/v2/seeker
        query: QueryJobs(...)   -> data.job_search.result[]
        auth : Bearer <JWT>     (JWT 由 POST /v2/create-anonymous 取得)

該 API 受 Cloudflare 保護，直接 requests 會被擋（403/405）。
因此本爬蟲使用 Playwright 真實瀏覽器：
  1. 載入首頁自動通過 Cloudflare Turnstile，取得 cf_clearance cookie
  2. 在瀏覽器上下文內用 fetch() 呼叫 GraphQL（共享瀏覽器指紋，穩定通過）
  3. 解析結構化 JSON，比解析 DOM 更穩定

分頁：GraphQL 變數 offset / limit（每頁 12 筆）。
詳情頁：另開頁面解析職責 / 要求 / 發佈時間。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from base_scraper import BaseScraper
from job_model import JobRecord

# ---- 地區字典（中文名 / 英文名 / shortCode / _id）----
# 來源：Moovup 前端 JS bundle，已實測 shortCode 可作為 GraphQL district 過濾值
_DISTRICT_FILE = Path(__file__).resolve().parent / "moovup_districts.json"


def _load_districts() -> list[dict]:
    try:
        with open(_DISTRICT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning("[moovup] 讀取地區字典失敗：%s", e)
        return []


_DISTRICTS = _load_districts()
_ZH2CODE = {d["zh"]: d["shortCode"] for d in _DISTRICTS}
_EN2CODE = {d["en"]: d["shortCode"] for d in _DISTRICTS}
_CODE2CODE = {d["shortCode"]: d["shortCode"] for d in _DISTRICTS}
# 反向對照：英文區名 / shortCode -> 中文區名（用於把職位掛載的多個地區轉中文）
_EN2ZH = {d["en"]: d["zh"] for d in _DISTRICTS}
_SHORT2ZH = {d["shortCode"]: d["zh"] for d in _DISTRICTS}


def resolve_districts(district_input: Optional[str]) -> list[str]:
    """把使用者輸入解析為 shortCode 清單。

    接受：中文名（深水埗）/ 英文名（Sham Shui Po）/ shortCode（000017），
    可用逗號分隔多個地區。未知地區會忽略並提示。
    """
    if not district_input:
        return []
    codes: list[str] = []
    for item in str(district_input).split(","):
        item = item.strip()
        if not item:
            continue
        code = _ZH2CODE.get(item) or _EN2CODE.get(item) or _CODE2CODE.get(item)
        if code:
            codes.append(code)
        else:
            logger.warning(
                "[moovup] 未知地區：%s（已忽略，參見 docs/地區編號對照表.md）", item
            )
    if codes:
        logger.info("[moovup] 地區過濾 shortCode：%s", ", ".join(codes))
    return codes

try:
    from playwright.sync_api import sync_playwright
    from playwright.sync_api import TimeoutError as PWTimeout
except ImportError:  # pragma: no cover
    sync_playwright = None
    PWTimeout = Exception  # 未裝 Playwright 時 _ensure_browser 會先擋下，此別名僅保語法可用

logger = logging.getLogger(__name__)

MOOVUP_BASE = "https://moovup.com"
API_SEEKER = "https://api.moovup.com/v2/seeker"
API_ANON = "https://api.moovup.com/v2/create-anonymous"

# GraphQL 搜尋查詢（從網站前端還原，欄位涵蓋列表所需全部資訊）
QUERY_JOBS = """
query QueryJobs (
  $company: ID
  $exclude: [ID]
  $district: [ID]
  $employment: [Employment]
  $workingHour: [JobSearchWorkingHour]
  $fromWorkingDaysPerWeek: Float
  $fromWorkingHoursPerDay: Float
  $hourlyRate: Float
  $monthlyRate: Float
  $jobType: [ID]
  $limit: Int
  $offset: Int
  $term: String
  $latlng: MLatLng
) {
  job_search(
    company: $company
    exclude: $exclude
    term: $term,
    district: $district,
    employment: $employment,
    from_working_days_per_week: $fromWorkingDaysPerWeek,
    from_working_hours_per_day: $fromWorkingHoursPerDay,
    hourly_rate: $hourlyRate,
    monthly_rate: $monthlyRate,
    job_type: $jobType,
    limit: $limit,
    offset: $offset,
    working_hour: $workingHour,
    latlng: $latlng
  ) {
    result {
      _id
      address { district_name district_short_code }
      company { company_logo_thumbnail name }
      employment
      from_hourly_rate
      from_monthly_rate
      to_hourly_rate
      to_monthly_rate
      job_name
      slug { locale value }
    }
    total
  }
}
"""

# 僱傭類型枚舉 -> 中文
EMP_MAP = {
    "FullTime": "全職",
    "PartTime": "兼職",
    "Contract": "合約",
    "Temporary": "臨時工",
    "Internship": "實習",
    "Freelance": "自由職業",
    "Gig": "散工",
}


class MoovupScraper(BaseScraper):
    source = "moovup"
    use_browser = True

    def __init__(self, headers: dict | None = None, limit: int = 12):
        super().__init__(headers)
        self.limit = limit
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None
        self._jwt: Optional[str] = None
        self._total: Optional[int] = None

    # ---------------- 瀏覽器生命週期 ----------------
    def _ensure_browser(self) -> None:
        if self._page is not None:
            return
        if sync_playwright is None:
            raise RuntimeError(
                "未安裝 Playwright，請先執行：pip install playwright && playwright install chromium"
            )
        self._pw = sync_playwright().start()
        ua = self.headers.get("User-Agent", "")
        self._browser = self._pw.chromium.launch(headless=True)
        self._ctx = self._browser.new_context(
            user_agent=ua,
            locale="zh-HK",
        )
        self._page = self._ctx.new_page()
        # 預熱：載入首頁，讓 Cloudflare 自動通過並種下 cf_clearance cookie
        logger.info("[moovup] 啟動瀏覽器並通過 Cloudflare...")
        self._page.goto(MOOVUP_BASE + "/hk/", wait_until="domcontentloaded", timeout=60000)
        self._page.wait_for_timeout(2500)
        self._jwt = self._get_anon_token()
        if self._jwt:
            logger.info("[moovup] 已取得匿名 JWT。")
        else:
            logger.warning("[moovup] 未取得匿名 JWT，API 可能需驗證。")

    def close(self) -> None:
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()
            self._browser = None
            self._page = None
            self._ctx = None
            self._pw = None

    # ---------------- 內部 API 呼叫 ----------------
    def _get_anon_token(self) -> Optional[str]:
        js = (
            "async () => {"
            "  try {"
            "    const r = await fetch('%s', {method:'POST',"
            "      headers:{'Content-Type':'application/json'}, body:'{}'});"
            "    const j = await r.json();"
            "    return j.access_token || (j.data && j.data.access_token) || null;"
            "  } catch(e) { return null; }"
            "}" % API_ANON
        )
        try:
            return self._page.evaluate(js)
        except Exception as e:  # noqa: BLE001
            logger.warning("[moovup] 取得匿名 token 失敗：%s", e)
            return None

    def _graphql(self, query: str, variables: dict) -> dict:
        js = (
            "async (args) => {"
            "  const headers = {'Content-Type':'application/json'};"
            "  if (args.token) headers['Authorization'] = 'Bearer ' + args.token;"
            "  const body = JSON.stringify({query: args.query, variables: args.variables});"
            "  const r = await fetch('%s', {method:'POST', headers: headers, body: body});"
            "  return await r.json();"
            "}" % API_SEEKER
        )
        return self._page.evaluate(js, {"query": query, "variables": variables, "token": self._jwt})

    # ---------------- 欄位轉換 ----------------
    @staticmethod
    def _slug_zh(job: dict) -> str:
        slug = job.get("slug") or []
        for s in slug:
            if s.get("locale") == "zh-hant":
                return s.get("value", "")
        return slug[0].get("value", "") if slug else ""

    @staticmethod
    def _fmt_salary(job: dict) -> str:
        fm = job.get("from_monthly_rate")
        tm = job.get("to_monthly_rate")
        fh = job.get("from_hourly_rate")
        th = job.get("to_hourly_rate")

        def kfmt(v):
            if v is None:
                return ""
            v = float(v)
            return f"{v / 1000:.0f}K" if v >= 1000 else f"{v:.0f}"

        def nfmt(v):
            return "" if v is None else f"{float(v):.0f}"

        if fm or tm:
            lo, hi = kfmt(fm), kfmt(tm)
            s = f"${lo}"
            if hi and hi != lo:
                s += f"-{hi}"
            return s + "/月"
        if fh or th:
            lo, hi = nfmt(fh), nfmt(th)
            s = f"${lo}"
            if hi and hi != lo:
                s += f"-{hi}"
            return s + "/小時"
        return ""

    def _to_record(self, job: dict) -> JobRecord:
        _id = job.get("_id", "")
        slug_zh = self._slug_zh(job)
        if slug_zh:
            url = f"{MOOVUP_BASE}/hk/job/{slug_zh}/{_id}/"
        else:
            url = f"{MOOVUP_BASE}/hk/job/{_id}/"

        addr = job.get("address") or []
        # 集齊職位掛載的「所有」地區，全部轉中文後合併成一欄（用 、 分隔）。
        # Moovup 單筆職位可掛多個地區，使用者要求保存時全部地區都存在同一欄。
        locations: list[str] = []
        for a in addr:
            en = (a.get("district_name") or "").strip()
            code = (a.get("district_short_code") or "").strip()
            zh = _EN2ZH.get(en) or _SHORT2ZH.get(code) or en
            if zh and zh not in locations:
                locations.append(zh)
        location = "、".join(locations)
        # 回退：若 API 未回傳 address，則取 slug 末端的中文地區名
        if not location and slug_zh:
            parts = slug_zh.split("-")
            if parts:
                location = parts[-1]
        emp = job.get("employment", "")
        job_type = EMP_MAP.get(emp, emp)
        company = (job.get("company") or {}).get("name", "")
        title = job.get("job_name", "")

        return JobRecord(
            job_id=JobRecord.make_id(self.source, _id),
            source=self.source,
            title=title,
            company=company,
            location=location,
            salary=self._fmt_salary(job),
            job_type=job_type,
            url=url,
            raw=job,
        )

    # ---------------- 公開介面 ----------------
    def scrape_all(self, *args, **kwargs):
        """--days 不支援 Moovup（詳情頁日期為中文相對文字，未穩定解析）。

        依 main.py 對 --days 的說明（「moovup 不支援，傳入會警告並忽略」），
        在此攔下 days 參數：警告後忽略，不觸發 base 的「強制抓詳情 + 逐筆過濾」
        （否則 days_since_posted 回 None 會靜默丟光所有職位）。
        僅影響本站（跨站隔離），其餘參數原樣透傳。"""
        if kwargs.get("days") is not None:
            logger.warning(
                "[moovup] --days 不支援 Moovup（詳情日期為相對文字），已忽略此篩選")
            kwargs["days"] = None
        return super().scrape_all(*args, **kwargs)

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
        offset = (page - 1) * self.limit
        district_codes = resolve_districts(district)
        variables = {
            "company": None,
            "district": district_codes,
            "employment": [],
            "fromWorkingDaysPerWeek": None,
            "fromWorkingHoursPerDay": None,
            "hourlyRate": None,
            "jobType": [],
            "latlng": None,
            "limit": self.limit,
            "monthlyRate": None,
            "offset": offset,
            "term": keyword,
            "workingHour": [],
        }
        data = self._with_retry(self._graphql, QUERY_JOBS, variables)
        js = (data or {}).get("data", {}).get("job_search", {})
        if page == 1:
            self._total = js.get("total")
            logger.info("[moovup] 關鍵字『%s』共 %s 筆職位。", keyword, self._total)
        result = js.get("result", []) or []
        return [self._to_record(j) for j in result]

    def get_detail(self, job_url: str) -> Optional[JobRecord]:
        self._ensure_browser()
        # networkidle 在 Nuxt SPA（常駐連線）下可能永不觸發；逾時不視為失敗——
        # 頁面導航通常已完成（SSR 內容已在 DOM），帶著已載入內容繼續解析即可，
        # 避免動輒乾等 60 秒再觸發整輪重試。
        try:
            self._page.goto(job_url, wait_until="networkidle", timeout=60000)
        except PWTimeout:
            logger.warning("[moovup] networkidle 等待逾時（SPA 常見），以已載入內容繼續")
        self._page.wait_for_timeout(2000)
        # 從 URL 取出職位 UUID，還原與列表一致的 job_id
        m = re.search(
            r"/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
            job_url,
        )
        _id = m.group(1) if m else ""
        job_id = JobRecord.make_id(self.source, _id)
        info = self._page.evaluate(
            r"""() => {
                const txt = (sel) => {
                    const e = document.querySelector(sel);
                    return e ? (e.textContent || '').trim() : '';
                };
                const desc = txt('[class*="duty"]');
                let req = '';
                document.querySelectorAll('[class*="requirement"]').forEach(e => {
                    const t = (e.textContent || '').trim();
                    if (t) req += t + '\n';
                });
                let posted = '';
                const bodyTxt = document.body.textContent || '';
                const m = bodyTxt.match(/(\d+)\s*(個月前|天前|日前|小時前|週前|個星期前)/);
                if (m) posted = m[0];
                return {desc, req: req.trim(), posted};
            }"""
        )
        return JobRecord(
            job_id=job_id,
            url=job_url,
            source=self.source,
            description=info.get("desc", ""),
            requirements=info.get("req", ""),
            posted_date=info.get("posted", ""),
        )

    @property
    def total(self) -> Optional[int]:
        return self._total
