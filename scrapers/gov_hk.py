"""
勞工處互動就業服務 (jobs.gov.hk / www1.jobs.gov.hk) 爬蟲 (Phase 2)

技術特點
--------
勞工處 IES 為 ASP.NET MVC 伺服器渲染網站，無 Cloudflare、無 CAPTCHA，難度最低。
真實網站位於 www1.jobs.gov.hk 子域（首頁會 307 跳轉過去），語言路徑 /0/tc/。

搜尋流程：
  1. POST /0/tc/jobseeker/jobsearch/search/  帶 criteria.* 表單（關鍵字、地區等）
     -> 服務端記住搜尋條件 (Session)，回傳第 1 頁結果
  2. 翻頁 GET /0/tc/jobseeker/jobsearch/quickview/?direct=False&page=N
     -> 沿用同一 Session 的搜尋條件，回傳第 N 頁（每頁約 20 筆）

結果列表：每筆職位為 div.row.item[data-jobcard]，內含標題 / 薪資 / 地點 / 職位編號。
詳情頁 (jobCard)：用穩定 id 標識 -> #empName(公司) #locDesc(地區)
  #jobRemark(職責) #eduRemark(資歷/要求)。

地區過濾：勞工處用獨立的地區數字 ID（與 Moovup 體系不同），見 gov_hk_districts.json。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from base_scraper import BaseScraper
from config import REQUEST_TIMEOUT
from job_model import JobRecord

logger = logging.getLogger(__name__)

BASE = "https://www1.jobs.gov.hk"
SEARCH_URL = BASE + "/0/tc/jobseeker/jobsearch/search/"
QUICKVIEW_URL = BASE + "/0/tc/jobseeker/jobsearch/quickview/"
DETAIL_URL = BASE + "/0/tc/jobseeker/jobCard/"

_DISTRICT_FILE = Path(__file__).resolve().parent / "gov_hk_districts.json"


def _load_districts() -> list[dict]:
    try:
        with open(_DISTRICT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning("[gov_hk] 讀取地區字典失敗：%s", e)
        return []


_DISTRICTS = _load_districts()
# 反向對照：地區名 -> 數字 ID（忽略「區」字與分組標題，便於模糊匹配）
_NAME2ID: dict[str, str] = {}
for _d in _DISTRICTS:
    _name = _d.get("name", "")
    if _name.startswith("--"):
        continue  # 跳過「--全香港島--」等分組標題
    _NAME2ID[_name] = _d["id"]
    _NAME2ID[_name.replace("區", "")] = _d["id"]


def resolve_districts(district_input: Optional[str]) -> list[str]:
    """把使用者輸入解析為勞工處地區數字 ID 清單。

    支援中文名（屯門 / 屯門區）、逗號分隔多區；未知地區忽略並提示。
    """
    if not district_input:
        return []
    ids: list[str] = []
    for item in str(district_input).split(","):
        item = item.strip()
        if not item:
            continue
        code = _NAME2ID.get(item) or _NAME2ID.get(item.replace("區", ""))
        if code:
            ids.append(code)
        else:
            logger.warning("[gov_hk] 未知地區：%s（已忽略）", item)
    if ids:
        logger.info("[gov_hk] 地區過濾 ID：%s", ", ".join(ids))
    return ids


# ---------- 工作種類（空缺類別 / criteria.jobType） ----------
_CATEGORY_FILE = Path(__file__).resolve().parent / "gov_hk_categories.json"


def _load_categories() -> list[dict]:
    try:
        with open(_CATEGORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning("[gov_hk] 讀取工作種類字典失敗：%s", e)
        return []


_CATEGORIES = _load_categories()
_NAME2CAT: dict[str, str] = {c["name"]: c["id"] for c in _CATEGORIES}


def resolve_category(category_input: Optional[str]) -> str:
    """把使用者輸入（中文名）解析為勞工處空缺類別數字 ID。

    表單為單選，故只取第一個有效值；不支援 / 空輸入回傳空字串（= 所有類別）。
    """
    if not category_input:
        return ""
    for item in str(category_input).split(","):
        item = item.strip()
        if not item:
            continue
        code = _NAME2CAT.get(item)
        if code:
            logger.info("[gov_hk] 工作種類過濾 ID：%s（%s）", code, item)
            return code
        logger.warning("[gov_hk] 未知工作種類：%s（已忽略）", item)
    return ""


# ---------- 行業（criteria.industry） ----------
_INDUSTRY_FILE = Path(__file__).resolve().parent / "gov_hk_industries.json"


def _load_industries() -> list[dict]:
    try:
        with open(_INDUSTRY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning("[gov_hk] 讀取行業字典失敗：%s", e)
        return []


_INDUSTRIES = _load_industries()
_NAME2IND: dict[str, str] = {i["name"]: i["id"] for i in _INDUSTRIES}


def resolve_industry(industry_input: Optional[str]) -> str:
    """把使用者輸入（中文名）解析為勞工處行業數字 ID。

    表單為單選，故只取第一個有效值；不支援 / 空輸入回傳空字串（= 所有行業，
    已實測：不送 criteria.industry 或送空字串皆代表「所有行業」）。
    """
    if not industry_input:
        return ""
    for item in str(industry_input).split(","):
        item = item.strip()
        if not item:
            continue
        code = _NAME2IND.get(item)
        if code:
            logger.info("[gov_hk] 行業過濾 ID：%s（%s）", code, item)
            return code
        logger.warning("[gov_hk] 未知行業：%s（已忽略）", item)
    return ""


class GovHkScraper(BaseScraper):
    source = "gov_hk"
    use_browser = False

    def __init__(self, headers: dict | None = None):
        super().__init__(headers)
        self.session = requests.Session()
        self._posted = False
        self._last_keyword: Optional[str] = None
        self._last_district: Optional[str] = None
        self._last_category: str = ""
        self._last_industry: str = ""
        self._last_sort: str = ""

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
        district_ids = resolve_districts(district)
        cat_id = resolve_category(category)
        ind_id = resolve_industry(industry)
        # 關鍵字 / 地區 / 工作種類 / 行業 / 排序 任一變動時需重新 POST；否則直接翻頁
        need_post = (
            page == 1
            or not self._posted
            or self._last_keyword != keyword
            or self._last_district != district
            or self._last_category != cat_id
            or self._last_industry != ind_id
            or self._last_sort != (sort or "")
        )
        if need_post:
            soup = self._get_search_page()
            data = self._build_form(soup, keyword, district_ids, cat_id, ind_id, sort)
            r = self.session.post(
                SEARCH_URL,
                headers={**self.headers, "Referer": SEARCH_URL},
                data=data,
                timeout=REQUEST_TIMEOUT,
            )
            self._posted = True
            self._last_keyword = keyword
            self._last_district = district
            self._last_category = cat_id
            self._last_industry = ind_id
            self._last_sort = sort or ""
            html = r.text
        else:
            r = self.session.get(
                QUICKVIEW_URL,
                params={"direct": "False", "page": page},
                headers=self.headers,
                timeout=REQUEST_TIMEOUT,
            )
            html = r.text
        return self._parse_list(html)

    def _get_search_page(self) -> BeautifulSoup:
        r = self.session.get(SEARCH_URL, headers=self.headers, timeout=REQUEST_TIMEOUT)
        return BeautifulSoup(r.text, "lxml")

    @staticmethod
    def _build_form(
        soup: BeautifulSoup,
        keyword: str,
        district_ids: list[str],
        cat_id: str = "",
        ind_id: str = "",
        sort: str = "",
    ) -> dict:
        data: dict = {}
        for inp in soup.find_all("input"):
            n = inp.get("name")
            if not n:
                continue
            t = inp.get("type", "text")
            if t in ("hidden", "text"):
                data[n] = inp.get("value", "")
        data["criteria.searchField"] = keyword
        data["criteria.searchByOption"] = "1"   # 1=按職位名稱搜尋
        # 工作種類 / 行業：空字串代表「所有」（已實測：不送或送空皆為不篩選）
        data["criteria.jobType"] = cat_id
        data["criteria.industry"] = ind_id
        # 排序：空字串 = 網站預設；否則送 criteria.sortBy（如 post_dt_desc）
        if sort:
            data["criteria.sortBy"] = sort
        if district_ids:
            data["criteria.selectedDistricts"] = district_ids
        return data

    # ---------- 解析列表 ----------
    def _parse_list(self, html: str) -> list[JobRecord]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.find_all("div", class_="item", attrs={"data-jobcard": True})
        jobs: list[JobRecord] = []
        for c in cards:
            rec = self._parse_card(c)
            if rec:
                jobs.append(rec)
        return jobs

    def _parse_card(self, c) -> Optional[JobRecord]:
        # 標題：d-flex 容器內第一個 div（排除儲存按鈕 a）
        title_div = c.select_one("div.d-flex.justify-content-between")
        title = ""
        if title_div:
            d = title_div.find("div")
            title = d.get_text(strip=True) if d else ""
        salary_el = c.select_one(".icon_salary")
        salary = salary_el.get_text(strip=True) if salary_el else ""
        loc_el = c.select_one(".icon_address")
        location = loc_el.get_text(strip=True) if loc_el else ""
        jobcard = c.get("data-jobcard", "")
        url = urljoin(BASE, jobcard)
        # 職位編號（job_id）
        inp = c.find("input")
        ordno = inp.get("value") if (inp and inp.get("value")) else ""
        job_id = f"gov_hk_{ordno}" if ordno else url
        now = datetime.now().isoformat(timespec="seconds")
        return JobRecord(
            job_id=job_id,
            source=self.source,
            title=title,
            company="",
            location=location,
            salary=salary,
            job_type="",
            description="",
            requirements="",
            url=url,
            posted_date="",
            scraped_at=now,
        )

    # ---------- 詳情頁 ----------
    def get_detail(self, job_url: str) -> Optional[JobRecord]:
        r = self.session.get(job_url, headers=self.headers, timeout=REQUEST_TIMEOUT)
        soup = BeautifulSoup(r.text, "lxml")
        emp = soup.find(id="empName")
        loc = soup.find(id="locDesc")
        remark = soup.find(id="jobRemark")
        edu = soup.find(id="eduRemark")
        posted = soup.find(id="postedDt")          # 刊登日期，格式 DD/MM/YYYY
        # 行業：detail 頁以「行業 :」label + 下一個 span 顯示（如「建造業」）
        ind_label = soup.find(
            "span", string=lambda t: t and t.strip().startswith("行業 :")
        )
        industry = ""
        if ind_label:
            ind_val = ind_label.find_next_sibling("span")
            if ind_val:
                industry = ind_val.get_text(strip=True)
        clip = soup.find(attrs={"data-ordno": True})
        ordno = clip.get("data-ordno") if clip else ""
        job_id = f"gov_hk_{ordno}" if ordno else job_url
        now = datetime.now().isoformat(timespec="seconds")
        return JobRecord(
            job_id=job_id,
            source=self.source,
            company=emp.get_text(strip=True) if emp else "",
            location=loc.get_text(strip=True) if loc else "",
            description=remark.get_text(strip=True) if remark else "",
            requirements=edu.get_text(strip=True) if edu else "",
            url=job_url,
            posted_date=posted.get_text(strip=True) if posted else "",
            industry=industry,
            scraped_at=now,
        )

    # ---------- 日期解析（供 base 的 --days 篩選使用） ----------
    def days_since_posted(self, job: JobRecord) -> int | None:
        s = getattr(job, "posted_date", "")
        if not s:
            return None
        try:
            d = datetime.strptime(s, "%d/%m/%Y").date()
        except ValueError:
            return None
        # max(0, ...) 鉗制未來日期（站方時區差可能出現明天刊登）：
        # 對 --days 過濾結果零影響（負數與 0 對任何 days>=0 的判斷同真），僅防禦性收邊
        return max(0, (date.today() - d).days)

    def close(self) -> None:
        if self.session:
            self.session.close()
