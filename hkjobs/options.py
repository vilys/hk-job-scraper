"""把 scrapers/*.json 的 5 種結構正規化為統一條目（`hkjobs options` 的資料源）。

⚠️ 只做形狀轉換，不修改字典、不決定值域：值域一律以 JSON 檔實際內容為準。
搜尋時的正規化仍由各站爬蟲自己負責（本模組不參與 --district 解析）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Callable

from hkjobs.capabilities import SOURCES


@dataclass(frozen=True)
class OptionEntry:
    id: str | None
    name: str
    aliases: tuple[str, ...] = ()
    parent_id: str | None = None


def _read(filename: str) -> Any:
    return json.loads((files("scrapers") / filename).read_text(encoding="utf-8"))


def _uniq(items) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return tuple(out)


def _simple_pairs(filename: str):
    return [
        OptionEntry(id=str(r["id"]), name=r.get("name", ""))
        for r in _read(filename)
    ]


def _moovup_district():
    return [
        OptionEntry(
            id=r.get("shortCode"),
            name=r.get("zh", ""),
            aliases=_uniq([r.get("en", ""), r.get("shortCode", "")]),
        )
        for r in _read("moovup_districts.json")
    ]


def _jobsdb_district():
    return [
        OptionEntry(id=r["slug"], name=r["zh"], aliases=_uniq([r["slug"]]))
        for r in _read("jobsdb_districts.json")
    ]


def _jobsdb_category():
    return [
        OptionEntry(
            id=r["slug"],
            name=r.get("zh") or r["name"],
            aliases=_uniq([r.get("name", ""), r["slug"]]),
        )
        for r in _read("jobsdb_classifications.json")
    ]


def _linkedin_district():
    data = _read("linkedin_geo.json")
    reverse: dict[str, list[str]] = {}
    for alias, district in (data.get("aliases") or {}).items():
        reverse.setdefault(district, []).append(alias)
    return [
        OptionEntry(
            id=str(v.get("geoUrn") or ""),
            name=zh_name,
            aliases=_uniq([v.get("en", ""), v.get("displayName", ""),
                           *reverse.get(zh_name, [])]),
        )
        for zh_name, v in (data.get("districts") or {}).items()
    ]


def _recruit_district():
    return [
        OptionEntry(
            id=str(r["id"]),
            name=r.get("zh") or r.get("name", ""),
            aliases=_uniq([*(r.get("aliases") or []), r.get("zh", ""), r.get("name", "")]),
        )
        for r in _read("recruit_districts.json")
    ]


def _recruit_category():
    return [
        OptionEntry(
            id=str(r.get("cat_id") or r["id"]),
            name=r.get("name", ""),
            aliases=_uniq([*(r.get("aliases") or []), r.get("zh", "")]),
        )
        for r in _read("recruit_categories.json")
    ]


def _jobmarket_dimension(filename: str):
    return [
        OptionEntry(
            id=str(r["id"]),
            name=r.get("zh") or r.get("name", ""),
            aliases=_uniq([*(r.get("aliases") or []), r.get("name", "")]),
        )
        for r in _read(filename)
    ]


def _foundit_district():
    return [
        OptionEntry(id=r["id"], name=r.get("name", ""),
                    aliases=_uniq(r.get("aliases") or []))
        for r in _read("foundit_locations.json")["locations"]
    ]


def _efc_district():
    return [
        OptionEntry(
            id=r["id"],
            name=r.get("name_zh") or r.get("name", ""),
            aliases=_uniq([r.get("name", ""), *(r.get("aliases") or [])]),
        )
        for r in _read("efc_geo.json")["locations"]
    ]


def _liepin_district():
    data = _read("liepin_areas.json")
    return [
        OptionEntry(
            id=None,
            name=v.get("zh_hant") or key,
            aliases=_uniq([key, v.get("en", ""), *(v.get("aliases") or [])]),
        )
        for key, v in (data.get("districts") or {}).items()
    ]


def _offertoday_dimension(filename: str, list_key: str):
    out: list[OptionEntry] = []
    for row in _read(filename)[list_key]:
        parent_id = str(row["id"])
        out.append(OptionEntry(
            id=parent_id,
            name=row.get("name", ""),
            aliases=_uniq([row.get("name_en", "")]),
        ))
        for child in row.get("children") or []:
            out.append(OptionEntry(
                id=str(child["id"]),
                name=child.get("name", ""),
                aliases=_uniq([child.get("name_en", "")]),
                parent_id=parent_id,
            ))
    return out


_LOADERS: dict[tuple[str, str], Callable[[], list[OptionEntry]]] = {
    ("moovup", "district"): _moovup_district,
    ("gov_hk", "district"): lambda: _simple_pairs("gov_hk_districts.json"),
    ("gov_hk", "category"): lambda: _simple_pairs("gov_hk_categories.json"),
    ("gov_hk", "industry"): lambda: _simple_pairs("gov_hk_industries.json"),
    ("jobsdb", "district"): _jobsdb_district,
    ("jobsdb", "category"): _jobsdb_category,
    ("linkedin", "district"): _linkedin_district,
    ("recruit", "district"): _recruit_district,
    ("recruit", "category"): _recruit_category,
    ("jobmarket", "district"): lambda: _jobmarket_dimension("jobmarket_districts.json"),
    ("jobmarket", "category"): lambda: _jobmarket_dimension("jobmarket_categories.json"),
    ("jobmarket", "industry"): lambda: _jobmarket_dimension("jobmarket_industries.json"),
    ("foundit", "district"): _foundit_district,
    ("efc", "district"): _efc_district,
    ("liepin", "district"): _liepin_district,
    ("offertoday", "district"): lambda: _offertoday_dimension("offertoday_areas.json", "districts"),
    ("offertoday", "category"): lambda: _offertoday_dimension("offertoday_categories.json", "categories"),
    ("offertoday", "industry"): lambda: _offertoday_dimension("offertoday_industries.json", "industries"),
}

_DIM_META: dict[tuple[str, str], tuple[str, list[str]]] = {
    ("moovup", "district"): ("single", ["zh", "en", "shortCode"]),
    ("gov_hk", "district"): ("single", ["id", "name"]),
    ("gov_hk", "category"): ("single", ["id", "name"]),
    ("gov_hk", "industry"): ("single", ["id", "name"]),
    ("jobsdb", "district"): ("single", ["zh", "slug"]),
    ("jobsdb", "category"): ("single", ["zh", "en", "slug"]),
    ("linkedin", "district"): ("single", ["zh", "en", "alias"]),
    ("recruit", "district"): ("multi", ["id", "en", "zh", "alias"]),
    ("recruit", "category"): ("single", ["id", "en", "zh", "alias"]),
    ("jobmarket", "district"): ("multi", ["id", "zh", "en", "alias"]),
    ("jobmarket", "category"): ("single", ["id", "zh", "en", "alias"]),
    ("jobmarket", "industry"): ("single", ["id", "zh", "en", "alias"]),
    ("foundit", "district"): ("single", ["slug", "en", "zh"]),
    ("efc", "district"): ("single", ["en", "zh"]),
    ("liepin", "district"): ("single", ["zh", "en", "alias"]),
    ("offertoday", "district"): ("multi", ["id", "zh", "en"]),
    ("offertoday", "category"): ("single", ["id", "zh", "en"]),
    ("offertoday", "industry"): ("single", ["id", "zh", "en"]),
}

_FREE_DIMENSIONS = {("indeed", "district")}


def dimension_kinds() -> dict[str, str]:
    """給測試／文件用：列出每個 (source, dimension) 的 kind。"""
    return {f"{s}.{d}": meta[0] for (s, d), meta in _DIM_META.items()}


def load_dimension(source: str, dimension: str) -> dict | None:
    """回傳正規化維度；不支援回 None。"""
    info = SOURCES.get(source)
    if info is None:
        return None
    if dimension == "sort":
        if not info.sort_values:
            return None
        return {"kind": "enum", "values": list(info.sort_values)}
    if not info.supports.get(dimension, False):
        return None
    if (source, dimension) in _FREE_DIMENSIONS:
        return {"kind": "free", "accepts": ["free_text"], "count": 0, "values": []}

    entries = _LOADERS[(source, dimension)]()
    kind, accepts = _DIM_META[(source, dimension)]
    return {
        "kind": kind,
        "accepts": accepts,
        "count": len(entries),
        "values": [
            {
                "id": e.id,
                "name": e.name,
                "aliases": list(e.aliases),
                "parentId": e.parent_id,
            }
            for e in entries
        ],
    }
