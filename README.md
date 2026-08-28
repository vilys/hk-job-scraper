# 香港求職網站自動搜尋程式 (HK Job Scraper)

> ⚠️ **適用範圍備註**：本程式採「一網站一爬蟲模組」設計，目前已完成 **五座據點**：
> - **Moovup 好工速遞（moovup.com）** —— 見「🗺️ 按地區篩選（Moovup）」與「🧭 技術筆記（Moovup）」
> - **勞工處互動就業服務（jobs.gov.hk / www1.jobs.gov.hk）** —— 見「🗺️ 按地區篩選（勞工處）」與「🧭 技術筆記（勞工處）」
> - **JobsDB（hk.jobsdb.com）** —— 見「🗺️ 按地區篩選（JobsDB）」與「🧭 技術筆記（JobsDB）」
> - **LinkedIn（www.linkedin.com）** —— 見「🧭 技術筆記（LinkedIn）」與「🗺️ 按地區篩選（LinkedIn）」
> - **Indeed（hk.indeed.com）** —— 見「🧭 技術筆記（Indeed）」與「🗺️ 按地區篩選（Indeed）」
>
> 各爬蟲模組**僅針對其對應網站**，彼此的資料結構、地區編號體系互不相同（五站的地區字典各自獨立），請勿跨站混用。

模組化、可擴充的香港求職網站爬蟲。目前已完成 **Moovup 好工速遞**、**勞工處 gov.hk**、**JobsDB**、**LinkedIn**、**Indeed** 五座據點並實測通過（見文末路線圖）。

---

## 📌 開發規範（重要！）

> ⚠️ **用戶鐵律：每一家網站（每一座據點）都必須把「爬取方法」在文件上寫清楚，否則時間久了會混亂。**

新增任何據點時，除了寫程式，還**必須**在本文檔為該站補齊以下兩個小節（參考已有的 Moovup 與勞工處範例）：

1. **🧭 技術筆記（站名 逆向要點）** —— 寫清完整方法：
   - 真實網域 / 跳轉規則
   - 搜尋機制（GraphQL API / HTML 表單 / JSON 接口）
   - 反爬保護與繞過方式（Cloudflare / CAPTCHA / 指紋偽裝）
   - 翻頁機制（offset / page / quickview / cursor）
   - 詳情頁解析方式（穩定 id / 選擇器）
   - 地區篩選體系（該站專屬 ID 或編碼）
   - 各欄位資料來源
2. **🗺️ 按地區篩選（站名）** —— 說清該站地區字典與用法。

此外，不同據點的**地區字典 / 資料結構各自獨立，不可跨站混用**；技術筆記也只針對該站。

此外，**各站功能必須彼此隔離**：任一據點新增 / 修改某功能（如 `--sort` 選項、`--days` 行為、地區解析邏輯），不得影響其他據點的既有行為。每一項功能在各站是否支援、如何實作，均由該站爬蟲模組自行決定；不支援的功能應 `logger.warning` 後忽略並提示，絕不可報錯中斷或靜默改變其他站的輸出。新增據點時須同步更新下方「📊 各站功能支援矩陣」。

---

## ✨ 功能特性

- **統一資料模型**：所有網站產出同一套 `JobRecord`（13 個標準欄位），方便合併與去重。
- **多格式匯出**：JSON / CSV（UTF-8 BOM，Excel 直接開不亂碼），支援增量寫入與 `job_id` 去重。
- **Moovup 據點已實戰驗證**：
  - 透過 Playwright 真實瀏覽器自動繞過 Cloudflare Turnstile。
  - 在瀏覽器上下文內呼叫官方 GraphQL API，解析結構化 JSON（比啃 DOM 穩定）。
  - 支援關鍵字搜尋、分頁、職位詳情（職責 / 要求 / 發佈時間）。
  - **支援按地區篩選**（中文名 / 英文名 / 編號皆可，見下方「按地區篩選（Moovup）」）。
- **勞工處 gov.hk 據點已實戰驗證**：
  - 傳統 ASP.NET MVC 伺服器渲染，**無 Cloudflare、無 CAPTCHA**，僅用 `requests` + `BeautifulSoup` 即可。
  - 搜尋：POST 搜尋表單 → 後續頁 GET `quickview?page=N` 翻頁（每頁約 20 筆）。
  - 詳情：解析職位卡頁 `#empName`(公司) / `#jobRemark`(職責) / `#eduRemark`(要求) / `#postedDt`(**刊登日期 `DD/MM/YYYY`**) 等穩定 id。
  - **支援按地區篩選**（勞工處專屬數字 ID，見下方「按地區篩選（勞工處）」）。
  - **支援按工作種類 / 行業篩選**（見下方「按工作種類 / 行業篩選（勞工處）」）。
  - **支援時間排列與近期篩選**：`--sort` 依刊登日期/薪資/經驗/學歷排序；`--days N` 只留最近 N 天內刊登（見下方「按刊登日期排序 / 近期篩選（勞工處）」）。
  - **支援按工作種類 / 行業篩選**（勞工處 `criteria.jobType` / `criteria.industry` 兩套獨立維度，見下方「按工作種類 / 行業篩選（勞工處）」）。
- **JobsDB 據點已實戰驗證**：
  - React SSR + Cloudflare。用 Playwright 真瀏覽器訪首頁取得 `cf_clearance` Cookie，**共用同一 session**，不硬撞 GraphQL。
  - 職位列表是**伺服器渲染**進 `/jobs?keywords=K&page=N` 的 HTML（卡片用 `data-automation='normalJob'`），**非 GraphQL 列表呼叫**——故每頁只需 1 次 GET，比硬刷 API 安全得多。
  - **支援關鍵字搜尋 + `?page=N` 翻頁**（每頁約 20–30 筆）。
  - **支援職能（工作種類）+ 地區篩選**：`--category`（職能，中文/英文/slug，如 `資訊及通訊科技`）與 `--district`（地區，中文/slug，如 `荃灣`）已接上，透過 `/jobs-in-<職能>/in-<地區>` 瀏覽網址實現（見下方「🗺️ 按地區篩選（JobsDB）」）。
  - **支援近期篩選 `--days N`**：列表頁已含相對刊登日（如 `7d ago`），直接由列表過濾，不必抓 30 筆詳情/頁（與 gov.hk 不同）。
  - **支援排序 `--sort`**：JobsDB 網站 UI 僅提供「相關性（預設）」與「刊登日期（Date）」兩種排序。對應實作：`--sort post_dt_desc` → 網址加 `?sortmode=ListedDate`（新→舊，已實測 1h→2h→3h 遞增）；其餘選項（`post_dt_asc` / `salary_*` / `yr_exp_*` / `edu_lvl_*`）為 gov_hk 專有，JobsDB 無對應 UI，傳入會警告並回退預設。`--days` 未指定 `--sort` 時自動套 `post_dt_desc`，讓新職位堆在前、提早停翻（見下方「🧭 技術筆記（JobsDB）」）。
  - **不支援項**：`--industry`（JobsDB 無獨立行業維度，職能已涵蓋，傳入會忽略並提示）。
- **LinkedIn 據點已實戰驗證（訪客模式）**：
  - **無須登入、無須 Playwright**：職位搜尋結果為**伺服器渲染 HTML**（plain `requests` + `BeautifulSoup` 即可），詳情另有**免登入 guest API** `jobs-guest/jobs/api/jobPosting/<id>`。比前幾站更輕量。
  - **支援關鍵字搜尋 + 地點**：`/jobs/search/?keywords=K&location=Hong%20Kong`；`--district` 經 18 區字典（`scrapers/linkedin_geo.json`）翻譯成英文區名餵給 `location=`（中文「元朗」→`Yuen Long`，含旺角/銅鑼灣等別名）。⚠️ 訪客模式 `geoUrn=` 無效，故走 `location=` 文字。
  - **支援近期篩選 `--days N`**：列表卡已含相對刊登日（`4 days ago` / `1 week ago`，強制英文語系以利解析），直接由列表過濾，不必抓詳情。
  - **支援排序 `--sort post_dt_desc`**：對應網址 `sortBy=DD`（最新優先），並讓 `--days` 提早停翻；其餘選項為 gov_hk 專有，傳入會警告並回退預設。
  - **跨頁去重 + 提早停翻**：LinkedIn 訪客模式深翻頁（`start`）行為不穩定（會隨機化/AB 測試），故以 `job_id` 去重，整頁皆已見即停，避免無限迴圈。穩定深翻頁需登入態 `li_at` cookie（見下方技術筆記）。
  - **不支援項**：`--category` / `--industry`（LinkedIn 簡易搜尋無乾淨對應維度，傳入會忽略並提示）。
  - ⚠️ **訪客模式天花板**：未登入時單次執行約可拿 ~25–60 筆獨特職位（受隨機化翻頁限制）；提供 `li_at` cookie 後翻頁趨於穩定、可抓更深。
