"""
JobMarket 求職廣場 (www.jobmarket.com.hk) 爬蟲 — 擴充八站 Wave 1

技術特點
--------
J2EE / JSP 站。**全程普通 requests 即可**（use_browser=False），
無 Cloudflare 挑戰（頁面僅載入 CF 腳本）、無 CAPTCHA、robots 極寬鬆（僅禁 /UpFiles/）。

架構：搜尋殼頁 `/Jobs/search?...` 只是一層 iframe 容器，
真正的職位列表由 **iframe 內的 `/Job/JobList` 端點伺服器渲染**：

  /Job/JobList?Searchtext=K&Page=N&AreaID=..&AreaLocationID=..&
              JobFunctionID=..&SubJobFunctionID=..&JobIndustryID=..

  - 每頁 20 筆；`Page=N` 翻頁（實測 1/2/3 頁無重複）。
  - 每張卡（`div.job-list-con`）：職稱 `h3`、公司 `p.company-name`、
    **刊登日 `p.post-date`（`04 Sep 2026`）**、job id 在 `a.saved-a` 的 `save-id`
    屬性（同 `li[data-jobid]`）。
  - ⚠️ 關鍵字參數名是 **`Searchtext`**，不是 `keyword`（站方 iframe 也用錯，
    `keyword=engineer` 會被無視、回全站 3594 筆——這是站方殼頁與列表端點
    參數名不一致的坑）。

列表卡本身**沒有地區欄**（`p.company-addr` 顯示 "loading"），地區由站方 JS
呼叫批次 API **`/API/Web/GetJobDetail/<id1,id2,...>`** 補回。本爬蟲在列表階段
即呼叫同一 API（每頁 1 次），一次補齊 JobLocation / JobType / JobIndustry /
Qualification / Benefit / JobDetails——故 `location` 預設就有值，不必 --detail。

詳情頁（`--detail` 才抓）：`/Job/CurrentJob?Jobid=<id>`（普通 GET），
含 `.job-post-content`（完整描述）、`.job-par`（行業/職能）、`.benefits`。

篩選體系（全部直接進 JobList 端點，不需瀏覽網址 slug）
--------
- 地區：`AreaID`（5 大區：香港島/九龍/新界/離島/其他）與
  `AreaLocationID`（75 子區，如元朗=68），皆逗號多選。
- 職能：`JobFunctionID`（28 大類）+ `SubJobFunctionID`（195 細類）；
  細類**可單送**（與 Recruit 不同，無需搭配大類）。
- 行業：`JobIndustryID`（30 業）。
- 排序：站方 UI 的 Order 參數實測無有效效果（Order=PostDate 甚至回 0 筆），
  列表大致按刊登日新→舊（job id 遞減；**頂部推廣／置頂區塊不參與排序且通常偏舊**）
  → `--sort` 一律警告後忽略。此例外不影響 `list_sorted_desc` 的提早停翻：
  推廣區塊只在頂部，若整頁皆過期，後頁只會更舊。

字典（本站專屬，與其他六站互不混用）
--------
- `jobmarket_districts.json`：80 項（5 AreaID + 75 AreaLocationID，中英雙語）
- `jobmarket_categories.json`：223 項（28 大類 + 195 細類，細類記 cat_id）
- `jobmarket_industries.json`：30 項（中英雙語）
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from base_scraper import BaseScraper
from config import DEFAULT_HEADERS, REQUEST_TIMEOUT
from job_model import JobRecord

logger = logging.getLogger(__name__)

BASE = "https://www.jobmarket.com.hk"
JOBLIST_URL = BASE + "/Job/JobList"
BATCH_API_URL = BASE + "/API/Web/GetJobDetail/"

# ---- 列表卡選擇器 ----
CARD_SEL = "div.job-list-con"
# ---- 詳情頁選擇器（/Job/CurrentJob）----
DETAIL_TITLE_SEL = ".job-post"
DETAIL_DESC_SEL = ".job-post-content"
DETAIL_DATE_SEL = ".job-list-detail-date"
DETAIL_INDUSTRY_SEL = ".job-par"
DETAIL_BENEFIT_SEL = ".benefits"

_HERE = Path(__file__).resolve().parent


def _load_dict(name: str) -> list[dict]:
    try:
        with open(_HERE / name, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning("[jobmarket] 讀取字典 %s 失敗：%s", name, e)
        return []


_DISTRICTS = _load_dict("jobmarket_districts.json")
_CATEGORIES = _load_dict("jobmarket_categories.json")
_INDUSTRIES = _load_dict("jobmarket_industries.json")


def _build_lookup(entries: list[dict]) -> dict[str, dict]:
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
_INDUSTRY_LUT = _build_lookup(_INDUSTRIES)


def _resolve_param(district_input: Optional[str]) -> tuple[list[str], list[str]]:
    """把使用者輸入解析為 (AreaID 清單, AreaLocationID 清單)。"""
    areas: list[str] = []
    locs: list[str] = []
    if not district_input:
        return areas, locs
    for item in str(district_input).split(","):
        item = item.strip()
        if not item:
            continue
        hit = _DISTRICT_LUT.get(item.lower())
        if not hit:
            logger.warning("[jobmarket] 未知地區：%s（已忽略）", item)
            continue
        if hit.get("param") == "AreaID":
            areas.append(hit["id"])
        else:
            locs.append(hit["id"])
    if areas or locs:
        logger.info(
            "[jobmarket] 地區過濾：AreaID=%s AreaLocationID=%s",
            ",".join(areas) or "-", ",".join(locs) or "-",
        )
    return areas, locs


def resolve_categories(category_input: Optional[str]) -> tuple[list[str], list[str]]:
    """把使用者輸入解析為 (JobFunctionID 清單, SubJobFunctionID 清單)。

    細類可直接送（無需搭配大類，與 Recruit 不同）。
    """
    fns: list[str] = []
    subfns: list[str] = []
    if not category_input:
        return fns, subfns
    for item in str(category_input).split(","):
        item = item.strip()
        if not item:
            continue
        hit = _CATEGORY_LUT.get(item.lower())
        if not hit:
            logger.warning("[jobmarket] 未知職能：%s（已忽略）", item)
            continue
        if hit.get("type") == "subFunction":
            logger.info("[jobmarket] 職能過濾：細類 %s（%s）", item, hit["id"])
            subfns.append(hit["id"])
        else:
            logger.info("[jobmarket] 職能過濾：大類 %s（%s）", item, hit["id"])
            fns.append(hit["id"])
    return fns, subfns


def resolve_industries(industry_input: Optional[str]) -> list[str]:
    if not industry_input:
        return []
    ids: list[str] = []
    for item in str(industry_input).split(","):
        item = item.strip()
        if not item:
            continue
        hit = _INDUSTRY_LUT.get(item.lower())
        if not hit:
            logger.warning("[jobmarket] 未知行業：%s（已忽略）", item)
            continue
        logger.info("[jobmarket] 行業過濾：%s（%s）", item, hit["id"])
        ids.append(hit["id"])
    return ids


class JobMarketScraper(BaseScraper):
    source = "jobmarket"
    use_browser = False      # 全程普通 requests：列表端點 + 批次 API + 詳情頁皆可直接 GET
    list_has_date = True     # 列表卡 p.post-date 已有刊登日（04 Sep 2026）
    list_sorted_desc = True  # 大致新→舊；頂部推廣區塊例外（該區塊偏舊，提早停翻仍安全）

    def __init__(self, headers: dict | None = None):
        super().__init__(headers)
        self.session = requests.Session()

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
        if sort:
            logger.warning(
                "[jobmarket] 不支援 --sort（站方 Order 參數實測無效；"
                "列表大致按刊登日新→舊，頂部推廣區塊除外），已忽略")

        params: dict[str, str] = {"Page": str(max(1, page))}
        if keyword:
            params["Searchtext"] = keyword
        areas, locs = _resolve_param(district)
        if areas:
            params["AreaID"] = ",".join(areas)
        if locs:
            params["AreaLocationID"] = ",".join(locs)
        fns, subfns = resolve_categories(category)
        if fns:
            params["JobFunctionID"] = ",".join(fns)
        if subfns:
            params["SubJobFunctionID"] = ",".join(subfns)
        inds = resolve_industries(industry)
        if inds:
            params["JobIndustryID"] = ",".join(inds)

        r = self._get(JOBLIST_URL, params=params)
        if r is None:
            return []
        cards = self._parse_cards(r.text)
        if not cards:
            return []
        self._enrich_batch(cards)
        return [self._build_record(c) for c in cards if c.get("id")]

    def _get(self, url: str, params: dict | None = None):
        """帶重試的 GET（經基類 _with_retry 呼叫時不再多包一層）。"""
        for attempt in range(1, 4):
            try:
                r = self.session.get(
                    url, params=params,
                    headers={**DEFAULT_HEADERS, **(self.headers or {})},
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code == 200:
                    return r
                logger.warning(
                    "[jobmarket] HTTP %s：%s（第 %d 次）", r.status_code, url, attempt)
            except Exception as e:  # noqa: BLE001
                logger.warning("[jobmarket] 請求失敗：%s（第 %d 次）", e, attempt)
            if attempt < 3:
                time.sleep(2 ** attempt)
        return None

    # ---------- 列表解析 ----------
    @staticmethod
    def _parse_cards(html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        cards: list[dict] = []
        for c in soup.select(CARD_SEL):
            a = c.select_one("a.saved-a")
            jid = a.get("save-id") if a else None
            if not jid:
                li = c.find_parent("li")
                jid = li.get("data-jobid") if li else None
            if not jid:
                continue
            h3 = c.select_one("h3")
            comp = c.select_one("p.company-name")
            comp_a = comp.find("a") if comp else None
            posted = c.select_one("p.post-date")
            cards.append({
                "id": str(jid).strip(),
                "title": h3.get_text(strip=True) if h3 else "",
                "company": (comp_a.get_text(strip=True) if comp_a
                            else (comp.get_text(strip=True) if comp else "")),
                "posted": posted.get_text(strip=True) if posted else "",
            })
        return cards

    # ---------- 批次補齊（站方自己的 GetJobDetail API） ----------
    def _enrich_batch(self, cards: list[dict]) -> None:
        ids = ",".join(c["id"] for c in cards)
        r = self._get(BATCH_API_URL + ids)
        if r is None:
            logger.warning("[jobmarket] 批次 API 失敗，地區/職缺類型將留空")
            return
        try:
            data = r.json()
        except Exception as e:  # noqa: BLE001
            logger.warning("[jobmarket] 批次 API 回應非 JSON：%s", e)
            return
        if data.get("Status") != 1 or not isinstance(data.get("Body"), list):
            return
        by_id = {str(b.get("JobID")): b for b in data["Body"]}
        for c in cards:
            b = by_id.get(c["id"])
            if not b:
                continue
            loc = b.get("JobLocation") or []
            c["location"] = " / ".join(str(x).strip() for x in loc if str(x).strip())
            jtype = b.get("JobType") or []
            c["job_type"] = ", ".join(str(x).strip() for x in jtype if str(x).strip())
            ind = b.get("JobIndustry") or []
            c["industry"] = ", ".join(str(x).strip() for x in ind if str(x).strip())
            qual = b.get("Qualification") or ""
            if isinstance(qual, list):
                qual = ", ".join(str(x).strip() for x in qual if str(x).strip())
            c["qualification"] = str(qual).strip()
            benefit = b.get("Benefit") or []
            c["benefit"] = "；".join(str(x).strip() for x in benefit if str(x).strip())
            summary = b.get("JobSummary")
            details = b.get("JobDetails") or []
            bits = []
            if summary:
                bits.append(str(summary).strip())
            bits.extend(str(x).strip() for x in details if str(x).strip())
            c["summary"] = "\n".join(b for b in bits if b)

    def _build_record(self, c: dict) -> JobRecord:
        jid = c["id"]
        posted = (c.get("posted") or "").strip()
        # p.post-date 文字為 "Post Date\n04 Sep 2026"
        m = re.search(r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})", posted)
        if m:
            posted = m.group(1)
        # requirements：學歷 + 福利 + 列表摘要（詳情層級無獨立欄位，合併保留）
        bits = []
        if c.get("qualification"):
            bits.append(f"學歷：{c['qualification']}")
        if c.get("benefit"):
            bits.append(f"福利：{c['benefit']}")
        if c.get("summary"):
            bits.append(c["summary"])
        now = datetime.now().isoformat(timespec="seconds")
        return JobRecord(
            job_id=f"jobmarket::{jid}",
            source=self.source,
            title=(c.get("title") or "").strip(),
            company=(c.get("company") or "").strip(),
            location=(c.get("location") or "").strip(),
            salary="",                       # 列表卡無薪資欄；薪資常在描述文字內
            job_type=(c.get("job_type") or "").strip(),
            industry=(c.get("industry") or "").strip(),
            description="",
            requirements="\n".join(bits),
            url=BASE + "/Job/CurrentJob?Jobid=" + jid,
            posted_date=posted,
            scraped_at=now,
        )

    # ---------- 詳情頁 ----------
    def get_detail(self, job_url: str) -> Optional[JobRecord]:
        r = self._get(job_url)
        if r is None:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        m = re.search(r"Jobid=(\d+)", job_url)
        jid = m.group(1) if m else ""
        title_el = soup.select_one(DETAIL_TITLE_SEL)
        desc_el = soup.select_one(DETAIL_DESC_SEL)
        date_el = soup.select_one(DETAIL_DATE_SEL)
        par_el = soup.select_one(DETAIL_INDUSTRY_SEL)

        posted = ""
        if date_el:
            m2 = re.search(r"(\d{1,2}-[A-Za-z]{3}-\d{4})", date_el.get_text(" ", strip=True))
            if m2:
                posted = m2.group(1)

        # .job-par 文字：Industry X Job Function Y Information Technology ...
        industry = ""
        if par_el:
            m3 = re.search(r"Industry\s+(.+?)\s+Job\s+Function", par_el.get_text(" ", strip=True))
            if m3:
                industry = m3.group(1).strip()

        benefit = ""
        ben_el = soup.select_one(DETAIL_BENEFIT_SEL)
        if ben_el:
            benefit = ben_el.get_text(" ", strip=True)

        now = datetime.now().isoformat(timespec="seconds")
        return JobRecord(
            job_id=f"jobmarket::{jid}",
            source=self.source,
            title=title_el.get_text(strip=True) if title_el else "",
            company="",                      # 列表層已抓公司；此處不重複
            location="",
            salary="",
            job_type="",
            industry=industry,
            description=desc_el.get_text("\n", strip=True) if desc_el else "",
            requirements=f"福利：{benefit}" if benefit else "",
            url=job_url,
            posted_date=posted,
            scraped_at=now,
        )

    # ---------- 日期解析 ----------
    def days_since_posted(self, job: JobRecord) -> int | None:
        s = (getattr(job, "posted_date", "") or "").strip()
        if not s:
            return None
        # 列表 "04 Sep 2026" / 詳情 "05-Sep-2026"
        for fmt in ("%d %b %Y", "%d-%b-%Y"):
            try:
                d = datetime.strptime(s, fmt).date()
            except ValueError:
                continue
            return max(0, (date.today() - d).days)
        return None

    # ---------- 收尾 ----------
    def close(self) -> None:
        if self.session is not None:
            try:
                self.session.close()
            except Exception:  # noqa: BLE001
                pass
            self.session = None
