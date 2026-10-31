# 香港求職網站自動搜尋程式 (HK Job Scraper)

> 🚀 **第一次用？看這一節就夠，60 秒能跑出第一份結果。** 後面的技術筆記是給要改程式的人看的，不必先讀。

## ⚡ 60 秒上手

```bash
# 1) 取得程式
git clone https://github.com/vilys/hk-job-scraper.git
cd hk-job-scraper

# 2) 安裝依賴（先選 A 就好，想跑更多站再回頭裝 B）
#    A. 最小安裝 —— 足夠跑「不需要瀏覽器」的據點
pip install requests beautifulsoup4 lxml

#    B. 完整安裝 —— 要跑 Moovup / JobsDB / foundit / 獵聘 等才需要
# pip install -r requirements.txt
# playwright install chromium        # 只需執行一次

# 3) 跑第一支（推薦：勞工處。免瀏覽器、免登入、免 cookie）
python main.py --source gov_hk --keyword "會計" --pages 1
```

結果會寫到 `output/gov_hk_會計.json`；想要 Excel 可直接開的格式，把結尾換成 `--output csv`。

> 📌 **第一次看到「公司」欄位是空的，不是壞了。** 列表頁本身只有標題／地區／薪資／連結，
> 公司名稱、職責描述、刊登日期要進詳情頁才拿得到。加上 `--detail` 就會補齊，
> 代價是**每筆多 1 支請求**——所以預設關閉，請自行斟酌量。

**為什麼第一支建議用 `gov_hk`？** 它是政府網站，ASP.NET 伺服器渲染、沒有 Cloudflare、不需要登入，
是全專案門檻最低的據點。先用它確認環境沒問題，再去挑戰需要瀏覽器的站——這樣出錯時，
你只需要懷疑一件事，而不是三件。

**各站需要什麼？**

| 需求 | 據點 |
|---|---|
| 只要 `requests`（最小安裝即可） | 勞工處 `gov_hk`、JobMarket、eFinancialCareers、LinkedIn、OfferToday |
| 需要 Playwright + `playwright install chromium` | Moovup、JobsDB、Recruit、Indeed（停用中） |
| **另需本機安裝 Google Chrome**（指紋辨識） | foundit、獵聘 `liepin`、BOSS直聘 |

```bash
# 其他常見用法
python main.py --source gov_hk   --keyword "零售" --pages 2 --district 屯門 --days 7
python main.py --source jobsdb   --keyword "data" --pages 2 --days 7 --output both
python main.py --source moovup   --keyword "會計" --pages 3 --detail
python main.py --source all      --keyword "會計" --pages 1        # 全部「已啟用」據點各跑 1 頁（自動略過停用來源）
python main.py --help                                              # 完整參數
```

> 🐢 **爬蟲禮節**：本專案預設把請求間隔拉在 1.5–8 秒。請不要為了快而改小，
> 也不要一次開多個終端同時跑同一個站。被站方封鎖一次，往往要用「天」來等。

> 🔧 **只想驗證程式邏輯、不想發任何請求？** 跑 `python -m unittest discover -s tests`，
> 22 個測試、約 0.06 秒、零網路請求。

> 🔒 **文件中的公網 IP 一律遮罩**（如 `1.64.x.x`、`182.239.x.x`），只保留 ASN、電信商、
> `mobile`／`proxy` 等技術特徵。這些欄位足以說明「換了業者仍被擋」的推論，
> 但不必把任何人的實際位址留在網路上。
>
> 📌 2026-10-28 已對**整條歷史**執行同樣的遮蔽（`git filter-branch`），
> 因此該日之前的 commit hash **全部改變**；舊連結會 404 屬預期，程式內容與提交訊息未受影響。

---

> ⚠️ **適用範圍備註**：本程式採「一網站一爬蟲模組」設計，目前共有 **12 個模組、10 座可用據點**：
> - **Moovup 好工速遞（moovup.com）** —— 見「🗺️ 按地區篩選（Moovup）」與「🧭 技術筆記（Moovup）」
> - **勞工處互動就業服務（jobs.gov.hk / www1.jobs.gov.hk）** —— 見「🗺️ 按地區篩選（勞工處）」與「🧭 技術筆記（勞工處）」
> - **JobsDB（hk.jobsdb.com）** —— 見「🗺️ 按地區篩選（JobsDB）」與「🧭 技術筆記（JobsDB）」
> - **LinkedIn（www.linkedin.com）** —— 見「🧭 技術筆記（LinkedIn）」與「🗺️ 按地區篩選（LinkedIn）」
> - **Indeed（hk.indeed.com）** —— 見「🧭 技術筆記（Indeed）」與「🗺️ 按地區篩選（Indeed）」
> - **Recruit（www.recruit.com.hk）** —— 見「🧭 技術筆記（Recruit 逆向要點）」與「🗺️ 按地區篩選（Recruit）」
> - **JobMarket 求職廣場（www.jobmarket.com.hk）** —— 見「🧭 技術筆記（JobMarket 逆向要點）」與「🗺️ 按地區篩選（JobMarket）」
> - **foundit（www.foundit.hk，原 Monster HK）** —— 見「🧭 技術筆記（foundit 逆向要點）」與「🗺️ 按地區篩選（foundit）」
> - **eFinancialCareers（www.efinancialcareers.hk）** —— 見「🧭 技術筆記（eFinancialCareers 逆向要點）」與「🗺️ 按地區篩選（eFinancialCareers）」
> - **獵聘 Liepin（www.liepin.com）** ⚠️ 受限模組 —— 見「🧭 技術筆記（獵聘）」
> - **BOSS直聘（www.zhipin.com）** ⚠️ 受限模組 —— 見「🧭 技術筆記（BOSS直聘）」
>
> 各爬蟲模組**僅針對其對應網站**，彼此的資料結構、地區編號體系互不相同（各站的地區字典各自獨立），請勿跨站混用。
>
> ⚠️ **受限模組說明（2026-09-11 更新）**：
> - **獵聘 Liepin** —— 已於 2026-09-11 **升級為可用香港據點**（證實有約 800 筆香港職缺）。
>   ⚠️ 但 `www.liepin.com/robots.txt` 明文 `Disallow: /*?*`（帶查詢串路徑禁抓），
>   本模組搜尋網址帶查詢串 → 屬禁區；職缺資料實由 `api-c.liepin.com` 供應，
>   該主機**無 robots.txt（404）**。**請自行評估合規風險。**
> - **BOSS直聘 Zhipin** —— 維持**受限**。2026-09-11 複查：職缺城市體系不含香港，
>   港澳台專區對訪客為空並要求登入 → 對本專案無可用價值。

模組化、可擴充的香港求職網站爬蟲。已完成 **Moovup 好工速遞**、**勞工處 gov.hk**、**JobsDB**、**LinkedIn**、**Recruit**、**JobMarket**、**foundit**、**eFinancialCareers**、**OfferToday**、**獵聘 Liepin** 十座可用據點；**Indeed** 因站方對香港訪客強制登入（2026-09-11 真人實測）現標為**停用**（程式碼保留，可原地復活）；**BOSS直聘** 為受限模組（香港職缺為空且需登入，見文末路線圖）。

> 🆕 **2026-09-11：獵聘從「受限空殼」翻身為第十座據點。** 舊版判定「香港覆蓋未證實、多數回 0 筆」，本次重新偵察發現兩個關鍵：① 香港城市碼是 **320**（舊碼 `900` 是錯的）② **`city` 與 `dq` 必須同時送**才會過濾（只送 `city` 時站方完全不過濾）。修正後實測取得 **40 筆香港職缺、七個關鍵欄位零空值**，並支援香港 18 區篩選。詳見「🧭 技術筆記（獵聘）」。

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
  - **支援近期篩選 `--days N`**：列表卡已含刊登日（2026-09-09 起**優先取 `<time datetime="YYYY-MM-DD">` 絕對日期**；無該屬性才用相對文字 `4 days ago`，強制英文語系以利解析），直接由列表過濾，不必抓詳情。此外 `--days` 會**下推為站方端 `f_TPR=r<N×86400>`**，讓 LinkedIn 只回傳該時間窗內的職缺（實測 `--days 7` 回傳 80 筆全數落於 7 天內）。
  - **支援排序 `--sort post_dt_desc`**：對應網址 `sortBy=DD`（最新優先），並讓 `--days` 提早停翻；其餘選項為 gov_hk 專有，傳入會警告並回退預設。
  - **雙軌翻頁（2026-09-09 改版）**：第 1 頁走 `/jobs/search/`（一次 ~58 張），第 2 頁起改走訪客分頁端點 `/jobs-guest/jobs/api/seeMoreJobPostings/search`（`start` 為索引、每頁 10 張，且 `start` 從已累積筆數接續，避開「兩個端點共用結果池」的陷阱）。全程以 `job_id` 去重，整頁皆已見即停，避免無限迴圈。實測 `--pages 4 --days 7` 可累積 **80 筆全數有效**（改版前第 2 頁即停）。
  - **不支援項**：`--category` / `--industry`（LinkedIn 簡易搜尋無乾淨對應維度，傳入會忽略並提示）。
  - ✅ **天花板已上修（2026-09-09）**：改用訪客分頁端點後，實測 `--pages 4 --days 7` 可累積 80 筆（58→66→73→80）且全數符合時間窗，不再受限於 ~60 筆。訪客結果仍會「漂移」（同一 `start` 每次取樣可能不同），故以去重累積、邊際效益遞減；提供 `li_at` cookie 後為登入態，翻頁最穩定。
- **Recruit 據點已實戰驗證（擴充八站 Wave 1）**：
  - **ASP.NET WebForms + Vue 3 混合站**，無 Cloudflare、無 CAPTCHA，但篩選值藏在 hidden 欄位（不是 checkbox），搜尋鈕被 CSS 藏住，翻頁只能在真瀏覽器內跑 `__doPostBack`。
  - **支援關鍵字 + 地區 + 職能三維篩選**：`--district`（94 區，中英文皆可，如 `元朗`/`Yuen Long`）、`--category`（34 大類 + 290 細類，中英雙語）。實測 engineer 全站 820 筆 → 元朗 15 筆、資訊科技大類 204 筆、元朗+資訊科技 1 筆。
  - **支援近期篩選 `--days N`**：列表卡已含刊登日（`YYYY-MM-DD`），直接由列表過濾，不必抓詳情（瞬時）。
  - **支援排序 `--sort`**：`post_dt_desc` / `salary_desc` / `exp` / `edu` / `relevance` 對應結果頁 `sortByDDL`。
  - **每頁 25 筆、翻頁約 1.7 秒**；`--detail` 走詳情頁的 JSON-LD（地區 / 行業 / 僱傭類型 / 描述，約 0.2 秒/筆）。
  - **不支援項**：`--industry`（該站無行業篩選維度，傳入會忽略並提示）。
  - ⚠️ **列表無地區欄**：地區只在詳情 JSON-LD 裡，故預設 `location` 為空，需加 `--detail` 才補得到。
- **JobMarket 求職廣場據點已實戰驗證（擴充八站 Wave 1）**：
  - **JSP 站、全程普通 requests（不需 Playwright）**：列表端點 + 批次 API + 詳情頁皆可直接 GET；無 Cloudflare 挑戰、無 CAPTCHA，robots 極寬鬆。
  - **支援關鍵字 + 地區 + 職能 + 行業四維篩選**：`--district`（5 大區 + 75 子區，中英文皆可，如 `元朗`/`Yuen Long`）、`--category`（28 大類 + 195 細類）、`--industry`（30 行業）。實測 engineer 204 筆、資訊科技職能 21 筆、元朗 engineer 1 筆。
  - **列表階段即自動補地區/職缺類型/行業/學歷**：呼叫站方自己的批次 API `/API/Web/GetJobDetail/<ids>`（每頁 1 次），`location` 預設就有值——與 Recruit 不同，不必 `--detail`。
  - **支援近期篩選 `--days N`**：列表卡已含刊登日（`04 Sep 2026`），直接由列表過濾，瞬時。
  - **每頁 20 筆、翻頁 `Page=N` 無重複**；`--detail` 走 `/Job/CurrentJob?Jobid=` 完整描述。
  - **不支援項**：`--sort`（站方 Order 參數實測無效；列表預設已按刊登日新→舊，傳入會警告並忽略）。
- **foundit 據點已實戰驗證（擴充八站 Wave 2，原 Monster HK）**：
  - **指紋 WAF 站**：`/search/*` 對 requests 與 Playwright 內建 Chromium headless 一律 403；**需以系統 Google Chrome 指紋（`channel="chrome"`）headless 開啟**。職位詳情 `/job/*` 則普通 requests 直達（~0.5 秒/筆）。
  - **關鍵字搜尋走 SEO 瀏覽頁**：站方自己的搜尋 API 目前故障（404），改打伺服器端渲染的 `/search/<關鍵字>-jobs[-in-<地區>][-<頁碼>]`（20 筆/頁），engineer 實測 2,989 筆。
  - **支援地區 `--district`**：46 個瀏覽頁 slug（中英文皆可，如 `kowloon`/`九龍`）。
  - **支援近期篩選 `--days N`**：列表卡含「Posted N hours/days ago」相對日期，瞬時過濾。
  - **`--detail` 走詳情頁 JSON-LD**（描述 / 刊登日 / 地區 / 僱傭類型 / 薪資）。
  - **保底資料源**：`/xmlsitemap/active-jobs-sitemap0.xml.gz`（全站 8,799 職位 + lastmod）。
  - **不支援項**：`--category` / `--industry` / `--sort`（SEO 瀏覽頁無對應參數，傳入會警告並忽略）。
- **eFinancialCareers 據點已實戰驗證（擴充八站 Wave 2）**：
  - **純 JSON API、全程普通 requests（不需瀏覽器）**：`job-search-ui.efinancialcareers.com/v3/efc/jobs/search`（robots `Disallow: /v1` 暗示的版本化端點一族）。
  - **金融/銀行/投資垂直站**：香港職缺 ~2,900 筆（空關鍵字全站 71,605 筆），與綜合站互補性強。
  - **支援地區 `--district`**：大區級（`Hong Kong` / `Hong Kong Island` / `Kowloon`，中英文皆可；站方地區索引對細分區回 0 筆，故只收錄大區）。
  - **支援近期篩選 `--days N`**：API 每筆含 `postedDate`（ISO 時間戳），瞬時過濾。
  - **`--detail` 走詳情頁 JSON-LD**（完整描述 / baseSalary / skills）。
  - **不支援項**：`--category` / `--industry` / `--sort`（站方僅 relevance 排序，其餘值一律被忽略；傳入會警告並忽略）。
