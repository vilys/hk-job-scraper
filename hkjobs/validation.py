# -*- coding: utf-8 -*-
"""支援站的字典值前置驗證：在發出任何爬取請求之前擋下無效篩選值。

與「跨站不支援參數」的區別（AGENTS.md 兩條規則不可混用）：

- `options.load_dimension()` 回 `None`（該站不支援此維度）或 `kind="free"`
  （接受自由文字）→ 沿用既有行為「警告後忽略」，本模組不介入。
- 回傳固定值域 → 該站**支援**此維度，輸入值不在值域內代表篩選不會生效。
  過去 scraper 只印一行 WARNING 就回傳未過濾結果且 exit 0，求職者會誤以為
  篩到了目標職位；這種「假成功」比報錯更危險，故由 CLI 以 exit 2 擋下。

只處理有字典的三個維度；`--sort` 的值域差異是既有設計（各站各自警告後回退），
`--days` 不屬字典維度，兩者都不在此驗證範圍。
"""
from __future__ import annotations

import difflib
import re

from hkjobs.options import load_dimension

DIMENSION_FLAGS = {
    "district": "--district",
    "category": "--category",
    "industry": "--industry",
}
DIM_LABELS = {
    "district": "地區",
    "category": "工作種類／職能",
    "industry": "行業",
}
_CJK = re.compile(r"[\u4e00-\u9fff]")


def _accepted_values(info: dict) -> set[str]:
    """把 options 的值域攤平為可比對字串（name / id / aliases，大小寫不計）。"""
    out: set[str] = set()
    for value in info.get("values") or []:
        if isinstance(value, dict):
            candidates = [value.get("name"), value.get("id"),
                          *(value.get("aliases") or [])]
        else:
            candidates = [value]
        for candidate in candidates:
            text = str(candidate or "").strip().casefold()
            if text:
                out.add(text)
    # 各站 scraper 對中文地區普遍接受「去區字尾」／「加區字尾」的寫法
    # （見 scrapers/gov_hk.py 的 resolve_districts）。驗證要比 scraper 寬鬆，
    # 否則會把合法別名誤判成無效值。
    for text in list(out):
        if text.endswith("區"):
            out.add(text[:-1])
        elif _CJK.search(text):
            out.add(text + "區")
    return out


def _is_accepted(value: str, accepted: set[str]) -> bool:
    text = value.strip().casefold()
    if not text:
        return True
    if text in accepted:
        return True
    return text.endswith("區") and text[:-1] in accepted


def _candidates(value: str, info: dict) -> list[str]:
    names = []
    for item in info.get("values") or []:
        if isinstance(item, dict):
            if item.get("name"):
                names.append(str(item["name"]))
        elif item:
            names.append(str(item))
    return difflib.get_close_matches(value, names, n=3, cutoff=0.4)


def validate_dimensions(args, plan) -> tuple[list[str], list[str]]:
    """回 `(fatal, warnings)`；fatal 非空時 CLI 應回 exit 2 且不發任何請求。

    單一站：任一維度值無效即 fatal。
    `--source all`：只有「所有支援該維度的站」都判定無效才 fatal
    （例如 `--category 打字員` 對每一站都不成立）。若部分站接受、部分站不接受，
    保留既有各站「警告後忽略」的行為，只在 stderr 提醒，不誤傷跨站字典差異
    （各站地區／職能字典本來就獨立，沒有一個值能同時適用九站）。
    """
    fatal: list[str] = []
    warnings: list[str] = []
    multi = getattr(args, "source", None) == "all"

    for dim, flag in DIMENSION_FLAGS.items():
        raw_value = getattr(args, dim, None)
        if not raw_value:
            continue
        items = [x.strip() for x in str(raw_value).split(",") if x.strip()]
        if not items:
            continue

        bad: list[tuple[str, dict, str]] = []
        good: list[str] = []
        for name, enabled in plan:
            if not enabled:
                continue
            info = load_dimension(name, dim)
            if info is None or info.get("kind") == "free":
                continue  # 不支援／自由文字：既有「警告後忽略」不變
            accepted = _accepted_values(info)
            invalid = [x for x in items if not _is_accepted(x, accepted)]
            if invalid:
                bad.append((name, info, invalid[0]))
            else:
                good.append(name)

        if not bad:
            continue
        if not multi or not good:
            name, info, wrong = bad[0]
            lines = [
                f"{flag}「{wrong}」不是 {name} 的有效{DIM_LABELS[dim]}值；"
                "為避免回傳未過濾結果，已停止（未發出任何爬取請求）。"
            ]
            near = _candidates(wrong, info)
            if near:
                lines.append(f"  最接近的候選：{'、'.join(near)}")
            lines.append(
                f"  查詢全部有效值：hkjobs options --source {name} --dimension {dim}"
            )
            fatal.append("\n".join(lines))
        else:
            names = "、".join(sorted({row[0] for row in bad}))
            warnings.append(
                f"注意：{flag}「{items[0]}」在 {names} 不是有效值，這些站沿用既有"
                "「警告後忽略」行為（其餘站仍套用篩選）；可用 "
                f"hkjobs options --source <站> --dimension {dim} 查詢。"
            )
    return fatal, warnings
