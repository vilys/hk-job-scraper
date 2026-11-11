# AGENTS.md — 給 AI agent 與程式呼叫者

本專案是香港職位搜尋器（12 個模組、9 座預設啟用據點），輸出統一的 `JobRecord`。
本文件是**機器契約**；人類安裝與各站逆向筆記見 `README.md`。
舊入口 `python main.py` 仍可使用，但**沒有** `--json`、嚴格 exit code 與能力查詢。

## 安裝

```bash
pipx install .        # 推薦：隔離環境，取得 hkjobs 命令
pip install -e .      # 開發用（裝完請先啟用 venv）
hkjobs --version      # 驗證命令真的在 PATH 上
```

⚠️ 若 `hkjobs` 顯示 `command not found`：先啟用 venv（Windows `.venv\Scripts\activate`；
macOS/Linux `source .venv/bin/activate`），或直接呼叫 `.venv\Scripts\hkjobs.exe`。
**不需安裝、也不依賴 PATH 的可靠入口**：在 repo 根目錄用 `python -m hkjobs`。

需要瀏覽器的據點另外安裝：`pip install ".[browser]" && playwright install chromium`。
部分據點另需本機 Google Chrome（看 `sources` 的 `needsChrome`）。

## 探索流程（請照順序，不要硬編碼）

1. `hkjobs sources --json` — 據點清單、啟用狀態、支援維度、每頁筆數、`daysMode`（`--days` 成本）。
2. `hkjobs options --source <據點> --json` — 該站有效的地區/職能/行業/排序值（含 `id` 與 `aliases`）。
3. `hkjobs search --source <據點> --keyword <詞> --json` — 結果在 stdout。

```bash
hkjobs sources --json | jq '.presets.all'
hkjobs options --source jobsdb --dimension district --json | jq '.dimensions.district.values[] | select(.name=="荃灣")'
hkjobs search --source jobsdb --keyword data --days 7 --pages 1 --json | jq '.summary'
```

## 命令

- `hkjobs search`：參數同 `python main.py`（`--source/--keyword/--pages/--days/--district/--category/--industry/--sort/--detail/--fill-location`），另有：
  - `--json`：stdout 只輸出單一 JSON 封套；**不主動寫檔**（除非同時給 `--out`）；日誌走 stderr（預設 WARNING）。
  - `--out PATH`：顯式寫檔；`.csv` 寫職位 CSV（UTF-8 BOM、**schema v2 共 19 欄**），其他副檔名寫 JSON（`--json` 時為完整封套）。
  - `--sort-by date|salary`：**跨站排序**。`--source all` 預設 `date`（刊登日新→舊）；單站預設不排序，保留站方相關性。解析不出日期／薪金者排最後，不丟棄。
  - `--salary-by min|mid|max`：配合 `--sort-by salary` 的取樣依據，**預設 `mid`（中位數 `(min+max)/2`，無 max 時用單點薪金）**；`min` 取下限、`max` 取上限（舊版行為）。設定的值記錄在 `query.salaryBy`，人類輸出會標明。
  - `--fill-gaps`：一鍵補齊各站已知缺口（`gov_hk`／`moovup` → `--detail`，`recruit` → `--fill-location`）。執行前列出額外請求數預估；`--yes` 或 `--json` 模式略過互動確認。`query.fillGaps` 為 `true`。
  - `--yes`：跳過 `--fill-gaps` 的互動確認（給腳本／agent 用）。
  - `--no-dedup`：關閉去重。預設以「URL 完全相同」或「(正規化標題, 正規化公司) 相同」合併，保留 `sources` / `urls`。
  - `-q`：日誌只留 ERROR。
  - **人類模式專用（不影響 `--json` 封套與 exit code）**：`--limit N`（預設 20，0 = 全部）、`--no-list`（只印摘要）、`--force`（允許 `--out` 覆蓋既有檔）。
- `hkjobs sources [--json]`：能力矩陣。
- `hkjobs options --source <站> [--dimension district|category|industry|sort] [--json]`：有效值。

**人類模式（`--json` 缺席）才有的行為，agent 不必依賴：**

