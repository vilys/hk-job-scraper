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

- `hkjobs search`：參數同 `python main.py`（`--source/--keyword/--pages/--days/--salary-min/--district/--category/--industry/--sort/--detail/--fill-location`），另有：
  - `--json`：stdout 只輸出單一 JSON 封套；**不主動寫檔**（除非同時給 `--out`）；日誌走 stderr（預設 WARNING）。
  - `--out PATH`：顯式寫檔；`.csv` 寫職位 CSV（UTF-8 BOM、**schema v2 共 19 欄**），其他副檔名寫 JSON（`--json` 時為完整封套）。
  - `--sort-by date|salary`：**跨站排序**。`--source all` 預設 `date`（刊登日新→舊）；單站預設不排序，保留站方相關性。解析不出日期／薪金者排最後，不丟棄。
  - `--salary-by min|mid|max`：配合 `--sort-by salary` 的取樣依據，**預設 `mid`（中位數 `(min+max)/2`，無 max 時用單點薪金）**；`min` 取下限、`max` 取上限（舊版行為）。設定的值記錄在 `query.salaryBy`，人類輸出會標明。
  - `--fill-gaps`：一鍵補齊各站已知缺口（`gov_hk`／`moovup` → `--detail`，`recruit` → `--fill-location`）。執行前列出額外請求數預估；`--yes` 或 `--json` 模式略過互動確認。`query.fillGaps` 為 `true`。
  - `--yes`：跳過 `--fill-gaps` 的互動確認（給腳本／agent 用）。
  - `--no-dedup`：關閉去重。預設以「URL 完全相同」或「(正規化標題, 正規化公司, **同一 ISO 刊登日**) 相同」合併，保留 `sources` / `urls`；**不同刊登日的重貼視為獨立職缺**，兩筆日期皆解析不出時才退回舊的 (標題, 公司) 鍵。
  - `-q`：日誌只留 ERROR。
  - **人類模式專用（不影響 `--json` 封套與 exit code）**：`--limit N`（預設 20，0 = 全部）、`--no-list`（只印摘要）、`--force`（允許 `--out` 覆蓋既有檔）。
- `hkjobs sources [--json]`：能力矩陣。
- `hkjobs options --source <站> [--dimension district|category|industry|sort] [--json]`：有效值。
- `hkjobs guide` / `hkjobs`（無子命令）：互動引導模式，詳見下方專節。

**人類模式（`--json` 缺席）才有的行為，agent 不必依賴：**

