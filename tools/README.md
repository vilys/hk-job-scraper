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

基準檔是 `output/all_baseline.json`（2026-11-11 真跑 `--source all` 的 196 筆 **v1** 封套）。
`--salary-by min|mid|max` 配合 `--sort-by salary`，預設 `mid`（中位數 `(min+max)/2`）。
工具只是把真資料餵進現行 `contract.search_payload()` 與 `cli._print_human()`，
`generatedAt` 之外的職位內容不會反映站方最新變動。

#### 首次使用：基準檔不在 repo

`output/` 列在 `.gitignore`，所以 fresh clone **不會**有 `output/all_baseline.json`；
直接跑重播會得到 `FileNotFoundError`（exit 1）。先產生一份（**這是一次九站真爬取**，
請遵守速率禮節：只跑一次、用 `--pages 1`，之後一律改用離線重播，
不要為了驗證重跑 `--source all`）：

```bash
mkdir -p output                       # Windows cmd：if not exist output mkdir output
python -m hkjobs search --source all --keyword 文員 --pages 1 --json --out output/latest_v2.json
```

本機沒有 `hkjobs` 指令時一律用 `python -m hkjobs`（見 README「60 秒上手」）。
刻意存成 `latest_v2.json` 而不是直接叫 `all_baseline.json`，是為了避免把 v2 檔誤當成 v1 基準。

#### 基準檔請用 v1 原始封套（v2 不等價）

現行 CLI 的 `--json` 輸出是 **v2**（`schemaVersion=2`），上面那條指令產生的就是 v2。
v2 拿去當 `--baseline` **機械上可跑（exit 0）**，但驗不到聚合最核心的解析路徑：

| | v1 原始封套（建議） | v2 封套（現行 CLI 輸出） |
|---|---|---|
| 重播可否執行 | 可 | 可，exit 0 |
| `jobs[].posted_date` | 站方原字串（`19h ago`、`10/11/2026`…） | 已是 ISO `YYYY-MM-DD` |
| `posted_date_raw` | 沒有此欄 | 有，但重播時被丟掉 |
| 會跑 `parse_date()` 的相對時間／`DD/MM/YYYY` 分支 | **會** | **不會**（ISO 原樣轉回） |
| 去重與 `rawTotal` | 由 196 筆原始資料重算，現行去重規則 `total=194 / deduped=2`（舊規則曾為 187 / 9） | 資料已去重過，只是 194 筆再算一次，`deduped=0 / rawTotal=194` |

原因：`tools/replay_aggregation.py` 用 `JobRecord.from_dict()` 重建職位，而
`JobRecord.FIELDS` 只有 **v1 的 13 欄**——`posted_date_raw`、`salary_min/max/period`、
`sources`、`urls` 全部被忽略。v2 的 `posted_date` 已是 ISO，`to_v2()` 只是把 ISO
原樣放回去，相對時間與 `DD/MM/YYYY` 分支根本沒被執行。2026-11-11 實測
（**現行去重規則**）：v1 基準有 **81 筆非空非 ISO 日期**、重播後
`total=194 / deduped=2 / rawTotal=196 / withSalary=55`；
v2 基準 `posted_date` 非 ISO **0 筆**、`deduped=0 / rawTotal=194`。

> 去重規則已改：同 URL、或同「標題＋公司＋同一 ISO 刊登日」才合併；**不同刊登日的
> 重貼會保留**，兩筆日期皆空才退回舊的「標題＋公司」鍵。舊文件寫的
> `187 / deduped=9` 是 2026-11-11 當天舊規則的歷史數字，不是現行結果。
>
> 本機若還留著當天舊規則產出的 `output/all.json`（v2 封套、**187 筆**），那是歷史快照；
> 直接跑 `python tools/replay_aggregation.py` 會以現行規則覆寫成 **194 筆**。想保留舊快照
> 請先另存，或用 `--out output/<別名>.json` 指定輸出（本文件的驗證都建議這樣做）。

