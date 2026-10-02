#!/usr/bin/env python3
"""월드·유산 빌더: data_src/*.json → data/regions.json, data/01_heritage.json + 유산 보상 아이템 자동 생성.

생성물 (generated="heritage" 태그가 붙은 행만 재생성, 수작업 행은 보존):
  regions.json          17 권역 · 노드(7 상시 + 7 은닉 + 확장) · 도로 간선 · 국경 링크 · 뱃길
  01_heritage.json      수작업 유산 + 노드 유형 기반 자동 유산
  02_equipment.json     금속공예(장비)/민속공예(장신구)/전적(서책) 자동 보상
  03_specialties.json   도자·수중 유산의 복원 특산품 + 특산물 레시피북
  06_life_gear.json     건축·명승 유산의 《답사록》
  14_skills.json        서책 패시브 스킬
사용: python3 tools/build_world.py [--report] [--period]  (--period = anachronism_policy replace 로 1회 빌드)
"""
import math
import random
import sys

from common import SRC, gear_stats, load, price, romanize, save
import json

MAP_W, MAP_H = 3840, 2160
PX_PER_LI = 20.0                 # 완전판 4.2: 10리 = 200px
OW_LI = 2750.0                   # 전국 지도 세로 1.0 = 약 2,750리(≈1,100km)
BORDER_LINK_RATIO = 0.4          # 권역 중심 간 거리 중 국경 구간 비율
MOUNTAIN_REGIONS = {"MAP_03", "MAP_04", "MAP_05", "MAP_14", "MAP_15", "MAP_16"}
TYPE_CODE = {"city": "CITY", "town": "TOWN", "station": "STATION", "temple": "TEMPLE", "spring": "SPRING", "fort": "FORT",
             "beacon": "BEACON", "stupa": "STUPA", "tomb": "TOMB", "scenic": "SCENIC", "wreck": "WRECK", "ruin": "RUIN",
             "seowon": "SEOWON", "shrine": "SHRINE", "hazard": "HAZARD"}
MOUNTAIN_TYPES = {"temple", "fort", "scenic", "stupa", "hazard", "beacon", "shrine"}

W = json.loads((SRC / "world_table.json").read_text(encoding="utf-8"))
IMP_PATH = SRC / "heritage450" / "import.json"   # tools/import_heritage450.py 생성(국가유산 448 · 공식/이벤트 노드)
IMP = json.loads(IMP_PATH.read_text(encoding="utf-8")) if IMP_PATH.exists() else {"nodes": [], "heritage": [], "official_links": {}}
H = json.loads((SRC / "heritage_curated.json").read_text(encoding="utf-8"))


def short(name):
    return name.split()[0] if " " in name else name


# ---------------------------------------------------------------- 노드 생성
def build_nodes():
    nodes, used_ids, by_name = [], set(), {}

    def make(region, name, ntype, hidden=False, source="doc", note="", parent=None, lore="역사"):
        nn = region[-2:]
        base = f"ND_{nn}_{TYPE_CODE[ntype]}_{romanize(name)}"
        nid, k = base, 2
        while nid in used_ids:
            nid, k = f"{base}_{k}", k + 1
        used_ids.add(nid)
        fac = list(W["type_facilities"][ntype]) + W["extra_facilities"].get(name, [])
        if name in W["coastal"]:
            fac.append("ferry")
        n = {"id": nid, "name": name, "region": region, "type": ntype, "type_label": W["type_labels"][ntype],
             "hidden": hidden, "pos": [0, 0], "facilities": sorted(set(fac)), "source": source, "lore": lore}
        if note:
            n["note"] = note
        if name in W["anachronism"]:
            a = W["anachronism"][name]
            n["anachronism"] = a["issue"] if isinstance(a, dict) else a
            if isinstance(a, dict):
                n["period_candidates"] = [c["name"] for c in a["candidates"]]
        if parent:
            n["_parent"] = parent
        nodes.append(n)
        key = (region, name)
        by_name[key] = n
        by_name.setdefault(name, n)
        return n

    for r in W["regions"]:
        rid = r["id"]
        for ntype in ("city", "town", "station", "temple"):
            for name in r[ntype]:
                ov = W["overrides"].get(name, {})
                make(rid, ov.get("rename", name), ov.get("type", ntype), note=ov.get("note", ""))
        for name in r["misc"]:
            ov = W["overrides"].get(name, {})
            make(rid, ov.get("rename", name), ov.get("type", W["misc_default_type"]), note=ov.get("note", ""))
        make(rid, W["beacons"][rid], "beacon", source="added", note="원문 표에 봉수 노드가 없어 권역당 1개 추가(명칭 고증 필요)")
    for h in W["hidden"]:
        make(h["region"], h["name"], h["type"], hidden=True, source="added", parent=h["parent"], lore=h.get("lore", "역사"))
    # 국가유산 448 반영분: 공식 노드(중복 제외) + 유산 자리 노드(가시·은닉). 기존 노드 id·순서는 그대로
    for x in IMP["nodes"]:
        n = make(x["region"], x["name"], x["type"], hidden=x["hidden"], source="heritage450", note=x.get("note", ""),
                 parent=x.get("parent"))
        n["facilities"] = sorted(set(n["facilities"]) | set(x.get("facilities_extra", [])))
        for k in ("official", "discover"):
            if k in x:
                n[k] = x[k]
        if x.get("source_heritage"):
            n["_imported_site"] = True
    for n in nodes:
        if n["id"] in IMP["official_links"]:
            n["official"] = IMP["official_links"][n["id"]]
    return nodes, by_name