- 預設列出前 20 筆職位（標題／公司／地區／薪金／刊登日）+ 來源摘要；摘要顯示 `N/M 筆有薪金`。
- 薪金欄若顯示 `約$8,800-10,560/月 (原時薪 $50 - $60)`，表示那是**換算估算**、不是實領月薪；基準每日 8 小時 × 每月 22 個工作日（時薪 ×176、日薪 ×22、年薪 ÷12）。原生月薪照原文顯示，表格下方會再印一次基準。
- 人類輸出的薪金欄顯示規則（**只影響表格**，不改 `jobs[]` 欄位、`CSV` 內容或 `schemaVersion`）：換算值標「約」置前、站方原文以 `(原…)` 括號保留在後、單位詞（`原時薪`／`原日薪`／`原年薪`）提到括號最前，故 36 格欄寬截斷後**單位詞仍可見**（舊寫法 `(原 $60 - $65 …` 會把「時薪」切掉）。原文重複的全形單位括號在顯示層去掉一次，`salary` 原文在 CSV／JSON 完整不變。
- `--out` 目標檔已存在時**拒絕覆蓋並回 exit 2**（在發任何請求之前），需 `--force`；`--json --out` 維持既有可覆寫行為。
- `--pages 0` 回 exit 2（用法錯誤），不再是「0 筆結果 / exit 5」。
- 勞工處 `gov_hk` 列表頁沒有公司名也沒有刊登日，兩者都需 `--detail`；公司欄全空時人類輸出會提示。
- **`--days` 只做日期過濾，不改排序**（2026-11-11 起）；`query.sort` 為 `null` 表示保留站方相關性排序。要日期排序請明確指定 `--sort post_dt_desc`。
- JobsDB 站方 `daterange` 只吃 1/3/7/14/31；`--days 10` 會送 `daterange=14`，**客戶端再篩回 10 天**，人類輸出會明確提示，不會靜默放寬。
- `--source all` 的人類摘要另印「各站欄位完整度」小表（公司／薪金／地區／日期命中數）與已知缺口建議；`--json` 對應 `summary.sources[].coverage`。
- `efc` 未指定 `--district` 時預設 `Hong Kong`（原本會回 London／New York），stderr 與人類輸出皆提示可改。

## 輸出契約（schemaVersion = 2，2026-11-11 起）

成功：

```json
{"schemaVersion":2,"command":"search","generatedAt":"…","query":{…,"sortBy":"date","dedup":true},
 "summary":{"total":187,"rawTotal":196,"deduped":9,"withSalary":55,"sortBy":"date",
   "sources":[{"name":"jobsdb","status":"ok","jobs":30,"error":null,
               "coverage":{"jobs":30,"company":30,"salary":10,"location":30,"date":30}}]},
 "jobs":[{"job_id":"jobsdb::123","source":"jobsdb","title":"…","company":"…",
          "location":"…","salary":"$15K - $17K","job_type":"…","industry":"…",
          "description":"…","requirements":"…","url":"…",
          "posted_date":"2026-11-10","scraped_at":"…",
          "salary_min":15000,"salary_max":17000,"salary_period":"month",
          "posted_date_raw":"19h ago","sources":["jobsdb"],"urls":["…"]}]}
```

失敗（exit ≠ 0 時）：

```json
{"schemaVersion":2,"command":"search","generatedAt":"…",
 "error":{"code":"partial_failure","message":"部分來源失敗：jobsdb"},
 "summary":{…},"jobs":[…]}
```

`code` ∈ `partial_failure` / `all_sources_failed` / `no_results` / `unexpected`。

### v1 → v2 新舊欄位對照

| 位置 | v1 | v2 | 說明 |
|---|---|---|---|
| 根 | `schemaVersion: 1` | `schemaVersion: 2` | `sources` / `options` 封套同步為 2 |
| `jobs[]` | `posted_date` 原字串（6 種格式） | `posted_date` **一律 ISO `YYYY-MM-DD`** | 相對時間以該筆 `scraped_at` 換算；無法解析給 `""`。2026-11-11 起另支援勞工處詳情頁 `DD/MM/YYYY`（**日在前**，如 `10/11/2026` → `2026-11-10`）；與 `on MM-DD` 是不同格式，不混用 |
| `jobs[]` | — | `posted_date_raw` | 保留站方原文，方便除錯與回溯 |
| `jobs[]` | — | `salary_min` / `salary_max` | **整數月薪估算**；解析不出為 `null` |
| `jobs[]` | — | `salary_period` | `month` \| `hour` \| `day` \| `year`；換算基準**每日 8 小時、每月 22 個工作日**：時薪 ×176、日薪 ×22、年薪 ÷12。`salary` 原文不變，非原生月薪者不可讀成實領月薪 |
| `jobs[]` | — | `sources` / `urls` | 去重合併後的所有來源與連結（陣列；CSV 中以 `\|` 分隔） |
| `summary` | `withSalary` 計所有非空字串 | **只計 `salary` 含阿拉伯數字者** | `TBD` / `Competitive` / `Negotiable` / `面議` 不再計入 |
| `summary` | — | `deduped` / `rawTotal` | 被合併筆數／原始筆數；`total + deduped == rawTotal` |
| `summary` | — | `sortBy` | `date` \| `salary` \| `null`（單站不排序） |
| `summary.sources[]` | — | `coverage` | `{jobs, company, salary, location, date}` 命中數；僅 `status=ok` 有 |
| `query` | — | `sortBy` / `dedup` | 反映本次實際設定 |
| `query` | — | `salaryBy`（僅 `--sort-by salary` 時） | `min` \| `mid` \| `max`；`date`／不排序的封套逐鍵不變 |
| `query` | — | `fillGaps` | `--fill-gaps` 是否啟用（布林） |

