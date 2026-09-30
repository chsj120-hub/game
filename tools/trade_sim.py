#!/usr/bin/env python3
"""자유 무역(시장 매매) 수익 모델 — 무역 퀘스트가 아닌 '원산지에서 사서 먼 곳에 파는' 자유 매매의 상한을 계산한다.

모델
  · 매수 = 기준가 × buy_at_origin(0.72), 매도 = 기준가 × sell_by_hops[권역 거리](0.60/0.95/1.15/1.35) × 신선도
  · 5일장 물량: 등급별 stock_by_grade(기본 20 / 상품 8 / 진상품 3) — 현재 코드는 '장터 노드마다' 따로 셈
  · 해금: 등급품은 Rank ≥ 등급, 원산지 발전도는 신분 L 에서 min(3, L−1) 까지 올렸다고 가정
  · 적재: carry_base + 행장(봇짐/지게) + 탈것 + 동료 3인 평균 carry_bonus, 무게 비율 0.7(감속 없음)까지
  · 이동: 권역 거점 간 최단 경로 게임 시간(travel_sim.trip, 도보 90 / 준마 145 px/s), 한 번에 편도 1회 판매
  · 비교: 같은 등급 구간의 콘텐츠 엽전 수입(economy_sim 균형형) = '몇 번의 무역 편도로 그 등급 콘텐츠 수입과 같아지나'
사용: python3 tools/trade_sim.py [--per-region]   (--per-region = 물량을 권역 단위로 묶는 추천안)
"""
import argparse
import itertools
from collections import deque

from common import load, price, tier_curve
import travel_sim as TS
import economy_sim as ES

OV = load("00_overview.json")
T = OV["trade"]
REG = load("regions.json")
SP = [s for s in load("03_specialties.json")["specialties"] if s["kind"] != "crafted"]
COMP = load("13_companions.json")["companions"]
REGIONS = {r["id"]: r for r in REG["regions"]}
NODES = {n["id"]: n for n in REG["nodes"]}
MARKETS = {r: [n for n in REG["nodes"] if n["region"] == r and ({"market", "market5"} & set(n["facilities"]))] for r in REGIONS}
CARRY_COMP = 3 * sum(c.get("carry_bonus", 0) for c in COMP) / len(COMP)
GEAR = {1: 10, 2: 10, 3: 40, 4: 40, 5: 40}                   # 봇짐 → 지게(Rank 3)
MOUNT = {1: (20, 90.0), 2: (25, 90.0), 3: (30, 145.0), 4: (35, 145.0), 5: (35, 145.0)}  # (적재, 이동 px/s)


def hops(a, b):
    if a == b:
        return 0
    dist, q = {a: 0}, deque([a])
    while q:
        c = q.popleft()
        for nb in REGIONS[c]["adjacent"]:
            if nb not in dist:
                dist[nb] = dist[c] + 1
                if nb == b:
                    return dist[nb]
                q.append(nb)
    return 3


HOURS = {}


def travel(a, b, v):
    """거점 간 최단 게임 시간(h)·거친 노드 수 — 육로(리 → 시간) + 해로(days × 24h)"""
    k = (a, b, v)
    if k in HOURS:
        return HOURS[k]
    import heapq
    mv = OV["movement"]
    g = {}
    for e in REG["edges"] + REG["border_links"]:
        h = e["li"] * REG["px_per_li"] / (v * mv["terrain"].get(e["terrain"], 1.0)) * mv["game_minutes_per_walk_second"] / 60
        g.setdefault(e["a"], []).append((e["b"], h))
        g.setdefault(e["b"], []).append((e["a"], h))
    for e in REG["sea_routes"]:
        g.setdefault(e["a"], []).append((e["b"], 24.0 * e.get("days", 1)))
        g.setdefault(e["b"], []).append((e["a"], 24.0 * e.get("days", 1)))
    src, dst = REGIONS[a]["hub"], REGIONS[b]["hub"]
    dist, pq = {src: (0.0, 0)}, [(0.0, 0, src)]
    while pq:
        d, n, u = heapq.heappop(pq)
        if u == dst:
            break
        if d > dist[u][0]:
            continue
        for w, h in g.get(u, []):
            if d + h < dist.get(w, (1e18, 0))[0]:
                dist[w] = (d + h, n + 1)
                heapq.heappush(pq, (d + h, n + 1, w))
    HOURS[k] = dist.get(dst, (1e9, 99))
    return HOURS[k]


def sat_total(unit_price, q, on):
    """판매 포화: 한 장터에서 q개를 팔 때의 매도 합계 배율(개당 −per_unit, 하한 floor)"""
    if not on:
        return q
    sat = T.get("sell_saturation", {"per_unit": 0.0, "floor": 1.0})
    return sum(max(sat["floor"], 1 - sat["per_unit"] * k) for k in range(q))


