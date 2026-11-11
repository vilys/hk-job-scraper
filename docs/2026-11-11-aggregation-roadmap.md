# 聚合平台下一步設計（只設計，尚未實作）

> 2026-11-11 · 狀態：**設計稿，未開工**
> 本輪已完成 schema v2 的正規化／跨站排序／去重／完整度（見 `AGENTS.md`）。
> 本文只回答「接下來三項能力要長在哪裡」，不含任何程式碼變更。

## 0. 先畫清楚邊界

| 層 | 現在負責什麼 | 生命週期 |
|---|---|---|
| `scrapers/*` | 把站方頁面變成 `JobRecord`（v1，13 欄） | 單次請求 |
| `hkjobs/aggregate.py` | v1 → v2、去重、排序、完整度 | 單次執行、記憶體內 |
| `hkjobs/contract.py` | 組 `--json` 封套（v2） | 單次執行 |
| `exporter.py` | 把 `JobRecord` 增量寫進 `output/*.json` / `.csv` | **跨次**，但是「資料堆」 |
| `output/` | 已被 gitignore | 本機 |

關鍵洞察：**`exporter` 已經是跨次儲存，但它只會「附加並依 `job_id` 去重」，沒有任何使用者狀態的位置。**
收藏／已申請／看過，是「人對職缺的關係」，不是職缺本身的欄位。把這些塞進 `jobs[]` 會讓每次搜尋的封套愈來愈胖，而且 `--json` 的 agent 契約會被污染。

因此設計原則：**狀態另存，搜尋結果保持無狀態。**

## 1. 資料存哪

`output/hkjobs.sqlite3`（Python 標準庫 `sqlite3`，零新依賴、`output/` 已 gitignore）。

為什麼是 SQLite 而不是另一份 JSON：

- 收藏／已申請會被反覆讀寫，JSON 每次全檔重寫，容易在中断時毀損（`exporter` 已為此做過原子寫入備份，不想再複製一次）
- 需要「上次跑過之後新增了哪些」這種查詢，SQL 的 `WHERE first_seen > ?` 一行搞定
- 單檔、可直接用 DB 工具檢查、可 `VACUUM`；不需伺服器
- 與 `exporter` 不衝突：兩者各自寫自己的檔案，互不覆寫

**不做**：雲端同步、帳號、多人共用同一個 state 檔（見 §5）。

## 2. Schema（提案）

```sql
-- 職缺主檔：以 v2 的穩定鍵為身份，原始欄位只留查核用的最小集合
CREATE TABLE jobs (
  fingerprint   TEXT PRIMARY KEY,   -- sha1(normalize(title)|normalize(company)|source_group)
  title         TEXT NOT NULL,
  company       TEXT,
  canonical_url TEXT,
  salary_min    INTEGER,            -- 月薪；NULL = 解析不出
  salary_max    INTEGER,
  posted_date   TEXT,               -- ISO
  first_seen    TEXT NOT NULL,      -- UTC ISO
  last_seen     TEXT NOT NULL,
  blob          TEXT                -- 完整 v2 紀錄（JSON），供離線重播
);

-- 人對職缺的狀態（唯一會被使用者寫入的表）
CREATE TABLE job_state (
  fingerprint   TEXT PRIMARY KEY REFERENCES jobs(fingerprint),
  starred       INTEGER NOT NULL DEFAULT 0,
  applied       INTEGER NOT NULL DEFAULT 0,
  hidden        INTEGER NOT NULL DEFAULT 0,
  note          TEXT NOT NULL DEFAULT '',
  updated_at    TEXT NOT NULL
);

-- 每次執行留一列，讓「新職缺通知」有可靠的比較基準
CREATE TABLE runs (
  run_id        TEXT PRIMARY KEY,
  started_at    TEXT NOT NULL,
  query_json    TEXT NOT NULL,       -- 當次 query（source/keyword/days…）
  raw_total     INTEGER NOT NULL,
  deduped       INTEGER NOT NULL,
  new_count     INTEGER NOT NULL     -- 本次 first_seen == run_id 的筆數
);
```

### 身份鍵（最需要想清楚的一件事）

現在 `job_id` 有三種格式（各站自行產生），而且**去重後一筆職缺可能來自多站**，
所以 `job_id` 不適合當長期主鍵。改用 `fingerprint`：

