"""
Recruit (www.recruit.com.hk) 爬蟲 — 擴充八站 Wave 1

技術特點
--------
ASP.NET WebForms + Vue 3 混合站。無 Cloudflare、無 CAPTCHA，但有三個坑：

1. **篩選值藏在 hidden 欄位，不在 checkbox**
   畫面上的 checkbox 是 Vue `v-model` 綁定，真正被 POST 出去的是這三條 hidden：
     - `UclRespJobSearchFilterControl$keywordTxt`          關鍵字
     - `UclRespJobSearchFilterControl$locationSearchHidden` 地區（逗號分隔 ID）
     - `UclRespJobSearchFilterControl$jobCatSearchHidden`   職能大類（逗號分隔 ID）
     - `UclRespJobSearchFilterControl$jobFuncSearchHidden`  職能細類（**須同時給 jobCat 才生效**）
   實測：只勾 checkbox 無效（總數不變）；直接填 hidden 才有效
   （engineer 全站 820 筆 → 元朗 15 筆、資訊科技大類 204 筆、元朗+資訊科技 1 筆）。

2. **搜尋鈕在 DOM 中不可見**
   `#UclRespJobSearchFilterControl_searchBtn` 是 `type=submit` 但被 CSS 藏住，
   Playwright 的 `.click()` 會等 30 秒後噴 `element is not visible`。
   改用 JS `el.click()` 直接觸發送出（3~5 秒完成搜尋）。

3. **翻頁只能在真瀏覽器裡做**
   分頁是 `__doPostBack('pagerBottom$...')`。實測用 `requests` 送 `__EVENTTARGET`
   一律無效（伺服器重跑搜尋回第 1 頁，甚至回首頁）；
   但在 Playwright 裡執行 `__doPostBack()` 完全正常。故本站 `use_browser=True`。
   - 每頁 25 筆；`input[name=totalCnt]` 為結果總數。
   - 用「Next」鈕（`pagerBottom$ctl02$ctl00`）逐頁前進最穩（頁碼鈕名稱會隨頁碼位移）。

搜尋流程
--------
  1. GET 首頁 → 填關鍵字 → 塞 hidden 篩選值 → JS 點搜尋鈕
  2. 結果頁（form action = jobseeker/JobSearchResult.aspx）→ 解析 tr.JobGrid
  3. 翻頁 → `__doPostBack('pagerBottom$ctl02$ctl00','')` → 再解析

資料來源
--------
- 列表卡 `tr.JobGrid[id=<jobOrder>]`：職稱 / 公司 / 網址 / 學歷 / 薪資 / 年資 / **刊登日**
  （列表沒有地區欄，需 `--detail` 才補得到）
- 詳情頁 `/job-detail/<公司slug>/<職稱slug>/<jobOrder>`：內含 **JSON-LD JobPosting**
  （地區、行業、僱傭類型、薪資區間、完整描述）

地區 / 職能字典
--------
- `recruit_districts.json`：94 個地區（英文原名 + 45 個中文別名，如 Yuen Long／元朗）
- `recruit_categories.json`：34 大類 + 290 細類（中英雙語別名；細類記錄所屬 cat_id）
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from base_scraper import BaseScraper
from config import DEFAULT_HEADERS, REQUEST_TIMEOUT
from job_model import JobRecord

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


BASE = "https://www.recruit.com.hk"
HOME_URL = BASE + "/"

# ---- 表單元素 ----
KEYWORD_SEL = "input[name='UclRespJobSearchFilterControl$keywordTxt']"
SEARCH_BTN = "#UclRespJobSearchFilterControl_searchBtn"
_HIDDEN_IDS = {
    "location": "UclRespJobSearchFilterControl_locationSearchHidden",
    "jobCat": "UclRespJobSearchFilterControl_jobCatSearchHidden",
    "jobFunc": "UclRespJobSearchFilterControl_jobFuncSearchHidden",
}
# 職位卡
CARD_SEL = "tr.JobGrid"
# 翻頁：用「Next」鈕最穩（頁碼鈕名稱會隨頁碼位移）
PAGER_NEXT_TARGET = "pagerBottom$ctl02$ctl00"

# 排序：結果頁 select[name=sortByDDL] 的選項值
_SORT_MAP = {
    "post_dt_desc": "POST_DATE",
    "post_dt_asc": "POST_DATE",
    "post_date": "POST_DATE",
    "date": "POST_DATE",
    "salary_desc": "SALARY_FROM",
    "salary": "SALARY_FROM",
    "exp": "WORK_EXP_FROM",
    "experience": "WORK_EXP_FROM",
    "edu": "EDU_LEVEL_ID",
    "education": "EDU_LEVEL_ID",
    "relevance": "RELEVANCE_PRIORITY",
}

_HERE = Path(__file__).resolve().parent


def _load_dict(name: str) -> list[dict]:
    try:
        with open(_HERE / name, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning("[recruit] 讀取字典 %s 失敗：%s", name, e)
        return []


_DISTRICTS = _load_dict("recruit_districts.json")
_CATEGORIES = _load_dict("recruit_categories.json")


def _build_lookup(entries: list[dict]) -> dict[str, dict]:
    """建立「別名（小寫）→ 項目」對照表。"""
    lut: dict[str, dict] = {}
    for e in entries:
        keys = set(e.get("aliases") or [])
        keys.add(e.get("name", ""))
        if e.get("zh"):
            keys.add(e["zh"])
        for k in keys:
            if k:
                lut[str(k).strip().lower()] = e
    return lut


_DISTRICT_LUT = _build_lookup(_DISTRICTS)
_CATEGORY_LUT = _build_lookup(_CATEGORIES)

# JSON-LD address 裡可能出現的「假值」——站方沒資料時會塞 N/A 之類的字串，
# 直接當地區寫入會污染資料（實測 25 筆中有 2 筆是 N/A）。
_BAD_LOC = {"", "n/a", "na", "--", "-", "none", "null", "nil", "not specified"}


def _addr_to_location(addr: dict) -> str:
    """把 JSON-LD 的 address 物件轉成地區字串（過濾假值、去重）。"""
    parts: list[str] = []
    for k in ("streetAddress", "addressLocality", "addressRegion"):
        v = str(addr.get(k) or "").strip()
        if v and v.lower() not in _BAD_LOC:
            parts.append(v)
    return " / ".join(dict.fromkeys(parts))


def resolve_districts_named(district_input: Optional[str]) -> tuple[list[str], list[str]]:
    """把使用者輸入解析為 (地區 ID 清單, 地區英文名稱清單)。

    支援中英文（元朗 / Yuen Long）、逗號分隔多區；未知地區警告後忽略。
    名稱用途：列表頁本身**沒有地區欄**，若使用者明確篩選了地區，
    站方保證結果皆屬該區 → 可零請求回填 location（見 `search()`）。
    """
    if not district_input:
        return [], []
    ids: list[str] = []
    names: list[str] = []
    for item in str(district_input).split(","):
        item = item.strip()
        if not item:
            continue
        hit = _DISTRICT_LUT.get(item.lower())
        if hit:
            ids.append(hit["id"])
            nm = (hit.get("name") or "").strip()
            if nm:
                names.append(nm)
        else:
            logger.warning("[recruit] 未知地區：%s（已忽略）", item)
    if ids:
        logger.info("[recruit] 地區過濾：%s（%d 區）", ", ".join(ids), len(ids))
    return ids, names


def resolve_districts(district_input: Optional[str]) -> list[str]:
    """同 `resolve_districts_named`，但只回傳 ID 清單（舊介面，保留相容）。"""
    return resolve_districts_named(district_input)[0]


def resolve_category(category_input: Optional[str]) -> tuple[str, str]:
    """把使用者輸入解析為 (jobCat 大類 ID, jobFunc 細類 ID)。

    Recruit 的特性：**jobFunc 必須搭配所屬 jobCat 才會生效**，單送會被忽略。
    故命中細類時一併回傳它的父類別。
    """
    if not category_input:
        return "", ""
    for item in str(category_input).split(","):
        item = item.strip()
        if not item:
            continue
        hit = _CATEGORY_LUT.get(item.lower())
        if not hit:
            logger.warning("[recruit] 未知職能：%s（已忽略）", item)
            continue
        if hit.get("type") == "jobFunc":
            parent = hit.get("cat_id") or ""
            logger.info(
                "[recruit] 職能過濾：%s（細類 %s / 大類 %s）",
                item, hit["id"], parent or "無",
            )
            if not parent:
                logger.warning(
                    "[recruit] 細類 %s 查無所屬大類，將單送（可能被站方忽略）", hit["id"])
            return parent, hit["id"]
        logger.info("[recruit] 職能過濾：%s（大類 %s）", item, hit["id"])
        return hit["id"], ""
    return "", ""


def resolve_sort(sort_input: Optional[str]) -> str:
    """把通用排序參數轉成 Recruit 的 sortByDDL 選項值。"""
    if not sort_input:
        return ""
    val = _SORT_MAP.get(str(sort_input).strip().lower(), "")
    if val:
        logger.info("[recruit] 排序：%s → %s", sort_input, val)
    else:
        logger.warning("[recruit] 不支援的排序 %s（已忽略）", sort_input)
    return val


class RecruitScraper(BaseScraper):
    source = "recruit"
    use_browser = True       # WebForms 翻頁必須在真瀏覽器內執行 __doPostBack
    list_has_date = True     # 列表卡 td.post-date-col 已有刊登日（YYYY-MM-DD）

    def __init__(self, headers: dict | None = None):
        super().__init__(headers)
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._sig: tuple | None = None
        self._page_no = 0
        self._session = requests.Session()
        self._loc_names: list[str] = []   # --district 解析出的地區名，供列表回填 location

    # ---------- 瀏覽器 ----------
    def _ensure_browser(self):
        if self._page is not None:
            return self._page
        if sync_playwright is None:
            raise RuntimeError("需要 playwright：pip install playwright && playwright install chromium")
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            locale="zh-HK",
            viewport={"width": 1366, "height": 900},
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
        if industry:
            logger.warning("[recruit] 不支援 --industry（該站無行業篩選），已忽略")

        loc_ids, loc_names = resolve_districts_named(district)
        # 列表頁無地區欄：把「使用者明確篩選的地區」記下來，供 _build_record 零請求回填
        self._loc_names = loc_names
        cat_id, func_id = resolve_category(category)
        sort_val = resolve_sort(sort)

        sig = (keyword, tuple(loc_ids), cat_id, func_id, sort_val)
        if page <= 1 or sig != self._sig or self._page_no == 0:
            if not self._new_search(keyword, loc_ids, cat_id, func_id, sort_val):
                return []
            self._sig = sig
            self._page_no = 1

        # 逐頁前進到目標頁（用 Next 鈕，名稱不隨頁碼位移）
        while self._page_no < page:
            if not self._next_page():
                return []
            self._page_no += 1

        return self._parse_current()

    def _new_search(
        self,
        keyword: str,
        loc_ids: list[str],
        cat_id: str,
        func_id: str,
        sort_val: str,
    ) -> bool:
        pg = self._ensure_browser()
        pg.goto(HOME_URL, wait_until="domcontentloaded", timeout=45_000)
        pg.wait_for_selector(KEYWORD_SEL, timeout=20_000)
        if keyword:
            pg.fill(KEYWORD_SEL, keyword)
        # 直接塞 hidden 欄位（Vue v-model 的 checkbox 不會被送出）
        pg.evaluate(
            """([ids, vals]) => {
                const set = (id, v) => {
                    const el = document.getElementById(id);
                    if (!el) return;
                    el.value = v || "";
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                };
                set(ids.location, vals.loc);
                set(ids.jobCat, vals.cat);
                set(ids.jobFunc, vals.func);
            }""",
            [_HIDDEN_IDS, {"loc": ",".join(loc_ids), "cat": cat_id, "func": func_id}],
        )
        # 搜尋鈕被 CSS 藏住 → 用 JS 觸發
        pg.eval_on_selector(SEARCH_BTN, "el => el.click()")
        try:
            pg.wait_for_selector("input[name='totalCnt'], " + CARD_SEL, timeout=45_000)
        except Exception as e:  # noqa: BLE001
            logger.warning("[recruit] 搜尋後等待結果逾時：%s", e)
            return False

        if sort_val:
            self._apply_sort(sort_val)

        total = pg.eval_on_selector_all("input[name='totalCnt']", "els => els.map(e => e.value)")
        logger.info("[recruit] 搜尋完成，結果總數：%s", total[0] if total else "?")
        return True

    def _apply_sort(self, sort_val: str) -> None:
        pg = self._page
        pg.eval_on_selector_all(
            "select[name='sortByDDL']",
            """(els, v) => els.forEach(e => {
                   e.value = v;
                   e.dispatchEvent(new Event('change', {bubbles: true}));
               })""",
            sort_val,
        )
        pg.wait_for_timeout(2500)
        try:
            pg.wait_for_selector(CARD_SEL, timeout=30_000)
        except Exception:  # noqa: BLE001
            pass

    def _next_page(self) -> bool:
        pg = self._page
        # 先確認「Next」鈕可用（到最後一頁時它會帶 disabled 且無 href），
        # 避免每次都乾等 30 秒的 wait_for_selector 逾時
        try:
            usable = pg.eval_on_selector_all(
                "a.next-page",
                """els => els.some(e => !e.hasAttribute('disabled')
                                    && (e.getAttribute('href') || '').indexOf('__doPostBack') >= 0)""",
            )
        except Exception:  # noqa: BLE001
            usable = True
        if not usable:
            logger.info("[recruit] 已到最後一頁（Next 鈕已停用）")
            return False
        try:
            pg.evaluate("t => __doPostBack(t, '')", PAGER_NEXT_TARGET)
            pg.wait_for_timeout(1500)
            pg.wait_for_selector(CARD_SEL, timeout=30_000)
        except Exception as e:  # noqa: BLE001
            logger.warning("[recruit] 翻頁失敗：%s", e)
            return False
        return True

    # ---------- 解析列表 ----------
    _CARD_JS = """
        els => els.map(e => {
            const a = e.querySelector('a.title');
            const c = e.querySelector('a.company');
            const td = cls => { const x = e.querySelector('td.' + cls);
                                return x ? x.textContent.trim() : ''; };
            const exp = e.querySelector('input[id$="_expiryDate"]');
            return {
                id: e.id || '',
                title: a ? a.textContent.trim() : '',
                url: a ? (a.getAttribute('href') || '') : '',
                company: c ? c.textContent.trim() : '',
                salary: td('salary-col'),
                edu: td('edu-col'),
                exp: td('exp-col'),
                posted: td('post-date-col'),
                expiry: exp ? (exp.value || '') : '',
            };
        })
    """

    def _parse_current(self) -> list[JobRecord]:
        pg = self._page
        try:
            raw = pg.eval_on_selector_all(CARD_SEL, self._CARD_JS)
        except Exception as e:  # noqa: BLE001
            logger.warning("[recruit] 解析職位卡失敗：%s", e)
            return []
        jobs: list[JobRecord] = []
        for r in raw or []:
            rec = self._build_record(r)
            if rec:
                jobs.append(rec)
        return jobs

    def _build_record(self, r: dict) -> Optional[JobRecord]:
        job_id = (r.get("id") or "").strip()
        url = (r.get("url") or "").strip()
        if url:
            url = urljoin(BASE, url)
        if not job_id:
            return None
        salary = (r.get("salary") or "").strip()
        if salary in ("--", "-", "N/A"):
            salary = ""
        edu = (r.get("edu") or "").strip()
        exp = (r.get("exp") or "").strip()
        if exp in ("--", "-", "N/A"):
            exp = ""
        # 學歷 / 年資在列表層沒有專屬欄位，合併進 requirements 以免資訊遺失
        bits = [f"學歷：{edu}" if edu else "", f"年資：{exp} 年" if exp else ""]
        requirements = "；".join(b for b in bits if b)
        now = datetime.now().isoformat(timespec="seconds")
        return JobRecord(
            job_id=f"recruit::{job_id}",
            source=self.source,
            title=(r.get("title") or "").strip(),
            company=(r.get("company") or "").strip(),
            # 列表頁本身無地區欄。若使用者只篩了**單一地區**，站方保證結果屬於該區
            # → 零請求回填；多地區聯集時無法判斷各筆歸屬，寧可留空（不猜），
            #   改用 --fill-location（逐筆 AJAX）或 --detail 取得精確值。
            location=(self._loc_names[0] if len(self._loc_names) == 1 else ""),
            salary=salary,
            job_type="",
            industry="",
            description="",
            requirements=requirements,
            url=url or (BASE + "/jobseeker/JobDetail.aspx?jobOrder=" + job_id),
            posted_date=(r.get("posted") or "").strip(),
            scraped_at=now,
        )

    # ---------- 詳情頁（JSON-LD） ----------
    def get_detail(self, job_url: str) -> Optional[JobRecord]:
        r = self._session.get(
            job_url,
            headers={**DEFAULT_HEADERS, **(self.headers or {})},
            timeout=REQUEST_TIMEOUT,
        )
        html = r.text
        m = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        if not m:
            logger.warning("[recruit] 詳情頁無 JSON-LD：%s", job_url)
            return None
        # 站方 JSON-LD 內含未跳脫的控制字元（換行等），需先清除再解析
        try:
            data = json.loads(re.sub(r"[\x00-\x1f\x7f]", " ", m.group(1)), strict=False)
        except Exception as e:  # noqa: BLE001
            logger.warning("[recruit] JSON-LD 解析失敗：%s", e)
            return None
        if data.get("@type") != "JobPosting":
            return None

        # 地區：jobLocation → address（streetAddress 常是「New Territories」這類大區）
        loc_parts = []
        jl = data.get("jobLocation")
        if isinstance(jl, list):
            jl = jl[0] if jl else {}
        addr = (jl or {}).get("address") or {}
        for k in ("streetAddress", "addressLocality", "addressRegion"):
            v = addr.get(k)
            if v:
                loc_parts.append(str(v).strip())
        # 三個欄位常重複（如 New Territories / Hong Kong / Hong Kong），去重後再串
        loc_parts = list(dict.fromkeys(loc_parts))

        # 薪資：baseSalary 可能是 N/A
        sal_raw = (data.get("baseSalary") or {}).get("value") or {}
        salary = ""
        if sal_raw:
            unit = sal_raw.get("unitText") or ""
            lo, hi = sal_raw.get("minValue"), sal_raw.get("maxValue")
            nums = [str(x) for x in (lo, hi) if x and str(x) not in ("N/A", "None")]
            if nums:
                salary = " - ".join(dict.fromkeys(nums))
                if unit:
                    salary += f" {unit}"

        emp = data.get("employmentType") or ""
        if isinstance(emp, list):
            emp = ", ".join(str(x) for x in emp)
        emp_map = {"FULL_TIME": "全職", "PART_TIME": "兼職",
                   "CONTRACTOR": "合約", "TEMPORARY": "臨時", "INTERN": "實習"}
        job_type = emp_map.get(str(emp).upper(), emp)

        posted = (data.get("datePosted") or "")[:10]
        now = datetime.now().isoformat(timespec="seconds")
        return JobRecord(
            job_id=f"recruit::{self._job_id_from_url(job_url)}",
            source=self.source,
            title=(data.get("title") or "").strip(),
            company=((data.get("hiringOrganization") or {}).get("name") or "").strip(),
            location=" / ".join(loc_parts),
            salary=salary,
            job_type=job_type,
            industry=(data.get("industry") or "").strip(),
            description=self._clean_html(data.get("description") or ""),
            requirements=(data.get("occupationalCategory") or "").strip(),
            url=(data.get("url") or job_url).strip(),
            posted_date=posted,
            scraped_at=now,
        )

    @staticmethod
    def _job_id_from_url(url: str) -> str:
        return url.rstrip("/").rsplit("/", 1)[-1]

    @staticmethod
    def _clean_html(s: str) -> str:
        return BeautifulSoup(str(s), "html.parser").get_text(" ", strip=True)

    # ---------- 日期解析 ----------
    def days_since_posted(self, job: JobRecord) -> int | None:
        s = (getattr(job, "posted_date", "") or "").strip()
        if not s:
            return None
        s = s[:10]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                d = datetime.strptime(s, fmt).date()
            except ValueError:
                continue
            return max(0, (date.today() - d).days)
        return None

    # ---------- 收尾 ----------
    # ---------- 列表補地區（AJAX 詳情端點，純 requests） ----------
    # 列表卡（tr.JobGrid）確實沒有地區欄（實測只有 title-company / edu / salary /
    # exp / post-date / relevance）。但點卡片時前端會打
    # `/jobseeker/JobDetail.aspx?jobOrder=<id>&ajax=Y`（見 N_common.js 的
    # getAjaxJobDetailUrl），回傳約 35KB 且含 JSON-LD address → **純 requests 可拿**，
    # 不必開瀏覽器。故提供「逐筆補地區」的選項。
    AJAX_DETAIL_URL = BASE + "/jobseeker/JobDetail.aspx"

    def _fetch_location(self, jid: str) -> str:
        """用輕量 AJAX 端點取單筆地區；失敗或無值回空字串（不拋出）。"""
        if not jid:
            return ""
        try:
            r = self._session.get(
                self.AJAX_DETAIL_URL,
                params={"jobOrder": jid, "ajax": "Y"},
                headers={**DEFAULT_HEADERS, **(self.headers or {})},
                timeout=REQUEST_TIMEOUT,
            )
            if r.status_code != 200:
                logger.warning("[recruit] AJAX 地區 HTTP %s：%s", r.status_code, jid)
                return ""
        except Exception as e:  # noqa: BLE001
            logger.warning("[recruit] AJAX 地區請求失敗 %s：%s", jid, e)
            return ""
        m = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', r.text, re.S)
        if not m:
            return ""
        try:
            data = json.loads(re.sub(r"[\x00-\x1f\x7f]", " ", m.group(1)), strict=False)
        except Exception:  # noqa: BLE001
            return ""
        jl = data.get("jobLocation")
        if isinstance(jl, list):
            jl = jl[0] if jl else {}
        return _addr_to_location((jl or {}).get("address") or {})

    def fill_locations(self, records: list[JobRecord]) -> int:
        """對整批紀錄補地區（列表階段專用）。回傳成功補上的筆數。

        ⚠️ 每筆會多打 1 支請求（25 筆/頁 → 25 支），故**預設關閉**，
        需由 `--fill-location` 明確啟用；內建 `self._sleep()` 節流。
        """
        n = 0
        for rec in records or []:
            if rec.location:          # 已有值（如單區 --district 回填）就不再打
                continue
            jid = (rec.job_id or "").split("::")[-1]
            loc = self._fetch_location(jid)
            if loc:
                rec.location = loc
                n += 1
            self._sleep()
        logger.info("[recruit] 列表補地區：%d/%d 筆取得地區", n, len(records or []))
        return n

    def close(self) -> None:
        for attr in ("_context", "_browser"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:  # noqa: BLE001
                    pass
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
        self._pw = self._browser = self._context = self._page = None
        if self._session is not None:
            try:
                self._session.close()
            except Exception:  # noqa: BLE001
                pass
