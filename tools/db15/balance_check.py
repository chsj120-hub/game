#!/usr/bin/env python3
"""DB-15 변환 결과를 게임 CTB 시뮬레이터(tools/balance_sim.py)로 검증·보정한다.

1) 게임 보스와 짝지은 6종: DB-15 변환 스킬로 싸워도 게임 목표를 만족하는지(아니면 게임 스킬 유지 권고)
2) 신규 보스(4등급 4종·5등급 2종): 게임 목표(4등급 클러치 A / 5등급 원본 F·4등급 세트 H)에 맞게 HP·ATK 보정
3) 일반 적 1~3등급: 필드 조우 목표(1마리 ≥85%, 3마리 50~90%)에 맞게 ATK 보정
4) 인스턴스 8종: DB-15 웨이브 구성 그대로 풀코스 클리어율
사용: python3 tools/db15/balance_check.py [--tune] [--trials 120]
  --tune  보정값을 data_src/db15/tuning.json 에 기록(audit_fix.py 가 읽어 반영)
"""
import argparse
import json
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import balance_sim as S  # noqa: E402

DB = HERE.parents[1] / "data_src" / "db15"
EXP = json.loads((DB / "db15_game.json").read_text(encoding="utf-8"))
MATCHED = {"ENM_031": "en_bulgasari", "ENM_032": "en_imugi", "ENM_033": "en_jirisan_sanshin",
           "ENM_038": "en_arang", "ENM_039": "en_heukryong", "ENM_042": "en_yeokcheon"}


def register(tuning=None):
    tuning = tuning or {}
    for s in EXP["11_전체스킬_통합_346종"]:
        if s["owner_game"] in ("enemy", "companion", "hero"):
            S.IDX[s["skill_id"]] = {"id": s["skill_id"], "name": s["name_kr"], "owner": s["owner_game"], "target": s["target_game"],
                                    "ap_cost": int(s["ap_cost"]), "power": float(s["power"]), "element": s["element"],
                                    "affinity": s["affinity"], "cooldown": int(s["cooldown"]), "effects": s["effects_json"] or {}}
    for e in EXP["09_조선설화_적목록_42종"]:
        t = tuning.get(e["enemy_id"], {})
        S.IDX[e["enemy_id"]] = {"id": e["enemy_id"], "name": e["name_kr"], "kind": e["kind"], "yu_bul_seon_type": e["yu_bul_seon_type"],
                                "tier": int(e["tier"]), "hp": t.get("hp", e["hp"]), "atk": t.get("atk", e["atk"]), "def": e["def"],
                                "speed": e["speed"], "combat_scale": float(e["combat_scale"]), "base_ap": 3, "element": e["element"],
                                "res": e["res_json"] or {}, "skills": [x for x in str(e["skills"]).split(",") if x],
                                "boss_tier": int(e["boss_tier"]) if e["boss_tier"] else 0, "enrage": e["enrage_json"] or {}}


def boss_eval(eid, trials, t5):
    rows = {}
    for cls in S.CLASSES:
        scs = S.scenarios_t5(eid, cls) if t5 else S.scenarios(eid, cls)
        for name, sc in scs.items():
            if name[0] not in ("A", "B", "D", "F", "H"):
                continue
            wr, turns, hp, _ = S.simulate(eid, sc, trials)
            rows.setdefault(name[0], []).append((wr, statistics.median(turns) if turns else None, statistics.mean(hp) if hp else 0))
    agg = {k: (sum(x[0] for x in v) / 3, statistics.mean([x[1] for x in v if x[1]]) if any(x[1] for x in v) else 0, sum(x[2] for x in v) / 3)
           for k, v in rows.items()}
    return agg


T5_MAX_TURNS = 22   # 게임 5등급 보스(아랑 등) F 세팅 17~19턴 — 지나치게 긴 소모전 방지


def boss_ok(agg, t5, m=0.0):
    """m = 판정 여유(보정 단계에서 경계값 근처 통과를 막아 검증 단계의 표본 흔들림에도 유지되게)."""
    tgt = S.B["clutch_target_turns"]
    if t5:
        return agg["F"][0] >= 0.6 + m and agg["H"][0] <= 0.35 - m and agg["F"][1] <= T5_MAX_TURNS
    a = agg["A"]
    return a[0] >= 0.6 + m and tgt[0] - 0.5 <= a[1] <= tgt[1] + 0.5 and a[2] < 0.4 and agg["B"][0] <= 0.35 - m and agg["D"][0] <= 0.35 - m