- 預設列出前 20 筆職位（標題／公司／地區／薪金／刊登日）+ 來源摘要；摘要顯示 `N/M 筆有薪金`。
- 薪金欄若顯示 `約$8,800-10,560/月 (原時薪 $50 - $60)`，表示那是**換算估算**、不是實領月薪；基準每日 8 小時 × 每月 22 個工作日（時薪 ×176、日薪 ×22、年薪 ÷12）。原生月薪照原文顯示，表格下方會再印一次基準。
- 人類輸出的薪金欄顯示規則（**只影響表格**，不改 `jobs[]` 欄位、`CSV` 內容或 `schemaVersion`）：換算值標「約」置前、站方原文以 `(原…)` 括號保留在後、單位詞（`原時薪`／`原日薪`／`原年薪`）提到括號最前，故 36 格欄寬截斷後**單位詞仍可見**（舊寫法 `(原 $60 - $65 …` 會把「時薪」切掉）。原文重複的全形單位括號在顯示層去掉一次，`salary` 原文在 CSV／JSON 完整不變。
- `--out` 目標檔已存在時**拒絕覆蓋並回 exit 2**（在發任何請求之前），需 `--force`；`--json --out` 維持既有可覆寫行為。
- `--pages 0` 回 exit 2（用法錯誤），不再是「0 筆結果 / exit 5」。
- **`--pages N` 是頁數，不是筆數**（2026-11-15 定案）：每頁筆數是站方契約（`hkjobs sources --json` 的 `perPage`，10–58 不等；LinkedIn 首頁 58、續頁 10），同一個 N 在 `--source all` 下各站產出量不同，**屬預期行為**。結果上限為各頁筆數之和（一般站是 `N × perPage`；LinkedIn 首頁 58 + 續頁 10×(N-1)），會隨結果不足一頁、`--days`／`--salary-min` 客戶端過濾而更少。`--limit` 只影響人類清單，不影響抓取量。執行前日誌會印出該站的「最多 N 頁，每頁約 M 筆 → 上限約 X 筆」。
- **JobsDB `pageSize=30` 是上述契約的一部分**（GraphQL 與 SSR 一致）：不得為減少請求數改成 100 讓 `--pages` 的產出量靜默放大三倍；若真要改，必須把 transport 頁切成 30 筆的「邏輯頁」（或另開明確的筆數參數）。`tests/test_pages_semantics.py` 有護欄測試（預設 30、`per_page` 與 transport 一致、上限 100 仍保留）。
- 勞工處 `gov_hk` 列表頁沒有公司名也沒有刊登日，兩者都需 `--detail`；公司欄全空時人類輸出會提示。
- **`--days` 只做日期過濾，不改排序**（2026-11-11 起）；`query.sort` 為 `null` 表示保留站方相關性排序。要日期排序請明確指定 `--sort post_dt_desc`。
- JobsDB 站方 `daterange` 只吃 1/3/7/14/31；`--days 10` 會送 `daterange=14`，**客戶端再篩回 10 天**，人類輸出會明確提示，不會靜默放寬。GraphQL 通道改用 `filter.listedAt:"Nd"` 下推（同一組離散值；`31→"30d"`）。
- **`--salary-min N`（2026-11-15）**：只保留月薪有機會達到 N 的職位（以區間上限判斷，缺上限時用單點值；與站方 `salaryMin` 的區間交集語意一致）。**只有 GraphQL 通道是真的站方端下推**（`filter.salaryMin:"<N>m"`）；SSR fallback 的 `salaryrange`／`salarytype` **實測無效**（2026-11-15：`salaryrange=100000-` 仍回同一組 30 張卡，等 12 秒亦無變化），該路徑僅客戶端篩，且 SSR 列表薪金覆蓋低（同頁 7/30）→ fallback ＋ `--salary-min` 會把 23/30 當「無法判斷」丟掉。其他來源由 `BaseScraper.scrape_all()` 以 `aggregate.parse_salary()` 的正規化月薪兜底；薪金解析不出者一律排除。`query.salaryMin` 回顯；`schemaVersion` 仍 2、`jobs[]` 13 欄不變。
- `--source all` 的人類摘要另印「各站欄位完整度」小表（公司／薪金／地區／日期命中數）與已知缺口建議；`--json` 對應 `summary.sources[].coverage`。
- `efc` 未指定 `--district` 時預設 `Hong Kong`（原本會回 London／New York），stderr 與人類輸出皆提示可改。

## JobsDB GraphQL 搜尋通道（2026-11-15）

`scrapers/jobsdb.py::search()` 的路由（**不改變 `--json` 封套、`jobs[]` 13 欄、`schemaVersion=2`**）：

| 條件 | 通道 | 請求 |
|---|---|---|
| 只給 `--keyword`／`--days`／`--salary-min`／`--pages`（或都不給） | `POST https://hk.jobsdb.com/graphql` 的 `jobSearchV7` | 每頁 1 次 POST，`pageSize=30` |
| 給 `--district`（且在 `jobsdb_districts.json` 的 40 個之內） | 同上，地區以 `searchIntent.where:["<英文名>"]` 下推 | 每頁 1 次 POST，**不開瀏覽器** |
| 給 `--district` 但字典外／給 `--category`／給 `--sort` | 既有 Playwright SSR 瀏覽網址 | 每頁 1 次 GET（共用 `cf_clearance`） |
| `JOBSDB_GRAPHQL=0` | 既有 Playwright SSR | 同上 |
| GraphQL 失敗（非 200／Cloudflare HTML／`errors`／形狀不符／網路例外） | **熔斷本輪**並退回 SSR | 後續頁不再打 GraphQL |