- **獵聘 / BOSS直聘 受限模組（擴充八站 Wave 5，僅因用戶明確要求提供）**：
  - ⚠️ 兩站 robots.txt 明文禁搜尋抓取（`Disallow: /*?*` / `Disallow: /*?query=*`）、反爬極兇（IP 驗證碼 / 全站安全驗證），且**均無香港站**（`/hk/` 404）。
  - 模組可執行、行為可預期：首次實例化即警告 robots 與反爬風險；被攔時回 0 筆（明確警告，非靜默、非 crash）。
  - 獵聘已驗證的資料機制：搜尋頁空殼 → 站方 JS 呼叫 `api-c.liepin.com/…/pc-search-job`（POST）；瀏覽器首次導航偶爾可攔截到回應，多次請求即觸發 IP 驗證碼。
  - **不支援項**：`--district`（zhipin）/ `--category` / `--industry` / `--sort` / `--days` / `--detail` / `--pages > 1`（全部警告後忽略或回空）。
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
├── LICENSE                 # MIT 授權
├── .gitattributes          # 換行符策略：全專案統一 LF（消除 Windows CRLF 警告）
├── tools/                  # 診斷／偵察腳本（非常規執行所需，見 tools/README.md）
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
│   ├── jobsdb.py            # JobsDB 爬蟲（已實作 + 實測；關鍵字+翻頁+--days+職能/地區篩選）
│   ├── linkedin.py          # LinkedIn 爬蟲（訪客模式，免登入免瀏覽器）
│   ├── linkedin_geo.json    # LinkedIn 地區字典（18 區：中文/英文/別名/geoUrn）
│   ├── indeed.py            # Indeed 爬蟲（Playwright 過 Cloudflare + 內嵌 pubDate 取日）
│   ├── recruit.py           # Recruit 爬蟲（WebForms：hidden 欄位篩選 + __doPostBack 翻頁）
│   ├── recruit_districts.json    # Recruit 地區字典（94 區：英文原名 + 45 個中文別名）
│   ├── recruit_categories.json   # Recruit 職能字典（34 大類 + 290 細類，中英雙語 + cat_id）
│   ├── jobmarket.py         # JobMarket 爬蟲（JSP：純 requests + 批次 API 補地區）
│   ├── jobmarket_districts.json  # JobMarket 地區字典（80 項：5 AreaID + 75 AreaLocationID，中英雙語）
│   ├── jobmarket_categories.json # JobMarket 職能字典（28 大類 + 195 細類，細類記 cat_id）
│   ├── jobmarket_industries.json # JobMarket 行業字典（30 業，中英雙語）
│   ├── foundit.py           # foundit 爬蟲（原 Monster HK：Chrome 指紋 + SEO 瀏覽頁）
│   ├── foundit_locations.json    # foundit 地區字典（46 個瀏覽頁 slug，中英雙語）
│   ├── efc.py               # eFinancialCareers 爬蟲（純 JSON API，免瀏覽器）
│   └── efc_geo.json         # eFC 地區字典（3 大區：Hong Kong / HK Island / Kowloon）
├── tests/                  # 離線測試（零請求）：python -m unittest discover -s tests
│   ├── test_job_model.py   # JobRecord 模型與壞資料防禦
│   ├── test_exporter.py    # 去重 / BOM / 損毀備份
│   └── test_dictionaries.py # 17 個字典的完整性與跨站隔離
├── docs/
│   ├── moovup_地區編號對照表.md    # 人可直讀的 Moovup 地區↔編號對照表
│   └── 擴充八站開發計畫.md         # 擴充八站的偵察結論、五波順序與驗收標準
├── output/                 # 匯出檔案目錄（自動建立）
└── requirements.txt
```

---

## ⚙️ 環境要求與安裝

- Python 3.10+
- 需要 Playwright 的據點：**Moovup**（Cloudflare Turnstile）、**JobsDB**（Cloudflare）、**Indeed**（Cloudflare，⚠️ **須本機 `channel="chrome"`**）、**Recruit**（WebForms 翻頁需真瀏覽器）、**foundit**（⚠️ **須本機 `channel="chrome"`**，內建 Chromium 被 WAF 403）。**JobMarket / eFinancialCareers / OfferToday** 不需要（全程普通 requests）。
- ⚠️ **foundit / 獵聘 / BOSS直聘 需要本機安裝 Google Chrome**：foundit 的 WAF 與獵聘、BOSS直聘的反爬均以指紋區分瀏覽器，模組以 `channel="chrome"`（系統 Chrome）headless 開啟；未安裝 Chrome 時會啟動失敗並提示。
- 只需 `requests` + `beautifulsoup4`、不需瀏覽器的據點：**勞工處 gov.hk**、**LinkedIn**（訪客模式）。

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
| `--source` | 否 | `moovup` | 爬蟲來源：`moovup` \| `gov_hk` \| `jobsdb` \| `linkedin` \| `indeed`（停用） \| `recruit` \| `jobmarket` \| `foundit` \| `efc` \| `liepin` \| `zhipin`（受限） \| `offertoday` \| `all`（全部**已啟用**據點各跑 `--pages` 頁；`enabled=False` 的 indeed / liepin / zhipin 會自動略過並提示，仍可個別指定）。各站支援差異見下方「📊 各站功能支援矩陣」。 |
| `--keyword` | 否 | 空 | 搜尋關鍵字（繁體中文或英文皆可；**留空 = 不限定關鍵字，僅依地區/類別瀏覽，gov_hk 支援**；JobsDB 留空則搜全站） |
| `--pages` | 否 | `3` | 最大翻頁數。各站每頁筆數不同（Moovup 12、勞工處 ~20、JobsDB ~20–30、LinkedIn 首頁 ~58／續頁 10…），詳見矩陣「每頁筆數」列。 |
| `--output` | 否 | `json` | 輸出格式：`json` \| `csv` \| `both` |
| `--detail` | 否 | 關 | 同時抓取每筆職位的詳情（職責 / 要求 / 發佈時間 / **刊登日期**）；**JobsDB 的 `--detail` 為 best-effort**，詳情頁選擇器與列表略有差異，實測微調中 |
| `--outfile` | 否 | 自動命名 | 自訂輸出檔名（不含副檔名），預設 `output/<source>_<keyword>` |
| `--district` | 否 | 無 | 地區篩選，**多數據點已接上**（支援的站與格式見矩陣「地區」列）。例：JobsDB 用中文名或 slug（`荃灣` \| `tsuen-wan`，見 `scrapers/jobsdb_districts.json`）；勞工處用數字 ID 或中文；Moovup 用 shortCode。**各站字典獨立，不可混用**；逗號分隔時 JobsDB 僅取第一個。 |
| `--category` | 否 | 無 | 工作種類 / 職能篩選（支援：勞工處、JobsDB、Recruit、JobMarket、OfferToday，見矩陣）。例：JobsDB 用中文名 / 英文 / slug（見 `scrapers/jobsdb_classifications.json`）。**各站字典獨立**。 |
| `--industry` | 否 | 無 | 行業篩選（支援：勞工處、JobMarket、OfferToday）。JobsDB 無獨立行業維度，傳入會被忽略並提示。 |
| `--sort` | 否 | 無 | 排序：**gov_hk 全選項支援**（`post_dt_desc`(新→舊) / `post_dt_asc`(舊→新) / `salary_desc`·`salary_asc`(月薪) / `yr_exp_asc`·`yr_exp_desc`(經驗) / `edu_lvl_asc`·`edu_lvl_desc`(學歷)）；**JobsDB 與 LinkedIn 僅支援 `post_dt_desc`**（新→舊），其餘選項為 gov_hk 專有、傳入會警告並回退預設。設 `--days` 未指定 `--sort` 時自動套 `post_dt_desc` |
| `--days` | 否 | 無 | 只保留最近 N 天內刊登的職位。各站實作不同：勞工處 / JobsDB / LinkedIn / OfferToday 有**站方端**日期參數；Moovup 不支援（警告後忽略）；獵聘以 `refreshTime`（刷新日）近似。詳見矩陣「近期」列。 |

### 📊 各站功能支援矩陣（重要：功能互不相連）

> ⚠️ **不同站點的功能彼此獨立**：下表每一格的支援方式、參數語意、字典都**只屬於該站**。
> 任一站新增 / 修改某功能（如排序選項、地區解析）**不會影響其他站**。
> 不支援的功能一律 `logger.warning` 後忽略並提示，絕不報錯中斷或改變他站輸出。

| 功能 / 參數 | Moovup | 勞工處 gov.hk | JobsDB | LinkedIn | Indeed | Recruit | JobMarket | foundit | eFinancialCareers | 獵聘 ⚠️ | BOSS直聘 ⚠️ | OfferToday |
|------|------|------|------|------|------|------|------|------|------|------|------| ------ |
| 關鍵字 `--keyword` | ✅ 支援 | ✅ 支援 | ✅ 可留空 | ✅ 支援 | ✅ 支援（⚠️ **必給關鍵字**——空 `q=` 站方回 `did not match any jobs` / 0 筆） | ✅ 可留空（純分類瀏覽） | ✅ 支援（可留空） | ✅ 支援（可留空→地區瀏覽頁） | ✅ 支援（可留空） | ⚠️ 機制已驗證（40 筆/頁）但連 6–7 支請求會觸發 IP 驗證碼 | ⚠️ 香港職缺為空（港澳台專區 0 張 + 登入牆） | ✅ 支援（可留空） |
| 地區 `--district` | ✅ shortCode（32 區） | ✅ 數字 ID（27 項） | ✅ slug（40 區） | ✅ 18 區字典（zh→英文 `location=`；geoUrn 訪客模式無效） | ✅ 自由文字 `l=`（預設 Hong Kong） | ✅ 數字 ID（94 區，中英文皆可，逗號多選）⚠️ **列表本身無地區欄**：單區篩選時**零請求回填**該區；多區／未篩選 → 用 `--fill-location`（AJAX 逐筆，25 筆/頁 = 25 支請求）或 `--detail` | ✅ AreaID 5 大區 + AreaLocationID 75 子區（中英文皆可，逗號多選） | ✅ 46 個瀏覽頁 slug（中英文皆可） | ⚠️ 僅 3 大區（HK / HK Island / Kowloon；細分區站方回 0 筆） | ⚠️ 僅城市碼 + 客戶端分區比對（`320` 香港；18 區見 `liepin_areas.json`，簡繁英皆可） | ❌ 不適用（香港不在站方城市體系） | ✅ 純 code 18 區 + 129 子區（中英文皆可，逗號多選） |
| 職能 / 工作種類 `--category` | ❌ 不適用 | ✅ 數字 ID（29 類） | ✅ slug（30 職能） | ❌ 不適用 | ❌ 不適用 | ✅ 數字 ID（34 大類 + 290 細類，中英雙語） | ✅ 數字 ID（28 大類 + 195 細類；細類可單送） | ❌ 不適用（SEO 瀏覽頁無此參數） | ❌ 不適用 | ❌ 不適用 | ❌ 不適用 | ✅ POSITION level-2 code（31 大類 + 431 細類） |
| 行業 `--industry` | ❌ 不適用 | ✅ 數字 ID（27 業） | ❌ 職能已涵蓋 | ❌ 不適用 | ❌ 不適用 | ❌ 不適用（站方無此維度） | ✅ 數字 ID（30 業，中英雙語） | ❌ 不適用 | ❌ 不適用（sectors 無對應過濾參數） | ❌ 不適用 | ❌ 不適用 | ✅ INDUSTRY level-2 code（15 大類 / 53 細類；大類自動展開細類） |
| 排序 `--sort` | ❌ 不適用 | ✅ 8 選項全支援 | ⚠️ 僅 `post_dt_desc` | ⚠️ 僅 `post_dt_desc` | ❌ 不適用（訪客） | ⚠️ 5 選項（`post_dt_desc`/`salary_desc`/`exp`/`edu`/`relevance`） | ❌ 不適用（站方 Order 實測無效；預設已新→舊） | ❌ 不適用（SEO 頁固定排序） | ❌ 不適用（僅 relevance，其他值被忽略） | ❌ 不適用 | ❌ 不適用 | ❌ 不適用（API 無排序參數） |
| 近期 `--days` | ❌ 不適用 | ✅ **站方端 `criteria.postedDtFr/To`**（2026-09-09 新增，格式 DD/MM/YYYY：列表無日期，舊流程須逐筆抓詳情取 `#postedDt`，改為站方端後 20 筆僅 2 支請求） | ✅ 列表含日期 + **站方端 `daterange=N`**（2026-09-10 新增，實測站方總數 2,241 → 467 筆；⚠️ 只吃 `1/3/7/14/31` 五個離散值，其餘數字站方不理會，本爬蟲自動向上取整） | ✅ 列表含**絕對日期**（`<time datetime="YYYY-MM-DD">`）；`--days` 另**下推站方端 `f_TPR=r<N×86400>`**（2026-09-09 新增，實測 80 筆全數落於 7 天內） | ⛔ **2026-09-11 據點停用，本列僅供復活時參考**：內嵌職位陣列瞬時（~9s，不點擊）+ **站方端 `fromage=N`**（2026-09-09 加入，⚠️ **從未實測驗證**——該站次日即遭封鎖、最終證實為強制登入牆，見 Indeed 章節）⚠️ 2026-09-08 修正：改用 `formattedRelativeTime`，站方只給下限（`30+ days ago`）時用 `createDate`；舊碼用 `pubDate`（feed 原始刊登日，實測 947–2811 天前）且以大寫 `jobKey` 配對（那是追蹤物件）→ 日期張冠李戴，已修 | ✅ 列表含日期（`YYYY-MM-DD`，瞬時） | ✅ 列表含日期（`04 Sep 2026`，瞬時） | ✅ 列表含相對日期（瞬時） | ✅ API `postedDate` ISO 瞬時（⚠️ 2026-09-09 實測 `postedDate` / `datePosted` / `daysSincePosted` 三種參數名皆無效，站方端無日期過濾；因列表已含 ISO 日期、客戶端零成本篩選，影響極小） | ⚠️ 客戶端（`refreshTime` **刷新日**近似，非刊登日：實測 40 筆中 1天→6 / 3天→22 / 7天→33 / 14天→38） | ❌ 不適用 | ⚠️ 送 `publishTime` + 客戶端再篩（僅 `on MM-DD` 可算天數） |
| 詳情 `--detail` | ✅ 支援 | ✅ 支援 | ✅ 已實測修正（2026-09-08：selector 全錯導致只抓到標題——正確值為 `advertiser-name`／`job-detail-location`／`job-detail-classifications`／`job-detail-work-type`／`jobAdDetails`；薪資無穩定欄位故留空） | ✅ 免登入 API | ✅ 已實測修正（2026-09-08）：描述原只抓到 17 字（`(.*?)</div>` 撞上巢狀 div）→ 改 DOM `inner_text` + 巢狀配對，實測 934–2476 字；另加點擊重試與 🐢 熔斷（連續 2 筆失敗即停止），16 筆由 **9 分鐘 / 剩 1 筆** → **~1 分鐘 / 完整** | ✅ JSON-LD（~0.2s/筆）——2026-09-08 起地區另有更省的 `--fill-location`（`/jobseeker/JobDetail.aspx?jobOrder=<id>&ajax=Y`，約 35KB，純 requests） | ✅ CurrentJob 頁（完整描述；地區列表階段已有） | ✅ JSON-LD（requests 直達 ~0.5s/筆） | ✅ JSON-LD（完整描述 / baseSalary / skills） | ❌ 不適用（詳情受驗證碼保護） | ❌ 不適用（詳情受安全驗證保護） | ✅ 已實測：完整描述（HTML→純文字）+ 行業 `industryDesc`（列表無此欄） |
| 每頁筆數 | 12（GraphQL） | ~20 | ~20–30 | 首頁 ~58／續頁 10（guest 端點） | ~16 | 25 | 20 | 20（SEO SSR） | 50（pageSize 可調，API 實測 100 也吃） | 40（pageSize=40；實測 42 張卡、剔除 2 筆外地後 40 張全在香港） | 0（港澳台專區無職缺） | 10（站方上限） |
| 瀏覽器 Playwright | ✅ 需 | ❌ 不需 | ✅ 需 | ❌ 不需 | ✅ 需（⚠️ **必須 `channel="chrome"`**——2026-09-08 實測內建 Chromium 指紋被 CF 擋：標題 `Just a moment...` + `Additional Verification Required`，輪詢 45s 也不過；改用本機 Chrome 後立即正常。無本機 Chrome 時自動退回並警告。⚠️⚠️ **2026-09-09：另須「UA 不覆寫」**，否則 Client Hints 版本不一致仍會被擋；⛔ **2026-09-11：據點停用（0 筆）**——真人手動開也只見登入牆，非單純封鎖（詳見 Indeed 章節）） | ✅ 需（`__doPostBack` 翻頁） | ❌ 不需（純 requests） | ✅ 需（⚠️ **必須 `channel="chrome"`**，內建 Chromium 被 WAF 403；詳情頁則 requests 直達） | ❌ 不需（純 JSON API） | ✅ 需（`channel="chrome"`；**必須讓頁面自己的 JS 發請求**——直接 requests 或瀏覽器內 fetch 打 API 皆回 `flag=0/-1400`；連 6–7 支請求觸發 IP 驗證碼） | ✅ 需（`channel="chrome"`；⛔ 2026-09-11 複查：首頁改為可開，但港澳台專區 0 張 + 登入牆） | ❌ 不需（🚀 冷 requests 直打 API，無 cookie 亦可） |
| 深翻頁穩定度 | ✅ cursor | ✅ quickview | ✅ page | ✅ 雙軌（2026-09-09）：首頁 `/jobs/search/` + 續頁 guest 端點，`start` 從已累積筆數接續；實測 4 頁 80 筆，`li_at` 更穩 | ⚠️ `start=N`；cf_clearance 沿用，`--days` 已無需點擊、`--detail` 改 JS 點擊提速 | ✅ Next 鈕 `__doPostBack`，~1.7s/頁 | ✅ `Page=N`，實測無重複 | ✅ 路徑後綴 `-2`/`-3`…（SSR） | ✅ `page=N`（API 穩定） | ❌ 僅第 1 頁（`currentPage` **未實測驗證**——偵察時觸發驗證碼而停手） | ❌ 僅第 1 頁（港澳台專區本身 0 張） | ✅ `page=N`（靠 `hasMore` 判斷；`total` 是推薦池規模，不可信） |

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

