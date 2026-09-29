#!/usr/bin/env python3
"""체계형 시트 생성기.

- 02_장착아이템: 유·불·선 × 4부위 × 4·5등급 원본 장비(24종, generated=true) 재생성
- 08_포획구: 유(포승)·불(염주)·선(부적)·무(덫) × 1~5등급 = 20종
- 16_고유제작_전투장착(모작): 원본 스탯 × MOJAK_RATIO(0.70~0.80) = 24종

사용: python3 tools/gen_systematic.py
"""
from common import gear_stats, load, save

MOJAK_RATIO = 0.75
FAMILIES = {"yu": {"element": "metal"}, "bul": {"element": "holy"}, "seon": {"element": "fire"}}
NAMES = {
    ("yu", "weapon", 4): "사인참사검", ("yu", "weapon", 5): "용천 어검",
    ("yu", "armor", 4): "두석린갑", ("yu", "armor", 5): "용린 어갑",
    ("yu", "shoes", 4): "흑피 목화", ("yu", "shoes", 5): "청룡 목화",
    ("yu", "accessory", 4): "수군 청동인장", ("yu", "accessory", 5): "어보 옥인",
    ("bul", "weapon", 4): "금강저", ("bul", "weapon", 5): "항마 금강저",
    ("bul", "armor", 4): "승군 철가사", ("bul", "armor", 5): "사명 금란가사",
    ("bul", "shoes", 4): "행각 철혜", ("bul", "shoes", 5): "달마 초혜",
    ("bul", "accessory", 4): "사리함 패", ("bul", "accessory", 5): "진신사리 패",
    ("seon", "weapon", 4): "칠성검", ("seon", "weapon", 5): "태을 뇌검",
    ("seon", "armor", 4): "학창의", ("seon", "armor", 5): "우의 선포",
    ("seon", "shoes", 4): "운혜", ("seon", "shoes", 5): "축지 운리",
    ("seon", "accessory", 4): "호로병 패", ("seon", "accessory", 5): "선도 복숭아 옥패",
}
ROUTES = {  # 4등급=인접 2~3권역 3노드, 5등급=전국 3~5권역 4~5노드 (build_world.py 노드 id)
    ("yu", 4): ["ND_02_CITY_HANYANGGYEONGJO", "ND_06_CITY_GONGJUCHUNGCHEONGGAMYEONG", "ND_07_CITY_JEONJUJEONRAGAMYEONG"],
    ("yu", 5): ["ND_02_CITY_HANYANGGYEONGJO", "ND_13_CITY_PYEONGYANGBU", "ND_10_CITY_DAEGUGYEONGSANGGAMYEONG", "ND_07_CITY_JEONJUJEONRAGAMYEONG"],
    ("bul", 4): ["ND_09_CITY_GYEONGJUBU", "ND_10_CITY_DAEGUGYEONGSANGGAMYEONG", "ND_10_TOWN_MILYANG"],
    ("bul", 5): ["ND_09_CITY_GYEONGJUBU", "ND_10_TEMPLE_HAEINSA", "ND_13_TEMPLE_MYOHYANGSANBOHYEONSA", "ND_16_SCENIC_BAEKDUSANCHEONJI"],
    ("seon", 4): ["ND_04_CITY_GANGREUNGDAEDOHOBU", "ND_04_CITY_WONJUGANGWONGAMYEONG", "ND_05_CITY_CHUNGJUMOK"],
    ("seon", 5): ["ND_06_SHRINE_GYERYONGSANSINDOAN", "ND_02_CITY_HANYANGGYEONGJO", "ND_13_TEMPLE_MYOHYANGSANBOHYEONSA", "ND_16_SCENIC_BAEKDUSANCHEONJI", "ND_17_CITY_JEJUMOKJEJUEUPSEONG"],
}
MOJAK_MATS = {
    ("yu", 4): [("mat_iron", 10), ("mat_charcoal", 8), ("mat_cowhide", 3)],
    ("yu", 5): [("mat_meteor_iron", 2), ("mat_iron", 12), ("mat_charcoal", 10)],
    ("bul", 4): [("mat_copper", 8), ("mat_sarira_crystal", 1), ("mat_hemp", 4)],
    ("bul", 5): [("mat_sarira_crystal", 3), ("mat_copper", 10), ("mat_silk_thread", 4)],
    ("seon", 4): [("mat_cinnabar", 1), ("mat_silk_thread", 6), ("mat_mulberry", 6)],
    ("seon", 5): [("mat_cinnabar", 3), ("mat_silk_thread", 8), ("mat_meteor_iron", 1)],
}
SLOT_LABEL = {"weapon": "무기", "armor": "갑옷", "shoes": "신발", "accessory": "장신구"}


def scale(stats, ratio):
    return {k: (round(v * ratio, 3) if isinstance(v, float) else int(round(v * ratio))) for k, v in stats.items()}


