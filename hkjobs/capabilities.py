"""12 站能力矩陣（`hkjobs sources` 的單一資料源）。

可從 scraper class 讀到的欄位（enabled / needs_browser）由契約測試交叉核對；
站方特有資訊（days_mode、sort_values、每頁筆數、needs_chrome）以 README
「各站功能支援矩陣」為準。改動任何據點行為時，必須同步更新本表。
`GAP_FILL_ACTIONS` 是 `--fill-gaps` 的單一資料源，`SALARY_CONVERSION_BASIS`
是薪金換算基準的單一文字來源（CLI 人類輸出直接引用）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config import delay_for

ALL_SORT_VALUES: tuple[str, ...] = (
    "post_dt_desc", "post_dt_asc",
    "salary_desc", "salary_asc",
    "yr_exp_desc", "yr_exp_asc",
    "edu_lvl_desc", "edu_lvl_asc",
)

_ALL_SORTS = ALL_SORT_VALUES

# `--fill-gaps` 的單一資料源：站名 → (要自動開啟的旗標, 補齊的欄位, 每筆額外請求數)。
# 只列「站方列表頁實測全缺、且本專案已有補齊手段」的據點；其餘站不是列表已完整，
# 就是站方根本不提供該欄位（COVERAGE_ADVICE 標為已知限制），硬打詳情也補不到。
# 請求數估算用 SourceInfo.per_page × --pages，執行前會先列出並要求確認。
GAP_FILL_ACTIONS: dict[str, tuple[str, str, int]] = {
    "gov_hk": ("detail", "company / posted_date", 1),
    "moovup": ("detail", "posted_date", 1),
    "recruit": ("fillLocation", "location", 1),
}

# 時薪／日薪／年薪換算成「可比較月薪」的基準。與 aggregate.PERIOD_TO_MONTH 一致；
# 這是估算值，不是僱主實際給付的月薪，人類輸出會逐筆標明。
SALARY_CONVERSION_BASIS = "每日 8 小時、每月 22 個工作日（時薪 ×176、日薪 ×22、年薪 ÷12）"


@dataclass(frozen=True)
class SourceInfo:
    name: str
    label: str
    enabled: bool
    needs_browser: bool
    needs_chrome: bool
    per_page: int
    keyword_required: bool
    days_mode: str                    # server | list | detail | approx | none
    sort_values: tuple[str, ...] = ()
    supports: dict[str, bool] = field(default_factory=dict)
    request_delay: float = 0.0
    notes: str = ""


SOURCES: dict[str, SourceInfo] = {
    "moovup": SourceInfo(
        name="moovup", label="好工速遞", enabled=True,
        needs_browser=True, needs_chrome=False, per_page=12,
        keyword_required=False, days_mode="none", sort_values=(),
        supports={"district": True, "category": False, "industry": False,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("moovup"),
        notes="Cloudflare Turnstile 需 Playwright；列表無日期（實測 0/12），--detail 才補；"
              "不支援 --days。薪金含時薪寫法（如 $45-50/小時），聚合時依 8h×22 日換算為月薪。"
              "--fill-gaps 會自動開 --detail 補刊登日。",
    ),
    "gov_hk": SourceInfo(
        name="gov_hk", label="勞工處", enabled=True,
        needs_browser=False, needs_chrome=False, per_page=20,
        keyword_required=False, days_mode="server", sort_values=_ALL_SORTS,
        supports={"district": True, "category": True, "industry": True,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("gov_hk"),
        notes="ASP.NET SSR；--days 走站方 postedDtFr/To 且不改排序；--sort 8 值全支援。"
              "⚠️ 列表頁無僱主欄位，company 需 --detail（每筆多 1 支請求）。"
              "詳情頁 #postedDt 為 DD/MM/YYYY（日在前），聚合層正規化為 ISO；"
              "--fill-gaps 會自動開 --detail 補 company 與 posted_date。",
    ),
    "jobsdb": SourceInfo(
        name="jobsdb", label="JobsDB", enabled=True,
        needs_browser=True, needs_chrome=False, per_page=20,
        keyword_required=False, days_mode="server", sort_values=("post_dt_desc",),
        supports={"district": True, "category": True, "industry": False,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("jobsdb"),
        notes="2026-11-15 起預設走 GraphQL jobSearchV7（免瀏覽器、補結構化薪金與精確刊登日）；"
              "--district 若在字典 40 個之內，改以 searchIntent.where 下推（免瀏覽器；"
              "查詢帶 distanceKms:2，站方會納入附近地區）。"
              "指定 --category/--sort、地區不在字典、設 JOBSDB_GRAPHQL=0 或通道熔斷時"
              "退回 Playwright SSR，此時薪金常缺（實測 30 筆中 23 筆無薪金）。"
              "--days 站方端仍只吃 1/3/7/14/31，"
              "GraphQL 轉為 listedAt:\"Nd\"（31→30d）；只做日期過濾、保留相關性排序。"
              "--salary-min 下推為 GraphQL filter.salaryMin:\"Nm\"（m=monthly）；"
              "SSR fallback 的 salaryrange 網址參數實測無效（2026-11-15），該路徑僅客戶端篩，"
              "且 SSR 列表薪金覆蓋低，fallback 下會丟掉大量「無法判斷」的職位。"
              "其餘來源沒有站方端參數，由客戶端依正規化月薪兜底篩選。"
              "--detail 自 2026-11-15 起也走 GraphQL jobDetails 免瀏覽器（完整 JD HTML 轉純文字）；"
              "上述 SSR 情境與通道熔斷時才需 Playwright，故 needsBrowser 維持 True。"
              "✅ GraphQL 通道已於 2026-11-15 做過即時驗證（搜尋／翻頁／詳情／地區 where 抽驗 3 區）；"
              "仍未驗證：中文關鍵字送 text、--category/--sort 的 SSR 瀏覽網址、"
              "字典外 39 個地區的 where 命中率。",
    ),
    "linkedin": SourceInfo(
        name="linkedin", label="LinkedIn", enabled=True,
        needs_browser=False, needs_chrome=False, per_page=58,
        keyword_required=False, days_mode="server", sort_values=("post_dt_desc",),
        supports={"district": True, "category": False, "industry": False,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("linkedin"),
        notes="訪客模式；首頁 ~58、續頁 ~10；深翻頁可設 LINKEDIN_LI_AT。"
              "列表不提供薪金（實測 0/59），聚合時列為已知缺口。",
    ),
    "indeed": SourceInfo(
        name="indeed", label="Indeed", enabled=False,
        needs_browser=True, needs_chrome=True, per_page=16,
        keyword_required=True, days_mode="server", sort_values=(),
        supports={"district": True, "category": False, "industry": False,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("indeed"),
        notes="停用（2026-09-11 強制登入牆）；--keyword 必給；需本機 Chrome。",
    ),
    "recruit": SourceInfo(
        name="recruit", label="Recruit", enabled=True,
        needs_browser=True, needs_chrome=False, per_page=25,
        keyword_required=False, days_mode="list", sort_values=_ALL_SORTS,
        supports={"district": True, "category": True, "industry": False,
                  "detail": True, "fillLocation": True},
        request_delay=delay_for("recruit"),
        notes="列表無地區欄；單區篩選零請求回填，多區/未篩選需 --fill-location；"
              "asc 排序以站方 desc 近似並警告。--fill-gaps 會自動開 --fill-location 補地區。",
    ),
    "jobmarket": SourceInfo(
        name="jobmarket", label="JobMarket 求職廣場", enabled=True,
        needs_browser=False, needs_chrome=False, per_page=20,
        keyword_required=False, days_mode="list", sort_values=(),
        supports={"district": True, "category": True, "industry": True,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("jobmarket"),
        notes="純 requests；站方預設大致新→舊（頂部推廣／置頂區塊不排序，偏舊故不影響提早停翻）；"
              "無 --sort 參數。列表不提供薪金（實測 0/20），且同站重複職缺常見，聚合時會去重。",
    ),
    "foundit": SourceInfo(
        name="foundit", label="foundit", enabled=True,
        needs_browser=True, needs_chrome=True, per_page=20,
        keyword_required=False, days_mode="list", sort_values=(),
        supports={"district": True, "category": False, "industry": False,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("foundit"),
        notes="需本機 Google Chrome（內建 Chromium 被 WAF 403）；SEO 瀏覽頁固定排序。"
              "列表不提供薪金（實測 0/20）。",
    ),
    "efc": SourceInfo(
        name="efc", label="eFinancialCareers", enabled=True,
        needs_browser=False, needs_chrome=False, per_page=50,
        keyword_required=False, days_mode="list", sort_values=(),
        supports={"district": True, "category": False, "industry": False,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("efc"),
        notes="純 JSON API；地區僅 3 大區（細分區站方回 0 筆）。"
              "2026-11-11 起未指定 --district 時預設 Hong Kong（原會回 London／New York 等全球職缺）；"
              "薪金多為 Competitive／Negotiable，不計入 withSalary。",
    ),
    "liepin": SourceInfo(
        name="liepin", label="獵聘", enabled=False,
        needs_browser=True, needs_chrome=True, per_page=40,
        keyword_required=False, days_mode="approx", sort_values=(),
        supports={"district": True, "category": False, "industry": False,
                  "detail": False, "fillLocation": False},
        request_delay=delay_for("liepin"),
        notes="停用；近 N 天以刷新日近似；詳情受驗證碼保護；連 6–7 支請求即觸發 IP 驗證碼。",
    ),
    "zhipin": SourceInfo(
        name="zhipin", label="BOSS直聘", enabled=False,
        needs_browser=True, needs_chrome=True, per_page=0,
        keyword_required=False, days_mode="none", sort_values=(),
        supports={"district": False, "category": False, "industry": False,
                  "detail": False, "fillLocation": False},
        request_delay=delay_for("zhipin"),
        notes="停用；香港不在站方城市體系（港澳台專區 0 張且需登入）。",
    ),
    "offertoday": SourceInfo(
        name="offertoday", label="OfferToday", enabled=True,
        needs_browser=False, needs_chrome=False, per_page=10,
        keyword_required=False, days_mode="server", sort_values=(),
        supports={"district": True, "category": True, "industry": True,
                  "detail": True, "fillLocation": False},
        request_delay=delay_for("offertoday"),
        notes="免瀏覽器純 API；每頁上限 10；--days 送 publishTime 並客戶端再篩（只認 on MM-DD）。",
    ),
}