# 23) LinkedIn：訪客模式深翻頁（2026-09-09 起第 2 頁起自動走 guest 分頁端點，
#     實測 --pages 4 --days 7 可累積 80 筆；設 li_at cookie 則為登入態，翻頁最穩）
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

# 27) Recruit：基本搜尋（需 Playwright：WebForms 翻頁要在真瀏覽器內跑 __doPostBack）
python main.py --source recruit --keyword "engineer" --pages 2

# 28) Recruit：地區篩選（94 區字典，中英文皆可，如 元朗 / Yuen Long）
python main.py --source recruit --keyword "engineer" --district 元朗 --pages 2

# 29) Recruit：職能篩選（34 大類 + 290 細類；給細類會自動補上所屬大類，如 DBA → 資訊科技）
python main.py --source recruit --category "資訊科技" --days 7 --pages 2
python main.py --source recruit --category "DBA" --days 7

# 30) Recruit：地區 + 職能 + 近期三維（列表已含刊登日 → --days 瞬時過濾）
python main.py --source recruit --district 元朗 --category "資訊科技" --days 7 --outfile recruit_yl_it_7d

# 31) Recruit：要地區 / 行業 / 職缺類型 / 描述時加 --detail（詳情頁 JSON-LD，~0.2s/筆；列表無地區欄）
python main.py --source recruit --keyword "engineer" --pages 2 --detail --outfile recruit_eng_detail

# 31b) Recruit：只想補地區、不想抓整份詳情 → --fill-location（AJAX 端點，比 --detail 輕）
#      （若 --district 只給單一地區，連這個都不必加：會零請求直接回填）
python main.py --source recruit --keyword "engineer" --pages 1 --fill-location --outfile recruit_eng_loc

# 32) Recruit：排序（post_dt_desc / salary_desc / exp / edu / relevance → 結果頁 sortByDDL）
python main.py --source recruit --keyword "engineer" --sort salary_desc --pages 2

# 33) JobMarket：基本搜尋（純 requests，不需 Playwright）
python main.py --source jobmarket --keyword "engineer" --pages 2

# 34) JobMarket：地區篩選（5 大區 + 75 子區，中英文皆可，如 元朗 / Yuen Long / 新界）
python main.py --source jobmarket --keyword "engineer" --district 元朗 --pages 2

# 35) JobMarket：職能 + 行業篩選（28 大類 + 195 細類；30 行業）
python main.py --source jobmarket --category "資訊科技" --pages 2
python main.py --source jobmarket --industry "Banking / Finance / Investment" --days 7

# 36) JobMarket：地區 + 近期三維（列表已含刊登日 → --days 瞬時；地區列表階段即自動補齊）
python main.py --source jobmarket --district 元朗 --days 7 --outfile jobmarket_yl_7d

# 37) JobMarket：要完整描述時加 --detail（走 /Job/CurrentJob?Jobid=）
python main.py --source jobmarket --keyword "engineer" --pages 2 --detail --outfile jobmarket_eng_detail

# 38) foundit：基本搜尋（SEO 瀏覽頁 SSR；⚠️ 需本機 Google Chrome——WAF 封鎖 Chromium 指紋）
python main.py --source foundit --keyword "engineer" --pages 2

# 39) foundit：地區篩選（46 個瀏覽頁 slug，中英文皆可）
python main.py --source foundit --keyword "developer" --district kowloon
python main.py --source foundit --keyword "developer" --district 九龍

# 40) foundit：近期三維（列表含「Posted N hours ago」相對日期 → --days 瞬時）
python main.py --source foundit --keyword "engineer" --days 7

# 41) eFC：基本搜尋（純 JSON API，免瀏覽器；金融/銀行/投資垂直站）
python main.py --source efc --keyword "risk manager" --pages 2

# 42) eFC：地區（僅大區：Hong Kong / Hong Kong Island / Kowloon，中英文皆可）+ 近期
python main.py --source efc --keyword "analyst" --district 九龍 --days 7
python main.py --source efc --keyword "" --district "Hong Kong Island"   # 空關鍵字 = 純瀏覽

# 43) 獵聘（⚠️ 受限模組：robots 禁抓 + IP 驗證碼；回 0 筆屬預期，警告會說明原因）
python main.py --source liepin --keyword "engineer"

# 44) BOSS直聘（⚠️ 受限模組：全站安全驗證；回 0 筆屬預期）
python main.py --source zhipin --keyword "engineer"
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
- **⚠️ User-Agent 必須與本機 Chrome 同版本（2026-09-10 血淚教訓）**：
  Cloudflare 會比對 UA 與 Client Hints（`sec-ch-ua`）回報的真實版本。UA 說 `Chrome/124`
  但瀏覽器實為 152，這種落差是極經典的機器人訊號，會直接卡在 managed challenge
  （Indeed 據點即因此陣亡，詳見其技術筆記）。
  本專案已改為**開機自動量測**本機 Chrome 版本（`config.CHROME_VERSION`），
  不會再腐化；可用環境變數 `CHROME_UA_VERSION` 手動覆寫。
  👉 **若你換了瀏覽器或在沒有 Chrome 的機器上執行，請確認這個值是否合理。**
- **反爬禮貌**：預設已加入請求間隔與隨機抖動，請勿惡意高併發爬取。

---

## 🩺 全站健康檢查（SOP + 基準）

### 為什麼要定期做

**老據點會悄悄壞掉。** Indeed 就是活教材——它在 2026-09-08 還能抓 16 張卡片，
兩天後連真人也只能看到登入牆。中間沒有任何錯誤訊息，只是默默回傳 0 筆。
定期健康檢查是唯一能提早發現的方法。

### SOP（🐢 依爬蟲禮節）

一次 1 支請求、間隔 ≥8 秒、單輪 ≤5 站、每輪回報；遇限速／驗證碼／非預期回應立即停手。
Indeed 已停用，不列入；獵聘 / BOSS直聘屬受限模組，確認受限即可。

```bash
# 基本搜尋（每站 1 頁）
for s in moovup gov_hk jobsdb linkedin recruit jobmarket foundit efc offertoday; do
  python main.py --source $s --pages 1 --outfile _health_$s
  sleep 8
done

# 再對「有站方端日期過濾」的四站補驗 --days 7
for s in gov_hk linkedin jobsdb offertoday; do
  python main.py --source $s --pages 1 --days 7 --outfile _hdays_$s
  sleep 8
done
```

產出檔名以 `_` 開頭者屬偵察性質，檢查完請歸檔到 `output/_probe/`
（⚠️ 勿用 `mv output/_*.json` 一次掃——會連正式資料集一起搬走，已發生過一次）。

### 最近一次檢查結果（2026-09-11，環境：HKT 家用寬頻）

十座可用據點**全數正常**（獵聘為 2026-09-11 新加入）：

| 來源 | 基本搜尋 | `--days 7` | 站方端日期參數 |
|---|---|---|---|
| moovup | 12 | — | 不適用 |
| 勞工處 gov_hk | 20 | 20 ✅ | `postedDtFr=04/09/2026` ~ `postedDtTo=11/09/2026` |
| JobsDB | 30 | 30 ✅ | `daterange=7` |
| LinkedIn | 60 | 60 ✅ | `f_TPR=r604800` |
| Recruit | 25 | — | 不適用（列表含日期，客戶端篩） |
| JobMarket | 25 | — | 不適用（列表含日期） |
| foundit | 20 | — | 不適用（列表含相對日期） |
| eFinancialCareers | 50（`total=70,412`） | — | 無站方端參數（客戶端篩 ISO 日期） |
| OfferToday | 10 | 8 ✅ | `publishTime` + 客戶端再篩 |
| **獵聘 Liepin** 🆕 | **40**（香港，`total≈800`） | 33（客戶端，以 `refreshTime` 近似） | 無（客戶端篩）⚠️ **連 6–7 支請求會觸發 IP 驗證碼，檢查時僅跑 1 次** |
| ⛔ Indeed | — | — | **據點停用**（強制登入牆，見其技術筆記） |
| ⚠️ BOSS直聘 | — | — | **受限**：香港職缺為空（港澳台專區 0 張 + 登入牆），不列入檢查 |

下次檢查時請與此表比對：**筆數「歸零」或「異常膨脹」都算異常**。
⚠️ 獵聘因驗證碼門檻低，健康檢查時**只跑 1 次**。
⚠️⚠️ 獵聘回 0 筆時**不要只看 log**：2026-09-14 實測，即使已跳轉到驗證碼頁，
log 仍可能只印「未攔截到搜尋 API 回應」（跳轉時序不定，URL 判讀會漏）。
正確做法是執行 `python tools/_probe_liepin.py` 聽診，直接看**標題**（`安全中心-验证码`）
與 euuid 解碼內容，一次區分「驗證碼／站方改版／等待不足」三種病因。
（模組已於 2026-09-14 改為**優先用標題判讀**，0 筆時也會印出最終 URL 與標題。）

> 📌 **獵聘現況（2026-09-14，定稿）**：本機 HKT 寬頻 IP 已被 **IP 級驗證碼封鎖**
> （`captchaPage_ip_PC`，冷卻 ≥38 小時未解除）→ **暫不列入健康檢查巡檢**。
> 程式邏輯（`--district` / `--days`）已於同日**零請求離線驗證全綠**，
> 僅「分頁 `currentPage` 端到端」與「`--district` 實跑」待換 IP 或冷卻後補測。
> 期間回 0 筆屬**預期，非故障**；勿密集重試（只會延長封鎖）。

---

## 🧪 離線測試（`tests/`）

> 🐢 **為什麼要有測試**：這是爬蟲專案，任何驗證若只能靠真實請求，就與
> 「不要太狠、一步一步、不要被封」直接衝突。這套測試的任務是把**能在本地推理完的
> 部分全部搬進沙盤**，讓我們不必為了確認一行邏輯而多打一支請求。

```bash
python -m unittest discover -s tests -v      # 22 個測試，約 0.06 秒，零網路請求
```

框架選用**標準庫 `unittest`**（非 pytest）：零安裝、零依賴變更，clone 下來即可跑。

| 測試檔 | 守什麼 |
|---|---|
| `test_job_model.py` | `JobRecord` 的 id 生成、13 欄位集合、dict 往返、壞資料防禦 |
| `test_exporter.py` | 增量去重（後到覆蓋）、CSV 必帶 UTF-8 BOM 且恰 13 欄、**既有檔損毀時必須先備份 `.corrupt.bak`** |
| `test_dictionaries.py` | 17 個字典可載入且數量對齊功能矩陣、**字典不可跨站混用**、獵聘簡繁別名齊備 |

### 這套測試當場抓到的 bug（2026-09-15）

- ⚠️ **`JobRecord.from_dict` 缺 `source` / `job_id` 時會拋 `TypeError`** → 已修。
  影響比想像嚴重：`exporter._load_existing_json` 會把這個例外判為「檔案損毀」，
  於是**備份 `.corrupt.bak` 後整份舊資料被清空**——一份人工編輯過、少了一欄的 CSV
  就足以釀災。修法：`job_id` 補 `""`、`source` 由 `job_id` 前綴推導，
  讓單筆壞資料不再拖垮整份檔案。（行為改變僅發生在原本會拋例外的失敗路徑，
  正常資料輸出零改變。）
- ✅ 順帶查清 `linkedin_geo.json` 的 `districts` 是 **20 項**：
  18 區 + `香港`／`全港` 兩個 fallback（共用 geoUrn `103291313`），字典本身無誤。

### 測試的邊界（如實標註）

- 只涵蓋**零請求**的純邏輯與字典；各站的實際爬取（選擇器、翻頁、反爬）**仍需實測**，
  測試**不能**取代「🩺 全站健康檢查」。
- 字典數量斷言是**刻意釘死**的：數字變動代表字典被動過，測試會紅，確認後再更新對照表。

### 換行符策略（`.gitattributes`，2026-09-15）

Windows 本機 `core.autocrlf=true`，Git 在取出檔案時會轉成 CRLF；但編輯工具寫入的是 LF，
於是每次改檔都會跳出：

> *"This file uses 'LF' line endings, but Git is configured to convert them to
> 'CRLF' the next time the file is checked out."*

這**不是錯誤**，但每次都跳很吵，而且代表「同一份檔案在不同系統內容不同」。

對策：在專案根目錄放 `.gitattributes`，內容一行 `* text=auto eol=lf`——
**版本庫存 LF、工作區也維持 LF**，不再來回翻譯（`eol` 屬性優先於 `core.autocrlf`，
跨平台行為一致）。

- ✅ 查證過：既有提交的 blob **全部已是 LF**，故加入本檔**不產生任何歷史改動**
  （實測 `git add --renormalize .` 後 status 無任何額外異動）。
- ℹ️ 工作區目前仍有 18 個舊檔是 CRLF（多為 `scrapers/*.json` 字典），
  屬**無害殘留**：Git 會在提交時正規化，不影響執行也不再觸發警告；
  若想徹底一致，重 clone 一次即可全部變成 LF。
- 🧪 這對爬蟲的實質好處：輸出的 CSV／JSON 不會混進 `\r`，下游解析器較不易踩雷。

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
- **站方端日期過濾（`--days` → `criteria.postedDtFr/To`，2026-09-09 新增）**：
  搜尋表單其實內建刊登日期區間欄位，格式 **DD/MM/YYYY**（input placeholder 為
  「日日/月月/年年年年」）：`criteria.postedDtFr`=起日、`criteria.postedDtTo`=迄日。
  `--days N` 會經 `base_scraper` 的 `set_days()` 掛載點下推為 `(今天-N) ~ 今天`。
  - ⭐ **效益最大**：列表本身**沒有**刊登日，舊流程為了 `--days` 必須**逐筆抓詳情**
    取 `#postedDt`（20 筆 = 20 支額外請求）；改為站方端過濾後**完全不必抓詳情**，
    整輪只需 2 支請求（GET 表單 + POST 搜尋）。
  - 啟用後 `_within_days()` 直接信任站方結果（列表無日期，客戶端無從二度篩選）。
  - **實測驗證**：`--days 1` 抓前三筆詳情，刊登日皆為 `09/09/2026`（當天，天數 = 0）—
    站方職缺存量上萬，隨機三筆不可能全為同一天，證實過濾確實生效。
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
- **站方端日期過濾（`--days` → `daterange=N`，2026-09-10 新增）**：
  - **參數名與合法值直接由站方側邊欄「Date posted」的連結取得**（不靠猜）：

    | UI 選項 | 參數 |
    |---|---|
    | Today | `daterange=1` |
    | Last 3 days | `daterange=3` |
    | Last 7 days | `daterange=7` |
    | Last 14 days | `daterange=14` |
    | Last 30 days | **`daterange=31`** |

  - ⚠️ **只吃這五個離散值**：送 `daterange=10` 這類數字站方不予理會（與 eFC 的
    「參數名對了但站方不認」是同一類陷阱）。本爬蟲取「不小於請求天數的最小合法值」
    並記錄取整行為；`--days > 31` 則不啟用站方端，退回客戶端以 `jobListingDate` 篩選。
  - **實測證據**：同一關鍵字 `software engineer`，站方 `data-automation="totalJobsMessage"`
    由 **2,241 jobs** 降為 **467 jobs**（`daterange=7`）→ 過濾確實生效。
    ⚠️ 不可用「筆數」或「前幾筆日期」驗證：`--days` 會自動套 `sortmode=ListedDate`
    （最新優先），前 30 筆本來就都是幾分鐘內的，看起來就像生效了其實是假象。
