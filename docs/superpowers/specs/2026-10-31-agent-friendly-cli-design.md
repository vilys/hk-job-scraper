# hkjobs — Agent 友善 CLI 契約（設計文件）

- 日期：2026-10-31
- 狀態：已與使用者確認方向（形態＝Agent 友善 CLI 契約；相容策略＝完全相容；輸出＝純 stdout、無副作用；附屬命令＝`sources` + `options`；路線＝薄外掛）
- 相關文件：`README.md`（功能與各站技術筆記）、`AGENTS.md`（本設計新增）

## 1. 背景與問題

本專案目前只有 `python main.py` 一種入口，且是為「人在終端機手動操作」設計的：

1. **不可安裝**：靠 `sys.path.insert` 才能 import；agent 必須知道 repo 絕對路徑。
2. **無機器可讀契約**：結果只寫檔（`output/*.json`），stdout 只有日誌；agent 得猜檔名、再讀檔。
3. **成敗不可判定**：`main.py` 對每站 `except Exception` 後繼續，且永遠 `exit 0`；agent 無法區分「沒職缺」與「被反爬擋住」。
4. **能力與字典散落**：12 站支援哪些參數散在 1,745 行 README 的矩陣與 18 個 JSON 字典中，agent 只能硬編碼或全文閱讀，極易幻覺。
5. **有副作用且不可預期**：寫檔固定落 `output/`、預設增量合併舊資料；agent 每次呼叫都可能改動磁碟狀態。

## 2. 目標 / 非目標

### 目標

- 提供可安裝的 `hkjobs` 命令，三個子命令：`search`、`sources`、`options`。
- `--json` 機器模式：stdout 只有**一個** JSON 物件；預設**不寫任何檔案**；日誌全走 stderr。
- 以 exit code 明確區分成功／參數錯／部分失敗／全失敗／零結果。
- 能力矩陣與字典可自描述查詢，agent 不必讀 README 或 JSON 檔。
- 根目錄 `AGENTS.md` 說明安裝、契約、探索流程、速率禮節與安全規則。
- **完全相容**：既有 `python main.py ...` 的參數、預設值、輸出檔行為、exit 行為一律不變。

### 非目標（本期不做）

- MCP server、HTTP API 服務。
- `schema`、`doctor`、`--dry-run` 子命令（使用者未選；契約保留未來擴充空間）。
- 併發抓取、排程、資料庫。
- 搬動既有模組或改寫 14 個爬蟲的 import（見「風險」）。

## 3. 使用者與成功標準

| 使用者 | 成功標準 |
|---|---|
| AI agent（Claude／Cursor／Qoder 等） | 只讀 `AGENTS.md` 或 `hkjobs --help`，就能完成「查據點 → 查有效值 → 搜尋 → 解析結果 → 依 exit code 決策」，全程不需進 repo 目錄或讀原始碼 |
| 一般使用者 | `pipx install .` 或 `pip install -e .` 後在任意目錄使用 `hkjobs`；原有 `python main.py` 文件不需改寫 |

## 4. 架構

### 4.1 檔案佈局（既有程式碼僅 `main.py` 改參數定義；另更新 `.gitignore` 與 README 文件）

```
hk-job-scraper/
├── pyproject.toml            # 新增：打包與 console script
├── AGENTS.md                 # 新增：agent 操作手冊
├── main.py                   # 修改：build_argparser() 改呼叫 hkjobs.args（行為不變）
├── hkjobs/
│   ├── __init__.py           # 版本號 __version__
│   ├── __main__.py           # python -m hkjobs
│   ├── cli.py                # 子命令分派；main(argv) -> int
│   ├── args.py               # search 參數定義（唯一來源，main.py 共用）
│   ├── capabilities.py       # 12 站能力表（單一真相來源）
│   ├── options.py            # 字典 adapter：(source, dimension) -> list[OptionEntry]
│   └── contract.py           # 封套組裝、exit code、stdout/stderr、UTF-8 設定
├── scrapers/                 # 不動
├── config.py base_scraper.py exporter.py job_model.py   # 不動
└── tests/test_cli_contract.py # 新增
```

### 4.2 依賴方向