- **零憑證**：請求只帶 UA、`Accept`、`Content-Type`、`Origin`、`Referer`；無 Cookie、無 `Authorization`、無 `li_at`。`solVisitorId`／`sessionId` 每次以 `uuid4()` 動態產生（匿名追蹤 ID，不綁帳號）。設計上**不需要登入**。
- 已驗證維度：`text`（原始字串，不做 percent-encode）、`filter.listedAt`、`filter.salaryMin`、`searchIntent.where`（地區，2026-11-15 實測）、`responseConfig.page/pageSize`、`sort:"score"`。職能與 `sort:"date"` 沒有實證，故不下推。
- **`--district` 下推 `searchIntent.where`（2026-11-15）**：地名由字典 slug 推導（`tuen-mun` → `Tuen Mun`），不需要額外英文表。實測 `where:["Tuen Mun District"]` 與 `where:["Tuen Mun"]` 回傳完全相同，故採後者。三個地區抽驗：屯門 30/30、沙田 30/30 落在該區；**中環 26/30**（另 4 筆在灣仔／尖沙咀）——查詢固定帶 `distanceKms: 2`，站方會把「附近」納入，這是站方語意而非過濾錯誤。字典外地區一律退回瀏覽網址，不拿猜出的地名去試。
- **`--salary-min` 下推 `filter.salaryMin`**（2026-11-15）：值為 `"<N>m"`，`m`=monthly（唯一有實證的週期），與 `listedAt` 共用同一個 `filter` 物件。SSR fallback 仍會帶 `salaryrange=<N>-&salarytype=monthly`，但**實測無效**（僅與站方 UI 參數形狀一致、無害），該路徑靠客戶端兜底；其他來源同樣由 `BaseScraper` 客戶端兜底。
- 資料增益：`salary {min,max,period,currency}` 補上 SSR 常缺的薪金；`listedAt.dateTimeUtc` 精確 UTC 存 `raw["graphql"]["listed_at_utc"]`。`posted_date` 仍輸出相對字串（`2d ago`），因為 `days_since_posted()` 只認相對格式——若改 ISO 會讓 `--days` 濾光。
- `cjs.salary.hideSalary` 是雇主交給索引但選擇不對求職者顯示的**旗標**：旗標只存 `raw["graphql"]["hide_salary"]`、不進 13 欄主表；**但對應的薪資數值照常填入主表 `salary`，會出現在 CSV／JSON 輸出**（離線快照 157/202 筆）。描述此行為時須區分「旗標」與「薪資數值」，兩者去向不同，不可混為一談。
- 使用範圍：輸出供個人求職參考與一次性市場研究；對外發布／薪酬談判指南／資料產品前須先確認 Jobsdb／SEEK 服務條款。邊界：只抓公開廣告、零憑證、不取求職者個資、不投遞履歷、不繞付費牆。
- 節流：單頁只發 1 次 POST、不重試、不併發；翻頁間隔由 `BaseScraper._sleep()` 統一負責（JobsDB 2 秒 + 抖動）。熔斷避免 `_with_retry` 把同頁重撞成「3 次 GraphQL + 3 次瀏覽器」。
- **`--detail` 改走 GraphQL `jobDetails`**（2026-11-15）：`get_detail()` 優先打 `jobDetails(id)` 取 `content`（HTML → 純文字），常見路徑（只給 `--keyword`／`--days`／`--pages` + `--detail`）**完全不啟動 Playwright**。失敗熔斷本輪並退回既有 Playwright 詳情流程；`JOBSDB_GRAPHQL=0` 同步停用。搜尋與詳情兩個 operation 的熔斷旗標彼此獨立。
- 詳情 query 刻意**不選** `products.questionnaire`（申請問卷題目定義），維持「只抓公開廣告」邊界；單一回應過大（413 / Payload Too Large）改用不含 `content` 的精簡 query，只影響該筆、不熔斷整輪。`jobDetails: null` 視為單筆無資料。
- `BaseScraper.detail_replace_fields` 是 opt-in 白名單（預設空）；只有 `JobsDBScraper` 宣告 `{"description"}`，讓完整 JD 覆蓋列表 abstract，其餘 11 站「list 優先、detail 只補空」政策完全不變。
- `needsBrowser` 在能力矩陣**維持 `True`**：`--category`／`--sort`、字典外地區，以及兩個通道的 fallback 仍需要瀏覽器（`--district` 已於 2026-11-15 起可走 GraphQL `where`）。
- ✅ **2026-11-15 即時驗證**：`jobSearchV7` 單頁 30 筆、`listedAt:"7d"` 生效、30/30 有薪金；`--salary-min 60000` 回傳與基準僅 9 筆重疊的另一組 30 筆，證明站方 `salaryMin` 真的生效（`17000` 那組與基準相同，因該頁全部已達標，不能作為證據）；`--pages 2` → 60 筆零重複、`page=2` 全新 30 筆；`jobDetails` 兩筆 4,391／4,766 字純文字 JD、零 HTML 標籤；`JOBSDB_GRAPHQL=0` 的 SSR fallback 可正常載入（取得 `cf clearance`、無 Cloudflare 阻擋）但 `salaryrange` 不生效。
- ⚠️ **仍未即時驗證**：中文關鍵字送 `text`、`--category`／`--sort` 的 SSR 瀏覽網址、熔斷後的真實退回流程、`--district` 在字典外 39 個地區的 `where` 命中率（只抽驗屯門／沙田／中環）；`31→"30d"` 仍為推導。`JOBSDB_GRAPHQL=0` 是可一鍵回退的安全閥，但會讓 `--salary-min` 嚴重失真（見上）。