GEO = json.loads((SRC / "node_geo.json").read_text(encoding="utf-8")) if (SRC / "node_geo.json").exists() else {}
GEO_MARGIN = (260, 220)      # 지도 가장자리 여백(px) — 국경 통로·UI 공간
GEO_MIN_GAP = 150            # 가시 노드 최소 간격(px) = 7.5리. 실제 위치가 더 가까우면 밀어냄(한양 도성 안 여러 노드 등)
GEO_HIDDEN_RANGE = (150, 420)
GEO_HIDDEN_GAP = 90          # 은닉 노드 최소 간격(px)  # 은닉 노드 ↔ 부모 거리(px). 탐색 반경 13~33리 규칙이 성립하도록 방향은 유지·거리만 이 범위로
KM_PER_DEG_LAT = 110.57


def geo_projection(pts):
    """권역 노드 위경도 → 등거리 원통 투영(권역 중심 위도의 cos 로 경도 보정) · 3840×2160 여백 안에 가득 차도록 축척."""
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    lat0 = (min(lats) + max(lats)) / 2
    kx = 111.32 * math.cos(math.radians(lat0))
    w_km = (max(lons) - min(lons)) * kx
    h_km = (max(lats) - min(lats)) * KM_PER_DEG_LAT
    mx, my = GEO_MARGIN
    km_per_px = max(w_km / (MAP_W - 2 * mx), h_km / (MAP_H - 2 * my), 0.005)
    # 지도 중앙 = 노드 범위의 중앙
    lonc = (min(lons) + max(lons)) / 2
    return {"lat0": round(lat0, 5), "lon_c": round(lonc, 5), "lat_c": round(lat0, 5), "km_per_px": round(km_per_px, 5),
            "kx": round(kx, 4), "ky": KM_PER_DEG_LAT, "map_size": [MAP_W, MAP_H]}


def geo_to_px(pr, lat, lon):
    x = MAP_W / 2 + (lon - pr["lon_c"]) * pr["kx"] / pr["km_per_px"]
    y = MAP_H / 2 - (lat - pr["lat_c"]) * pr["ky"] / pr["km_per_px"]
    return [x, y]