`hkjobs.cli` → `hkjobs.args` / `hkjobs.contract` / `hkjobs.capabilities` / `hkjobs.options` → `scrapers.SCRAPERS`、`job_model.JobRecord`、`exporter`。
`main.py` → `hkjobs.args`（僅此一條，避免循環依賴）。
`hkjobs` 不 import `main`。

### 4.3 打包（`pyproject.toml`）

- build backend：setuptools（扁平佈局，不搬檔）
- `name = "hk-job-scraper"`、`dynamic = ["version"]`（版本單一來源：`hkjobs.__version__ = "0.1.0"`，由 setuptools `attr` 讀取）、`requires-python = ">=3.10"`
- `dependencies = ["requests>=2.31", "beautifulsoup4>=4.12", "lxml>=5.0"]`
- `[project.optional-dependencies] browser = ["playwright>=1.40"]`
- `[project.scripts] hkjobs = "hkjobs.cli:main"`
- `[tool.setuptools] py-modules = ["config", "base_scraper", "exporter", "job_model"]`、`packages = ["hkjobs", "scrapers"]`
- `[tool.setuptools.package-data] scrapers = ["*.json"]`
- `.gitignore` 增列 `build/`、`dist/`、`*.egg-info/`
- `requirements.txt` 保持不變（仍為「完整安裝」）
- 文件註明：建議 `pipx install .` 或 `pip install -e .`；不建議非隔離安裝（頂層 `config` 模組名可能與其他套件衝突）

## 5. 命令介面

全域：`hkjobs [-h] {search,sources,options} ...`；`hkjobs --version` 輸出 `hkjobs 0.1.0`。

### 5.1 `hkjobs search`

輸入旗標與 `main.py` **完全相同**（共用 `hkjobs.args`，含 help 文字與預設值）：

| 旗標 | 預設 | 說明 |
|---|---|---|
| `--source` | `moovup` | 12 站之一或 `all`（僅跑 `enabled=True`） |
| `--keyword` | `""` | 留空＝僅瀏覽 |
| `--pages` | `3` | 最大翻頁數 |
| `--days` | 無 | 近 N 天內刊登 |
| `--district` / `--category` / `--industry` / `--sort` | 無 | 各站支援度見 `sources` |
| `--detail` / `--fill-location` | 關 | 同原行為 |

輸出旗標（新）：

| 旗標 | 說明 |
|---|---|
| `--json` | 機器模式：stdout 輸出單一 JSON 封套；不寫檔；日誌走 stderr（預設 WARNING 級） |
| `--out PATH` | 顯式寫檔。`.csv` → 職位 CSV（UTF-8 BOM）；其他副檔名 → JSON（`--json` 時寫完整封套，否則寫職位陣列） |
| `-q, --quiet` | 日誌只留 ERROR |

- 無 `--json`（人類模式）：終端印各站摘要與總筆數，並提示 `--out` 用法；**不寫檔**。
- `--source all`：順序執行 `enabled` 站；停用站位於 `summary.sources[]` 中標記 `skipped`，並印一次 warning。

### 5.2 `hkjobs sources`

- 無參數。列出 12 站能力（資料來自 `capabilities.py`）。
- `--json` 輸出見 §7.2；人類模式印固定寬度表格（站名／啟用／瀏覽器／每頁／支援維度／近 N 天機制）。

### 5.3 `hkjobs options`

| 旗標 | 必填 | 說明 |
|---|---|---|
| `--source` | 是 | 具體站名（不接受 `all`；否則 exit 2） |
| `--dimension` | 否 | `district` / `category` / `industry` / `sort`；預設全部 |
| `--json` | 否 | 機器模式；人類模式印「維度 → 值（別名）」清單 |

- 不支援的維度在 JSON 中為 `null`；`--dimension industry --source jobsdb` → `{"dimensions":{"industry":null}}`，exit 0（不報錯，符合「不支援即忽略」的專案精神）。

## 6. 輸出契約

### 6.1 成功封套（`--json`）

```json
{
  "schemaVersion": 1,
  "command": "search",
  "generatedAt": "2026-10-31T04:12:33Z",
  "query": {
    "source": "jobsdb", "keyword": "data", "pages": 2, "days": 7,
    "district": null, "category": null, "industry": null,
    "sort": "post_dt_desc", "detail": false, "fillLocation": false
  },
  "summary": {
    "total": 37,
    "withSalary": 12,
    "sources": [
      {"name": "jobsdb", "status": "ok", "jobs": 37, "error": null}
    ]
  },
  "jobs": [
    {"job_id": "jobsdb::123", "source": "jobsdb", "title": "…", "company": "…",
     "location": "…", "salary": "…", "job_type": "…", "industry": "…",
     "description": "…", "requirements": "…", "url": "…",
     "posted_date": "2026-10-29", "scraped_at": "2026-10-31T04:10:02+00:00"}
  ]
}
```

