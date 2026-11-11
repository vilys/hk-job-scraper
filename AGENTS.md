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
  - `--out PATH`：顯式寫檔；`.csv` 寫職位 CSV（UTF-8 BOM），其他副檔名寫 JSON（`--json` 時為完整封套）。
  - `-q`：日誌只留 ERROR。
  - **人類模式專用（不影響 `--json` 封套與 exit code）**：`--limit N`（預設 20，0 = 全部）、`--no-list`（只印摘要）、`--force`（允許 `--out` 覆蓋既有檔）。
- `hkjobs sources [--json]`：能力矩陣。
- `hkjobs options --source <站> [--dimension district|category|industry|sort] [--json]`：有效值。

**人類模式（`--json` 缺席）才有的行為，agent 不必依賴：**

- 預設列出前 20 筆職位（標題／公司／地區／薪金／刊登日）+ 來源摘要；摘要顯示 `N/M 筆有薪金`。
- `--out` 目標檔已存在時**拒絕覆蓋並回 exit 2**（在發任何請求之前），需 `--force`；`--json --out` 維持既有可覆寫行為。
- `--pages 0` 回 exit 2（用法錯誤），不再是「0 筆結果 / exit 5」。
- 勞工處 `gov_hk` 列表頁沒有公司名也沒有刊登日，兩者都需 `--detail`；公司欄全空時人類輸出會提示。
- **`--days` 只做日期過濾，不改排序**（2026-11-11 起）；`query.sort` 為 `null` 表示保留站方相關性排序。要日期排序請明確指定 `--sort post_dt_desc`。

## 輸出契約（schemaVersion = 1）

成功：

```json
{"schemaVersion":1,"command":"search","generatedAt":"…","query":{…},
 "summary":{"total":37,"withSalary":12,
   "sources":[{"name":"jobsdb","status":"ok","jobs":37,"error":null}]},
 "jobs":[{"job_id":"jobsdb::123","source":"jobsdb","title":"…","company":"…",
          "location":"…","salary":"…","job_type":"…","industry":"…",
          "description":"…","requirements":"…","url":"…",
          "posted_date":"…","scraped_at":"…"}]}
```

失敗（exit ≠ 0 時）：

```json
{"schemaVersion":1,"command":"search","generatedAt":"…",
 "error":{"code":"partial_failure","message":"部分來源失敗：jobsdb"},
 "summary":{…},"jobs":[…]}
```

`code` ∈ `partial_failure` / `all_sources_failed` / `no_results` / `unexpected`。

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
- 變更多人類輸出／旗標，必須同步更新：`README.md` 的「給 AI agent／程式呼叫」章節、本文件命令段、`search --help` 的 epilog。
- 各站功能彼此隔離；不支援的參數一律警告後忽略，不得報錯中斷或影響他站。
- 執行 `python -m unittest discover -s tests`（零網路）必須全綠；目前 106 個測試。