**結論**：要驗證聚合解析（日期正規化、薪金解析、去重、排序）請用 **v1 原始封套**
（從既有存檔取得，或由舊版 CLI 輸出）。**不要把隨便一份最新 `--json` 輸出當成等價基準**；
它適合驗證顯示層／排序／薪金中位數，但不能據此宣稱日期解析沒壞。

fresh clone 若手上只有 v2，有兩條零網路的路：

1. 直接跑解析器單元測試：`python -m unittest tests.test_aggregate_v2_fixes -v`
   （內含真實 12 筆 gov_hk `DD/MM/YYYY` 與相對時間案例，不需要基準檔）。
2. 把 v2 降階成 v1：`posted_date_raw` 寫回 `posted_date`、刪掉 v2 專有欄位、
   `schemaVersion` 改回 1。跨平台單行（離線、零請求，可直接貼進 cmd／PowerShell／bash）：

```bash
python -c "import json,pathlib; d=json.loads(pathlib.Path('output/latest_v2.json').read_text(encoding='utf-8')); V1=('job_id','source','title','company','location','salary','job_type','industry','description','requirements','url','posted_date','scraped_at'); [j.__setitem__('posted_date',j.pop('posted_date_raw',j['posted_date'])) for j in d['jobs']]; d['jobs']=[{k:j[k] for k in V1} for j in d['jobs']]; d['schemaVersion']=1; pathlib.Path('output/baseline_from_v2.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')"
python tools/replay_aggregation.py --baseline output/baseline_from_v2.json --out output/replay_from_v2.json
```

> **別覆寫 `output/all_baseline.json`**：若手上已有真正的 196 筆 v1 基準，
> 一覆寫就救不回被去重合併掉的 2 筆。降階檔請另存新名，用 `--baseline` 指定。
>
> 降階後 `posted_date_raw` 回到 `posted_date`，重播時確實會跑 `parse_date()`
> （實測原始字串 `1h ago`、`49m ago` 重現、162/194 筆轉成 ISO）。但 v2 已經去重合併過，
> 降階檔只有 194 筆、`deduped=0 / rawTotal=194`，仍不等於原本 196 筆的 v1 基準：
> **這條路適合驗解析，不適合驗去重**。

### Windows cp950 主控台

`--help` 曾因說明文字裡的 `⚠️`（U+26A0）直接 `UnicodeEncodeError`。現在入口會比照
`hkjobs.contract.configure_io()` 先把 stdout／stderr 設為 UTF-8，且所有 `tools/*.py`
的 module docstring 都只用 cp950 可編碼字元；其餘探針腳本也在入口重設兩個串流。
新增輸出文字時請避開 emoji／`≈` 等 cp950 無法編碼的字元（`→` `×` `÷` `—` 則可用）。

### 相關入口（不在 tools/ 裡，但常被一起問到）

| 入口 | 用途 |
|---|---|
| `python -m hkjobs guide`／`python -m hkjobs`（無子命令） | 互動引導：用編號選站、職能、天數，固定 `--pages 1`；選完**先印完整命令**再問要不要執行，取消即零請求 |
| 雙擊 `start.bat`（Windows） | 自動找 `venv`／`.venv`、檢查依賴（缺了提示 `pip install -r requirements.txt`）後進入同一個引導模式 |
| `python build_dashboard.py` | 把 `output/` 的 JSON／CSV 做成單檔 HTML 看板，**認得 CLI 的 schema v2 封套**；預設 16px、大字模式、鍵盤可達；`--out` 純檔名放 `output/`，含目錄或絕對路徑照給，寫入失敗回 `exit 2` 且不丟 traceback |

`build_dashboard.py` 的日期解析統一呼叫 `hkjobs.aggregate.parse_date`（不再有第二套 regex），
`age_days` 以該筆 `scraped_at` 為基準；但它以 `job_id` 去重，與聚合層的
「URL／標題＋公司＋刊登日」去重鍵不同，兩邊筆數不必相等（見 `AGENTS.md`）。

跑之前請先問自己：這一支請求，真的非打不可嗎？
能從已存檔的回應或字典推理出來的，就不要驚動站方。