- `jobs` 與 `JobRecord.to_dict()` 欄位**完全一致**（13 欄），不新增、不改名。
- `summary.withSalary`：`salary` 字串非空的筆數（列表層未必有薪資，`--detail` 可補）。
- `--source all` 時 `query.source` 為 `"all"`，逐站結果見 `summary.sources`。
- `summary.sources[].status` ∈ `ok` / `failed` / `skipped`；失敗時 `error` 為字串訊息。
- `query.sort` 回報**實際生效值**（`--days` 未給 `--sort` 時自動為 `post_dt_desc`）。

### 6.2 錯誤封套

```json
{"schemaVersion":1,"command":"search",
 "error":{"code":"all_sources_failed","message":"所有來源均失敗：jobsdb, linkedin"},
 "summary":{"total":0,"withSalary":0,"sources":[{"name":"jobsdb","status":"failed","jobs":0,"error":"HTTP 403"}]},
 "jobs":[]}
```

`error.code` ∈ `partial_failure` / `all_sources_failed` / `no_results` / `unexpected`。
（`usage` 類錯誤由 argparse 處理，見 §6.4。）

### 6.3 exit code

| 值 | 意義 | 對應 error.code |
|---|---|---|
| 0 | 成功且 ≥1 筆 | `null` |
| 2 | 參數／用法錯誤（未知 source、無效 dimension、`options` 傳 `all`） | 無封套 |
| 3 | 部分來源失敗（至少一站失敗、其餘完成） | `partial_failure` |
| 4 | 全部來源失敗 | `all_sources_failed` |
| 5 | 所有來源成功但 0 筆 | `no_results` |
| 1 | 未預期例外（bug） | `unexpected` |

優先序：`1 > 4 > 3 > 5 > 0`。舊 `python main.py` 的 exit 行為不變（永遠 0）。

### 6.4 stdout / stderr 規則

- `--json`：stdout 僅有單一 JSON 物件（含失敗）；日誌固定 stderr，預設 WARNING。
- 非 `--json`：stdout 為人類摘要；日誌 stderr（INFO）。
- argparse 的用法錯誤維持原生行為：usage 印 stderr、exit 2、**不保證有 JSON 封套**（`--json` 放在無效參數之後時亦然）。文件明確說明。
- `hkjobs` 啟動時把 stdout/stderr 重新設為 UTF-8（`sys.stdout.reconfigure(encoding="utf-8")`），避免 Windows cp950 下輸出中文 JSON 失敗；`--out` 一律以 UTF-8 寫入（CSV 依 §5.1 帶 BOM）。

## 7. 能力表（`hkjobs/capabilities.py`）

### 7.1 資料結構

```python
@dataclass(frozen=True)
class SourceInfo:
    name: str                 # 與 SCRAPERS key 一致
    label: str                # 中文名，例如「勞工處」
    enabled: bool
    needs_browser: bool
    needs_chrome: bool        # 必須本機 Chrome（channel="chrome"）
    per_page: int             # 站方每頁筆數（上限或典型值）
    keyword_required: bool
    days_mode: str            # server | list | detail | approx | none
    sort_values: tuple[str, ...]   # CLI 接受且有意義的 --sort 值
    supports: dict[str, bool]      # district/category/industry/detail/fillLocation
    request_delay: float
    notes: str
```

`days_mode` 語意（給 agent 估算成本）：
- `server`：站方端參數，**0 額外請求**
- `list`：列表已含日期，客戶端過濾，**0 額外請求**
- `detail`：需逐筆抓詳情取日期（每筆 +1 請求）
- `approx`：以站方「刷新日」近似，非精確刊登日
- `none`：不支援，傳入會警告並忽略
- `per_page` 存站方典型／上限值；特例（LinkedIn 首頁 58、續頁 10）寫入 `notes`。
- `valueCounts` **不寫死在能力表**：`sources` 輸出時由 `options` adapter 即時計算（含子項），避免與字典檔漂移。

