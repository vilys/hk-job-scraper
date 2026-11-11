"""聚合層：把各站 JobRecord 煉成可比較、可排序、可去重的 schema v2 紀錄。

設計原則
--------
* **爬蟲零侵入**：本模組只吃 `list[SourceResult]`，輸出 `list[dict]`。
  `JobRecord`、`exporter`、`main.py` 完全不動，仍維持既有 13 欄。
* **原字串不丟**：`salary` 與 `posted_date_raw` 保留站方原文；
  `posted_date` 才是正規化後的 ISO。解析失敗一律給空值／null，不猜、不丟資料。
* **可比較優先**：`salary_min` / `salary_max` 一律是「月薪整數」，
  原始週期記在 `salary_period`。換算係數見 `PERIOD_TO_MONTH`。
* **相對時間以 scraped_at 為基準**，不是執行當下的 now，讓離線重播結果可重現。
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

# ---- schema v2 新增欄位（舊 13 欄見 job_model.JobRecord.FIELDS）----
V2_EXTRA_FIELDS: tuple[str, ...] = (
    "salary_min", "salary_max", "salary_period",
    "posted_date_raw",
    "sources", "urls",
)

# 時薪→月薪：8 小時/天 × 22 工作日；日薪→月薪：22 工作日；年薪→月薪：÷12
PERIOD_TO_MONTH: dict[str, float] = {
    "month": 1.0,
    "hour": 8.0 * 22.0,
    "day": 22.0,
    "year": 1.0 / 12.0,
}

# ---- 薪金 ----
# 面議類：有字串但無任何可比較數字
_NO_SALARY_WORDS = re.compile(
    r"^(?:tbd|competitive|negotiable|面議|議價|待議|薪金面議|—|-{2,}|n/?a|)$",
    re.IGNORECASE,
)
_NUM_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([Kk千萬])?")
_PERIOD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("hour", re.compile(r"per\s*hour|/\s*h(?:ou)?r|時薪|每小時|/\s*小時|hourly|\bph\b", re.I)),
    ("day", re.compile(r"per\s*day|/\s*day|日薪|每日|/\s*日|daily", re.I)),
    ("year", re.compile(r"per\s*(?:annum|year)|/\s*year|年薪|annual|p\.?a\.?|\bpa\b", re.I)),
    ("month", re.compile(r"per\s*month|/\s*month|/\s*m\b|/\s*月|月薪|每月|monthly|per\s*m\b", re.I)),
)
_MULTIPLIER = {"K": 1_000, "k": 1_000, "千": 1_000, "萬": 10_000}


def _to_int(num: str, unit: str | None) -> int:
    value = float(num.replace(",", ""))
    if unit:
        value *= _MULTIPLIER.get(unit, 1)
    return int(round(value))


def parse_salary(raw: str) -> tuple[int | None, int | None, str | None]:
    """回傳 `(月薪下限, 月薪上限, 原始週期)`；解析不出給 `(None, None, None)`。

    涵蓋實測格式：`$15K/月`、`$13,000 - $14,000 （月薪）`、
    `$16,617 – $23,000 per month`、`$15K - $17K`、`$15.5K - $16.5K`、
    `$13K-14K/M`；另支援時薪／日薪／年薪。
    """
    text = (raw or "").strip()
    if not text or _NO_SALARY_WORDS.match(text):
        return None, None, None

    period = "month"
    for name, pattern in _PERIOD_PATTERNS:
        if pattern.search(text):
            period = name
            break

    # 先把週期標記從字串移除，避免 `/M`、`per month` 之類被誤當數字單位
    cleaned = text
    for _, pattern in _PERIOD_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"[（(][^）)]*[）)]", " ", cleaned)  # （月薪）等註記

    numbers = [
        (_to_int(m.group(1), m.group(2)), m.group(2))
        for m in _NUM_RE.finditer(cleaned)
    ]
    if not numbers:
        return None, None, None

    low = numbers[0][0]
    high = numbers[1][0] if len(numbers) > 1 else low
    if high < low:
        low, high = high, low
    # 極端值視為解析失敗（例如把職位編號當成薪金）
    if low <= 0 or high > 100_000_000:
        return None, None, None

    factor = PERIOD_TO_MONTH[period]
    return int(round(low * factor)), int(round(high * factor)), period


# ---- 日期 ----
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_RELATIVE: tuple[tuple[re.Pattern[str], str], ...] = (
    # 實測 2026-11-11 baseline：jobsdb 有 `49m ago`、foundit 有 `an hour ago`
    (re.compile(r"(\d+)\s*(?:m|min|mins|minute|minutes)\s*ago", re.I), "minutes"),
    (re.compile(r"(\d+)\s*(?:h|hr|hrs|hour|hours)\s*ago", re.I), "hours"),
    (re.compile(r"(\d+)\s*(?:d|day|days)\s*ago", re.I), "days"),
    (re.compile(r"(\d+)\s*(?:w|wk|week|weeks)\s*ago", re.I), "weeks"),
    (re.compile(r"(\d+)\s*(?:mo|month|months)\s*ago", re.I), "months"),
    (re.compile(r"(\d+)\s*(?:y|yr|year|years)\s*ago", re.I), "years"),
    (re.compile(r"within\s*(\d+)\s*(?:mo|month|months)", re.I), "months"),
)
_ARTICLE_REL = re.compile(r"\ban?\s+(hour|day|week|month|year)s?\s+ago", re.I)
_ARTICLE_DELTA = {
    "hour": timedelta(hours=1), "day": timedelta(days=1),
    "week": timedelta(weeks=1), "month": timedelta(days=30),
    "year": timedelta(days=365),
}
# 舊存檔（moovup 等）與舊版儀表板留下的中文相對時間／`30d+`。
# 儀表板過去自己養一套 parser，改用本函式時若少了這幾種格式，
# 既有 output/ 裡的舊職位會突然變成「日期未知」，故在此補齊成單一來源。
_REL_CN = re.compile(r"(\d+)\s*(分鐘|小時|星期|個月|時|天|日|週|周|月|年)前")
_CN_DELTA = {
    "分鐘": timedelta(minutes=1),
    "小時": timedelta(hours=1), "時": timedelta(hours=1),
    "天": timedelta(days=1), "日": timedelta(days=1),
    "週": timedelta(weeks=1), "周": timedelta(weeks=1),
    "星期": timedelta(weeks=1),
    "個月": timedelta(days=30), "月": timedelta(days=30),
    "年": timedelta(days=365),
}
_DAYS_PLUS = re.compile(r"^(\d+)\s*d\+$", re.I)
_MMDD = re.compile(r"\bon\s+(\d{1,2})-(\d{1,2})\b")
# 勞工處 gov_hk 詳情頁 #postedDt 的格式是 DD/MM/YYYY（日在前），依據：
#   (1) scrapers/gov_hk.py:363 的實測註解與 days_since_posted() 的
#       strptime(s, "%d/%m/%Y")；
#   (2) 2026-11-11 真跑 `--source gov_hk --category 打字 --detail --days 30`
#       的 output/打字_30天.csv：12/12 筆 posted_date_raw 皆如 `10/11/2026`。
# 與 _MMDD（`on 11-10`，站方另一種「月-日」相對寫法）是不同來源、不同格式，
# 不可混用；本專案只處理勞工處，故遇斜線一律以 DD/MM 解讀。
_DDMMYYYY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_DMONTH_YEAR = re.compile(r"^(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})$")
_MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
_MONTHS.update({m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 1)})


def _reference(scraped_at: str) -> datetime:
    """相對時間的換算基準；每筆用自己的 scraped_at，讓離線重播可重現。"""
    if scraped_at:
        try:
            dt = datetime.fromisoformat(scraped_at.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def parse_date(raw: str, scraped_at: str = "") -> str:
    """轉成 ISO `YYYY-MM-DD`；無法解析回 `""`（原字串由呼叫端留在 posted_date_raw）。

    絕對日期涵蓋 `YYYY-MM-DD`、`DD/MM/YYYY`（勞工處詳情頁）、`D Mon YYYY`、
    `YYYY/MM/DD`、`on MM-DD`；相對時間含 `19h ago`／`an hour ago`／
    `7日前`／`2個月前`／`30d+` 等。
    """
    text = (raw or "").strip()
    if not text:
        return ""
    ref = _reference(scraped_at)

    m = _ISO_DATE.match(text)
    if m:
        return text
    # ISO 時間戳（eFC 詳情等）
    if re.match(r"^\d{4}-\d{2}-\d{2}T", text):
        return text[:10]

    for pattern, unit in _RELATIVE:
        m = pattern.search(text)
        if not m:
            continue
        n = int(m.group(1))
        delta = {
            "minutes": timedelta(minutes=n),
            "hours": timedelta(hours=n),
            "days": timedelta(days=n),
            "weeks": timedelta(weeks=n),
            "months": timedelta(days=n * 30),
            "years": timedelta(days=n * 365),
        }[unit]
        return (ref - delta).date().isoformat()

    m = _ARTICLE_REL.search(text)
    if m:
        return (ref - _ARTICLE_DELTA[m.group(1).lower().rstrip("s")]).date().isoformat()

    m = _REL_CN.search(text)
    if m:
        return (ref - int(m.group(1)) * _CN_DELTA[m.group(2)]).date().isoformat()

    m = _DAYS_PLUS.match(text)
    if m:
        return (ref - timedelta(days=int(m.group(1)))).date().isoformat()

    if re.search(r"just now|today|剛剛|今天", text, re.I):
        return ref.date().isoformat()

    m = _MMDD.search(text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = ref.year
        if (month, day) > (ref.month, ref.day):
            year -= 1  # 尚未到達的月日 → 去年
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return ""

    m = _DDMMYYYY.match(text)
    if m:
        # 日在前（勞工處）；datetime 會擋掉 32/13/2026 之類的非法日期
        day, month, year = (int(x) for x in m.groups())
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return ""

    m = _DMONTH_YEAR.match(text)
    if m and m.group(2).lower() in _MONTHS:
        try:
            return datetime(int(m.group(3)), _MONTHS[m.group(2).lower()],
                            int(m.group(1))).date().isoformat()
        except ValueError:
            return ""

    # 其他松散絕對格式（如 2026/11/03）
    m = re.match(r"^(\d{4})[/.](\d{1,2})[/.](\d{1,2})$", text)
    if m:
        try:
            return datetime(*(int(x) for x in m.groups())).date().isoformat()
        except ValueError:
            return ""
    return ""


# ---- 正規化（去重用）----
def _norm(text: str) -> str:
    """NFKC + 小寫 + 空白壓縮；不动標點，避免把不同職位誤判為同一筆。"""
    s = unicodedata.normalize("NFKC", text or "").strip().lower()
    return re.sub(r"\s+", " ", s)


def _append_unique(seq: list[str], values: Iterable[str]) -> None:
    for v in values:
        if v and v not in seq:
            seq.append(v)


# ---- v2 紀錄 ----
def to_v2(job: dict) -> dict:
    """從 v1 dict 建出 v2 dict（不改動傳入物件）。"""
    out = dict(job)
    salary = str(job.get("salary") or "")
    lo, hi, period = parse_salary(salary)
    raw_date = str(job.get("posted_date") or "")
    out["salary_min"] = lo
    out["salary_max"] = hi
    out["salary_period"] = period
    out["posted_date_raw"] = raw_date
    out["posted_date"] = parse_date(raw_date, str(job.get("scraped_at") or ""))
    out["sources"] = [job["source"]] if job.get("source") else []
    out["urls"] = [job["url"]] if job.get("url") else []
    return out


def has_numeric_salary(job: dict) -> bool:
    """`withSalary` 與 coverage 的唯一判準：原字串含阿拉伯數字。"""
    return bool(re.search(r"\d", str(job.get("salary") or "")))


# ---- 去重 ----
def deduplicate(jobs: list[dict]) -> tuple[list[dict], int]:
    """重貼（不同刊登日的同一職位）是獨立職缺，不再被吞掉。

    鍵的優先序：

    1. URL 完全相同 → 合併（同一則貼文，與日期無關）。
    2. (正規化標題, 正規化公司, **ISO 刊登日**) 三者相同 → 合併；
       這涵蓋同日跨站張貼（如 recruit + jobmarket 的 procurement clerk）。
    3. 刊登日不同 → **保留為獨立筆**，求職者才看得到「公司又重貼了一次」。
    4. 兩筆日期都解析不出 → 退回舊的 (標題, 公司) 合併，避免列表層
       （無日期欄）的資料重複爆炸。

    公司為空時只用 URL 判定，避免把不同僱主的「公司欄缺失」職位誤併。
    合併只累加 `sources` / `urls`，其餘欄位取第一筆
    （跨站互補補齊屬下一輪，見 docs/）。
    """
    out: list[dict] = []
    by_url: dict[str, dict] = {}
    by_tcd: dict[tuple[str, str, str], dict] = {}   # 有日期：標題 + 公司 + ISO 日
    by_tc: dict[tuple[str, str], dict] = {}         # 兩筆皆無日期：退回舊鍵
    merged = 0

    for job in jobs:
        url = (job.get("url") or "").strip()
        title = _norm(str(job.get("title") or ""))
        company = _norm(str(job.get("company") or ""))
        tc = (title, company) if title and company else None
        iso_date = str(job.get("posted_date") or "").strip()

        target = None
        if url and url in by_url:
            target = by_url[url]
        elif tc and iso_date:
            target = by_tcd.get((title, company, iso_date))
        elif tc and not iso_date:
            target = by_tc.get(tc)

        if target is not None:
            _append_unique(target["sources"], job.get("sources") or [])
            _append_unique(target["urls"], job.get("urls") or [])
            merged += 1
            continue

        out.append(job)
        if url:
            by_url[url] = job
        if tc:
            if iso_date:
                by_tcd[(title, company, iso_date)] = job
            else:
                by_tc[tc] = job
    return out, merged


# ---- 排序 ----
SORT_LABELS = {
    "date": "刊登日期（新→舊）",
    "salary": "月薪（高→低）",
}

# 薪金排序的取樣依據。求職者看到「14K 起跳」排在「18K 起跳」前面會覺得不可信，
# 故預設改用中位數 (min+max)/2；仍可用 --salary-by min|mid|max 切回下限／上限。
SALARY_BY_CHOICES: tuple[str, ...] = ("min", "mid", "max")
SALARY_BY_LABELS = {
    "min": "月薪下限",
    "mid": "月薪中位數 (min+max)/2",
    "max": "月薪上限",
}


def salary_sort_value(job: dict, salary_by: str = "mid") -> float | None:
    """回傳該筆用於排序的月薪值；沒有可比較數字回 `None`（排最後，不丟棄）。

    `min` / `max` 缺一側時用另一側補；`mid` 無 max 時視為單點薪金，直接用 min。
    """
    if salary_by not in SALARY_BY_CHOICES:
        raise ValueError(f"未知的薪金排序依據：{salary_by}")
    low, high = job.get("salary_min"), job.get("salary_max")
    if low is None and high is None:
        return None
    low = high if low is None else low
    high = low if high is None else high
    if salary_by == "min":
        return float(low)
    if salary_by == "max":
        return float(high)
    return (low + high) / 2


def sort_label(by: str, salary_by: str = "mid") -> str:
    """人類模式「排序依據」那一行；把取樣依據寫清楚，不讓人猜。"""
    if by == "salary":
        return f"{SALARY_BY_LABELS[salary_by]}（高→低）"
    return SORT_LABELS[by]


def sort_jobs(jobs: list[dict], by: str | None, *, salary_by: str = "mid") -> list[dict]:
    """無日期／無數字的排最後，且一筆都不丟。"""
    if not by:
        return list(jobs)
    if by == "date":
        valued = [j for j in jobs if j.get("posted_date")]
        missing = [j for j in jobs if not j.get("posted_date")]
        valued.sort(key=lambda j: j["posted_date"], reverse=True)
        return valued + missing
    if by == "salary":
        valued, missing = [], []
        for j in jobs:
            value = salary_sort_value(j, salary_by)
            (missing if value is None else valued).append(j)
        valued.sort(key=lambda j: salary_sort_value(j, salary_by), reverse=True)
        return valued + missing
    raise ValueError(f"未知的排序依據：{by}")


# ---- 完整度 ----
def coverage(jobs: list[dict]) -> dict[str, int]:
    return {
        "jobs": len(jobs),
        "company": sum(1 for j in jobs if j.get("company")),
        "salary": sum(1 for j in jobs if has_numeric_salary(j)),
        "location": sum(1 for j in jobs if j.get("location")),
        "date": sum(1 for j in jobs if j.get("posted_date")),
    }


COVERAGE_ADVICE = {
    "recruit": ("location", "加 --fill-location 補地區"),
    "gov_hk": ("company", "加 --detail 補公司名（每筆多 1 支請求）"),
    "moovup": ("date", "加 --detail 補刊登日"),
    "linkedin": ("salary", "站方列表不提供薪金，屬已知限制"),
    "jobmarket": ("salary", "站方列表不提供薪金，屬已知限制"),
    "foundit": ("salary", "站方列表不提供薪金，屬已知限制"),
    "jobsdb": ("salary", "站方列表薪金常缺，屬已知限制"),
}


def coverage_advice(results: list) -> list[str]:
    """針對「該站全缺」的欄位給一行建議；部分缺不嘮叨。"""
    lines: list[str] = []
    for r in results:
        if r.status != "ok" or not r.jobs:
            continue
        known = COVERAGE_ADVICE.get(r.name)
        if not known:
            continue
        field, advice = known
        cov = coverage([to_v2(j.to_dict()) for j in r.jobs])
        if cov[field] == 0:
            lines.append(f"  {r.name} {field} 0/{cov['jobs']} → {advice}")
    return lines


# ---- CSV（human / --out 用，UTF-8 BOM 讓 Excel 直接開）----
def csv_fields(v1_fields: tuple[str, ...]) -> list[str]:
    return list(v1_fields) + list(V2_EXTRA_FIELDS)


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return "|".join(str(v) for v in value)
    if value is None:
        return ""
    return value


def write_csv(jobs: list[dict], path: Path, fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for job in jobs:
                writer.writerow({k: _csv_value(job.get(k)) for k in fields})
        tmp.replace(path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