def goods(origin, L, per_region):
    dev = min(3, L - 1)
    out = []
    for s in SP:
        if s["region"] != origin or s["dev_level"] > dev:
            continue
        gr = s.get("grade", 0)
        if gr > 0 and L < s["tier"]:
            continue
        stock = s.get("stock", T["stock_by_grade"][gr] if "grade" in s else (6 if s["kind"] == "premium" else 20))
        out.append((s, stock * (1 if per_region else max(1, len(MARKETS[origin])))))
    return out


def best_trip(L, per_region, saturate=None):
    saturate = per_region if saturate is None else saturate
    cap = (OV["movement"]["carry_base"] + GEAR[L] + MOUNT[L][0] + CARRY_COMP) * 0.7
    v = MOUNT[L][1]
    best = None
    for o, d in itertools.permutations(REGIONS, 2):
        g = goods(o, L, per_region)
        if not g:
            continue
        h = hops(o, d)
        gh, nodes = travel(o, d, v)
        mult = T["sell_by_hops"][min(h, 3)]
        rows = []
        for s, stock in g:
            fresh = max(0.0, 1 - 0.05 * nodes) if s.get("perishable") else 1.0
            unit = s["base_price"] * (mult * fresh - T["buy_at_origin"])
            if unit > 0:
                rows.append((unit / s["weight"], mult * fresh, s, stock))
        rows.sort(key=lambda r: -r[0])
        left, profit, cash, load_ = cap, 0.0, 0.0, []
        for _, sell_m, s, stock in rows:
            q = min(stock, int(left // s["weight"]))
            # 포화: 판매 권역 장터 최대 2곳에 나눠 판다고 가정
            while q > 0:
                half = (q + 1) // 2
                gain = s["base_price"] * (sell_m * (sat_total(1, half, saturate) + sat_total(1, q - half, saturate)) - T["buy_at_origin"] * q)
                if gain > 0:
                    break
                q -= 1
            if q <= 0:
                continue
            left -= q * s["weight"]
            profit += gain
            cash += q * s["base_price"] * T["buy_at_origin"]
            load_.append(f"{s['name']}×{q}")
        days = max(gh / 24.0, 0.25)
        cand = (profit / days, profit, days, o, d, h, cash, load_)
        if best is None or cand[0] > best[0]:
            best = cand
    return best


def content_income(L):
    """economy_sim 균형형의 해당 등급 콘텐츠 엽전(유산 매각·퀘스트·무역 퀘스트·처치)"""
    E, P = ES.E, ES.P
    i = L - 1
    h = tier_curve(E["heritage_money"], L) * (1 + P["heritage_hidden_share"] * (E["hidden_mult"] - 1))
    tot = P["heritage"][i] * h * ES.STYLES["균형형"][2]
    for k in ("gear_quest", "mount_quest", "companion", "companion_promo", "instance", "event", "main", "bounty"):
        qt = {"gear_quest": "gear", "mount_quest": "mount"}.get(k, k)
        tot += P[k][i] * E["quest_money"]["base"] * E["quest_money"]["growth"] ** i * E["quest_type_mult"][qt]["money"]
    tot += P["trade"][i] * price("specialty", L) * 10 * (T["specialty_quest_margin"] - T["buy_at_origin"])
    tot += P["kills"][i] * ES.enemy_reward(OV, L, False, "money") + P["boss"][i] * ES.enemy_reward(OV, L, True, "money")
    return tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-region", action="store_true")
    a = ap.parse_args()
    for label, pr in (("구 방식(장터 노드마다 물량 · 포화 없음)", False), ("현재(권역 공유 물량 · 판매 포화)", True)):
        if a.per_region and not pr:
            continue
        print(f"\n══ 자유 무역 상한 — {label}")
        print("  신분 | 최선 편도(원산지→판매지, 권역 거리) | 이익 | 게임 일수 | 냥/게임일 | 투자금 | 그 등급 콘텐츠 수입 | 편도 몇 번이면 같아지나")
        for L in range(1, 6):
            per_day, profit, days, o, d, h, cash, load_ = best_trip(L, pr)
            inc = content_income(L)
            print(f"  R{L}  | {REGIONS[o]['name']}→{REGIONS[d]['name']} ({h}) | {profit:9,.0f} | {days:4.1f} | {per_day:8,.0f} | {cash:8,.0f} | "
                  f"{inc:10,.0f} | {inc / max(profit, 1):5.1f}회   [{', '.join(load_[:4])}{' …' if len(load_) > 4 else ''}]")
    fm = T.get("free_trade_model", {})
    print(f"\n  economy_sim 반영: 신분 등급마다 편도 {fm.get('trips_per_tier')}회 × 최선 이익 × 효율 {fm.get('efficiency')}")


def free_trade_income(L):
    """economy_sim 용 — 현재 규칙(권역 공유·포화)에서 신분 L 구간 자유 무역 기대 수입"""
    fm = T.get("free_trade_model", {"trips_per_tier": 0, "efficiency": 0})
    return fm["trips_per_tier"] * best_trip(L, T.get("stock_scope") == "region")[1] * fm["efficiency"]


if __name__ == "__main__":
    main()