- **翻頁機制**：URL 加 `?page=N`（N 從 1 開始）。到尾頁後卡片數為 0，爬蟲自動停止（與 Moovup 的 offset / gov.hk 的 quickview 都不同）。
  - ⚠️ **訪客深翻頁只到第 2 頁（2026-09-10 實測）**：`page=3` / `page=5` 皆回傳 0 張卡片
    且連 `totalJobsMessage` 都沒有，**與是否帶 `daterange` 無關**（兩種情況都 0）→ 屬站方既有行為，非本爬蟲限制。
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
  - ⚠️ **舊認知（2026-09-09 已突破）**：`/jobs/search/?start=N` 在訪客模式下會被隨機化 / AB 測試，同一 `start` 可能回傳不同批次（實測 `start=0/50` 同批、`start=10/25` 另批、`total` 數 265↔478 跳動），單次約 ~25–60 筆即撞天花板。**改用訪客分頁端點後可持續突破**（見下方「翻頁機制」）。
  - **解鎖最穩定翻頁**：在 `config.LINKEDIN_LI_AT`（或環境變數 `LINKEDIN_LI_AT`）填入自己的 `li_at` cookie 即可切到登入態，此時 `start` 翻頁趨於穩定、可抓更深。cookie 取得：瀏覽器登入 linkedin.com → DevTools → Application → Cookies → 複製 `li_at` 值。⚠️ cookie 等同帳號憑證，僅供個人使用、切勿外洩，且請遵守 LinkedIn 服務條款、維持禮貌爬取頻率。
- **搜尋機制：伺服器渲染 HTML**（非 GraphQL、非 JSON API）。`GET /jobs/search/?keywords=K&location=L&start=N[&sortBy=DD]` 直接回傳含職位卡的完整 HTML，用 `BeautifulSoup` 解析即可（訪客模式實測回傳 ~58 張職位卡）。
- **翻頁機制（2026-09-09 改版：雙軌）**：

  | 頁數 | 端點 | 行為 |
  |------|------|------|
  | 第 1 頁 | `/jobs/search/` | 一次取數十張卡（實測 58），CP 值最高 |
  | 第 2 頁起 | `/jobs-guest/jobs/api/seeMoreJobPostings/search` | `start` 為索引、**每頁固定 10 張** |

  - 後者是 LinkedIn 給搜尋引擎 / 未登入訪客用的分頁端點，回傳**裸 HTML 片段**（無
    `.jobs-search__results-list` 外層容器），但卡片內部結構與 `/jobs/search/` 完全相同，
    故解析邏輯共用（程式碼在 selector 落空時自動退回 `li`）。
  - ⚠️ **兩個陷阱（皆為實測踩坑，勿重蹈）**：
    1. **每頁是 10 張、不是 25 張**——沿用舊步長 25 會直接吃掉 15 張卡。
    2. **帶相同 `f_TPR` + `sortBy` 時，兩個端點共用同一個結果池**。若第 2 頁從
       `start=10` 起算，會整頁落在首頁已取的 58 筆內、被去重擋掉而「假性停止翻頁」。
       故 `start` 一律從**已累積筆數**接著往下走：`max((page-1)*10, len(_seen))`。
  - **實測戰果**（`--pages 4 --days 7`）：58 → 66 → 73 → **80 筆，且全數落在 7 天內**；
    改版前同一條件下第 2 頁即停，且多數舊職缺還會被客戶端日期篩選丟棄。
  - 訪客結果仍會「漂移」（同一 `start` 每次取樣可能不同），故以 `job_id` 跨頁去重累積，
    整頁皆已見即停止翻頁（避免無限迴圈）；提供 `li_at` 後為登入態，翻頁最穩定。
- **職位卡解析（`.jobs-search__results-list li` 內）**：
  - `a.base-card__full-link` → 連結 `…/jobs/view/<slug>-<id>`，取網址 slug 尾段數字作 `job_id`（標準鍵 `linkedin::<id>`）
  - `.base-search-card__title` → 職位名
  - `.base-search-card__subtitle` → 公司
  - `.job-search-card__location`（或 `.base-search-card__metadata` 第一行）→ 地點
  - `time` → 刊登日。**優先取 `datetime` 屬性**（`datetime="2026-09-07"`，絕對日期、較精確）；無該屬性才退回文字（如 `4 days ago`）
  - 訪客卡通常**不含薪資**（留空）
- **詳情頁（免登入 guest API）**：`GET /jobs-guest/jobs/api/jobPosting/<id>` 回傳公開職位頁 HTML 片段（status 200，含完整 `description`）。解析：
  - `.top-card-layout__title` → 職位名
  - `.topcard__flavor` → 公司
  - `.topcard__flavor--bullet` → 地點
  - `.description__text` / `.show-more-less-html__markup` → 描述（最長可達數千字）
  - 刊登日：詳情頂部文字抓相對時間（與列表同源）
- **語系處理**：強制 `Accept-Language: en-US`，確保刊登日為英文（`4 days ago`）便於 `days_since_posted()` 解析；同時備援中文單位（`4 天前` / `3 個月前`）解析，雙語皆可用。地點也因此為 `Hong Kong, Hong Kong SAR` 而非中文本地化。
- **站方端日期過濾（`--days` → `f_TPR`，2026-09-09 新增）**：`--days N` 會經 `base_scraper`
  的 `set_days()` 掛載點下推為 `f_TPR=r<N×86400>`（7 天 = `r604800`；24h = `r86400`；
  30 天 = `r2592000`），讓 LinkedIn **只回傳該時間窗內的職缺**，不必再抓一堆然後丟掉。
  實測：帶 `r604800` 時回傳卡片全數落於 7 天內；未帶時會混入一年以上的舊職缺
  （如 `2025-04-30`）。
  ⚠️ 此掛載點為 LinkedIn 專用：其他據點未實作 `set_days()`，`base_scraper` 會整段跳過、
  行為完全不變（已回歸驗證 OfferToday 10→8、JobMarket 25→20 無異）。
- **刊登日絕對日期解析（踩坑）**：卡片 `<time>` 的 `datetime` 是 `YYYY-MM-DD`。
  解析正則 `(\d{4})-(\d{2})-(\d{2})` 有**三個捕獲組**，`m.group(1)` 只是「年」——
  誤用會讓 `strptime("2026", "%Y-%m-%d")` 拋錯、全部職缺被誤判為逾期（實測 58 筆全滅）。
  **必須用 `m.group(0)`**（完整匹配）；且不加結尾錨點，以容忍 ISO 帶時間格式
  （`2026-09-07T12:34:56Z`）。這與 Indeed 的 `jobkey`／`jobKey` 是同一類「張冠李戴」坑。
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
  | `posted_date` | 列表 `<time datetime="YYYY-MM-DD">`（優先）／相對時間文字（備援）／詳情頂部相對時間；`days_since_posted()` 三種格式皆可解析 |
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

  - 🐢 **2026-09-09 最新狀態：已定位根因，但最終卡在「IP 層級封鎖」（非程式可解）。**
    本次修復逐步排除三層防線，過程與結論如下（每層都有實測證據）：

    | 層次 | 現象 | 處置 | 結果 |
    |---|---|---|---|
    | ① 指紋不延續 | 每次 `new_context()` → CF 當成全新訪客 | 改 `launch_persistent_context` 持久化 profile | 已修 |
    | ② **UA 與 Client Hints 版本不一致** | UA 寫 `Chrome/124`，本機實為 `Chrome/152` | Indeed **不再覆寫 UA**（改用瀏覽器原生） | ✅ **突破挑戰** |
    | ③ Indeed 全站封鎖 | 換全新 ISP 的 IP 仍封鎖；首頁／搜尋／hk／www 全擋 | 非單純 IP 層級，**待查**（見下方二次複測） | ⛔ |

    - **②是本次最關鍵的發現**：`config.DEFAULT_HEADERS` 的 UA 停留在 `Chrome/124.0.0.0`，
      但本機 Chrome 已是 152。Cloudflare 會比對 UA 與 Client Hints（`sec-ch-ua`）的真實版本，
      「嘴巴說 124、身體是 152」是極經典的機器人訊號。改用原生 UA 後，
      **同一支請求從 `Just a moment...` 變成通過挑戰、抵達 Indeed 自己的封鎖頁**。
      僅改 `indeed` 模組，`DEFAULT_HEADERS` 仍供其他來源沿用（跨站隔離）。
    - **③是 IP 層級，證據充分**：封鎖頁直接印出來源 IP；且以 `INDEED_RESET_PROFILE=1`
      清空 cookie 重來仍被擋（排除 cookie／profile 因素）。
      同時實測 **JobsDB（同樣走 CF）在同一顆 IP 上正常拿到 30 筆**
      → 證明 IP 並未全面陣亡，是 **Indeed 這一區把我們拉黑**（很可能是當日反覆嘗試累積所致）。
    - **結論與建議**：程式面已無可著力處，讓 IP 冷靜數小時至數天再試。
      `fromage=N` 仍標註為**尚未實測驗證**。

  - 🔁 **2026-09-10 複測（IP 未更換，仍封鎖）**：
    - 使用者已重開路由器，但**對外 IP 仍是同一顆 HKT 位址**（以 `ifconfig.me` 獨立驗證，
      非 Indeed 回報）。封鎖同樣存在，來源 IP 一字不差。
    - **為什麼重開路由器沒換到 IP**：本機為內網 `192.168.1.111`、閘道 `192.168.1.1`，
      對外 IP 由路由器的 WAN 持有。經查該 IP 屬 **HKT（香港電訊，AS4760）家用寬頻**
      （`proxy=false` / `hosting=false`，確為動態配發），但 HKT 常用 **sticky DHCP**——
      依 MAC 綁定且租約偏長，短時間重啟會拿回同一顆。
      ⚠️ **「重開電源」≠「重新撥號」**，必須在路由器後台執行釋放／更新 WAN，
      或等租約到期。
    - 封鎖頁中**不含任何解封時間線索**（已翻查 `retry` / `expire` / `unblock` 等關鍵字，
      僅命中 CSS），Cloudflare 從不揭露封鎖時長。經驗值為數小時至數天。
    - ✅ 好消息：新建的 `_block_state()` 表現理想，**9 秒內判讀出封鎖並立即停手**
      （舊碼會傻等 45 秒），不會因反覆重試加深黑名單。

  - 🚨 **2026-09-10 二次複測（換手機熱點、全新 IP）——推翻「IP 封鎖」結論**：
    使用者改用手機熱點，對外 IP 由 HKT 寬頻 `1.64.x.x`（AS4760）
    換成 **中國移動香港 `182.239.x.x`（AS9231）**，`mobile=true` /
    `proxy=false` / `hosting=false`（乾淨的行動網路 IP，完全另一家業者）。
    ⚠️ **仍遭一模一樣的封鎖**（`Blocked - Indeed.com`）。

    - 進一步實測，**封鎖是全站性、不分鏡像的**：

      | 測試目標 | 結果 |
      |---|---|
      | `hk.indeed.com/jobs?q=...`（搜尋頁） | ⛔ Blocked |
      | `hk.indeed.com/`（首頁） | ⛔ Blocked |
      | `www.indeed.com/jobs?q=...`（非 HK 鏡像） | ⛔ Blocked |

    - **對照組（關鍵）**：同一顆全新 IP 上，**JobsDB（同樣走 Cloudflare）正常取 30 筆**
      → 排除「新 IP 有問題」與「Cloudflare 全面封鎖」，是 Indeed 單方面所為。
    - **結論修正**：既然橫跨兩個不同 ASN（HKT 寬頻 / 中國移動行動網路）、
      且清空 profile（`INDEED_RESET_PROFILE=1`，等同全新指紋 + 全新 IP）仍被擋，
      **這已非單純的 IP 層級封鎖**。較可能是 Indeed 對自動化流量的
      指紋／行為層級封鎖，或其香港／亞洲區的全站性策略。
      ⚠️ 因此「換 IP 等待解封」不再是有效解法。
    - **仍待你確認（零請求，5 秒可驗）**：用手動 Chrome 開 `https://hk.indeed.com/`——
      - 若**手動正常** → 是「自動化被識別」，尚有機會（可試有頭模式 `INDEED_HEADLESS=0`）
      - 若**手動也被擋** → 全站性封鎖，Indeed 據點就此陣亡，建議轉為
        「標註停用」並把資源投給其他據點

  - 🔚 **2026-09-11 最終結論（真人實測）——據點對訪客而言已陣亡**：
    使用者以手動 Chrome 開啟 `https://hk.indeed.com/`，**沒有出現 Blocked 封鎖頁，
    而是被要求登入（login wall）**；使用者未登入即離開。

    - ⭐ **這兩個結果天差地遠，而且指向同一個結論**：
      自動化 → `Blocked`；真人 → **強制登入**。
      表示 Indeed 目前對香港訪客採「**強制登入**」策略——
      即便哪天 `Blocked` 解除，訪客也過不了這道登入牆。
    - 因此本據點對「訪客模式爬蟲」而言已無實用價值。
      **程式碼保留不動**（CF 若日後放寬可原地復活），但不再投入偵察資源。
    - 若要重啟本據點，唯一可行路徑是提供**已登入的 Indeed 帳號 cookie**
      （相當於另一個等級的工程，且須自行承擔帳號風險），目前不建議。
    1. 先驗 IP 是否已更換（不打 Indeed，避免吵到它）：
       ```bash
       python -c "import requests;print(requests.get('https://ifconfig.me/ip',timeout=15).text)"
       ```
       若印出的 IP 仍屬 HKT／AS4760 → 尚未更換，不必浪費請求測 Indeed。
    2. IP 確認不同後，清空 profile 重跑一次（讓它重新握手）：
       ```bash
       INDEED_RESET_PROFILE=1 python main.py --source indeed --keyword "software engineer" --pages 1 --outfile _probe_indeed_r3
       ```
    3. **若第 2 步成功拿到職缺**，立刻驗證 `fromage=N` 是否真的生效——
       ⚠️ 不可只看「筆數」或「前幾筆日期」（Indeed 預設按相關性排序，前幾筆本來就新）。
       要比的是**帶與不帶 `fromage` 的總數／日期分布**：
       ```bash
       python main.py --source indeed --keyword "software engineer" --pages 1 --outfile _ind_nofilter
       python main.py --source indeed --keyword "software engineer" --pages 1 --days 7 --outfile _ind_fromage7
       ```
       再比對兩份結果的 `posted_date` 最大值。若 `--days 7` 那批的最舊日期明顯較新
       → 站方端過濾生效，可把 README 功能矩陣中 `fromage=N` 的
       「⚠️ 尚未實測驗證」改為「✅ 已驗證」。
    4. 若第 2 步仍回 `Blocked` → 回到等待，不要再反覆嘗試。
    - ✅ **延伸風險已拆除（2026-09-10）**：`config.DEFAULT_HEADERS` 原本寫死
      `Chrome/124.0.0.0`，而 foundit / jobsdb / liepin / recruit / zhipin 都沿用同一份
      UA —— 等於五顆未爆彈共用一根引線。已改為**開機自動量測本機 Chrome 版本**
      （`config._detect_chrome_version()`，實測抓到 `152.0.7977.83`），
      從此 UA 與 Client Hints 永遠一致，不會再腐化。
      可用環境變數 `CHROME_UA_VERSION` 覆寫。實測六站回歸全數正常：
      jobsdb 30 / recruit 25 / foundit 20 / moovup 12 / efc 50 / offertoday 10。
