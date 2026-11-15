"""JobsDB (hk.jobsdb.com) 爬蟲。

逆向要點（詳見 README「🧭 技術筆記（JobsDB）」）：
- 反爬：Cloudflare。用 Playwright 真瀏覽器共享 cf_clearance，不硬撞。
- 搜尋機制：SSR 頁面  /jobs?keywords=K&page=N ，職位卡片以
  data-automation='normalJob' 渲染（非 GraphQL 列表呼叫，故單頁一次 GET 即可）。
- 翻頁：URL 加  ?page=N （首頁 /jobs?keywords=K 會 301 轉為 /K-jobs，page 參數保留）。
- 詳情頁：/job/<id> ，同樣靠 data-automation 屬性解析。
- 地區 / 分類（職能）：JobsDB 使用自有 slug 體系（與 Moovup / 勞工處 完全獨立）。
  職能瀏覽網址為 /jobs-in-<classification-slug>（如 information-communication-technology），
  地區以 /in-<district-slug> 串接（如 /jobs-in-<職能>/in-<地區>）；字典見
  scrapers/jobsdb_classifications.json / jobsdb_districts.json。--district / --category 已實作；
  --industry 在 JobsDB 無此維度（職能已涵蓋），忽略並提示。
- 排序（--sort）：JobsDB 網站 UI 僅提供兩種排序——「相關性（Relevance，預設，不帶參數）」
  與「刊登日期（Date）」。Date 由網址查詢參數 sortmode 控制：?sortmode=ListedDate = 新→舊
  （已實測：1h→2h→3h 遞增）。故 --sort 在本站只支援 post_dt_desc（對應 ListedDate）；
  其餘選項（post_dt_asc / salary_* / yr_exp_* / edu_lvl_*）為 gov_hk 專有，JobsDB 無對應，
  傳入會警告並回退網站預設（Relevance）。sortmode 可與 keywords/page/地區瀏覽網址共存（站方
  會將 /jobs?keywords=K&page=N&sortmode=ListedDate 301 正規化為 /K-jobs?...，Playwright 自動跟隨）。
- 刊登日為「相對時間」字串（7d ago / 13h ago / Just now），用 days_since_posted() 解析。
- 標題會併入「New」徽章（如 `...EngineerNew`），以 strip_new_badge() 剝除。
- GraphQL 搜尋通道（2026-11-15，見下方「GraphQL 搜尋通道」區塊）：
  POST /graphql 的 jobSearchV7 可取得 SSR 卡片沒有的結構化薪資與精確刊登日。
  search() 在「只用了已驗證維度」時優先走此通道，失敗或指定未驗證維度時
  自動熔斷並退回既有 Playwright SSR 流程；JOBSDB_GRAPHQL=0 可一鍵停用。
  零憑證（無 Cookie / Authorization），13 欄契約與 schemaVersion=2 皆不變。
  ⚠️ 本通道以離線快照開發，尚未對站方發過真實請求；見 README 技術筆記。
- GraphQL 詳情通道（2026-11-15，見下方「jobDetails 詳情通道」區塊）：
  get_detail() 優先打 jobDetails(id) 取完整 JD（content 為 HTML，轉純文字），
  常見路徑（--keyword/--days/--pages + --detail）因此不必啟動 Playwright。
  失敗熔斷本輪並退回既有 Playwright 詳情流程；JOBSDB_GRAPHQL=0 同步停用。
  刻意不選 products.questionnaire（申請問卷題目），維持「只抓公開廣告」邊界。
- GraphQL 薪金下限（2026-11-15）：--salary-min 下推成 filter.salaryMin:"<N>m"
  （m=monthly，離線 payload 有實證）；退回 SSR 時 URL 改用
  salaryrange=<N>-&salarytype=monthly。兩個通道語意一致，都是「月薪下限」。
  其他來源沒有站方端參數，由 base_scraper 的客戶端兜底統一篩選。
- GraphQL 轉接（2026-11-15 離線 spike）：record_from_graphql() 把 jobSearchV7
  單筆轉成 13 欄 JobRecord，純函式、零請求。
  來歷旗標（hideSalary）存 raw["graphql"] 供追溯；對應薪資數值仍填主表 salary，
  使用範圍與合規提醒見 README「使用範圍」。
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover — 允許「只裝 requests」的極簡安裝
    sync_playwright = None

from config import DEFAULT_HEADERS, REQUEST_TIMEOUT
from job_model import JobRecord
from base_scraper import BaseScraper

# 站方把「New」徽章直接併入標題文字（無子元素、無偽元素，實測 2026-10-31）。
# 只剝緊貼前一字元的尾綴，避免誤傷「Brand New」這類正常標題。
_NEW_BADGE_RE = re.compile(r"(?<=\S)New$")


def strip_new_badge(title: str) -> str:
    return _NEW_BADGE_RE.sub("", (title or "").strip()).strip()

logger = logging.getLogger(__name__)

BASE = "https://hk.jobsdb.com"
LIST_URL = BASE + "/jobs"

# ---- GraphQL 搜尋回應轉接（2026-11-15 離線 spike，零請求） ----
# 站方 SSR 頁把 Apollo cache 放在 window.SEEK_APOLLO_DATA，其中 jobSearchV7
# 的回應與 /graphql 端點同形。以下純函式只做「單筆 job → JobRecord 13 欄」
# 的離線轉接：不發請求、不啟動瀏覽器、不改既有 search()/get_detail() 流程。
#
# 離線快照實證（2026-11-14）：
#   salary {min,max,period,currency} 是顯示用值（已除以 100）；
#   cjs.salary.hideSalary=true 代表招聘頁不顯示，但搜尋索引仍保留薪資區間；
#   listedAt.dateTimeUtc 是 UTC ISO；categories 為 [子類, 大類]。
# 取捨：posted_date 仍輸出相對時間字串，與 days_since_posted() 及
#   aggregate.parse_date() 相容；精確 UTC 存 raw["graphql"]["listed_at_utc"]。
#   若日後改輸出精確 ISO，須先擴充 days_since_posted()，否則 --days 會濾光。

_GRAPHQL_PERIOD_LABEL = {
    "monthly": "per month",
    "hourly": "per hour",
    "annual": "per year",
}


def _gql_text(value) -> str:
    """安全取 GraphQL 本地化文字（displayName.text / label.text / name）。"""
    if isinstance(value, dict):
        for key in ("text", "name", "label", "displayName"):
            v = value.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
            if isinstance(v, dict):
                got = _gql_text(v)
                if got:
                    return got
    return value.strip() if isinstance(value, str) else ""


def _gql_salary_text(salary) -> tuple[str, dict]:
    """salary {min,max,period,currency} 轉成站方卡片同形字串 + 中繼資訊。

    未知週期回空字串（不假造單位）；min == max 只給單點數字。
    中繼資訊只進 raw，不改 13 欄主表。
    """
    if not isinstance(salary, dict):
        return "", {}
    period = str(salary.get("period") or "").strip().lower()
    info = {
        "salary_period": period,
        "salary_currency": str(salary.get("currency") or ""),
    }
    label = _GRAPHQL_PERIOD_LABEL.get(period)
    if not label:
        return "", info
    try:
        low = int(float(salary.get("min") or 0))
        high = int(float(salary.get("max") or 0))
    except (TypeError, ValueError):
        return "", info
    if low <= 0:
        return "", info
    if high <= 0 or high == low:
        return f"${low:,} {label}", info
    if high < low:
        low, high = high, low
    return f"${low:,} – ${high:,} {label}", info


def _gql_relative_date(utc_text, now: datetime) -> str:
    """UTC ISO 轉成站方卡片同形相對時間（Just now / Nm ago / Nh ago / Nd ago）。"""
    if not isinstance(utc_text, str) or not utc_text.strip():
        return ""
    try:
        dt = datetime.fromisoformat(utc_text.strip().replace("Z", "+00:00"))
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ref = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    delta = (ref.astimezone(timezone.utc) - dt).total_seconds()
    if delta < 60:
        return "Just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    return f"{int(delta // 86400)}d ago"


def record_from_graphql(job: dict, *, now: datetime | None = None) -> JobRecord:
    """jobSearchV7 單筆轉成 JobRecord（純函式、零請求）。

    缺欄位／型別異常一律安全退化，單筆壞資料不拖垮整批。
    hideSalary 旗標存 raw["graphql"] 供追溯、不進 13 欄主表；但薪資數值
    仍填入主表 salary（含招聘頁刻意不顯示的值），使用範圍見 README。
    """
    if not isinstance(job, dict):
        job = {}
    reference = now or datetime.now(timezone.utc)
    jid = str(job.get("id") or "").strip()

    advertiser = job.get("advertiser") if isinstance(job.get("advertiser"), dict) else {}
    organisation = job.get("organisation") if isinstance(job.get("organisation"), dict) else {}
    company = _gql_text(advertiser) or _gql_text(organisation)

    cjs = job.get("cjs") if isinstance(job.get("cjs"), dict) else {}
    cjs_salary = cjs.get("salary") if isinstance(cjs.get("salary"), dict) else {}
    work_types = cjs.get("workTypes")
    job_type = ""
    if isinstance(work_types, list):
        job_type = ", ".join(t for t in (_gql_text(w) for w in work_types) if t)
    role_titles = cjs.get("roleTitles")
    roles = [str(r.get("shortId") or "") for r in role_titles
             if isinstance(r, dict) and r.get("shortId")] if isinstance(role_titles, list) else []

    cats = job.get("categories") if isinstance(job.get("categories"), list) else []
    labels = [t for t in (_gql_text(c) for c in cats) if t]
    industry = labels[-1] if labels else ""   # [子類, 大類]，取大類

    arrangements = job.get("workArrangements")
    work_arrangements = [t for t in (_gql_text(a) for a in arrangements) if t] \
        if isinstance(arrangements, list) else []

    salary_text, salary_meta = _gql_salary_text(job.get("salary"))
    listed = job.get("listedAt") if isinstance(job.get("listedAt"), dict) else {}
    utc = str(listed.get("dateTimeUtc") or "")
    posted = _gql_relative_date(utc, reference)

    meta = {
        "hide_salary": bool(cjs_salary.get("hideSalary")),
        "listed_at_utc": utc,
        "categories": labels,
        "role_titles": roles,
        "work_arrangements": work_arrangements,
        "advertiser_id": str(advertiser.get("id") or ""),
        **salary_meta,
    }
    return JobRecord(
        job_id=f"jobsdb_{jid}" if jid else "jobsdb_",
        source="jobsdb",
        title=strip_new_badge(str(job.get("title") or "")),
        company=company,
        location=_gql_text(job.get("location")),
        salary=salary_text,
        job_type=job_type,
        industry=industry,
        description=str(job.get("abstract") or ""),
        requirements="",
        url=f"{BASE}/job/{jid}" if jid else "",
        posted_date=posted,
        scraped_at=reference.isoformat(),
        raw={"graphql": meta},
    )


# ---- GraphQL 搜尋通道（2026-11-15；只在已驗證維度上啟用） ----
# 依據：2026-11-14 離線快照（SSR 的 window.SEEK_APOLLO_DATA + /graphql 回應）。
# SSR 自己的 ROOT_QUERY key 就是完整 params，故 query 形狀不是猜的：
#   responseConfig.pageSize = 30；searchIntent.text 是**原始字串**（"AI Agent"，
#   不是 "ai%20agent"）；sort 只見 "score"；filter 只見 listedAt / salaryMin。
#
# 三個刻意不下的推（沒有離線實證，避免「結果看起來成功其實語意錯」）：
#   1. 地區（--district）：filter 無對應欄位；SSR 用瀏覽網址 /in-<slug>。
#   2. 職能（--category）：filter 有 categoryId，但需要內部數值 ID，字典只有 slug。
#   3. 排序（--sort）：只見 sort:"score"，沒有 sort:"date" 的實證。
# 上述任一維度被指定時，search() 直接走既有 Playwright 瀏覽網址。
#
# --days 的對應：set_days() 存的是 URL 的 daterange（1/3/7/14/31），
# GraphQL 用 "Nd"。31 是 URL 上「Last 30 days」的值，SSR 自拼 URL 的
# daterange=30 對應 filter.listedAt:"30d"，故 31 → "30d"（此格為推導，未實測）。
#
# 節流：單頁只發 1 次 POST，不重試、不併發；翻頁間隔由 BaseScraper._sleep()
# 統一負責（JobsDB 2 秒 + 抖動）。任何通道級失敗即熔斷本輪，直接退回 SSR，
# 不讓 _with_retry 把同一頁重撞成「3 次 GraphQL + 3 次瀏覽器」。
_GRAPHQL_URL = BASE + "/graphql"
_GRAPHQL_PAGE_SIZE = 30          # 與 SSR 每頁 30 張卡一致，維持 --pages 語意
_GRAPHQL_LISTED_AT = {
    "1": "1d", "3": "3d", "7": "7d", "14": "14d", "31": "30d",
}

_GRAPHQL_QUERY_TEMPLATE = """query {
  jobSearchV7(params: {
    responseConfig: {
      enrichment: {relatedSearchesCount: 12, suggestions: ["locationV1","queryParamLabelsV1","sabFilterV1","organisationV1","relatedSearchesV1"]}
      page: __PAGE__, pageSize: __PAGE_SIZE__, representations: ["uiV1"], results: ["jobs"]
    },
    searchContext: {brand: "jobsdb", channel: "web", intent: "SEARCH", solVisitorId: __VISITOR_ID__, source: "FE_SERP"},
    searchIntent: {country: "HK", distanceKms: 2, __FILTER__locale: "en-HK", sort: __SORT__, text: __TEXT__},
    sessionId: __SESSION_ID__
  }) {
    results {
      jobs {
        id title abstract
        advertiser { id name }
        organisation { id name }
        location { id displayName { text } }
        workArrangements { id label { text } }
        cjs { workTypes { sourceId name(locale: "en-HK") } salary { minimum maximum currency period hideSalary } roleTitles { shortId } }
        listedAt { dateTimeUtc }
        salary { min max period currency }
        categories { id label(locale: "en-HK") }
      }
    }
    metadata { sol }
  }
}"""


class JobsDBGraphQLError(RuntimeError):
    """GraphQL 通道不可用（網路／Cloudflare／schema 改版／回應形狀不符）。

    由 search() 捕捉後熔斷並退回既有 Playwright SSR 流程，不向上拋。
    """


# salaryMin 的週期後綴：m = monthly。目前只有 "17000m" 這一個形狀有離線
# payload 實證（2026-11-14 的 202 筆查詢），故 --salary-min 一律視為月薪，
# 不提供 --salary-type 去猜 hourly / annual 的後綴，避免「看起來成功但單位錯」。
_GRAPHQL_SALARY_MIN_SUFFIX = "m"


def graphql_salary_min(value) -> str:
    """把 `--salary-min` 正整數轉成站方 `salaryMin` 字串（`<n>m`）。

    純函式：0／None／負數／非整數一律回空字串（呼叫端視為「不下推」），
    不拋錯、不猜單位。`m` 是 monthly，為目前唯一有離線實證的週期。
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return ""
    if number <= 0:
        return ""
    return f"{number}{_GRAPHQL_SALARY_MIN_SUFFIX}"