- **禮貌爬取**：請求間隔 + 隨機抖動 + 失敗重試（指數退避），降低被封風險。

---

## 📁 專案結構

```
hk-job-scraper/
├── main.py                 # 統一命令列入口
├── config.py               # 全域設定：請求間隔 / UA / 輸出目錄 / 各站選擇器
├── job_model.py            # JobRecord 統一資料模型
├── exporter.py             # JSON / CSV 匯出（增量 + 去重）
├── base_scraper.py         # 爬蟲抽象基類（search / get_detail / scrape_all）
├── build_dashboard.py      # 聚合 output/ 所有產出 → 單檔離線 HTML 儀表板
├── scrapers/
│   ├── __init__.py         # 爬蟲註冊表（SCRAPERS）
│   ├── moovup.py           # Moovup 爬蟲（已實作 + 實測）
│   ├── moovup_districts.json  # Moovup 地區字典（32 區：中文名/英文名/shortCode/_id）
│   ├── gov_hk.py           # 勞工處爬蟲（已實作 + 實測）
│   ├── gov_hk_districts.json  # 勞工處地區字典（27 項：數字 ID → 地區名）
│   ├── gov_hk_categories.json # 勞工處工作種類字典（29 類：數字 ID → 類別名）
│   ├── gov_hk_industries.json # 勞工處行業字典（27 業：數字 ID → 行業名）
│   ├── jobsdb_classifications.json # JobsDB 職能字典（30 個：name/zh/slug）
│   ├── jobsdb_districts.json # JobsDB 地區字典（40 個：zh/slug，已驗證）
│   └── jobsdb.py            # JobsDB 爬蟲（已實作 + 實測；關鍵字+翻頁+--days+職能/地區篩選）
├── docs/
│   └── moovup_地區編號對照表.md    # 人可直讀的 Moovup 地區↔編號對照表
├── output/                 # 匯出檔案目錄（自動建立）
└── requirements.txt
```

---

## ⚙️ 環境要求與安裝

- Python 3.10+
- 僅 **Moovup** 與 **JobsDB** 需要 Playwright 的 Chromium 瀏覽器；**勞工處 gov.hk** 只需 `requests` + `beautifulsoup4`，不需瀏覽器。

```bash
# 1. 建立並啟用虛擬環境（建議）
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. 安裝依賴
pip install -r requirements.txt

# 3. 安裝 Playwright 瀏覽器（首次必需，只需一次）
playwright install chromium
```

> 依賴：`requests`、`beautifulsoup4`、`lxml`、`playwright`
> （後續階段的 gov.hk 等不需要 Playwright，屆時可只裝基礎套件。）

---

## 🚀 快速開始

```bash
# 搜尋「會計」，抓 3 頁，匯出 JSON（預設）
python main.py --source moovup --keyword "會計" --pages 3

# 同時匯出 JSON 與 CSV，並抓取每筆職位的詳情
python main.py --source moovup --keyword "會計" --pages 5 --output both --detail

# 勞工處 gov.hk：搜尋「會計」，抓 2 頁（每頁約 20 筆）
python main.py --source gov_hk --keyword "會計" --pages 2

# 勞工處 + 詳情 + 雙格式
python main.py --source gov_hk --keyword "零售" --pages 3 --output both --detail

# LinkedIn：訪客模式搜尋（無須登入），抓 3 頁
python main.py --source linkedin --keyword "data engineer" --pages 3
```

抓取的結果會寫入 `output/<source>_<keyword>.json`（與 `.csv`），例如 `output/moovup_會計.json`、`output/gov_hk_會計.json`。

---

## 📖 完整命令列參數

| 參數 | 必填 | 預設 | 說明 |
|------|------|------|------|
| `--source` | 否 | `moovup` | 爬蟲來源：`moovup` \| `gov_hk` \| `jobsdb` \| `linkedin` \| `all` |
| `--keyword` | 否 | 空 | 搜尋關鍵字（繁體中文或英文皆可；**留空 = 不限定關鍵字，僅依地區/類別瀏覽，gov_hk 支援**；JobsDB 留空則搜全站） |
| `--pages` | 否 | `3` | 最大翻頁數（Moovup 每頁約 12 筆；gov.hk 每頁約 20 筆；JobsDB 每頁約 20–30 筆） |
| `--output` | 否 | `json` | 輸出格式：`json` \| `csv` \| `both` |
| `--detail` | 否 | 關 | 同時抓取每筆職位的詳情（職責 / 要求 / 發佈時間 / **刊登日期**）；**JobsDB 的 `--detail` 為 best-effort**，詳情頁選擇器與列表略有差異，實測微調中 |
| `--outfile` | 否 | 自動命名 | 自訂輸出檔名（不含副檔名），預設 `output/<source>_<keyword>` |
| `--district` | 否 | 無 | 地區篩選（**Moovup / 勞工處 / JobsDB 均已接上**）。JobsDB 用中文名或 slug（如 荃灣 \| tsuen-wan，見 `scrapers/jobsdb_districts.json`，**40 個已驗證**）；多個以逗號分隔時 JobsDB 僅取第一個。 |
| `--category` | 否 | 無 | 工作種類 / 職能篩選（**勞工處 + JobsDB 已接上**）。JobsDB 用中文名 / 英文 / slug（如 `資訊及通訊科技` \| `Information & Communication Technology`，見 `scrapers/jobsdb_classifications.json`，**30 個含 slug**）。兩站字典獨立。 |
| `--industry` | 否 | 無 | 行業篩選（**僅 gov_hk 支援**；JobsDB 無獨立行業維度，傳入會被忽略並提示） |
| `--sort` | 否 | 無 | 排序：**gov_hk 全選項支援**（`post_dt_desc`(新→舊) / `post_dt_asc`(舊→新) / `salary_desc`·`salary_asc`(月薪) / `yr_exp_asc`·`yr_exp_desc`(經驗) / `edu_lvl_asc`·`edu_lvl_desc`(學歷)）；**JobsDB 僅支援 `post_dt_desc`**（對應網址 `?sortmode=ListedDate`，新→舊），其餘選項為 gov_hk 專有、傳入會警告並回退預設。設 `--days` 未指定 `--sort` 時自動套 `post_dt_desc` |
| `--days` | 否 | 無 | 只保留最近 N 天內刊登的職位。**勞工處**：自動抓詳情取刊登日期，並預設按日期由近至遠排序；**JobsDB**：列表頁已含相對刊登日（`7d ago`），直接由列表過濾，不必抓詳情 |

### 📊 各站功能支援矩陣（重要：功能互不相連）

> ⚠️ **不同站點的功能彼此獨立**：下表每一格的支援方式、參數語意、字典都**只屬於該站**。
> 任一站新增 / 修改某功能（如排序選項、地區解析）**不會影響其他站**。
> 不支援的功能一律 `logger.warning` 後忽略並提示，絕不報錯中斷或改變他站輸出。