- **真實網域**：`https://hk.indeed.com`（香港鏡像；職位搜尋 `/jobs`、單筆詳情 `/viewjob`）。
- **反爬保護（Cloudflare「Just a moment...」）**：
  - plain `requests` → **403 被擋**；必須用 **Playwright**（本爬蟲 `use_browser=True`）。
  - ⚠️ **必須用本機 Google Chrome（`channel="chrome"`），不能用內建 Chromium（2026-09-08 修復）**：
    實測內建 Chromium 已完全被 CF 擋下——頁面標題停在 `Just a moment...`，內文為
    `Additional Verification Required` + `Your Ray ID for this request is …`，
    輪詢 45 秒也不會過關（舊筆記寫「幾秒內即過關」已失效）。
    改用 `channel="chrome"` 後**立即正常**（beacon 16 張）。與 **foundit** 是同一類型的指紋坑。
    程式內已做降級：無本機 Chrome 時退回內建 Chromium 並 `logger.warning` 預告會被擋。
  - **關鍵坑（重要）**：Indeed 的 Cloudflare 在「首頁 → 搜尋頁」的跳轉上特別頑固（實測偶發 45 秒仍過不了）；
    但**直接 goto 搜尋頁**（`/jobs?q=…&l=…`）幾秒內即過關。故本爬蟲**不先做首頁預熱**，而是直接在 `search()` 跳搜尋頁並輪詢 `.job_seen_beacon` 出現（最多 ~45 秒）。
  - **持久化 profile（2026-09-09 改版）**：改用
    `launch_persistent_context(user_data_dir=.chrome_profiles/indeed, channel="chrome")`，
    並注入自刻的隱身腳本（`navigator.webdriver` 抹除、`window.chrome` 補齊等；
    本專案未裝 `playwright-stealth`，故自行注入等效最小集合）。
    profile 目錄已加進 `.gitignore`（含 `cf_clearance` cookie，不進版本庫）。
    環境變數：`INDEED_HEADLESS=0` 有頭模式暖機、`INDEED_RESET_PROFILE=1` 清空 profile
    重來、`INDEED_UA=...` 明確指定 UA（不給則用瀏覽器原生）。
  - **阻擋狀態判讀（`_block_state()`，2026-09-09 新增）**：等待卡片時不再傻等 45 秒，
    而是在 ~6 秒時判讀目前卡在哪一關並給可行動的線索：
    - `challenge`（CF managed challenge）→ warning，建議有頭模式暖機
    - `blocked`（IP 層級封鎖）→ **error 並立即停手**，不再翻頁、不再加重黑名單
    - ⚠️ 判讀必須**標題 + 內文雙重比對**：挑戰頁載入後標題會被 JS 改寫成
      `Security Check - Indeed.com`（實測），只看標題會漏判成正常頁。
  - ⚠️ **空關鍵字一律 0 筆（2026-09-08 實測）**：`q=` 為空時站方回傳
    `headerMsg: "The search Jobs in Hong Kong did not match any jobs."`、
    `originalResultCount: 0`，頁面上**一張職位卡都沒有**（`.job_seen_beacon` = 0、`[data-jk]` = 0）。
    這是**站方行為，不是爬蟲故障**；程式會明確 `logger.warning` 提醒補 `--keyword`。
    （註：HTML 中 `viewjob` 字串會出現數十次，但那是 JS 內的 token 名如 `"viewjob":"mobvjtk"`，**不是職位連結**，勿據此誤判。）
- **搜尋機制：SSR + 客戶端渲染 HTML**。網址
  `https://hk.indeed.com/jobs?q=KEYWORD&l=LOCATION&start=N`（`start` 步長 10，首頁不加 `start`）。
- **職位卡（`.job_seen_beacon`，每頁 ~16 張，表格佈局）**：
  - 標題 `a.jcs-JobTitle`（含 `data-jk` 屬性 = 職位 ID，如 `7b8620949d7f8b54`）；`job_id` = `indeed::<jk>`
  - 公司 `span[data-testid='company-name']`
  - 地點 `div[data-testid='text-location']`（如 `Remote` / `Hong Kong` / `Cyberport, Hong Kong Island`）
  - 薪資：卡片**無專屬元素**，為卡片內文文字（如「$18,000 - $30,000 a month」），以正則從 `inner_text` 抓取
- **刊登日（重要）**：列表卡可見 HTML（inner_text）雖然**不含日期**（只有 title/company/location/salary），
  Indeed 卻在**內嵌的 mosaic provider JSON**（`window.mosaic.providerData["mosaic-provider-jobcards"]`）
  中為每個職位提供日期欄位。**`list_has_date=True` → `--days` 篩選瞬時完成，無需逐張點擊
  （優化前需 ~11 分鐘，優化後 ~9 秒）。**
- **⚠️ 刊登日欄位陷阱（2026-09-08 修復，原實作為 bug）**：職位物件裡有三種日期，**不能用錯**：

  | 欄位 | 意義 | 實測值（同一頁 15 筆） |
  |------|------|------------------------|
  | `jobkey`（**全小寫 k**） | 職位 ID 的正確鍵名 | — |
  | `formattedRelativeTime` | 站方 UI 顯示的相對時間 | `"3 days ago"` / `"30+ days ago"` |
  | `createDate` | Indeed 建檔時間（毫秒戳） | 4～193 天前 |
  | `pubDate` | **雇主 feed 的原始刊登日** | ⚠️ 947～2811 天前，長期職缺會是**數年前** |

  舊實作的兩個錯誤：① 用 `"jobKey"`（大寫 K）配對——那個鍵位於 `mouseDownHandlerOption`
  追蹤物件裡，導致日期**張冠李戴**；② 直接用 `pubDate` 當刊登日——把「3 天前」的職缺報成
  **1880 天前**。修正後的策略是：**優先用 `formattedRelativeTime`**；若它只給下限
  （`"30+ days ago"`）則改用 `createDate` 折算天數；兩者都缺才退回 `pubDate`。
  修正前後對照：同一職位由 `1879 day ago` → `0 day ago`，且描述內文自帶
  `Posting Date: 2026-09-07`，交叉驗證一致。
  解析方式也從「位置掃描 9KB 視窗」改為 `JSONDecoder.raw_decode` 直接解析
  `"results":[...]` 陣列（能正確處理字串內的括號，也不再依賴位置猜測）。
- **詳情頁（僅 `--detail` 顯式要描述時才用）**：
  - ⚠️ **直連 `/viewjob?jk=<id>` 會重觸發 Cloudflare（40 秒仍被擋）**，不可行。
  - ✅ **從搜尋頁「點擊職位連結」開側面板（SPA）則不重觸發 CF**（cf_clearance 沿用），2–3 秒內載入，
    詳情 HTML 含 `datePublished` 毫秒戳與 `age:"X days ago"`。故 `get_detail()` 實作為「在當前搜尋頁點擊對應 `a[data-jk]`」而非直連 viewjob。
  - **點擊改用 JS `element.click()` 直接派發事件**（繞過「面板遮住卡片 → Playwright 判定 `element is not visible`」的坑），
    單張詳情 ~0.4–0.9 秒。
  - ⚠️ **兩個會讓 `--detail` 慢到爆的坑（2026-09-08 實測修復）**：
    1. **卡片出現後立刻點擊有機會點不開**（SPA 事件尚未綁定）→ 現在 `search()` 收尾多等 1.5 秒，
       且 `_open_card()` 內建「失敗重試一次」。
    2. **面板開了但描述抓到空字串時，舊碼會掉進「重新 goto 整頁」的回退**（每次輪詢 45 秒）
       ——16 筆的 `--detail` 曾被拖到 **8 分鐘**。現在改為「原地再讀一次」就回傳，
       不再動輒整頁重載；回退輪詢也從 15×3s 縮到 10×2s。
  - **描述抽取**：優先用 DOM `#jobDescriptionText` 的 `inner_text()`；純 HTML 回退則做
    `<div>` **巢狀配對**後去標籤。⚠️ 不能用 `(.*?)</div>`——描述內含巢狀 `div`/`ul`，
    非貪婪只會抓到第一層（實測整段描述只剩 `Client Description` 17 字）。
    修正後單筆描述 934 / 2034 / 2476 字。
  - 日期解析：優先用 `search()` 時建立的 `{jk: 相對時間}` 對照表（最準）；
    獨立呼叫時才從 HTML 抓，且**必須優先匹配 `Posted`／`Date Posted`**
    ——「Employer Active 1 day ago」是雇主活躍度，會把 30+ 天的職缺誤報成 1 天內。
    `days_since_posted()` 解析「N day(s) ago」。
  - 🐢 **熔斷機制**：連續 2 筆點不開面板就停止後續抓取（保留刊登日、只丟描述），
    不再逐筆整頁重載。修復前後：16 筆 `--detail` 由 **9 分鐘 / 剩 1 筆** → 約 **1 分鐘 / 描述完整**。
  - 每個 `get_detail()` 都會 log 耗時，方便日後再定位效能瓶頸。
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

## 🧭 技術筆記（Recruit 逆向要點）

- **真實網域**：`https://www.recruit.com.hk`（首頁 `/`，結果頁 `jobseeker/JobSearchResult.aspx`，詳情 `/job-detail/<公司slug>/<職稱slug>/<jobOrder>`，另有 `/jobseeker/JobDetail.aspx?jobOrder=<ID>` 相容網址）。
- **技術棧**：**ASP.NET WebForms + Vue 3 混合站**。無 Cloudflare、無 CAPTCHA；robots 寬鬆（僅禁會員頁）。
- **搜尋機制（本站最大的坑）**：畫面上的地區/職能 checkbox 是 Vue `v-model` 綁定，**勾了也不會被送出**；真正 POST 出去的是三條 hidden 欄位：
  - `UclRespJobSearchFilterControl$keywordTxt`（關鍵字，text）
  - `UclRespJobSearchFilterControl$locationSearchHidden`（地區，逗號分隔 ID）
  - `UclRespJobSearchFilterControl$jobCatSearchHidden`（職能大類，逗號分隔 ID）
  - `UclRespJobSearchFilterControl$jobFuncSearchHidden`（職能細類；**必須搭配所屬 jobCat 大類才生效**，單送會被站方忽略）
  - 實測：只勾 checkbox 總數不變；直接以 JS 填 hidden 值 + 派發 input/change 事件才生效（engineer 全站 820 筆 → 元朗 15 筆、資訊科技大類 204 筆、元朗+資訊科技 1 筆）。
- **搜尋鈕在 DOM 中不可見**：`#UclRespJobSearchFilterControl_searchBtn` 被 CSS 藏住，Playwright 的 `.click()` 會等 30 秒噴 `element is not visible`；改用 JS `el.click()` 直接触發（3–5 秒完成搜尋）。
- **翻頁只能在真瀏覽器內做**：分頁是 `__doPostBack('pagerBottom$…', '')`。實測用 `requests` 送 `__EVENTTARGET` 一律無效（伺服器重跑搜尋回第 1 頁，甚至回首頁）；在 Playwright 裡執行 `__doPostBack()` 完全正常。故本站 `use_browser=True`。
  - 每頁 25 筆；`input[name=totalCnt]` 為結果總數。
  - 翻頁用「Next」鈕（`pagerBottom$ctl02$ctl00`）逐頁前進最穩（頁碼鈕的 name 會隨頁碼位移）。
  - 翻頁前先檢查 `a.next-page` 是否已停用，避免末頁乾等 30 秒逾時。
- **排序**：結果頁 `select[name=sortByDDL]`（`POST_DATE` / `SALARY_FROM` / `WORK_EXP_FROM` / `EDU_LEVEL_ID` / `RELEVANCE_PRIORITY`），改值後派發 change 事件。
- **職位卡（`tr.JobGrid`，每頁 25 張）**：`tr` 的 `id` 即 jobOrder（job_id = `recruit::<jobOrder>`）；職稱/網址 `a.title`、公司 `a.company`、薪資 `td.salary-col`、學歷 `td.edu-col`、年資 `td.exp-col`、**刊登日 `td.post-date-col`（`YYYY-MM-DD`）**。列表卡另有隱藏 `input[id$="_expiryDate"]`（截止日）。
  - 學歷 / 年資在列表層無專屬 JobRecord 欄位，合併寫入 `requirements`（`學歷：…；年資：…`）以免資訊遺失。
  - ⚠️ **列表無地區欄**（2026-09-08 實測確認：`tr.JobGrid` 只有 `saved-job-col`／`title-company-col`／`edu-col`／`salary-col`／`exp-col`／`post-date-col`／`relevance-col`，**確實沒有地區**）。三種填法，依成本由低到高：
    1. **零請求**：`--district` 只篩**單一地區**時，站方保證結果屬於該區 → 直接回填該區英文名（如 `Yuen Long`）。多區聯集時無法判斷各筆歸屬，**寧可留空不猜**。
    2. **`--fill-location`（推薦）**：走列表卡片 `onclick` 背後的 AJAX 端點
       `/jobseeker/JobDetail.aspx?jobOrder=<id>&ajax=Y`（見 `N_common.js` 的 `getAjaxJobDetailUrl`）→
       回傳約 **35KB**、含 JSON-LD `address`，**純 `requests` 即可**（不必開瀏覽器）。
       實測 25 筆全數可補（Kowloon Bay / Tseung Kwan O / Mong Kok…）。
       ⚠️ 每筆多 1 支請求（25 筆/頁 → 25 支），故**預設關閉**，內建節流。
    3. **`--detail`**：抓完整詳情頁 JSON-LD（最重，但同時補描述／行業等全部欄位）。
  - ⚠️ 站方 `address` 三欄**可能是 `N/A` 假值**（實測 25 筆中 2 筆）→ 已過濾
    （`n/a`、`--`、`-`、`none`、`null` 等），全為假值時 `location` 留空而非寫入 `N/A`。
- **詳情頁**：內含 **JSON-LD `JobPosting` 結構化資料**（地區 / 行業 / 僱傭類型 / 薪資區間 / 完整描述 / `datePosted`）。注意站方 JSON-LD 內含未跳脫的控制字元，需先清 `\x00–\x1f` 再 `json.loads`。地區取 `jobLocation.address` 的 streetAddress / addressLocality / addressRegion 三欄**去重後**合併（三欄常重複如 New Territories / Hong Kong / Hong Kong）。
  - 詳情用普通 `requests` 即可（無反爬），~0.2 秒/筆。
- **`--days` 行為**：`list_has_date=True`，列表卡已含刊登日（`YYYY-MM-DD`），由列表直接過濾，**不必抓詳情（瞬時）**；`days_since_posted()` 支援 `%Y-%m-%d` 與 `%d/%m/%Y` 兩種格式。
- **地區篩選體系**：Recruit 專屬數字 ID（逗號分隔可多選），與其他五站完全獨立，不可混用（見下方「🗺️ 按地區篩選（Recruit）」）。
- **不支援項**：`--industry`（該站無行業篩選維度，傳入 `logger.warning` 後忽略）。均不影響其他據點。
- **各欄位資料來源總表（Recruit → JobRecord）**：

  | JobRecord 欄位 | 來源（Recruit 選擇器 / 邏輯） |
  |----------------|------------------------------|
  | `job_id` | `recruit::<jobOrder>`（取自 `tr.JobGrid` 的 `id`） |
  | `source` | 常數 `"recruit"` |
  | `title` | `a.title` |
  | `company` | `a.company` |
  | `location` | 列表無此欄，留空；`--detail` 時取 JSON-LD `jobLocation.address`（去重合併） |
  | `salary` | 列表 `td.salary-col`；`--detail` 時取 JSON-LD `baseSalary`（min–max + 單位） |
  | `job_type` | `--detail` 時取 JSON-LD `employmentType`（FULL_TIME→全職等映射） |
  | `industry` | `--detail` 時取 JSON-LD `industry` |
  | `description` | `--detail` 時取 JSON-LD `description`（清 HTML 標籤） |
  | `requirements` | 列表層合併 `td.edu-col` + `td.exp-col`；`--detail` 時取 JSON-LD `occupationalCategory` |
  | `url` | `a.title` 的 href（urljoin 補絕對網址） |
  | `posted_date` | 列表 `td.post-date-col`（`YYYY-MM-DD`）；`--detail` 時 JSON-LD `datePosted` 亦可 |
  | `scraped_at` | 抓取當下 `datetime.now()` |

## 🗺️ 按地區篩選（Recruit）