def _gql_literal(value) -> str:
    """用 JSON 字串語法產生安全的 GraphQL string literal（含中文、引號跳脫）。"""
    return json.dumps(str(value or ""), ensure_ascii=False)


def build_graphql_query(*, keyword: str, page: int = 1, listed_at: str = "",
                        sort: str = "score", visitor_id: str = "", session_id: str = "",
                        salary_min: int | str | None = 0,
                        page_size: int = _GRAPHQL_PAGE_SIZE) -> str:
    """純函式：組出 jobSearchV7 查詢字串（不發請求、不讀環境、不帶憑證）。

    visitor_id / session_id 是前端產生的隨機匿名 UUID，不綁定帳號；呼叫端
    每次以 uuid4() 動態產生，避免把任何固定識別值寫進公開 repo。
    salary_min 為月薪下限；非正整數自動忽略，不讓壞值污染 query。
    """
    try:
        p = max(1, int(page))
        size = max(1, min(100, int(page_size)))
    except (TypeError, ValueError) as e:
        raise JobsDBGraphQLError(f"分頁參數無效：{e}") from e
    filters = []
    if listed_at:
        filters.append(f"listedAt: {_gql_literal(listed_at)}")
    salary = graphql_salary_min(salary_min)
    if salary:
        filters.append(f"salaryMin: {_gql_literal(salary)}")
    flt = f"filter: {{{', '.join(filters)}}}, " if filters else ""
    repl = {
        "__PAGE__": str(p),
        "__PAGE_SIZE__": str(size),
        "__VISITOR_ID__": _gql_literal(visitor_id),
        "__SESSION_ID__": _gql_literal(session_id),
        "__SORT__": _gql_literal(sort or "score"),
        "__TEXT__": _gql_literal(keyword),
        "__FILTER__": flt,
    }
    # 單次掃描：替換進去的關鍵字不會再被當成 placeholder 處理
    return re.sub(r"__[A-Z_]+__", lambda m: repl.get(m.group(), m.group()),
                  _GRAPHQL_QUERY_TEMPLATE)


