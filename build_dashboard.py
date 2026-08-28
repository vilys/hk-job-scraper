"""聚合 output/ 內所有爬蟲產出 → 單檔離線 HTML 儀表板。

用法：
    python build_dashboard.py                       # 掃 output/，產生 output/dashboard.html
    python build_dashboard.py --out 我的看板.html     # 自訂檔名
    python build_dashboard.py --glob "output/*.json" # 只吃 JSON（不吃 CSV）

設計要點：
- 資料**內嵌**進 HTML（不用 fetch），因此產出的 html 直接雙擊就能開（file:// 下
  瀏覽器會擋 fetch 外部 JSON，內嵌可避開這個坑）。
- 容錯讀取：CSV 可能是 UTF-8 / UTF-8-BOM / Big5(cp950) / GB18030，逐個嘗試。
- 自動跳過非職位檔（如 ict_density_leaderboard.json 是地區統計，不是職位陣列）。
- 依 job_id 去重（多檔重複匯出同一職位時，保留描述較完整 / 抓取較新的一筆）。
- 正規化刊登日：五站格式各異（"23h ago" / "10/07/2026" / "2 days ago" / "7日前"），
  統一折算成 age_days（距今天數）以便篩選與排序。
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
}

# CSV 讀取時的編碼候選（含香港常見的 Big5 / GB18030）
_ENCODINGS = ("utf-8-sig", "utf-8", "cp950", "big5hkscs", "gb18030", "latin-1")


# ---------------- 讀檔 ----------------
def _read_json_jobs(path: str) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        print(f"  ! 略過（JSON 讀取失敗）{os.path.basename(path)}：{e}")
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
_REL_EN = re.compile(r"(\d+)\s*(hour|hr|h|day|d|week|w|month|mo|year|y)s?", re.I)
_REL_CN = re.compile(r"(\d+)\s*(小時|時|天|日|週|周|星期|個月|月|年)")
_UNIT_DAYS_EN = {"hour": 0, "hr": 0, "h": 0, "day": 1, "d": 1, "week": 7, "w": 7,
                 "month": 30, "mo": 30, "year": 365, "y": 365}
_UNIT_DAYS_CN = {"小時": 0, "時": 0, "天": 1, "日": 1, "週": 7, "周": 7,
                 "星期": 7, "個月": 30, "月": 30, "年": 365}


def parse_age_days(rec: dict) -> int | None:
    """把各站刊登日折算成「距今天數」。無法判定回 None。

    支援（實測樣本）：
      JobsDB  "23h ago" / "1d ago" / "3d ago"
      Indeed  "11 day ago" / "2 day ago"
      LinkedIn "2 days ago" / "23 hours ago" / "1 day ago"
      Moovup  "7日前" / "2個月前"（中文）
      勞工處  "10/07/2026"（DD/MM/YYYY）
      其他    ISO 日期 / 時間戳
    """
    s = (rec.get("posted_date") or "").strip()
    if not s:
        return None
    low = s.lower()
    if "just now" in low or "剛剛" in low or low in ("now", "today", "今天"):
        return 0
    if "30d+" in low:
        return 30

    # 英文相對時間
    m = _REL_EN.search(low)
    if m:
        mult = _UNIT_DAYS_EN.get(m.group(2))
        if mult is None:
            return None
        n = int(m.group(1))
        return 0 if mult == 0 else n * mult

    # 中文相對時間
    m = _REL_CN.search(s)
    if m:
        mult = _UNIT_DAYS_CN.get(m.group(2))
        if mult is None:
            return None
        n = int(m.group(1))
        return 0 if mult == 0 else n * mult

    # 西式日期 DD/MM/YYYY（勞工處）
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            return max(0, (date.today() - d).days)
        except ValueError:
            return None

    # ISO 日期 / 時間戳
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            d = date.fromisoformat(m.group(0))
            return max(0, (date.today() - d).days)
        except ValueError:
            return None
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
        "posted_date": (rec.get("posted_date") or "").strip(),
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
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font-family:"PingFang HK","Microsoft JhengHei",system-ui,-apple-system,sans-serif;
       font-size:14px;line-height:1.6}
  a{color:var(--accent);text-decoration:none}
  a:hover{text-decoration:underline}
  .wrap{max-width:1180px;margin:0 auto;padding:22px 20px 60px}
  header{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;justify-content:space-between;margin-bottom:16px}
  h1{margin:0;font-size:23px;letter-spacing:.5px}
  .sub{color:var(--muted);font-size:12.5px}
  .btn{background:var(--panel2);border:1px solid var(--line);color:var(--ink);
       border-radius:9px;padding:7px 13px;font-size:12.5px;cursor:pointer}
  .btn:hover{border-color:var(--accent)}
  .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
  .stat{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:13px 15px;box-shadow:var(--shadow)}
  .stat b{display:block;font-size:22px;line-height:1.25}
  .stat span{color:var(--muted);font-size:11.5px}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:14px 16px;margin-bottom:14px;box-shadow:var(--shadow)}
  .panel h3{margin:0 0 10px;font-size:13px;color:var(--muted);font-weight:600;letter-spacing:.4px}
  .bars{display:flex;flex-direction:column;gap:7px}
  .barrow{display:flex;align-items:center;gap:10px}
  .barname{width:96px;font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .barbg{flex:1;background:var(--panel2);border-radius:7px;height:22px;overflow:hidden}
  .bar{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:7px}
  .barval{width:58px;text-align:right;font-size:12px;color:var(--muted)}
  .ctrl{display:flex;flex-wrap:wrap;gap:9px;align-items:center}
  .ctrl input[type=search],.ctrl select{flex:1;min-width:150px;background:var(--panel2);
       border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:9px 11px;font-size:13px}
  .ctrl input[type=search]:focus,.ctrl select:focus{outline:none;border-color:var(--accent)}
  .chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}
  .chip{background:var(--chip);border:1px solid var(--line);color:var(--ink);
        border-radius:999px;padding:5px 12px;font-size:12.5px;cursor:pointer;user-select:none}
  .chip.on{background:var(--chipOn);border-color:var(--chipOn);color:#fff}
  .chip .n{opacity:.7;font-size:11px;margin-left:4px}
  label.cb{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--muted);cursor:pointer}
  table{width:100%;border-collapse:collapse}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:13px;
        padding:13px 15px;margin-bottom:9px;box-shadow:var(--shadow)}
  .card:hover{border-color:var(--accent)}
  .row1{display:flex;gap:9px;align-items:baseline;flex-wrap:wrap}
  .ttl{font-size:15px;font-weight:600;flex:1;min-width:200px}
  .badge{font-size:10.5px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);
         background:var(--panel2);color:var(--muted);white-space:nowrap}
  .badge.moovup{color:#ffb86c;border-color:#ffb86c55}
  .badge.gov_hk{color:#8be9a8;border-color:#8be9a855}
  .badge.jobsdb{color:#7cc4ff;border-color:#7cc4ff55}
  .badge.linkedin{color:#9db4ff;border-color:#9db4ff55}
  .badge.indeed{color:#c8a2ff;border-color:#c8a2ff55}
  .row2{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:12.5px;margin-top:5px}
  .age{color:var(--accent2);font-weight:600}
  .sal{color:var(--warn);font-weight:600}
  .desc{margin-top:8px;color:var(--muted);font-size:12.5px;white-space:pre-wrap;
        display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .desc.open{display:block;-webkit-line-clamp:unset}
  .more{margin-top:5px;font-size:12px;color:var(--accent);cursor:pointer;background:none;border:none;padding:0}
  .empty{text-align:center;color:var(--muted);padding:40px 0}
  #loadMore{width:100%;margin-top:12px}
  footer{color:var(--muted);font-size:11.5px;text-align:center;margin-top:22px;line-height:1.9}
  @media(max-width:640px){.barname{width:72px}.wrap{padding:16px 12px 40px}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>🛰️ 香港求職聚合台</h1>
      <div class="sub" id="sub"></div>
    </div>
    <div style="display:flex;gap:8px">
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

  <div class="panel">
    <div class="ctrl">
      <input type="search" id="q" placeholder="🔍 搜尋職位 / 公司 / 地區 / 描述 / 行業…">
      <select id="daysSel">
        <option value="0">不限刊登時間</option>
        <option value="3">3 天內</option>
        <option value="7">7 天內</option>
        <option value="14">14 天內</option>
        <option value="30">30 天內</option>
        <option value="90">90 天內</option>
      </select>
      <select id="locSel"><option value="">全部地區</option></select>
      <select id="sortSel">
        <option value="new">最新優先</option>
        <option value="old">最舊優先</option>
        <option value="sal">薪資高→低</option>
        <option value="src">依來源</option>
        <option value="ttl">依職位名</option>
      </select>
      <label class="cb"><input type="checkbox" id="salOnly"> 只看有薪資</label>
    </div>
    <div class="chips" id="srcChips"></div>
    <div class="sub" style="margin-top:9px" id="count"></div>
  </div>

  <div id="list"></div>
  <button class="btn" id="loadMore">載入更多</button>

  <footer id="foot"></footer>
</div>

<script>
window.JOBS = __DATA__;
window.META = __META__;

const JOBS = window.JOBS, META = window.META, LABEL = META.source_label || {};
const PAGE = 40;
let shown = PAGE, activeSrc = new Set();

const $ = id => document.getElementById(id);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const ageTxt = j => j.age_days === null ? "日期未知"
  : (j.age_days === 0 ? "今天" : j.age_days + " 天前");
const salTxt = j => !j.salary ? "" :
  (j.salary + (j.salary_unit ? "（" + j.salary_unit + "）" : ""));
// 刊登日為主；列表層抓取常無刊登日，退而顯示「抓取於 N 天前」作為參考座標
const ageHtml = j => j.age_days === null
  ? `未知刊登日${j.scraped_days === null ? "" : `（抓取於 ${j.scraped_days} 天前）`}`
  : `${ageTxt(j)}${j.posted_date ? "（" + esc(j.posted_date) + "）" : ""}`;

function initStats(){
  $("sub").textContent = `五站聚合 · 共 ${META.total} 筆職位 · 來自 ${META.files_used} 個輸出檔`
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

  // 來源 chips
  $("srcChips").innerHTML = srcs.map(([k,v]) =>
    `<span class="chip" data-src="${esc(k)}">${esc(LABEL[k]||k)}<span class="n">${v}</span></span>`).join("");
  $("srcChips").querySelectorAll(".chip").forEach(c => c.onclick = () => {
    const s = c.dataset.src;
    if (activeSrc.has(s)) { activeSrc.delete(s); c.classList.remove("on"); }
    else { activeSrc.add(s); c.classList.add("on"); }
    shown = PAGE; render();
  });

  // 地區下拉
  const locs = Object.keys(cnt).sort((a,b) => cnt[b]-cnt[a]);
  $("locSel").innerHTML = '<option value="">全部地區</option>' +
    locs.map(l => `<option value="${esc(l)}">${esc(l)}（${cnt[l]}）</option>`).join("");

  $("foot").innerHTML = `hk-job-scraper · 聚合 ${META.raw_rows} 筆原始列 → 去重後 ${META.total} 筆`
    + (META.files_skipped && META.files_skipped.length
        ? `<br>已略過非職位檔：${META.files_skipped.map(esc).join("、")}` : "")
    + `<br>其中 ${META.unknown_date} 筆無刊登日（列表層抓取所致），套用時間篩選時會被排除；`
    + `想補齊日期可對該站重跑並加上 <code>--detail</code>。`
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
  return `<div class="card">
    <div class="row1">
      <span class="ttl">${j.url ? `<a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.title||"(無職稱)")}</a>`
                                : esc(j.title||"(無職稱)")}</span>
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
    ${d ? `<div class="desc">${esc(d)}</div><button class="more">展開全文 ▾</button>` : ""}
    ${j.requirements ? `<div class="desc" style="display:none">要求：${esc(j.requirements)}</div>` : ""}
  </div>`;
}

function render(){
  const out = filtered();
  $("count").textContent = `符合條件 ${out.length} 筆（顯示 ${Math.min(shown, out.length)} 筆）`;
  const slice = out.slice(0, shown);
  $("list").innerHTML = out.length ? slice.map(cardHtml).join("") :
    '<div class="empty">🫧 沒有符合條件的職位，試著放寬篩選</div>';
  $("list").querySelectorAll(".more").forEach(b => b.onclick = () => {
    const d = b.previousElementSibling;
    const open = d.classList.toggle("open");
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
$("topBtn").onclick = () => window.scrollTo({top:0, behavior:"smooth"});

initStats();
render();
</script>
</body>
</html>
"""