| 功能 / 參數 | Moovup | 勞工處 gov.hk | JobsDB | LinkedIn | Indeed |
|------|------|------|------|------|------|
| 關鍵字 `--keyword` | ✅ 支援 | ✅ 支援 | ✅ 可留空 | ✅ 支援 | ✅ 支援 |
| 地區 `--district` | ✅ shortCode（32 區） | ✅ 數字 ID（27 項） | ✅ slug（40 區） | ✅ 18 區字典（zh→英文 `location=`；geoUrn 訪客模式無效） | ✅ 自由文字 `l=`（預設 Hong Kong） |
| 職能 / 工作種類 `--category` | ❌ 不適用 | ✅ 數字 ID（29 類） | ✅ slug（30 職能） | ❌ 不適用 | ❌ 不適用 |
| 行業 `--industry` | ❌ 不適用 | ✅ 數字 ID（27 業） | ❌ 職能已涵蓋 | ❌ 不適用 | ❌ 不適用 |
| 排序 `--sort` | ❌ 不適用 | ✅ 8 選項全支援 | ⚠️ 僅 `post_dt_desc` | ⚠️ 僅 `post_dt_desc` | ❌ 不適用（訪客） |
| 近期 `--days` | ❌ 不適用 | ✅ 抓詳情取日期 | ✅ 列表含日期 | ✅ 列表含日期 | ✅ 內嵌 pubDate 瞬時（~9s，不點擊） |
| 詳情 `--detail` | ✅ 支援 | ✅ 支援 | ⚠️ best-effort | ✅ 免登入 API | ✅ 詳情面板（JS 點擊，~1s/張） |
| 瀏覽器 Playwright | ✅ 需 | ❌ 不需 | ✅ 需 | ❌ 不需 | ✅ 需（Cloudflare） |
| 深翻頁穩定度 | ✅ cursor | ✅ quickview | ✅ page | ⚠️ 訪客 ~60 筆；`li_at` cookie 解鎖 | ⚠️ `start=N`；cf_clearance 沿用，`--days` 已無需點擊、`--detail` 改 JS 點擊提速 |

> 圖例：✅ 完全支援　⚠️ 部分 / 有限支援　❌ 不適用（傳入會警告並忽略）

### 使用範例

```bash
# 1) 基本搜尋 + JSON（Moovup）
python main.py --source moovup --keyword "零售" --pages 2

# 2) 雙格式 + 詳情（Moovup）
python main.py --source moovup --keyword "工程師" --pages 3 --output both --detail

# 3) 自訂檔名
python main.py --source moovup --keyword "侍應" --pages 2 --output csv --outfile waiter_jobs

# 4) 按地區篩選（Moovup，中文名）
python main.py --source moovup --keyword "會計" --district "深水埗" --pages 3

# 5) 按地區篩選（Moovup，英文名 / 編號，效果相同）
python main.py --source moovup --keyword "會計" --district "Sham Shui Po"
python main.py --source moovup --keyword "會計" --district "000017"

# 6) 多個地區（Moovup，逗號分隔）
python main.py --source moovup --keyword "兼職" --district "深水埗,觀塘,油尖旺" --pages 3

# 7) 勞工處：基本搜尋
python main.py --source gov_hk --keyword "會計" --pages 2

# 8) 勞工處：按地區篩選（中文名，自動轉換為勞工處數字 ID）
python main.py --source gov_hk --keyword "會計" --district "屯門" --pages 2

# 9) 勞工處：詳情 + 雙格式
python main.py --source gov_hk --keyword "零售" --pages 3 --output both --detail

# 10) 勞工處：按工作種類篩選（屯門的會計職位）
python main.py --source gov_hk --keyword "會計" --district "屯門" --category "會計" --pages 2

# 11) 勞工處：按行業篩選（金融業）
python main.py --source gov_hk --keyword "會計" --industry "金融業" --pages 2

# 12) 勞工處：不給關鍵字，僅按地區 + 工作種類瀏覽（屯門的電腦及資訊科技職位）
python main.py --source gov_hk --district "屯門" --category "電腦及資訊科技" --pages 2

# 13) 勞工處：只留最近 10 天內刊登的職位（自動抓詳情取刊登日期，並按日期由近至遠排）
python main.py --source gov_hk --district "屯門" --category "電腦及資訊科技" --days 10 --outfile tuenmun_it_10d

# 14) 勞工處：依刊登日期由近至遠排序（post_dt_desc = 新→舊）
python main.py --source gov_hk --keyword "會計" --sort post_dt_desc --detail --pages 2

# 15) JobsDB：關鍵字搜尋「teacher」，抓 3 頁（每頁約 20–30 筆）
python main.py --source jobsdb --keyword "teacher" --pages 3

# 16) JobsDB：只留最近 7 天內刊登的職位（列表頁已有相對日，直接過濾）
python main.py --source jobsdb --keyword "accountant" --days 7 --pages 3 --outfile jobsdb_accountant_7d

# 17) JobsDB：留空關鍵字搜全站最新職缺（--days 控時間窗）
python main.py --source jobsdb --keyword "" --days 3 --pages 2

# 18) JobsDB：職能「資訊及通訊科技」+ 地區「荃灣」+ 3 天內（Task #16 實作）
python main.py --source jobsdb --category "資訊及通訊科技" --district 荃灣 --days 3 --outfile jobsdb_ict_tsuenwan_3d

# 19) JobsDB：純職能瀏覽（不給關鍵字），全港「銀行及金融服務」最近 7 天
python main.py --source jobsdb --category "銀行及金融服務" --days 7 --pages 3

# 20) LinkedIn：基本搜尋（訪客模式，無須登入、無須 Playwright）
python main.py --source linkedin --keyword "data engineer" --pages 3

# 21) LinkedIn：鎖定香港 + 只留最近 30 天內（--district 作為自由文字 location）
python main.py --source linkedin --keyword "data engineer" --district "Hong Kong" --days 30 --pages 3

# 22) LinkedIn：依刊登日期由近至遠排序（post_dt_desc → 網址 sortBy=DD，並讓 --days 提早停翻）
python main.py --source linkedin --keyword "software engineer" --sort post_dt_desc --pages 3

# 23) LinkedIn：啟用登入態深翻頁（需先設 li_at cookie；未設則退訪客模式 ~60 筆天花板）
#    Windows (PowerShell):  $env:LINKEDIN_LI_AT="你的cookie"
#    macOS / Linux:         export LINKEDIN_LI_AT="你的cookie"
python main.py --source linkedin --keyword "data engineer" --pages 10

# 24) Indeed：基本搜尋（需 Playwright 過 Cloudflare；關鍵字 + 香港）
python main.py --source indeed --keyword "software engineer" --pages 2

# 25) Indeed：地區自由文字（l= 文字；預設 Hong Kong）
python main.py --source indeed --keyword "data engineer" --district "Tsuen Wan" --pages 2

# 26) Indeed：只留最近 30 天內（經內嵌 pubDate 瞬時篩選 ~9s，無需逐張點擊；pubDate 為原始刊登日，比 UI 略保守）
python main.py --source indeed --keyword "software engineer" --days 30 --pages 2 --outfile indeed_sw_30d

# 26b) Indeed：要完整職位描述時顯式抓詳情（JS 點擊面板取，~1s/張；直連 viewjob 因 CF 不可行）
python main.py --source indeed --keyword "software engineer" --days 30 --detail --outfile indeed_sw_30d_detail

# 27) Indeed：不支援的功能會自動提示、不報錯（--category / --industry / --sort 傳入會被忽略並警告）
python main.py --source indeed --keyword "software engineer" --category "IT" --pages 2

# 24) LinkedIn：不支援的功能會自動提示、不報錯（--category / --industry 傳入會被忽略並警告）
python main.py --source linkedin --keyword "data engineer" --industry "金融業" --pages 2

# 25) LinkedIn：中文區名自動翻譯（元朗 → Yuen Long），5 天內科技職缺
python main.py --source linkedin --keyword "software engineer" --district 元朗 --days 5

# 26) LinkedIn：別名也通（旺角 → Yau Tsim Mong）
python main.py --source linkedin --keyword "developer" --district 旺角 --days 7
```

---

## 🗺️ 按地區篩選（Moovup）

Moovup 的搜尋 API 原生支援 `district` 過濾。本程式已內建 32 個香港地區的對照字典，
你可以用最直覺的方式指定地區，程式會自動翻譯成 API 認得的編號：

- **中文名**：`深水埗`、`油尖旺`、`沙田` …
- **英文名**：`Sham Shui Po`、`Yau Tsim Mong`、`Shatin` …
- **shortCode 編號**：`000017`、`000014`、`000026` …

> 地區 ↔ 編號完整對照見：**`docs/moovup_地區編號對照表.md`**
> （32 區，按香港島 / 九龍 / 新界東 / 新界西 / 大嶼山 分組）

⚠️ **小提醒**：Moovup 上單一職位可同時掛多個地區。因此用「深水埗」篩選後，
偶有職位因同時標註其他區而混入——這與官網自身篩選行為一致，屬正常現象。

---

## 🗺️ 按地區篩選（勞工處 gov.hk）

