#!/usr/bin/env python3
"""명성 총량 재정립 + 진행 몬테카를로 + 엽전 여유 점검.

1) 총량(반복 원천 제외): 최대(전부 기증·정시) / 기준(3택 균등) / 최소(기증 0) — 원천별·도(道)별
2) 진행 시뮬: 콘텐츠를 무작위 순서로 찾아가며(신분 게이트·등급 가중) 3택을 확률 선택.
   재미 장치 전부 반영 — 답사 명성 분리, 윗등급 선행 보너스/하위 감쇠, 관아 감정 거부(보관·매각),
   암시장 적발, 권역 전수 수집 보너스, 메인 N장 = Rank N 게이트
3) 보정: 균형형 플레이어가 콘텐츠의 1/3 을 찾았을 때(중앙값) Rank 5(엔딩 가능) 도달하도록 Rank 5 임계를 이분 탐색,
   Rank 2~4 = R5·((L−1)/4)^k. 도(道) 명성 5단계 = 그 도 콘텐츠 2/3 시점 도 명성 중앙값, 1~4단계 = ·(L/5)^1.3
4) 엽전: 성향별 수입/필수 지출 비율과 조정 추천안
사용: python3 tools/economy_sim.py [--write] [--players 300]
"""
import argparse
import math
import random
import statistics
from collections import Counter, defaultdict

from common import load, price, quest_reward, enemy_reward, save, tier_curve

OV = load("00_overview.json")
E = OV["economy"]
P = OV["content_plan"]
SIDE = load("22_side_systems.json")
HER = load("01_heritage.json")["heritage"]
NODES = load("regions.json")["nodes"]
TIERS = [1, 2, 3, 4, 5]
D = E["heritage_discovery_share"]
K_SHAPE = 2.245                      # 기존 적합식 곡률 유지(초반 빠르게·후반 길게)
PROV = OV["provinces"]
R2P = {r: p["id"] for p in PROV for r in p["regions"]}
STYLES = {"기증형": (0.60, 0.20, 0.20), "균형형": (1 / 3, 1 / 3, 1 / 3), "매각형": (0.15, 0.25, 0.60)}
BLACK_SHARE, HOLD_WHEN_REFUSED = 0.35, 0.7
PROV_PCT = 0.30


# ================================================================ 콘텐츠 목록 생성 (완성판 목표 수량 → 도·권역 배분)
def alloc(total, weights):
    """최대 잉여 배분"""
    s = sum(weights.values())
    raw = {k: total * v / s for k, v in weights.items()}
    out = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - out[k], reverse=True)[: total - sum(out.values())]:
        out[k] += 1
    return out


REGION_HER = Counter(h["region"] for h in HER)
REGION_NODE = Counter(n["region"] for n in NODES)
CAT_BY_TIER = {t: Counter(h["category"] for h in HER if h["tier"] == t) or Counter({"architecture": 1}) for t in TIERS}


def build_items(seed=1):
    rng = random.Random(seed)
    items = []
    for t in TIERS:
        per_reg = alloc(P["heritage"][t - 1], {r: REGION_HER.get(r, 0) + 1 for r in REGION_NODE})
        cats = list(CAT_BY_TIER[t].elements())
        for reg, n in per_reg.items():
            for _ in range(n):
                cat = rng.choice(cats)
                hidden = rng.random() < P["heritage_hidden_share"]
                base = tier_curve(E["heritage_rep"], t) * E["category_mult"].get(cat, {}).get("rep", 1.0) * (E["hidden_mult"] if hidden else 1.0)
                items.append({"g": "H", "t": t, "reg": reg, "prov": R2P[reg], "base": base})
    qtypes = {"gear_quest": "gear", "mount_quest": "mount", "companion": "companion", "companion_promo": "companion_promo",
              "instance": "instance", "event": "event", "trade": "trade"}
    for key, qt in qtypes.items():
        g = "P" if key.startswith("companion") else "Q"   # 동료 영입·승급은 신분 Rank ≥ 등급에서만(일반 퀘스트는 등급−1)
        for t in TIERS:
            for reg, n in alloc(P[key][t - 1], dict(REGION_NODE)).items():
                for _ in range(n):
                    items.append({"g": g, "t": t, "reg": reg, "prov": R2P[reg], "base": quest_reward(OV, t, qt, "rep"), "src": key})
    for t in TIERS:
        for reg, n in alloc(P["boss"][t - 1], dict(REGION_NODE)).items():
            for _ in range(n):
                items.append({"g": "Q", "t": t, "reg": reg, "prov": R2P[reg], "base": enemy_reward(OV, t, True, "rep"), "src": "boss"})
    caps = [p["regions"][0] for p in PROV]
    for t in TIERS:  # 메인 시나리오 5장 — 도를 돌아가며
        reg = caps[(t * 2) % len(caps)]
        items.append({"g": "M", "t": t, "reg": reg, "prov": R2P[reg], "base": quest_reward(OV, t, "main", "rep"), "src": "main"})
    hw = SIDE["hwacheop"]["reward"]["reputation"]
    for i in range(P["hwacheop"]["scenes"] + P["hwacheop"]["scenic_snapshots"]):
        reg = list(REGION_NODE)[i % 17]
        items.append({"g": "S", "t": 1, "reg": reg, "prov": R2P[reg], "base": hw, "src": "hwacheop"})
    tk = SIDE["takbon"]["per_sheet"]["reputation"]
    regs = [r for r in REGION_NODE for _ in range(1)]
    for i in range(P["takbon_sheets"]):
        reg = regs[i % 17]
        items.append({"g": "S", "t": 1, "reg": reg, "prov": R2P[reg], "base": tk, "src": "takbon"})
    return items