**schemaVersion 維持 2**：本輪沒有新增／改動任何 `jobs[]` 欄位；`query` 本來就是動態反映參數的物件，新增的鍵舊客戶端可忽略。若未來新增 `jobs[]` 欄位才需升 v3 並補對照表。

**相容性承諾**：exit code（0/1/2/3/4/5）、`error.code`、命令名稱、既有 13 個 `jobs[]` 欄位名稱、`python main.py` 的輸出（仍為 v1 的 13 欄）全部不變。`--out` 的 CSV 由 13 欄增為 19 欄（UTF-8 BOM 不變）。

## exit code

| 值 | 意義 | 建議動作 |
|---|---|---|
| 0 | 成功且 ≥1 筆 | 使用結果 |
| 2 | 參數／用法錯誤（**無 JSON 封套**，看 stderr） | 修正參數 |
| 3 | 部分來源失敗 | 讀 `summary.sources`，可重試失敗站 |
| 4 | 全部來源失敗 | 稍後重試；先跑 `sources` 檢查 |
| 5 | 成功但 0 筆 | 放寬 `--days`／換關鍵字／先查 `options` |
| 1 | 未預期錯誤（bug） | 回報並附 stderr |

優先序：`1 > 4 > 3 > 5 > 0`。

## 速率禮節（必須遵守）

- 一次只跑一個來源，**不要並行**同一站，也不要同時啟動多個 `hkjobs`。
- `--source all` 會依序跑 9 站；僅供便利使用，**勿用於巡檢**。需要多站時分批（每批 ≤5 站、批間休息 ≥30 秒）。
- 首次探測用 `--pages 1`；確認結果再增加。
- 站方請求間隔已寫死在 1.5–8 秒（見 `sources` 的 `requestDelaySeconds`），不要嘗試繞過。
- 被擋一次往往要等數天；寧可慢，不要猛。

## 安全與隱私

- `LINKEDIN_LI_AT` 等同 LinkedIn 帳號憑證：不得輸出、寫入日誌、提交或貼到對話中。
- 爬取結果可能含個資與聯絡方式；不要公開上傳未經處理的原始輸出。
- 不要為了驗證而讀取或列印 `~/.git-credentials`、環境變數中的 token。

## 修改本專案時

- 新增／變更據點行為，必須同步更新：`hkjobs/capabilities.py`、README 的「各站功能支援矩陣」與該站技術筆記。
- 變更多人類輸出／旗標，必須同步更新：`README.md` 的「給 AI agent／程式呼叫」章節、本文件命令段、`search --help` 的 epilog；若動到離線重播，另同步 `tools/replay_aggregation.py` 與 `tools/README.md`。薪金欄顯示格式另同步 README「薪金換算基準」與本文件「人類模式」段（含範例輸出字串）。
- 新增／調整旗標時，`hkjobs/capabilities.py` 是能力與薪金換算基準的單一資料源（`GAP_FILL_ACTIONS` / `SALARY_CONVERSION_BASIS`），不要在 CLI 裡另寫一份。
- Windows cp950：所有人類輸出與 `tools/*.py` 的 `--help` 不得因非 cp950 字元 crash；新文字先確認可編碼（`≈`／emoji 不行，`→` `×` `÷` `—` 可以），或在入口呼叫 `contract.configure_io()`。
- 各站功能彼此隔離；不支援的參數一律警告後忽略，不得報錯中斷或影響他站。
- 執行 `python -m unittest discover -s tests`（零網路）必須全綠；目前 173 個測試。
- 變更聚合層（正規化／去重／排序／完整度）須同步 `hkjobs/aggregate.py`、`hkjobs/contract.py` 的 `SCHEMA_VERSION`、本文件對照表與 README。