def fmt(agg, t5):
    if t5:
        return f"F(5등급 원본) {agg['F'][0]*100:3.0f}% {agg['F'][1]:4.1f}턴 · H(4등급 세트) {agg['H'][0]*100:3.0f}%"
    a = agg["A"]
    return f"A(클러치) {a[0]*100:3.0f}% {a[1]:4.1f}턴 최저HP {a[2]*100:3.0f}% · B {agg['B'][0]*100:3.0f}% · D {agg['D'][0]*100:3.0f}%"


def tune_boss(eid, trials, t5, tuning):
    e = S.IDX[eid]
    hp, atk = float(e["hp"]), float(e["atk"])
    tgt = sum(S.B["clutch_target_turns"]) / 2
    for _ in range(10):
        tuning[eid] = {"hp": int(round(hp / 10) * 10), "atk": int(round(atk))}
        register(tuning)
        agg = boss_eval(eid, trials, t5)
        if boss_ok(agg, t5, 0.05):
            return agg
        if t5:
            if agg["F"][0] < 0.6:
                atk *= 0.94
            elif agg["H"][0] > 0.35:
                atk *= 1.07          # 4등급 세트를 막는 건 화력(방어·HP 차이를 찌름) — HP 는 턴만 늘림
            if agg["F"][1] > T5_MAX_TURNS:
                hp *= 0.92
        else:
            a = agg["A"]
            if a[1]:
                hp *= max(0.85, min(1.15, tgt / a[1]))
            if a[0] < 0.6:
                atk *= 0.94
            elif a[2] >= 0.4 or agg["B"][0] > 0.35 or agg["D"][0] > 0.35:
                atk *= 1.05
    return agg


FIELD = {1: (1, dict(weapon="eq_w1_mokgeom", armor="eq_a1_cheollik", shoes="eq_s1_jipsin", acc1="eq_c1_hopae"), []),
         2: (2, dict(weapon="eq_w2_hwando", armor="eq_a2_dujeonggap", shoes="eq_s2_bidan_jipsin", acc1="eq_c2_yeongdeung"), ["cp_chakho"]),
         3: (3, dict(S.T3, weapon="eq_w3_byeolungeom"), ["cp_heojun", "cp_jeonuchi"])}


def field_rate(group, tier, trials):
    rank, gear, party = FIELD[tier]
    rates = []
    for cls in S.CLASSES:
        sc = dict(cls=cls, rank=rank, gear=gear, party=party, items={}, mount=None)
        rng = random.Random(3)
        wins = sum(S.Engine([S.C(S.hero_stats(sc), "ally")], [S.C(S.enemy_stats(x), "enemy") for x in group], {}, rng).run().state == "victory"
                   for _ in range(trials))
        rates.append(wins / trials)
    return sum(rates) / 3