## 篩選值前置驗證（`hkjobs/validation.py`）

`validate_dimensions(args, plan)` 在 `cmd_search()` 建立 plan 後、**發出任何爬取請求之前**執行，
回 `(fatal, warnings)`；`fatal` 非空時 CLI 印到 stderr 並回 `exit 2`（無 JSON 封套）。

| 情境 | 判定 | 行為 |
|---|---|---|
| 該站**支援**此維度且有固定值域（`options.load_dimension()` 非 `None` 且 `kind != "free"`），但輸入不在值域 | 篩選不會生效，卻會回傳未過濾結果（「假成功」） | **exit 2、零請求**；給最接近候選（`difflib`）與 `hkjobs options --source <站> --dimension <維度>` |
| 該站**不支援**此維度（`None`）或 `kind="free"` | 既有設計 | 沿用「警告後忽略」，不報錯、不影響他站 |
| `--source all` 且各站字典不一致 | 只有「所有支援此維度的站都判無效」才 fatal | 部分站接受／部分站不接受只印提醒，不誤傷跨站字典差異 |

只驗證 `--district` / `--category` / `--industry` 三個字典維度；`--sort`（各站各自警告回退）與
`--days`（非字典）不在範圍。中文地區「去／加區字尾」的合法別名刻意比 scraper 寬鬆，
不會把合法值誤判成無效。

## 互動引導與 Windows 啟動器

- `hkjobs guide` 或 **`hkjobs`（無子命令）** → `hkjobs/guide.py`，零新依賴；所有輸入走 `contract.read_input()`。
- 站別選項來自 `capabilities.SOURCES`，職能選項來自 `options.load_dimension()`；固定 `--pages 1`。
- 選完先印**完整命令**（`display_command()`）再問 `Y/n`；取消或 EOF = 零請求、`exit 0`。
- `run_guide(execute=...)` 可注入執行函式供零網路測試；引導模式只組出一般人類模式命令。
- `start.bat`：ASCII-only、`chcp 65001`、自動找 `venv` / `.venv`，**先用
  `"%PY%" --version` 與版本檢查確認 Python 3.10+ 存在**，不存在／過舊時印
  `python.org`／`Add python.exe to PATH`／Microsoft Store 別名的 ASCII 提示後結束；
  之後才檢查依賴、缺了提示 `pip install -r requirements.txt`，最後進
  `python -m hkjobs guide`。前提檢查必須排在依賴檢查之前，否則會把「沒裝 Python」
  誤報成「缺套件 → Install failed」（2026-11-12 修，`tests/test_guide.py` 守住順序）。
