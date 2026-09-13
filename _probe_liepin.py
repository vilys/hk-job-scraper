# -*- coding: utf-8 -*-
"""獵聘診斷：一次導航，錄下所有 api 請求 / 最終 URL / 頁面卡片數。

用途：判斷「未攔截到搜尋 API 回應」到底是
  A. 站方改版（API 路徑變了）
  B. 等待時間不足（secscan JS 慢）
  C. 缺首次造訪 cookie
  D. 攔截本身不穩定（已知）
用法：
  python _probe_liepin.py [url]
"""
from __future__ import annotations

import sys
import time

from playwright.sync_api import sync_playwright

DEFAULT_URL = "https://www.liepin.com/zhaopin/?city=320&dq=320&currentPage=0"

CARD_SELECTORS = [
    "[class*='job-card']",
    "[class*='jobCard']",
    "[class*='job-list'] li",
    ".job-list-box .job-card-pc",
    "[data-nick*='job']",
]


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    reqs: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel="chrome")
        ctx = browser.new_context(locale="zh-CN", viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()

        def on_resp(resp):
            u = resp.url
            if "api" in u or "search" in u:
                reqs.append({"url": u[:160], "status": resp.status})

        pg.on("response", on_resp)

        print(f"[nav] {url}")
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:  # noqa: BLE001
            print(f"[nav] 失敗：{e}")

        for waited in (5, 10, 15):
            pg.wait_for_timeout(5_000)
            n = 0
            for sel in CARD_SELECTORS:
                try:
                    n = max(n, pg.locator(sel).count())
                except Exception:  # noqa: BLE001
                    pass
            print(f"[wait {waited:>2}s] url={pg.url[:110]}")
            print(f"[wait {waited:>2}s] title={pg.title()[:80]!r} cards={n}")

        print("\n=== 攔截到的 api / search 回應 ===")
        if not reqs:
            print("（無）")
        for r in reqs:
            print(f"  {r['status']}  {r['url']}")

        # 頁面正文前 600 字，判斷是否驗證碼 / 空殼
        try:
            body = pg.inner_text("body")[:600]
            print("\n=== body 前 600 字 ===")
            print(body)
        except Exception as e:  # noqa: BLE001
            print(f"[body] 讀取失敗 {e}")

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