def instance_rate(waves, tier, trials):
    vals = []
    for cls in S.CLASSES:
        if tier >= 5:
            sc = S.scenarios_t5("en_arang", cls)["F 5등급 원본 풀세트 + 신선로 + 동료3 + 탕약×3"]
        elif tier == 4:
            sc = S.scenarios("en_bulgasari", cls)["A 클러치 세팅 (T3 풀세트+준마+명물음식+동료3+십전대보탕×3)"]
        else:
            rank, gear, party = FIELD[tier]
            sc = dict(cls=cls, rank=rank, gear=gear, party=party + (["cp_samyeong"] if tier == 3 else ["cp_bobusang"]),
                      items={"hr_sipjeon": 2 if tier == 3 else 1}, mount=None)
        rng = random.Random(11)
        ok = 0
        for _ in range(trials):
            allies = [S.C(S.hero_stats(sc), "ally")]
            items = dict(sc["items"])
            good = True
            for w in waves:
                for a in allies:
                    a.gauge, a.first_turn = 0.0, True
                eng = S.Engine(allies, [S.C(S.enemy_stats(x), "enemy") for x in w], items, rng).run()
                items = eng.items
                if eng.state != "victory":
                    good = False
                    break
            ok += good
        vals.append(ok / trials)
    return sum(vals) / 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tune", action="store_true")
    ap.add_argument("--trials", type=int, default=120)
    a = ap.parse_args()
    tpath = DB / "tuning.json"
    tuning = json.loads(tpath.read_text(encoding="utf-8")) if (tpath.exists() and not a.tune) else {}
    register(tuning)
    enemies = {e["enemy_id"]: e for e in EXP["09_조선설화_적목록_42종"]}
    result = {"matched": {}, "new_boss": {}, "field": {}, "instance": {}}
    ok_all = True

    print("══ 1) 게임 보스와 짝지은 6종 — DB-15 변환 스킬 사용 시")
    for eid, gid in MATCHED.items():
        t5 = int(enemies[eid]["tier"]) == 5
        agg = boss_eval(eid, a.trials, t5)
        good = boss_ok(agg, t5, 0.05 if a.tune else 0.0)
        result["matched"][eid] = {"ok": good, "summary": fmt(agg, t5)}
        print(f"  {eid} {enemies[eid]['name_kr'][:14]:<14} {fmt(agg, t5)}  {'충족' if good else '미충족 → 게임 스킬 유지'}")
        if not good and a.tune:
            g = S.load("12_enemies.json")
            tuning[eid] = {"skills_game": next(x for x in g["enemies"] if x["id"] == gid)["skills"]}

    print("\n══ 2) 신규 보스 — 게임 목표에 맞춘 HP·ATK")
    for eid, e in enemies.items():
        if not e["boss_tier"] or eid in MATCHED:
            continue
        t5 = int(e["tier"]) == 5
        before = (e["hp"], e["atk"])
        agg = tune_boss(eid, a.trials, t5, tuning) if a.tune else boss_eval(eid, a.trials, t5)
        good = boss_ok(agg, t5)
        ok_all &= good
        now = (S.IDX[eid]["hp"], S.IDX[eid]["atk"])
        result["new_boss"][eid] = {"ok": good, "summary": fmt(agg, t5), "before": before, "after": now}
        print(f"  {eid} {e['name_kr'][:14]:<14} HP {before[0]}→{now[0]} ATK {before[1]}→{now[1]}  {fmt(agg, t5)}  {'충족' if good else '미충족'}")

    print("\n══ 3) 일반 적 필드 조우 (1마리 ≥85%, 같은 적 3마리 50~90%)")
    trials_f = max(60, a.trials // 2)
    for eid, e in enemies.items():
        tier = int(e["tier"])
        if e["boss_tier"]:
            continue
        n = 2 if e["enemy_tier"] == "ELITE" else 3   # 정예(두목급)는 2마리 조우를 기준
        if a.tune:
            # HP·ATK 공통 배율 s 를 이분 탐색(승률은 s 에 단조 감소) — 목표 n마리 조우 70% (허용 50~90%)
            hp0, atk0 = float(e["hp_conv"]), float(e["atk_conv"])
            lo, hi = 0.4, 3.5

            def at(s):
                tuning[eid] = {"hp": max(1, int(round(hp0 * s))), "atk": max(1, int(round(atk0 * s)))}
                register(tuning)
                return field_rate([eid] * n, tier, trials_f)
            seen = []
            for _ in range(11):
                mid = (lo + hi) / 2
                rate = at(mid)
                seen.append((mid, rate))
                if rate > 0.7:
                    lo = mid
                else:
                    hi = mid
            # 승률은 HP·ATK 정수 반올림 때문에 계단형 → 평가한 점 중 50~90% 안에서 70%에 가장 가까운 배율 채택
            inside = [x for x in seen if 0.55 <= x[1] <= 0.85] or seen
            at(min(inside, key=lambda x: abs(x[1] - 0.7))[0])
        r1 = field_rate([eid], tier, trials_f)
        r3 = field_rate([eid] * n, tier, trials_f)
        good = r1 >= 0.85 and 0.5 <= r3 <= 0.9
        ok_all &= good
        result["field"][eid] = {"ok": good, "r1": round(r1, 2), "rn": round(r3, 2), "n": n, "hp": S.IDX[eid]["hp"], "atk": S.IDX[eid]["atk"],
                                "hp_conv": e["hp_conv"], "atk_conv": e["atk_conv"]}
        print(f"  {eid} T{tier} {e['name_kr'][:14]:<14} HP {e['hp_conv']}→{S.IDX[eid]['hp']} ATK {e['atk_conv']}→{S.IDX[eid]['atk']}  "
              f"1마리 {r1*100:3.0f}% · {n}마리 {r3*100:3.0f}% {'' if good else '✗'}")

    print("\n══ 4) 인스턴스 풀코스 (DB-15 웨이브 그대로, 미니게임·정비 미사용)")
    for w in EXP["14_탐색_미니게임_연속전투"]:
        rate = instance_rate(w["waves_json"], int(w["tier"]), max(30, a.trials // 4))
        result["instance"][w["instance_id"]] = round(rate, 2)
        print(f"  {w['instance_id']} T{w['tier']} {w['name_kr'][:18]:<18} {rate*100:5.1f}%")

    if a.tune:
        tpath.write_text(json.dumps(tuning, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n보정값 기록: {tpath}")
    (DB / "balance_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n결과:", "PASS" if ok_all else "TUNING NEEDED")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