- **第一哩路**：README 開頭的「60 秒上手」順序固定為「取得程式（git／ZIP）→
  `python --version` → 雙擊 `start.bat` → 引導模式編號選」；`main.py` 只出現在
  legacy 小節。引導模式**不寫檔**（組出的命令不含 `--out`），要產檔請另下
  `--out` 指令再做 HTML 看板；文件不得寫成「引導抓完就能做看板」。
- **運行時同理**（2026-11-13 修）：`guide.py` 執行後的結尾提示必須先講「沒有寫入檔案」，
  再給可照抄的 `--out` 指令（`display_command()` 複用已印過的 `argv`，檔名由
  `_out_name()` 清理 Windows 非法字元），**最後才**提 `build_dashboard.py`；
  取消路徑不印這段提示。文字須 cp950 可編碼、無 emoji；`tests/test_guide.py::TestPostRunHint` 守住順序。
- **不變**：既有旗標 API、`--json` 單一 JSON 封套、`python main.py` 舊入口、exit code 全部不受影響。

### stdin 編碼（2026-11-12 修）

`configure_io()` 現在同時管輸出與輸入：

| 情境 | stdin 處理 |
|---|---|
| 真實 console（`isatty()` 為 True） | **完全不動**。Windows 走 Unicode API／PEP 528，本來就是 UTF-8；互動式打字不受影響 |
| 管道／檔案導向（`isatty()` 為 False） | `reconfigure(encoding="utf-8", errors="surrogateescape")`；避免 cp950 把 UTF-8 位元組解成 lone surrogate |
| 已出現 lone surrogate | `repair_stdin_text()` 用 `surrogateescape` 取回原始位元組，依 `utf-8 → cp950 → big5hkscs → gb18030` 重解；UTF-8 管道與 `cmd.exe` 的 cp950 管道都能還原中文 |

`read_input(prompt)` 是**所有** `input()` 的單一入口（引導模式各題、CLI 的
`--fill-gaps` `y/N` 確認），`EOFError`／`KeyboardInterrupt` 原樣丟給呼叫端。
回歸測試見 `tests/test_stdin_encoding.py`（含未設 `PYTHONIOENCODING` 的
cp950 管道重現、反向 cp950 位元組、console 不被 reconfigure 的保證）。

## 兩套去重語義（勿混用）

| 層 | 鍵 | 用途 |
|---|---|---|
| `contract.search_payload()` → `aggregate.deduplicate()` | 同 URL；或 (標題, 公司, **ISO 刊登日**) 相同；兩筆日期皆空退回 (標題, 公司) | 單次搜尋的跨站結果；**不同刊登日的重貼保留** |
| `build_dashboard.py::collect()` | `job_id` | 多檔快照合併，保留描述較完整／抓取較新者 |

現行 v1 基準（196 筆）離線重播：`total=194 / deduped=2 / rawTotal=196 / withSalary=55`；
舊規則（只看標題＋公司）是 `187 / deduped=9`。兩套數字不必相等。

## HTML 儀表板（`build_dashboard.py`）

**CLI 抓、HTML 讀**：認得 CLI 的 `{"schemaVersion": 2, "jobs": [...]}` 封套、舊職位陣列與
CSV；日期解析**唯一來源是 `hkjobs.aggregate.parse_date`**，`age_days` 以該筆 `scraped_at`
為基準（不是 `date.today()`）。預設 16px、大字模式（20px）、skip link、`<main>`／`<article>`／
`<h3>`、`aria-live`／`aria-pressed`／`aria-expanded`、鍵盤可達的 `<button>` 晶片。
`--out` 純檔名放 `output/` 下；含目錄或絕對路徑照給；寫入失敗印可讀訊息並回 `exit 2`，
不丟 traceback。