def place_geo(nodes, r):
    """실제 좌표 배치. 반환: 투영 파라미터(regions.json 에 기록 → tools/gen_terrain.py 가 같은 투영으로 지형을 그림)."""
    table = GEO[r["id"]]
    mine = [n for n in nodes if n["region"] == r["id"]]
    pr = geo_projection([table[n["name"]] for n in mine])
    for n in mine:
        lat, lon, conf = table[n["name"]]
        n["geo"] = [lat, lon]
        n["geo_conf"] = conf
        n["_true"] = geo_to_px(pr, lat, lon)
        n["pos"] = list(n["_true"])
    vis = [n for n in mine if not n["hidden"]]
    mx, my = GEO_MARGIN
    for _ in range(300):  # 최소 간격 확보(겹친 쌍을 서로 반씩 밀어냄) + 원위치로 약하게 복원
        moved = False
        for i, a in enumerate(vis):
            for b in vis[i + 1:]:
                dx, dy = b["pos"][0] - a["pos"][0], b["pos"][1] - a["pos"][1]
                d = math.hypot(dx, dy)
                if d < GEO_MIN_GAP:
                    if d < 1e-6:
                        ang = (sum(map(ord, a["id"] + b["id"])) % 360) * math.pi / 180
                        dx, dy, d = math.cos(ang), math.sin(ang), 1.0
                    push = (GEO_MIN_GAP - d) / 2 + 0.5
                    a["pos"][0] -= dx / d * push
                    a["pos"][1] -= dy / d * push
                    b["pos"][0] += dx / d * push
                    b["pos"][1] += dy / d * push
                    moved = True
        for n in vis:
            n["pos"][0] = min(MAP_W - mx / 2, max(mx / 2, n["pos"][0]))
            n["pos"][1] = min(MAP_H - my / 2, max(my / 2, n["pos"][1]))
        if not moved:
            break
    by = {n["name"]: n for n in mine}
    for n in mine:
        if not n["hidden"]:
            continue
        par = by[n["_parent"]]
        if par["hidden"] and "_placed" not in par:
            continue
        dx, dy = n["_true"][0] - par["_true"][0], n["_true"][1] - par["_true"][1]
        d = math.hypot(dx, dy)
        lo, hi = GEO_HIDDEN_RANGE
        if d < 1e-6:
            dx, dy, d = 1.0, 0.0, 1.0
        k = min(hi, max(lo, d)) / d
        n["pos"] = [par["pos"][0] + dx * k, par["pos"][1] + dy * k]
        n["_placed"] = True
    for n in mine:  # 은닉의 부모가 은닉인 경우(천황봉→신도안) 두 번째 패스
        if n["hidden"] and "_placed" not in n:
            par = by[n["_parent"]]
            dx, dy = n["_true"][0] - par["_true"][0], n["_true"][1] - par["_true"][1]
            d = math.hypot(dx, dy) or 1.0
            k = min(GEO_HIDDEN_RANGE[1], max(GEO_HIDDEN_RANGE[0], d)) / d
            n["pos"] = [par["pos"][0] + dx * k, par["pos"][1] + dy * k]
    hid = [n for n in mine if n["hidden"]]
    lo, hi = GEO_HIDDEN_RANGE
    for _ in range(200):   # 은닉 노드끼리·가시 노드와 최소 간격(국가유산 반영으로 한 고을 주변 은닉지가 여럿)
        moved = False
        for a in hid:
            for b in mine:
                if a is b:
                    continue
                dx, dy = a["pos"][0] - b["pos"][0], a["pos"][1] - b["pos"][1]
                d = math.hypot(dx, dy)
                if d < GEO_HIDDEN_GAP:
                    if d < 1e-6:
                        ang = (sum(map(ord, a["id"])) % 360) * math.pi / 180
                        dx, dy, d = math.cos(ang), math.sin(ang), 1.0
                    push = (GEO_HIDDEN_GAP - d) * (0.5 if b["hidden"] else 1.0) + 0.5
                    a["pos"][0] += dx / d * push
                    a["pos"][1] += dy / d * push
                    moved = True
            par = by[a["_parent"]]
            dx, dy = a["pos"][0] - par["pos"][0], a["pos"][1] - par["pos"][1]
            d = math.hypot(dx, dy) or 1.0
            k = min(hi + 40, max(lo, d)) / d
            a["pos"] = [par["pos"][0] + dx * k, par["pos"][1] + dy * k]
        if not moved:
            break
    for n in mine:
        n["pos"] = [round(min(MAP_W - 60, max(60, n["pos"][0]))), round(min(MAP_H - 60, max(60, n["pos"][1])))]
        n["geo_shift_km"] = round(math.dist(n["pos"], n["_true"]) * pr["km_per_px"], 2)
        n.pop("_true", None)
        n.pop("_placed", None)
    return pr


def place(nodes, regions):
    """data_src/node_geo.json 에 좌표가 모두 있는 권역은 실제 위치로, 아니면 자동 배치(임시)."""
    PROJ.clear()
    for r in regions:
        tab = GEO.get(r["id"], {})
        if tab and all(n["name"] in tab for n in nodes if n["region"] == r["id"]):
            PROJ[r["id"]] = place_geo(nodes, r)
    auto = [r for r in regions if r["id"] not in PROJ]
    if auto:
        missing = [n["name"] for n in nodes if n["region"] in {r["id"] for r in auto} and n["name"] not in GEO.get(n["region"], {})]
        print(f"[배치] 실제 좌표 없는 권역 {len(auto)}곳 자동 배치 — 누락 노드 {len(missing)}: {', '.join(missing[:12])}")
    place_auto(nodes, auto)


PROJ = {}


def place_auto(nodes, regions):
    for r in regions:
        rng = random.Random(int(r["id"][-2:]) * 7919)
        vis = [n for n in nodes if n["region"] == r["id"] and not n["hidden"]]
        vis.sort(key=lambda n: ["city", "station", "town", "fort", "temple", "spring", "scenic", "wreck", "ruin", "hazard", "beacon"].index(n["type"]) if n["type"] in ["city", "station", "town", "fort", "temple", "spring", "scenic", "wreck", "ruin", "hazard", "beacon"] else 99)
        placed = []
        for n in vis:
            best = None
            for _ in range(400):
                p = (rng.uniform(260, MAP_W - 260), rng.uniform(220, MAP_H - 220))
                d = min((math.dist(p, q) for q in placed), default=9999)
                if d >= 330:
                    best = p
                    break
                if best is None or d > min((math.dist(best, q) for q in placed), default=0):
                    best = p
            placed.append(best)
            n["pos"] = [round(best[0]), round(best[1])]
    auto_ids = {r["id"] for r in regions}
    by = {(n["region"], n["name"]): n for n in nodes}
    pending = [n for n in nodes if n["hidden"] and n["region"] in auto_ids]
    for _ in range(3):  # 은닉 노드의 부모가 은닉 노드인 경우(천황봉→신도안) 순서 해결
        for n in pending:
            par = by[(n["region"], n["_parent"])]
            if par["pos"] == [0, 0]:
                continue
            rng = random.Random(sum(map(ord, n["id"])) * 31)
            a, rad = rng.uniform(0, math.tau), rng.uniform(190, 320)
            n["pos"] = [round(min(MAP_W - 120, max(120, par["pos"][0] + math.cos(a) * rad))),
                        round(min(MAP_H - 120, max(120, par["pos"][1] + math.sin(a) * rad)))]