- Recruit 的地區篩選走 **hidden 欄位 `locationSearchHidden`（逗號分隔數字 ID）**，與 Moovup 的 shortCode、勞工處的數字 ID、JobsDB 的 slug、LinkedIn / Indeed 的自由文字**完全獨立**，不可跨站混用。
- 本程式內建 `scrapers/recruit_districts.json`：**94 個地區**（英文原名 + 45 個中文別名）。中英文皆可輸入：
  - `python main.py --source recruit --keyword "engineer" --district 元朗`（中文 → ID `69045`）
  - `python main.py --source recruit --keyword "engineer" --district "Yuen Long"`（英文原名，效果相同）
  - `python main.py --source recruit --keyword "engineer" --district "元朗,屯門"`（逗號分隔多區）
- 未知地區會 `logger.warning` 後忽略，不會報錯。
- ⚠️ **列表本身沒有地區欄**（與 JobMarket 不同——JobMarket 有批次 API 可補，Recruit 沒有）。因此 `location` 的來源依使用方式而定：

  | 用法 | location 結果 | 額外請求 |
  |------|--------------|---------|
  | `--district 元朗`（**單一地區**） | 直接回填 `Yuen Long`（站方篩選保證） | **0** |
  | `--district "元朗,屯門"`（多區） | 留空（無法判斷各筆歸屬，不猜） | 0 |
  | `--fill-location` | AJAX 端點逐筆補真實地區 | 每筆 1 支（25 筆/頁 → 25 支，含節流） |
  | `--detail` | 完整詳情 JSON-LD（連描述／行業一起補） | 每筆 1 支（完整頁，較重） |

  範例：`python main.py --source recruit --keyword engineer --fill-location --pages 1`
  （實測 25 筆全數補上：Kowloon Bay / Tseung Kwan O / Mong Kok / Tai Po District…；站方缺值時留空，不寫 `N/A`）
- ⚠️ `--fill-location` 目前**僅 recruit 支援**；傳給其他來源會 `logger.warning` 後忽略（那些站列表已含地區），不會中斷。
- 職能篩選（`--category`）同理由 `recruit_categories.json`（34 大類 + 290 細類，中英雙語）解析成 `jobCatSearchHidden` / `jobFuncSearchHidden`；給細類時會**自動補上所屬大類**（站方要求 jobFunc 必須搭配 jobCat 才生效），如 `--category "DBA"` → 細類 56121 + 大類「資訊科技」26000。

## 🧭 技術筆記（JobMarket 逆向要點）

- **真實網域**：`https://www.jobmarket.com.hk`（搜尋殼頁 `/Jobs/search?...`；職位列表端點 `/Job/JobList`；詳情 `/Job/CurrentJob?Jobid=<id>`）。
- **技術棧**：J2EE / JSP。**無 Cloudflare 挑戰**（頁面只載入 CF 腳本，內容正常回）、無 CAPTCHA；robots 極寬鬆（僅禁 `/UpFiles/`）。**全程普通 `requests` 即可，`use_browser=False`**。
- **搜尋架構（本站關鍵）**：`/Jobs/search?...` 殼頁只是一層 iframe 容器，真正的職位列表由 **iframe 內的 `/Job/JobList` 端點伺服器渲染**。爬蟲直接打該端點：
  `/Job/JobList?Searchtext=K&Page=N&AreaID=..&AreaLocationID=..&JobFunctionID=..&SubJobFunctionID=..&JobIndustryID=..`
  - ⚠️ **關鍵字參數名是 `Searchtext`，不是 `keyword`**。站方殼頁 iframe 誤用 `keyword=engineer`，該參數被列表端點**無視**、回全站 ~3594 筆——這是站方殼頁與列表端點參數名不一致的坑（由提交按鈕的 JS 得知真正參數名）。
  - 每頁 20 筆；`Page=N` 翻頁（實測 1/2/3 頁 job id 全無重複）。
- **搜尋參數全表**（從殼頁提交按鈕的 JS 抽出）：`Searchtext`（關鍵字）、`CompanyID`、`JobFunctionID` / `SubJobFunctionID`（逗號多選；**細類可直接單送**，與 Recruit 不同）、`JobIndustryID`、`QualificationID`、`ManagerialLevelID`、`AreaID`（5 大區）/ `AreaLocationID`（75 子區）、`JobType`、`SalaryFrom` / `SalaryTo` / `SalaryTypeID`、`WorkExperienceID_From/_To`、`IsGraduate=1`、`IsDesc=1`（描述內搜尋）。
- **職位卡（`div.job-list-con`，每頁 20 張）**：職稱 `h3`；公司 `p.company-name > a[href="/Job/?CompanyID=..."]`；**刊登日 `p.post-date`（`04 Sep 2026`）**；job id 在 `a.saved-a` 的 `save-id` 屬性（`li[data-jobid]` 同值）；`p.company-addr` 在原始 HTML 中是 "loading"。
  - ⚠️ **列表卡沒有薪資欄**（薪資常寫在職稱或描述內）。
- **地區補齊：站方批次 API（重要）**：列表載入後站方 JS 呼叫 **`GET /API/Web/GetJobDetail/<id1,id2,...>`**（JSON），回傳每筆的 `JobLocation` / `JobType` / `JobIndustry` / `Qualification` / `Benefit` / `JobDetails` / `JobSummary`。本爬蟲在列表階段即呼叫同一 API（**每頁 1 次**）補齊 location / job_type / industry / 學歷 / 福利——**`location` 預設就有值，不必 `--detail`**。
- **詳情頁（僅 `--detail` 顯式要完整描述時才用）**：`GET /Job/CurrentJob?Jobid=<id>`（普通 requests）。`​.job-post-content` 完整描述、`.job-par` 行業/職能文字（正則抽 `Industry X Job Function Y`）、`.job-list-detail-date` 內含 ref 編號與 `05-Sep-2026` 刊登日、`.benefits` 福利。
- **`--days` 行為**：`list_has_date=True`，列表卡已含刊登日（`%d %b %Y`），由列表直接過濾（瞬時）；`days_since_posted()` 另支援詳情層的 `%d-%b-%Y`。
- **排序**：站方 UI 的 `Order` 參數實測無有效效果（`Order=PostDate` 甚至回 0 筆），而列表預設即刊登日新→舊（job id 遞減）→ **`--sort` 一律警告後忽略**。
- **地區篩選體系**：JobMarket 專屬雙參數（`AreaID` 5 大區 + `AreaLocationID` 75 子區），與其他六站完全獨立，不可混用（見下方「🗺️ 按地區篩選（JobMarket）」）。
- **各欄位資料來源總表（JobMarket → JobRecord）**：

  | JobRecord 欄位 | 來源（JobMarket 選擇器 / 邏輯） |
  |----------------|------------------------------|
  | `job_id` | `jobmarket::<save-id>`（取自 `a.saved-a` 的 `save-id`；`li[data-jobid]` 同值） |
  | `source` | 常數 `"jobmarket"` |
  | `title` | 列表 `div.job-list-con h3` |
  | `company` | 列表 `p.company-name > a` |
  | `location` | **批次 API `JobLocation` 陣列**（` / ` 串接；列表階段即有） |
  | `salary` | 列表無薪資欄，留空（薪資常在職稱/描述文字內） |
  | `job_type` | 批次 API `JobType` 陣列 |
  | `industry` | 批次 API `JobIndustry`；`--detail` 時詳情 `.job-par` 正則亦可 |
  | `description` | `--detail` 時詳情 `.job-post-content` |
  | `requirements` | 批次 API `Qualification`（學歷）+ `Benefit`（福利）+ `JobSummary`/`JobDetails` 合併；`--detail` 時 `.benefits` 亦可 |
  | `url` | `https://www.jobmarket.com.hk/Job/CurrentJob?Jobid=<id>` |
  | `posted_date` | 列表 `p.post-date`（`04 Sep 2026`）；`--detail` 時 `05-Sep-2026` 亦可 |
  | `scraped_at` | 抓取當下 `datetime.now()` |

## 🗺️ 按地區篩選（JobMarket）

- JobMarket 的地區篩選走 **雙參數體系**：`AreaID`（5 大區：香港島 / 九龍 / 新界 / 離島 / 其他）與 `AreaLocationID`（75 子區，如元朗=68、屯門=67、沙田=59），可逗號多選。與 Moovup 的 shortCode、勞工處數字 ID、JobsDB slug、Recruit 數字 ID、LinkedIn / Indeed 自由文字**完全獨立**，不可跨站混用。
- 本程式內建 `scrapers/jobmarket_districts.json`：**80 項**（5 AreaID + 75 AreaLocationID，中英雙語）。中英文皆可輸入：
  - `python main.py --source jobmarket --keyword "engineer" --district 元朗`（中文 → AreaLocationID=68）
  - `python main.py --source jobmarket --keyword "engineer" --district "Yuen Long"`（英文，效果相同）
  - `python main.py --source jobmarket --keyword "engineer" --district 新界`（大區 → AreaID=3，涵蓋全部新界子區）
  - `python main.py --source jobmarket --district "元朗,屯門"`（逗號多區）
- 未知地區 `logger.warning` 後忽略，不報錯。
- 職能（`--category`）由 `jobmarket_categories.json`（28 大類 + 195 細類）解析成 `JobFunctionID` / `SubJobFunctionID`；行業（`--industry`）由 `jobmarket_industries.json`（30 楘）解析成 `JobIndustryID`。**細類可直接單送，無需搭配大類**（與 Recruit 不同）。

## 🧭 技術筆記（foundit 逆向要點）

- **品牌沿革**：`monster.com.hk` **301 → `www.foundit.hk`**（Monster 亞太區 2022 年重整品牌為 foundit）——模組命名 `foundit`，README 註明「原 Monster HK」。
- **指紋 WAF（本站最關鍵）**：`/search/*` 路徑對 Python `requests` 與 **Playwright 內建 Chromium headless** 一律 `403 Access Denied`（302 bytes）；但 **`chromium.launch(channel="chrome")`（本機 Google Chrome 指紋）headless 可過**（200 / 126KB 起）。職位詳情 `/job/*`、首頁 `/`、`/xmlsitemap/*` **不在封鎖範圍**，普通 requests 直達。
- **站方搜尋 API 已故障**：瀏覽器錄到前端打 `GET /home/api/searchResultsPage?start=0&limit=20&q=...`，但站方自己（真瀏覽器內）也收 `404 {"error":"Something went wrong..."}`——站方 server-side 故障，故 `/search/jobs?q=` 頁面顯示「We couldn't load these results」。**關鍵字搜尋不能走 API**。
- **作戰路線：SEO 瀏覽頁（伺服器端渲染）**：`/search/<關鍵字slug>-jobs[-in-<地區slug>][-<頁碼>]`
  - Chrome 指紋下這些頁面 **SSR 完整職位卡**（20 張/頁，不依賴壞掉的 API）；`engineer-jobs` 實測標題「2989 Engineer Jobs」。
  - **翻頁是路徑後綴**：`engineer-jobs-2`（Page 2）✅；`?page=2` 無效（標題不變）。
  - **關鍵字 + 地區組合**：`engineer-jobs-in-hong-kong-2` ✅（順序：skill → `-jobs` → `-in-<loc>` → `-<頁碼>`；頁碼放中間如 `engineer-jobs-2-in-hong-kong` 會被解析成亂碼頁）。
  - **空關鍵字**：走純地區瀏覽頁 `/search/jobs-in-<loc>`（預設 `hong-kong`）。
- **職位卡（`div[class*="rounded-2xl"][class*="p-4"]` 內含 `h2.jobCardTitle`，20 張/頁）**：職稱 `h2.jobCardTitle`；連結 `a[href*="/job/"]`（**job id = 網址尾碼數字**，如 `-65597666`）；公司 `span.jobCardCompany`；地區 `div.jobCardLocation`；技能列表；徽章（`Early Applicant` 等）；**刊登日為底部「Posted 13 hours ago」相對日期**（`div.flex.w-fit`）。
- **詳情頁（普通 requests 直達，~0.5 秒/筆）**：`/job/<slug>-<id>` 內含 **ld+json `JobPosting`**：`title` / `datePosted`（**格式 `04-09-2026` = dd-mm-yyyy**）/ `jobLocation.address` / `hiringOrganization.name` / `employmentType` / `baseSalary`（可能缺）/ `description`（HTML 片段）。
- **`--days` 行為**：`list_has_date=True`，列表卡相對日期由 `days_since_posted()` 解析（hours→0、days→N、weeks→N×7、months→N×30、years→N×365），由列表直接過濾，瞬時。
- **保底資料源（sitemap）**：`/xmlsitemap/sitemap-index.xml` → **`active-jobs-sitemap0.xml.gz`（全站 8,799 職位 + lastmod）**；另有 `todays-jobs-sitemap.xml`（130 筆/日）與各維度 SEO 頁索引。robots 對一般 UA 僅禁 seeker 後台與部分端點。
- **各欄位資料來源總表（foundit → JobRecord）**：

  | JobRecord 欄位 | 來源（foundit 選擇器 / 邏輯） |
  |----------------|------------------------------|
  | `job_id` | `foundit::<網址尾碼數字>`（如 `foundit::65597666`） |
  | `source` | 常數 `"foundit"` |
  | `title` | 列表 `h2.jobCardTitle`；`--detail` 時 ld+json `title` |
  | `company` | 列表 `span.jobCardCompany`；`--detail` 時 ld+json `hiringOrganization.name` |
  | `location` | 列表 `div.jobCardLocation`；`--detail` 時 ld+json 地址去重段 |
  | `salary` | `--detail` 時 ld+json `baseSalary`（列表卡無薪資欄） |
  | `job_type` | `--detail` 時 ld+json `employmentType` |
  | `industry` | 該站無此維度，留空 |
  | `description` | `--detail` 時 ld+json `description` 純文字化 |
  | `url` | 列表 `a[href*="/job/"]`（絕對化） |
  | `posted_date` | 列表相對日期（如 `13 hours ago`）；`--detail` 時 `YYYY-MM-DD` |
  | `scraped_at` | 抓取當下 `datetime.now()` |

## 🗺️ 按地區篩選（foundit）

- foundit 的地區是 **46 個 SEO 瀏覽頁 slug**（來源 `jobs-by-locations-sitemap`），寫進網址路徑（`-in-<slug>`），與 Moovup 的 shortCode、勞工處數字 ID、JobsDB slug、Recruit 數字 ID、JobMarket 雙參數、LinkedIn / Indeed 自由文字**完全獨立**，不可跨站混用。
- 本程式內建 `scrapers/foundit_locations.json`：**46 項**（name + 中文別名）。中英文皆可輸入：
  - `python main.py --source foundit --keyword "engineer" --district kowloon`
  - `python main.py --source foundit --keyword "engineer" --district 九龍`（別名 → `kowloon`）
  - `python main.py --source foundit --keyword "" --district 香港`（空關鍵字 = 純地區瀏覽頁）
- ⚠️ **粒度是站方瀏覽頁級**：香港只有 `hong-kong` / `kowloon` / `admiralty-kranji` / `gloucester-road` / `science-park` / `remote` 等少數項，**無元朗 / 屯門等細區**（該站未提供對應瀏覽頁）；另含台灣 / 新加坡 / 曼谷等亞洲地區（該站職源跨區）。
- 未知地區 `logger.warning` 後忽略，不報錯。

## 🧭 技術筆記（eFinancialCareers 逆向要點）