### 7.2 12 站內容（依 README 矩陣與 class 旗標）

| source | label | enabled | browser | chrome | perPage | keyword | days | sort values | district | category | industry | detail | fillLoc | delay |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| moovup | 好工速遞 | ✓ | ✓ | | 12 | 建議 | none | — | 32（shortCode） | — | — | ✓ | | 1.5 |
| gov_hk | 勞工處 | ✓ | | | 20 | 可留空 | server | 8 值全支援 | 27 | 29 | 27 | ✓ | | 2.0 |
| jobsdb | JobsDB | ✓ | ✓ | | 20–30（記 20） | 可留空 | server | post_dt_desc | 40（slug） | 30（slug） | — | ✓ | | 2.0 |
| linkedin | LinkedIn | ✓ | | | 58（首頁；續頁 10） | 可留空 | server | post_dt_desc | 20（geoUrn 字典；README 舊稱 18） | — | — | ✓ | | 5.0 |
| indeed | Indeed | ✗ | ✓ | ✓ | 16 | **必給** | server | — | 自由文字 | — | — | ✓ | | 3.0 |
| recruit | Recruit | ✓ | ✓ | | 25 | 可留空 | list | 8 值（asc 以站方 desc 近似並警告） | 94 | 324 | — | ✓ | ✓ | 2.0 |
| jobmarket | JobMarket 求職廣場 | ✓ | | | 20 | 可留空 | list | — | 80 | 223 | 30 | ✓ | | 1.5 |
| foundit | foundit | ✓ | ✓ | ✓ | 20 | 可留空 | list | — | 46（slug） | — | — | ✓ | | 2.0 |
| efc | eFinancialCareers | ✓ | | | 50 | 可留空 | list | — | 3 | — | — | ✓ | | 1.5 |
| liepin | 獵聘 | ✗ | ✓ | ✓ | 40 | 可留空 | approx | — | 18（`districts`）＋城市映射 | — | — | — | | 8.0 |
| zhipin | BOSS直聘 | ✗ | ✓ | ✓ | 0 | 可留空 | none | — | — | — | — | — | | 5.0 |
| offertoday | OfferToday | ✓ | | | 10 | 可留空 | server | — | 18＋129 子區 | 31＋431 細類 | 15＋53 細類 | ✓ | | 3.0 |

- `sort_values` 的值域固定為 `post_dt_desc` / `post_dt_asc` / `salary_desc` / `salary_asc` / `yr_exp_desc` / `yr_exp_asc` / `edu_lvl_desc` / `edu_lvl_asc`。
- 表中數字為目前字典規模，僅供閱讀；`--json` 的 `valueCounts` 一律即時計算。
- `notes` 保存各站關鍵提醒（例如 recruit 需 `--fill-location`、indeed 必給關鍵字、offertoday 只認 `on MM-DD`）。

### 7.3 `sources --json` 輸出

```json
{"schemaVersion":1,"command":"sources","generatedAt":"…",
 "sources":[{ "name":"gov_hk","label":"勞工處","enabled":true,
   "needsBrowser":false,"needsChrome":false,"perPage":20,
   "keywordRequired":false,"daysMode":"server",
   "sortValues":["post_dt_desc","…"],
   "supports":{"district":true,"category":true,"industry":true,"detail":true,"fillLocation":false},
   "valueCounts":{"district":27,"category":29,"industry":27},
   "requestDelaySeconds":2.0,
   "notes":"…" }],
 "presets":{"all":["moovup","gov_hk","…"]}}
```

`presets.all` 只含 `enabled` 站，與 `search --source all` 行為一致。

### 7.4 防漂移

契約測試對每個來源交叉核對：`enabled` / `needsBrowser` 與 `cls.enabled` / `cls.use_browser` 一致；`days_mode` 屬合法列舉；`sort_values` ⊆ 8 值；`sources` 筆數 = `len(SCRAPERS)`；每個 `supports=True` 的維度都能產出 `options` 資料。README 的「各站功能支援矩陣」在實作時同步更新（僅在表格下方補一句：機器可讀版本見 `hkjobs sources --json`）。

## 8. 字典查詢（`hkjobs/options.py`）

### 8.1 正規化條目

```json
{"id": "central", "name": "中環", "aliases": ["central", "中環"], "parentId": null}
```