def apply_anachronism_policy(nodes):
    """replace 정책: 좌표·id(슬롯)는 그대로 두고 이름·유형·시설만 1순위 후보로 교체."""
    if W.get("anachronism_policy", "keep") != "replace":
        return []
    done = []
    for n in nodes:
        a = W["anachronism"].get(n["name"])
        if not isinstance(a, dict) or not a["candidates"] or a["candidates"][0]["name"].startswith("("):
            continue
        c = a["candidates"][0]
        old = n["name"]
        n.update({"name": c["name"], "renamed_from": old, "type": c["type"], "type_label": W["type_labels"][c["type"]], "note": c["basis"]})
        fac = list(W["type_facilities"][c["type"]]) + (["ferry"] if "ferry" in n["facilities"] else []) + c.get("add_facilities", [])
        if c.get("lore"):
            n["lore"] = c["lore"]
        n["facilities"] = sorted(set(fac))
        if c["type"] in ("stupa", "tomb", "wreck", "ruin", "seowon", "shrine"):
            n["hidden"] = False  # 원문 가시 노드 슬롯이었으므로 가시 유지
        n.pop("anachronism", None)
        done.append((old, c["name"], c["type"]))
    return done


def placement_report(nodes):
    """권역별 노드 밀도·최근접 간격과, 고증 문제 노드 슬롯이 담당하는 역할(빠질 경우 생기는 공백·유형 수 변화)."""
    lines = []
    for r in W["regions"]:
        vis = [n for n in nodes if n["region"] == r["id"] and not n["hidden"]]
        nn = []
        for n in vis:
            d = min(math.dist(n["pos"], m["pos"]) for m in vis if m is not n)
            nn.append(d)
        lines.append(f"  {r['id']} {r['name']:<6} 가시 {len(vis):>2} · 최근접 간격 중앙 {sorted(nn)[len(nn)//2]/PX_PER_LI:4.1f}리 (최소 {min(nn)/PX_PER_LI:4.1f})")
        for n in vis:
            if not n.get("anachronism") and not n.get("renamed_from"):
                continue
            others = [m for m in vis if m is not n]
            gap = min(math.dist(n["pos"], m["pos"]) for m in others) / PX_PER_LI
            near = sum(1 for m in others if math.dist(n["pos"], m["pos"]) < 600) 
            same = sum(1 for m in others if m["type"] == n["type"])
            lines.append(f"      ↳ [{n['type_label']}] {n.get('renamed_from', n['name'])}{' → ' + n['name'] if n.get('renamed_from') else ''}: "
                         f"빠지면 반경 {gap:4.1f}리 공백 · 30리 안 이웃 {near}곳 · 권역 내 같은 유형 {same}곳 남음"
                         + (f" · 후보 {', '.join(n.get('period_candidates', []))}" if n.get("period_candidates") else ""))
    return lines


def edge_terrain(a, b):
    if "wreck" in (a["type"], b["type"]):
        return "water"
    if a["type"] in MOUNTAIN_TYPES or b["type"] in MOUNTAIN_TYPES:
        return "mountain"
    return "road"


def build_edges(nodes, regions):
    edges, seen = [], set()
    by = {(n["region"], n["name"]): n for n in nodes}

    def add(a, b, kind="road"):
        key = tuple(sorted((a["id"], b["id"])))
        if key in seen or a is b:
            return
        seen.add(key)
        d = math.dist(a["pos"], b["pos"])
        edges.append({"a": a["id"], "b": b["id"], "li": round(d / PX_PER_LI, 1), "terrain": edge_terrain(a, b), "kind": kind})

    for r in regions:
        vis = [n for n in nodes if n["region"] == r["id"] and not n["hidden"]]
        # Prim MST
        inside, rest = [vis[0]], vis[1:]
        while rest:
            a, b = min(((x, y) for x in inside for y in rest), key=lambda p: math.dist(p[0]["pos"], p[1]["pos"]))
            add(a, b)
            inside.append(b)
            rest.remove(b)
        for n in vis:  # 순환로: 최근접 2개
            for m in sorted((m for m in vis if m is not n), key=lambda m: math.dist(n["pos"], m["pos"]))[:2]:
                add(n, m)
    for n in nodes:
        if n["hidden"]:
            add(n, by[(n["region"], n["_parent"])], "trail")
    return edges


