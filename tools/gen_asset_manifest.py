#!/usr/bin/env python3
"""에셋 매니페스트 + 이미지 생성 프롬프트 자동 생성 (완전판 11장).

출력
  assets/ASSET_MANIFEST.json   필요한 모든 에셋 경로·규격·용도·존재 여부 (게임은 없으면 절차적 대체)
  assets/PROMPTS.csv           유물·아이템 아이콘 프롬프트 (구 형식 호환, 11.2 템플릿)
  assets/prompts/<batch>.csv   종류별 배치 프롬프트 (스타일 공통 문구 + 복식 고증 + negative) — tools/prompt_lib.py
  assets/**/                   폴더 구조(.gitkeep)
사용: python3 tools/gen_asset_manifest.py
"""
import csv
import json
from pathlib import Path

from common import DATA, ROOT, load
import prompt_lib as PL

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
    "scene":       {"size": "1920x1080 (대화 배경, 하단 300px 은 대화창에 가려짐)", "format": "PNG/WebP", "import": "Lossless"},
}
SCENE_DESC = {"city": "a walled Joseon provincial town with a government office gate and market street", "town": "a small Joseon village with thatched houses and a big zelkova tree",
              "station": "a Joseon post-horse relay station with stables", "temple": "a Korean Buddhist mountain temple courtyard with a stone pagoda",
              "spring": "a Joseon hot-spring inn with steam rising", "fort": "a Joseon mountain fortress wall and gate tower", "beacon": "a stone beacon-fire mound on a ridge",
              "stupa": "an old stone pagoda standing in a temple ruin", "tomb": "a royal burial mound with stone guardian statues", "scenic": "a famous Korean scenic landscape of cliffs and pines",
              "wreck": "a tidal mudflat coast with fishing boats and old ship timbers", "ruin": "an overgrown site of old foundation stones and broken kiln shards",
              "seowon": "a Confucian academy lecture hall with a pavilion", "shrine": "a village shaman shrine under a sacred tree with straw ropes", "hazard": "a steep mountain pass trail"}
NPC_BUST = {"official": ("아전", "civil_official"), "monk": ("노승", "monk"), "elder": ("촌로", "laborer"), "soldier": ("군관·역졸", "military"),
            "merchant": ("객주·장인", "merchant"), "shaman": ("무녀", "shaman"), "scholar": ("유생", "scholar"), "fisher": ("어부·뱃사람", "boatman"),
            "innkeeper": ("주모", "innkeeper"), "traveler": ("유람객", "scholar")}

PROMPT = ("A museum-quality historical artifact illustration of {name_kr} ({category_sub}), crafted from {material}, dating back to {era} "
          "Joseon Dynasty. " + PL.STYLE_COMMON + ", " + PL.KIND_TAIL["icon"][0])
BATCH = {}   # batch 이름 → 행 목록


