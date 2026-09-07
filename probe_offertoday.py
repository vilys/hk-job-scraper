# -*- coding: utf-8 -*-
"""OfferToday round 8：驗證職能/行業篩選格式 + 偵測普通 requests 能否直打 API。

🐢 1 次導航 + 2 支瀏覽器內 POST（間隔 8s） + 1 支冷 requests（無 cookie）＝ 3 支 API 請求。
🛑 安全閥：code != 0 / status != 200 / 驗證碼徵兆 → 立即中止本輪。
每支請求直接判讀「真命中（suppleCard=false）vs 遞補推薦（true）」並交叉驗證篩選是否生效。
"""
import sys, json, time
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
API = "/wapi/geek/recommend/search/list"
GAP = 8

BASE = {"keyword": "", "page": 1, "pageSize": 10, "salaryType": 0,
        "publishTime": "", "employmentTypes": [], "experiences": [],
        "educationLevels": [], "benefits": [], "workPermits": [],
        "rcdType": 7, "jobFunctionCodes": [], "industries": [],
        "subDistrictCodes": [], "searchSource": None}

TESTS = [
    ("fn_118000",  {"jobFunctionCodes": ["118000"]}),   # 資訊科技（大類）
    ("ind_101",    {"industries": ["101"]}),            # 財務/金融（大類）
]

aborted = False
summary = []


def judge(name, st, body):
    """回傳 True=繼續, False=中止"""
    if st != 200 or any(k in body[:400] for k in ("驗證碼", "验证", "captcha")):
        print(f"[{name}] 🛑 HTTP {st} / 疑似驗證碼 → 中止：{body[:200]}")
        summary.append((name, f"ABORT {st}", ""))
        return False
    try:
        d = json.loads(body)
    except Exception:
        print(f"[{name}] 🛑 非 JSON → 中止")
        summary.append((name, "NON-JSON", ""))
        return False
    if d.get("code") != 0:
        print(f"[{name}] 🛑 code={d.get('code')} → 中止：{str(d.get('message'))[:120]}")
        summary.append((name, f"code={d.get('code')}", ""))
        return False

    data = d.get("data") or {}
    lst = data.get("resultList") or []
    real = [j for j in lst if j.get("cardType") == 0 and not j.get("suppleCard")]
    supp = [j for j in lst if j.get("cardType") == 0 and j.get("suppleCard")]
    empty_card = any(j.get("cardType") == 3 for j in lst)
    print(f"[{name}] ✅ code=0  真命中={len(real)}  遞補={len(supp)}  "
          f"total={data.get('total')}  hasMore={data.get('hasMore')}  無結果卡={empty_card}")

    # 交叉驗證：真命中卡片的職能分佈
    dist, titles = {}, []
    for j in real:
        fns = j.get("jobFunctions") or []
        code = str(fns[0].get("code")) if fns else "-"
        dist[code] = dist.get(code, 0) + 1
        titles.append(j.get("jobName"))
    top = sorted(dist.items(), key=lambda x: -x[1])
    print(f"        職能分佈：{', '.join(f'{k}×{v}' for k, v in top)}")
    for t in titles[:3]:
        print(f"        ・ {t}")
    summary.append((name, f"真命中 {len(real)}", f"遞補 {len(supp)} / 職能 {top[:3]}"))
    return True


with sync_playwright() as p:
    b = p.chromium.launch(headless=True, channel="chrome")
    ctx = b.new_context(user_agent=UA, locale="zh-HK")
    pg = ctx.new_page()
    r = pg.goto("https://www.offertoday.com/hk/search",
                wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(6000)
    print(f"[nav] status={r.status}")

    for name, override in TESTS:
        if aborted:
            print(f"[{name}] ⏭  已中止，跳過")
            summary.append((name, "SKIPPED", ""))
            continue
        time.sleep(GAP)                       # 🐢
        payload = dict(BASE); payload.update(override)
        res = pg.evaluate("""async ([path, payload]) => {
            try {
                const r = await fetch(path, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json',
                              'Accept': 'application/json, text/plain, */*'},
                    credentials: 'include', body: JSON.stringify(payload)
                });
                return {status: r.status, body: await r.text()};
            } catch (e) { return {status: -1, body: String(e)}; }
        }""", [API, payload])
        body = res.get("body") or ""
        open(f"output/_ot_r8_{name}.json", "w", encoding="utf-8").write(body)
        if not judge(name, res.get("status"), body):
            aborted = True

    b.close()

# ── 第三支：冷 requests（無 cookie、無瀏覽器）──
print("\n[cold_requests] 🐢 等待 8s 後出發 …")
time.sleep(GAP)
try:
    import requests
    resp = requests.post(
        "https://www.offertoday.com" + API,
        json=dict(BASE),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/plain, */*",
                 "User-Agent": UA,
                 "Origin": "https://www.offertoday.com",
                 "Referer": "https://www.offertoday.com/hk/search"},
        timeout=30,
    )
    body = resp.text
    open("output/_ot_r8_cold_requests.json", "w", encoding="utf-8").write(body)
    print(f"[cold_requests] HTTP {resp.status_code}  {len(body)} bytes")
    if resp.status_code == 200:
        try:
            d = json.loads(body)
            n = len((d.get("data") or {}).get("resultList") or [])
            print(f"                code={d.get('code')}  resultList={n}")
            summary.append(("cold_requests", f"HTTP200 code={d.get('code')}", f"可行，{n} 卡"))
        except Exception:
            print(f"                非 JSON：{body[:200]}")
            summary.append(("cold_requests", "HTTP200 非JSON", ""))
    else:
        print(f"                {body[:300]}")
        summary.append(("cold_requests", f"HTTP{resp.status_code}", "需 Playwright"))
except Exception as e:
    print(f"[cold_requests] 例外：{e}")
    summary.append(("cold_requests", "EXC", str(e)[:80]))

print("\n=== R8 總結 ===")
for n, s, extra in summary:
    print(f"  {n:16s} {s:22s} {extra}")