勞工處使用**獨立的數字地區 ID 體系**（與 Moovup 的 shortCode 完全不同）。本程式已內建
27 個地區的對照字典（`scrapers/gov_hk_districts.json`），你只需用中文地區名，程式會自動轉成 ID：

- **中文名（含或不含「區」字皆可）**：`屯門`、`屯門區`、`深水埗`、`荃灣` …
- 多個地區用逗號分隔：`屯門,元朗,沙田`

> 勞工處地區字典僅用於 gov_hk 爬蟲；Moovup 地區請見上一節，兩者**不可混用**。

⚠️ **小提醒**：與 Moovup 類似，勞工處單一職位也可能同時掛多個地區（例如「屯門,尖東」），
用「屯門」篩選後偶有同時標註其他區的職位混入，屬正常現象。

---

## 🗺️ 按工作種類 / 行業篩選（勞工處 gov.hk）

勞工處的搜尋表單除了地區，還有**兩套互相獨立**的分類維度，本程式均已接上：

### ① 工作種類（空缺類別）→ `--category`
對應表單欄位 `criteria.jobType`，為**單選**下拉，共 **29 類**，用數字 ID 編碼：

| ID | 類別 | ID | 類別 | ID | 類別 |
|----|------|----|------|----|------|
| 1 | 會計 | 11 | 司機 | 22 | 營業代表/推廣/售貨員 |
| 2 | 收銀員 | 12 | 家務助理 | 23 | 倉務 |
| 3 | 文員 | 13 | 工程 | 25 | 秘書 |
| 4 | 清潔 | 14 | 非技術工人/雜工 | 26 | 教師/導師 |
| 5 | 電腦及資訊科技 | 15 | 管理/行政 | 27 | 技工 |
| 6 | 建築/測量 | 16 | 採購 | 28 | 導遊 |
| 7 | 客戶服務 | 17 | 其他 | 30 | 打字 |
| 8 | 廚師/侍應 | 18 | 其他專業人員/輔助專業人員 | 31 | 物業管理/保安員 |
| 9 | 設計/繪圖 | 19 | 辦公室助理 | | |
| 10 | 跟車/送貨 | 20 | 生產/工廠職位 | | |

> 完整字典見：**`scrapers/gov_hk_categories.json`**（29 項，數字 ID → 類別名）。
> 此欄位**語意是「職位類別」**，與 `JobRecord.job_type`（工作性質：全職/兼職）不同，請勿混淆。

### ② 行業 → `--industry`
對應表單欄位 `criteria.industry`，為**單選**下拉，共 **27 業**，用數字 ID 編碼
（含兩個負號 ID：飲食業 = `-1`、零售業 = `-2`）：

| ID | 行業 | ID | 行業 |
|----|------|----|------|
| 1 | 政府部門 | 16 | 通訊業 |
| 2 | 醫院 | 17 | 金融業 |
| 3 | 服裝製品業 | 18 | 保險業 |
| 4 | 紡織業 | 19 | 地產業 |
| 5 | 塑膠製品業 | 20 | 商用服務業 |
| 6 | 金屬製品業 | 21 | 教育服務業 |
| 7 | 電子製品業 | 22 | 福利機構 |
| 8 | 其他製造業 | 23 | 其他社區及社會服務業 |
| 9 | 批發業 | 24 | 住戶服務業 |
| 11 | 進出口貿易 | 25 | 其他個人服務業 |
| 13 | 酒店業 | 26 | 建造業 |
| 14 | 運輸業 | 27 | 其他 |
| 15 | 倉庫業 | -1 | 飲食業 |
| | | -2 | 零售業 |

> 完整字典見：**`scrapers/gov_hk_industries.json`**（27 項，數字 ID → 行業名）。

### 使用方式
- 只需用**中文名**，程式自動翻譯成對應 ID；空值代表「所有」（不篩選）。
- 三個維度（地區 / 工作種類 / 行業）可**自由組合**，例如「屯門的會計職缺」：
  `python main.py --source gov_hk --keyword "會計" --district "屯門" --category "會計"`
- 表單均為單選，故每次只取第一個有效值；未知名稱會被忽略並提示。

⚠️ **小提醒**：`criteria.industry` 下拉**沒有「所有行業」空選項**，經實測確認——
不送該欄位或送空字串皆代表「所有行業」，故程式對未指定的行業統一送空字串，不會誤篩。

---

## 🗺️ 按刊登日期排序 / 近期篩選（勞工處 gov.hk）

### ① 時間排列（排序）→ `--sort`
勞工處搜尋表單含 `criteria.sortBy` 下拉，本程式已接上，可選值：

| `--sort` 值 | 意義 |
|-------------|------|
| `post_dt_desc` | 空缺刊登日期 **由近至遠**（新 → 舊） |
| `post_dt_asc` | 空缺刊登日期 **由遠至近**（舊 → 新） |
| `salary_desc` / `salary_asc` | 薪酬（月薪）由多至少 / 由少至多 |
| `yr_exp_asc` / `yr_exp_desc` | 相關工作經驗由少至多 / 由多至少 |
| `edu_lvl_asc` / `edu_lvl_desc` | 教育程度由低至高 / 由高至低 |

### ② 只留近期職位 → `--days N`
`--days 10` 表示「只保留最近 10 天內刊登的職位」。實作方式：
- **自動開啟詳情抓取**（因為列表本身不含日期，日期只在職位卡詳情頁）；
- 從詳情頁 `id="postedDt"` 讀取刊登日期（格式 `DD/MM/YYYY`，如 `10/07/2026`）；
- 計算距今天數，丟棄超過 N 天的職位；
- 並**自動套用 `post_dt_desc` 排序**（由近至遠），一旦某頁已無符合者即停止翻頁。

> 這兩個功能**僅 gov_hk 支援**；Moovup 的 `--sort` / `--days` 會被忽略（其日期格式為「N 日前」，後續可另行接上）。

---

## 🗺️ 按地區篩選（JobsDB）

JobsDB 使用**完全自有的 slug / 查詢體系**，與 Moovup 的 shortCode、勞工處的數字 ID **三者互不相通**，
不可混用。

### 已逆向發現的瀏覽網址規律（2026-07-17 實測）
- **職能（Classification）瀏覽**：`https://hk.jobsdb.com/jobs-in-<classification-slug>`
  - 例：`jobs-in-information-communication-technology`（資訊及通訊科技）
  - ⚠️ **不是** `/jobs/<slug>`（會 301 跳回 `/jobs` 失效），正確前綴是 **`jobs-in-`**。
- **地區（Location）串接**：在職能網址後接 `/in-<location-slug>`
  - 例：`jobs-in-information-communication-technology/in-yuen-long`（元朗）
  - 本質等同搜尋列 `where` 欄位（`name="where"`，placeholder「Enter suburb, city, or region」），slug 如 `yuen-long`。
- 翻頁同樣用 `?page=N`（與關鍵字搜尋一致）。

### 字典現狀（均已建檔，與另兩站獨立）
- **職能字典**：`scrapers/jobsdb_classifications.json`（**30 個頂層職能**，每筆含 `name`(英) / `zh`(中) / `slug`，
  如 `information-communication-technology` → `資訊及通訊科技`）。slug 由搜尋頁職能 facet 的 `href` 實測抓取。
- **地區字典**：`scrapers/jobsdb_districts.json`（**40 個地區**，每筆含 `zh` / `slug`，
  如 `tsuen-wan` → 荃灣）。每個 slug 均經「瀏覽網址不會靜默導向首頁」驗證，避免錯 slug 導致 0 結果。

### 爬蟲現狀（main.py）
`--district` / `--category` **已接進爬蟲並實測**（2026-07-25，Task #16）：爬蟲依字典解析成 slug，
組出 `/jobs-in-<職能>/in-<地區>` 瀏覽網址後翻頁擷取。`--industry` 不適用（忽略並提示）；`--sort` 暫未接。
先前手動撈到的「ICT + 元朗 + 3 天內」資料（見 `output/jobsdb_ict_yuenlong_3d.json`）即此機制的驗證基礎。

---

## 📊 輸出格式