def parse_graphql_response(data: dict, *, now: datetime | None = None) -> list[JobRecord]:
    """純函式：驗證 /graphql 回應並轉成 13 欄 JobRecord 清單（零請求）。

    形狀不對（含 GraphQL errors、schema 改版）一律丟 JobsDBGraphQLError，
    讓 search() 熔斷並退回 SSR；空清單是合法結果，不觸發 fallback。
    """
    if not isinstance(data, dict):
        raise JobsDBGraphQLError("回應不是 JSON 物件")
    if data.get("errors"):
        detail = json.dumps(data["errors"], ensure_ascii=False)[:200]
        raise JobsDBGraphQLError(f"GraphQL errors（可能 schema 改版）：{detail}")
    payload = data.get("data")
    search = payload.get("jobSearchV7") if isinstance(payload, dict) else None
    results = search.get("results") if isinstance(search, dict) else None
    jobs = results.get("jobs") if isinstance(results, dict) else None
    if not isinstance(jobs, list):
        raise JobsDBGraphQLError("回應缺少 data.jobSearchV7.results.jobs 陣列")
    return [record_from_graphql(j, now=now) for j in jobs]


# ---- jobDetails 詳情通道（2026-11-15，以朋友 202 份離線回應查證） ----
# 依據：jobDetails(id) 是網頁前端自己用的公開 operation，請求不需 Cookie /
# Authorization / sessionId / solVisitorId，只帶一般標頭即可取得完整 JD。
# ⚠️ 刻意不選 products { questionnaire { questions } }：那是申請問卷的題目定義，
#    靠近投遞流程、與求職搜尋無關。維持「只抓公開廣告內容」的使用範圍邊界。
_JOB_DETAILS_QUERY = """query JobDetails($id: ID!) {
  jobDetails(id: $id) {
    job {
      id title abstract content
      advertiser { id name }
      location { label }
      workTypes { label }
      listedAt { dateTimeUtc }
      expiresAt { dateTimeUtc }
      salary { label }
    }
  }
}"""