def build_borders(nodes, regions):
    rmap = {r["id"]: r for r in regions}
    links, done = [], set()
    for r in regions:
        for other in r["adjacent"]:
            key = tuple(sorted((r["id"], other)))
            if key in done:
                continue
            done.add(key)
            a, b = rmap[key[0]], rmap[key[1]]

            def gate(src, dst):
                dx, dy = dst["ow"][0] - src["ow"][0], dst["ow"][1] - src["ow"][1]
                L = math.hypot(dx, dy) or 1
                target = (MAP_W / 2 + dx / L * MAP_W * 0.45, MAP_H / 2 + dy / L * MAP_H * 0.45)
                cand = [n for n in nodes if n["region"] == src["id"] and not n["hidden"] and n["type"] in ("city", "town", "station", "fort")]
                return min(cand, key=lambda n: math.dist(n["pos"], target))
            ga, gb = gate(a, b), gate(b, a)
            li = round(math.dist(a["ow"], b["ow"]) * OW_LI * BORDER_LINK_RATIO)
            terr = "mountain" if (a["id"] in MOUNTAIN_REGIONS or b["id"] in MOUNTAIN_REGIONS) else "road"
            links.append({"a": ga["id"], "b": gb["id"], "li": li, "terrain": terr, "kind": "border", "regions": [a["id"], b["id"]]})
            ga.setdefault("border_to", []).append(b["id"])
            gb.setdefault("border_to", []).append(a["id"])
    return links


def build_sea(nodes):
    by = {n.get("renamed_from", n["name"]): n for n in nodes}
    out = []
    for s in W["sea_routes"]:
        a, b = by[s["a"]], by[s["b"]]
        out.append({"a": a["id"], "b": b["id"], "fare": s["fare"], "days": s["days"], "wind_sensitive": s.get("wind_sensitive", False), "kind": "ferry"})
    return out


# ---------------------------------------------------------------- 유산 + 보상 아이템
RECORD_BUFF = {  # node type → (버프 키, 등급당 값)
    "city": ("trade_price", 0.012), "fort": ("def_pct", 0.015), "temple": ("res_all", 0.01),
    "scenic": ("fatigue_gain", -0.03), "ruin": ("reputation_gain", 0.012), "stupa": ("res_all", 0.012),
    "town": ("reputation_gain", 0.01),
}
JEJU_TOWN = "방사탑"   # 제주 마을 수호 돌탑(방사탑)·돌하르방


def town_landmark(n):
    """고을(town) 1등급 유산 이름 — 고을마다 있던 마을 수호물(장승·서낭당), 제주는 방사탑"""
    return f"{n['name']} {JEJU_TOWN}" if n["region"] == "MAP_17" else f"{n['name']} 장승·서낭당"

TOMB_ITEMS = [("accessory", "금동관"), ("weapon", "환두대도"), ("armor", "찰갑")]


