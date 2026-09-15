# -*- coding: utf-8 -*-
"""字典檔健檢（零請求）。

守兩條鐵律：
  1. **字典損毀不得拖垮全站** —— 任何字典載入失敗都要在這裡亮紅燈，
     而不是等到 `import scrapers` 炸掉（2026-08-19 修復的 major 級問題）。
  2. **字典不可跨站混用** —— 有 source 標記的字典必須與檔名所屬的站一致。

數量斷言對齊 README「各站功能支援矩陣」（2026-09 版）。數字變動代表字典
被動過，測試就會紅——這是刻意的，請確認後再更新此表。
"""
from __future__ import annotations

import glob
import json
import os
import unittest

_SCRAPERS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scrapers"
)

# 頂層為 list 的字典：檔名 -> 期望筆數
EXPECTED_LIST = {
    "gov_hk_districts.json": 27,
    "gov_hk_categories.json": 29,
    "gov_hk_industries.json": 27,
    "jobsdb_districts.json": 40,
    "jobsdb_classifications.json": 30,
    "recruit_districts.json": 94,
    "recruit_categories.json": 324,      # 34 大類 + 290 細類
    "jobmarket_districts.json": 80,      # 5 大區 + 75 子區
    "jobmarket_categories.json": 223,    # 28 大類 + 195 細類
    "jobmarket_industries.json": 30,
    "moovup_districts.json": 32,
}

# 頂層為 dict 的字典：檔名 -> (取值路徑, 期望筆數)
EXPECTED_NESTED = {
    "liepin_areas.json": (["districts"], 18),
    "linkedin_geo.json": (["districts"], 20),     # 18 區 + 香港/全港 2 個 fallback
    "offertoday_areas.json": (["districts"], 18),
    "offertoday_categories.json": (["categories"], 31),
    "offertoday_industries.json": (["industries"], 15),
    "foundit_locations.json": (["locations"], 46),
    "efc_geo.json": (["locations"], 3),
}


def _load(filename: str):
    with open(os.path.join(_SCRAPERS, filename), encoding="utf-8") as f:
        return json.load(f)


def _dig(obj, path: list[str]):
    for key in path:
        obj = obj[key]
    return obj


class TestDictionaryIntegrity(unittest.TestCase):
    def test_all_dict_files_load_and_are_non_empty(self):
        files = sorted(glob.glob(os.path.join(_SCRAPERS, "*.json")))
        self.assertGreaterEqual(len(files), 17, "字典檔數量異常減少")
        for path in files:
            with self.subTest(file=os.path.basename(path)):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self.assertTrue(data, f"{os.path.basename(path)} 為空")

    def test_list_dictionary_sizes(self):
        for name, expected in EXPECTED_LIST.items():
            with self.subTest(dict=name):
                data = _load(name)
                self.assertIsInstance(data, list)
                self.assertEqual(len(data), expected)

    def test_nested_dictionary_sizes(self):
        for name, (path, expected) in EXPECTED_NESTED.items():
            with self.subTest(dict=name):
                self.assertEqual(len(_dig(_load(name), path)), expected)


class TestNoCrossSiteContamination(unittest.TestCase):
    """鐵律 #2：字典不得跨站混用。有 source 標記者必須與檔名所屬站一致。"""

    def test_source_field_matches_filename(self):
        """有 source 標記者必須以檔名所屬的站名開頭。

        註：部分字典（如 linkedin_geo.json）的 source 是一整句來源敘述
        （"LinkedIn jobs-guest/api/... (2026-07-30 逆向)"），故比對前綴而非全等。
        """
        for name in EXPECTED_NESTED:
            data = _load(name)
            source = data.get("source") or (data.get("_meta") or {}).get("source")
            if not source:
                continue
            with self.subTest(dict=name):
                self.assertTrue(
                    str(source).lower().startswith(name.split("_")[0].lower()),
                    f"{name} 的 source 標記為 {source!r}，與所屬站不符，恐為跨站混用",
                )


class TestLiepinDistricts(unittest.TestCase):
    """獵聘簡繁別名回歸測試。

    2026-09-11 踩過：只列繁體「觀塘」時，打簡體「观塘」（獵聘自己的寫法）
    反而配對失敗。此後每個區都必須同時具備繁體名、英文名與別名。
    """

    def setUp(self):
        self.areas = _load("liepin_areas.json")

    def test_every_district_has_hant_english_and_aliases(self):
        for key, meta in self.areas["districts"].items():
            with self.subTest(district=key):
                self.assertTrue(meta.get("zh_hant"), f"{key} 缺繁體名")
                self.assertTrue(meta.get("en"), f"{key} 缺英文名")
                self.assertTrue(meta.get("aliases"), f"{key} 缺別名")

    def test_hong_kong_city_code_is_320(self):
        self.assertEqual(self.areas["city"]["香港"]["code"], "320")


if __name__ == "__main__":
    unittest.main()
