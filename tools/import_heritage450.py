#!/usr/bin/env python3
"""국가유산 448종 · 이벤트 노드 306 · 공식 노드 214 반영기 (data_src/heritage450/*.xlsx).

  1) 읽기·정리: 빈 행 제거, 이벤트 이름 접두어("[절경/유적] … 발굴지") 정리, 파일 내부 중복(이름·좌표·유사명) 검사
  2) 권역 판정: 게임 기존 노드(위경도) 가중 최근접 5곳 투표 — 제주는 위도로 고정
  3) 좌표 검사: 실제 고도(SRTM 30m·GTOPO30)로 바다 위 여부 → 반경 3km 안 가장 가까운 육지로 자동 보정(해저 유산 제외)
  4) 공식 노드 ↔ 게임 노드 중복 판정(같은 유형군 2.5km 안, 또는 같은 지명 6km 안) → 병합(기존 id 유지), 좌표 차이 1km↑는 충돌로 표기하고
     공식 좌표(육지·같은 권역)로 data_src/node_geo.json 수정. 중복이 아니면 새 가시 노드
  5) 유산 배치: 이벤트 노드가 있으면 그 자리(0.5km 안에 노드가 있으면 그 노드, 없으면 새 은닉 노드 = 발견 기능·조건 부여),
     없으면 3km 안 노드에 함께 두고(한 노드 여러 유산), 그것도 없으면 새 가시 노드
  6) 등급·보상: 원본 명성/엽전 고정값(300/150 …)은 쓰지 않는다. 지정 종별 가중 점수 → build_world 가 전체 유산 등급 분포를
     content_plan 모양에 맞춰 배정 → 보상은 economy 공식, 신분 임계는 economy_sim 재보정
출력: data_src/heritage450/import.json (build_world 가 읽음) · data_src/node_geo.json 보정 · docs/국가유산450_반영_점검.xlsx
사용: python3 tools/import_heritage450.py  (이후 build_world → … 파이프라인)
"""
import difflib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "db15"))
import xlsx_io  # noqa: E402
from common import DATA, ROOT, SRC  # noqa: E402

SRC450 = SRC / "heritage450"
OUT = SRC450 / "import.json"
REPORT = ROOT / "docs" / "국가유산450_반영_점검.xlsx"
GEO_PATH = SRC / "node_geo.json"

MATCH_SAME_CLASS_KM = 2.5
MATCH_SAME_NAME_KM = 6.0
COORD_CONFLICT_KM = 1.0
EVENT_MERGE_KM = 0.5
ATTACH_KM = 3.0
LAND_FIX_KM = 5.0

CLASS = {"city": "settle", "town": "settle", "station": "settle", "fort": "settle", "temple": "temple", "stupa": "temple",
         "spring": "spring", "tomb": "tomb", "scenic": "scenic", "ruin": "ruin", "seowon": "seowon", "shrine": "shrine",
         "beacon": "beacon", "wreck": "wreck", "hazard": "hazard"}
MASTER_TYPE = {"METROPOLIS": "city", "CITY": "town", "POST_STATION": "station", "TEMPLE": "temple", "SPA": "spring",
               "TOMB": "tomb", "FORTRESS_DEPOT": "fort"}
MASTER_FAC = {"OFFICE": "gwana", "HARBOR": "ferry", "REST": "jumak", "POST": "yeokcham", "TEMPLE": "temple", "SPA": "bath",
              "TOMB": "investigate", "SHRINE": "investigate"}
EVENT_TYPE = {"SCENIC_FOREST_VALLEY": "scenic", "SCENIC_WATERFALL_CAVE": "scenic", "SCENIC_PEAK": "scenic",
              "SCENIC_COAST_ISLAND": "scenic", "LOST_TEMPLE_PAGODA": "stupa", "HERMITAGE_ALTAR": "shrine",
              "ANCIENT_TOMB_TUMULUS": "tomb"}