### JSON（`output/moovup_<keyword>.json`）
標準欄位的陣列，例如：
```json
{
  "job_id": "moovup::76c3d987-...",
  "source": "moovup",
  "title": "會計文員",
  "company": "Kidswise智逸兒童發展中心",
  "location": "深水埗",
  "salary": "$14K-17K/月",
  "job_type": "全職",
  "description": "",
  "requirements": "",
  "url": "https://moovup.com/hk/job/全職-會計文員-深水埗/76c3d987-.../",
  "posted_date": "7日前",
  "scraped_at": "2026-07-08T09:08:26.340371+00:00"
}
```

### CSV（`output/moovup_<keyword>.csv`）
含 UTF-8 BOM 的 13 欄表格，Excel 直接開啟中文不亂碼。欄位順序同 `JobRecord.FIELDS`：
`job_id, source, title, company, location, salary, job_type, industry, description, requirements, url, posted_date, scraped_at`

> **增量與去重**：重跑同一關鍵字會自動與舊檔合併，以 `job_id` 去重（後抓到的覆蓋舊值）。

---

## 📊 聚合儀表板（`build_dashboard.py`）

把 `output/` 裡**所有**爬蟲產出（五站、任意多次任務的 JSON/CSV）聚合成一個**單檔離線網頁**，
直接雙擊就能開，不必起伺服器。

```bash
# 基本：掃 output/*.json + output/*.csv → 產生 output/dashboard.html
python build_dashboard.py

# 自訂輸出檔名
python build_dashboard.py --out 科技職缺總覽.html

# 只吃 JSON（不吃 CSV，避開舊檔編碼問題）
python build_dashboard.py --glob "output/*.json"
```

### 頁面功能
- **搜尋**：關鍵字比對職稱 / 公司 / 地區 / 描述 / 行業 / 要求
- **篩選**：據點（多選晶片）、地區下拉、刊登時間（3/7/14/30/90 天內）、只看有薪資
- **排序**：最新 / 最舊 / 薪資高→低 / 依來源 / 依職稱
- **圖表**：據點分佈長條圖、熱門地區 TOP 10
- **其他**：深淺主題切換、描述展開全文、職位標題直接連回原始網頁、分頁載入

### 資料處理（為什麼能混著吃五站的檔）
| 議題 | 處理方式 |
|------|----------|
| 五站日期格式各異 | 統一折算 `age_days`（距今天數）：`23h ago` / `3d ago` / `30d+ ago` / `2 days ago` / `7日前` / `2個月前` / `10/07/2026` 全數支援 |
| 列表層抓取無刊登日 | 另計 `scraped_days`（抓取距今），卡片顯示「未知刊登日（抓取於 N 天前）」；套用時間篩選時這類會被排除 |
| 同一職位重複出現在多檔 | 以 `job_id` 去重，保留描述較完整 / 抓取較新的一筆 |
| CSV 編碼不一（UTF-8 / BOM / Big5 / GB18030） | 逐個編碼嘗試；`ict_density_leaderboard.*` 等非職位檔自動略過 |
| 薪資文字五花八門 | 解析出數值 + 單位（月/小時/年）供排序與「只看有薪資」；**不做跨單位換算**（時薪與月薪不可比） |

> 網頁是**快照**：爬完新資料後重跑一次 `python build_dashboard.py` 就會更新（資料內嵌進 HTML，
> 刻意不用 `fetch`，因為 `file://` 下瀏覽器會擋外部 JSON 讀取）。

---

## 🏗️ 架構設計

```
main.py           命令列解析 → 選擇爬蟲 → 呼叫 scrape_all → 匯出
   │
base_scraper.py   BaseScraper（抽象）
   │               search() / get_detail()（子類實作）
   │               scrape_all()：翻頁 + 重試 + 間隔 + 詳情 + 匯出
   │
moovup.py         MoovupScraper：Playwright 繞 Cloudflare → GraphQL 取資料
gov_hk.py         GovHkScraper：requests POST 搜尋 → GET quickview 翻頁 → 解析職位卡
jobsdb.py         JobsDBScraper：Playwright 共用 session 過 Cloudflare → 解析 SSR HTML 職位卡
   │
job_model.py      JobRecord：所有爬蟲的統一輸出契約
exporter.py       export_json / export_csv：增量 + 去重 + BOM
config.py         請求間隔 / UA / 輸出目錄 / 各站選擇器集中管理
```

**擴充新網站**：在 `scrapers/` 新增 `xxx.py` 繼承 `BaseScraper` 實作 `search()` 與
`get_detail()`，再到 `scrapers/__init__.py` 的 `SCRAPERS` 註冊即可，無需改動主流程。

---

## ⚠️ 已知限制與注意事項

- **`--detail` 模式較慢**：每筆職位需另開頁面（Moovup 等待渲染、gov.hk 另發請求），量大時請斟酌使用。
- **地點中文來源**：
  - Moovup：主要取自職位網址 slug 末段的中文區名；極少數 slug 不含區名時回退英文 `district_name`。
  - gov.hk：取自職位卡 `#locDesc` 欄位（官方中文區名）。
- **Cloudflare 保護**：Moovup 受 Cloudflare Turnstile 保護，本程式靠 Playwright 真瀏覽器通過；
  若長時間高頻請求仍有被限流（429）風險，請適度降低 `--pages` 或拉長間隔（`config.REQUEST_DELAY`）。
- **JobsDB 的 Cloudflare**：hk.jobsdb.com 同樣在 Cloudflare 後。本程式**先訪首頁取得 `cf_clearance` Cookie、
  後續所有列表請求共用同一瀏覽器 session**（不重建 context），因此實測中不會反覆觸發挑戰。
  但 JobsDB 反爬更嚴，請嚴守禮貌間隔（預設 2 秒 + 抖動），並避免 `--pages` 開太大；
  若出現 403 / 轉圈，先停 10 分鐘再試，切勿重試狂刷。
- **JobsDB 功能邊界**：`--district` / `--category` / `--sort` **已生效**（透過瀏覽網址與 `?sortmode=ListedDate`）；`--industry` 不適用（JobsDB 無此維度，忽略並提示）；`--detail` 詳情頁解析為 best-effort。
  詳見上方「🗺️ 按地區篩選（JobsDB）」與下方「🧭 技術筆記（JobsDB）」。
- **gov.hk 無反爬但請禮貌**：勞工處網站無 Cloudflare，但仍建議保持預設 2 秒間隔，避免對政府伺服器造成壓力。
- **反爬禮貌**：預設已加入請求間隔與隨機抖動，請勿惡意高併發爬取。

---

## 🧭 技術筆記（Moovup 逆向要點）

- 首頁 `https://moovup.com/hk/` 為 Nuxt SSR，職位結果由前端透過 GraphQL 取得：
  `POST https://api.moovup.com/v2/seeker`，查詢 `QueryJobs`。
- 該 API 受 Cloudflare 保護，**直接 `requests` 會被擋（403/405）**；必須用真瀏覽器
  自動過 Turnstile 後，在瀏覽器上下文內 `fetch` 才能穩定通過。
- 匿名存取需先 `POST https://api.moovup.com/v2/create-anonymous` 取得 JWT（`Bearer`）。
- 分頁：`offset` / `limit`（每頁 12）。地區過濾：`district: [shortCode]`。

---

## 🧭 技術筆記（勞工處 gov.hk 逆向要點）

- 真實網站位於 **`www1.jobs.gov.hk`** 子域（首頁 `www.jobs.gov.hk` 會 307 跳轉過去）；語言路徑 `/0/tc/`。
- 搜尋為 ASP.NET MVC 表單：**POST `/0/tc/jobseeker/jobsearch/search/`** 帶 `criteria.*` 欄位
  （`criteria.searchField`=關鍵字、`criteria.selectedDistricts`=地區數字 ID 陣列），
  服務端記住搜尋條件並回傳第 1 頁。
- 翻頁：**GET `/0/tc/jobseeker/jobsearch/quickview/?direct=False&page=N`**（沿用 Session 條件），每頁約 20 筆；
  到尾頁後回傳空列表，爬蟲自動停止。
- 列表每筆職位為 `div.row.item[data-jobcard]`，內含標題 / `.icon_salary`(薪資) / `.icon_address`(地點) /
  職位編號（`input#ord_no_N` 或 `a[data-ordno]`）。
- 詳情頁（jobCard）：用穩定 `id` 標識——`#empName`(公司) / `#locDesc`(地區) /
  `#jobRemark`(職責) / `#eduRemark`(資歷/要求) / **`#postedDt`(刊登日期，格式 `DD/MM/YYYY`)**。