- **真實網域**：香港站 `https://www.efinancialcareers.hk`（`/jobs-hong-kong`、`/search-jobs/hong-kong` 等**常見路徑皆 404**——路徑規則與一般求職站不同）。職位詳情 `/jobs-<City>-<Region>-<標題>.id<數字>`。
- **robots 線索**：`Disallow: /v1` 暗示版本化 API 一族 → 前端實際使用 **`https://job-search-ui.efinancialcareers.com/v3/efc/jobs/search`**。
- **技術棧**：Angular SPA（`<efc-job-search-results>`）+ JSON API；**API 普通 `requests` 直達**（`use_browser=False`）。站方 Angular transfer-state 亦把首頁回應內嵌在 HTML 裡（雙保險）。
- **搜尋參數（實測）**：`q`（關鍵字，**可空**＝純瀏覽）、`location`（自由文字地名，**40km 半徑模糊地理搜尋**）、`countryCode2=HK`、`radius`/`radiusUnit`、`page`、`pageSize`（站方 15；**實測 50 / 100 都接受**，本程式用 50）、`facets`（原樣保留站方清單）、`sortBy`（**僅 `relevance` 有效**，其他值被靜默忽略）。
- **回應結構**：`data[]`（每筆 `jobId` / `title` / `detailsPageUrl` / `jobLocation{city,state,country}` / `postedDate`（**ISO 時間戳**） / `salary` / `minSalary`/`maxSalary` / `companyName` / `employmentType` / `positionType` / `sectors[]` / `summary` / `description`）、`meta.totalResults` / `pageCount`。
- **地區過濾實測（重要限制）**：`location=Hong Kong` → 578 筆（engineer）✅、`Hong Kong Island` ✅、`Kowloon` ✅；但 **細分區（`Yuen Long` / `Sha Tin` / `Tsuen Wan`…）全部回 0 筆**——站方地區索引只到大區級 → `efc_geo.json` 只收錄 3 大區。
- **詳情頁**：`requests` GET 詳情網址 → **ld+json `JobPosting`**（`description` 完整描述 / `baseSalary{value{minValue,maxValue,currency}}` / `skills` / `datePosted` / `validThrough`）。⚠️ ld+json 的 `identifier` 是**另一套 API hash id**（如 `oPTJ3NGIwowU`），**job_id 以詳情網址的 `.idNNNNN` 為準**（= API `jobId`，與列表一致）。
- **`--days` 行為**：`list_has_date=True`（API `postedDate` ISO 時間戳），由列表直接過濾，瞬時。
- **各欄位資料來源總表（eFC → JobRecord）**：

  | JobRecord 欄位 | 來源（eFC API / 選擇器） |
  |----------------|------------------------------|
  | `job_id` | `efc::<jobId>`（API 數字 id；詳情自網址 `.idNNNNN` 還原同值） |
  | `source` | 常數 `"efc"` |
  | `title` | API `title`；`--detail` 時 ld+json `title` |
  | `company` | API `companyName`（fallback `clientBrandName`）；詳情 `hiringOrganization.name` |
  | `location` | API `jobLocation.displayName`（fallback city/country 去重） |
  | `salary` | API `salary` 文字或 min/max 格式化；`--detail` 時 ld+json `baseSalary` |
  | `job_type` | API `employmentType` / `positionType` 合併 |
  | `industry` | API `sectors[]`（`INFORMATION_TECHNOLOGY/ENGINEERING` → `Information Technology/Engineering`） |
  | `description` | `--detail` 時 ld+json `description` 純文字化（API 的 `summary` 過短，不填） |
  | `requirements` | `--detail` 時 ld+json `skills` |
  | `url` | API `detailsPageUrl`（絕對化至 `www.efinancialcareers.hk`） |
  | `posted_date` | API `postedDate`（ISO）取 `[:10]` |
  | `scraped_at` | 抓取當下 `datetime.now()` |

## 🗺️ 按地區篩選（eFinancialCareers）

- eFC 的地區走 API **`location` 自由文字參數**（40km 半徑模糊地理搜尋），但站方地區索引**僅支援大區級**，與 foundit 的 46 slug、JobMarket 的 80 項等**完全獨立**，不可跨站混用。
- 本程式內建 `scrapers/efc_geo.json`：**3 大區**（中英文皆可輸入）：
  - `python main.py --source efc --keyword "analyst" --district "Hong Kong"`（全港）
  - `python main.py --source efc --keyword "analyst" --district 九龍`（→ `Kowloon`）
  - `python main.py --source efc --keyword "analyst" --district 港島`（→ `Hong Kong Island`）
- ⚠️ 細分區（元朗 / 沙田 / 荃灣等）**站方回 0 筆**，未收錄——傳入未收錄名稱會 `logger.warning` 後忽略，不報錯。

---

## 🧭 技術筆記（獵聘 liepin 逆向要點 — 2026-09-11 重做為香港據點）

> **2026-09-11 重大更新**：原 Wave 5 版本判定「香港覆蓋未證實、多數回 0 筆」。本次重新偵察後證實
> **獵聘有完整的香港職缺庫**（站方回報約 800 筆，含真實港區），並找出正確的過濾方式 → 升級為可用據點。

- ⚠️ **robots 狀態（如實揭露）**：`www.liepin.com/robots.txt` 明文 `Disallow: /*?*`
  （所有帶查詢串的路徑禁抓），本模組的搜尋網址帶查詢串 → **屬禁區**，模組保留
  `_ROBOTS_RESTRICTED` 標記與實例化警告。
  但實際職缺資料由**另一台主機** `api-c.liepin.com` 供應，而該主機
  **沒有 robots.txt（HTTP 404）** — 按 RFC 9309，沒有 robots.txt 即表示該主機
  未設任何限制。**請自行評估合規風險。**

- ✅ **香港覆蓋（已證實）**：城市字典 `320 = 香港`（另有 `330` 澳門、`340` 台灣；
  `410` = 全国「不過濾」）。實測 `?city=320&dq=320` 回傳 42 張卡、**40 張在香港**，
  含真實港區：湾仔区 / 油尖旺区 / 观塘区 / 沙田区 / 中西区 / 西贡区 / 北区 /
  离岛区 / 深水埗区 / 元朗区。站方 `pagination.totalCounts` ≈ 800。
  ⚠️ 舊版記載的 `city=900` 是**錯誤的**，正確值為 **320**（本次修正）。

- ⭐⭐ **最關鍵的陷阱：`city` 與 `dq` 必須同時給**
  只送 `city=320` 時，前端仍把 `dq` 填成 `410`（全国），結果**完全沒過濾**。
  實測證據：`city=320`（香港）與 `city=050020`（廣州）回傳**一模一樣**的結果
  （皆 42 張、`totalCounts` 皆 807、地區分布皆以上海為主）。
  → **必須 `city=320&dq=320` 才會生效**（生效後 `totalCounts` 變 800、地區轉為香港）。

- **資料機制**：搜尋頁 `/zhaopin/?...` 是空殼，資料由站方 JS POST
  `api-c.liepin.com/api/com.liepin.searchfront4c.pc-search-job`，
  payload 結構為 `data.mainSearchPcConditionForm`：
  `city` / `dq` / `key` / `pubTime` / `currentPage` / `pageSize`（40）/ `industry` / `salaryCode` / `eduLevel` …
  - ⛔ **直接 requests 呼叫該 API 一律失敗**：`flag=0, code=-1400「出错了（400）」`。
  - ⛔ **瀏覽器內 `fetch()` 呼叫也失敗**（同一個錯誤）——缺 secscan 前端令牌。
  - ✅ **唯一可行路徑**：讓**頁面自己的 JS** 發出請求，我們只監聽回應。
  - ✅ 網址參數會被前端正確讀進 payload（實測 `key` / `city` / `dq` 皆生效），
    故**直接用網址篩選即可，不必改寫請求**（Playwright `route` 改寫亦實測無效）。

- **欄位來源**（`jobCardList[].job` / `.comp`）：
  | 欄位 | 來源 |
  |---|---|
  | `job_id` | `job.jobId`（`JobRecord.make_id("liepin", jobId)`） |
  | `title` | `job.title` |
  | `company` | `comp.compName` |
  | `location` | `job.dq`（如 `香港-湾仔区`） |
  | `salary` | `job.salary`（如 `25-35k·24薪`） |
  | `url` | `job.link`（`https://www.liepin.com/job/19<id>.shtml`） |
  | `posted_date` | `job.refreshTime`（`YYYYMMDDHHMMSS`）→ 轉 `YYYY-MM-DD` |
  | `description` | `requireWorkYears` + `requireEduLevel` 合併 |
  | `requirements` | `job.labels` 合併 |

- ⚠️ `refreshTime` 是**刷新時間，不是刊登日**（站方未提供刊登日欄位）。
  `--days` 以此**近似**，實測 40 筆中：`--days 1` → 6 筆、`3` → 22、`7` → 33、`14` → 38。
  客戶端篩選（`list_has_date=True`），不抓詳情。

- 🐢 **反爬：IP 驗證碼門檻約 6–7 支請求**
  2026-09-11 實測：連續第 6–7 支請求觸發 `safe.liepin.com` IP 驗證碼，
  本機 Chrome 指紋亦無法避免。對策：請求間隔由 5s 拉到 **8s**、
  建議 `--pages 1～2` 為宜；命中驗證碼時模組**警告後回 0 筆並停止翻頁**（不硬闖）。

- 🩺 **2026-09-14 聽診：IP 級驗證碼，冷卻 38 小時仍未解除**（⚠️ 重要）
  9/11 10:29 產出 40 筆後，本輪於 9/14 00:30 再試：
  - `--district 元朗 --pages 1` → **0 筆**，但日誌只印「未攔截到搜尋 API 回應」，看不出原因。
  - **立即停手**，改用聽診器 `python tools/_probe_liepin.py`（單次導航，錄下所有 api 請求／
    最終 URL／標題／頁面卡片數）查明真相：
    - 頁面 5 秒內被導向 `https://safe.liepin.com/page/liepin/captchaPage_ip_PC?euuid=...`
    - `title = '安全中心-验证码'`，內文「猎聘安全中心发现您的帐号或IP可能存在异常」
    - 攔截到的只有兩支：安全中心的 `apm.setting` 與
      `api-security-liepin.liepin.com/…/intercept.unlogin.ip-captcha-page-init`
  - ⭐ **確證為 IP 級封鎖**：`euuid` 是 base64，解開為
    `flag10001|ip_ua:1.64.x.x:Mozilla/5...`（`flag10001` + `ip_ua` 帶本機公網 IP），
    鎖的正是 HKT 家用寬頻那顆（此時手機熱點已斷、流量回到有線）。
  - ⚠️ **間隔 38 小時未自動解除** → 獵聘的 IP 冷卻期可能以「天」計，
    **切勿密集重試**（重試只會延長封鎖，且我們這輪 2 支就讓它從「還能開頁」變成「直接跳驗證碼」）。
  - ✅ 對策：遇到 0 筆時先跑 `python tools/_probe_liepin.py` 聽診，
    區分「驗證碼（等冷卻／換 IP）」與「站方改版（要改程式）」——兩種病藥完全不同。

- **地區篩選**：站方只到城市層級（香港 = 320），**無分區碼**；
  分區名出現在 `dq` 字串（如「香港-观塘区」）→ `--district` 以客戶端字串比對
  （字典見 `scrapers/liepin_areas.json`，支援簡／繁／英，如「观塘」「觀塘」「Kwun Tong」）。
  ⚠️ 分區別名須**同時含簡體與繁體短名**——2026-09-11 踩過：只列繁體「觀塘」時，
  打簡體「观塘」反而配對失敗（程式已另加「区/區」後綴正規化雙保險）。

- **不支援項**：`--category` / `--industry` / `--sort`（無對應字典）、
  `--detail`（詳情頁受保護、風險高）→ 全部 `logger.warning` 後忽略。
  ⚠️ **分頁（`currentPage`）仍待端到端驗證**——2026-09-14 因站方 IP 驗證碼未能實測；
  `--pages > 1` 若回空，先跑 `tools/_probe_liepin.py` 確認是否為驗證碼，非程式故障。

- ✅ **離線驗證（2026-09-14，零請求，拿 9/11 存檔 40 筆回歸）**：
  - **地區篩選全綠**：元朗 1 / 观塘 6 / 湾仔区 11 / 油尖旺 7 / 沙田 4 / 中西区 2 / 离岛 1；
    簡繁後綴四種寫法「观塘／觀塘／观塘区／觀塘區」**皆命中 6 筆**（舊 bug 已根治）；
    英文 `Kwun Tong` → 6 筆、`Yuen Long` → 1 筆；未知值（如「火星」）僅警告並回退全香港 40 筆。
  - **日期解析全綠**：40/40 有日期，範圍 2026-09-01 ～ 2026-09-11，`days_since_posted()` 計算正確。
  - 換言之：`--district` 與 `--days` 的**程式邏輯已證明無誤**，只欠站方放行做端到端實跑。

- **實測驗收（2026-09-11，HKT 家用寬頻）**：
  `--pages 1` → **40 筆香港職缺**，七個關鍵欄位（`job_id`/`title`/`company`/
  `location`/`salary`/`url`/`posted_date`）**零空值**；地區分布 湾仔区 11 /
  油尖旺区 7 / 观塘区 6 / 沙田区 4 / 香港 4 / 中西区 2 / 西贡区 2 / 其他 4。

### 🗺️ 按地區篩選（獵聘）

- **層級**：站方只到**城市**層級（`320` 香港 / `330` 澳門 / `340` 台灣），
  **沒有分區碼**。分區名以字串形式出現在職缺的 `dq` 欄位（如 `香港-观塘区`），
  因此 `--district` 香港 18 區是**客戶端字串比對**（零額外請求）。
- **預設即香港**：本專案為香港求職爬蟲，未給 `--district` 時固定送 `city=320&dq=320`；
  給了無法辨識的值也同樣回退全香港（僅 `logger.warning`，不中斷）。
- **字典** `scrapers/liepin_areas.json`（獵聘專用，**不得跨站混用**）：
  18 區 × 簡體（站方寫法）／繁體／英文／常見地名別名。
  支援「观塘」「觀塘」「觀塘區」「Kwun Tong」等寫法。
- ⚠️ **別名必須簡繁並列**：2026-09-11 踩過——只列繁體「觀塘」時，打簡體「观塘」
  （獵聘自己用的寫法）反而配對失敗。程式另做「区／區」後綴正規化雙保險。

```bash
# 全香港（預設）
python main.py --source liepin --pages 1
# 元朗區（繁簡英皆可）
python main.py --source liepin --district 元朗
python main.py --source liepin --district YuenLong
# 觀塘
python main.py --source liepin --district 观塘
```

⚠️ 分區篩選是**從該頁結果中挑出**符合者，站方每次回傳的 40 筆是動態取樣，
熱門區（湾仔、油尖旺、观塘）筆數較多，冷門區可能為 0 筆——**0 筆不等於該區沒有職缺**。

---

## 🧭 技術筆記（BOSS直聘 zhipin 逆向要點 — Wave 5 受限模組）

> **2026-09-11 複查**：站方防護已從「全站安全验证」改為**部分開放 + 登入牆**。
> 首頁與海外專區可用純 `requests` 開啟（無安全驗證），但**香港職缺對訪客仍為零**
> （港澳台專區空 + 要求登入）。結論：仍不適合作為香港據點。

- ⚠️ **robots 受限**：`robots.txt` 明文 `Disallow: /*?query=*`、`*?city=*` 等，
  並**點名禁 `Jobuispider`**。本模組標記 `_ROBOTS_RESTRICTED`，實例化即警告。
- **2026-09-11 實測（與舊版記載不同之處）**：
  - ✅ 純 `requests` 開 `https://www.zhipin.com/` → **HTTP 200、513KB 真實頁面、
    108 個 `/job_detail/` 連結、無「安全验证」**（舊版記為「任何路徑一律落安全验证」）。
  - ✅ 網址為**路徑式 SEO 結構**：`/c100010000-p100109/`（城市-職能）、
    `/overseas/z8/`（中国港澳台）、`/overseas/p130000/`（職能），
    純路徑**不在** `Disallow: /*?query=*` 範圍內；但帶關鍵字時會用
    `/c100010000/?query=...`，那才是禁區。
  - ⛔ **港澳台專區是空的**：`/overseas/z8/`（中国港澳台）回傳 **0 張職位卡**，
    頁面明文「**没有更多职位，尝试登录查看全部职位 立即登录**」→ **登入牆**
    （與 Indeed 香港同類處置）。
  - ⛔ 首頁出現的 2 次「香港」是**電話國碼下拉選單**（`+852 中国香港`），
    **不是職缺城市**；父層 `/overseas/` 的職缺城市為上海／南京／青島等內地城市
    （該專區是「駐外職位」，供內地人出國，非香港職缺）。
  - 國家碼字典（`/overseas/` SSR 內嵌）確有 `101 = 中国香港`，
    但屬**國家/地區層級**，且該區實際無職缺。
