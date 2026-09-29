#!/usr/bin/env python3
"""DB-15 동료 65명 + 게임 전용 2명 → data/13_companions.json (시작 1~3등급·승급 퀘스트) · 동료 스킬 → 14_skills.json
· 선단 불사환 → 즉사 방지 버프(09 · 18).

전제: tools/db15/audit_fix.py 를 먼저 실행(data_src/db15/db15_game.json 생성).
게임에 이미 있던 동료 12명은 튜닝된 게임 스킬을 유지하고, 나머지는 DB-15 전투 스킬 변환본(3등급 기준 수치)을 쓴다.
사용: python3 tools/db15/merge_companions.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import load, save  # noqa: E402

DB = HERE.parents[1] / "data_src" / "db15"
EXP = json.loads((DB / "db15_game.json").read_text(encoding="utf-8"))
ELEM = {"yu": "metal", "bul": "holy", "seon": "wood", "none": "none"}
LORE = [("역사", "역사"), ("신화", "설화"), ("설화", "설화"), ("소설", "창작"), ("직업", "창작")]


def main():
    old = {c["id"]: c for c in load("13_companions.json")["companions"]}
    sk_doc = load("14_skills.json")
    skills = {s["id"]: s for s in sk_doc["skills"]}
    conv = {s["skill_id"]: s for s in EXP["11_전체스킬_통합_346종"]}
    promos = {}
    for q in EXP["_promotions"]:
        promos.setdefault(q["companion"], []).append({k: q[k] for k in ("id", "tier", "name", "lore", "min_rank", "trigger_node", "requires", "route", "steps")})
    out, added_sk = [], 0
    for r in EXP["10_동료_캐릭터_65종"]:
        cid = r["game_id"]
        fam = r["family"]
        g = old.get(cid)
        if g:
            sk_ids = g["skills"]
        else:
            sk_ids = []
            for src in [x for x in str(r["skills"]).split(",") if x]:
                s = conv[src]
                sid = "sk_cp_" + src[9:11]
                skills[sid] = {"id": sid, "name": s["name_kr"].split(": ", 1)[-1], "owner": "companion", "target": s["target_game"],
                               "ap_cost": int(s["ap_cost"]), "power": float(s["power"]), "element": s["element"], "affinity": s["affinity"],
                               "cooldown": int(s["cooldown"]), "effects": s["effects_json"] or {}, "db15": src}
                sk_ids.append(sid)
                added_sk += 1
        el = g["element"] if g else next((skills[s]["element"] for s in sk_ids if skills[s]["element"] not in ("weapon", "none")), ELEM[fam])
        kn = r["knowledge_add_json"]
        out.append({
            "id": cid, "name": r["name_kr"], "family": fam, "role": r["role"], "tier": int(r["start_tier"]), "start_tier": int(r["start_tier"]),
            "max_tier": 5, "yu_bul_seon_type": fam, "element": el, "hp": r["hp"], "atk": r["atk"], "def": r["def"], "speed": r["speed"],
            "res": 0.05, "skills": sk_ids, "knowledge": dict(kn), "knowledge_add": kn, "knowledge_per_promotion": r["knowledge_per_promotion_json"],
            "primary_knowledge": r["primary_knowledge"], "recruit": {"min_rank": int(r["recruit_min_rank"]), "route": r["recruit_route_json"],
                                                                     "condition": r["recruit_condition"]},
            "lore_tag": next(v for k, v in LORE if k in str(r["category_type"])), "carry_bonus": int(r["carry_bonus"]),
            "signature_item": r["signature_item"], "category": r["category_type"], "era": r["era"], "desc": r["description"],
            "db15_id": r["companion_id"], "promotion": sorted(promos.get(cid, []), key=lambda q: q["tier"])})
    for cid, x in EXP["_extra_companions"].items():
        g = dict(old[cid])
        g.update({"tier": x["start_tier"], "start_tier": x["start_tier"], "max_tier": 5, "knowledge": dict(x["knowledge_add"]),
                  "knowledge_add": x["knowledge_add"], "knowledge_per_promotion": {x["primary"]: 1}, "primary_knowledge": x["primary"],
                  "recruit": {"min_rank": x["start_tier"], "route": x["route"]}, "promotion": sorted(promos.get(cid, []), key=lambda q: q["tier"])})
        out.append(g)
    doc = load("13_companions.json")
    doc["companions"] = out
    doc["_schema"] = ("13_동료 67명(유28·불9·선13·무15 + 게임 전용 2). tier=시작 등급(1~3, 유명도·능력 점수 3등분), max_tier=5. "
                      "promotion[]=승급 퀘스트(서사 맞춤 자동 설계: 트리거 = 신분 Rank≥t·동행·대표 지식≥t·시작 장소 방문, 동선 route_rules 준수). "
                      "현재 등급은 GameState.companions[id].tier. 승급 시 knowledge_per_promotion 가산(지식 합 = 현재 등급), 스킬 숙련 +8%/등급. "
                      "동료 기여 = 스킬·지식·짐 무게(스탯 합산 없음). hp/atk/def/speed 는 시작 등급 표시용. 일급 = wage_per_day(현재 등급), 막사 대기 시 0.")
    save("13_companions.json", doc)
    sk_doc["skills"] = list(skills.values())
    save("14_skills.json", sk_doc)
    # 선단 불사환 → 즉사 방지 버프
    hr = load("09_herbal_recipes.json")
    for x in hr["recipes"]:
        if x["id"] == "hr_seondan":
            x["name"] = "선단 불사환"
            x["effect"] = {"death_ward": {"turns": 3, "hp_floor": 1}}
    hr["_schema"] = hr["_schema"].replace("effect={heal_pct, revive_pct, cure[], buff{}}", "effect={heal_pct, cure[], buff{}, death_ward{turns,hp_floor}}")
    save("09_herbal_recipes.json", hr)
    se = load("18_status_effects.json")
    if not any(s["id"] == "death_ward" for s in se["battle"]):
        se["battle"].append({"id": "death_ward", "name": "불사(不死)", "icon": "st_death_ward", "type": "buff", "skip_turn": False, "boss_immune": False,
                             "desc": "치명타를 맞아도 HP 1 로 버티며 더 줄지 않음(자기 턴 3회 지속)"})
    save("18_status_effects.json", se)
    tiers = [c["tier"] for c in out]
    print(f"동료 {len(out)}명 (시작 1등급 {tiers.count(1)} · 2등급 {tiers.count(2)} · 3등급 {tiers.count(3)}) · 신규 스킬 {added_sk} · "
          f"승급 퀘스트 {sum(len(c['promotion']) for c in out)}건")


if __name__ == "__main__":
    main()