SKILL = {"OBSERVE": "search", "GATHER": "gather", "CAMP": "camp", "HUNT": "hunt"}
GRADE_SA = {5: 0, 7: 1, 9: 2}          # 발견 등급 → 파티 사(士) 지식 요구(게임 지식 0~10 척도에 맞춤)
CATEGORY = {"석조미술": "architecture", "건축/사적": "architecture", "전적/고문서": "document", "회화/서예": "document",
            "도자공예": "ceramic_specialty", "금속공예": "metal", "불상": "folk_craft", "민속/공예": "folk_craft",
            "목조공예": "folk_craft"}
FACTION = {"유(儒)": "yu", "불(佛)": "bul", "선(仙)": "seon"}
DESIG_SCORE = {"세계기록유산": 10, "국보": 9, "국보급": 8, "보물": 7, "보물급": 6, "사적": 6, "명승": 5, "국가무형유산": 5,
               "시도유형문화유산": 4, "기념물": 4, "민속자료": 3, "유적": 3, "전적/고문서": 3}
TYPE_FOR_CATEGORY = {"석조미술": "stupa", "건축/사적": "ruin", "불상": "temple", "도자공예": "ruin", "금속공예": "ruin",
                     "전적/고문서": "seowon", "회화/서예": "seowon", "민속/공예": "shrine", "목조공예": "shrine"}


def km(a, b):
    dy = (a[0] - b[0]) * 110.57
    dx = (a[1] - b[1]) * 111.32 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dx, dy)


def norm(s):
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s)
    return re.sub(r"\s|관아|치소|읍성|역참|유수부|대도호부|도호부|감영|포구", "", s)


def stem(s):
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s).strip()
    return re.sub(r"(목|부|현|군|진|역|참)$", "", s.split()[0]) if s else ""


# 현대 지명 → 1861년 조선 지명(가제티어 조회·유산 이름 보정)
ALIAS = {"서울": "한양", "한양(서울)": "한양", "대전": "회덕", "포항": "영일", "청진": "부령", "나진": "경흥", "혜산": "갑산",
         "신흥": "함흥", "원산": "덕원", "개풍": "개성", "화성": "남양", "부산": "동래", "여수": "여수"}
MODERN = {"대전", "포항", "청진", "나진", "혜산", "신흥", "원산", "개풍", "화성", "부산", "서울"}
POST1861 = re.compile(r"개항|조약|주교|순교|성지|1866|1871|1876|양요")
ADMIN = re.compile(r"(대도호부|도호부|유수부|감영|목|부|현|군|진|역|참|읍|포구|치소)$")


def place_key(s):
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s).strip()
    return ADMIN.sub("", s.split()[0]) if s else ""


def full_key(s):
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s).strip()
    t = s.split()
    if t:
        t[0] = ADMIN.sub("", t[0])
    return "".join(t)


def rows(name):
    d = xlsx_io.read(SRC450 / f"{name}.xlsx")
    r = list(d.values())[0]
    head = r[0]
    return [dict(zip(head, x)) for x in r[1:] if any(v not in ("", None) for v in x)]


# ---------------------------------------------------------------- 지형(바다/육지)
class Land:
    def __init__(self):
        try:
            import gen_terrain as gt
            self.s = gt.SRTM(gt.RAW / "srtm")
            self.g = gt.GTOPO30(gt.RAW / "gtopo30")
            self.ok = bool(self.g.tiles)
        except Exception:
            self.ok = False

    def elev(self, la, lo):
        v = self.s.get(la, lo)
        return self.g.get(la, lo) if v is None else v

    def is_land(self, la, lo):
        """그 지점 고도 > 0.5m (tools/gen_terrain.py 의 '바다 위 노드' 판정과 같은 기준)"""
        if not self.ok:
            return True
        return self.elev(la, lo) > 0.5

    def nearest_land(self, la, lo, max_km=LAND_FIX_KM):
        if self.is_land(la, lo):
            return la, lo, 0.0
        best = None
        step = 0.003
        for r in range(1, int(max_km / 0.33) + 2):
            for i in range(-r, r + 1):
                for j in (-r, r):
                    for (a, b) in ((i, j), (j, i)):
                        p = (la + a * step, lo + b * step / math.cos(math.radians(la)))
                        if self.is_land(*p):
                            d = km((la, lo), p)
                            if d <= max_km and (best is None or d < best[2]):
                                best = (round(p[0], 4), round(p[1], 4), round(d, 2))
            if best:
                return best
        return None