- `id`：站方識別碼（shortCode／數字 ID／slug／geoUrn）；無則 `null`
- `name`：首選顯示名（中文優先）
- `aliases`：其他可接受的寫法（含英文、別名）
- `parentId`：巢狀字典（offertoday／jobmarket 細類）指向父項 `id`，否則 `null`
- 不修改、不複製字典檔；adapter 只做形狀轉換，**值域以 JSON 檔實際內容為準**

### 8.2 adapter 對照

| source | district | category | industry |
|---|---|---|---|
| moovup | `moovup_districts.json`（shortCode／zh／en） | — | — |
| gov_hk | `gov_hk_districts.json`（id／name） | `gov_hk_categories.json` | `gov_hk_industries.json` |
| jobsdb | `jobsdb_districts.json`（slug／zh） | `jobsdb_classifications.json`（slug／zh／name） | — |
| linkedin | `linkedin_geo.json`（districts＋aliases） | — | — |
| indeed | 自由文字（kind=`free`，values=[]） | — | — |
| recruit | `recruit_districts.json` | `recruit_categories.json` | — |
| jobmarket | `jobmarket_districts.json` | `jobmarket_categories.json` | `jobmarket_industries.json` |
| foundit | `foundit_locations.json` | — | — |
| efc | `efc_geo.json` | — | — |
| liepin | `liepin_areas.json`（districts＋city） | — | — |
| zhipin | — | — | — |
| offertoday | `offertoday_areas.json`（大區＋children） | `offertoday_categories.json` | `offertoday_industries.json` |

### 8.3 `options --json` 輸出

```json
{"schemaVersion":1,"command":"options","source":"jobsdb","generatedAt":"…",
 "dimensions":{
   "district":{"kind":"single","accepts":["zh","slug"],"count":40,
               "values":[{"id":"central","name":"中環","aliases":["central","中環"],"parentId":null}]},
   "category":{"kind":"single","accepts":["zh","en","slug"],"count":30,"values":["…"]},
   "industry":null,
   "sort":{"kind":"enum","values":["post_dt_desc"]}}}
```

- `kind`：`single`（`--district` 逗號多值時 JobsDB 只取第一個）／`multi`（可逗號多值）／`free`（自由文字）／`enum`（排序）
- `count` 為實際可傳入的葉節點數（含子項）
- 支援但字典為空（如 indeed 自由文字）→ `{"kind":"free","accepts":["free_text"],"count":0,"values":[]}`
- `sort`：`sort_values` 為空時整個維度為 `null`；`zhipin` 等全無字典的站，三個維度與 `sort` 皆為 `null`，exit 0

## 9. 相容性與部署

- `main.py`：`build_argparser()` 改為 `return build_search_argparser(description="香港求職網站自動搜尋程式")`；其餘 `main()` 邏輯、輸出檔命名、日誌格式、exit 行為**一律不動**。
- `scrapers/*`、`config.py`、`base_scraper.py`、`exporter.py`、`job_model.py`：**零改動**。
- `requirements.txt`：不變。
- 既有 32 個測試：必須全綠。
- 執行期新依賴：**0**（只用 argparse／json／dataclasses／pathlib 標準庫）。
- Python 下限：3.10（沿用 README）。

## 10. 文件

### 10.1 `AGENTS.md`（新增，根目錄）

1. 專案一句話說明與能力邊界（能做什麼／不能做什麼）
2. 安裝：`pipx install .`／`pip install -e .`／`python -m hkjobs`
3. **探索流程（強制順序）**：`sources` → `options` → `search`，禁止硬編碼站名與字典值
4. 命令參考與最小範例（含 `jq` 取值範例）
5. JSON 封套欄位與 exit code 表
6. 速率禮節：順序執行、勿並行同站、首次先 `--pages 1`、間隔 1.5–8 秒不可調小
7. 安全與隱私：`LINKEDIN_LI_AT` 等同帳號憑證，不得輸出／提交；輸出可能含個資
8. 舊 `python main.py` 仍可用，但無機器契約與嚴格 exit code
9. 指向 README「開發規範」：新增據點必須補技術筆記與更新能力表

### 10.2 `README.md`