def gen_equipment_and_mojak():
    eq = load("02_equipment.json")
    items = [i for i in eq["items"] if i.get("generated") != "systematic"]
    mojak = []
    for fam in FAMILIES:
        for slot in ("weapon", "armor", "shoes", "accessory"):
            for tier in (4, 5):
                oid = f"eq_{fam}_{slot}_{tier}"
                stats = gear_stats(slot, tier, fam)
                name = NAMES[(fam, slot, tier)]
                items.append({
                    "id": oid, "name": name, "slot": slot, "tier": tier, "family": fam,
                    "element": FAMILIES[fam]["element"] if slot == "weapon" else "none",
                    "affinity": fam, "weight": {"weapon": 3.0, "armor": 6.0, "shoes": 0.8, "accessory": 0.2}[slot],
                    "stats": stats,
                    "acquire": {"type": "quest", "quest_name": f"{name} 전승 서사", "min_rank": tier,
                                "route": ROUTES[(fam, tier)],
                                "fail_consolation": f"mj_{fam}_{slot}_{tier}"},
                    "mojak_recipe": f"mj_{fam}_{slot}_{tier}",
                    "generated": "systematic",
                })
                mojak.append({
                    "id": f"mj_{fam}_{slot}_{tier}",
                    "name": f"[모작] {name}",
                    "family": fam, "slot": slot, "tier": tier,
                    "original": oid, "ratio": MOJAK_RATIO,
                    "stats": scale(stats, MOJAK_RATIO),
                    "element": FAMILIES[fam]["element"] if slot == "weapon" else "none",
                    "min_rank": tier,
                    "materials": [{"id": m, "qty": q} for m, q in MOJAK_MATS[(fam, tier)]],
                    "craft_anywhere": True,
                    "recipe_sources": ["sell_original", "quest_fail_consolation"],
                })
    eq["items"] = items
    save("02_equipment.json", eq)
    save("16_mojak_gear.json", {
        "_schema": "16_고유제작_전투장착[모작] 24종. 유·불·선 × 4부위 × 4·5등급. 원본 스탯의 70~80%. Rank(min_rank)+원자재만 충족하면 전국 어디서나 야외 단조. 레시피 해금: 원본 장비 상점 매각 시 또는 전용 서사 퀘스트 실패 시 패자부활 지급.",
        "mojak": mojak})
    return len(mojak)


CAPTURE = {
    "yu":   ("포승", "human", ["삼끈 포승", "홍사 포승", "포도청 오랏줄", "의금부 홍사오랏", "어명 금포승"], ["mat_hemp", "mat_cotton", "mat_silk_thread", "mat_silk_thread", "mat_silk_thread"]),
    "bul":  ("염주", "ghost", ["율무 염주", "보리수 염주", "백팔 염주", "사리 염주", "불사리 금강염주"], ["mat_wood", "mat_wood", "mat_wood", "mat_sarira_crystal", "mat_sarira_crystal"]),
    "seon": ("부적", "yokai", ["황지 부적", "주사 부적", "칠성 부적", "태을 부적", "옥추 신부"], ["mat_mulberry", "mat_mulberry", "mat_cinnabar", "mat_cinnabar", "mat_cinnabar"]),
    "mu":   ("덫", "beast", ["올가미", "창애 덫", "함정 덫", "착호 틀덫", "신궁 그물"], ["mat_hemp", "mat_iron", "mat_iron", "mat_iron", "mat_meteor_iron"]),
}
METHOD = {"yu": "고용", "bul": "빙의", "seon": "봉인", "mu": "길들이기"}
CAP_RATE = [0.30, 0.40, 0.50, 0.60, 0.70]
CAP_PRICE = [30, 90, 250, 700, 1800]


def gen_capture():
    tools = []
    for fam, (kind, target, names, mats) in CAPTURE.items():
        for t in range(5):
            tools.append({
                "id": f"cap_{fam}_{t + 1}", "name": names[t], "family": fam, "kind": kind,
                "tier": t + 1, "target_kind": target, "base_rate": CAP_RATE[t],
                "price": CAP_PRICE[t], "skill": f"sk_cap_{fam}", "method": METHOD[fam], "weight": 0.3,
                "craft": {"book": "bk_tool_capture", "materials": [{"id": mats[t], "qty": 1 + t}]},
            })
    save("08_capture_tools.json", {
        "_schema": "08_포획구. 유(포승·고용: 인간, 고용비 추가)·불(염주·빙의/해원: 원혼)·선(부적·봉인: 요괴)·무(덫·길들이기: 맹수, 먹이 보너스) × 5등급. 빈사(HP≤30%)에서만, 보스 불가. 계통 규칙은 00_overview.capture.methods.",
        "tools": tools})
    return len(tools)


if __name__ == "__main__":
    print(f"16_mojak: {gen_equipment_and_mojak()}종, 08_capture: {gen_capture()}종 생성 완료")