# 單一回應過大（Cloudflare 413 / Payload Too Large）時改用不含 content 的精簡版，
# 只影響該筆、不熔斷整輪；description 退回 abstract。
_JOB_DETAILS_QUERY_LIGHT = """query JobDetails($id: ID!) {
  jobDetails(id: $id) {
    job {
      id title abstract
      advertiser { id name }
      location { label }
      workTypes { label }
      listedAt { dateTimeUtc }
      expiresAt { dateTimeUtc }
      salary { label }
    }
  }
}"""


def build_job_details_query(*, light: bool = False) -> str:
    """純函式：回傳 jobDetails 查詢字串（不發請求、不帶憑證）。"""
    return _JOB_DETAILS_QUERY_LIGHT if light else _JOB_DETAILS_QUERY


def _gql_html_to_text(html: str) -> str:
    """職位正文 HTML 轉純文字，對齊既有 Playwright inner_text() 的語意。"""
    if not isinstance(html, str) or not html.strip():
        return ""
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _is_payload_too_large(error: BaseException) -> bool:
    """單一回應過大的訊號（不是限流、也不是通道掛掉）。"""
    msg = str(error).lower()
    return "413" in msg or "payload too large" in msg


def parse_job_details_response(data: dict, *, job_url: str = "",
                               now: datetime | None = None) -> Optional[JobRecord]:
    """純函式：jobDetails 回應轉 13 欄 JobRecord（零請求）。

    - 形狀異常／GraphQL errors → 丟 JobsDBGraphQLError，由 get_detail() 熔斷。
    - `jobDetails: null`（職位下架）→ 回 None，屬單筆無資料，不熔斷。
    - `content` 是 HTML，轉純文字後放 description；精簡版退回 abstract。
    """
    if not isinstance(data, dict):
        raise JobsDBGraphQLError("詳情回應不是 JSON 物件")
    if data.get("errors"):
        detail = json.dumps(data["errors"], ensure_ascii=False)[:200]
        raise JobsDBGraphQLError(f"詳情 GraphQL errors（可能 schema 改版）：{detail}")
    payload = data.get("data")
    details = payload.get("jobDetails") if isinstance(payload, dict) else None
    if details is None:
        return None
    if not isinstance(details, dict):
        raise JobsDBGraphQLError("詳情回應 jobDetails 形狀不符")
    job = details.get("job")
    if job is None:
        return None
    if not isinstance(job, dict):
        raise JobsDBGraphQLError("回應缺少 data.jobDetails.job 物件")

    reference = now or datetime.now(timezone.utc)
    jid = str(job.get("id") or "").strip()
    advertiser = job.get("advertiser") if isinstance(job.get("advertiser"), dict) else {}
    listed = job.get("listedAt") if isinstance(job.get("listedAt"), dict) else {}
    expired = job.get("expiresAt") if isinstance(job.get("expiresAt"), dict) else {}
    utc = str(listed.get("dateTimeUtc") or "")
    content = job.get("content") if isinstance(job.get("content"), str) else ""
    description = _gql_html_to_text(content) or str(job.get("abstract") or "")
    salary = _gql_text(job.get("salary"))

    return JobRecord(
        job_id=f"jobsdb_{jid}" if jid else "jobsdb_",
        source="jobsdb",
        title=strip_new_badge(str(job.get("title") or "")),
        company=_gql_text(advertiser),
        location=_gql_text(job.get("location")),
        salary=salary,
        job_type=_gql_text(job.get("workTypes")),
        industry="",
        description=description,
        requirements="",
        url=job_url or (f"{BASE}/job/{jid}" if jid else ""),
        posted_date=_gql_relative_date(utc, reference),
        scraped_at=reference.isoformat(),
        raw={"graphql_detail": {
            "listed_at_utc": utc,
            "expires_at_utc": str(expired.get("dateTimeUtc") or ""),
            "content_html_length": len(content),
            "salary_label": salary,
        }},
    )