def build_heritage(nodes):
    by = {(n["region"], n["name"]): n for n in nodes}
    by_name = {n.get("renamed_from", n["name"]): n for n in nodes}
    heritage, gen = [], {"items": [], "records": [], "specialties": [], "recipes": [], "skills": []}
    used_nodes = set()
    for c in H["curated"]:
        n = by_name[c["node"]]
        row = dict(c)
        row.update({"node": n["id"], "region": n["region"], "hidden": n["hidden"], "node_type": n["type"]})
        heritage.append(row)
        used_nodes.add(n["id"])
        n["heritage"] = c["id"]
    idx, tomb_i = len(heritage) + 1, 0
    by_rn = {(n["region"], n["name"]): n for n in nodes}
    imp_nodes = set()
    for x in IMP["heritage"]:
        imp_nodes.add(by_rn[(x["region"], x["node_name"])]["id"])
    # 고을(town) 1등급 유산은 기존 유산 id(her_001~144)를 바꾸지 않도록 맨 뒤에 번호를 매긴다.
    # 국가유산 448 반영 노드는 그 뒤(기존 id 불변). 국가유산이 놓인 새 노드는 자동 유산을 만들지 않는다
    basen = [n for n in nodes if n.get("source") != "heritage450"]
    newn = [n for n in nodes if n.get("source") == "heritage450" and n["id"] not in imp_nodes]
    order = [n for n in basen if n["type"] != "town"] + [n for n in basen if n["type"] == "town"] + newn
    for n in order:
        if n["id"] in used_nodes or n["type"] not in H["type_category"]:
            continue
        cat = H["type_category"][n["type"]]
        if n["type"] == "ruin" and H["ruin_kiln_keyword"] in n["name"]:
            cat = "ceramic_specialty"
        tier = H["tier_overrides"].get(n["name"], H["type_tier"][n["type"]])
        hid = f"her_{idx:03d}"
        idx += 1
        s = short(n["name"])
        hname = town_landmark(n) if n["type"] == "town" else n["name"]
        if cat in ("architecture", "scenic"):
            key, per = RECORD_BUFF.get(n["type"], ("reputation_gain", 0.012))
            rid = f"rec_{hid}"
            gen["records"].append({"id": rid, "name": f"《{hname} 답사록》", "slot": "record", "tier": tier,
                                   "icon": "icon_scroll_jokja.png", "buffs": {key: round(per * tier, 3)}, "generated": "heritage"})
            if n["type"] == "scenic":
                gen["records"][-1]["permanent_hp"] = 1
            reward = rid
        elif cat == "metal":
            if n["type"] == "stupa":
                slot, label, fam = "accessory", "사리장엄구", "bul"
            else:
                slot, label = TOMB_ITEMS[tomb_i % 3]
                fam = "none"
                tomb_i += 1
            reward = f"eq_{hid}"
            gen["items"].append({"id": reward, "name": f"{s} {label}", "slot": slot, "tier": tier, "family": fam,
                                 "element": "metal" if slot == "weapon" else "none", "stats": gear_stats(slot, tier, fam, 0.9),
                                 "acquire": {"type": "heritage", "heritage": hid}, "generated": "heritage"})
        elif cat == "folk_craft":
            reward = f"eq_{hid}"
            gen["items"].append({"id": reward, "name": f"{s} 벽사 패물", "slot": "accessory", "tier": tier, "family": "none",
                                 "element": "holy", "stats": gear_stats("accessory", tier, "none", 1.0),
                                 "acquire": {"type": "heritage", "heritage": hid}, "generated": "heritage"})
        elif cat == "document":
            reward, sk = f"eq_{hid}", f"sk_pas_{hid}"
            know = {"yu": 1 + tier // 3}
            if n["type"] == "seowon" and "오죽헌" in n["name"]:
                know = {"yu": 1 + tier // 3, "sa": 1}
            gen["skills"].append({"id": sk, "name": f"{s} 학통", "owner": "passive", "target": "self", "element": "none",
                                  "power": 0.0, "ap_cost": 0, "cooldown": 0,
                                  "effects": {"passive": {"def_pct": round(0.01 * tier, 3), "knowledge": know}}, "generated": "heritage"})
            gen["items"].append({"id": reward, "name": f"《{s} 문집》", "slot": "book", "tier": tier, "family": "yu", "element": "none",
                                 "stats": {}, "passive_skill": sk, "acquire": {"type": "heritage", "heritage": hid}, "generated": "heritage"})
        else:  # ceramic_specialty
            spid, reward = f"sp_{hid}", f"spr_{hid}"
            label = "해저 인양 청자" if n["type"] == "wreck" else "복원 도자"
            gen["specialties"].append({"id": spid, "name": f"{s} {label}", "region": n["region"], "node": n["id"], "kind": "crafted",
                                       "tier": tier, "base_price": price("specialty_crafted", tier), "dev_level": 0, "generated": "heritage"})
            mats = [{"id": "mat_white_clay", "qty": 3}, {"id": "mat_charcoal", "qty": 4}] if tier <= 3 else \
                   [{"id": "mat_celadon_clay", "qty": 3}, {"id": "mat_charcoal", "qty": 5}, {"id": "mat_lacquer", "qty": 1}]
            gen["recipes"].append({"id": reward, "name": f"【{s} 복원 비전서】", "tier": tier, "produces": spid, "facility": "gongbang",
                                   "materials": mats, "generated": "heritage"})
        heritage.append({"id": hid, "name": hname, "node": n["id"], "region": n["region"], "category": cat, "tier": tier,
                         "reward": reward, "hidden": n["hidden"], "node_type": n["type"], "lore": n.get("lore", "역사")})
        n["heritage"] = hid
    heritage += build_imported(nodes, heritage, gen, by_rn)
    per_node = {}
    for h in heritage:
        per_node.setdefault(h["node"], []).append(h["id"])
    for n in nodes:
        if n["id"] in per_node:
            n["heritage"] = per_node[n["id"]][0]
            if len(per_node[n["id"]]) > 1:
                n["heritage_ids"] = per_node[n["id"]]
    for h in heritage:
        h["public_data"] = {"provider": "국가유산청", "license": "공공누리 제1유형(출처표시)",
                            "ccbaKdcd": "", "ccbaAsno": "", "ccbaCtcd": "", "source_url": "", "description": ""}
    return heritage, gen


IMP_RECORD_BUFF = {"architecture": ("reputation_gain", 0.012), "scenic": ("fatigue_gain", -0.03)}
IMP_FAMILY = {"yu": "yu", "bul": "bul", "seon": "seon"}


def imported_tiers(imported, others):
    """국가유산 448: 원본 등급(3~5만 존재)·고정 보상 대신, 전체 유산 등급 분포가 content_plan.heritage 모양이 되도록
    지정 종별 점수 순으로 1~5등급 배정 → 보상은 economy 공식, 신분 임계는 economy_sim 이 재보정."""
    shape = load("00_overview.json")["content_plan"]["heritage"]
    total = len(imported) + len(others)
    fixed = [sum(1 for h in others if h["tier"] == t) for t in range(1, 6)]
    quota = [max(0, round(total * shape[t] / sum(shape)) - fixed[t]) for t in range(5)]
    diff = len(imported) - sum(quota)
    quota[0] += diff        # 반올림 차이는 1등급에서 흡수
    ranked = sorted(imported, key=lambda x: (-x["score"], x["name"]))
    tiers, i = {}, 0
    for t in (5, 4, 3, 2, 1):
        for x in ranked[i:i + max(0, quota[t - 1])]:
            tiers[x["id"]] = t
        i += max(0, quota[t - 1])
    for x in ranked:
        tiers.setdefault(x["id"], 1)
    return tiers


def build_imported(nodes, others, gen, by_rn):
    out = []
    tiers = imported_tiers(IMP["heritage"], others)
    for x in IMP["heritage"]:
        n = by_rn[(x["region"], x["node_name"])]
        hid, tier, cat, name = x["id"], tiers[x["id"]], x["category"], x["name"]
        fam = IMP_FAMILY.get(x.get("faction", ""), "none")
        if cat in ("architecture", "scenic"):
            key, per = IMP_RECORD_BUFF[cat] if cat == "scenic" else RECORD_BUFF.get(n["type"], IMP_RECORD_BUFF["architecture"])
            reward = f"rec_{hid}"
            gen["records"].append({"id": reward, "name": f"《{name} 답사록》", "slot": "record", "tier": tier, "icon": "icon_scroll_jokja.png",
                                   "buffs": {key: round(per * tier, 3)}, "generated": "heritage", **({"permanent_hp": 1} if cat == "scenic" else {})})
        elif cat in ("metal", "folk_craft"):
            reward = f"eq_{hid}"
            label = "원불(願佛)" if x.get("category_kr") == "불상" else ("모각 의장품" if cat == "metal" else "벽사 패물")
            gen["items"].append({"id": reward, "name": f"{name} {label}", "slot": "accessory", "tier": tier, "family": fam,
                                 "element": "metal" if cat == "metal" else "holy", "stats": gear_stats("accessory", tier, fam, 0.9 if cat == "metal" else 1.0),
                                 "acquire": {"type": "heritage", "heritage": hid}, "generated": "heritage"})
        elif cat == "document":
            reward, sk = f"eq_{hid}", f"sk_pas_{hid}"
            k = fam if fam in ("yu", "bul", "seon") else "yu"
            gen["skills"].append({"id": sk, "name": f"{name.split()[0]} {name.split()[-1]} 학통"[:24], "owner": "passive", "target": "self",
                                  "element": "none", "power": 0.0, "ap_cost": 0, "cooldown": 0,
                                  "effects": {"passive": {"def_pct": round(0.01 * tier, 3), "knowledge": {k: 1 + tier // 3}}}, "generated": "heritage"})
            gen["items"].append({"id": reward, "name": f"《{name}》 필사본", "slot": "book", "tier": tier, "family": k, "element": "none",
                                 "stats": {}, "passive_skill": sk, "acquire": {"type": "heritage", "heritage": hid}, "generated": "heritage"})
        else:  # ceramic_specialty
            spid, reward = f"sp_{hid}", f"spr_{hid}"
            gen["specialties"].append({"id": spid, "name": f"{name} 재현품", "region": n["region"], "node": n["id"], "kind": "crafted",
                                       "tier": tier, "base_price": price("specialty_crafted", tier), "dev_level": 0, "generated": "heritage",
                                       "real_name": name, "desc": x.get("desc", "")})
            mats = [{"id": "mat_white_clay", "qty": 3}, {"id": "mat_charcoal", "qty": 4}] if tier <= 3 else \
                   [{"id": "mat_celadon_clay", "qty": 3}, {"id": "mat_charcoal", "qty": 5}, {"id": "mat_lacquer", "qty": 1}]
            gen["recipes"].append({"id": reward, "name": f"【{name} 재현 비전서】", "tier": tier, "produces": spid, "facility": "gongbang",
                                   "materials": mats, "generated": "heritage"})
        row = {"id": hid, "name": name, "node": n["id"], "region": n["region"], "category": cat, "tier": tier, "reward": reward,
               "hidden": n["hidden"], "node_type": n["type"], "lore": x.get("lore", "역사"), "faction": x.get("faction", ""),
               "designation": x["designation"], "desc": x.get("desc", ""), "source": "heritage450", "src_tier": x["src_tier"]}
        if x.get("template"):
            row["orig_name"] = x["orig_name"]
        out.append(row)
    return out


def merge(file, key, rows, tag="heritage"):
    doc = load(file)
    keep = [r for r in doc[key] if r.get("generated") != tag]
    doc[key] = keep + rows
    save(file, doc)


def main():
    if "--period" in sys.argv:
        W["anachronism_policy"] = "replace"
    regions = W["regions"]
    nodes, _ = build_nodes()
    place(nodes, regions)          # 좌표는 원문 명칭·유형으로 먼저 확정(슬롯 고정)
    replaced = apply_anachronism_policy(nodes)
    edges = build_edges(nodes, regions)
    borders = build_borders(nodes, regions)
    sea = build_sea(nodes)
    heritage, gen = build_heritage(nodes)
    for n in nodes:
        n.pop("_parent", None)
    hub = {}
    for n in nodes:
        if n["type"] == "city" and n["region"] not in hub:
            hub[n["region"]] = n["id"]
    out_regions = []
    for r in regions:
        rid = r["id"].lower()
        out_regions.append({"id": r["id"], "name": r["name"], "overworld_pos": r["ow"], "rice_price": r["rice"],
                            "climate": r["climate"], "adjacent": r["adjacent"], "daedong_sheets": r["sheets"], "hub": hub[r["id"]],
                            "sea_only": not r["adjacent"],
                            "map_texture": f"res://assets/maps/regions/{rid}.png",
                            "mask_texture": f"res://assets/maps/masks/{rid}_mask.png",
                            "parallax_dir": f"res://assets/parallax/{rid}/",
                            **({"geo_projection": PROJ[r["id"]]} if r["id"] in PROJ else {})})
    save("regions.json", {
        "_schema": "build_world.py 생성물(직접 수정 금지 → data_src 수정 후 재빌드). 17권역(MAP_01~17) · nodes(7상시+7은닉+확장 hazard) · edges(권역 내 도로/오솔길) · border_links(인접 권역 국경) · sea_routes(나루터 뱃길). pos=권역 지도 px(3840×2160, 10리=200px). geo=[위도,경도](data_src/node_geo.json) → regions[].geo_projection 으로 투영(최소 간격 7.5리를 위해 밀린 거리 geo_shift_km).",
        "map_size": [MAP_W, MAP_H], "px_per_li": PX_PER_LI,
        "regions": out_regions, "nodes": nodes, "edges": edges, "border_links": borders, "sea_routes": sea})
    doc = load("01_heritage.json")
    doc["heritage"] = heritage
    doc["_schema"] = ("01_국가유산. build_world.py 생성(수작업: data_src/heritage_curated.json). category→보상형태: architecture/scenic=답사록, "
                      "ceramic_specialty=특산물 레시피북, folk_craft=장신구, metal=장착 장비, document=서책. 기증/매각 수치는 economy 공식으로 런타임 산출. "
                      "public_data=국가유산청 공공데이터(공공누리 제1유형) 연동 필드.")
    doc["category_reward_map"]["scenic"] = "record"
    save("01_heritage.json", doc)
    merge("06_life_gear.json", "life_gear", gen["records"])
    merge("02_equipment.json", "items", gen["items"])
    merge("03_specialties.json", "specialties", gen["specialties"])
    merge("03_specialties.json", "specialty_recipes", gen["recipes"])
    merge("14_skills.json", "skills", gen["skills"])
    cnt = {}
    for n in nodes:
        cnt[n["type"]] = cnt.get(n["type"], 0) + 1
    print(f"regions {len(out_regions)} · nodes {len(nodes)} {cnt}")
    print(f"edges {len(edges)} · border {len(borders)} · sea {len(sea)} · heritage {len(heritage)}")
    print("generated:", {k: len(v) for k, v in gen.items()})
    print(f"고증 정책: {W.get('anachronism_policy', 'keep')}" + (f" — 교체 {len(replaced)}건: " + ", ".join(f"{a}→{b}({t})" for a, b, t in replaced) if replaced else ""))
    if "--report" in sys.argv:
        print("\n══ 배치 리포트 (좌표가 임시 자동배치인 동안은 참고용 — 실제 지도 좌표 입력 후 재실행)")
        print("\n".join(placement_report(nodes)))


if __name__ == "__main__":
    main()
