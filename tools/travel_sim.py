#!/usr/bin/env python3
"""이동·탐색 체감 분석기 — 지도 크기/이동 속도/축척 조정안을 수치로 비교한다.

측정: 권역 내 간선·국경 링크 거리(리), 대표 여정(인접 거점·권역 횡단·전국 종단)의 실시간(초)·게임 시간·피로(휴식 횟수),
      전 노드 답사 최소 이동량(MST 근사), 은닉 노드↔부모 거리 분포(탐색 반경 적정값).
사용: python3 tools/travel_sim.py
"""
import heapq
import math
import statistics

from common import load

OV = load("00_overview.json")
REG = load("regions.json")
MV, SV = OV["movement"], OV["survival"]
NODES = {n["id"]: n for n in REG["nodes"]}
BY_NAME = {n["name"]: n["id"] for n in REG["nodes"]}


def graph():
    g = {k: [] for k in NODES}
    for e in REG["edges"] + REG["border_links"]:
        g[e["a"]].append((e["b"], e["li"], e["terrain"]))
        g[e["b"]].append((e["a"], e["li"], e["terrain"]))
    return g


G = graph()


def shortest(a, b):
    dist, pq = {a: 0.0}, [(0.0, a, [])]
    while pq:
        d, u, path = heapq.heappop(pq)
        if u == b:
            return d, path
        if d > dist.get(u, 1e18):
            continue
        for v, li, t in G[u]:
            nd = d + li
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                heapq.heappush(pq, (nd, v, path + [(li, t)]))
    return None, []


def trip(path, px_per_li, v_px, pace, min_per_s):
    """(실시간 초, 게임 시간 h, 피로 누적, 휴식 필요 횟수)"""
    real = game_min = fat = 0.0
    for li, t in path:
        v = v_px * MV["terrain"].get(t, 1.0)
        px = li * px_per_li
        real += px / (v * pace)
        game_min += px / v * min_per_s
        fat += li / SV["tick_li"] * SV["fatigue_per_tick"] * SV["fatigue_mult"]["terrain"].get(t, 1.0)
    return real, game_min / 60, fat, int(fat // 70)


def mst_li():
    ids = list(NODES)
    inside, total = {ids[0]}, 0.0
    best = {v: (li, u) for u, lst in [(ids[0], G[ids[0]])] for v, li, _ in lst}
    pq = [(li, v) for v, (li, _) in best.items()]
    heapq.heapify(pq)
    while pq and len(inside) < len(ids):
        li, v = heapq.heappop(pq)
        if v in inside:
            continue
        inside.add(v)
        total += li
        for w, l2, _ in G[v]:
            if w not in inside:
                heapq.heappush(pq, (l2, w))
    return total


def main():
    ppl = REG["px_per_li"]
    road = [e["li"] for e in REG["edges"] if e["kind"] == "road"]
    border = [e["li"] for e in REG["border_links"]]
    print("══ 거리 분포(리)")
    print(f"  권역 내 도로 간선  중앙값 {statistics.median(road):.0f} (p10 {sorted(road)[len(road)//10]:.0f} ~ p90 {sorted(road)[len(road)*9//10]:.0f})")
    print(f"  국경 링크          중앙값 {statistics.median(border):.0f} (범위 {min(border)}~{max(border)})")
    hid = []
    for n in REG["nodes"]:
        if n["hidden"]:
            for v, li, _ in G[n["id"]]:
                hid.append(li)
    print(f"  은닉 노드↔부모     중앙값 {statistics.median(hid):.1f} · p75 {sorted(hid)[len(hid)*3//4]:.1f} · 최대 {max(hid):.1f}")
    tot = mst_li()
    print(f"  전 노드 연결 최소 이동량(MST) {tot:,.0f}리  → 전수 답사 추정 {tot*1.6:,.0f}리(되짚기 ×1.6)")

    trips = [("인접 거점(권역 내 1구간)", "한양 경조", "양재역"), ("권역 중심 횡단", "한양 경조", "여주"),
             ("인접 권역 거점", "한양 경조", "공주 충청감영"), ("3권역 연계(3~4등급 동선)", "한양 경조", "전주 전라감영"),
             ("전국 종단(5등급 동선)", "한양 경조", "의주목"), ("삼남→북관", "전주 전라감영", "함흥부")]
    scen = [("기준(배율1.0)", ppl, 90.0, 1.0, MV["game_minutes_per_walk_second"])]
    if "field_pace_mult" in MV:
        scen.append(("조정안 도보", ppl, 90.0, MV["field_pace_mult"], MV["game_minutes_per_walk_second"]))
        scen.append(("조정안 준마", ppl, 145.0, MV["field_pace_mult"], MV["game_minutes_per_walk_second"]))
        scen.append(("조정안 익숙한 길(도보)", ppl, 90.0, MV["field_pace_mult"] * MV["known_road_pace_mult"], MV["game_minutes_per_walk_second"]))
    print("\n══ 대표 여정 (실시간 초 / 게임 시간 / 피로 누적 → 휴식 횟수)")
    for label, a, b in trips:
        d, path = shortest(BY_NAME[a], BY_NAME[b])
        row = []
        for sname, p, v, pace, mps in scen:
            r, gh, fat, rests = trip(path, p, v, pace, mps)
            row.append(f"{sname} {r:4.0f}초")
        _, gh, fat, rests = trip(path, ppl, 90.0, 1.0, MV["game_minutes_per_walk_second"])
        print(f"  {label:<22} {d:6.0f}리 · 게임 {gh:5.1f}h · 피로 {fat:4.0f}(휴식 {rests}) │ " + " · ".join(row))
    for sname, p, v, pace, mps in scen:
        secs = tot * 1.6 * p / (v * pace)
        print(f"  전수 답사 순수 이동 [{sname}] ≈ {secs/3600:.1f}시간(실시간)")
    sr = OV["facilities"]["search"]
    print(f"\n══ 탐색: 기본 반경 {sr['radius_li']}리 + 사 지식당 {sr['radius_li_per_sa']}리 · 발견률 {sr['detect_chance']}+{sr['detect_per_sa']}/랭크")
    for sa in (0, 3, 6, 10):
        rad = sr["radius_li"] + sr["radius_li_per_sa"] * sa
        cover = sum(1 for x in hid if x <= rad) / len(hid)
        print(f"  사 {sa:>2}: 반경 {rad:>4.0f}리 — 부모 거점에서 닿는 은닉지 {cover*100:5.1f}% · 1회 발견 기대 {cover*min(0.95, sr['detect_chance']+sr['detect_per_sa']*sa)*100:4.1f}%")


if __name__ == "__main__":
    main()