- **結論**：BOSS直聘的職缺城市體系**不含香港**，港澳台專區對訪客為空且需登入
  → 對香港求職爬蟲**無可用價值**；模組保留（日後站方政策改變可復活），
  但不投入偵察資源。
- **模組策略**：導航 `/web/geek/job?query=<kw>` → 標題/內容含「安全验证」即警告後回 0 筆；
  若能通過則解析 `.job-card-wrapper`（`.job-name` 的 `/job_detail/<encryptId>.html`、
  `.company-name`、`.job-area`、`.salary`）。
- **不支援項**：`--district`（香港不在城市體系）/ `--category` / `--industry` /
  `--sort` / `--days` / `--detail` / `--pages > 1`（分頁依賴查詢串 = robots 禁區）
  → 全部警告後忽略或回空。

---

## 🧭 技術筆記（OfferToday 逆向要點）

> **前身 HKGoodJobs**（舊域 `hkgoodjobs.com` 全面 403，2026-09 止損）於 2026 年更名 **OfferToday** 重新上線，本據點為「Wave 3′ 復活賽」成果（R1–R10 低速偵察，2026-09）。

- **身世之謎**：入口 `https://www.offertoday.com/hk/recommend`。SPA（Vue）＋ 頁面載 `static.zhipin.com/assets/sdk/apm/patas.2.1.0.min.js`（**BOSS直聘 APM SDK**）→ **疑為 BOSS直聘的香港站**，但**未繼承其全站安全驗證**，目前對自動化友善；另有 `/web/security/entry/index.js` 需持續觀察是否升級防護。
- **🚀 免瀏覽器**：R8/R9 實測 **冷 `requests`（無 cookie、無瀏覽器指紋）直打列表 API 回 `code=0`**，且關鍵字／地區／職能／行業／翻頁**全數生效** → `use_browser=False`，與 JobMarket、eFinancialCareers 同級輕量。
- **⚠️ 2026-10-29 起必須帶 `traceid` 標頭**：列表與詳情 API 全數回 `HTTP 400`，回應只有 `Failure: 400 Bad Request`，標頭為 `Server-Info: boss-alb` / `process-stage: Stage-Inbound`——**閘道層就拒掉，根本沒進應用層**。逐項比對瀏覽器真實 XHR 後定位：只補 `traceid: <任意非空字串>`（實測 `F-abc` 即可）立刻回 `200`；`api-language`、`x-requested-with`、`device_id` cookie 均非必要。已於 `_post()` 與 `get_detail()` 統一補上。
- **列表 API**：`POST /wapi/geek/recommend/search/list`
  payload：`keyword` / `page` / `pageSize`（**上限 10**）/ `salaryType`（0 月薪、1 時薪）/ `publishTime`（0 今天、1 三天、2 七天、3 十四天）/ `employmentTypes` / `experiences` / `educationLevels` / `benefits` / `workPermits` / `rcdType`（固定 7）/ `jobFunctionCodes` / `industries` / `subDistrictCodes` / `searchSource`。回應在 `data.resultList`。
- **🎴 `cardType` 過濾（模組必守，否則會拿到假結果）**

  | cardType | `suppleCard` | 意義 | 處理 |
  |---|---|---|---|
  | 0 | `false` | **真命中** | ✅ 收錄 |
  | 0 | `true` | 推薦遞補（湊數用，與查詢無關） | ❌ 丟棄 |
  | 1 | – | 橫幅廣告（無 `jobId`） | ❌ 丟棄 |
  | 2 | – | 空結果插圖 | ❌ 丟棄 |
  | 3 | – | 「No more results」分隔線 | ❌ 無結果訊號，停止翻頁 |

- **🔑 編碼規則（⚠️ 字典 JSON 裡的複合鍵要拆前綴才能送 API）**
  - 地區 `subDistrictCodes` → **純 code**：區級 `HK101304`（元朗全區）、子區級 `HK101304104`（天水圍）。
    字典中子區的 `id` 是 `s<區碼>c<子區碼>`（`getHomePopWords` 的 **SEO slug**）——誤用會得到 `total=0` + 全數遞補（R6 血淚）。
  - 職能 `jobFunctionCodes` → POSITION **level-2 code**：`118000`＝所有資訊科技、`118001`＝架構師、`118006`＝開發者。level-1 與「所有」level-2 剛好同碼，故大類碼可直接送。
  - 行業 `industries` → INDUSTRY **level-2 code**：`1001`＝會計/審計/稅務、`1005`＝銀行、`1018`＝金融服務、`1027`＝保險。
    ⚠️ **level-1（`101` 財務/金融）只是群組標題，不是有效值**（送它 `total=0`）→ 要篩整個大類，**模組會自動展開成其全部細類**。
- **🕐 刊登日 `jobPostTime`（三種格式）**

  | 格式 | 範例 | 可否算天數 |
  |---|---|---|
  | `... on MM-DD` | `Updated on 09-03`、`Posted on 08-28` | ✅ 可（假設當年，跨年 -1 年） |
  | `... within 3 months` | `Updated within 3 months` | ❌ 太舊 |
  | `... N months ago` | `Posted 3 months ago` | ❌ 太舊 |

  → `publishTime` 是**軟篩選**（只讓推薦池偏向近期，仍會夾帶舊職位），
  故 `--days` 採**雙保險**：送 `publishTime` 參數 **＋** 客戶端再篩（後兩種格式一律淘汰）。
- **⚠️ `data.total` 不可信**：每次回傳都不同（475 / 800 / 353…），是**推薦池規模**而非命中數 → **分頁只能靠 `hasMore`**。
- **⚠️ 深翻頁會重疊**：推薦池以 `page` 遞增時會重複吐出相同職位——實測 `--category 資訊科技 --pages 5`
  抓回 50 筆、`job_id` 去重後為 **23 筆**（約 54% 重複）→ 深翻頁邊際效益遞減，
  重複由 `exporter` 的 `job_id` 去重吸收（增量寫入時亦同）。
- **欄位來源（列表卡一次到位，多數情況不需 `--detail`）**：`jobName` / `companyName` / `locationDesc` / `salaryDesc` / `jobTypeDesc` / `experience` / `educationDesc` / `skills` / `benefits` / `workPermitDesc` / `jobPostTime`。`jobId` 是加密字串（如 `XKouaVdubvupuJ3bljVhsg==`），職位網址 `/hk/job/<urlquote(id)>`。
- **✅ 詳情 API（R10 實測通過）**：`GET /wapi/geek/recommend/jobDetail`
  ⚠️ **參數一個都不能少**（只給 `id` + `sessionId` 會回 `code=2 Invalid param`）：
  ```
  id=<加密 jobId>&sessionId=<UUID>&lid=<UUID>.offer_today_hk_search_visitor_grcd:common.<UUID>.1
    &encryptExpectId=<取自列表卡>&markId=&curIndex=0&encryptJobId=<加密 jobId>
  ```
  - `sessionId` 不見於任何回應 → 是**前端自產的 UUID**，本模組自行 `uuid4()` 產生即可。
  - `lid` / `encryptExpectId` 取自列表卡（模組於列表階段暫存原始卡片）。
  - 🎁 回應獨有欄位：**`jobDesc`**（HTML 完整描述，模組轉純文字）、
    **`industryDesc`**（**列表沒有的行業**）、**`postDaysAgo`**（站方已算好的天數）、
    `salaryDesc` / `workExperienceDesc` / `educationDesc` / `brandIntroduce` / `addressVO`。
- **禮節**：`request_delay` 設為 3 秒（推薦池 API 較敏感），`pageSize` 上限 10 → 每頁 1 支請求。

## 🗺️ 按地區篩選（OfferToday）

- OfferToday 的地區走 API 的 **`subDistrictCodes`** 參數，吃**純 code**：
  - 區級　→ `HK101304`（元朗全區）
  - 子區級 → `HK101304104`（天水圍）
- 字典 `scrapers/offertoday_areas.json` 共 **18 行政區 + 129 子區**（中英文皆可輸入，逗號多選），
  與其他站（Moovup shortCode／gov_hk 數字 ID／JobsDB slug／JobMarket AreaID…）**完全獨立，不可混用**。
  18 區：中西區、灣仔、東區、南區、油尖旺、深水埗、九龍城、黃大仙、觀塘、葵青、荃灣、屯門、元朗、北區、大埔、沙田、西貢、離島。
- 範例：
  ```bash
  python main.py --source offertoday --district 元朗 --pages 3
  python main.py --source offertoday --district "元朗,屯門" --keyword engineer
  python main.py --source offertoday --category 資訊科技 --district 元朗
  python main.py --source offertoday --industry 銀行 --pages 2
  ```
- ⚠️ 未收錄的地區名稱會 `logger.warning` 後忽略，不報錯中斷。

---

## 🗺️ 路線圖（依計劃書）

| 階段 | 網站 | 難度 | 狀態 |
|------|------|------|------|
| 1–3 | Moovup 好工速遞 | 中（Cloudflare） | ✅ 已完成並實測 |
| 4 | 勞工處 gov.hk | 低（無反爬） | ✅ 已完成並實測 |
| 5 | JobsDB | 中高（需 Playwright） | ✅ 已完成並實測（關鍵字 + 翻頁 + --days + 職能/地區篩選 + --sort post_dt_desc；--industry 不適用） |
| 6 | LinkedIn | 高（強反爬） | ✅ 已完成並實測（訪客模式：關鍵字 + 地點 + --days + --sort post_dt_desc；深翻頁不穩定，填 li_at cookie 可解鎖；--category/--industry 不適用） |
| 7 | Indeed | 高（Cloudflare） | ✅ 已完成並實測（⚠️ 2026-09-08 修復：**必須本機 Chrome**——內建 Chromium 指紋已被 CF 擋下；**必須給 --keyword**——空 `q=` 站方回 0 筆。關鍵字 + 地區自由文字；**--days 經內嵌 pubDate 瞬時篩選 ~9s**；--detail 用 JS 點擊面板取描述 ~1s/張；--category/--industry/--sort 不適用） |
| 8 | Recruit（擴充八站 Wave 1） | 中（WebForms） | ✅ 已完成並實測（hidden 欄位三維篩選：關鍵字 + 94 區地區 + 34 大類/290 細類職能；--days 列表瞬時；--sort 五種；--detail 走 JSON-LD；列表無地區欄需 --detail；--industry 不適用） |
| 9 | JobMarket（擴充八站 Wave 1） | 低–中（JSP） | ✅ 已完成並實測（純 requests 免瀏覽器；四維篩選：關鍵字 Searchtext + 5 大區/75 子區 + 28 大類/195 細類 + 30 行業；批次 API 列表階段補地區/職缺類型；--days 列表瞬時；--sort 不適用） |
| 10 | foundit 原 Monster HK（擴充八站 Wave 2） | 中–高（指紋 WAF） | ✅ 已完成並實測（⚠️ 需本機 Google Chrome——WAF 封鎖 Chromium 指紋；關鍵字走 SEO SSR 瀏覽頁〔站方 API 故障 404〕；路徑後綴翻頁；46 地區 slug 中英雙語；--days 列表相對日期瞬時；--detail 走 JSON-LD〔requests 直達〕；--category/--industry/--sort 不適用；sitemap 8,799 職位保底） |
| 11 | eFinancialCareers（擴充八站 Wave 2） | 中（JSON API） | ✅ 已完成並實測（純 JSON API 免瀏覽器 `job-search-ui…/v3/efc/jobs/search`；關鍵字可空；--district 僅 3 大區〔站方細分區回 0 筆〕；--days API ISO 瞬時；--detail 走 JSON-LD；--category/--industry/--sort 不適用；香港 ~2,900 筆） |
| — | ~~HKGoodJobs~~ → **OfferToday**（擴充八站 Wave 3′ 復活賽） | 低（純 JSON API） | ✅ **已完成並實測**（2026-09-07 落地，第十座可用據點。🚀 **免瀏覽器純 requests**——冷請求無 cookie 亦可；關鍵字 + 18 區/129 子區 + 31 大類/431 細類職能 + 15 大類/53 細類行業；`cardType` 過濾防假結果；`--days` 送 `publishTime` + 客戶端再篩；`--detail` 已實測（補描述/行業/`postDaysAgo`）；`--sort` 不適用；`pageSize` 上限 10，翻頁靠 `hasMore`） |
| — | HKGoodJobs（擴充八站 Wave 3） | 判定 | ❌ **判定不可行，止損**（裸域全面真 403——Apache 伺服器端拒絕所有路徑，HTTP/HTTPS、真 Chrome 指紋、忽略憑證錯誤皆同；TLS 憑證另錯置錯誤網域。站方配置即拒所有自動/人工存取） |
| — | Glassdoor HK（擴充八站 Wave 4） | 高（CF + 誘餌） | ❌ **判定不可行，止損**（CF 挑戰不穩；首次可 200 但回**位置污染頁**——geoId 被無視、按資料中心 IP 定位到印度小頁鎮「Ambahta Rindān」，`Hong Kong` 僅 2 次 / `Ambahta` 37 次、0 個真職位連結。抓到也是錯資料） |
| 12 | 獵聘 Liepin（擴充八站 Wave 5） | 🟡 中（robots 禁抓 www 查詢串；IP 驗證碼門檻 ~6–7 支） | ✅ **2026-09-11 升級為可用香港據點**（第十座）！修正城市碼 `900`→**320**，並發現 `city` 與 `dq` 必須同時送才會過濾；實測 40 筆香港職缺、七關鍵欄位零空值、站方 `total≈800`；建香港 18 區字典；`--days` 以 `refreshTime` 客戶端篩選。⚠️ 分頁未驗證；連 6–7 支請求觸發 IP 驗證碼（間隔已調 8s） |
| 13 | BOSS直聘 Zhipin（擴充八站 Wave 5） | 🔴 高（robots 禁抓 `?query=`/`?city=`） | ⚠️ **2026-09-11 複查：維持受限**。防護由「全站安全验证」改為部分開放（首頁純 requests 可開、路徑式 SEO 網址），但**港澳台專區 0 張職位卡 + 登入牆**，香港不在職缺城市體系 → 對本專案無可用價值；模組保留待站方政策改變 |

> 路線圖前五站全數達標 ✅：Moovup / 勞工處 / JobsDB / LinkedIn / Indeed 五座據點皆已落地並實測。LinkedIn 現以訪客模式落地——功能可用但單次約 ~25–60 筆天花板；提供 `li_at` cookie（config.LINKEDIN_LI_AT / 環境變數）後深翻頁趨穩、可抓更深。Indeed 的 `--days` 現已由內嵌 `pubDate` 瞬時篩選（~9 秒，不再逐張點擊）；`--detail` 取描述改用 JS 點擊面板（~1 秒/張）；直連 viewjob 因 Cloudflare 不可行。
>
> **擴充八站計畫全數收官**（見 `docs/擴充八站開發計畫.md`）：Wave 1（Recruit、JobMarket）與 Wave 2（foundit、eFinancialCareers）**已完成** ✅✅✅✅（第六至九座可用據點）；Wave 3 HKGoodJobs ❌ 判定不可行（伺服器端全面 403）、Wave 4 Glassdoor ❌ 判定不可行（位置污染誘餌頁）；Wave 5 獵聘 + BOSS直聘 ⚠️ 受限模組依用戶要求落地（robots 禁抓 + 反爬極兇，行為可預期但不產資料）。
>
> 🆕 **Wave 3′ 復活賽收官（2026-09-07）**：HKGoodJobs 更名為 **OfferToday**（`www.offertoday.com`）後重啟偵察，R1–R10 十輪低速實測全數 `code=0`、**未觸發任何驗證碼或限速**，已落地為第十座可用據點。疑為 BOSS直聘香港站技術底（載 `static.zhipin.com` APM SDK）但**未繼承其全站安全驗證**——是目前成本最低的據點之一（免瀏覽器、純 JSON API）。