- **行業（industry）** 由詳情頁的「`行業 :`」label + 其下一個 `<span>` 取得（如 `建造業`）；
  填入 `JobRecord.industry`（第 13 個標準欄位，僅 gov_hk 有值，moovup 留空）。這正是「先盤點行業、再排除部分」流程的資料基礎。
- 職位編號（如 `35-26-0011843`）作為 `job_id`；**刊登日期**由詳情頁 `#postedDt` 取得（如 `10/07/2026`），
  故 `posted_date` 在抓詳情（`--detail` 或 `--days`）後會被填滿；未抓詳情時留空。
- **排序（時間排列）** = `criteria.sortBy`，下拉可選值：`post_dt_desc`(刊登日期新→舊) /
  `post_dt_asc`(舊→新) / `salary_desc`·`salary_asc`(月薪) / `yr_exp_asc`·`yr_exp_desc`(經驗) /
  `edu_lvl_asc`·`edu_lvl_desc`(學歷)。未送則用網站預設順序。
- **工作種類 / 行業篩選（兩套獨立維度）**：
  - **工作種類（空缺類別）** = `criteria.jobType`，**單選**下拉，29 類數字 ID（會計=1…物業管理/保安員=31，24/29 兩碼網頁未列出）。空值 = 所有類別。
  - **行業** = `criteria.industry`，**單選**下拉，27 業數字 ID（含負號：飲食業=-1、零售業=-2）。
  - ⚠️ 關鍵陷阱：`criteria.industry` 下拉**沒有「所有行業」空選項**。經實測——不送該欄位、或送空字串 `""`，二者皆代表「所有行業」（不篩選）；送具體 ID 才會過濾（例：飲食業 -1 → 結果數下降）。故程式對未指定的行業統一送空字串，避免誤套用第一個選項（商用服務業）。
  - 三維度（地區 `selectedDistricts` / 工作種類 `jobType` / 行業 `industry`）在 POST 表單中**同時生效、可疊加**。
  - 完整字典：`scrapers/gov_hk_categories.json`（29 類）、`scrapers/gov_hk_industries.json`（27 業）。

---

## 🧭 技術筆記（JobsDB 逆向要點）

- **真實網域**：`https://hk.jobsdb.com`（首頁 `/` 會經 Cloudflare；搜尋結果在 `/jobs?keywords=K&page=N`）。
- **反爬保護：Cloudflare**。實測**用真瀏覽器（Playwright Chromium）即可通過，不會跳出 Turnstile 挑戰**。
  關鍵做法：**先 `goto` 首頁一次，讓瀏覽器拿到 `cf_clearance` Cookie，之後所有列表請求共用同一個
  `BrowserContext` / `Page`**，不重建、不重挑戰。UA 帶 `zh-HK,zh;q=0.9` 且 `locale="zh-HK"`。
  - ⚠️ **絕不硬撞 GraphQL**：JobsDB 的 GraphQL 端點（如 `JobCountsV6`、`GetBanner`）只會對 facet / banner 發請求，
    **職位列表本身不在 GraphQL 回傳裡**。若想靠爬 API 拿列表，反而更容易被標記。故採 SSR HTML 路線最穩。
- **搜尋機制：React SSR + 伺服器渲染 HTML**。鍵入關鍵字後網址變成 `/jobs?keywords=K`（首頁有時 301 轉為 `/K-jobs`，
  但帶 `?page=N` 時仍走 `/jobs?keywords=K&page=N`，`page` 參數會保留）。職位卡片以
  `data-automation='normalJob'` 渲染在 HTML 中，直接 `query_selector_all` 即可，每頁只需 1 次 GET。
- **翻頁機制**：URL 加 `?page=N`（N 從 1 開始）。到尾頁後卡片數為 0，爬蟲自動停止（與 Moovup 的 offset / gov.hk 的 quickview 都不同）。
- **職能 / 地區 瀏覽網址（非關鍵字搜尋時用）**：職能瀏覽為 `/jobs-in-<classification-slug>`
  （如 `jobs-in-information-communication-technology`，**注意前綴是 `jobs-in-` 而非 `jobs/`**）；
  地區接續為 `/in-<location-slug>`（如 `in-yuen-long`，對應搜尋列 `where` 欄位的 slug）。
  本次「ICT + 元朗」查詢即靠此網址成功，證明可行，待整合進爬蟲（Task #16）。
- **職位卡解析（`[data-automation='normalJob']` 子元素）**：
  - `jobTitle` → 職位名（其 `href` 形如 `/job/<id>?...`，取 `<id>` 作 `job_id` 前綴 `jobsdb_`）
  - `jobCompany` → 公司
  - `jobCardLocation` → 地區（缺則回退 `jobLocation`）
  - `jobSalary` → 薪資（列表常省略，故薪資欄位填充率約 3 成）
  - `jobShortDescription` → 簡述
  - `jobClassification` / `jobSubClassification` → 職位大類 / 子類（作為 `industry` 欄位來源，**自有 slug 體系**）
  - `jobListingDate` → **相對刊登日**（如 `2d ago`、`6h ago`、`Just now`、`30d+ ago`）
- **刊登日（相對時間）解析**：格式為**縮寫** `2d ago` / `6h ago` / `Just now` / `30d+ ago`（非 `7 days ago` 全字）。
  `days_since_posted()` 把 `2d ago`→2、`6h ago`/`Just now`→0、`30d+ ago`/更久視為過舊（`--days` 過濾時會被排除），其餘無法解析→`None`。
  因**列表頁已含此欄位**，JobsDB 的 `--days` 過濾**不需要抓詳情**，比 gov.hk 省 30 次/頁請求。
- **排序（`--sort`）機制**：JobsDB 網站 UI 排序下拉（`[data-automation='sortby']`）僅有兩項——
  **Relevance（相關性，預設，不帶參數）** 與 **Date（`?sortmode=ListedDate`，刊登日期新→舊）**。
  實測 `sortmode=ListedDate` 會讓列表由最新排到最舊（1h→2h→3h… 遞增）。
  - 實作對應：`--sort post_dt_desc` → 網址加 `sortmode=ListedDate`；其餘選項（`post_dt_asc` / `salary_*` / `yr_exp_*` / `edu_lvl_*`）為 **gov_hk 專有**，JobsDB 無對應 UI，傳入會 `logger.warning` 並回退預設（Relevance）。
  - `sortmode` 參數可與 `keywords` / `page` / 地區瀏覽網址共存：站方會將 `/jobs?keywords=K&page=N&sortmode=ListedDate` 301 正規化為 `/K-jobs?page=N&sortmode=ListedDate`（Playwright 自動跟隨）。
  - **與 `--days` 的協同優化**：`base_scraper` 在設 `--days` 且未指定 `--sort` 時自動套 `post_dt_desc`；新職位因此堆在最前，一旦某頁全超出天數即停止翻頁（如「ICT + 荃灣 + 3 天內」第 2 頁全為舊職位即停），大幅減少請求數與被封風險。
- **詳情頁**：`/job/<id>`，同樣靠 `data-automation` 屬性（`job-detail-title` / `jobDescription` / `jobRequirements` 等）解析，
  為 **best-effort**（v1 選擇器與列表略有差異，實測微調中）。`--detail` 模式抓取後會補 `description` / `requirements`。
- **各欄位資料來源總表（JobsDB → JobRecord）**：

  | JobRecord 欄位 | 來源（JobsDB 選擇器 / 邏輯） |
  |----------------|------------------------------|
  | `job_id` | `jobsdb_<id>`（取自 `jobTitle` 連結的 `/job/<id>`） |
  | `source` | 常數 `"jobsdb"` |
  | `title` | `jobTitle` |
  | `company` | `jobCompany` |
  | `location` | `jobCardLocation` → 回退 `jobLocation` |
  | `salary` | `jobSalary`（常缺） |
  | `job_type` | 列表未提供，留空 |
  | `industry` | `jobClassification` → 回退 `jobSubClassification`（自有 slug） |
  | `description` | `jobShortDescription`（列表）/ `jobDescription`（詳情） |
  | `requirements` | `jobRequirements`（僅詳情有） |
  | `url` | `https://hk.jobsdb.com` + `jobTitle` 連結 |
  | `posted_date` | `jobListingDate`（相對時間字串） |
  | `scraped_at` | 抓取當下 `datetime.now()` |