ITEMS = build_items()
ONE_TIME_BONUS = {"hwacheop_complete": SIDE["hwacheop"]["complete_bonus"]["reputation"], "takbon_complete": SIDE["takbon"]["complete_bonus"]["reputation"]}


# ================================================================ 총량
def budget():
    src = defaultdict(lambda: [0.0, 0.0, 0.0])   # [최대, 기준, 최소]
    prov = defaultdict(lambda: [0.0, 0.0, 0.0])
    reg_base = defaultdict(float)
    for it in ITEMS:
        if it["g"] == "H":
            mx, ref, mn = it["base"], it["base"] * (D + (1 - D) / 3), it["base"] * D
            key = "유산(답사+기증)"
            reg_base[it["reg"]] += it["base"]
        else:
            mx = ref = mn = it["base"]
            key = {"gear_quest": "장비 서사 퀘스트", "mount_quest": "탈것 퀘스트", "companion": "동료 영입", "companion_promo": "동료 승급 퀘스트",
                   "instance": "탐색 연속전투",
                   "event": "역사·설화 이벤트", "trade": "무역 퀘스트", "boss": "권역·신화 보스", "main": "메인 시나리오",
                   "hwacheop": "화첩", "takbon": "탁본"}[it["src"]]
        for i, v in enumerate((mx, ref, mn)):
            src[key][i] += v
            prov[it["prov"]][i] += v
    for reg, b in reg_base.items():
        v = b * E["region_collection_bonus"]
        for i in range(3):
            src["권역 전수 수집 보너스"][i] += v
            prov[R2P[reg]][i] += v
    for k, v in ONE_TIME_BONUS.items():
        for i in range(3):
            src["화첩·탁본 완성"][i] += v
    tot = [sum(v[i] for v in src.values()) for i in range(3)]
    return src, prov, tot, reg_base


def rank_gap(t, rank):
    g = E["rank_gap"]
    gap = t - rank
    return 1 + g["above_bonus_per_tier"] * gap if gap > 0 else max(g["floor"], 1 - g["below_penalty_per_tier"] * -gap)


def thresholds_from_r5(r5):
    th = [0]
    for L in (2, 3, 4, 5):
        v = r5 * ((L - 1) / 4) ** K_SHAPE
        step = 500 if v >= 10000 else 100
        th.append(int(round(v / step) * step))
    return th


