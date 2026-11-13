"""聚合 output/ 內所有爬蟲產出 → 單檔離線 HTML 儀表板。

用法：
    python build_dashboard.py                       # 掃 output/，產生 output/dashboard.html
    python build_dashboard.py --out 我的看板.html     # 自訂檔名
    python build_dashboard.py --glob "output/*.json" # 只吃 JSON（不吃 CSV）

設計要點：
- 資料**內嵌**進 HTML（不用 fetch），因此產出的 html 直接雙擊就能開（file:// 下
  瀏覽器會擋 fetch 外部 JSON，內嵌可避開這個坑）。
- 容錯讀取：CSV 可能是 UTF-8 / UTF-8-BOM / Big5(cp950) / GB18030，逐個嘗試。
- JSON 同時認得「職位陣列」與 CLI 的 v1／v2 封套（`schemaVersion` + `jobs`）。
- 自動跳過非職位檔（如 ict_density_leaderboard.json 是地區統計，不是職位陣列）。
- 依 job_id 去重（多檔重複匯出同一職位時，保留描述較完整 / 抓取較新的一筆）；
  這與 hkjobs 聚合層的「同 URL／同標題＋公司＋同刊登日」是不同的語義，見 README。
- 日期解析統一交給 `hkjobs.aggregate.parse_date`，並以該筆 `scraped_at`
  為基準算天數，舊存檔不會「越放越舊」。
- 無障礙：預設字級 16px、可切大字模式、語義化 article/heading、
  aria 與鍵盤可達的來源按鈕；放大到 200% 仍能捲動閱讀。
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

from hkjobs import aggregate

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

FIELDS = [
    "job_id", "source", "title", "company", "location", "salary", "job_type",
    "industry", "description", "requirements", "url", "posted_date", "scraped_at",
]

SOURCE_LABEL = {
    "moovup": "Moovup 好工速遞",
    "gov_hk": "勞工處",
    "jobsdb": "JobsDB",
    "linkedin": "LinkedIn",
    "indeed": "Indeed",
    "recruit": "Recruit",
    "jobmarket": "JobMarket",
    "foundit": "foundit",
    "efc": "eFinancialCareers",
    "liepin": "獵聘",
    "zhipin": "BOSS直聘",
    "offertoday": "OfferToday",
}

# CSV 讀取時的編碼候選（含香港常見的 Big5 / GB18030）
_ENCODINGS = ("utf-8-sig", "utf-8", "cp950", "big5hkscs", "gb18030", "latin-1")


# ---------------- 讀檔 ----------------
def _read_json_jobs(path: str) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        print(f"  ! 略過（JSON 讀取失敗）{os.path.basename(path)}：{e}")
        return []

    # CLI 的 `hkjobs search --json --out x.json` 產出 v1／v2 封套：
    # {"schemaVersion": 1|2, "jobs": [...]}。過去只認陣列，這類檔案會被
    # 誤判成「非職位檔」，其實它們正是最重要的輸入。
    if isinstance(data, dict):
        rows = data.get("jobs")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict) \
                and ("job_id" in rows[0] or "title" in rows[0]):
            return [dict(r) for r in rows]
        return []
    if not isinstance(data, list) or not data:
        return []  # 非職位陣列（如地區統計檔）
    if not isinstance(data[0], dict):
        return []
    if "job_id" not in data[0] and "title" not in data[0]:
        return []
    return [dict(r) for r in data]


def _read_csv_jobs(path: str) -> list[dict]:
    for enc in _ENCODINGS:
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                rows = list(csv.DictReader(f))
            if rows and ("job_id" in rows[0] or "title" in rows[0]):
                if enc != "utf-8-sig":
                    print(f"  i {os.path.basename(path)} 以 {enc} 編碼成功讀取")
                return [dict(r) for r in rows]
            return []
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception as e:  # noqa: BLE001
            print(f"  ! 略過（CSV 讀取失敗）{os.path.basename(path)}：{e}")
            return []
    print(f"  ! 略過（編碼無法辨識）{os.path.basename(path)}")
    return []


# ---------------- 正規化 ----------------
def _reference_day(scraped_at: str) -> date:
    """刊登天數的基準是「抓取當日」；沒有 scraped_at 才退回今天。

    舊版用 `date.today()` 當基準，同一份 2026-11-11 的存檔到 2027 年
    會被算成「300 天前」，越放越舊。以每筆自己的 scraped_at 為準，
    離線重播與歷史存檔都能重現相同的數字。
    """
    if re.match(r"^\d{4}-\d{2}-\d{2}", scraped_at):
        try:
            return date.fromisoformat(scraped_at[:10])
        except ValueError:
            pass
    return date.today()


def parse_age_days(rec: dict) -> int | None:
    """把刊登日折算成「距抓取日天數」；無法判定回 None。

    日期解析統一交給 `hkjobs.aggregate.parse_date`（與 CLI 同一套規則，
    不再養第二套 regex），相對時間以該筆 `scraped_at` 換算。
    v2 封套會把站方原文放在 `posted_date_raw`，優先使用它。
    """
    raw = str(rec.get("posted_date_raw") or rec.get("posted_date") or "").strip()
    if not raw:
        return None
    scraped_at = str(rec.get("scraped_at") or "").strip()
    iso = aggregate.parse_date(raw, scraped_at)
    if not iso:
        return None
    try:
        posted = date.fromisoformat(iso)
        return max(0, (_reference_day(scraped_at) - posted).days)
    except (ValueError, TypeError):
        return None


def parse_scraped_days(s: str) -> int | None:
    """抓取時間距今幾天。列表層抓取的職位常無刊登日，抓取日可作為參考座標
    （注意：抓取日 ≠ 刊登日，只能證明「職位當時仍在架上」）。"""
    s = (s or "").strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        return None
    try:
        d = date.fromisoformat(m.group(0))
    except ValueError:
        return None
    return max(0, (date.today() - d).days)


_SALARY_NUM = re.compile(r"([\d,]+(?:\.\d+)?)\s*[kK]?")


def parse_salary(rec: dict) -> tuple[float | None, str, str]:
    """從薪資文字抓數字與單位，回傳 (排序用數值, 單位, 期間)。

    僅供排序 / 篩選「有薪資」之用，不做跨單位換算（時薪與月薪不可直接相比）。
    """
    raw = (rec.get("salary") or "").strip()
    if not raw or "$" not in raw and not re.search(r"\d", raw):
        return None, "", ""
    unit = "月" if re.search(r"月|month|/mo", raw, re.I) else (
        "小時" if re.search(r"小時|hour|/hr|/h", raw, re.I) else (
            "年" if re.search(r"年|year|annum", raw, re.I) else ""))
    nums: list[float] = []
    for m in _SALARY_NUM.finditer(raw):
        tok = m.group(1).replace(",", "")
        try:
            v = float(tok)
        except ValueError:
            continue
        # "$18K" 這種縮寫：數值過小且原文字含 K 時視為千
        seg = raw[m.start():m.end()]
        if re.search(r"\d\s*[kK]", seg) or (v < 1000 and "k" in seg.lower()):
            v *= 1000
        nums.append(v)
    if not nums:
        return None, unit, ""
    return min(nums), unit, ""


def normalize(rec: dict, src_file: str) -> dict:
    job_id = (rec.get("job_id") or "").strip() or (
        (rec.get("url") or "") + "|" + (rec.get("title") or "")
    )
    lo, unit, _ = parse_salary(rec)
    raw_date = str(rec.get("posted_date_raw") or rec.get("posted_date") or "").strip()
    scraped_at = str(rec.get("scraped_at") or "").strip()
    iso_date = aggregate.parse_date(raw_date, scraped_at) or raw_date
    return {
        "id": job_id,
        "source": (rec.get("source") or "").strip() or "unknown",
        "title": (rec.get("title") or "").strip(),
        "company": (rec.get("company") or "").strip(),
        "location": (rec.get("location") or "").strip(),
        "salary": (rec.get("salary") or "").strip(),
        "salary_num": lo,
        "salary_unit": unit,
        "job_type": (rec.get("job_type") or "").strip(),
        "industry": (rec.get("industry") or "").strip(),
        "description": (rec.get("description") or "").strip(),
        "requirements": (rec.get("requirements") or "").strip(),
        "url": (rec.get("url") or "").strip(),
        "posted_date": iso_date,
        "age_days": parse_age_days(rec),
        "scraped_days": parse_scraped_days(rec.get("scraped_at")),
        "scraped_at": (rec.get("scraped_at") or "").strip(),
        "file": os.path.basename(src_file),
    }


def _better(a: dict, b: dict) -> dict:
    """去重時挑「較好」的一筆：描述較完整者勝，其次抓取時間較新者。"""
    sa = len(a.get("description") or "") + len(a.get("requirements") or "")
    sb = len(b.get("description") or "") + len(b.get("requirements") or "")
    if sa != sb:
        return a if sa > sb else b
    return a if (a.get("scraped_at") or "") >= (b.get("scraped_at") or "") else b


def collect(patterns: list[str]) -> tuple[list[dict], dict]:
    files: list[str] = []
    for pat in patterns:
        files.extend(sorted(glob.glob(pat, recursive=False)))
    files = [f for f in dict.fromkeys(files) if os.path.isfile(f)]

    raw: list[tuple[dict, str]] = []
    skipped: list[str] = []
    for p in files:
        ext = os.path.splitext(p)[1].lower()
        rows = _read_json_jobs(p) if ext == ".json" else (
            _read_csv_jobs(p) if ext == ".csv" else [])
        if rows:
            raw.extend((r, p) for r in rows)
        elif ext in (".json", ".csv"):
            skipped.append(os.path.basename(p))

    merged: dict[str, dict] = {}
    for r, p in raw:
        n = normalize(r, p)
        if not n["title"] and not n["id"]:
            continue
        if n["id"] in merged:
            merged[n["id"]] = _better(merged[n["id"]], n)
        else:
            merged[n["id"]] = n

    jobs = list(merged.values())
    # 預設排序：刊登日新→舊；同天者以抓取時間新→舊（sort 穩定，故先排次要鍵）
    jobs.sort(key=lambda j: j.get("scraped_at") or "", reverse=True)
    jobs.sort(key=lambda j: j["age_days"] if j["age_days"] is not None else 10 ** 6)

    per_source: dict[str, int] = {}
    for j in jobs:
        per_source[j["source"]] = per_source.get(j["source"], 0) + 1

    scraped = [j["scraped_at"][:10] for j in jobs if j["scraped_at"]]
    meta = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total": len(jobs),
        "raw_rows": len(raw),
        "files_used": len({p for _, p in raw}),
        "files_skipped": skipped,
        "per_source": per_source,
        "scraped_min": min(scraped) if scraped else "",
        "scraped_max": max(scraped) if scraped else "",
        "with_salary": sum(1 for j in jobs if j["salary_num"] is not None),
        "unknown_date": sum(1 for j in jobs if j["age_days"] is None),
        "scraped_recent_7": sum(1 for j in jobs
                                if j["scraped_days"] is not None and j["scraped_days"] <= 7),
        "source_label": SOURCE_LABEL,
    }
    return jobs, meta


# ---------------- HTML ----------------
def _json_safely(obj) -> str:
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return s.replace("</", "<\\/").replace("<!--", "<\\!--")


HTML = r"""<!DOCTYPE html>
<html lang="zh-HK" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>香港求職聚合台 · hk-job-scraper</title>
<style>
  :root[data-theme="dark"]{
    --bg:#0e1420; --panel:#151d2c; --panel2:#1b2536; --line:#26324a;
    --ink:#e8eef7; --muted:#93a3bd; --accent:#5aa9ff; --accent2:#7ee0c0;
    --chip:#223049; --chipOn:#2f6fd0; --warn:#f0b429; --shadow:0 6px 24px rgba(0,0,0,.35);
  }
  :root[data-theme="light"]{
    --bg:#f4f7fb; --panel:#ffffff; --panel2:#f8fafd; --line:#e2e9f3;
    --ink:#1f2d3d; --muted:#6b7a90; --accent:#0b6bcb; --accent2:#12a37a;
    --chip:#eaf1fb; --chipOn:#0b6bcb; --warn:#b7791f; --shadow:0 6px 24px rgba(20,40,80,.08);
  }
  :root{--fs:16px;--fs-sm:15px}
  :root[data-font="large"]{--fs:20px;--fs-sm:18px}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font-family:"PingFang HK","Microsoft JhengHei",system-ui,-apple-system,sans-serif;
       font-size:var(--fs);line-height:1.65;overflow-wrap:anywhere}
  a{color:var(--accent);text-decoration:none}
  a:hover{text-decoration:underline}
  :focus-visible{outline:3px solid var(--accent);outline-offset:2px}
  .skip{position:absolute;left:-9999px;top:0;background:var(--panel);color:var(--ink);
        padding:10px 16px;border:2px solid var(--accent);z-index:10}
  .skip:focus{left:8px;top:8px}
  .sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;
           overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
  .wrap{max-width:1180px;margin:0 auto;padding:22px 20px 60px}
  header{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;justify-content:space-between;margin-bottom:16px}
  h1{margin:0;font-size:calc(var(--fs) * 1.45);letter-spacing:.5px}
  .sub{color:var(--muted);font-size:var(--fs-sm)}
  .btn{background:var(--panel2);border:1px solid var(--line);color:var(--ink);
       border-radius:9px;padding:7px 13px;font-size:var(--fs-sm);font-family:inherit;cursor:pointer}
  .btn:hover{border-color:var(--accent)}
  .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-bottom:14px}
  .stat{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:13px 15px;box-shadow:var(--shadow)}
  .stat b{display:block;font-size:calc(var(--fs) * 1.4);line-height:1.25}
  .stat span{color:var(--muted);font-size:var(--fs-sm)}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:14px 16px;margin-bottom:14px;box-shadow:var(--shadow)}
  .panel h3{margin:0 0 10px;font-size:var(--fs-sm);color:var(--muted);font-weight:600;letter-spacing:.4px}
  .bars{display:flex;flex-direction:column;gap:7px}
  .barrow{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  .barname{width:auto;min-width:96px;max-width:38%;font-size:var(--fs-sm);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .barbg{flex:1;min-width:80px;background:var(--panel2);border-radius:7px;height:22px;overflow:hidden}
  .bar{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:7px}
  .barval{width:auto;min-width:58px;text-align:right;font-size:var(--fs-sm);color:var(--muted)}
  .ctrl{display:flex;flex-wrap:wrap;gap:9px;align-items:center}
  .ctrl input[type=search],.ctrl select{flex:1;min-width:170px;background:var(--panel2);
       border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:9px 11px;
       font-size:var(--fs);font-family:inherit}
  .ctrl input[type=search]:focus,.ctrl select:focus{outline:3px solid var(--accent);outline-offset:1px}
  .chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}
  .chip{background:var(--chip);border:1px solid var(--line);color:var(--ink);font-family:inherit;
        border-radius:999px;padding:5px 12px;font-size:var(--fs-sm);cursor:pointer;user-select:none}
  .chip:hover{border-color:var(--accent)}
  .chip.on{background:var(--chipOn);border-color:var(--chipOn);color:#fff}
  .chip .n{opacity:.8;font-size:var(--fs-sm);margin-left:4px}
  label.cb{display:inline-flex;align-items:center;gap:6px;font-size:var(--fs-sm);color:var(--muted);cursor:pointer}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:13px;
        padding:13px 15px;margin-bottom:9px;box-shadow:var(--shadow)}
  .card:hover{border-color:var(--accent)}
  .row1{display:flex;gap:9px;align-items:baseline;flex-wrap:wrap}
  .ttl{margin:0;font-size:calc(var(--fs) * 1.08);font-weight:600;flex:1;min-width:200px}
  .badge{font-size:var(--fs-sm);padding:2px 8px;border-radius:999px;border:1px solid var(--line);
         background:var(--panel2);color:var(--muted);white-space:nowrap}
  .badge.moovup{color:#ffb86c;border-color:#ffb86c55}
  .badge.gov_hk{color:#8be9a8;border-color:#8be9a855}
  .badge.jobsdb{color:#7cc4ff;border-color:#7cc4ff55}
  .badge.linkedin{color:#9db4ff;border-color:#9db4ff55}
  .badge.indeed{color:#c8a2ff;border-color:#c8a2ff55}
  .row2{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:var(--fs-sm);margin-top:5px}
  .age{color:var(--accent2);font-weight:600}
  .sal{color:var(--warn);font-weight:600}
  .desc{margin-top:8px;color:var(--muted);font-size:var(--fs-sm);white-space:pre-wrap;
        display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .desc.open{display:block;-webkit-line-clamp:unset}
  .more{margin-top:5px;font-size:var(--fs-sm);font-family:inherit;color:var(--accent);
        cursor:pointer;background:none;border:none;padding:0}
  .empty{text-align:center;color:var(--muted);padding:40px 0;font-size:var(--fs)}
  .empty code{display:inline-block;margin:8px 0;padding:4px 8px;border-radius:6px;
              background:var(--panel2);color:var(--ink);font-size:.95em;
              overflow-wrap:anywhere;text-align:left}
  #loadMore{width:100%;margin-top:12px}
  footer{color:var(--muted);font-size:var(--fs-sm);text-align:center;margin-top:22px;line-height:1.9}
  :root[data-font="large"] .barname{max-width:45%}
  :root[data-font="large"] .ctrl input[type=search],
  :root[data-font="large"] .ctrl select{min-width:220px}
  @media(max-width:640px){.barname{min-width:72px;max-width:42%}.wrap{padding:16px 12px 40px}}
</style>
</head>
<body>
<a class="skip" href="#main">跳至主要內容</a>
<main class="wrap" id="main">
  <header>
    <div>
      <h1>🛰️ 香港求職聚合台</h1>
      <div class="sub" id="sub"></div>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn" id="fontBtn" aria-pressed="false">A+ 大字模式</button>
      <button class="btn" id="themeBtn">🌗 主題</button>
      <button class="btn" id="topBtn">↑ 回頂部</button>
    </div>
  </header>

  <div class="stats" id="stats"></div>

  <div class="panel">
    <h3>據點分佈</h3>
    <div class="bars" id="srcBars"></div>
  </div>

  <div class="panel">
    <h3>熱門地區 TOP 10</h3>
    <div class="bars" id="locBars"></div>
  </div>

  <section class="panel" aria-label="篩選條件">
    <h2 class="sr-only">篩選條件</h2>
    <div class="ctrl">
      <label class="sr-only" for="q">搜尋職位、公司、地區或描述</label>
      <input type="search" id="q" placeholder="🔍 搜尋職位 / 公司 / 地區 / 描述 / 行業…">
      <label class="sr-only" for="daysSel">刊登時間</label>
      <select id="daysSel">
        <option value="0">不限刊登時間</option>
        <option value="3">3 天內</option>
        <option value="7">7 天內</option>
        <option value="14">14 天內</option>
        <option value="30">30 天內</option>
        <option value="90">90 天內</option>
      </select>
      <label class="sr-only" for="locSel">地區</label>
      <select id="locSel"><option value="">全部地區</option></select>
      <label class="sr-only" for="sortSel">排序方式</label>
      <select id="sortSel">
        <option value="new">最新優先</option>
        <option value="old">最舊優先</option>
        <option value="sal">薪資高→低</option>
        <option value="src">依來源</option>
        <option value="ttl">依職位名</option>
      </select>
      <label class="cb"><input type="checkbox" id="salOnly"> 只看有薪資</label>
    </div>
    <div class="chips" id="srcChips" role="group" aria-label="依來源篩選"></div>
    <div class="sub" style="margin-top:9px" id="count" role="status" aria-live="polite"></div>
  </section>

  <div id="list" role="list" aria-label="職位清單"></div>
  <button class="btn" id="loadMore" aria-controls="list">載入更多</button>

  <footer id="foot"></footer>
</main>

<script>
window.JOBS = __DATA__;
window.META = __META__;

const JOBS = window.JOBS, META = window.META, LABEL = META.source_label || {};
// 兩種「空」不同：完全沒資料要教人先抓；有資料但被篩選濾光才維持舊提示。
const EMPTY_DATA_HTML = __EMPTY_DATA__;
const EMPTY_FILTER_HTML = __EMPTY_FILTER__;
const PAGE = 40;
let shown = PAGE, activeSrc = new Set();

const $ = id => document.getElementById(id);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const ageTxt = j => j.age_days === null ? "日期未知"
  : (j.age_days === 0 ? "今天" : j.age_days + " 天前");
// 原始薪資字串常已含「per month / 月薪 / hour」，別再補一次單位
const salTxt = j => !j.salary ? "" :
  (j.salary + (j.salary_unit && !/(月|month|年|year|annum|小時|hour|hr|\/h)/i.test(j.salary)
    ? "（" + j.salary_unit + "）" : ""));
// 刊登日為主；列表層抓取常無刊登日，退而顯示「抓取於 N 天前」作為參考座標
const ageHtml = j => j.age_days === null
  ? `未知刊登日${j.scraped_days === null ? "" : `（抓取於 ${j.scraped_days} 天前）`}`
  : `${ageTxt(j)}${j.posted_date ? "（" + esc(j.posted_date) + "）" : ""}`;

function initStats(){
  $("sub").textContent = `${Object.keys(META.per_source).length} 站聚合 · 共 ${META.total} 筆職位 · 來自 ${META.files_used} 個輸出檔`
    + (META.scraped_min ? ` · 抓取期間 ${META.scraped_min} ~ ${META.scraped_max}` : "")
    + ` · 生成於 ${META.generated_at}`;
  $("stats").innerHTML = [
    ["總職位（去重後）", META.total],
    ["有標示薪資", META.with_salary],
    ["據點數", Object.keys(META.per_source).length],
    ["近 7 天內抓取", META.scraped_recent_7],
  ].map(([k,v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join("");

  // 據點分佈
  const srcs = Object.entries(META.per_source).sort((a,b) => b[1]-a[1]);
  const maxS = Math.max(1, ...srcs.map(s => s[1]));
  $("srcBars").innerHTML = srcs.map(([k,v]) =>
    `<div class="barrow"><div class="barname">${esc(LABEL[k]||k)}</div>
     <div class="barbg"><div class="bar" style="width:${(v/maxS*100).toFixed(1)}%"></div></div>
     <div class="barval">${v} 筆</div></div>`).join("");

  // 地區 TOP10
  const cnt = {};
  JOBS.forEach(j => { const k = (j.location||"").trim(); if(k) cnt[k] = (cnt[k]||0)+1; });
  const top = Object.entries(cnt).sort((a,b) => b[1]-a[1]).slice(0,10);
  const maxL = Math.max(1, ...top.map(t => t[1]));
  $("locBars").innerHTML = top.length ? top.map(([k,v]) =>
    `<div class="barrow"><div class="barname" title="${esc(k)}">${esc(k)}</div>
     <div class="barbg"><div class="bar" style="width:${(v/maxL*100).toFixed(1)}%"></div></div>
     <div class="barval">${v} 筆</div></div>`).join("") : '<div class="sub">無地區資料</div>';

  // 來源 chips 用 button（不是 span），鍵盤 Tab 可達、螢幕報讀器可讀狀態
  $("srcChips").innerHTML = srcs.map(([k,v]) =>
    `<button type="button" class="chip" data-src="${esc(k)}" aria-pressed="false">${esc(LABEL[k]||k)}<span class="n">${v}</span></button>`).join("");
  $("srcChips").querySelectorAll(".chip").forEach(c => c.onclick = () => {
    const s = c.dataset.src;
    const on = !activeSrc.has(s);
    if (on) activeSrc.add(s); else activeSrc.delete(s);
    c.classList.toggle("on", on);
    c.setAttribute("aria-pressed", String(on));
    shown = PAGE; render();
  });

  // 地區下拉
  const locs = Object.keys(cnt).sort((a,b) => cnt[b]-cnt[a]);
  $("locSel").innerHTML = '<option value="">全部地區</option>' +
    locs.map(l => `<option value="${esc(l)}">${esc(l)}（${cnt[l]}）</option>`).join("");

  $("foot").innerHTML = `hk-job-scraper · 聚合 ${META.raw_rows} 筆原始列 → 去重後 ${META.total} 筆`
    + (META.files_skipped && META.files_skipped.length
        ? `<br>已略過（非職位檔或無法讀取）：${META.files_skipped.map(esc).join("、")}` : "")
    + `<br>其中 ${META.unknown_date} 筆無刊登日（列表層抓取所致），套用時間篩選時會被排除；`
    + `想補齊日期可對該站重跑並加上 <code>--detail</code>。`
    + `<br>刊登天數以該筆的抓取時間為基準，舊存檔不會越算越舊。`
    + `<br>爬完新資料後重新產生：<code>python build_dashboard.py</code>`;
}

function filtered(){
  const q = $("q").value.trim().toLowerCase();
  const days = +$("daysSel").value;
  const loc = $("locSel").value;
  const salOnly = $("salOnly").checked;
  const sort = $("sortSel").value;
  let out = JOBS.filter(j => {
    if (activeSrc.size && !activeSrc.has(j.source)) return false;
    if (loc && (j.location||"") !== loc) return false;
    if (salOnly && !j.salary_num) return false;
    if (days) { if (j.age_days === null || j.age_days > days) return false; }
    if (q) {
      const hay = [j.title, j.company, j.location, j.description, j.industry,
                   j.job_type, j.requirements].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  const cmp = {
    new: (a,b) => (a.age_days ?? 1e9) - (b.age_days ?? 1e9),
    old: (a,b) => (b.age_days ?? -1) - (a.age_days ?? -1),
    sal: (a,b) => (b.salary_num || 0) - (a.salary_num || 0),
    src: (a,b) => (a.source||"").localeCompare(b.source||"") || (a.age_days ?? 1e9) - (b.age_days ?? 1e9),
    ttl: (a,b) => (a.title||"").localeCompare(b.title||"", "zh-Hant"),
  }[sort];
  return out.sort(cmp);
}

function cardHtml(j){
  const d = j.description || "";
  return `<article class="card" role="listitem">
    <div class="row1">
      <h3 class="ttl">${j.url ? `<a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.title||"(無職稱)")}</a>`
                                : esc(j.title||"(無職稱)")}</h3>
      <span class="badge ${esc(j.source)}">${esc(LABEL[j.source]||j.source)}</span>
    </div>
    <div class="row2">
      ${j.company ? `<span>🏢 ${esc(j.company)}</span>` : ""}
      ${j.location ? `<span>📍 ${esc(j.location)}</span>` : ""}
      ${j.salary ? `<span class="sal">💰 ${esc(salTxt(j))}</span>` : ""}
      <span class="age">🕒 ${ageHtml(j)}</span>
      ${j.job_type ? `<span>型態 ${esc(j.job_type)}</span>` : ""}
      ${j.industry ? `<span>行業 ${esc(j.industry)}</span>` : ""}
      <span style="opacity:.55">${esc(j.file||"")}</span>
    </div>
    ${d ? `<div class="desc">${esc(d)}</div><button type="button" class="more" aria-expanded="false">展開全文 ▾</button>` : ""}
    ${j.requirements ? `<div class="desc" style="display:none">要求：${esc(j.requirements)}</div>` : ""}
  </article>`;
}

function render(){
  const out = filtered();
  $("count").textContent = `符合條件 ${out.length} 筆（顯示 ${Math.min(shown, out.length)} 筆）`;
  const slice = out.slice(0, shown);
  $("list").innerHTML = out.length ? slice.map(cardHtml).join("") :
    (JOBS.length === 0 ? EMPTY_DATA_HTML : EMPTY_FILTER_HTML);
  $("list").querySelectorAll(".more").forEach(b => b.onclick = () => {
    const d = b.previousElementSibling;
    const open = d.classList.toggle("open");
    b.setAttribute("aria-expanded", String(open));
    b.textContent = open ? "收合 ▴" : "展開全文 ▾";
  });
  $("loadMore").style.display = shown < out.length ? "block" : "none";
  $("loadMore").textContent = `載入更多（尚有 ${out.length - shown} 筆）`;
}

["q","daysSel","locSel","sortSel","salOnly"].forEach(id => {
  const el = $(id);
  el.addEventListener(id === "q" ? "input" : "change", () => { shown = PAGE; render(); });
});
$("loadMore").onclick = () => { shown += PAGE; render(); };
$("themeBtn").onclick = () => {
  const r = document.documentElement;
  r.dataset.theme = r.dataset.theme === "dark" ? "light" : "dark";
};
$("fontBtn").onclick = () => {
  const r = document.documentElement, b = $("fontBtn");
  const big = r.dataset.font !== "large";
  r.dataset.font = big ? "large" : "normal";
  b.setAttribute("aria-pressed", String(big));
  b.textContent = big ? "A- 標準字級" : "A+ 大字模式";
};
$("topBtn").onclick = () => window.scrollTo({top:0, behavior:"smooth"});

initStats();
render();
</script>
</body>
</html>
"""


EMPTY_DATA_COMMAND = ("python -m hkjobs search --source gov_hk --pages 1 "
                      "--keyword 文員 --out output/文員.json")
EMPTY_DATA_HINT = (
    "output/ 目前沒有職位資料。請先執行 <code>" + EMPTY_DATA_COMMAND
    + "</code>，再重新產生看板。"
)
EMPTY_FILTER_HINT = "🫧 沒有符合條件的職位，試著放寬篩選"


def build_html(jobs: list[dict], meta: dict) -> str:
    """只注入用得到的空狀態訊息：0 檔 HTML 不會出現「放寬篩選」。"""
    empty_data = (f'<div class="empty">{EMPTY_DATA_HINT}</div>'
                  if not jobs else "")
    empty_filter = (f'<div class="empty">{EMPTY_FILTER_HINT}</div>'
                    if jobs else "")
    return (HTML
            .replace("__EMPTY_DATA__", _json_safely(empty_data))
            .replace("__EMPTY_FILTER__", _json_safely(empty_filter))
            .replace("__DATA__", _json_safely(jobs))
            .replace("__META__", _json_safely(meta)))


def _resolve_out(value: str) -> Path:
    """純檔名維持既有契約（放在 output/ 下）；含目錄或絕對路徑時照使用者給的用。

    舊版一律 `OUTPUT_DIR / value`，`--out output/x.html` 會變成
    `output/output/x.html` 後直接 FileNotFoundError traceback。
    """
    path = Path(value)
    if path.is_absolute() or len(path.parts) > 1:
        return path
    return OUTPUT_DIR / path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="聚合 output/ 職位資料 → 單檔 HTML 儀表板")
    ap.add_argument("--glob", action="append", default=None,
                    help="輸入檔 glob（可重複）；預設 output/*.json 與 output/*.csv")
    ap.add_argument("--out", default="dashboard.html",
                    help="輸出檔：純檔名放在 output/ 下；含目錄或絕對路徑則直接寫到該處")
    args = ap.parse_args(argv)

    patterns = args.glob or [str(OUTPUT_DIR / "*.json"), str(OUTPUT_DIR / "*.csv")]
    print(f"掃描來源：{patterns}")
    jobs, meta = collect(patterns)
    print(f"原始列 {meta['raw_rows']} 筆 → 去重後 {meta['total']} 筆"
          f"（{meta['files_used']} 個檔案）")
    print(f"據點分佈：{meta['per_source']}")
    if meta["files_skipped"]:
        print(f"已略過（非職位檔或無法讀取）：{', '.join(meta['files_skipped'])}")
    if meta["total"] == 0:
        print("提醒：目前沒有讀到任何職位資料，產生的會是空看板。")
        print(f"  請先執行 {EMPTY_DATA_COMMAND}，再重新產生看板。")

    out_path = _resolve_out(args.out)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(build_html(jobs, meta), encoding="utf-8")
    except OSError as e:
        print(f"無法寫入 {out_path}：{e}", file=sys.stderr)
        print("請確認路徑與權限；純檔名會寫到 output/ 下。", file=sys.stderr)
        return 2
    size_kb = out_path.stat().st_size / 1024
    print(f"已產生 {out_path}（{size_kb:.0f} KB）— 直接雙擊即可開啟")
    return 0


if __name__ == "__main__":
    sys.exit(main())
