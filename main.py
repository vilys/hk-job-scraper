"""
統一執行入口 (Phase 7.1)

用法範例：
    python main.py --source moovup --keyword "零售" --pages 3 --output json
    python main.py --source moovup --keyword "會計" --pages 5 --output both --detail
    python main.py --source all    --keyword "工程師" --pages 2 --output csv

說明：
    --source   moovup | gov_hk | jobsdb | linkedin | all（四座據點皆已實作）
    --keyword  搜尋關鍵字（繁體中文或英文皆可）
    --pages    最大翻頁數（每頁約 12 筆）
    --output   json | csv | both
    --detail   同時抓取每筆職位的詳情（職責/要求/發佈時間）
    --outfile  自訂輸出檔名（不含副檔名）；預設 output/<source>_<keyword>
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# 讓腳本無論從哪裡執行都能 import 本專案模組
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config import OUTPUT_DIR  # noqa: E402
from scrapers import SCRAPERS  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="香港求職網站自動搜尋程式")
    p.add_argument("--source", default="moovup",
                   help="爬蟲來源：moovup | gov_hk | jobsdb | linkedin | all")
    p.add_argument("--keyword", default="",
                   help="搜尋關鍵字（留空 = 不限定關鍵字，僅依地區/類別瀏覽；"
                        "gov_hk 支援，moovup 建議仍給關鍵字）")
    p.add_argument("--pages", type=int, default=3, help="最大翻頁數")
    p.add_argument("--output", default="json",
                   choices=["json", "csv", "both"], help="輸出格式")
    p.add_argument("--detail", action="store_true",
                   help="同時抓取職位詳情（職責/要求/發佈時間/刊登日期）")
    p.add_argument("--outfile", default=None,
                   help="自訂輸出檔名（不含副檔名）")
    p.add_argument("--district", default=None,
                   help="地區過濾（可逗號分隔多個，JobsDB 僅取第一個）："
                        "gov_hk 用數字 ID / 中文（如 屯門=188）；"
                        "JobsDB 用中文名或 slug（如 荃灣 | tsuen-wan，見 scrapers/jobsdb_districts.json）；"
                        "moovup 用 shortCode；"
                        "LinkedIn 用自由文字（如 Hong Kong | Tsuen Wan，預設 Hong Kong）。各站體系獨立，不可混用。")
    p.add_argument("--category", default=None,
                   help="工作種類 / 職能過濾："
                        "gov_hk 用中文名（如 會計 | 文員 | 司機 | 清潔）；"
                        "JobsDB 用中文名或英文或 slug（如 資訊及通訊科技 | Information & Communication "
                        "Technology，見 scrapers/jobsdb_classifications.json）。兩站字典獨立。")
    p.add_argument("--industry", default=None,
                   help="行業過濾：僅 gov_hk 支援（中文名，如 飲食業 | 建造業 | 零售業 | 金融業）。"
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
                        "moovup 不支援（傳入會警告並忽略）。預設按刊登日期由近至遠排序。")
    return p


def main() -> None:
    args = build_argparser().parse_args()

    # 解析要執行的爬蟲
    if args.source == "all":
        sources = list(SCRAPERS.keys())
    elif args.source in SCRAPERS:
        sources = [args.source]
    else:
        logger.error("未知來源：%s（可選：%s）", args.source, ", ".join(SCRAPERS))
        sys.exit(1)

    kw_safe = args.keyword.replace(" ", "_") or "all"
    total_written = 0

    for src in sources:
        ScraperCls = SCRAPERS[src]
        logger.info("==== 開始爬取來源：%s ====", src)
        scraper = ScraperCls()
        try:
            if args.outfile:
                out_path = OUTPUT_DIR / f"{args.outfile}"
            else:
                out_path = OUTPUT_DIR / f"{src}_{kw_safe}"
            # 轉為帶副檔名的完整路徑（exporter 會視格式加 .json/.csv）
            ext = "json" if args.output in ("json", "both") else "csv"
            out_path = out_path.with_suffix("." + ext)

            jobs = scraper.scrape_all(
                keyword=args.keyword,
                max_pages=args.pages,
                district=args.district,
                category=args.category,
                industry=args.industry,
                sort=args.sort,
                days=args.days,
                with_detail=args.detail,
                output=str(out_path),
                fmt=args.output,
            )
            total_written += len(jobs)
            logger.info("[%s] 本輪取得 %d 筆職位。", src, len(jobs))
        except Exception as e:  # noqa: BLE001
            logger.exception("[%s] 執行失敗：%s", src, e)
        finally:
            scraper.close()

    logger.info("全部完成，共處理 %d 筆職位。", total_written)


if __name__ == "__main__":
    main()