def main():
    H, EV, NM = rows("heritage_450"), rows("event_nodes"), rows("nodes_master")
    for e in EV:
        e["clean"] = re.sub(r"\s*발굴지$", "", re.sub(r"^\[[^\]]*\]\s*", "", e["name_kr"])).strip()
    report = defaultdict(list)
    report["요약"].append(["항목", "값"])

    # ---- 1) 파일 내부 중복
    dup_in = [["파일", "A", "B", "거리(km)", "이름 유사도", "판정"]]
    for lab, lst, key in (("국가유산", H, "name_kr"), ("공식 노드", NM, "name_kr"), ("이벤트 노드", EV, "clean")):
        c = Counter(x[key] for x in lst)
        for k, v in c.items():
            if v > 1:
                dup_in.append([lab, k, k, 0, 1.0, "이름 중복 → 첫 행만 사용"])
        for i, a in enumerate(lst):
            for b in lst[i + 1:]:
                d = km((a["latitude"], a["longitude"]), (b["latitude"], b["longitude"]))
                s = difflib.SequenceMatcher(None, norm(a[key]), norm(b[key])).ratio()
                if d < 0.05 or (d < 1.0 and s > 0.7):
                    dup_in.append([lab, a[key], b[key], round(d, 2), round(s, 2), "좌표·이름이 거의 같음 → 첫 행만 사용"])
    seen = set()
    H2 = []
    for h in H:
        if h["name_kr"] in seen:
            continue
        seen.add(h["name_kr"])
        H2.append(h)
    H = H2
    report["파일내_중복"] = dup_in

    # ---- 기준 월드(이전 반영분 제외)
    reg = json.loads((DATA / "regions.json").read_text(encoding="utf-8"))
    base = [n for n in reg["nodes"] if n.get("source") != "heritage450"]
    snap = SRC450 / "node_geo_before_import.json"   # 최초 실행 시 원본 보관 → 재실행해도 같은 결과(충돌 기록 유지)
    if not snap.exists():
        snap.write_text(GEO_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    geo = json.loads(snap.read_text(encoding="utf-8"))
    for n in base:
        n["geo"] = geo[n["region"]][n["name"]][:2]
    rname = {r["id"]: r["name"] for r in reg["regions"]}
    land = Land()
    report["요약"].append(["지형 검사", "SRTM 30m(남)·GTOPO30(북)" if land.ok else "원자료 없음 — 생략(tools/fetch_geo.sh)"])

    def region_of(p):
        if p[0] < 33.7 and p[1] > 125.9:
            return "MAP_17", 0.0
        near = sorted(base, key=lambda n: km(p, n["geo"]))[:5]
        vote = Counter()
        for n in near:
            vote[n["region"]] += 1 / (km(p, n["geo"]) + 1)
        r = vote.most_common(1)[0][0]
        return r, round(km(p, near[0]["geo"]), 1)

    def fix_land(p, label, name, allow_sea=False):
        if allow_sea or land.is_land(*p):
            return p
        q = land.nearest_land(*p)
        if q:
            report["바다위_보정"].append([label, name, p[0], p[1], q[0], q[1], q[2], "가장 가까운 육지로 이동"])
            return (q[0], q[1])
        report["바다위_보정"].append([label, name, p[0], p[1], "", "", "", f"{LAND_FIX_KM}km 안 육지 없음 → 원좌표 유지(섬·해안 확인 필요)"])
        return p
    report["바다위_보정"].append(["구분", "이름", "원 위도", "원 경도", "보정 위도", "보정 경도", "이동(km)", "처리"])
    report["바다위_보정"][:] = [report["바다위_보정"][-1]]

    # ---- 2~4) 공식 노드
    geo_fix = [["게임 노드", "권역", "공식 노드", "게임 좌표", "공식 좌표", "차이(km)", "처리"]]
    merged = [["공식 노드 id", "공식 이름", "공식 유형", "→ 게임 노드", "게임 유형", "거리(km)", "판정 근거"]]
    new_nodes, taken, links = [], {}, {}
    all_nodes = list(base)
    for m in NM:
        p = fix_land((m["latitude"], m["longitude"]), "공식 노드", m["name_kr"])
        r, dnear = region_of(p)
        t = MASTER_TYPE[m["node_type"]]
        cands = []
        for n in base:
            d = km(p, n["geo"])
            same_cls = CLASS.get(n["type"]) == CLASS[t]
            same_name = stem(n["name"]) and stem(n["name"]) == stem(m["name_kr"]) or norm(n["name"]) == norm(m["name_kr"])
            if (same_cls and d <= MATCH_SAME_CLASS_KM) or (same_name and d <= MATCH_SAME_NAME_KM and CLASS.get(n["type"]) in (CLASS[t], "settle")):
                cands.append((0 if same_name else 1, d, n, "같은 지명" if same_name else "같은 유형군·근접"))
        cands.sort(key=lambda c: (c[0], c[1]))
        cands = [c for c in cands if c[2]["id"] not in taken]
        if cands:
            _, d, n, why = cands[0]
            taken[n["id"]] = m["node_id"]
            merged.append([m["node_id"], m["name_kr"], m["node_type"], n["name"], n["type"], round(d, 2), why])
            links[n["id"]] = {"id": m["node_id"], "name": m["name_kr"], "modern": m["modern_match"], "desc": m["description"]}
            if d > COORD_CONFLICT_KM:
                if not land.is_land(*p):
                    geo_fix.append([n["name"], rname[n["region"]], m["name_kr"], n["geo"], list(p), round(d, 2), "공식 좌표가 바다/수면 → 게임 좌표 유지"])
                elif n["region"] != r:
                    geo_fix.append([n["name"], rname[n["region"]], m["name_kr"], n["geo"], list(p), round(d, 2), f"권역 판정 불일치({rname[r]}) → 게임 좌표 유지"])
                else:
                    old = geo[n["region"]][n["name"]]
                    geo[n["region"]][n["name"]] = [round(p[0], 4), round(p[1], 4), "O"]
                    geo_fix.append([n["name"], rname[n["region"]], m["name_kr"], old[:2], list(p), round(d, 2), "공식 좌표로 수정(신뢰도 O)"])
                    n["geo"] = list(p)
            continue
        fac = sorted({MASTER_FAC[f] for f in str(m["facilities"]).split(",") if f in MASTER_FAC}
                     | ({"market" if t == "city" else "market5"} if "MARKET" in str(m["facilities"]) else set()))
        nn = {"region": r, "name": m["name_kr"], "type": t, "hidden": False, "geo": list(p), "facilities_extra": fac,
              "official": {"id": m["node_id"], "modern": m["modern_match"], "desc": m["description"], "illustration": m["illustration_path"]},
              "note": m["description"], "near_km": dnear}
        new_nodes.append(nn)
        all_nodes.append(nn)
    report["노드_중복병합"] = merged
    report["좌표_충돌"] = geo_fix

    # ---- 4.5) 유산 좌표 검증: 이름의 지명(가제티어)과 좌표가 25km 이상 어긋나면 지명 쪽으로 옮김.
    #      'A/B/C 물건' 형식(템플릿 행)은 공식 명칭이 아니므로 한 고을로 구체화하고 '비지정(창작)'으로 표기
    band = defaultdict(list)
    for m in NM:
        band[int(m["node_id"].split("_")[1][1:])].append(m["latitude"])
    band = {c: (min(v) - 0.3, max(v) + 0.3) for c, v in band.items()}
    gaz = defaultdict(list)       # 지명 → [(위도, 경도, 노드 이름)]
    full = []                     # (정규화 전체 이름, 좌표, 노드 이름)
    for n in base:
        gaz[place_key(n["name"])].append((n["geo"][0], n["geo"][1], n["name"]))
        full.append((full_key(n["name"]), (n["geo"][0], n["geo"][1]), n["name"]))
    for n in new_nodes:
        gaz[place_key(n["name"])].append((n["geo"][0], n["geo"][1], n["name"]))
        full.append((full_key(n["name"]), (n["geo"][0], n["geo"][1]), n["name"]))
    ev_chop = {e["linked_heritage_name"]: int(e["chop_num"]) for e in EV}
    tmpl_order = defaultdict(list)
    for h in H:
        t0 = h["name_kr"].split()[0]
        if "/" in t0:
            tmpl_order[t0].append(h["name_kr"])
    reloc = [["원 이름", "게임 이름", "지명", "원 좌표", "지명 좌표", "어긋남(km)", "처리"]]
    tmpl = [["원 이름(템플릿)", "게임 이름", "원 지정", "게임 지정", "고을", "처리"]]
    era = [["유산", "사유"]]

    def pick(cands, lat, chop):
        if chop in band:
            lo, hi = band[chop]
            inb = [c for c in cands if lo <= c[0] <= hi]
            if inb:
                cands = inb
        return min(cands, key=lambda c: abs(c[0] - lat))

    used_names = {h["name_kr"] for h in H if "/" not in h["name_kr"].split()[0]}
    for h in H:
        name, p = h["name_kr"], (h["latitude"], h["longitude"])
        t0 = name.split()[0]
        chop = ev_chop.get(name)
        h["orig_name"] = name
        if "/" in t0:
            places = t0.split("/")
            k = tmpl_order[t0].index(name)
            obj = " ".join(name.split()[1:])
            for j in range(len(places)):   # 다른 묶음과 이름이 겹치면(전라 순천·평안 순천 등) 다음 고을
                pl = ALIAS.get(places[(k + j) % len(places)], places[(k + j) % len(places)])
                if f"{pl} {obj}" not in used_names:
                    break
            h["name_kr"] = f"{pl} {obj}"
            used_names.add(h["name_kr"])
            h["template"] = True
            tmpl.append([name, h["name_kr"], h["designated_type"], "비지정(창작)", pl,
                         "지명 묶음 → 한 고을로 구체화 · 공식 지정 아님(창작 유산으로 표기)"])
            h["designated_type"] = "비지정(창작)"
            key = pl
        else:
            key = ALIAS.get(place_key(name), place_key(name))
            if place_key(name) in MODERN:
                h["name_kr"] = key + name[len(name.split()[0]):]
                era.append([name, f"현대 지명 '{place_key(name)}' → 1861년 지명 '{key}'로 이름 보정: {h['name_kr']}"])
            used_names.add(h["name_kr"])
        if POST1861.search(name):
            era.append([name, "1861년 이후 사건·인물 관련 — 고증 확인 필요(유지)"])
        fk = full_key(name)
        spec = [f for f in full if len(f[0]) >= 3 and f[0] in fk and f[0] != key]
        target = None
        if spec:
            f = max(spec, key=lambda f: len(f[0]))
            target = (f[1][0], f[1][1], f[2])
        elif gaz.get(key):
            target = pick(gaz[key], p[0], chop)
        else:   # 첫 낱말이 지명이 아니면(조선왕조실록 태백산사고본 등) 뒤 낱말의 앞부분(3자 이상)으로 조회
            for tok in re.split(r"[\s/()]", name)[1:]:
                hits = [k for k in gaz if len(k) >= 3 and tok.startswith(k)]
                if hits:
                    target = pick(gaz[max(hits, key=len)], p[0], chop)
                    break
        if target is None:
            continue
        d = km(p, target[:2])
        if d > 25:
            # 이벤트(은닉) 유산은 지명 노드에서 3~6km 떨어진 곳(고유 방향), 일반 유산은 그 노드 자리로
            if name in ev_chop:
                ang = (sum(map(ord, name)) % 360) * math.pi / 180
                rr = 3 + (sum(map(ord, name)) % 30) / 10
                q = (target[0] + rr * math.sin(ang) / 110.57, target[1] + rr * math.cos(ang) / (111.32 * math.cos(math.radians(target[0]))))
                q = fix_land(q, "재배치 유산", h["name_kr"]) if land.ok else q
            else:
                q = (target[0], target[1])
            reloc.append([name, h["name_kr"], f"{key} → {target[2]}", [p[0], p[1]], [round(q[0], 4), round(q[1], 4)], round(d, 1),
                          "지명 쪽으로 재배치(원 좌표는 대동여지도 첩 범위만 맞고 경도가 어긋남)"])
            h["latitude"], h["longitude"] = round(q[0], 4), round(q[1], 4)
            h["relocated"] = True
    report["좌표_지명불일치"] = reloc
    report["템플릿_유산"] = tmpl
    report["시대_고증주의"] = era
    seen = set()
    H2 = []
    for h in H:   # 구체화 뒤 같은 이름이 생기면 중복 제거
        if h["name_kr"] in seen:
            report["파일내_중복"].append(["국가유산", h["orig_name"], h["name_kr"], 0, 1.0, "구체화 뒤 이름 중복 → 제외"])
            continue
        seen.add(h["name_kr"])
        H2.append(h)
    H = H2

    # ---- 5) 유산 배치
    ev_by = {e["linked_heritage_name"]: e for e in EV}
    ev_by = {h["name_kr"]: ev_by[h["orig_name"]] for h in H if h["orig_name"] in ev_by}
    place = [["유산", "지정", "원 등급", "권역", "배치", "노드", "거리(km)", "비고"]]
    imported = []
    her_old = json.loads((DATA / "01_heritage.json").read_text(encoding="utf-8"))["heritage"]
    old_names = {re.sub(r"\s", "", h["name"]): h for h in her_old if not str(h["id"]).startswith("her_n")}
    dup_game = [["국가유산", "게임 유산", "게임 id", "거리(km)", "판정"]]
    for i, h in enumerate(H, 1):
        p0 = (h["latitude"], h["longitude"])
        underwater = bool(re.search(r"해저|침몰|인양", h["name_kr"]))
        p = fix_land(p0, "국가유산", h["name_kr"], allow_sea=underwater)
        r, _ = region_of(p)
        key = re.sub(r"\s", "", h["name_kr"])
        if key in old_names:
            dup_game.append([h["name_kr"], old_names[key]["name"], old_names[key]["id"], 0, "같은 유산 → 게임 행 유지(가져오지 않음)"])
            continue
        vis = [n for n in all_nodes if n["region"] == r and not n.get("hidden")]
        e = ev_by.get(h["name_kr"])
        if e and (h.get("template") or h["name_kr"] != h["orig_name"]):
            e["clean"] = h["name_kr"]
        near_any = min(((km(p, n["geo"]), n) for n in all_nodes if n["region"] == r), key=lambda x: x[0], default=(1e9, None))
        near_vis = min(((km(p, n["geo"]), n) for n in vis), key=lambda x: x[0], default=(1e9, None))
        how, node_name, dist, extra = "", "", 0.0, ""
        new = None
        if e and near_any[0] <= EVENT_MERGE_KM:
            how, node_name, dist, extra = "이벤트 노드 → 기존 노드와 같은 자리(병합)", near_any[1]["name"], near_any[0], e["event_node_id"]
        elif e:
            ntype = "wreck" if underwater else EVENT_TYPE[e["node_subtype"]]
            new = {"region": r, "name": e["clean"], "type": ntype, "hidden": True, "geo": list(p), "parent": near_vis[1]["name"],
                   "discover": {"skill": SKILL.get(e["required_life_skill"], "search"), "sa": GRADE_SA.get(int(e["required_grade"]), 0),
                                "grade": int(e["required_grade"]), "clue": e["discovery_clue"]},
                   "official": {"id": e["event_node_id"], "illustration": e["illustration_path"], "subtype": e["node_subtype"]},
                   "note": e["discovery_clue"]}
            how, node_name, dist = "새 은닉 노드(발견 필요)", e["clean"], near_vis[0]
            extra = f"부모 {near_vis[1]['name']} · 발견 [{SKILL.get(e['required_life_skill'])}] 사 {new['discover']['sa']}"
        elif near_vis[0] <= ATTACH_KM:
            how, node_name, dist = "기존 노드에 함께 배치(한 노드 여러 유산)", near_vis[1]["name"], near_vis[0]
        else:
            t = TYPE_FOR_CATEGORY.get(h["category"], "ruin")
            if re.search(r"릉|총$|고분|왕묘", h["name_kr"]):
                t = "tomb"
            if h["designated_type"] == "명승":
                t = "scenic"
            new = {"region": r, "name": re.sub(r"\s+", " ", h["name_kr"]), "type": t, "hidden": False, "geo": list(p),
                   "official": {"heritage": h["name_kr"]}, "note": h["description"]}
            how, node_name, dist = "새 가시 노드", new["name"], near_vis[0]
        if new:
            new["source_heritage"] = h["name_kr"]
            new_nodes.append(new)
            all_nodes.append(new)
        cat = "scenic" if h["designated_type"] == "명승" else CATEGORY[h["category"]]
        score = DESIG_SCORE.get(h["designated_type"], 2) + (0 if h.get("template") else 0.4 * int(h["tier"])) + (0.3 if e else 0)
        imported.append({"id": f"her_n{i:03d}", "name": h["name_kr"], "orig_name": h["orig_name"], "template": bool(h.get("template")), "node_name": node_name, "region": r, "category": cat,
                         "category_kr": h["category"], "designation": h["designated_type"], "faction": FACTION.get(h["faction"], ""),
                         "src_tier": int(h["tier"]), "src_money": h["money_reward"], "src_rep": h["reputation_gain"], "score": round(score, 2),
                         "desc": h["description"], "geo": [round(p[0], 4), round(p[1], 4)], "hidden": bool(new and new["hidden"]),
                         "lore": "창작" if h.get("template") else "역사"})
        place.append([h["name_kr"], h["designated_type"], h["tier"], rname[r], how, node_name, round(dist, 2), extra])
    report["유산_배치"] = place
    report["게임유산_중복"] = dup_game

    # 최종 육지 검사(해저 유산 노드 제외): 5km 안 육지로, 없으면 권역의 가장 가까운 가시 노드 쪽으로 당김
    for n in new_nodes:
        if n["type"] == "wreck" or land.is_land(*n["geo"]):
            continue
        q = land.nearest_land(*n["geo"])
        if q:
            report["바다위_보정"].append(["최종 노드", n["name"], n["geo"][0], n["geo"][1], q[0], q[1], q[2], "가장 가까운 육지로 이동"])
            n["geo"] = [q[0], q[1]]
            continue
        vis = [v for v in all_nodes if v["region"] == n["region"] and not v.get("hidden") and v is not n and land.is_land(*v["geo"])]
        v = min(vis, key=lambda v: km(n["geo"], v["geo"]))
        for t in [i / 20 for i in range(1, 21)]:
            q = (n["geo"][0] + (v["geo"][0] - n["geo"][0]) * t, n["geo"][1] + (v["geo"][1] - n["geo"][1]) * t)
            if land.is_land(*q):
                break
        report["바다위_보정"].append(["최종 노드", n["name"], n["geo"][0], n["geo"][1], round(q[0], 4), round(q[1], 4), round(km(n["geo"], q), 2),
                                   f"5km 안 육지 없음 → {v['name']} 쪽 첫 육지로 이동"])
        n["geo"] = [round(q[0], 4), round(q[1], 4)]
    for h in imported:   # 유산 좌표 = 놓인 노드 좌표
        for n in all_nodes:
            if n["region"] == h["region"] and n["name"] == h["node_name"]:
                h["geo"] = [round(n["geo"][0], 4), round(n["geo"][1], 4)]
                break

    # 새 노드 이름 충돌(같은 권역 기존 이름) → 접미어
    names = defaultdict(set)
    for n in base:
        names[n["region"]].add(n["name"])
    ren = {}
    for n in new_nodes:
        nm, k = n["name"], 2
        while nm in names[n["region"]]:
            nm, k = f"{n['name']} ({k})", k + 1
        if nm != n["name"]:
            ren[(n["region"], n["name"])] = nm
            report["이름_충돌"].append([rname[n["region"]], n["name"], nm])
            n["name"] = nm
        names[n["region"]].add(nm)
    if report["이름_충돌"]:
        report["이름_충돌"].insert(0, ["권역", "원 이름", "게임 이름"])
    for h in imported:
        h["node_name"] = ren.get((h["region"], h["node_name"]), h["node_name"])
    for n in new_nodes:
        if n.get("parent"):
            n["parent"] = ren.get((n["region"], n["parent"]), n["parent"])
        geo.setdefault(n["region"], {})[n["name"]] = [round(n["geo"][0], 4), round(n["geo"][1], 4), "O"]

    # ---- 권역 판정이 먼 것(기존 노드에서 60km 이상) 경고
    far = [["구분", "이름", "권역", "가장 가까운 기존 노드(km)"]]
    for n in new_nodes:
        if n.get("near_km", 0) > 60:
            far.append(["공식 노드", n["name"], rname[n["region"]], n["near_km"]])
    report["권역_경계확인"] = far

    counts = Counter(n["type"] for n in new_nodes)
    by_reg = Counter(n["region"] for n in new_nodes)
    report["요약"] += [
        ["국가유산 행", len(H)], ["이벤트 노드 행", len(EV)], ["공식 노드 행", len(NM)],
        ["파일 내부 중복", len(dup_in) - 1], ["공식 노드 ↔ 게임 노드 중복(병합)", len(merged) - 1], ["좌표 충돌(1km↑)", len(geo_fix) - 1],
        ["바다 위 좌표 보정", len(report["바다위_보정"]) - 1], ["지명-좌표 불일치 재배치(25km↑)", len(report["좌표_지명불일치"]) - 1],
        ["템플릿 행('A/B/C 물건') → 한 고을 창작 유산", len(report["템플릿_유산"]) - 1], ["시대·고증 주의", len(report["시대_고증주의"]) - 1], ["국가유산 ↔ 게임 유산 같은 유산", len(dup_game) - 1],
        ["가져온 국가유산", len(imported)], ["새 노드", f"{len(new_nodes)} (가시 {sum(1 for n in new_nodes if not n['hidden'])} · 은닉 {sum(1 for n in new_nodes if n['hidden'])})"],
        ["새 노드 유형", ", ".join(f"{k} {v}" for k, v in counts.most_common())],
        ["권역별 새 노드", ", ".join(f"{rname[k]} {v}" for k, v in sorted(by_reg.items()))],
        ["등급·보상", "원본 고정 명성/엽전은 사용 안 함 → build_world 가 분포 배정, economy 공식 산출, economy_sim 재보정"]]
    GEO_PATH.write_text(json.dumps(geo, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT.write_text(json.dumps({"_about": "tools/import_heritage450.py 생성 — build_world.py 가 병합", "nodes": new_nodes,
                               "heritage": imported, "official_links": links},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    json.dump({k: v for k, v in report.items()}, open(SRC450 / "report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    for k, v in report["요약"]:
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
