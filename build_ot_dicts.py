# -*- coding: utf-8 -*-
"""從 R4 快取的 filter/content/all 建立 OfferToday 三套字典（離線，不打任何請求）。

來源：output/_ot_filter_content_all.json（data.tc 中文 / data.en 英文）
編碼規則：
  - 地區：s<區碼>c<子區碼>     例 sHK101304cHK101304104 = 元朗區・天水圍
  - 職能：<大類碼>c<細類碼>    例 118000c118003 = 資訊科技・電腦操作員
  - 行業：<大類碼>c<細類碼>
"""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")

SRC = "output/_ot_filter_content_all.json"
d = json.load(open(SRC, encoding="utf-8"))
tc, en = d["data"]["tc"], d["data"]["en"]


def flat(node, out):
    """扁平化樹（跳過根節點）"""
    for c in node.get("children") or []:
        out.append({"code": c["code"], "name": c["name"],
                    "parent": c.get("parentCode"), "level": c.get("level")})
        flat(c, out)
    return out


def en_map(node, out):
    """英文樹 → code → name"""
    for c in node.get("children") or []:
        out[c["code"]] = c["name"]
        en_map(c, out)
    return out


EN_AREA = en_map(en["AREA"], {})
EN_POS = en_map(en["POSITION"], {})
EN_IND = en_map(en["INDUSTRY"], {})

# ---------- 1) 地區 ----------
areas = []
for dist in tc["AREA"]["children"]:
    dcode, dname = dist["code"], dist["name"]
    subs = []
    for s in dist["children"]:
        if s["code"] == dcode:          # 跳過「所有 XX」節點
            continue
        subs.append({
            "id": f"s{dcode}c{s['code']}",
            "name": s["name"],
            "name_en": EN_AREA.get(s["code"], ""),
            "district": dname,
        })
    areas.append({
        "id": dcode,
        "name": dname,
        "name_en": EN_AREA.get(dcode, ""),
        "sub_count": len(subs),
        "children": subs,
    })

# ---------- 2) 職能 ----------
cats = []
for big in tc["POSITION"]["children"]:
    bcode, bname = big["code"], big["name"]
    subs = []
    for s in big["children"]:
        if s["code"] == bcode:
            continue
        subs.append({"id": f"{bcode}c{s['code']}", "name": s["name"],
                     "name_en": EN_POS.get(s["code"], ""), "category": bname})
    cats.append({"id": bcode, "name": bname, "name_en": EN_POS.get(bcode, ""),
                 "sub_count": len(subs), "children": subs})

# ---------- 3) 行業 ----------
inds = []
for big in tc["INDUSTRY"]["children"]:
    bcode, bname = big["code"], big["name"]
    subs = []
    for s in big["children"]:
        if s["code"] == bcode:
            continue
        subs.append({"id": f"{bcode}c{s['code']}", "name": s["name"],
                     "name_en": EN_IND.get(s["code"], ""), "industry": bname})
    inds.append({"id": bcode, "name": bname, "name_en": EN_IND.get(bcode, ""),
                 "sub_count": len(subs), "children": subs})

# ---------- 4) 其他篩選枚舉 ----------
enums = {
    "job_publish_time": tc["JOB_PUBLISH_TIME"],   # 0=今天 1=3天 2=7天 3=14天
    "edu_level": tc["EDU_LEVEL"],
    "employment_type": tc["EMPLOYMENT_TYPE"],
    "salary_type": tc["SALARY_TYPE"],
    "work_experience": tc["WORK_EXPERIENCE_PORTFOLIO"],
    "work_permit": tc["WORK_PERMIT_DESC"],
}

json.dump({"source": "offertoday",
           "note": "地區字典：香港 18 行政區 + 子區。id 為送給站方的 locationCode（s<區碼>c<子區碼>）；"
                   "只給區碼（如 HK101304）代表全區。來源 /wapi/geek/recommend/filter/content/all。",
           "districts": areas},
          open("scrapers/offertoday_areas.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

json.dump({"source": "offertoday",
           "note": "職能字典：31 大類 + 細類。id 格式 <大類碼>c<細類碼>，只給大類碼代表全類。",
           "categories": cats},
          open("scrapers/offertoday_categories.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

json.dump({"source": "offertoday",
           "note": "行業字典：15 大類 + 細類。id 格式 <大類碼>c<細類碼>。",
           "industries": inds,
           "enums": enums},
          open("scrapers/offertoday_industries.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

n_sub_area = sum(a["sub_count"] for a in areas)
n_sub_cat = sum(c["sub_count"] for c in cats)
n_sub_ind = sum(i["sub_count"] for i in inds)
print(f"offertoday_areas.json      : {len(areas)} 區 / {n_sub_area} 子區")
print(f"offertoday_categories.json : {len(cats)} 大類 / {n_sub_cat} 細類")
print(f"offertoday_industries.json : {len(inds)} 大類 / {n_sub_ind} 細類 + 6 組枚舉")
print()
print("元朗區子區：", ", ".join(f"{c['name']}={c['id']}" for c in
      next(a for a in areas if a["name"] == "元朗")["children"][:5]), "...")