- 「60 秒上手」後補一小段「想用 `hkjobs` 命令 / 給 agent 用？見 `AGENTS.md`」
- 新增「🤖 給 AI agent／程式呼叫」一節：三個命令、`--json` 範例、exit code 表、指向 `AGENTS.md`
- 更新「📁 專案結構」樹（`hkjobs/`、`pyproject.toml`、`AGENTS.md`）
- 支援矩陣下方註明「機器可讀版本：`hkjobs sources --json`」

## 11. 測試計畫（全部零網路）

新增 `tests/test_cli_contract.py`：

| # | 測試 | 驗證 |
|---|---|---|
| 1 | 能力表覆蓋 | 每站存在、`enabled`/`needsBrowser` 與 class 一致、`daysMode` 合法、`sortValues` ⊆ 8 值 |
| 2 | `sources --json` | 可解析、`schemaVersion==1`、12 站、`presets.all` 只含 enabled |
| 3 | `options` 全組合 | 每個支援維度非空；抽樣精確值：jobsdb `tsuen-wan`/荃灣、gov_hk 會計、offertoday `101000`＋children `parentId`、moovup `000011`、efc `Hong Kong` |
| 4 | `options` 不支援維度 | 回 `null`、exit 0 |
| 5 | `search --json` 成功 | 以假 scraper 注入，stdout 為單一 JSON、`jobs` 13 欄、exit 0、目錄無新檔 |
| 6 | 零結果 | 假 scraper 回 `[]` → exit 5、`error.code=="no_results"` |
| 7 | 部分／全部失敗 | 一好一壞 → exit 3；全壞 → exit 4 |
| 8 | `--out` | `.json` 寫封套、`.csv` 寫 UTF-8 BOM、指定路徑不巢狀 |
| 9 | 用法錯誤 | 未知 source／`options --source all` → exit 2 |
| 10 | 舊 CLI 快照 | `main.build_argparser()` 的 option strings 與預設值與固定清單相同 |
| 11 | UTF-8 | `--json` 模式 stdout encoding 為 utf-8（Windows 模擬） |

驗收（實機、非測試）：
1. venv 內 `pip install -e .`，到 repo **外**目錄執行 `hkjobs sources --json`、`hkjobs --version`。
2. 真跑 `hkjobs search --source gov_hk --keyword 會計 --pages 1 --json`（低負載），確認 stdout 純 JSON、`summary.sources` 正確。
3. `python main.py --source gov_hk --keyword 會計 --pages 1` 行為與改動前一致（輸出檔、日誌、exit 0）。
4. `python -m unittest discover -s tests` 全綠。

## 12. 風險與對策

| 風險 | 對策 |
|---|---|
| 能力表與實際行為漂移 | 交叉測試（§7.4）＋ `AGENTS.md`／README 明文規矩：改站點行為必須同步改 `capabilities.py` |
| 頂層 `config` 模組與他套件撞名（非隔離安裝） | 文件建議 `pipx`／venv／`-e`；長期可再走「完整重構」 |
| argparse 用法錯誤無 JSON | 文件明說：exit 2 時讀 stderr；不要假設一定有封套 |
| 字典數量與 README 舊描述不符（liepin） | adapter 以 JSON 檔為準，測試鎖定實際 count；README 同步更正 |
| Windows 主控台編碼 | `hkjobs` 強制 stdout/stderr UTF-8；`--out` UTF-8 |
| 站方限流／反爬 | 沿用原有間隔與 `enabled` 設計；agent 文件要求 `--pages` 保守、勿並行 |
| `--json` 大結果集佔記憶體 | 本期接受（單站上限小、`--pages` 可控）；不在本期做串流 |

## 13. 驗收定義（Definition of Done）

- [ ] `hkjobs search|sources|options` 三命令可用，`--json` 契約與 §6 完全一致
- [ ] exit code 五種情境皆有測試
- [ ] `hkjobs sources --json` 覆蓋 12 站且與 class 旗標一致
- [ ] `hkjobs options` 對所有支援組合可產出，抽樣值正確
- [ ] `python main.py` 行為與改動前一致（含 exit 0 與輸出檔命名）
- [ ] 既有 32 測試 + 新契約測試全綠
- [ ] `AGENTS.md`、README 新章節、專案結構樹完成
- [ ] `pip install -e .` 後可在 repo 外使用 `hkjobs`
- [ ] 無新增執行期依賴、無搬檔、無改動 14 個爬蟲模組
