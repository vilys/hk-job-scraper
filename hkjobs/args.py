"""hkjobs 命令列參數定義（main.py 與 hkjobs CLI 共用，避免兩套 help 漂移）。"""
from __future__ import annotations

import argparse


def add_search_arguments(
    p: argparse.ArgumentParser, *, include_output_flags: bool = True
) -> None:
    """加入搜尋旗標。文字與預設值必須與舊 main.py 完全一致。"""
    p.add_argument("--source", default="moovup",
                   help="爬蟲來源：moovup | gov_hk | jobsdb | linkedin | indeed | "
                        "recruit | jobmarket | foundit | efc | liepin | zhipin | "
                        "offertoday | all")
    p.add_argument("--keyword", default="",
                   help="搜尋關鍵字（留空 = 不限定關鍵字，僅依地區/類別瀏覽；"
                        "gov_hk 支援，moovup 建議仍給關鍵字）")
    p.add_argument("--pages", type=int, default=3, help="最大翻頁數")
    if include_output_flags:
        p.add_argument("--output", default="json",
                       choices=["json", "csv", "both"], help="輸出格式")
    p.add_argument("--detail", action="store_true",
                   help="同時抓取職位詳情（職責/要求/發佈時間/刊登日期）")
    p.add_argument("--fill-location", action="store_true",
                   help="列表階段補地區：僅 recruit 需要並支援（該站列表頁沒有地區欄）。"
                        "會對每筆多打 1 支輕量 AJAX 請求（25 筆/頁 → 25 支，含節流），故預設關閉。"
                        "若只用 --district 篩選單一地區，recruit 會零請求直接回填，不必開此選項。"
                        "其餘來源（列表已含地區）傳入會警告並忽略。")
    if include_output_flags:
        p.add_argument("--outfile", default=None,
                       help="自訂輸出檔名（不含副檔名）")
    p.add_argument("--district", default=None,
                   help="地區過濾（可逗號分隔多個，JobsDB 僅取第一個）："
                        "gov_hk 用數字 ID / 中文（如 屯門=188）；"
                        "JobsDB 用中文名或 slug（如 荃灣 | tsuen-wan，見 scrapers/jobsdb_districts.json）；"
                        "moovup 用 shortCode；"
                        "LinkedIn 用自由文字（如 Hong Kong | Tsuen Wan，預設 Hong Kong）；"
                        "offertoday 用中文/英文區名或子區名（如 元朗 | 天水圍 | Yuen Long）。"
                        "各站體系獨立，不可混用。")
    p.add_argument("--category", default=None,
                   help="工作種類 / 職能過濾："
                        "gov_hk 用中文名（如 會計 | 文員 | 司機 | 清潔）；"
                        "JobsDB 用中文名或英文或 slug（如 資訊及通訊科技 | Information & Communication "
                        "Technology，見 scrapers/jobsdb_classifications.json）；"
                        "offertoday 用中文/英文職能名（如 資訊科技 | 開發者，見 scrapers/offertoday_categories.json）。"
                        "兩站字典獨立。")
    p.add_argument("--industry", default=None,
                   help="行業過濾：僅 gov_hk 與 JobMarket 與 offertoday 支援"
                        "（gov_hk / JobMarket 用中文名，如 飲食業 | 建造業 | 零售業 | 金融業；"
                        "offertoday 用中英文行業名，如 銀行 | 財務/金融，見 scrapers/offertoday_industries.json；"
                        "注意大類會自動展開為細類）。"
                        "JobsDB 無獨立行業維度（職能分類已涵蓋），傳入會被忽略並提示。")
    p.add_argument("--sort", default=None,
                   choices=["post_dt_desc", "post_dt_asc",
                            "salary_desc", "salary_asc",
                            "yr_exp_asc", "yr_exp_desc",
                            "edu_lvl_asc", "edu_lvl_desc"],
                   help="排序：gov_hk 全選項支援（post_dt_desc=刊登日期新→舊 | "
                        "post_dt_asc=舊→新 | salary_desc/asc=月薪多/少 | "
                        "yr_exp_asc/desc=經驗少/多 | edu_lvl_asc/desc=學歷低/高）。"
                        "JobsDB 與 LinkedIn 僅支援 post_dt_desc（JobsDB 對應 sortmode=ListedDate；"
                        "LinkedIn 對應 sortBy=DD，皆為新→舊），其餘選項為 gov_hk 專有，"
                        "JobsDB / LinkedIn 傳入會警告並回退網站預設排序。"
                        "設 --days 時若未指定 --sort，自動套用 post_dt_desc。")
    p.add_argument("--days", type=int, default=None,
                   help="只保留最近 N 天內刊登的職位："
                        "gov_hk 自動抓詳情取日期；JobsDB 與 LinkedIn 直接用列表相對刊登日過濾（不抓詳情）；"
                        "moovup 不支援（傳入會警告並忽略）；"
                        "offertoday 支援：送站方 publishTime 參數 + 客戶端再篩"
                        "（只有「on MM-DD」格式能算天數，其餘視為過舊淘汰）。"
                        "預設按刊登日期由近至遠排序。")


def build_search_argparser(
    *, description: str, prog: str | None = None
) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description, prog=prog)
    add_search_arguments(p)
    return p


def add_machine_arguments(p: argparse.ArgumentParser) -> None:
    """hkjobs 專屬輸出旗標（舊 main.py 不加入）。"""
    p.add_argument("--json", action="store_true",
                   help="機器模式：stdout 輸出單一 JSON 封套、不寫檔；日誌走 stderr（預設 WARNING）")
    p.add_argument("--out", default=None, metavar="PATH",
                   help="顯式寫檔：.csv 寫職位 CSV（UTF-8 BOM）；其他副檔名寫 JSON"
                        "（--json 時寫完整封套，否則寫職位陣列）")
    p.add_argument("-q", "--quiet", action="store_true", help="日誌只保留 ERROR")