```
sha1( normalize(title) + "|" + normalize(company) + "|" + sorted(sources)[0] )
```

- `normalize` 直接複用 `aggregate._norm()`，與去重邏輯同源，避免「去重說同一筆、state 說兩筆」
- 公司為空時（勞工處列表）退回 `canonical_url` 的 sha1，代價是 `--detail` 補出公司名後會被視為新職缺 → **下一輪要處理的已知缺口**，見 §6
- 這個鍵只進 SQLite，**不進 `--json` 封套**，agent 契約完全不動

## 3. 與現有 exporter 的關係

| | `exporter.py` | 新的 `StateStore` |
|---|---|---|
| 目的 | 給人看的完整清單（CSV/JSON） | 給程式查的長期狀態 |
| 寫入時機 | `--out` 或 `main.py` 每次執行 | `hkjobs search` 每次執行（可 `--no-state` 關閉） |
| 去重依據 | `job_id` | `fingerprint` |
| 使用者狀態 | 無 | `job_state` |
| 衝突 | — | 無：不同檔案、不同鍵、彼此不讀對方 |

`exporter` **維持原樣**，一個字都不改（它是 `main.py` 的既有契約）。
`StateStore` 只由 `hkjobs` 呼叫；`python main.py` 不會產生狀態，行為不變。

## 4. 三項能力的落地順序

### Phase 1（下一輪，建議一起做）

1. `hkjobs/state.py`：`StateStore`，負責建表、 upsert `jobs`、寫 `runs`。零外部依賴。
2. `hkjobs star <fingerprint>` / `unstar` / `apply` / `hide` / `note`：只改 `job_state`。
3. `hkjobs search --new-since last`：比對 `first_seen` 與上一次 `runs`，人類輸出多一行「本次新增 N 筆」；`--json` 的 `summary.newSinceLast` 為可選新欄位（**若加，就要再升 schema v3**）。

### Phase 2（之後再评估）

4. **跨站互補補齊**：同一 `fingerprint` 的多筆 v2 紀錄，逐欄位以「非空且可信」覆蓋空白
   （典型：A 站缺公司、B 站有）。目前 `aggregate.deduplicate()` 刻意只合併 `sources`/`urls`，
   **本輪不做**，因為「誰的值比較可信」需要各站優先序表，屬另一個決策，不该順手猜。

### 明確不做（YAGNI）

- 雲端同步 / 帳號 / 跨裝置（單人本機工具，導入就要處理憑證與隱私）
- 自動投遞履歷、自動寫求職信（超出爬蟲範圍，且是高風險外部動作）
- Web UI / 儀表板（既有 `dashboard.html` 是離線靜態頁，够用）
- 全文搜尋引擎、推薦演算法（求職者要的是「看得到、不重複、數字可信」）
- 把 `job_state` 塞進 `--json` 封套（會污染 agent 契約；要查就用 `hkjobs state --json`）

## 5. 隱私與安全

- `output/` 已 gitignore；state 檔含個人備註與瀏覽紀錄，**不得提交、不得上傳**
- 職位內容可能含聯絡方式；`note` 由使用者自行輸入，不做任何外傳
- `LINKEDIN_LI_AT` 等憑證維持既有禁令，state 檔不碰環境變數

## 6. 已知缺口（下一輪開工前要先回答）

1. **公司名補齊會換 fingerprint**：勞工處不加 `--detail` 時公司為空，加了之後同一職缺會被算成兩筆。解法候選：以 `canonical_url` 為主鍵、`(title, company)` 只用作比對別名表。
2. **`job_id` 三格式**：技術債仍在（見專案記憶），但 `fingerprint` 讓它不再阻塞狀態層。
3. **`posted_date` 相對時間的基準**：本輪已改為以每筆 `scraped_at` 換算，離線重播可重現；`first_seen` 則應一律用執行當下 UTC，兩者不可混用。
4. **去重合併的可信來源優先序**：Phase 2 若要補欄位，需先訂出各站優先序（例如 `gov_hk --detail` 的公司名 > 其他站），不能靠「先到先贏」。

---

**結論**：下一輪只做 §4 的 Phase 1（StateStore + 收藏／已申請 + 新職缺通知），
並在開工前先解決 §6-1 的身份鍵問題。其餘能力留在這份地圖上，等真的有人需要再畫路線。