def bp(batch, kind, id_, path, name, body, costume_key=None, **extra):
    """배치 프롬프트 1행: 본문 + 복식 고증 + 공통 스타일 + 규격 꼬리 / negative."""
    tail, neg = PL.KIND_TAIL[kind]
    cos = PL.COSTUME.get(costume_key, "") if costume_key else ""
    prompt = ", ".join(x for x in (body, cos, PL.STYLE_COMMON, tail) if x)
    BATCH.setdefault(batch, []).append({"id": id_, "path": path, "kind": kind, "name_kr": name, "costume": costume_key or "",
                                        "prompt": prompt, "negative": PL.NEG_COMMON + ", " + neg, **extra})
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
        scene, air = PL.REGION_SCENE.get(r["id"], r["name"]), PL.CLIMATE.get(r.get("climate"), "")
        bp("maps", "region_map", r["id"], r["map_texture"], r["name"], f"regional map of {scene}",
           guide=f"assets/maps/guides/{rid}_relief.png (ControlNet lineart/canny) + {rid}_height.png (depth)")
        for layer, what in (("far", "distant layered mountain ridges"), ("mid", "rolling hills with pine groves and thatched villages"),
                            ("near", "roadside stone walls, jangseung totems and wild grass")):
            bp("parallax", "parallax", f"{r['id']}_{layer}", f"{r['parallax_dir']}{layer}.png", f"{r['name']} {layer}", f"{what} of {scene}, {air}")
        bp("battle_bg", "battle_bg", r["id"], f"res://assets/battle/bg_{rid}.png", r["name"], f"open field battleground in {scene}, {air}")
    out.append(entry("res://assets/maps/overworld.png", "overworld", "전국 17권역 조망 지도", ""))
    bp("maps", "overworld", "overworld", "res://assets/maps/overworld.png", "전국 조망", "map of the Korean peninsula")
    for t in ["city", "town", "station", "temple", "spring", "fort", "beacon", "stupa", "tomb", "scenic", "wreck", "ruin", "seowon", "shrine", "hazard"]:
        out.append(entry(f"res://assets/ui/markers/{t}.png", "marker", f"노드 마커({t})", t))
        bp("markers", "marker", f"marker_{t}", f"res://assets/ui/markers/{t}.png", t, f"map marker symbol for a {t} site on a Joseon map")
    for t, desc in SCENE_DESC.items():   # 대화 배경(노드 유형) — 노드 전용 삽화는 res://assets/scenes/nodes/<노드 id>.png 로 덮어쓰기
        out.append(entry(f"res://assets/scenes/{t}.png", "scene", f"대화 배경({t})", t))
        bp("scenes", "scene", f"scene_{t}", f"res://assets/scenes/{t}.png", t, desc + ", Joseon 1861")
    for role, (ko, ck) in NPC_BUST.items():  # 대화 NPC 상반신(역할별 공용)
        out.append(entry(f"res://assets/portraits/npc_{role}.png", "portrait", f"대화 NPC {ko} 상반신", role))
        bp("portraits_npc", "portrait", f"npc_{role}", f"res://assets/portraits/npc_{role}.png", ko, f"half-length portrait of a Joseon {role} ({ko}), friendly, speaking", ck)
    story = load("24_story.json") if (DATA / "24_story.json").exists() else {}
    for hid, v in sorted(story.get("mg_variants", {}).items()):  # 유산별 슬라이딩 원본(없으면 카탈로그 기본 그림)
        img = v.get("params", {}).get("image", "")
        if img.startswith("res://assets/minigames/heritage/"):
            h = next((x for x in load("01_heritage.json")["heritage"] if x["id"] == hid), {})
            out.append(entry(img, "minigame", f"{h.get('name', hid)} 조각 맞추기 원본", hid))
            bp("minigames_heritage", "minigame", hid, img, h.get("name", hid), f"frontal illustration of the Korean heritage artifact {h.get('name', hid)}")
    for c in load("19_classes_knowledge.json")["classes"]:
        cid = c["id"]
        out.append(entry(f"res://assets/portraits/hero_{cid}.png", "portrait", f"주인공 {c['name']} 수묵 초상", cid))
        out.append(entry(f"res://assets/ui/class/{cid}.png", "icon", f"{c['name']} 직업 아이콘(48px 표시)", cid))
        ck = PL.HERO_COSTUME.get(cid)
        bp("portraits_hero", "portrait", f"hero_{cid}", f"res://assets/portraits/hero_{cid}.png", c["name"], f"protagonist, a young Joseon {c['name']} traveller of 1861", ck)
        for anim in ("walk", "idle"):
            out.append(entry(f"res://assets/characters/hero_{cid}/{anim}.png", "sprite", f"주인공 {c['name']} {anim}", cid))
            bp("sprites", "sprite", f"hero_{cid}_{anim}", f"res://assets/characters/hero_{cid}/{anim}.png", f"{c['name']} {anim}",
               f"young Joseon {c['name']} traveller, {'walking' if anim == 'walk' else 'idle breathing'} animation", ck)
    for sc in load("23_tutorial.json")["scenarios"]:
        out.append(entry(sc["portrait"], "portrait", f"시나리오 주인공 {sc['hero_name']} 수묵 초상", sc["id"]))
        bp("portraits_hero", "portrait", sc["id"], sc["portrait"], sc["hero_name"],
           f"portrait of {sc.get('prompt_who', sc['hero_name'])}", sc.get("costume"))
    for c in load("13_companions.json")["companions"]:
        out.append(entry(f"res://assets/portraits/{c['id']}.png", "portrait", f"동료 {c['name']}", c["id"]))
        out.append(entry(f"res://assets/characters/{c['id']}/walk.png", "sprite", f"동료 {c['name']} 보행", c["id"]))
        ck = PL.COMPANION_COSTUME.get(c["name"])
        if ck is None:
            raise SystemExit(f"복식 고증 누락: {c['name']} → tools/prompt_lib.py COMPANION_COSTUME 에 추가")
        era = c.get("era", "")
        who = f"{c['name']}, {c.get('category', '')} ({era})"
        bp("portraits_companion", "portrait", c["id"], f"res://assets/portraits/{c['id']}.png", c["name"], f"portrait of {who}", ck, era=era)
        bp("sprites", "sprite", f"{c['id']}_walk", f"res://assets/characters/{c['id']}/walk.png", f"{c['name']} walk", f"{who}, walking animation", ck, era=era)
    for e in load("12_enemies.json")["enemies"]:
        out.append(entry(f"res://assets/portraits/{e['id']}.png", "portrait", f"적 {e['name']} (전투 슬롯)", e["id"]))
        bp("portraits_enemy", "portrait", e["id"], f"res://assets/portraits/{e['id']}.png", e["name"],
           PL.ENEMY_DESC.get(e["id"], e["name"]) + ", menacing, battle portrait", None, enemy_kind=e["kind"])
    for s in load("18_status_effects.json")["battle"]:
        out.append(entry(f"res://assets/ui/status/{s['id']}.png", "marker", f"상태이상 {s['name']}", s["id"]))
        bp("markers", "marker", f"status_{s['id']}", f"res://assets/ui/status/{s['id']}.png", s["name"], f"status effect symbol meaning '{s['name']}'")
    for r in range(1, 6):
        out.append(entry(f"res://assets/ui/seals/rank_{r}.png", "marker", f"신분 {r}등급 인장", str(r)))
        bp("markers", "marker", f"rank_{r}", f"res://assets/ui/seals/rank_{r}.png", f"{r}등급 인장", f"red cinnabar square seal impression, rank {r} of 5, {r} ornamental borders")
    for name, use in (("modal", "모달 패널(한지+놋쇠)"), ("dashboard_frame", "하단 대시보드 프레임 1920x360"), ("dialogue", "대화창 패널 1840x290(9-패치)")):
        out.append(entry(f"res://assets/ui/panels/{name}.png", "ui_9patch", use, name))
    out.append(entry("res://assets/icons/common/icon_scroll_jokja.png", "icon", "두루마기 족자 답사록 공통 아이콘", "record"))
    for m in load("21_minigames.json")["minigames"]:
        img = m.get("params", {}).get("image")
        if img:
            out.append(entry(img, "minigame", f"{m['name']} 원본 그림", m["id"]))
            bp("minigames", "minigame", m["id"], img, m["name"], "Goryeo celadon maebyeong vase with inlaid cranes" if "celadon" in img else "ink landscape of Inwang mountain after rain")
    for n in range(1, 23):
        out.append(entry(f"res://assets/minigames/takbon/sheet_{n:02d}.png", "minigame", f"대동여지도 제{n}첩 판목(탁본)", str(n)))
        bp("minigames", "minigame", f"takbon_{n:02d}", f"res://assets/minigames/takbon/sheet_{n:02d}.png", f"제{n}첩 판목",
           f"carved pear-wood printing block of Daedongyeojido sheet {n}, relief carved mountains and rivers, ink residue, seen from above")

    prompts = []
    def icon(id_, name, cat, tier, path):
        out.append(entry(path, "icon", f"{name} 아이콘", id_))
        sub, mat = CAT_SUB[cat]
        prompts.append({"id": id_, "path": path, "name_kr": name, "category_sub": sub, "material": mat, "era": ERA.get(tier, "Late"),
                        "prompt": PROMPT.format(name_kr=name, category_sub=sub, material=mat, era=ERA.get(tier, "Late"))})
        bp(f"icons_{cat}", "icon", id_, path, name, f"museum-quality illustration of {name} ({sub}), made of {mat}, {ERA.get(tier, 'Late')} Joseon period",
           category_sub=sub, material=mat)
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
    pd = ASSETS / "prompts"
    pd.mkdir(exist_ok=True)
    for old in pd.glob("*.csv"):
        old.unlink()
    for name, rows in sorted(BATCH.items()):
        keys = list(dict.fromkeys(k for r in rows for k in r))
        with open(pd / f"{name}.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys, restval="")
            w.writeheader()
            w.writerows(rows)
    (pd / "README.md").write_text("# 배치 프롬프트 (자동 생성: tools/gen_asset_manifest.py · 문구 사전: tools/prompt_lib.py)\n\n"
        "모든 prompt = 본문 + 복식 고증(인물) + 공통 스타일 + 규격 꼬리. negative 열은 생성기의 negative prompt 칸에 넣는다.\n\n"
        f"공통 스타일: `{PL.STYLE_COMMON}`\n\n| 배치 | 건수 |\n|---|---|\n"
        + "".join(f"| {n}.csv | {len(r)} |\n" for n, r in sorted(BATCH.items())), encoding="utf-8")
    print(f"배치 프롬프트 {sum(len(r) for r in BATCH.values())}건 · {len(BATCH)}개 파일")
    print(f"매니페스트 {len(out)}건 (보유 {have}) · 프롬프트 {len(prompts)}건 · 종류 {kinds}")


if __name__ == "__main__":
    main()
