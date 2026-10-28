# -*- coding: utf-8 -*-
"""OfferToday 冷請求探針（免瀏覽器、免 cookie）。

用法（請在專案根目錄執行）：python tools/probe_ot_cold.py <label> '<json override>' [<label2> '<json2>' ...]
每支請求間隔 GAP 秒，不重試、不併發。
🛑 安全閥：HTTP != 200 / code != 0 / 驗證碼徵兆 → 立即停手。
"""
import sys, json, time
sys.stdout.reconfigure(encoding="utf-8")
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
URL = "https://www.offertoday.com/wapi/geek/recommend/search/list"
GAP = 8

BASE = {"keyword": "", "page": 1, "pageSize": 10, "salaryType": 0,
        "publishTime": "", "employmentTypes": [], "experiences": [],
        "educationLevels": [], "benefits": [], "workPermits": [],
        "rcdType": 7, "jobFunctionCodes": [], "industries": [],
        "subDistrictCodes": [], "searchSource": None}

HDRS = {"Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": UA,
        "Origin": "https://www.offertoday.com",
        "Referer": "https://www.offertoday.com/hk/search"}


def one(label, override):
    payload = dict(BASE)
    payload.update(override)
    try:
        r = requests.post(URL, json=payload, headers=HDRS, timeout=30)
    except Exception as e:
        print(f"[{label}] 🛑 連線例外：{e}")
        return False
    body = r.text
    open(f"output/_ot_r9_{label}.json", "w", encoding="utf-8").write(body)
    if r.status_code != 200 or any(k in body[:400] for k in ("驗證碼", "验证", "captcha")):
        print(f"[{label}] 🛑 HTTP {r.status_code} → 停手：{body[:200]}")
        return False
    try:
        d = json.loads(body)
    except Exception:
        print(f"[{label}] 🛑 非 JSON → 停手")
        return False
    if d.get("code") != 0:
        print(f"[{label}] 🛑 code={d.get('code')} → 停手")
        return False

    data = d.get("data") or {}
    lst = data.get("resultList") or []
    real = [j for j in lst if j.get("cardType") == 0 and not j.get("suppleCard")]
    supp = [j for j in lst if j.get("cardType") == 0 and j.get("suppleCard")]
    nores = any(j.get("cardType") == 3 for j in lst)
    print(f"[{label}] ✅ code=0  真命中={len(real)}  遞補={len(supp)}  "
          f"total={data.get('total')}  hasMore={data.get('hasMore')}  無結果卡={nores}")
    for j in real[:4]:
        locs = j.get("locations") or {}
        while locs and (locs.get("children") or []):
            locs = locs["children"][0]
        fns = j.get("jobFunctions") or []
        print(f"        ・ {j.get('jobName')} @ {j.get('companyName')} "
              f"| {j.get('locationDesc')} | fn={fns[0].get('code') if fns else '-'}")
    return True


if __name__ == "__main__":
    args = sys.argv[1:]
    pairs = [(args[i], json.loads(args[i + 1])) for i in range(0, len(args), 2)]
    for idx, (label, ov) in enumerate(pairs):
        if idx:
            print(f"🐢 等待 {GAP}s …")
            time.sleep(GAP)
        if not one(label, ov):
            print("⏹ 觸發安全閥，本輪結束。")
            break
