"""
OfferToday (www.offertoday.com) 爬蟲 — 擴充八站 Wave 3′ 復活賽

前身 HKGoodJobs（舊域全面 403，已止損）於 2026 年更名為 OfferToday 重新上線。

技術特點
--------
SPA（Vue）＋ BOSS直聘技術底（頁面載 `static.zhipin.com` APM SDK），
但 **未繼承其全站安全驗證**；robots 極寬鬆。

🚀 **全程普通 requests 即可（use_browser=False）**
R8/R9 實測：冷請求（無 cookie、無瀏覽器指紋）直打列表 API 回 `code=0`，
且關鍵字／地區／職能／行業／翻頁**全數生效**。與 JobMarket、eFC 同級輕量。

核心端點
--------
  POST /wapi/geek/recommend/search/list
      payload: keyword / page / pageSize(=10 上限) / salaryType / publishTime /
               employmentTypes / experiences / educationLevels / benefits /
               workPermits / rcdType(=7) / jobFunctionCodes / industries /
               subDistrictCodes / searchSource
      回應: data.resultList  （⚠️ data.total 是推薦池規模，不可信）

🎴 cardType 過濾（**模組必守**，否則會拿到假結果）
--------
  | cardType | suppleCard | 意義             | 處理 |
  |----------|-----------|------------------|------|
  | 0        | false     | 真命中           | ✅ 收錄 |
  | 0        | true      | 推薦遞補（湊數） | ❌ 丟棄 |
  | 1        | –         | 橫幅廣告（無 jobId）| ❌ 丟棄 |
  | 2        | –         | 空結果插圖       | ❌ 丟棄 |
  | 3        | –         | 「No more results」分隔線 | ❌ 無結果訊號 |

編碼規則（⚠️ 與字典 JSON 裡的複合鍵不同，送 API 前必須拆前綴）
--------
- 地區 `subDistrictCodes`：**純 code**
  - 區級　→ `HK101304`（元朗全區）
  - 子區級 → `HK101304104`（天水圍）
  - 字典裡的 `s<區碼>c<子區碼>` 是 `getHomePopWords` 的 **SEO slug，送了會 total=0**。
- 職能 `jobFunctionCodes`：POSITION **level-2 code**
  - `118000`＝所有資訊科技、`118001`＝架構師、`118006`＝開發者
  - level-1 與「所有」level-2 剛好同碼，所以大類碼可直接送。
- 行業 `industries`：INDUSTRY **level-2 code**
  - `1001`＝會計/審計/稅務、`1005`＝銀行、`1018`＝金融服務、`1027`＝保險
  - ⚠️ **level-1（`101` 財務/金融）是群組標題，不是有效值**（送它 total=0）
    → 要篩整個大類，**必須展開成其全部細類**。

🕐 刊登日 `jobPostTime`（三種格式）
--------
  | 格式 | 範例 | 可否算天數 |
  |------|------|-----------|
  | `... on MM-DD` | `Updated on 09-03`、`Posted on 08-28` | ✅（假設當年，跨年 -1 年）|
  | `... within 3 months` | `Updated within 3 months` | ❌ 太舊 |
  | `... N months ago` | `Posted 3 months ago` | ❌ 太舊 |

  → `publishTime` 參數是**軟篩選**（只讓推薦池偏向近期，仍會夾帶舊職位），
    故 `--days` 採**雙保險**：送 `publishTime` 參數 + 客戶端再篩（淘汰後兩種格式）。

字典（本站專屬，與其他站互不混用）
--------
- `offertoday_areas.json`：18 區 / 129 子區
- `offertoday_categories.json`：31 大類 / 431 細類
- `offertoday_industries.json`：15 大類 / 53 細類 + 6 組枚舉
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests

from base_scraper import BaseScraper
from config import DEFAULT_HEADERS, REQUEST_TIMEOUT
from job_model import JobRecord

logger = logging.getLogger(__name__)

BASE = "https://www.offertoday.com"
API_LIST = BASE + "/wapi/geek/recommend/search/list"
API_DETAIL = BASE + "/wapi/geek/recommend/jobDetail"

PAGE_SIZE = 10          # 站方上限，超過會被無視
MAX_PAGE = 50           # 自我保護：每站最多翻 50 頁（每頁 1 支請求）

_HERE = Path(__file__).resolve().parent

# `--days` → `publishTime` 參數（0 今天 / 1 三天 / 2 七天 / 3 十四天）
_DAYS_TO_PUBLISH_TIME = ((1, 0), (3, 1), (7, 2), (14, 3))

# 「on MM-DD」→ 可算天數；其餘一律視為過舊
_RE_ON_MMDD = re.compile(r"(?:Updated|Posted)\s+on\s+(\d{1,2})-(\d{1,2})", re.I)


def _load_dict(name: str) -> dict:
    try:
        with open(_HERE / name, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning("[offertoday] 讀取字典 %s 失敗：%s", name, e)
        return {}


_AREAS = _load_dict("offertoday_areas.json").get("districts") or []
_CATEGORIES = _load_dict("offertoday_categories.json").get("categories") or []
_INDUSTRIES = _load_dict("offertoday_industries.json").get("industries") or []


def _k(s) -> str:
    """查表用的正規化鍵。"""
    return str(s or "").strip().lower()


def _leaf_code(compound_id) -> str:
    """把字典裡的複合鍵拆成 API 要的純 code。

    'sHK101101cHK101101104' → 'HK101101104'
    '101000c101001'         → '101001'
    '101c1001'              → '1001'
    'HK101304'              → 'HK101304'（無 'c' 時原樣回傳）
    """
    s = str(compound_id or "")
    return s.split("c", 1)[1] if "c" in s else s


def _add(lut: dict, keys, value) -> None:
    for k in keys:
        k = _k(k)
        if k:
            lut.setdefault(k, value)          # 先出現者優先（區級不被子區覆蓋）
            if k.startswith("all "):          # 'All Central and Western' → 也收 'central and western'
                lut.setdefault(k[4:], value)


def _build_area_lut() -> dict:
    """地區 → ('district'|'sub', code)；同時收錄 code 本身。"""
    lut: dict[str, tuple[str, str]] = {}
    for d in _AREAS:
        code = str(d.get("id") or "")
        _add(lut, [d.get("name"), d.get("name_en"), code], ("district", code))
        for ch in d.get("children") or []:
            sub = _leaf_code(ch.get("id"))
            _add(lut, [ch.get("name"), ch.get("name_en"), sub,
                       f"{d.get('name')}{ch.get('name')}"], ("sub", sub))
    return lut


def _build_category_lut() -> dict:
    """職能 → level-2 code（大類碼與「所有」level-2 同碼，可直接送）。"""
    lut: dict[str, str] = {}
    for c in _CATEGORIES:
        code = str(c.get("id") or "")
        _add(lut, [c.get("name"), c.get("name_en"), code], code)
        for ch in c.get("children") or []:
            sub = _leaf_code(ch.get("id"))
            _add(lut, [ch.get("name"), ch.get("name_en"), sub], sub)
    return lut


def _build_industry_lut() -> dict:
    """行業 → level-2 code 清單（大類展開成全部細類，因 level-1 不是有效值）。"""
    lut: dict[str, list[str]] = {}
    for ind in _INDUSTRIES:
        subs = [_leaf_code(ch.get("id")) for ch in (ind.get("children") or [])]
        _add(lut, [ind.get("name"), ind.get("name_en"), str(ind.get("id") or "")],
             subs or [str(ind.get("id") or "")])
        for ch in ind.get("children") or []:
            sub = _leaf_code(ch.get("id"))
            _add(lut, [ch.get("name"), ch.get("name_en"), sub], [sub])
    return lut


_AREA_LUT = _build_area_lut()
_CATEGORY_LUT = _build_category_lut()
_INDUSTRY_LUT = _build_industry_lut()


def resolve_districts(district_input: Optional[str]) -> list[str]:
    """把使用者輸入解析為 `subDistrictCodes`（純 code 清單）。"""
    codes: list[str] = []
    if not district_input:
        return codes
    for item in str(district_input).split(","):
        item = item.strip()
        if not item:
            continue
        hit = _AREA_LUT.get(_k(item))
        if not hit:
            logger.warning("[offertoday] 未知地區：%s（已忽略）", item)
            continue
        codes.append(hit[1])
    if codes:
        logger.info("[offertoday] 地區過濾：subDistrictCodes=%s", ",".join(codes))
    return codes


def resolve_categories(category_input: Optional[str]) -> list[str]:
    codes: list[str] = []
    if not category_input:
        return codes
    for item in str(category_input).split(","):
        item = item.strip()
        if not item:
            continue
        hit = _CATEGORY_LUT.get(_k(item))
        if not hit:
            logger.warning("[offertoday] 未知職能：%s（已忽略）", item)
            continue
        codes.append(hit)
    if codes:
        logger.info("[offertoday] 職能過濾：jobFunctionCodes=%s", ",".join(codes))
    return codes


def resolve_industries(industry_input: Optional[str]) -> list[str]:
    codes: list[str] = []
    if not industry_input:
        return codes
    for item in str(industry_input).split(","):
        item = item.strip()
        if not item:
            continue
        hit = _INDUSTRY_LUT.get(_k(item))
        if not hit:
            logger.warning("[offertoday] 未知行業：%s（已忽略）", item)
            continue
        for c in hit:
            if c and c not in codes:
                codes.append(c)
    if codes:
        logger.info("[offertoday] 行業過濾：industries=%s", ",".join(codes))
    return codes


def job_url(job_id: str) -> str:
    """職位網址：/hk/job/<加密 id>（'=' 保留原樣，'/' '+' 需編碼）。"""
    return f"{BASE}/hk/job/{quote(str(job_id), safe='=')}"


class OfferTodayScraper(BaseScraper):
    source = "offertoday"
    use_browser = False      # 🚀 冷 requests 直打 API 即可（R8/R9 實測）
    list_has_date = True     # 卡片有 jobPostTime；只有 "on MM-DD" 能算天數

    def __init__(self, headers: dict | None = None):
        super().__init__(headers)
        self.session = requests.Session()
        self._days: Optional[int] = None   # 由 scrape_all 注入，供 publishTime 使用

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
                "[offertoday] 不支援 --sort（站方 API 無排序參數），已忽略")

        page = max(1, int(page or 1))
        if page > MAX_PAGE:
            logger.warning("[offertoday] 已達自我保護上限 %d 頁，停止翻頁。", MAX_PAGE)
            return []

        payload: dict = {
            "keyword": keyword or "",
            "page": page,
            "pageSize": PAGE_SIZE,
            "salaryType": 0,
            "publishTime": "",
            "employmentTypes": [],
            "experiences": [],
            "educationLevels": [],
            "benefits": [],
            "workPermits": [],
            "rcdType": 7,
            "jobFunctionCodes": [],
            "industries": [],
            "subDistrictCodes": [],
            "searchSource": None,
        }
        if district:
            payload["subDistrictCodes"] = resolve_districts(district)
        if category:
            payload["jobFunctionCodes"] = resolve_categories(category)
        if industry:
            payload["industries"] = resolve_industries(industry)
        # publishTime 是軟篩選：送了仍會夾帶舊職位，故 scrape_all 還會再篩一次
        if self._days is not None:
            for limit, code in _DAYS_TO_PUBLISH_TIME:
                if self._days <= limit:
                    payload["publishTime"] = code
                    break
            else:
                logger.warning(
                    "[offertoday] --days %d 超出站方最長區間（14 天），"
                    "僅以客戶端篩選處理。", self._days)

        data = self._post(API_LIST, payload)
        if data is None:
            return []
        return self._parse_list(data)

    # ---------- HTTP ----------
    def _post(self, url: str, payload: dict) -> Optional[dict]:
        """POST JSON，回傳 data 內容；失敗回傳 None。"""
        headers = {**DEFAULT_HEADERS, **(self.headers or {})}
        headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": BASE,
            "Referer": BASE + "/hk/search",
        })
        for attempt in range(1, 4):
            try:
                r = self.session.post(url, json=payload, headers=headers,
                                      timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    logger.warning(
                        "[offertoday] HTTP %s（第 %d 次）— 可能觸發防護，放慢。",
                        r.status_code, attempt)
                    time.sleep(2 ** attempt)
                    continue
                body = r.json()
                if body.get("code") != 0:
                    logger.warning("[offertoday] API code=%s msg=%s",
                                   body.get("code"), body.get("msg"))
                    return None
                return body.get("data") or {}
            except Exception as e:  # noqa: BLE001
                logger.warning("[offertoday] 請求失敗：%s（第 %d 次）", e, attempt)
                if attempt < 3:
                    time.sleep(2 ** attempt)
        return None

    # ---------- 列表解析 ----------
    def _parse_list(self, data: dict) -> list[JobRecord]:
        raw_list = data.get("resultList") or []
        real = [j for j in raw_list
                if j.get("cardType") == 0 and not j.get("suppleCard")]
        dropped = len(raw_list) - len(real)
        if dropped:
            logger.info("[offertoday] 已丟棄 %d 張非真命中卡片"
                        "（遞補推薦 / 廣告 / 空結果卡）。", dropped)
        if not real:
            # cardType 3 = 「No more results」分隔線，或整頁皆遞補 → 視為無結果
            logger.info("[offertoday] 本頁無真命中，停止翻頁。")
            return []
        return [rec for rec in (self._build_record(j) for j in real) if rec]

    def _build_record(self, j: dict) -> Optional[JobRecord]:
        jid = j.get("jobId")
        if not jid:
            return None
        jid = str(jid)

        bits: list[str] = []
        if j.get("experience"):
            bits.append(f"經驗：{j['experience']}")
        if j.get("educationDesc"):
            bits.append(f"學歷：{j['educationDesc']}")
        skills = [str(s).strip() for s in (j.get("skills") or []) if str(s).strip()]
        if skills:
            bits.append(f"技能：{'、'.join(skills)}")
        bens = [str(b).strip() for b in (j.get("benefits") or []) if str(b).strip()]
        if bens:
            bits.append(f"福利：{'、'.join(bens)}")
        kws = [str(k).strip() for k in (j.get("keywords") or []) if str(k).strip()]
        if kws:
            bits.append("；".join(kws))
        if j.get("workPermitDesc"):
            bits.append(f"工作簽證：{j['workPermitDesc']}")

        return JobRecord(
            job_id=f"offertoday::{jid}",
            source=self.source,
            title=str(j.get("jobName") or "").strip(),
            company=str(j.get("companyName") or j.get("brandName") or "").strip(),
            location=str(j.get("locationDesc") or "").strip(),
            salary=str(j.get("salaryDesc") or "").strip(),
            job_type=str(j.get("jobTypeDesc") or "").strip(),
            industry="",                       # 列表卡無行業欄（--detail 才有機會補）
            description="",
            requirements="\n".join(bits),
            url=job_url(jid),
            posted_date=str(j.get("jobPostTime") or "").strip(),
            scraped_at=datetime.now().isoformat(timespec="seconds"),
            raw={"encryptExpectId": j.get("encryptExpectId") or ""},
        )

    # ---------- 詳情 ----------
    def get_detail(self, job_url_: str) -> Optional[JobRecord]:
        """抓單筆詳情（描述文字）。

        ⚠️ 端點形狀為依 R5 錄得的流量推導，**待實測微調**；
        解析失敗時僅 warning 並回傳 None，不中斷整體流程。
        """
        m = re.search(r"/hk/job/(.+?)(?:\?|$)", job_url_ or "")
        jid = m.group(1) if m else ""
        if not jid:
            return None
        try:
            r = self.session.get(
                API_DETAIL,
                params={"id": jid, "sessionId": ""},
                headers={**DEFAULT_HEADERS, **(self.headers or {})},
                timeout=REQUEST_TIMEOUT,
            )
            if r.status_code != 200:
                logger.warning("[offertoday] 詳情 HTTP %s：%s", r.status_code, job_url_)
                return None
            body = r.json()
        except Exception as e:  # noqa: BLE001
            logger.warning("[offertoday] 詳情請求失敗 %s：%s", job_url_, e)
            return None
        if body.get("code") != 0:
            logger.warning("[offertoday] 詳情 code=%s", body.get("code"))
            return None
        d = (body.get("data") or {}).get("jobInfo") or body.get("data") or {}
        desc = str(d.get("jobDesc") or d.get("description") or "").strip()
        if not desc:
            logger.warning("[offertoday] 詳情無描述欄位（端點形狀可能已變）：%s",
                           list(d)[:10])
            return None
        now = datetime.now().isoformat(timespec="seconds")
        return JobRecord(
            job_id=f"offertoday::{jid}",
            source=self.source,
            title=str(d.get("jobName") or "").strip(),
            company="",
            location="",
            salary="",
            job_type="",
            industry="",
            description=desc,
            requirements=str(d.get("requirement") or "").strip(),
            url=job_url_,
            posted_date="",
            scraped_at=now,
        )

    # ---------- --days 雙保險 ----------
    def scrape_all(self, *args, days: int | None = None, **kwargs):
        self._days = days          # 讓 search() 能一併送 publishTime 參數
        try:
            return super().scrape_all(*args, days=days, **kwargs)
        finally:
            self._days = None

    def days_since_posted(self, job: JobRecord) -> int | None:
        """只有 `... on MM-DD` 可算天數；`within 3 months` / `N months ago` 視為過舊。"""
        s = (getattr(job, "posted_date", "") or "").strip()
        if not s:
            return None
        m = _RE_ON_MMDD.search(s)
        if not m:
            return None
        try:
            month, day = int(m.group(1)), int(m.group(2))
            today = date.today()
            try:
                d = date(today.year, month, day)
            except ValueError:
                return None
            if d > today:                 # 跨年：例如 12 月抓到 01-05
                d = date(today.year - 1, month, day)
            return max(0, (today - d).days)
        except Exception:  # noqa: BLE001
            return None

    # ---------- 收尾 ----------
    def close(self) -> None:
        if self.session is not None:
            try:
                self.session.close()
            except Exception:  # noqa: BLE001
                pass
            self.session = None