# ================================================================ 진행 몬테카를로
def play(style, th, rng, reg_base, d_share=D):
    pd, pu, ps = STYLES[style]
    buckets = defaultdict(list)
    for i, it in enumerate(ITEMS):
        buckets[(it["g"], it["t"])].append(i)
    for b in buckets.values():
        rng.shuffle(b)
    total = len(ITEMS)
    prov_total = Counter(it["prov"] for it in ITEMS)
    reg_left = Counter(it["reg"] for it in ITEMS if it["g"] == "H")
    prov_done = Counter()
    rep, rank, done = 0.0, 1, 0
    prov_rep = defaultdict(float)
    held = []
    frac_at_rank = {1: 0.0}
    prov_at_23 = {}
    rep_at = {}
    dmr = OV["rank"]["donate_min_rank"]
    hw_left = sum(1 for it in ITEMS if it["src" if "src" in it else "g"] == "hwacheop")
    tk_left = sum(1 for it in ITEMS if it.get("src") == "takbon")

    def gain(v, prov):
        nonlocal rep
        rep += v
        prov_rep[prov] += v

    def donate(it):
        gain(it["base"] * (1 - d_share) * rank_gap(it["t"], rank), it["prov"])

    while done < total:
        ws = []
        for (g, t), lst in buckets.items():
            if not lst:
                continue
            if g == "H":
                w = 1.0 if t <= rank + 1 else 0.2
            elif g in ("M", "P"):
                w = 1.0 if rank >= t else 0.0
            elif g == "S":
                w = 1.0
            else:
                w = 1.0 if rank >= max(1, t - 1) else 0.0
            if w > 0:
                ws.append(((g, t), w * len(lst)))
        if not ws:
            break
        r = rng.random() * sum(w for _, w in ws)
        for key, w in ws:
            r -= w
            if r <= 0:
                break
        it = ITEMS[buckets[key].pop()]
        done += 1
        prov_done[it["prov"]] += 1
        if it["g"] == "H":
            gain(it["base"] * d_share * rank_gap(it["t"], rank), it["prov"])  # 답사 명성
            c = rng.random()
            if c < pd:
                if rank >= dmr[str(it["t"])]:
                    donate(it)
                elif rng.random() < HOLD_WHEN_REFUSED:
                    held.append(it)                                           # 감정 거부 → 보관
                else:
                    c = 1.0                                                   # 매각으로 전환
            if c >= pd + pu and rng.random() < BLACK_SHARE and rng.random() < E["venue"]["black_market"]["bust_chance"]:
                rep -= it["base"] * (1 - d_share) * E["venue"]["black_market"]["bust_rep_loss"]   # 암시장 적발
            reg_left[it["reg"]] -= 1
            if reg_left[it["reg"]] == 0:
                gain(reg_base[it["reg"]] * E["region_collection_bonus"], it["prov"])
        else:
            gain(it["base"], it["prov"])
            if it.get("src") == "hwacheop":
                hw_left -= 1
                if hw_left == 0:
                    gain(ONE_TIME_BONUS["hwacheop_complete"], it["prov"])
            if it.get("src") == "takbon":
                tk_left -= 1
                if tk_left == 0:
                    gain(ONE_TIME_BONUS["takbon_complete"], it["prov"])
        while rank < 5 and rep >= th[rank]:
            rank += 1
            frac_at_rank[rank] = done / total
            still = []
            for h in held:
                (donate(h) if rank >= dmr[str(h["t"])] else still.append(h))
            held = still
        pf = prov_done[it["prov"]] / prov_total[it["prov"]]
        if it["prov"] not in prov_at_23 and pf >= 2 / 3:
            prov_at_23[it["prov"]] = prov_rep[it["prov"]]
        for mark in (1 / 3, 2 / 3):
            if mark not in rep_at and done / total >= mark:
                rep_at[mark] = rep
    return {"frac_at_rank": frac_at_rank, "prov_at_23": prov_at_23, "rep_at": rep_at, "final_rep": rep, "prov_final": dict(prov_rep)}


def run(style, th, n, reg_base, seed=7, d_share=D):
    rng = random.Random(seed)
    return [play(style, th, rng, reg_base, d_share) for _ in range(n)]


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else float("nan")


def calibrate_r5(ref_total, reg_base, n):
    lo, hi = 0.02 * ref_total, 0.8 * ref_total
    for _ in range(18):
        mid = (lo + hi) / 2
        res = run("균형형", thresholds_from_r5(mid), n, reg_base, seed=3)
        med = statistics.median([r["frac_at_rank"].get(5, 1.0) for r in res])
        if med > 1 / 3:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


# ================================================================ 엽전
def money_supply_style(sell_share, qm_base=None, parts=None):
    tot = 0.0
    qm = dict(E["quest_money"])
    if qm_base:
        qm["base"] = qm_base
    parts = parts if parts is not None else {}
    for t in TIERS:
        i = t - 1
        h = tier_curve(E["heritage_money"], t) * (1 + P["heritage_hidden_share"] * (E["hidden_mult"] - 1))
        tot += P["heritage"][i] * h * sell_share
        parts["유산 매각"] = parts.get("유산 매각", 0) + P["heritage"][i] * h * sell_share
        q0 = tot
        for k in ("gear_quest", "mount_quest", "companion", "companion_promo", "instance", "event", "main", "bounty"):
            qt = {"gear_quest": "gear", "mount_quest": "mount"}.get(k, k)
            tot += P[k][i] * qm["base"] * qm["growth"] ** i * E["quest_type_mult"][qt]["money"]
        parts["퀘스트·이벤트"] = parts.get("퀘스트·이벤트", 0) + tot - q0
        tr = P["trade"][i] * price("specialty", t) * 10 * (OV["trade"]["specialty_quest_margin"] - OV["trade"]["buy_at_origin"])
        kl = P["kills"][i] * enemy_reward(OV, t, False, "money") + P["boss"][i] * enemy_reward(OV, t, True, "money")
        parts["무역"] = parts.get("무역", 0) + tr
        parts["처치·보스"] = parts.get("처치·보스", 0) + kl
        tot += tr + kl
    return tot