- **地區 / 分類體系（重要）**：JobsDB 的地區與分類是**自有 slug 體系**（如 `kowloon-east`、`accounting`），
  **與 Moovup 的 shortCode、勞工處的數字 ID 三者完全獨立**，不可跨站混用。v1 未接 `--district` / `--category` / `--industry`，
  詳見上方「🗺️ 按地區篩選（JobsDB）」。

---

## 🧭 技術筆記（LinkedIn 逆向要點）

- **真實網域**：`https://www.linkedin.com`（職位搜尋在 `/jobs/search/`；單筆詳情免登入 API 在 `/jobs-guest/jobs/api/jobPosting/<id>`）。站台會依訪客 IP 把網域導向地區鏡像（如 `hk.linkedin.com`），但路徑不變，不影響爬取。
- **反爬保護**：
  - LinkedIn 有強反爬（PerimeterX / HUMAN + 自研指紋、速率限制），但**職位搜尋（訪客模式）與職位詳情（guest API）對未登入使用者開放**，不需 `li_at` cookie 也能抓。
  - 關鍵限制：**訪客模式深翻頁不穩定**——`start` 參數會被隨機化 / AB 測試，同一 `start` 可能回傳不同批次（實測 `start=0/50` 同批、`start=10/25` 另批、`total` 數 265↔478 跳動）。故單次執行約能穩定拿 ~25–60 筆獨特職位。
  - **解鎖穩定深翻頁**：在 `config.LINKEDIN_LI_AT`（或環境變數 `LINKEDIN_LI_AT`）填入自己的 `li_at` cookie 即可切到登入態，此時 `start` 翻頁趨於穩定、可抓更深。cookie 取得：瀏覽器登入 linkedin.com → DevTools → Application → Cookies → 複製 `li_at` 值。⚠️ cookie 等同帳號憑證，僅供個人使用、切勿外洩，且請遵守 LinkedIn 服務條款、維持禮貌爬取頻率。
- **搜尋機制：伺服器渲染 HTML**（非 GraphQL、非 JSON API）。`GET /jobs/search/?keywords=K&location=L&start=N[&sortBy=DD]` 直接回傳含職位卡的完整 HTML，用 `BeautifulSoup` 解析即可（每頁約 25 張職位卡，訪客模式實測回傳 ~60 個 `li`，含少量推廣 / 重複）。
- **翻頁機制**：URL `start=N`（N 從 0 起，每頁 25）。**訪客模式 `start` 不可靠**（見上），故實作以 `job_id` 跨頁去重，整頁皆為已見職位即停止翻頁（避免無限迴圈）；提供 `li_at` 後可正常深翻。
- **職位卡解析（`.jobs-search__results-list li` 內）**：
  - `a.base-card__full-link` → 連結 `…/jobs/view/<slug>-<id>`，取網址 slug 尾段數字作 `job_id`（標準鍵 `linkedin::<id>`）
  - `.base-search-card__title` → 職位名
  - `.base-search-card__subtitle` → 公司
  - `.job-search-card__location`（或 `.base-search-card__metadata` 第一行）→ 地點
  - `time` → 相對刊登日（如 `4 days ago`）
  - 訪客卡通常**不含薪資**（留空）
- **詳情頁（免登入 guest API）**：`GET /jobs-guest/jobs/api/jobPosting/<id>` 回傳公開職位頁 HTML 片段（status 200，含完整 `description`）。解析：
  - `.top-card-layout__title` → 職位名
  - `.topcard__flavor` → 公司
  - `.topcard__flavor--bullet` → 地點
  - `.description__text` / `.show-more-less-html__markup` → 描述（最長可達數千字）
  - 刊登日：詳情頂部文字抓相對時間（與列表同源）
- **語系處理**：強制 `Accept-Language: en-US`，確保刊登日為英文（`4 days ago`）便於 `days_since_posted()` 解析；同時備援中文單位（`4 天前` / `3 個月前`）解析，雙語皆可用。地點也因此為 `Hong Kong, Hong Kong SAR` 而非中文本地化。
- **排序（--sort）**：`--sort post_dt_desc` → 網址 `sortBy=DD`（最新優先，實測有效）；其餘選項（`post_dt_asc` / `salary_*` / `yr_exp_*` / `edu_lvl_*`）為 gov_hk 專有，LinkedIn 無對應，傳入會 `logger.warning` 並回退網站預設（相關性）。
- **地區篩選體系（重要）**：LinkedIn 地區為**自由文字 `location=`**（無像 JobsDB slug / 勞工處數字 ID 的編碼體系）。2026-07-30 逆向發現訪客可達的 `jobs-guest/api/typeaheadHits?typeaheadType=GEO&geoTypes=POPULATED_PLACE,...` API 會回傳香港 18 區的 geoUrn（如元朗=`102989568`），**但訪客搜尋用 `geoUrn=<數字>` 參數完全無效**（實測回非目標區甚至美國職位）。有效機制是 `location=<英文區名>` 文字（LinkedIn 顯示「N jobs in Yuen Long」）。故本爬蟲以 `scrapers/linkedin_geo.json`（18 區 zh/英文/別名/geoUrn）把 `--district` 翻譯成標準英文區名餵給 `location=`。詳見上方「🗺️ 按地區篩選（LinkedIn）」。
- **各欄位資料來源總表（LinkedIn → JobRecord）**：

  | JobRecord 欄位 | 來源（LinkedIn 選擇器 / 邏輯） |
  |----------------|------------------------------|
  | `job_id` | `linkedin::<id>`（取自 `/jobs/view/…-<id>` 尾段數字） |
  | `source` | 常數 `"linkedin"` |
  | `title` | `.base-search-card__title`（列表）/ `.top-card-layout__title`（詳情） |
  | `company` | `.base-search-card__subtitle` / `.topcard__flavor` |
  | `location` | `.job-search-card__location` / `.topcard__flavor--bullet` |
  | `salary` | 訪客卡通常無，留空 |
  | `job_type` | 未提供，留空 |
  | `industry` | 未提供，留空 |
  | `description` | 詳情 `.description__text` |
  | `requirements` | 併入 description（訪客無獨立欄位） |
  | `url` | `https://www.linkedin.com/jobs/view/…-<id>` |
  | `posted_date` | `time`（列表）/ 詳情頂部相對時間 |
  | `scraped_at` | 抓取當下 `datetime.now()` |

## 🗺️ 按地區篩選（LinkedIn）

- LinkedIn 的 `location` 是**自由文字**，與 Moovup 的 shortCode、勞工處數字 ID、JobsDB 的 slug **三者完全獨立**，不可跨站混用。
- **香港 18 區字典（2026-07-30 逆向）**：`scrapers/linkedin_geo.json` 收錄 18 區 + 全港，每區含中文區名 / 英文 / geoUrn / 別名。`--district` 命中字典時自動翻譯成**標準英文區名**餵給 `location=`（英文如 `Yuen Long` 命中較穩）：
  - 中文區名：`--district 元朗` → `location=Yuen Long`
  - 別名：`--district 旺角` → `Yau Tsim Mong`；`--district 銅鑼灣` → `Wan Chai`；`--district 將軍澳` → `Sai Kung`
  - 英文 / 大小寫：`--district "Tsuen Wan"` / `"yuen long"` 亦命中
  - 未命中：原樣作 `location` 文字（best-effort，LinkedIn 可能仍能解析）
- ⚠️ **重要發現（geoUrn 無效）**：LinkedIn 的 `typeaheadHits` API 雖回傳每區 geoUrn，但訪客搜尋用 `geoUrn=<數字>` 參數**完全無效**（實測回傳非目標區、甚至美國職位）。故本爬蟲一律走 `location=<英文區名>` 文字——這在訪客模式才是有效機制。字典裡的 geoUrn 僅供登入態（`li_at`）參考、未驗證。
- 範例：
  - `python main.py --source linkedin --keyword "software engineer" --district 元朗 --days 5`（自動翻譯成 `location=Yuen Long`）
  - `python main.py --source linkedin --keyword "data engineer"`（不給 `--district`，預設 `Hong Kong`）
