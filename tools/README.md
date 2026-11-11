# tools/ — 診斷與偵察腳本

這些**不是**日常執行需要的東西。只有在「某個站突然回 0 筆」、
需要判斷病因（站方改版／驗證碼／等待不足）時才會用到。

> 🐢 **請一律在專案根目錄執行**，例如 `python tools/_probe_liepin.py`。
> 腳本以「當前工作目錄」為基準寫入 `output/_probe/`。

| 腳本 | 用途 | 請求量 |
|---|---|---|
| `_probe_liepin.py` | 獵聘聽診：一次導航，列出所有 api 請求、最終 URL、頁面標題、卡片數 | 1 次頁面導航 |
| `_probe_li_guest.py` | LinkedIn 訪客分頁端點驗證（手動指定 `start`） | 每次 1 支 |
| `probe_offertoday.py` | OfferToday 推薦池 API 偵察 | 手動，逐支 |
| `probe_ot_cold.py` | OfferToday 冷請求（免瀏覽器／免 cookie）參數對照 | 手動，逐支 |
| `replay_aggregation.py` | **零網路**：用已存檔的真實回應重播聚合管線，驗證改版 | 0 |

所有腳本都遵守專案禮節：**不併發、不重試、遇到異常（非 200／驗證碼／非預期內容）立即停手**。

### 離線重播（改聚合層時請優先用它）

```bash
python tools/replay_aggregation.py --sort-by salary --human --limit 8
python tools/replay_aggregation.py --sort-by salary --salary-by max --out output/by_max.json
python tools/replay_aggregation.py --no-dedup --out output/raw.json
```

基準檔是 `output/all_baseline.json`（2026-11-11 真跑 `--source all` 的 196 筆 v1 封套）。
`--salary-by min|mid|max` 配合 `--sort-by salary`，預設 `mid`（中位數 `(min+max)/2`）。
工具只是把真資料餵進現行 `contract.search_payload()` 與 `cli._print_human()`，
`generatedAt` 之外的職位內容不會反映站方最新變動。

### Windows cp950 主控台

`--help` 曾因說明文字裡的 `⚠️`（U+26A0）直接 `UnicodeEncodeError`。現在入口會比照
`hkjobs.contract.configure_io()` 先把 stdout／stderr 設為 UTF-8，且所有 `tools/*.py`
的 module docstring 都只用 cp950 可編碼字元；其餘探針腳本也在入口重設兩個串流。
新增輸出文字時請避開 emoji／`≈` 等 cp950 無法編碼的字元（`→` `×` `÷` `—` 則可用）。

跑之前請先問自己：這一支請求，真的非打不可嗎？
能從已存檔的回應或字典推理出來的，就不要驚動站方。
