#!/usr/bin/env python3
"""에셋 매니페스트 + 이미지 생성 프롬프트 자동 생성 (완전판 11장).

출력
  assets/ASSET_MANIFEST.json   필요한 모든 에셋 경로·규격·용도·존재 여부 (게임은 없으면 절차적 대체)
  assets/PROMPTS.csv           유물·아이템 아이콘용 Imagen/AI Studio 프롬프트 (11.2 템플릿 자동 치환)
  assets/**/                   폴더 구조(.gitkeep)
사용: python3 tools/gen_asset_manifest.py
"""
import csv
import json
from pathlib import Path

from common import DATA, ROOT, load

ASSETS = ROOT / "assets"

SPEC = {
    "region_map":  {"size": "3840x2160", "format": "PNG 8-bit(팔레트) 무손실", "import": "Lossless, Filter Linear, Mipmaps off"},
    "region_mask": {"size": "3840x2160 (지도와 1:1)", "format": "PNG 24-bit RGB", "import": "Lossless, Filter Nearest, Mipmaps off, sRGB off",
                    "channels": "R: 0–31 통행불가 · 32–95 수계 · 96–191 산악/고개 · 192–255 관로/평지 | G: 위험도 0–255 | B: ≥128 나루·도하 지점"},
    "overworld":   {"size": "1400x2000 권장(세로형 한반도)", "format": "PNG", "import": "Lossless"},
    "parallax":    {"size": "1920x720 가로 심리스(좌우 끝 연결)", "format": "PNG 32-bit(투명 상단)", "import": "Lossless, Repeat Enabled"},
    "sprite":      {"size": "프레임 128x128, 가로 배열 8프레임(1024x128)", "format": "PNG 32-bit 투명", "import": "Lossless, Filter Nearest(도트) 또는 Linear(수묵)"},
    "portrait":    {"size": "512x640 (HUD 210x240 · 전투 84x84 로 축소)", "format": "PNG 32-bit", "import": "Lossless"},
    "icon":        {"size": "256x256 정사각, 단색 한지 배경", "format": "PNG 32-bit", "import": "Lossless, Mipmaps on"},
    "marker":      {"size": "64x64", "format": "PNG 32-bit 투명", "import": "Lossless"},
    "ui_9patch":   {"size": "64x64 ~ 512x512 9-패치(여백 24px)", "format": "PNG 32-bit", "import": "Lossless"},
    "battle_bg":   {"size": "1920x720", "format": "PNG/WebP", "import": "Lossless"},
    "minigame":    {"size": "1024x1024(슬라이딩 원본) / 1600x1000(탁본 판목)", "format": "PNG", "import": "Lossless"},
}

PROMPT = ("A museum-quality historical artifact illustration of {name_kr} ({category_sub}), crafted from {material}, dating back to {era} "
          "Joseon Dynasty. Traditional Korean ink-and-wash painting style, subtle watercolor shading on authentic Hanji paper texture "
          "background, ambient occlusion, square 1:1 composition, game asset icon format, highly detailed, clean edges, centered --ar 1:1 --style raw")
CAT_SUB = {"weapon": ("Ceremonial Sword", "Forged Steel with Gold Inlay"), "armor": ("Lamellar Armor", "Iron Scales and Leather"),
           "shoes": ("Traditional Boots", "Leather and Silk"), "accessory": ("Talisman Ornament", "Gilt Bronze and Silk Tassel"),
           "book": ("Ancient Historical Manuscript", "Mulberry Hanji Paper & Ink"), "record": ("Hanging Scroll Travelogue", "Hanji Scroll with Wooden Rollers"),
           "specialty": ("Crafted Specialty Goods", "Traditional Handcraft Materials"), "recipe": ("Secret Craft Manual", "Stitched Hanji Book"),
           "herb": ("Medicinal Herb", "Dried Herbal Plant"), "food": ("Traditional Korean Dish", "Brassware and Porcelain Bowl"),
           "capture": ("Capture Tool", "Hemp Rope, Beads or Talisman Paper"), "mount": ("Mount Portrait", "Living Animal"), "material": ("Craft Raw Material", "Natural Material")}
ERA = {1: "Late", 2: "Late", 3: "Mid", 4: "Mid", 5: "Early"}


def entry(path, kind, use, ref=""):
    p = path.replace("res://", "")
    return {"path": path, "kind": kind, "spec": SPEC[kind], "use": use, "ref": ref, "exists": (ROOT / p).exists()}


