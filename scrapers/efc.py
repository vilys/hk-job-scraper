# -*- coding: utf-8 -*-
"""eFinancialCareers（www.efinancialcareers.hk）爬蟲 — 擴充八站 Wave 2。

🌐 站點特性（2026-09-05 逆向，見 README「🧭 技術筆記（eFinancialCareers 逆向要點）」）：
  - 金融 / 銀行 / 投資垂直專業站。香港職缺 ~2,900 筆（空關鍵字全站 71,605 筆）。
  - **純 JSON API，全程普通 requests，不需要瀏覽器**：
      https://job-search-ui.efinancialcareers.com/v3/efc/jobs/search
    （robots.txt 的 Disallow: /v1 暗示的即是這一族版本化端點；v3 為現行搜尋 API）
  - 搜尋參數：q（關鍵字，可空）、location（自由文字地名，40km 半徑模糊匹配）、
    page / pageSize（實測 100 也吃）、sortBy（**僅 relevance 有效**，其他值被忽略）、
    countryCode2=HK（站方以香港站身份發出）。
  - API 回應的 data[] **每筆已含 summary / description**，詳情頁（ld+json JobPosting）
    補 baseSalary / skills / validThrough 等更完整欄位。
  - 地區過濾只支援大區級：Hong Kong / Hong Kong Island / Kowloon（細分區回 0 筆）。
  - 刊登日 postedDate 為 ISO 時間戳 → list_has_date=True，--days 瞬時過濾。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from base_scraper import BaseScraper
from job_model import JobRecord

logger = logging.getLogger(__name__)

_API = "https://job-search-ui.efinancialcareers.com/v3/efc/jobs/search"
_SITE = "https://www.efinancialcareers.hk"

# 站方 Angular 前端送出的 facets 清單（原樣保留以求穩）
_FACETS = (
    "seniority|fullNormalizedJobTitle|locationPath|salaryRange|sectors|"
    "employmentType|experienceLevel|workArrangementType|salaryCurrency|"
    "minSalary|maxSalary|positionType|postedDate|clientBrandNameFilter"
)

_PAGE_SIZE = 50  # 實測 100 也接受，取 50 兼顧單頁大小與請求次數

# 2026-11-11 實測：不給 location 參數時站方回「全球」職缺
# （`analyst` 50 筆混入 London ×2 / New York / Gurugram / Dallas）。
# 這是香港求職站，故未指定 --district 時一律限縮到 Hong Kong。
_DEFAULT_LOCATION = "Hong Kong"

# ---- 地區字典 ----
_GEO_FILE = Path(__file__).with_name("efc_geo.json")
_GEO: dict[str, str] = {}


def _load_geo() -> dict[str, str]:
    """別名/名稱 → location 參數值。"""
    global _GEO
    if _GEO:
        return _GEO
    try:
        raw = json.loads(_GEO_FILE.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("[efc] 地區字典載入失敗：%s", e)
        _GEO = {"hong kong": "Hong Kong"}
        return _GEO
    mapping: dict[str, str] = {}
    for it in raw.get("locations", []):
        for key in (it.get("name"), it.get("id"), it.get("name_zh"), *(it.get("aliases") or [])):
            if key:
                mapping[key.strip().lower()] = it["id"]
    _GEO = mapping
    return _GEO


class EfcScraper(BaseScraper):
    source = "efc"
    use_browser = False      # JSON API，普通 requests 即可
    list_has_date = True     # API 每筆含 postedDate（ISO 時間戳）

    def __init__(self, headers: dict | None = None):
        super().__init__(headers)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": self.headers["User-Agent"],
                "Accept": "application/json",
                "Accept-Language": "en-HK,en;q=0.9",
                "Referer": _SITE + "/",
            }
        )

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
            loc = _load_geo().get(district.strip().lower())
            if not loc:
                logger.warning(
                    "[efc] --district %r 不在 efc_geo.json 內（站方地區索引僅支援"
                    " Hong Kong / Hong Kong Island / Kowloon 大區），"
                    "已回退預設 location=Hong Kong", district,
                )
                loc = _DEFAULT_LOCATION
        else:
            loc = _DEFAULT_LOCATION
            logger.info(
                "[efc] 未指定 --district，已預設 location=%s（避免回全球職缺）；"
                "可改用 --district \"Hong Kong Island\" / \"Kowloon\"", loc,
            )
        if category:
            logger.warning("[efc] 不支援 --category（該站無職能 facet 篩選參數），已忽略")
        if industry:
            logger.warning("[efc] 不支援 --industry（站方 sectors facet 無對應過濾參數），已忽略")
        if sort and sort != "relevance":
            logger.warning(
                "[efc] 不支援 --sort %r（站方僅 relevance 一種排序，其他值一律被忽略），已忽略",
                sort,
            )

        params = {
            "q": keyword or "",
            "countryCode2": "HK",
            "radius": 40,
            "radiusUnit": "km",
            "page": page,
            "pageSize": _PAGE_SIZE,
            "facets": _FACETS,
            "currencyCode": "HKD",
            "culture": "en",
            "recommendations": "true",
            "fj": "false",
            "includeRemote": "false",
            "includeUnspecifiedSalary": "true",
        }
        if loc:
            params["location"] = loc

        resp = self._session.get(_API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data") or []
        meta = data.get("meta") or {}
        logger.info(
            "[efc] 第 %d 頁回 %d 筆（total=%s）", page, len(items), meta.get("totalResults", "?")
        )
        return [self._to_record(it) for it in items if it]

    def _to_record(self, it: dict) -> JobRecord:
        job_id = str(it.get("jobId") or it.get("id") or "")
        rel = it.get("detailsPageUrl") or ""
        url = rel if rel.startswith("http") else _SITE + rel
        jloc = it.get("jobLocation") or {}
        location = jloc.get("displayName") or "、".join(
            x for x in (jloc.get("city"), jloc.get("country")) if x and x != "NA"
        )
        sectors = it.get("sectors") or []
        industry = " / ".join(s.replace("_", " ").title() for s in sectors)
        salary = it.get("salary") or ""
        if not salary and (it.get("minSalary") or 0) and (it.get("maxSalary") or 0):
            salary = f"{it['minSalary']:.0f} - {it['maxSalary']:.0f} HKD"
        posted = it.get("postedDate") or ""
        job_type = it.get("employmentType") or ""
        if it.get("positionType"):
            job_type = f"{job_type} / {it['positionType']}" if job_type else it["positionType"]
        return JobRecord(
            job_id=JobRecord.make_id(self.source, job_id),
            source=self.source,
            title=(it.get("title") or "").strip(),
            company=(it.get("companyName") or it.get("clientBrandName") or "").strip(),
            location=location,
            salary=salary,
            job_type=job_type,
            industry=industry,
            description="",  # 留給 --detail 補全（API 的 summary 過短且含 HTML）
            requirements="",
            url=url,
            posted_date=posted[:10] if posted else "",
            raw={"summary": it.get("summary") or ""},
        )

    # ---------- 詳情 ----------
    def get_detail(self, job_url: str) -> JobRecord | None:
        resp = self._session.get(job_url, timeout=30)
        resp.raise_for_status()
        sp = BeautifulSoup(resp.text, "html.parser")
        for tag in sp.find_all("script", type="application/ld+json"):
            try:
                d = json.loads(tag.string or "")
            except Exception:  # noqa: BLE001
                continue
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                return self._record_from_ldjson(d, job_url)
        logger.warning("[efc] 詳情頁無 JobPosting ld+json：%s", job_url)
        return None

    def _record_from_ldjson(self, d: dict, job_url: str) -> JobRecord:
        # description 是 HTML 片段 → 純文字化
        desc_html = d.get("description") or ""
        description = BeautifulSoup(desc_html, "html.parser").get_text(" ", strip=True)
        # 薪資
        salary = ""
        bs = d.get("baseSalary")
        if isinstance(bs, dict):
            val = bs.get("value") or {}
            lo, hi, cur = val.get("minValue"), val.get("maxValue"), val.get("currency", "")
            if lo and hi:
                salary = f"{lo:,.0f} - {hi:,.0f} {cur}".replace(", ", ",")
            elif lo or hi:
                salary = f"{lo or hi:,.0f} {cur}"
        skills = d.get("skills") or []
        requirements = "、".join(skills) if isinstance(skills, list) else str(skills or "")
        # 與列表一致的 job_id：以詳情網址的 .idNNNNN（= API jobId）為準；
        # ld+json 的 identifier 是另一套 API hash id（如 oPTJ3NGIwowU），不用
        m = re.search(r"\.id(\d+)", job_url)
        if m:
            raw_id = m.group(1)
        else:
            ident = d.get("identifier")
            raw_id = ""
            if isinstance(ident, dict):
                raw_id = str(ident.get("value") or ident.get("name") or "")
            elif ident:
                raw_id = str(ident)
            if not raw_id:
                raw_id = job_url
        posted = d.get("datePosted") or ""
        return JobRecord(
            job_id=JobRecord.make_id(self.source, raw_id),
            source=self.source,
            title=(d.get("title") or "").strip(),
            company=((d.get("hiringOrganization") or {}).get("name") or "").strip(),
            location=self._fmt_location(d.get("jobLocation")),
            salary=salary,
            job_type=d.get("employmentType") or "",
            industry="",
            description=description,
            requirements=requirements,
            url=job_url,
            posted_date=posted[:10] if posted else "",
        )

    @staticmethod
    def _fmt_location(jloc) -> str:
        if isinstance(jloc, list):
            jloc = jloc[0] if jloc else {}
        if not isinstance(jloc, dict):
            return ""
        addr = jloc.get("address") or {}
        parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
        # 相鄰重複段去除（如 Hong Kong, Hong Kong）
        out: list[str] = []
        for p in parts:
            if p and p != "NA" and (not out or out[-1] != p):
                out.append(p)
        return ", ".join(out)

    # ---------- 日期 ----------
    def days_since_posted(self, job: JobRecord) -> int | None:
        """postedDate 是 ISO 時間戳（列表 API）；詳情 ld+json 亦是 ISO。"""
        raw = job.posted_date
        if not raw:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw.replace("+00:00", "+0000"), fmt)
                if fmt == "%Y-%m-%d":
                    dt = dt.replace(tzinfo=timezone.utc)
                return max(0, (datetime.now(timezone.utc) - dt).days)
            except ValueError:
                continue
        return None

    def close(self) -> None:
        self._session.close()
