"""LinkedIn 訪客分頁端點探針（🐢 一次一支，手動指定 start）。

假說：訪客模式下 /jobs/search/?start=N 不穩定（隨機化/AB），
但 /jobs-guest/jobs/api/seeMoreJobPostings/search 是訪客專用分頁端點，
翻頁應更可靠。本腳本逐支驗證：指定 start，回傳卡片數與去重後的新增數。

用法：python tools/_probe_li_guest.py 0
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROBE = Path(__file__).resolve().parents[1] / "output" / "_probe"
PROBE.mkdir(parents=True, exist_ok=True)

GUEST = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch(start: int, keyword: str = "", location: str = "Hong Kong",
          f_tpr: str = "") -> str:
    params = {"keywords": keyword, "location": location, "start": str(start)}
    if f_tpr:
        params["f_TPR"] = f_tpr
    r = requests.get(GUEST, params=params, headers=HEADERS, timeout=30)
    print(f"[{start}] HTTP {r.status_code} | {len(r.text)} bytes | {r.url}")
    out = PROBE / f"_li_guest_s{start}.html"
    out.write_text(r.text, encoding="utf-8")
    print(f"       saved -> {out}")
    return r.text if r.status_code == 200 else ""


def cards(html: str):
    soup = BeautifulSoup(html, "lxml")
    items = []
    for li in soup.select("li"):
        link = li.select_one("a.base-card__full-link")
        if not link:
            continue
        href = link.get("href") or ""
        m = re.search(r"/jobs/view/.*-(\d+)", href)
        if not m:
            continue
        t = li.select_one(".base-search-card__title")
        c = li.select_one(".base-search-card__subtitle")
        loc = li.select_one(".job-search-card__location")
        tm = li.select_one("time")
        items.append({
            "id": m.group(1),
            "title": t.get_text(strip=True) if t else "",
            "company": c.get_text(strip=True) if c else "",
            "location": loc.get_text(strip=True) if loc else "",
            "posted": (tm.get("datetime") or tm.get_text(strip=True)) if tm else "",
        })
    return items


if __name__ == "__main__":
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    kw = sys.argv[2] if len(sys.argv) > 2 else ""
    f_tpr = sys.argv[3] if len(sys.argv) > 3 else ""
    loc = sys.argv[4] if len(sys.argv) > 4 else "Hong Kong"
    html = fetch(start, kw, loc, f_tpr)
    if html:
        items = cards(html)
        print(f"[{start}] 卡片數 {len(items)}")
        for it in items[:5]:
            print("   ", it["id"], "|", it["title"][:40], "|", it["company"][:28],
                  "|", it["location"], "|", it["posted"])
        ids = [i["id"] for i in items]
        print(f"[{start}] ids={ids}")
        (PROBE / f"_li_guest_s{start}.ids.txt").write_text("\n".join(ids), encoding="utf-8")