def build_html(jobs: list[dict], meta: dict) -> str:
    return (HTML
            .replace("__DATA__", _json_safely(jobs))
            .replace("__META__", _json_safely(meta)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="聚合 output/ 職位資料 → 單檔 HTML 儀表板")
    ap.add_argument("--glob", action="append", default=None,
                    help="輸入檔 glob（可重複）；預設 output/*.json 與 output/*.csv")
    ap.add_argument("--out", default="dashboard.html", help="輸出檔名（放在 output/ 下）")
    args = ap.parse_args(argv)

    patterns = args.glob or [str(OUTPUT_DIR / "*.json"), str(OUTPUT_DIR / "*.csv")]
    print(f"掃描來源：{patterns}")
    jobs, meta = collect(patterns)
    print(f"原始列 {meta['raw_rows']} 筆 → 去重後 {meta['total']} 筆"
          f"（{meta['files_used']} 個檔案）")
    print(f"據點分佈：{meta['per_source']}")
    if meta["files_skipped"]:
        print(f"已略過非職位檔：{', '.join(meta['files_skipped'])}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / args.out
    out_path.write_text(build_html(jobs, meta), encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"✅ 已產生 {out_path}（{size_kb:.0f} KB）— 直接雙擊即可開啟")
    return 0


if __name__ == "__main__":
    sys.exit(main())