def main():
    reg = load("regions.json")
    out = []
    for r in reg["regions"]:
        rid = r["id"].lower()
        out.append(entry(r["map_texture"], "region_map", f"{r['name']} 대동여지도 목판 텍스처(노드 좌표는 임시 — 제작 후 data_src 좌표 갱신)", r["id"]))
        out.append(entry(r["mask_texture"], "region_mask", f"{r['name']} 지형 판정 마스크", r["id"]))
        for layer, desc in (("far", "원경 산맥"), ("mid", "중경 숲·구릉"), ("near", "근경 길·돌담")):
            out.append(entry(f"{r['parallax_dir']}{layer}.png", "parallax", f"{r['name']} 패럴랙스 {desc}(수묵 담채)", r["id"]))
        out.append(entry(f"res://assets/battle/bg_{rid}.png", "battle_bg", f"{r['name']} 전투 배경", r["id"]))
    out.append(entry("res://assets/maps/overworld.png", "overworld", "전국 17권역 조망 지도", ""))
    for t in ["city", "town", "station", "temple", "spring", "fort", "beacon", "stupa", "tomb", "scenic", "wreck", "ruin", "seowon", "shrine", "hazard"]:
        out.append(entry(f"res://assets/ui/markers/{t}.png", "marker", f"노드 마커({t})", t))
    for c in load("19_classes_knowledge.json")["classes"]:
        cid = c["id"]
        out.append(entry(f"res://assets/portraits/hero_{cid}.png", "portrait", f"주인공 {c['name']} 수묵 초상", cid))
        out.append(entry(f"res://assets/ui/class/{cid}.png", "icon", f"{c['name']} 직업 아이콘(48px 표시)", cid))
        for anim in ("walk", "idle"):
            out.append(entry(f"res://assets/characters/hero_{cid}/{anim}.png", "sprite", f"주인공 {c['name']} {anim}", cid))
    for c in load("13_companions.json")["companions"]:
        out.append(entry(f"res://assets/portraits/{c['id']}.png", "portrait", f"동료 {c['name']}", c["id"]))
        out.append(entry(f"res://assets/characters/{c['id']}/walk.png", "sprite", f"동료 {c['name']} 보행", c["id"]))
    for e in load("12_enemies.json")["enemies"]:
        out.append(entry(f"res://assets/portraits/{e['id']}.png", "portrait", f"적 {e['name']} (전투 슬롯)", e["id"]))
    for s in load("18_status_effects.json")["battle"]:
        out.append(entry(f"res://assets/ui/status/{s['id']}.png", "marker", f"상태이상 {s['name']}", s["id"]))
    for r in range(1, 6):
        out.append(entry(f"res://assets/ui/seals/rank_{r}.png", "marker", f"신분 {r}등급 인장", str(r)))
    for name, use in (("modal", "모달 패널(한지+놋쇠)"), ("dashboard_frame", "하단 대시보드 프레임 1920x360")):
        out.append(entry(f"res://assets/ui/panels/{name}.png", "ui_9patch", use, name))
    out.append(entry("res://assets/icons/common/icon_scroll_jokja.png", "icon", "두루마기 족자 답사록 공통 아이콘", "record"))
    for m in load("21_minigames.json")["minigames"]:
        img = m.get("params", {}).get("image")
        if img:
            out.append(entry(img, "minigame", f"{m['name']} 원본 그림", m["id"]))
    for n in range(1, 23):
        out.append(entry(f"res://assets/minigames/takbon/sheet_{n:02d}.png", "minigame", f"대동여지도 제{n}첩 판목(탁본)", str(n)))

    prompts = []
    def icon(id_, name, cat, tier, path):
        out.append(entry(path, "icon", f"{name} 아이콘", id_))
        sub, mat = CAT_SUB[cat]
        prompts.append({"id": id_, "path": path, "name_kr": name, "category_sub": sub, "material": mat, "era": ERA.get(tier, "Late"),
                        "prompt": PROMPT.format(name_kr=name, category_sub=sub, material=mat, era=ERA.get(tier, "Late"))})
    for h in load("01_heritage.json")["heritage"]:
        icon(h["id"], h["name"], {"architecture": "record", "scenic": "record", "ceramic_specialty": "specialty", "folk_craft": "accessory",
                                  "metal": "weapon", "document": "book"}[h["category"]], h["tier"], f"res://assets/icons/heritage/{h['id']}.png")
    for fn, key, cat in (("02_equipment.json", "items", None), ("06_life_gear.json", "life_gear", "record"), ("07_mounts.json", "mounts", "mount"),
                         ("08_capture_tools.json", "tools", "capture"), ("09_herbal_recipes.json", "recipes", "herb"), ("10_herbs.json", "herbs", "herb"),
                         ("11_food_recipes.json", "recipes", "food"), ("15_recipe_books.json", "books", "recipe"), ("16_mojak_gear.json", "mojak", None),
                         ("05_materials.json", "materials", "material"), ("04_food_staples.json", "foods", "food")):
        for it in load(fn)[key]:
            if it.get("icon"):
                continue  # 공통 아이콘 사용(답사록)
            c = cat or it.get("slot", "accessory")
            icon(it["id"], it["name"], c if c in CAT_SUB else "accessory", it.get("tier", 1), f"res://assets/icons/items/{it['id']}.png")
    sp = load("03_specialties.json")
    for it in sp["specialties"]:
        icon(it["id"], it["name"], "specialty", it["tier"], f"res://assets/icons/items/{it['id']}.png")
    for it in sp["specialty_recipes"]:
        icon(it["id"], it["name"], "recipe", it["tier"], f"res://assets/icons/items/{it['id']}.png")

    for e in out:
        d = ROOT / Path(e["path"].replace("res://", "")).parent
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()
    have = sum(1 for e in out if e["exists"])
    kinds = {}
    for e in out:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    (ASSETS / "ASSET_MANIFEST.json").write_text(json.dumps({
        "_about": "tools/gen_asset_manifest.py 생성. 게임은 파일이 없으면 절차적 그리기로 대체하므로 어떤 순서로 넣어도 된다. 규격은 spec, 경로는 path 그대로.",
        "summary": {"total": len(out), "present": have, "by_kind": kinds}, "specs": SPEC, "assets": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(ASSETS / "PROMPTS.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "path", "name_kr", "category_sub", "material", "era", "prompt"])
        w.writeheader()
        w.writerows(prompts)
    print(f"매니페스트 {len(out)}건 (보유 {have}) · 프롬프트 {len(prompts)}건 · 종류 {kinds}")


if __name__ == "__main__":
    main()
