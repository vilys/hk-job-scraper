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
import re
import sys
from pathlib import Path

# 讓腳本無論從哪裡執行都能 import 本專案模組
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config import OUTPUT_DIR  # noqa: E402
from scrapers import SCRAPERS  # noqa: E402
from hkjobs.args import build_search_argparser  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def build_argparser() -> argparse.ArgumentParser:
    """向後相容的入口；定義集中在 hkjobs.args（與 hkjobs CLI 共用）。"""
    return build_search_argparser(description="香港求職網站自動搜尋程式")


def main() -> None:
    args = build_argparser().parse_args()

    # 解析要執行的爬蟲
    if args.source == "all":
        sources = [n for n, cls in SCRAPERS.items() if getattr(cls, "enabled", True)]
        skipped = [n for n, cls in SCRAPERS.items() if not getattr(cls, "enabled", True)]
        if skipped:
            logger.warning(
                "--source all 已略過停用來源：%s（需要時請用 --source <名稱> 單獨指定）",
                ", ".join(skipped),
            )
    elif args.source in SCRAPERS:
        sources = [args.source]
    else:
        logger.error("未知來源：%s（可選：%s）", args.source, ", ".join(SCRAPERS))
        sys.exit(1)

    # 關鍵字轉檔名：先剔除 Windows 路徑非法字元（\ / : * ? " < > |），空白轉底線
    kw_safe = re.sub(r'[\\/:*?"<>|]+', "", args.keyword).replace(" ", "_") or "all"
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
                fill_location=args.fill_location,
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