## 輸出契約（schemaVersion = 2，2026-11-11 起）

成功：

```json
{"schemaVersion":2,"command":"search","generatedAt":"…","query":{…,"sortBy":"date","dedup":true},
 "summary":{"total":194,"rawTotal":196,"deduped":2,"withSalary":55,"sortBy":"date",
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
- 變更多人類輸出／旗標，必須同步更新：`README.md` 的「給 AI agent／程式呼叫」章節、本文件命令段、`search --help` 的 epilog 與 `hkjobs/args.py` 的旗標說明；若動到離線重播，另同步 `tools/replay_aggregation.py` 與 `tools/README.md`。薪金欄顯示格式另同步 README「薪金換算基準」與本文件「人類模式」段（含範例輸出字串）。
- 新增／調整旗標時，`hkjobs/capabilities.py` 是能力與薪金換算基準的單一資料源（`GAP_FILL_ACTIONS` / `SALARY_CONVERSION_BASIS`），不要在 CLI 裡另寫一份。
- 變更篩選值驗證、引導模式、啟動器或 stdin 編碼，須同步 `hkjobs/validation.py`／`hkjobs/guide.py`／`hkjobs/contract.py`／`start.bat`、`tests/test_dimension_validation.py`／`tests/test_guide.py`／`tests/test_stdin_encoding.py`、本文件專節、README「60 秒上手」第 3／4 步與**運行時結尾提示**。文件裡的編號選項以 `guide.py` 實際順序為準（例如「最近幾天」的 `2` 是 3 天內，不是「3 天」）。
- 變更 README 章節標題或增減主章節，須同步開頭「我該讀哪裡？（受眾路由）」表與「目錄」的 `<a id>` 錨點；求職者路由固定四節（60 秒上手／食譜／儀表板／速率禮節）。技術筆記**只可搬位置或加路由，不得刪內容**；附錄標題層級為 `##` → 各站 `###` → 小節 `####`。
- 變更 HTML 看板，須同步 `build_dashboard.py`、`tests/test_dashboard.py`、README「聚合儀表板」章節；日期解析只能呼叫 `hkjobs/aggregate.py::parse_date`，不得再養第二套 regex。空狀態須區分「總資料 0 筆」（給可照抄的 `--out` 指令，0 檔 HTML 不得摻入「放寬篩選」字樣，連註解也一樣）與「有資料但被篩選濾光」（維持原句）；console 端 0 檔提醒與大字模式／鍵盤可達性一併守住。
- Windows cp950 **同時管輸出與輸入**：所有人類輸出、`build_dashboard.py` 與 `tools/*.py` 的 `--help` 不得因非 cp950 字元 crash；新文字先確認可編碼（`≈`／emoji 不行，`→` `×` `÷` `—` 可以），或在入口呼叫 `contract.configure_io()`。輸入面不得讓管道／agent 送中文時產生 lone surrogate 再炸在 `print()`；新增 `input()` 一律改用 `contract.read_input()`，不得直接呼叫 builtin。`start.bat` 必須維持全 ASCII（含 Python 前提、版本與安裝失敗等所有訊息）。
- 各站功能彼此隔離；不支援的參數一律警告後忽略，不得報錯中斷或影響他站。**但「該站支援且字典打錯」屬另一情境，須 exit 2 擋下**（見本文件「篩選值前置驗證」）。
- 執行 `python -m unittest discover -s tests`（零網路）必須全綠；目前 405 個測試。
- 變更聚合層（正規化／去重／排序／完整度）須同步 `hkjobs/aggregate.py`、`hkjobs/contract.py` 的 `SCHEMA_VERSION`、本文件對照表與 README；去重數字改動時一併更新 `tools/README.md` 的基準說明。