- 卡片上的 `location` 欄位有時較粗（如僅標 `Hong Kong SAR`），那是 LinkedIn 卡片標註本身，非篩選失效；LinkedIn 搜尋頁標題會顯示「N jobs in <地點>」證實篩選已套用。

---

## 🧭 技術筆記（Indeed 逆向要點）

- **真實網域**：`https://hk.indeed.com`（香港鏡像；職位搜尋 `/jobs`、單筆詳情 `/viewjob`）。
- **反爬保護（Cloudflare「Just a moment...」）**：
  - plain `requests` → **403 被擋**；必須用 **Playwright headless Chromium**（本爬蟲 `use_browser=True`）。
  - **關鍵坑（重要）**：Indeed 的 Cloudflare 在「首頁 → 搜尋頁」的跳轉上特別頑固（實測偶發 45 秒仍過不了）；
    但**直接 goto 搜尋頁**（`/jobs?q=…&l=…`）幾秒內即過關。故本爬蟲**不先做首頁預熱**，而是直接在 `search()` 跳搜尋頁並輪詢 `.job_seen_beacon` 出現（最多 ~45 秒）。
  - 共用同一 `BrowserContext`，cf_clearance cookie 取得後續翻頁沿用（不重建不重挑戰）。
- **搜尋機制：SSR + 客戶端渲染 HTML**。網址
  `https://hk.indeed.com/jobs?q=KEYWORD&l=LOCATION&start=N`（`start` 步長 10，首頁不加 `start`）。
- **職位卡（`.job_seen_beacon`，每頁 ~16 張，表格佈局）**：
  - 標題 `a.jcs-JobTitle`（含 `data-jk` 屬性 = 職位 ID，如 `7b8620949d7f8b54`）；`job_id` = `indeed::<jk>`
  - 公司 `span[data-testid='company-name']`
  - 地點 `div[data-testid='text-location']`（如 `Remote` / `Hong Kong` / `Cyberport, Hong Kong Island`）
  - 薪資：卡片**無專屬元素**，為卡片內文文字（如「$18,000 - $30,000 a month」），以正則從 `inner_text` 抓取
- **刊登日（重要）**：列表卡可見 HTML（inner_text）雖然**不含日期**（只有 title/company/location/salary），
  Indeed 卻在**內嵌的 mosaic provider JSON**（`window.mosaic.providerData["mosaic-provider-jobcards"]`）
  中為每個職位提供 `pubDate`（毫秒戳，原始的實際刊登時間）。故 `search()` 解析完卡片後，
  直接從 `page.content()` 以正則抽 `pubDate`→`jk` 對照表（`_build_pubdate_map`），折算為「N day ago」寫入
  `posted_date`。**`list_has_date=True` → `--days` 篩選瞬時完成，無需逐張點擊（優化前需 ~11 分鐘，優化後 ~9 秒）。**
  ⚠️ 注意：`pubDate` 是**原始刊登日**；Indeed 對「轉貼 / 刷新」的職位會在 UI 顯示較新的「X days ago」，
  因此 `--days` 以 `pubDate` 判斷會比 Indeed 網站 UI 略保守（可能少收幾筆轉貼職位），但絕不會誤把舊職位當新職位。
- **詳情頁（僅 `--detail` 顯式要描述時才用）**：
  - ⚠️ **直連 `/viewjob?jk=<id>` 會重觸發 Cloudflare（40 秒仍被擋）**，不可行。
  - ✅ **從搜尋頁「點擊職位連結」開側面板（SPA）則不重觸發 CF**（cf_clearance 沿用），2–3 秒內載入，
    詳情 HTML 含 `datePublished` 毫秒戳與 `age:"X days ago"`。故 `get_detail()` 實作為「在當前搜尋頁點擊對應 `a[data-jk]`」而非直連 viewjob。
  - **點擊改用 JS `element.click()` 直接派發事件**（繞過「面板遮住卡片 → Playwright 判定 `element is not visible`」的坑），
    單張詳情 ~1 秒（優化前因 re-goto 回退每張可達 8–60 秒）。失敗時仍回退：重新 goto 搜尋頁（cf_clearance 已種、很快）再 JS 點該卡。
  - 日期解析優先取 `age` 文字（「10 days ago」），回退 `datePublished` 毫秒戳轉相對天數；`days_since_posted()` 解析「N day(s) ago」。
- **地區篩選體系**：Indeed 用 `l=` **自由文字**（與 Moovup 的 shortCode、勞工處數字 ID、JobsDB 的 slug、LinkedIn 的 location 文字**各自獨立**，不可混用）。`--district` 直接作為 `l=` 文字（預設 `Hong Kong`）；LinkedIn 的 18 區字典不適用於此。
- **不支援項**：`--category` / `--industry`（Indeed HK 搜尋無對應乾淨維度，傳入會 `logger.warning` 並忽略）；`--sort`（訪客模式排序需登入態 facet，忽略並提示）。均不影響其他據點。
- **各欄位資料來源總表（Indeed → JobRecord）**：

  | JobRecord 欄位 | 來源（Indeed 選擇器 / 邏輯） |
  |----------------|------------------------------|
  | `job_id` | `indeed::<jk>`（取自 `a[data-jk]` 屬性） |
  | `source` | 常數 `"indeed"` |
  | `title` | `a.jcs-JobTitle > span` |
  | `company` | `span[data-testid='company-name']` |
  | `location` | `div[data-testid='text-location']` |
  | `salary` | 卡片內文正則（`$… a month` 等） |
  | `job_type` | 未提供，留空 |
  | `industry` | 未提供，留空 |
  | `description` | 詳情面板 `#jobDescriptionText` |
  | `requirements` | 併入 description |
  | `url` | `https://hk.indeed.com/viewjob?jk=<jk>` |
  | `posted_date` | **列表內嵌 `pubDate`（毫秒戳）折算「N day ago」**；`--detail` 時詳情面板 `age` / `datePublished` 亦可 |
  | `scraped_at` | 抓取當下 `datetime.now()` |

## 🗺️ 按地區篩選（Indeed）

- Indeed 的 `l` 是**自由文字**，與 Moovup 的 shortCode、勞工處數字 ID、JobsDB 的 slug、LinkedIn 的 `location` 文字**完全獨立**，不可跨站混用。
- `--district` 直接作為 `l=` 文字傳入（預設 `Hong Kong`）。Indeed 會自行 geocode 成對應市場區。範例：
  - `python main.py --source indeed --keyword "data engineer" --district "Tsuen Wan"`（文字 `l=Tsuen Wan`）
  - `python main.py --source indeed --keyword "software engineer"`（不給 `--district`，預設 `Hong Kong`）

---

## 🗺️ 路線圖（依計劃書）

| 階段 | 網站 | 難度 | 狀態 |
|------|------|------|------|
| 1–3 | Moovup 好工速遞 | 中（Cloudflare） | ✅ 已完成並實測 |
| 4 | 勞工處 gov.hk | 低（無反爬） | ✅ 已完成並實測 |
| 5 | JobsDB | 中高（需 Playwright） | ✅ 已完成並實測（關鍵字 + 翻頁 + --days + 職能/地區篩選 + --sort post_dt_desc；--industry 不適用） |
| 6 | LinkedIn | 高（強反爬） | ✅ 已完成並實測（訪客模式：關鍵字 + 地點 + --days + --sort post_dt_desc；深翻頁不穩定，填 li_at cookie 可解鎖；--category/--industry 不適用） |
| 7 | Indeed | 高（Cloudflare） | ✅ 已完成並實測（Playwright 過 CF；關鍵字 + 地區自由文字；**--days 經內嵌 pubDate 瞬時篩選 ~9s**；--detail 用 JS 點擊面板取描述 ~1s/張；--category/--industry/--sort 不適用） |

> 路線圖全數達標 ✅：Moovup / 勞工處 / JobsDB / LinkedIn / Indeed 五座據點皆已落地並實測。LinkedIn 現以訪客模式落地——功能可用但單次約 ~25–60 筆天花板；提供 `li_at` cookie（config.LINKEDIN_LI_AT / 環境變數）後深翻頁趨穩、可抓更深。Indeed 的 `--days` 現已由內嵌 `pubDate` 瞬時篩選（~9 秒，不再逐張點擊）；`--detail` 取描述改用 JS 點擊面板（~1 秒/張）；直連 viewjob 因 Cloudflare 不可行。
