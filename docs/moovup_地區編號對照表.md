# Moovup 地區編號對照表

> 📌 **適用範圍備註**：本對照表**僅針對 Moovup 好工速遞（moovup.com）** 單一網站。
> 其他求職網站（gov.hk / JobsDB / LinkedIn / Indeed）的地區編號體系不同，不適用本表。
> 程式內部資料：`scrapers/moovup_districts.json`（與本表內容一致，供爬蟲載入）。

> 來源：Moovup 前端 JS bundle（`00c111a.modern.js` 等）。
> 已實測：`shortCode` 與 `_id` 皆可作為 GraphQL `district` 過濾值。
> CLI 用法：`python main.py --source moovup --keyword 會計 --district 深水埗`
> 地區可用「中文名 / 英文名 / shortCode」指定，多個以逗號分隔。

共 32 個地區。

## 香港島

| 中文名 | 英文名 | shortCode | _id |
|--------|--------|-----------|-----|
| 中區 | Central | 000006 | `1d09ae94-3797-4166-9a4f-e3c9932d8f00` |
| 灣仔 / 銅鑼灣 | Wan Chai / Causeway Bay | 000007 | `c4522f49-d6f4-4a85-a65f-0c9ecfd15279` |
| 半山 / 山頂 | Mid-Levels & Peak | 000008 | `23ae6d02-e7ab-4ea4-a5f9-98a7c01ce06d` |
| 港島西 | Island West | 000009 | `d9eefd02-1d1d-4456-89e4-8bff7cfa62cb` |
| 薄扶林 | Pok Fu Lam | 000010 | `879d7821-b180-4852-8d55-b62d288c89a9` |
| 香港仔 | Aberdeen | 000011 | `69e07902-e089-4d3a-9b90-37d8f0e942f3` |
| 港島東 | Island East | 000012 | `f27f4613-077b-4c13-bc13-b75848887a57` |
| 港島南 | Island South | 000013 | `dc7bc95e-182e-4594-909d-18e3c6f9a610` |

## 九龍

| 中文名 | 英文名 | shortCode | _id |
|--------|--------|-----------|-----|
| 油尖旺 | Yau Tsim Mong | 000014 | `25e38c34-43eb-40eb-852f-2ccc1b438087` |
| 紅磡 | Hunghom | 000015 | `0b70e127-865d-45e3-9c42-8eb3a98eb5b7` |
| 西九龍 | West Kowloon | 000016 | `b225f834-fda0-4e64-aeee-a6893108b4f1` |
| 深水埗 | Sham Shui Po | 000017 | `37ddc1e5-f7c0-4121-84af-84a7f602adf6` |
| 美孚 | Mei Foo | 000018 | `9dd9e458-5d4a-4221-b570-e8a99187d83f` |
| 九龍塘 | Kowloon Tong | 000019 | `fd7091fc-08e4-4a9e-a248-2f940444021b` |
| 九龍城 | Kowloon City | 000020 | `0976e47c-9855-4e6e-8a27-f245c16f2e82` |
| 黃大仙 | Wong Tai Sin | 000021 | `fc3849e7-0b87-4fc1-bbee-450458735389` |
| 九龍灣 | Kowloon Bay | 000022 | `d274c0d9-1648-4cd6-84f3-a33676cc192b` |
| 觀塘 | Kwun Tong | 000023 | `3f2347a5-f705-4c3d-9969-1bd368efc9ff` |

## 新界東

| 中文名 | 英文名 | shortCode | _id |
|--------|--------|-----------|-----|
| 將軍澳 | Tseung Kwan O | 000024 | `cef000e4-0307-4324-b6cf-fb2af0c8887f` |
| 西貢 | Sai Kung | 000025 | `f83df9d5-6655-46f4-887f-3b30fe1c62ad` |
| 沙田 | Shatin | 000026 | `f17ee2fa-e153-4e9c-bdb5-ea9dc3534cb9` |
| 馬鞍山 | Ma On Shan | 000027 | `a795fc5d-1fa0-4898-8cbd-d65e09a3a7ed` |
| 大埔 | Tai Po | 000028 | `63eb31bc-fc1d-4436-8b50-18bb90bf3be9` |
| 粉嶺 & 上水 | Fanling & Sheung Shui | 000029 | `c555aebf-0ee6-4789-8dca-d1dce37d2b73` |

## 新界西

| 中文名 | 英文名 | shortCode | _id |
|--------|--------|-----------|-----|
| 葵涌 | Kwai Chung | 000030 | `8baa7f7b-9d2c-4347-be15-af812c11088e` |
| 青衣 | Tsing Yi | 000031 | `19d69cc1-1c6d-4b78-905d-0c326a95eba1` |
| 荃灣 | Tsuen Wan | 000032 | `4c2aac41-a5ba-43d2-a9a0-7b3cf2ca94d9` |
| 屯門 | Tuen Mun | 000033 | `def5f7ab-0526-40d4-b9d5-8facc88dd355` |
| 天水圍 | Tin Shui Wai | 000034 | `0e165f23-94c3-450f-82c7-a8d1429b0391` |
| 元朗 | Yuen Long | 000035 | `2aa8d2db-f267-47f4-beec-97b731a4c984` |

## 大嶼山

| 中文名 | 英文名 | shortCode | _id |
|--------|--------|-----------|-----|
| 東涌 & 機場 | Tung Chung and Airport | 000036 | `9d22456e-9bef-4f23-bb79-c843b984d1f2` |
| 愉景灣 & 迪士尼 | DBay & Disney | 000037 | `db063c1b-6688-421a-9986-5f75ccb9e9b7` |