def essential_spend():
    mats = {m["id"]: m["price"] for m in load("05_materials.json")["materials"]}
    mj = load("16_mojak_gear.json")["mojak"]
    tot = 0.0
    for L in TIERS:
        days = 60 * L
        if L <= 3:
            gear = sum(price(s, L) for s in ("weapon", "armor", "shoes", "accessory"))
        else:
            fam = [m for m in mj if m["tier"] == L and m["family"] == "yu"]
            gear = sum(mats[x["id"]] * x["qty"] for m in fam for x in m["materials"])
        mount = price("mount_ground", L) if L <= 3 else 0
        books = 2 * 150 * 2.6 ** (L - 1)
        wage = days * 3 * tier_curve(E["wage_per_day"], min(L, 5)) * 0.5   # 동행 3인, 현재 등급 ≤ 신분(승급 t 는 Rank ≥ t)
        upkeep = days * tier_curve(E["upkeep_per_day"], L)
        tot += gear + mount + books + wage + upkeep
    return tot


# ================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--players", type=int, default=300)
    args = ap.parse_args()
    src, prov, tot, reg_base = budget()
    print(f"══ 명성 총량 (반복 원천 제외: {', '.join(E['repeatable_sources'])}) — 콘텐츠 {len(ITEMS)}건")
    print(f"  {'원천':<16}{'최대(전부 기증)':>14}{'기준(3택 균등)':>14}{'최소(기증 0)':>12}")
    for k, v in sorted(src.items(), key=lambda kv: -kv[1][0]):
        print(f"  {k:<16}{v[0]:>14,.0f}{v[1]:>14,.0f}{v[2]:>12,.0f}")
    print(f"  {'합계':<16}{tot[0]:>14,.0f}{tot[1]:>14,.0f}{tot[2]:>12,.0f}")
    h = src["유산(답사+기증)"]
    print(f"  → 유산 명성 변동 폭: 답사 명성 분리 전 0~{h[0]:,.0f} / 분리 후 {h[2]:,.0f}~{h[0]:,.0f} (답사 {D*100:.0f}% 보장)")

    n_cal = max(80, args.players // 3)
    r5 = calibrate_r5(tot[1], reg_base, n_cal)
    th = thresholds_from_r5(r5)
    a = th[4] / 4 ** K_SHAPE
    print(f"\n══ 신분 임계 (균형형이 콘텐츠 1/3 을 찾았을 때 중앙값으로 Rank 5 → 엔딩 가능)")
    for L in TIERS:
        print(f"  Rank {L}: {th[L-1]:>8,}   (최대치 대비 {th[L-1]/tot[0]*100:5.1f}% · 기준치 대비 {th[L-1]/tot[1]*100:5.1f}%)")
    print(f"  적합식 Threshold(L) = {a:,.0f}·(L−1)^{K_SHAPE}")

    res = {s: run(s, th, args.players, reg_base, seed=11) for s in STYLES}
    prov_req = {}
    for p in PROV:
        vals = [r["prov_at_23"].get(p["id"]) for r in res["균형형"] if p["id"] in r["prov_at_23"]]
        prov_req[p["id"]] = pct(vals, PROV_PCT)  # 균형형 70% 가 2/3 시점에 가능
    print(f"\n══ 진행 시뮬 ({args.players}명/성향) — Rank 5 도달 시 찾은 콘텐츠 비율")
    for s, rr in res.items():
        f5 = [r["frac_at_rank"].get(5, 1.0) for r in rr]
        f3 = [r["frac_at_rank"].get(3, 1.0) for r in rr]
        print(f"  {s}: R3 {statistics.median(f3)*100:4.1f}% · R5 중앙값 {statistics.median(f5)*100:4.1f}% (p10 {pct(f5,.1)*100:4.1f} ~ p90 {pct(f5,.9)*100:4.1f}) · 1/3 시점 명성 {statistics.median([r['rep_at'][1/3] for r in rr]):,.0f}")
    for s in ("기증형", "매각형"):
        rr0 = run(s, th, max(80, args.players // 3), reg_base, seed=5, d_share=0.0)
        print(f"  (비교) 답사 명성 분리 없음 D=0 · {s}: R5 중앙값 {statistics.median([r['frac_at_rank'].get(5, 1.0) for r in rr0])*100:4.1f}%")

    def lv_req(req5):
        out = []
        for L in TIERS:
            v = req5 * (L / 5) ** 1.3
            out.append(int(round(v / 50) * 50))
        return out
    print("\n══ 도(道) 명성 — 도시 발전 5단계 요건 (그 도 콘텐츠 2/3 시점 균형형 하위 30%값)")
    print(f"  {'도':<6}{'도 최대':>9}{'도 기준':>9}{'5단계 요건':>10}{'  1~5단계':<32}  2/3 시점 가능률(기증/균형/매각) · 100% 시점 매각형")
    for p in PROV:
        req = lv_req(prov_req[p["id"]])
        feas = []
        for s in STYLES:
            vals = [r["prov_at_23"].get(p["id"], 0) for r in res[s]]
            feas.append(sum(1 for v in vals if v >= req[4]) / len(vals))
        full = [r["prov_final"].get(p["id"], 0) for r in res["매각형"]]
        full_ok = sum(1 for v in full if v >= req[4]) / len(full)
        p["standing_req"] = req
        p["standing_max"] = round(prov[p["id"]][0])
        p["standing_ref"] = round(prov[p["id"]][1])
        print(f"  {p['name']:<6}{prov[p['id']][0]:>9,.0f}{prov[p['id']][1]:>9,.0f}{req[4]:>10,}  {str(req):<32}  "
              f"{feas[0]*100:3.0f}/{feas[1]*100:3.0f}/{feas[2]*100:3.0f}%  · {full_ok*100:3.0f}%")

    print("\n══ 엽전 여유 (수입 ÷ 필수 지출)")
    sp = essential_spend()
    parts = {}
    money_supply_style(STYLES["균형형"][2], parts=parts)
    tot_bal = sum(parts.values())
    print("  균형형 수입 구성: " + " · ".join(f"{k} {v/tot_bal*100:.0f}%" for k, v in parts.items()))
    td = OV["town_dev"]
    per_city = sum(td["cost_base"] * td["cost_growth"] ** i for i in range(td["max"]))
    capitals = len(PROV) * per_city
    others = (37 - len(PROV)) * per_city
    ben = td["benefits"]["capital_per_level"]
    # 감영 혜택 환급(평균 단계 2.5 가정): 매입 할인은 장비·탈것·비전서 지출의 60%, 숙박·역마는 생활 소모의 30%에 적용
    refund = sp * 0.6 * ben["province_buy_discount"] * 2.5 + sp * 0.3 * (ben["province_inn_discount"] + ben["province_fast_travel_discount"]) / 2 * 2.5 * 0.35
    essential = sp + capitals - refund
    print(f"  필수 지출 = 장비·탈것·비전서·일급·생활 {sp:,.0f} + 감영 9곳 5단계 {capitals:,.0f} − 감영 혜택 환급 약 {refund:,.0f} = {essential:,.0f}냥")
    print(f"  {'성향':<6}{'수입/필수(적용)':>16}{'  (참고) 감영 제외':>14}{'  + 기타 도시 28곳 전부(선택)':>24}")
    for label in STYLES:
        inc = money_supply_style(STYLES[label][2])
        print(f"  {label:<6}{inc/essential:>16.2f}{inc/sp:>14.2f}{inc/(essential+others):>24.2f}")

    if args.write:
        for r in OV["rank"]["table"]:
            r["threshold"] = th[r["rank"] - 1]
        OV["rank"]["formula"] = {"type": "power", "a": round(a, 1), "k": K_SHAPE,
                                 "note": f"Threshold(L) = {a:,.0f}·(L−1)^{K_SHAPE}. R5 = 균형형이 콘텐츠 1/3 을 찾았을 때(중앙값) 도달하도록 진행 시뮬로 보정"}
        OV["rank"]["reputation_budget"] = {
            "max": round(tot[0]), "reference": round(tot[1]), "min": round(tot[2]),
            "by_source": {k: [round(x) for x in v] for k, v in src.items()},
            "columns": ["최대(전부 기증)", "기준(3택 균등)", "최소(기증 0)"],
            "excludes": E["repeatable_sources"],
            "r5_share_of_max": round(th[4] / tot[0], 3), "r5_share_of_reference": round(th[4] / tot[1], 3)}
        for r in ("pacing", "total_reputation_supply"):
            OV["rank"].pop(r, None)
        OV["provinces"] = PROV
        save("00_overview.json", OV)
        print("\n→ 00_overview.json: rank.table · formula · reputation_budget · provinces[].standing_req 기록")


if __name__ == "__main__":
    main()