# ---- JobsDB 自有 slug 字典（與 Moovup / 勞工處 完全獨立，見 README 鐵律） ----
_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_dict(name: str) -> list:
    """讀取 slug 字典。讀取失敗時警告並回空清單（與 gov_hk / moovup / linkedin
    的守護一致），避免字典檔缺損令整個 scrapers 套件 import 失敗、五站全滅。"""
    try:
        with open(os.path.join(_HERE, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning("[jobsdb] 讀取字典 %s 失敗（--category/--district 將不可用）：%s", name, e)
        return []


# 職能（分類）字典：list of {name(英), zh(中), slug}
_CLASSIFICATIONS = _load_dict("jobsdb_classifications.json")
# 地區字典：list of {zh, slug}
_DISTRICTS = _load_dict("jobsdb_districts.json")

_CAT_BY_ZH = {c["zh"]: c["slug"] for c in _CLASSIFICATIONS}
_CAT_BY_EN = {c["name"].lower(): c["slug"] for c in _CLASSIFICATIONS}
_CAT_BY_SLUG = {c["slug"]: c["slug"] for c in _CLASSIFICATIONS}
_DIST_BY_ZH = {d["zh"]: d["slug"] for d in _DISTRICTS}
_DIST_BY_SLUG = {d["slug"]: d["slug"] for d in _DISTRICTS}

# 詳情頁候選 data-automation 選擇器（v1 依實測微調）
_DETAIL_SELECTORS = {
    "title": ["job-detail-title", "jobTitle"],
    "company": ["jobCompany"],
    "location": ["jobLocation", "jobCardLocation"],
    "salary": ["jobSalary"],
    "description": ["jobDescription", "jobShortDescription"],
    "requirements": ["jobRequirements"],
    "classification": ["jobClassification"],
    "subclassification": ["jobSubClassification"],
    "listing_date": ["jobListingDate"],
}


class JobsDBScraper(BaseScraper):
    source = "jobsdb"
    use_browser = True
    # jobDetails.content 是完整 JD，比列表 abstract 更完整；顯式 opt-in 才覆寫，
    # 其餘據點仍維持「list 層級優先、detail 只補空」的既有政策。
    detail_replace_fields = frozenset({"description"})
    list_has_date = True   # 列表頁已含相對刊登日（jobListingDate），--days 不必抓詳情
    list_sorted_desc = True  # sortmode=ListedDate 為新→舊，--days 可提早停翻

    def __init__(self, headers: Optional[dict] = None):
        super().__init__(headers)
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._daterange: str = ""      # 站方端日期過濾（daterange=N），由 set_days() 注入
        self._salary_min: int = 0      # 站方端薪金下限（月薪），由 set_salary_min() 注入
        # GraphQL 通道熔斷：本輪一旦判定不可用就直接走 SSR，不重撞（見通道區塊註解）
        self._gql_broken: bool = False
        # jobDetails 詳情通道獨立熔斷（兩個 operation 各自判斷，不互相牽連）
        self._gql_detail_broken: bool = False

    # ---------- 站方端日期過濾掛載點（base_scraper.scrape_all 呼叫） ----------
    def set_days(self, days: int) -> None:
        """把 --days 下推成 JobsDB 的 `daterange=N`。

        ⚠️ 2026-09-10 逆向：站方側邊欄「Date posted」篩選器只給**五個離散值**
        （連結直接印在頁面上）：
            Today        → daterange=1
            Last 3 days  → daterange=3
            Last 7 days  → daterange=7
            Last 14 days → daterange=14
            Last 30 days → daterange=31   ← 注意是 31 不是 30
        只吃這五個值；送其他數字（如 daterange=10）站方不予理會。
        故取「不小於請求天數的最小合法值」；超過 31 天則不啟用站方端，
        退回客戶端篩選（列表本就含 jobListingDate，不會少抓）。
        """
        try:
            n = int(days)
        except (TypeError, ValueError):
            logger.warning("[jobsdb] --days %r 無法轉為整數，已忽略站方端過濾", days)
            return
        if n <= 0:
            return
        allowed = (1, 3, 7, 14, 31)
        picked = next((v for v in allowed if v >= n), None)
        if picked is None:
            logger.warning(
                "[jobsdb] --days %d 超出站方端上限（daterange 最大 31），"
                "僅由客戶端以列表 jobListingDate 篩選", n)
            return
        if picked != n:
            logger.info("[jobsdb] --days %d 無對應值，向上取整為 daterange=%d", n, picked)
        self._daterange = str(picked)
        logger.info("[jobsdb] 已啟用站方端日期過濾 daterange=%s", self._daterange)

    # ---------- 站方端薪金下限掛載點（base_scraper.scrape_all 呼叫） ----------
    def set_salary_min(self, value: int) -> None:
        """把 --salary-min 下推成 JobsDB 的站方端月薪下限。

        兩條通道語意一致，都是「月薪 ≥ N」：
        - GraphQL：filter.salaryMin: "<N>m"（m=monthly，2026-11-14 離線 payload 實證）；
        - SSR fallback：網址加 salaryrange=<N>-&salarytype=monthly
          （使用者提供並實測可用的網址形狀，可與 daterange 共存）。
        目前只做 monthly；hourly／annual 沒有實證，故不提供 --salary-type。
        """
        try:
            number = int(value)
        except (TypeError, ValueError):
            logger.warning(
                "[jobsdb] --salary-min %r 無法轉為整數，已忽略站方端下推", value)
            return
        if number <= 0:
            self._salary_min = 0
            return
        self._salary_min = number
        logger.info("[jobsdb] 已啟用站方端薪金下限 salaryMin=%s（monthly）",
                    graphql_salary_min(number))

    # ---------- 瀏覽器（共用一個 session，拿 cf clearance） ----------
    def _ensure_browser(self) -> None:
        if self._browser is not None:
            return
        if sync_playwright is None:
            raise RuntimeError(
                "此據點需要 Playwright：pip install playwright && playwright install chromium"
            )
        self._pw = self._start_playwright()
        self._browser = self._pw.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            user_agent=DEFAULT_HEADERS["User-Agent"],
            locale="zh-HK",
            # Accept-Language 是獨立標頭；先前被接在 UA 尾巴，變成
            # "...Chrome/156 zh-HK,zh;q=0.9" 這種一眼可辨的異常字串。
            extra_http_headers={"Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8"},
        )
        self._page = self._context.new_page()
        # 先訪首頁取得 Cloudflare clearance cookie（避免每頁重挑戰）
        try:
            self._page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_timeout(2000)
            logger.info("[jobsdb] 瀏覽器就緒（cf clearance 已取得）")
        except Exception as e:  # noqa: BLE001
            logger.warning("[jobsdb] 首頁預熱失敗（可能仍需挑戰）：%s", e)

    # ---------- slug 解析（JobsDB 自有體系） ----------
    @staticmethod
    def _derive_slug(text: str) -> str:
        """把任意文字推導成 JobsDB 風格 slug：小寫、&→and、去標點、空白→連字號。"""
        s = (text or "").lower().strip()
        s = s.replace("&", "and")
        s = re.sub(r"[^a-z0-9]+", "-", s)
        return s.strip("-")

    def resolve_category(self, value: str | None) -> str | None:
        """職能名（中/英/slug）→ slug。找不到則推導並警告（中文名無法推導，回 None）。"""
        v = (value or "").strip()
        if not v:
            return None
        if v in _CAT_BY_ZH:
            return _CAT_BY_ZH[v]
        if v.lower() in _CAT_BY_EN:
            return _CAT_BY_EN[v.lower()]
        if v in _CAT_BY_SLUG:
            return v
        # 中文名無法由字面推導 slug；英文/混合可嘗試
        if re.search(r"[\u4e00-\u9fff]", v):
            logger.warning("[jobsdb] 職能 %r 不在字典，忽略分類篩選（可用英文或 slug）", v)
            return None
        slug = self._derive_slug(v)
        logger.warning("[jobsdb] 職能 %r 不在字典，推導 slug=%r（未驗證）", v, slug)
        return slug

    def resolve_district(self, value: str | None) -> str | None:
        """地區名（中/英/slug）→ slug。多個以逗號分隔時取第一個並警告。"""
        v = (value or "").strip()
        if not v:
            return None
        parts = [p.strip() for p in v.split(",") if p.strip()]
        if len(parts) > 1:
            logger.warning("[jobsdb] 地區僅支援單一值，取第一個 %r（忽略 %s）",
                           parts[0], parts[1:])
        v = parts[0]
        if v in _DIST_BY_ZH:
            return _DIST_BY_ZH[v]
        if v in _DIST_BY_SLUG:
            return v
        slug = self._derive_slug(v)
        if slug in _DIST_BY_SLUG:
            return slug
        logger.warning("[jobsdb] 地區 %r 不在字典，推導 slug=%r（未驗證，可能導向首頁）", v, slug)
        return slug

    def resolve_sort(self, value: str | None) -> str | None:
        """將 --sort 選項對應到 JobsDB 網址參數 sortmode。

        JobsDB 網站 UI 僅提供「相關性（預設，不帶參數）」與「刊登日期（Date）」兩種排序。
        - post_dt_desc -> "ListedDate"（新→舊，已實測 1h→2h→3h 遞增）
        - 其餘選項（post_dt_asc / salary_* / yr_exp_* / edu_lvl_*）為 gov_hk 專有，
          JobsDB 無對應 UI，警告並回退 None（= 網站預設 Relevance）。
        """
        if not value:
            return None
        if value == "post_dt_desc":
            return "ListedDate"
        logger.warning(
            "[jobsdb] --sort %r 不適用 JobsDB（僅支援 post_dt_desc=按刊登日期新→舊；"
            "salary_*/yr_exp_*/edu_lvl_* 為 gov_hk 專有，post_dt_asc 無對應），"
            "已忽略並改用網站預設排序（相關性）", value)
        return None

    def _build_url(self, keyword: str, district: str | None, category: str | None,
                   page: int, sort: str | None = None) -> str:
        """組出 JobsDB 瀏覽網址：
        - 有職能：/jobs-in-<cat>  [ + /in-<dist> ]  [ ?keywords=K ] [ &page=N ] [ &sortmode=X ]
        - 無職能有地區：/jobs/in-<dist>  [ ?keywords=K ] [ &page=N ] [ &sortmode=X ]
        - 皆無：/jobs  [ ?keywords=K ] [ &page=N ] [ &sortmode=X ]
        翻頁：page>1 才加 page 參數（首頁省略，符合 JobsDB 行為）。
        排序：post_dt_desc -> sortmode=ListedDate（新→舊），其餘忽略（見 resolve_sort）。
        sortmode 與 keywords/page/地區瀏覽網址共存；站方會將 /jobs?keywords=K&... 301 為 /K-jobs?...。
        """
        cat_slug = self.resolve_category(category) if category else None
        dist_slug = self.resolve_district(district) if district else None
        sortmode = self.resolve_sort(sort) if sort else None

        if cat_slug:
            path = f"/jobs-in-{cat_slug}"
            if dist_slug:
                path += f"/in-{dist_slug}"
        elif dist_slug:
            path = f"/jobs/in-{dist_slug}"
        else:
            path = "/jobs"

        params = []
        if keyword:
            params.append(f"keywords={quote(keyword)}")
        if page and page > 1:
            params.append(f"page={page}")
        if sortmode:
            params.append(f"sortmode={sortmode}")
        if self._daterange:
            # 站方端日期過濾（僅 1/3/7/14/31 五個合法值，見 set_days）
            params.append(f"daterange={self._daterange}")
        if self._salary_min:
            # 站方端薪金下限（月薪）：salaryrange=<N>- 搭配 salarytype=monthly；
            # 與瀏覽網址的 daterange／keywords／sortmode 可共存（URL 實證）。
            params.append(f"salaryrange={self._salary_min}-")
            params.append("salarytype=monthly")
        if params:
            path += "?" + "&".join(params)
        return BASE + path

    # ---------- 搜尋（GraphQL 優先，既有 Playwright SSR 為 fallback） ----------
    def search(
        self,
        keyword: str,
        page: int = 1,
        district: Optional[str] = None,
        category: Optional[str] = None,
        industry: Optional[str] = None,
        sort: Optional[str] = None,
    ) -> list[JobRecord]:
        """單頁搜尋。只在「已驗證維度」上走 GraphQL，其餘一律用既有流程。

        路由規則見上方「GraphQL 搜尋通道」區塊：指定 --district / --category /
        --sort、設 JOBSDB_GRAPHQL=0、或本輪通道已熔斷時，直接走 _search_browser()。
        GraphQL 任何失敗都只熔斷本輪並退回 SSR，不向上拋、不重撞。
        """
        # JobsDB 無獨立「行業」維度（職能分類已涵蓋行業語意），忽略並提示
        if industry:
            logger.warning(
                "[jobsdb] --industry 不適用 JobsDB（職能分類已涵蓋行業語意），已忽略")

        if self._use_graphql(district=district, category=category, sort=sort):
            try:
                jobs = self._search_graphql(keyword, page)
                logger.info("[jobsdb] 第 %d 頁 GraphQL 取得 %d 筆", page, len(jobs))
                return jobs
            except Exception as e:  # noqa: BLE001 — 通道層任何意外都退回既有流程
                self._gql_broken = True
                logger.warning(
                    "[jobsdb] GraphQL 通道不可用（%s: %s），本輪改走 Playwright SSR",
                    type(e).__name__, str(e)[:200])
        return self._search_browser(keyword, page, district, category, sort=sort)

    def _use_graphql(self, *, district, category, sort) -> bool:
        """判斷本頁能否安全走 GraphQL（純判斷，不發請求）。"""
        if os.environ.get("JOBSDB_GRAPHQL", "1") == "0":
            return False
        if self._gql_broken:
            return False
        untested = [name for name, val in
                    (("--district", district), ("--category", category), ("--sort", sort))
                    if val]
        if untested:
            logger.info(
                "[jobsdb] 指定 %s（GraphQL 篩選維度未經離線實證），改走既有瀏覽網址",
                "、".join(untested))
            return False
        return True

    def _search_graphql(self, keyword: str, page: int) -> list[JobRecord]:
        """單頁 GraphQL 搜尋：1 次 POST → 驗證 → 13 欄轉接。"""
        listed_at = _GRAPHQL_LISTED_AT.get(self._daterange, "")
        query = build_graphql_query(
            keyword=keyword or "", page=page, listed_at=listed_at,
            salary_min=self._salary_min,
            sort="score",
            visitor_id=str(uuid.uuid4()), session_id=str(uuid.uuid4()),
        )
        logger.info("[jobsdb] POST /graphql（page=%d, listedAt=%s, salaryMin=%s, pageSize=%d）",
                    page, listed_at or "-", graphql_salary_min(self._salary_min) or "-",
                    _GRAPHQL_PAGE_SIZE)
        return parse_graphql_response(self._post_graphql(query))

    def _post_graphql(self, query: str, variables: Optional[dict] = None) -> dict:
        """送出 GraphQL 查詢（jobSearchV7 / jobDetails）並回傳 JSON。零憑證。

        不建立共用 Session、不保留任何狀態；Cloudflare 挑戰頁與非 200
        一律轉成 JobsDBGraphQLError，由呼叫端熔斷。variables 只給需要
        `$id` 的 jobDetails 使用，既有 jobSearchV7 呼叫的 payload 不變。
        """
        headers = dict(self.headers)
        headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": BASE,
            "Referer": BASE + "/",
        })
        payload = {"query": query}
        if variables is not None:
            payload["variables"] = variables
        response = requests.post(
            _GRAPHQL_URL, json=payload, headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        text = response.text or ""
        if response.status_code != 200:
            raise JobsDBGraphQLError(f"HTTP {response.status_code}")
        probe = text[:2000].upper()
        if "<!DOCTYPE HTML" in probe or "JUST A MOMENT" in probe:
            raise JobsDBGraphQLError("回應為 Cloudflare 挑戰頁（HTML）")
        try:
            return response.json()
        except ValueError as e:
            raise JobsDBGraphQLError(f"回應不是有效 JSON：{text[:120]}") from e

    def _search_browser(self, keyword: str, page: int, district, category,
                        sort: Optional[str] = None) -> list[JobRecord]:
        """既有 Playwright SSR 流程（內容與接入 GraphQL 前完全相同）。"""
        self._ensure_browser()
        url = self._build_url(keyword, district, category, page, sort=sort)
        logger.info("[jobsdb] GET %s", url)
        self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        self._page.wait_for_timeout(3000)  # 等 SSR + 客戶端渲染卡片
        cards = self._page.query_selector_all("[data-automation='normalJob']")
        logger.info("[jobsdb] 第 %d 頁卡片數：%d", page, len(cards))
        return [self._parse_card(c) for c in cards]

    @staticmethod
    def _parse_card(card) -> JobRecord:
        def _txt(da: str) -> str:
            el = card.query_selector(f"[data-automation='{da}']")
            return el.inner_text().strip() if el else ""

        def _href(da: str) -> str:
            el = card.query_selector(f"[data-automation='{da}']")
            return el.get_attribute("href") if el else ""

        title = strip_new_badge(_txt("jobTitle"))
        h = _href("jobTitle")
        m = re.search(r"/job/(\d+)", h or "")
        jid = m.group(1) if m else (h or title)
        classification = _txt("jobClassification").strip("() ").strip()
        sub = _txt("jobSubClassification")
        industry = classification or sub
        now = datetime.now().isoformat(timespec="seconds")
        return JobRecord(
            job_id=f"jobsdb_{jid}",
            source="jobsdb",
            title=title,
            company=_txt("jobCompany"),
            location=_txt("jobCardLocation") or _txt("jobLocation"),
            salary=_txt("jobSalary"),
            job_type="",
            description=_txt("jobShortDescription"),
            requirements="",
            url=urljoin(BASE, h) if h else "",
            posted_date=_txt("jobListingDate"),
            scraped_at=now,
            industry=industry,
        )

    # ---------- 詳情（2026-09-08 實測修正 selector） ----------
    # ⚠️ 舊版用的是 jobCompany / jobLocation / jobClassification / jobDescription，
    #    實測頁面上根本不存在這些 data-automation 值 → 只有標題抓得到，其餘全空。
    #    正確對照（實測列舉）：
    #      job-detail-title          → 職位名稱
    #      advertiser-name           → 公司（不是 jobCompany）
    #      job-detail-location       → 地區（不是 jobLocation）
    #      job-detail-classifications→ 職能／行業「細類 (大類)」
    #      job-detail-work-type      → 僱傭類型（Contract/Temp、Full Time…）
    #      jobAdDetails              → 完整描述
    #    薪資無穩定 data-automation（job-detail-add-expected-salary 是「登入查看」提示，
    #    非實際薪資）→ 留空，不硬湊。
    def get_detail(self, job_url: str) -> Optional[JobRecord]:
        """詳情頁：優先走 jobDetails GraphQL，失敗熔斷本輪並退回 Playwright。

        常見路徑（--keyword／--days／--pages + --detail）不會啟動瀏覽器。
        通道級失敗只熔斷本輪、不向上拋；單一回應過大則改用精簡查詢，
        只影響該筆。搜尋通道與詳情通道的熔斷旗標彼此獨立。
        """
        match = re.search(r"/job/(\d+)", job_url or "")
        jid = match.group(1) if match else ""
        if self._use_graphql_detail(jid):
            try:
                result = parse_job_details_response(
                    self._post_graphql(build_job_details_query(),
                                       variables={"id": jid}),
                    job_url=job_url,
                )
                if result is None:
                    logger.info("[jobsdb] jobDetails 無資料（%s），略過此筆詳情", jid)
                    return None
                return result
            except Exception as e:  # noqa: BLE001 — 通道層任何意外都退回既有流程
                if _is_payload_too_large(e):
                    try:
                        light = parse_job_details_response(
                            self._post_graphql(build_job_details_query(light=True),
                                               variables={"id": jid}),
                            job_url=job_url,
                        )
                        if light is not None:
                            logger.info("[jobsdb] 正文過大，僅取中繼資料（%s）", jid)
                            return light
                    except Exception as e2:  # noqa: BLE001
                        e = e2
                self._gql_detail_broken = True
                logger.warning(
                    "[jobsdb] jobDetails 通道不可用（%s: %s），本輪詳情改走 Playwright",
                    type(e).__name__, str(e)[:200])
        return self._get_detail_browser(job_url)

    def _use_graphql_detail(self, jid: str) -> bool:
        """判斷本筆詳情能否安全走 jobDetails（純判斷，不發請求）。"""
        if os.environ.get("JOBSDB_GRAPHQL", "1") == "0":
            return False
        if self._gql_detail_broken:
            return False
        if not jid:
            logger.info("[jobsdb] 網址無法抽出職位 ID，詳情改走既有瀏覽網址")
            return False
        return True

    def _get_detail_browser(self, job_url: str) -> Optional[JobRecord]:
        """既有 Playwright 詳情流程（原 get_detail 原封不動搬來，作為 fallback）。"""
        self._ensure_browser()
        self._page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
        self._page.wait_for_timeout(2500)

        def _txt(da: str) -> str:
            el = self._page.query_selector(f"[data-automation='{da}']")
            return el.inner_text().strip() if el else ""

        jid = re.search(r"/job/(\d+)", job_url)
        jid = jid.group(1) if jid else job_url
        now = datetime.now().isoformat(timespec="seconds")
        return JobRecord(
            job_id=f"jobsdb_{jid}",
            source="jobsdb",
            title=strip_new_badge(_txt("job-detail-title") or _txt("jobTitle")),
            company=_txt("advertiser-name"),
            location=_txt("job-detail-location"),
            salary=_txt("job-detail-salary") or _txt("jobSalary"),
            job_type=_txt("job-detail-work-type"),
            description=_txt("jobAdDetails"),
            requirements="",
            url=job_url,
            posted_date=_txt("jobListingDate"),
            scraped_at=now,
            industry=_txt("job-detail-classifications"),
        )

    # ---------- 相對時間解析（"7d ago" -> 7；"13h ago"/"Just now" -> 0） ----------
    def days_since_posted(self, job: JobRecord) -> Optional[int]:
        raw = (job.posted_date or "").strip().lower()
        if not raw:
            return None
        if "just now" in raw or raw == "now":
            return 0
        m = re.match(r"(\d+)\s*([dhms])", raw)
        if not m:
            return None
        n = int(m.group(1))
        unit = m.group(2)
        return 0 if unit in ("h", "m", "s") else n

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
