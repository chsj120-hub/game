#!/usr/bin/env python3
"""마스터 데이터셋(시트 00~22 + regions) 무결성 검증기. 오류 시 exit 1.

검사: id 중복 · 교차 참조 · 17권역 인접 대칭·쌀 시세 · 노드 시설/좌표/연결성 · 유산→보상 형태 · 동선 큐 2~5노드
      (장비·탈것·동료·인스턴스·이벤트 단계·메인 챕터) · 비전서 분배 6/5/5/8 · 모작 70~80% · 포획구 4×5 · 보스 도주 0%
      · 스킬 상태이상 · 미니게임 구현/문항 · 세시 24절기 · 신분 임계 단조성
      · 24 대화·서사: 퀘스트 동선·보상 · 서사 키/동선 길이 · 화자(who) · 선택지 조건(req)/효과(effects) 키 · 전설 잠금 · 유산별 미니게임 변형
"""
import sys
from collections import Counter, deque, defaultdict

from common import load

errors, warnings = [], []
E = errors.append
W = warnings.append

OV = load("00_overview.json")
REG = load("regions.json")
S = {
    "regions": REG["regions"], "nodes": REG["nodes"],
    "heritage": load("01_heritage.json")["heritage"], "items": load("02_equipment.json")["items"],
    "specialties": load("03_specialties.json")["specialties"], "specialty_recipes": load("03_specialties.json")["specialty_recipes"],
    "trade_quests": load("03_specialties.json")["trade_quests"], "foods": load("04_food_staples.json")["foods"],
    "materials": load("05_materials.json")["materials"], "life_gear": load("06_life_gear.json")["life_gear"],
    "mounts": load("07_mounts.json")["mounts"], "capture": load("08_capture_tools.json")["tools"],
    "herbal": load("09_herbal_recipes.json")["recipes"], "herbs": load("10_herbs.json")["herbs"],
    "food_recipes": load("11_food_recipes.json")["recipes"], "enemies": load("12_enemies.json")["enemies"],
    "companions": load("13_companions.json")["companions"], "skills": load("14_skills.json")["skills"],
    "books": load("15_recipe_books.json")["books"], "mojak": load("16_mojak_gear.json")["mojak"],
    "instances": load("17_instances.json")["instances"], "classes": load("19_classes_knowledge.json")["classes"],
    "events": load("20_events.json")["events"], "mains": load("20_events.json")["main_scenarios"],
    "minigames": load("21_minigames.json")["minigames"],
}
ST = load("18_status_effects.json")
CK = load("19_classes_knowledge.json")
SIDE = load("22_side_systems.json")
MG_DOC = load("21_minigames.json")
BATTLE_MG = load("17_instances.json")["minigames"]
CAT_MAP = load("01_heritage.json")["category_reward_map"]
FACILITIES = {"gwana", "jumak", "gaekju", "market", "market5", "forge", "forge_basic", "bookstore", "yakbang", "hyeminseo", "yakryeongsi",
              "antique", "black_market", "hyanggyo", "restaurant", "gongbang", "carpenter", "yeokcham", "temple", "bath", "checkpoint", "drill",
              "bounty", "beacon", "scenic", "investigate", "hazard", "ferry"}
IMPLS = {"archery", "bagua", "ssireum", "rhythm", "quiz", "gauge", "sliding", "trace", "rubbing", "timing"}
KNOW = set(CK["knowledge"]["academic"] + CK["knowledge"]["life"])

by, sheet = {}, {}
for sn, rows in S.items():
    for r in rows:
        rid = r.get("id")
        if rid is None:
            E(f"[{sn}] id 없음")
            continue
        if rid in by:
            E(f"id 중복: {rid} ({sheet[rid]} / {sn})")
        by[rid], sheet[rid] = r, sn
for s in ST["battle"]:
    by.setdefault(s["id"], s)
    sheet.setdefault(s["id"], "status")


def ref(rid, where, allowed=None):
    if rid not in by:
        E(f"{where}: 참조 누락 '{rid}'")
        return False
    if allowed and sheet[rid] not in allowed:
        E(f"{where}: '{rid}' 는 {sheet[rid]} (기대 {sorted(allowed)})")
        return False
    return True


MATS = {"materials", "herbs", "foods", "specialties"}


LINES = OV.get("crafting", {}).get("lines", {})


def mats(lst, where):
    for m in lst:
        if "group" in m:
            if m["group"] not in LINES:
                E(f"{where}: 재료군 '{m['group']}' 없음 (00_overview.crafting.lines)")
        else:
            ref(m["id"], where, MATS)


# ================================================================ 권역·노드·그래프
adj = {r["id"]: r["adjacent"] for r in S["regions"]}
if len(adj) != 17:
    E(f"권역 수 {len(adj)} ≠ 17")
for a, nbs in adj.items():
    for b in nbs:
        if b not in adj:
            E(f"{a}: 인접 권역 누락 {b}")
        elif a not in adj[b]:
            E(f"인접 비대칭 {a}→{b}")
lo, hi = OV["trade"]["rice_price_range"]
for r in S["regions"]:
    if not lo <= r["rice_price"] <= hi:
        E(f"{r['id']} 쌀 시세 {r['rice_price']} 범위 밖")
    ref(r["hub"], f"{r['id']}.hub", {"nodes"})
ms = REG["map_size"]
for n in S["nodes"]:
    w = f"node {n['id']}"
    if n["region"] not in adj:
        E(f"{w}: 권역 {n['region']} 없음")
    for f in n["facilities"]:
        if f not in FACILITIES:
            E(f"{w}: 알 수 없는 시설 {f}")
    if not (0 < n["pos"][0] < ms[0] and 0 < n["pos"][1] < ms[1]):
        E(f"{w}: 좌표 범위 밖 {n['pos']}")
    if "heritage" in n:
        ref(n["heritage"], w, {"heritage"})
g = {n["id"]: set() for n in S["nodes"]}
for e in REG["edges"] + REG["border_links"] + REG["sea_routes"]:
    for k in ("a", "b"):
        if e[k] not in g:
            E(f"간선 노드 누락 {e[k]}")
    if e["a"] in g and e["b"] in g:
        g[e["a"]].add(e["b"])
        g[e["b"]].add(e["a"])
start = S["nodes"][0]["id"]
seen, q = {start}, deque([start])
while q:
    c = q.popleft()
    for x in g[c]:
        if x not in seen:
            seen.add(x)
            q.append(x)
if len(seen) != len(g):
    E(f"노드 그래프 비연결: {len(g) - len(seen)}개 고립")
for s in REG["sea_routes"]:
    for k in ("a", "b"):
        if "ferry" not in by[s[k]]["facilities"]:
            W(f"뱃길 {s[k]} 에 나루터(ferry) 시설 없음")


def region_of(x):
    r = by.get(x)
    return r.get("region") if r else None


SEA_ADJ = defaultdict(set)
for _s in REG["sea_routes"]:
    _ra, _rb = by[_s["a"]]["region"], by[_s["b"]]["region"]
    if _ra != _rb:
        SEA_ADJ[_ra].add(_rb)
        SEA_ADJ[_rb].add(_ra)


def connected(regs):
    """동선 큐 인접 판정: 육로 인접 + 뱃길로 이어진 권역."""
    regs = list(regs)
    sn, qq = {regs[0]}, deque([regs[0]])
    while qq:
        c = qq.popleft()
        for nb in set(adj.get(c, [])) | SEA_ADJ[c]:
            if nb in regs and nb not in sn:
                sn.add(nb)
                qq.append(nb)
    return len(sn) == len(regs)


routes_checked = 0


def route(rt, tier, where, rules_key="route_rules"):
    global routes_checked
    routes_checked += 1
    rule = OV[rules_key][str(tier)]
    n0, n1 = rule["nodes"]
    if not n0 <= len(rt) <= n1:
        E(f"{where}: 동선 {len(rt)}노드 (T{tier} 허용 {n0}~{n1})")
    regs = []
    for x in rt:
        r = region_of(x)
        if r is None:
            E(f"{where}: 알 수 없는 노드 {x}")
            return
        if r not in regs:
            regs.append(r)
    if rule["scope"] == "same_region" and len(regs) != 1:
        E(f"{where}: 동일 권역 규칙 위반 {regs}")
    elif rule["scope"] in ("adjacent", "nationwide"):
        r0, r1 = rule["regions"]
        if not r0 <= len(regs) <= r1:
            E(f"{where}: 권역 수 {len(regs)} (허용 {r0}~{r1}) {regs}")
        if rule["scope"] == "adjacent" and not connected(regs):
            E(f"{where}: 인접 권역 연계 아님 {regs}")


# ================================================================ 국가유산 448 반영: 한 노드 여러 유산 · 발견 조건
her_by_node = defaultdict(list)
for h in S["heritage"]:
    her_by_node[h["node"]].append(h["id"])
for n in S["nodes"]:
    ids = n.get("heritage_ids") or ([n["heritage"]] if "heritage" in n else [])
    if sorted(ids) != sorted(her_by_node.get(n["id"], [])):
        E(f"node {n['id']}: heritage/heritage_ids 와 01 유산 배치 불일치")
    dc = n.get("discover")
    if dc:
        if not n["hidden"]:
            E(f"node {n['id']}: 발견 조건(discover)은 은닉 노드만")
        if dc.get("skill") not in ("search", "gather", "camp", "hunt") or not 0 <= dc.get("sa", 0) <= 10:
            E(f"node {n['id']}: 발견 조건 {dc}")
for h in S["heritage"]:
    if h.get("source") == "heritage450" and h.get("faction") not in ("yu", "bul", "seon", ""):
        E(f"01 {h['id']}: 계열 {h.get('faction')}")

# ================================================================ 유산
exp = {"record": {"life_gear"}, "specialty_recipe": {"specialty_recipes"}, "accessory": {"items"}, "equipment": {"items"}, "book": {"items"}}
for h in S["heritage"]:
    w = f"01 {h['id']}"
    if ref(h["node"], w, {"nodes"}) and by[h["node"]]["region"] != h["region"]:
        E(f"{w}: 권역 불일치")
    rt = CAT_MAP.get(h["category"])
    if not rt:
        E(f"{w}: 카테고리 {h['category']}")
        continue
    if ref(h["reward"], w, exp[rt]):
        rw = by[h["reward"]]
        if rt == "record" and (rw.get("slot") != "record" or rw.get("icon") != "icon_scroll_jokja.png"):
            E(f"{w}: 답사록 규격 위반")
        if rt == "accessory" and rw.get("slot") != "accessory":
            E(f"{w}: 민속공예 → 장신구")
        if rt == "book" and (rw.get("slot") != "book" or "passive_skill" not in rw):
            E(f"{w}: 전적 → 서책(패시브)")
        if rt == "equipment" and rw.get("slot") not in ("weapon", "armor", "shoes", "accessory"):
            E(f"{w}: 금속공예 → 장착 장비")
    if "minigame" in h:
        ref(h["minigame"], w, {"minigames"})

# ================================================================ 장비·제작
for it in S["items"]:
    w = f"02 {it['id']}"
    a = it.get("acquire", {})
    t = a.get("type")
    if t == "quest":
        route(a["route"], it["tier"], w)
    elif it["tier"] >= 4 and t not in ("quest", "heritage"):
        E(f"{w}: 4~5등급은 전용 퀘스트/유산 획득")
    if t == "forge":
        ref(a["book"], w, {"books"})
        mats(a["materials"], w)
        if it["id"] not in by.get(a["book"], {}).get("unlocks", []):
            E(f"{w}: 비전서 {a['book']} unlocks 누락")
    if t == "heritage":
        ref(a["heritage"], w, {"heritage"})
    for k in ("passive_skill",):
        if k in it:
            ref(it[k], w, {"skills"})
    for k in it.get("granted_skills", {}).values():
        if k not in by:
            W(f"{w}: 부여 스킬 {k} 미정의(추가 예정)")
    if "mojak_recipe" in it:
        ref(it["mojak_recipe"], w, {"mojak"})
    for c in it.get("class_restriction", []):
        ref(c, w, {"classes"})
    for k in it.get("req_knowledge", {}):
        if k not in KNOW:
            E(f"{w}: 지식 키 {k}")
for b in S["books"]:
    for u in b["unlocks"]:
        if not u.startswith("@"):
            ref(u, f"15 {b['id']}")
    if b["type"] == "martial":
        for d in b.get("obtain", {}).get("drop", []):
            ref(d["enemy"], f"15 {b['id']}", {"enemies"})
    elif "sold_at" not in b:
        E(f"15 {b['id']}: 판매처 없음")
    else:
        for r in b["sold_at"]["regions"]:
            if r != "*" and r not in adj:
                E(f"15 {b['id']}: 판매 권역 {r}")
        if b["sold_at"]["facility"] not in FACILITIES:
            E(f"15 {b['id']}: 판매 시설 {b['sold_at']['facility']}")
    if not b["unlocks"]:
        W(f"15 {b['id']}: 해금 레시피 없음(추가 예정)")
if dict(Counter(b["type"] for b in S["books"])) != {"food": 6, "medicine": 5, "tool": 5, "martial": 8}:
    E("15 비전서 분배 ≠ 6/5/5/8")
for rs, lab in ((S["herbal"], "09"), (S["food_recipes"], "11")):
    for r in rs:
        ref(r["book"], f"{lab} {r['id']}", {"books"})
        mats(r["ingredients"], f"{lab} {r['id']}")
        if r["id"] not in by.get(r["book"], {}).get("unlocks", []):
            E(f"{lab} {r['id']}: 비전서에서 해금되지 않음(철칙)")
fc = Counter(r["class"] for r in S["food_recipes"])
if fc["seomin"] < 9 or fc["sura"] < 9 or set(fc) != {"seomin", "sura"}:
    E(f"11 서민·수라 각 9종 이상 필요 ({dict(fc)})")
if any(r["tier"] < 2 for r in S["food_recipes"]):
    E("11 요리는 2등급 이상(1등급 요리 폐지)")
# 재료군·대체 사슬: 참조 · 등급 오름차순
for ln, v in LINES.items():
    ts = []
    for x in v["items"]:
        if ref(x, f"00 crafting.lines.{ln}", MATS):
            ts.append(by[x].get("tier", 1))
    if ts != sorted(ts):
        E(f"00 crafting.lines.{ln}: 등급이 오름차순이 아님 {ts}")
for x in OV.get("crafting", {}).get("no_substitute", []):
    ref(x, "00 crafting.no_substitute", MATS)
# 무역품 등급 사슬: 등급 = 기본 + grade, 가격 공식, 도감 명칭
for sp in S["specialties"]:
    gr = sp.get("grade", 0)
    if sp["kind"] != "crafted" and sp["base_price"] != 20 * 3 ** (sp["tier"] - 1):
        E(f"03 {sp['id']}: 가격 {sp['base_price']} ≠ 공식")
    if gr > 0:
        if not sp.get("real_name") or not sp.get("desc"):
            E(f"03 {sp['id']}: 등급품은 도감용 real_name·desc 필요")
        base = [b for b in S["specialties"] if b.get("line") == sp.get("line") and b.get("grade", 0) == 0]
        if len(base) != 1 or base[0]["tier"] + gr != sp["tier"]:
            E(f"03 {sp['id']}: 사슬 기본품/등급 불일치")
for f in S["foods"]:
    if "unpack" in f:
        ref(f["unpack"]["to"], f"04 {f['id']}.unpack", {"foods"})
    if "unit_of" in f:
        ref(f["unit_of"], f"04 {f['id']}.unit_of", {"foods"})
for sr in S["specialty_recipes"]:
    ref(sr["produces"], f"03 {sr['id']}", {"specialties"})
    mats(sr["materials"], f"03 {sr['id']}")
for sp in S["specialties"]:
    ref(sp["node"], f"03 {sp['id']}", {"nodes"})
for tq in S["trade_quests"]:
    if tq.get("reward_item"):
        ref(tq["reward_item"], f"03 {tq['id']}.reward_item")
    if tq.get("consign") and not tq.get("margin", 1) < 1:
        E(f"03 {tq['id']}: 위탁(consign) 운임 margin 은 1 미만")
    ref(tq["item"], f"03 {tq['id']}", {"specialties"})
    ref(tq["from"], f"03 {tq['id']}", {"nodes"})
    ref(tq["to"], f"03 {tq['id']}", {"nodes"})
for g_ in S["life_gear"]:
    if "craft" in g_:
        ref(g_["craft"]["book"], f"06 {g_['id']}", {"books"})
        mats(g_["craft"]["materials"], f"06 {g_['id']}")
    if "skill" in g_:
        ref(g_["skill"], f"06 {g_['id']}", {"skills"})
for m in S["mounts"]:
    a = m["acquire"]
    if a["type"] == "quest":
        route(a["route"], m["tier"], f"07 {m['id']}")
    if (m["tier"] <= 3) != (a["type"] == "shop"):
        E(f"07 {m['id']}: 1~3 역참 판매 / 4~5 퀘스트 규칙 위반")
    ref(m["skill"], f"07 {m['id']}", {"skills"})

# ================================================================ 모작·포획구
if len(S["mojak"]) != 24 or len({(m["family"], m["slot"], m["tier"]) for m in S["mojak"]}) != 24:
    E("16 모작 유·불·선×4부위×4·5등급 = 24 불일치")
for m in S["mojak"]:
    w = f"16 {m['id']}"
    mats(m["materials"], w)
    if not m.get("craft_anywhere"):
        E(f"{w}: craft_anywhere 필요")
    if ref(m["original"], w, {"items"}):
        o = by[m["original"]]["stats"]
        for k, v in m["stats"].items():
            if o.get(k):
                r = v / o[k]
                if not 0.66 <= r <= 0.84:  # 정수 반올림 허용
                    E(f"{w}: {k} 비율 {r:.2f}")
if len({(c["family"], c["tier"]) for c in S["capture"]}) != 20:
    E("08 포획구 4계통×5등급 불일치")

# ================================================================ 적·스킬·동료·클래스
statuses = {s["id"] for s in ST["battle"]}
for sk in S["skills"]:
    st = sk.get("effects", {}).get("status")
    if st and st["id"] not in statuses:
        E(f"14 {sk['id']}: 상태이상 {st['id']} 미정의")
    for k in sk.get("effects", {}).get("passive", {}).get("knowledge", {}):
        if k not in KNOW:
            E(f"14 {sk['id']}: 지식 키 {k}")
fl0, fl1 = OV["battle"]["flee_normal"]
for e in S["enemies"]:
    w = f"12 {e['id']}"
    for s in e["skills"]:
        ref(s, w, {"skills"})
    for d in e.get("drops", []):
        ref(d["id"], w)
    if e.get("boss_tier"):
        if e["flee_rate"] != 0 or e["capturable"]:
            E(f"{w}: 보스 도주 0%·포획 불가")
    elif not fl0 <= e["flee_rate"] <= fl1:
        E(f"{w}: 도주율 {e['flee_rate']}")
    for g_ in e.get("gimmicks", []):
        if g_["type"] not in ("persuade", "bribe", "lure", "purify", "riddle", "debate"):
            E(f"{w}: 기믹 {g_['type']}")
        if "item" in g_:
            ref(g_["item"], w)
        if "requires_item" in g_:
            ref(g_["requires_item"], w)
        mg = g_.get("minigame")
        if mg and mg != "rhythm":
            ref(mg, w, {"minigames"})
    for r in e.get("spawn_conditions", {}).get("regions", []):
        if r != "*" and r not in adj:
            E(f"{w}: 출현 권역 {r}")
    for n in e.get("spawn_conditions", {}).get("nodes", []):
        ref(n, w, {"nodes"})
    if e.get("capturable") and "capture_profile" not in e:
        E(f"{w}: 포획 가능 적은 capture_profile 필요")
for c in S["companions"]:
    w = f"13 {c['id']}"
    for s in c["skills"]:
        ref(s, w, {"skills"})
    for k in list(c.get("knowledge", {})) + list(c.get("knowledge_add", {})):
        if k not in KNOW:
            E(f"{w}: 지식 키 {k}")
    route(c["recruit"]["route"], c["tier"], w)
    # 동료 승급: 시작 1~3등급, 승급 퀘스트는 시작+1 … max_tier 연속, 트리거 = 신분·동행·지식·시작 장소
    cp_cfg = OV.get("companion_promotion", {})
    if cp_cfg:
        if c["tier"] not in cp_cfg["start_tiers"]:
            E(f"{w}: 시작 등급 {c['tier']} (허용 {cp_cfg['start_tiers']})")
        want = list(range(c["tier"] + 1, c.get("max_tier", cp_cfg["max_tier"]) + 1))
        got = [q["tier"] for q in c.get("promotion", [])]
        if got != want:
            E(f"{w}: 승급 퀘스트 등급 {got} ≠ {want}")
        if sum(c["knowledge_add"].values()) != c["tier"]:
            E(f"{w}: 시작 지식 합 {sum(c['knowledge_add'].values())} ≠ 시작 등급 {c['tier']}")
        for q in c.get("promotion", []):
            wq = f"{w} {q['id']}"
            route(q["route"], q["tier"], wq)
            ref(q["trigger_node"], wq, {"nodes"})
            if q["route"][0] != q["trigger_node"]:
                E(f"{wq}: 동선 시작 ≠ 트리거 장소")
            if q["min_rank"] != q["tier"]:
                E(f"{wq}: min_rank {q['min_rank']} ≠ 등급 {q['tier']}")
            for k in q["requires"].get("knowledge", {}):
                if k not in KNOW:
                    E(f"{wq}: 지식 키 {k}")
for c in S["classes"]:
    w = f"19 {c['id']}"
    for s in c["skills"]:
        ref(s, w, {"skills"})
    for i in c["start"]["items"]:
        ref(i, w)
    ref(c["scenario"], w, {"mains"})
for inst in S["instances"]:
    w = f"17 {inst['id']}"
    route(inst["route"], inst["tier"], w)
    if inst["minigame"] not in BATTLE_MG:
        E(f"{w}: 전투 미니게임 {inst['minigame']}")
    if not 3 <= len(inst["waves"]) <= 5:
        E(f"{w}: 웨이브 수 {len(inst['waves'])}")
    for wv in inst["waves"]:
        for eid in wv:
            ref(eid, w, {"enemies"})
    if "boss" in inst and inst["boss"] not in inst["waves"][-1]:
        E(f"{w}: 보스는 마지막 웨이브")
    for d in inst["rewards"].get("items", []):
        ref(d["id"], w)

# ================================================================ 상태·미니게임·이벤트·보조
recipe_ids = {r["id"] for r in S["herbal"]}
for f in ST["field"]:
    for c in f["cure_by"]:
        if c not in recipe_ids and c not in ("spring", "inn_rest_2", "hyeminseo"):
            E(f"18 {f['id']}: 치료 수단 {c}")
for m in S["minigames"]:
    w = f"21 {m['id']}"
    if m["impl"] not in IMPLS:
        E(f"{w}: impl {m['impl']}")
    if m.get("knowledge") and m["knowledge"] not in KNOW:
        E(f"{w}: 지식 {m['knowledge']}")
    if m["impl"] == "quiz":
        bank = m["params"].get("bank", [])
        if len(bank) < m["params"].get("need", 1):
            E(f"{w}: 문항 수 부족")
        for qq in bank:
            if not 0 <= qq["answer"] < len(qq["options"]):
                E(f"{w}: 정답 인덱스 오류 '{qq['q'][:20]}'")
    if m["impl"] == "trace" and len(m["params"].get("points", [])) < 3:
        E(f"{w}: 획순 점 부족")
for t, mg in MG_DOC["node_type_default"].items():
    ref(mg, f"21 node_type_default.{t}", {"minigames"})


def check_stages(stages, tier, w):
    route([s["node"] for s in stages], tier, w)
    for s in stages:
        ref(s["node"], w, {"nodes"})
        if s["action"] == "minigame":
            ref(s["minigame"], w, {"minigames"})
        if s["action"] == "deliver":
            ref(s["item"], w)
        if s["action"] == "battle":
            for wv in s["waves"]:
                for eid in wv:
                    ref(eid, w, {"enemies"})
        if s["action"] == "instance":
            ref(s["instance"], w, {"instances"})


for ev in S["events"]:
    w = f"20 {ev['id']}"
    check_stages(ev["stages"], ev["tier"], w)
    if "region" in ev.get("trigger", {}) and ev["trigger"]["region"] not in adj:
        E(f"{w}: 트리거 권역")
    b = ev.get("blockade")
    if b:
        ref(b["node"], w, {"nodes"})
        ref(b["detour"]["a"], w, {"nodes"})
        ref(b["detour"]["b"], w, {"nodes"})
    if ev.get("deadline_days", 0) <= 0:
        W(f"{w}: 기한 없음(Fail-safe 미적용)")
for mn in S["mains"]:
    ref(mn["class"], f"20 {mn['id']}", {"classes"})
    for ch in mn["chapters"]:
        check_stages(ch["stages"], ch["tier"], f"20 {mn['id']} ch{ch['chapter']}")
# ================================================================ 23 튜토리얼·시나리오·도움말
TUT = load("23_tutorial.json")
tut_ids = {st["tutorial"] for st in TUT["steps"]}
main_ids = {m["id"] for m in S["mains"]}
COUNTERS = {"open_facilities", "open_map", "buy", "sell", "craft", "unpack", "heritage", "battle_win", "trade_accept", "trade_done",
            "save", "event_stage", "gather", "camp"}
for sc in TUT["scenarios"]:
    w = f"23 {sc['id']}"
    ref(sc["class"], w, {"classes"})
    ref(sc["start_node"], w, {"nodes"})
    for it in sc.get("items", {}):
        ref(it, w)
    if sc.get("main") and sc["main"] not in main_ids:
        E(f"{w}: 메인 시나리오 {sc['main']} 없음")
    if sc.get("tutorial") and sc["tutorial"] not in tut_ids:
        E(f"{w}: 튜토리얼 {sc['tutorial']} 단계 없음")
for mn in S["mains"]:
    if mn.get("scenario") and mn["scenario"] not in {sc["id"] for sc in TUT["scenarios"]}:
        E(f"20 {mn['id']}: 시나리오 {mn['scenario']} 없음")
for st in TUT["steps"]:
    w, c = f"23 {st['id']}", st["cond"]
    t = c["type"]
    if t == "counter" and c["key"] not in COUNTERS:
        E(f"{w}: 카운터 키 {c['key']}")
    elif t == "at_node":
        ref(c["node"], w, {"nodes"})
    elif t == "has_item":
        ref(c["item"], w)
    elif t == "event_progress" and c["event"] not in main_ids | {e["id"] for e in S["events"]}:
        E(f"{w}: 이벤트 {c['event']} 없음")
    elif t not in ("ack", "counter", "visited", "at_node", "has_item", "event_progress"):
        E(f"{w}: 조건 종류 {t}")
if len({h["id"] for h in TUT["help"]}) != len(TUT["help"]):
    E("23 도움말 id 중복")

terms = [s["term"] for s in SIDE["seasonal"]]
if len(terms) != 24 or len(set(terms)) != 24:
    E("22 세시풍속 24절기 불일치")
for sc in SIDE["hwacheop"]["scenes"]:
    f = sc["trigger"].get("facility")
    if f and f not in FACILITIES:
        E(f"22 화첩 {sc['id']}: 시설 {f}")
mats(SIDE["takbon"]["materials"], "22 takbon")
ref(SIDE["takbon"]["complete_bonus"]["item"], "22 takbon")
sheets_all = sorted({n for r in S["regions"] for n in r["daedong_sheets"]})
if sheets_all != list(range(1, 23)):
    E(f"대동여지도 22첩 배분 누락: {sorted(set(range(1, 23)) - set(sheets_all))}")

# ================================================================ 도(道) 명성 · 동료 무게 · 명성 예산
covered = [r for p in OV["provinces"] for r in p["regions"]]
if sorted(covered) != sorted(adj):
    E(f"provinces 가 17권역을 정확히 한 번씩 덮지 않음: {sorted(set(adj) - set(covered))}")
for pv in OV["provinces"]:
    ref(pv["capital"], f"province {pv['id']}.capital", {"nodes"})
    if by.get(pv["capital"], {}).get("type") != "city" or by[pv["capital"]]["region"] not in pv["regions"]:
        E(f"province {pv['id']}: 감영은 해당 도의 대도시여야 함")
    req = pv.get("standing_req", [])
    if len(req) != OV["town_dev"]["max"] or req != sorted(req):
        E(f"province {pv['id']}: standing_req 5단계 단조 증가 필요 — economy_sim.py --write 실행")
    elif req[-1] > pv.get("standing_max", 0):
        E(f"province {pv['id']}: 5단계 요건이 도 최대 명성 초과")
for c in S["companions"]:
    if c.get("carry_bonus", -1) < 0:
        E(f"13 {c['id']}: carry_bonus 필요")
for e in S["enemies"]:
    b = e.get("capture_profile", {}).get("companion_bonuses", {})
    if b and ("flat_hp" in b or "flat_def" in b):
        E(f"12 {e['id']}: 동료 스탯 합산 필드 금지(지식·무게만)")
    if e.get("capturable") and "carry" not in b:
        E(f"12 {e['id']}: companion_bonuses.carry 필요")
rb = OV["rank"].get("reputation_budget", {})
if not rb or not (rb["min"] <= rb["reference"] <= rb["max"]):
    E("rank.reputation_budget 없음/순서 오류 — economy_sim.py --write 실행")
elif not 0.1 <= rb["r5_share_of_max"] <= 0.5:
    W(f"Rank 5 임계가 최대 명성의 {rb['r5_share_of_max']*100:.0f}% — 설계 범위 확인")
if not 0 < OV["economy"]["heritage_discovery_share"] < 1:
    E("heritage_discovery_share 는 0~1")

# ================================================================ 신분
th = [r["threshold"] for r in OV["rank"]["table"]]
if th != sorted(th) or th[0] != 0 or len(set(th)) != len(th):
    E(f"신분 임계 단조 증가 아님 {th}")
if OV["rank"]["formula"].get("a", 0) <= 0:
    E("rank.formula 미적합 — tools/economy_sim.py --write 실행 필요")

# ================================================================ 24 대화·서사 (tools/gen_story.py + data_src/story/edits)
STORY = load("24_story.json")
REQ_KEYS = {"rank", "money", "items", "knowledge", "party", "class", "flag", "visited"}
FX_KEYS = {"knowledge_xp", "money", "money_mult", "give", "take", "flag", "reputation"}
NPC_ROLES = {"official", "monk", "elder", "soldier", "merchant", "shaman", "scholar", "fisher", "innkeeper", "traveler"}
for m in STORY.get("minigames", []):
    if m["id"] in by:
        E(f"24 minigames: id 중복 {m['id']}")
    by[m["id"]], sheet[m["id"]] = m, "minigames"
    if m.get("impl") not in IMPLS:
        E(f"24 {m['id']}: impl {m.get('impl')}")
qids = set()
for it in S["items"]:
    if it.get("acquire", {}).get("type") == "quest":
        qids.add("q_" + it["id"])
for m in S["mounts"]:
    if m.get("acquire", {}).get("type") == "quest":
        qids.add("q_" + m["id"])
for c in S["companions"]:
    if c.get("recruit", {}).get("route"):
        qids.add("q_" + c["id"])
    for pq in c.get("promotion", []):
        qids.add(pq["id"])
for inst in S["instances"]:
    qids.add("q_" + inst["id"])
QROUTE = {}
for it in S["items"] + S["mounts"]:
    a = it.get("acquire", {})
    if a.get("type") == "quest":
        QROUTE["q_" + it["id"]] = a["route"]
for c in S["companions"]:
    if c.get("recruit", {}).get("route"):
        QROUTE["q_" + c["id"]] = c["recruit"]["route"]
    for pq in c.get("promotion", []):
        QROUTE[pq["id"]] = pq["route"]
for q in STORY.get("quests", []):
    w = f"24 퀘스트 {q['id']}"
    if q["id"] in qids or q["id"] in by:
        E(f"{w}: id 중복")
    qids.add(q["id"])
    QROUTE[q["id"]] = q["route"]
    if q.get("type") not in OV["economy"]["quest_type_mult"]:
        E(f"{w}: quest_type_mult 에 {q.get('type')} 없음")
    route(q["route"], q["tier"], w, q.get("rules", "route_rules"))
    if len(set(q["route"])) != len(q["route"]):
        E(f"{w}: 동선 중복 노드")
    rw = q.get("reward", {})
    if "item" in rw:
        ref(rw["item"], w, {"specialty_recipes", "items", "books"})
    if "heritage_unlock" in rw:
        ref(rw["heritage_unlock"], w, {"heritage"})
        if q["route"][-1] != rw["heritage_unlock"]:
            E(f"{w}: 전설 동선의 마지막은 그 유산이어야 함")
    av = q.get("avail", {})
    if "region" in av and av["region"] not in adj:
        E(f"{w}: avail.region {av['region']}")
    for k in ("heritage_resolved", "heritage_unvisited"):
        if k in av:
            ref(av[k], w, {"heritage"})
for hid, qid in STORY.get("lore_gate", {}).items():
    ref(hid, f"24 lore_gate {hid}", {"heritage"})
    if qid not in qids:
        E(f"24 lore_gate {hid}: 퀘스트 {qid} 없음")
comp_ids = {c["id"] for c in S["companions"]}
class_ids = {c["id"] for c in S["classes"]}
n_scene = n_choice = 0


def check_scene(sc, w):
    global n_scene, n_choice
    n_scene += 1
    bg = sc.get("bg", "")
    if bg and not bg.startswith("res://") and bg not in by:
        E(f"{w}: 배경 {bg} 없음")
    lines_ = sc.get("lines", [])
    if not lines_ and not sc.get("choices"):
        E(f"{w}: 대사 없음")
    for who in [ln.get("who", "") for ln in lines_] + list(sc.get("cast", [])):
        if who in ("hero", "narration", "") or who in comp_ids:
            continue
        if who.startswith("npc:"):
            parts = who.split(":", 2)
            if len(parts) < 3 or parts[1] not in NPC_ROLES:
                E(f"{w}: NPC 화자 형식 npc:<역할>:<이름> — {who}")
            continue
        E(f"{w}: 알 수 없는 화자 {who}")
    for ln in lines_:
        if not str(ln.get("text", "")).strip():
            E(f"{w}: 빈 대사")
    chs = sc.get("choices", [])
    ids_ = [c.get("id") for c in chs]
    if len(set(ids_)) != len(ids_):
        E(f"{w}: 선택지 id 중복")
    if chs and all(c.get("req") for c in chs):
        W(f"{w}: 조건 없는 선택지가 하나도 없음(모두 비활성일 수 있음)")
    for c in chs:
        n_choice += 1
        wc = f"{w} 선택지 {c.get('id')}"
        req, fx = c.get("req", {}), c.get("effects", {})
        for k in set(req) - REQ_KEYS:
            E(f"{wc}: 알 수 없는 조건 키 {k}")
        for k in set(fx) - FX_KEYS:
            E(f"{wc}: 알 수 없는 효과 키 {k}")
        for k in list(req.get("knowledge", {})) + list(fx.get("knowledge_xp", {})):
            if k not in KNOW:
                E(f"{wc}: 지식 키 {k}")
        for d_ in (req.get("items", {}), fx.get("give", {}), fx.get("take", {})):
            for iid in d_:
                ref(iid, wc)
        for cid in ([req["party"]] if isinstance(req.get("party"), str) else req.get("party", [])):
            if cid not in comp_ids:
                E(f"{wc}: 동료 {cid} 없음")
        for cl in ([req["class"]] if isinstance(req.get("class"), str) else req.get("class", [])):
            if cl not in class_ids:
                E(f"{wc}: 직업 {cl} 없음")
        for nd in ([req["visited"]] if isinstance(req.get("visited"), str) else req.get("visited", [])):
            ref(nd, wc, {"nodes"})


for key, nv in STORY.get("narratives", {}).items():
    w = f"24 서사 {key}"
    if not key.startswith("quest:") or key[6:] not in qids:
        E(f"{w}: 연결된 퀘스트 없음")
        continue
    rt = QROUTE.get(key[6:])
    if rt is not None and len(nv.get("steps", [])) != len(rt):
        E(f"{w}: steps {len(nv.get('steps', []))}개 ≠ 동선 {len(rt)}노드")
    if nv.get("status") not in ("draft", "edited", "final"):
        E(f"{w}: status {nv.get('status')} (draft|edited|final)")
    for part in ("intro", "outro"):
        if part in nv:
            check_scene(nv[part], f"{w}.{part}")
    for i, st in enumerate(nv.get("steps", [])):
        check_scene(st, f"{w}.steps[{i}]")
for e in S["events"]:
    for i, st in enumerate(e.get("stages", [])):
        if "dialogue" in st:
            check_scene(st["dialogue"], f"20 {e['id']} 단계 {i} dialogue")
for m in S["mains"]:
    for ch in m.get("chapters", []):
        for i, st in enumerate(ch.get("stages", [])):
            if "dialogue" in st:
                check_scene(st["dialogue"], f"20 {m['id']} {ch.get('chapter')}장 {i} dialogue")
            for c in st.get("choices", []):
                for k in set(c.get("req", {})) - REQ_KEYS:
                    E(f"20 {m['id']} {ch.get('chapter')}장 {i}: 알 수 없는 조건 키 {k}")
MG_ALL = {m["id"]: m for m in S["minigames"] + STORY.get("minigames", [])}
for hid, v in STORY.get("mg_variants", {}).items():
    w = f"24 mg_variants {hid}"
    ref(hid, w, {"heritage"})
    m = MG_ALL.get(v.get("minigame"))
    if not m:
        E(f"{w}: 미니게임 {v.get('minigame')} 없음")
        continue
    pr, impl = v.get("params", {}), m["impl"]
    if impl == "quiz":
        bank = pr.get("bank", m.get("params", {}).get("bank", []))
        if len(bank) < int(pr.get("need", 1)):
            E(f"{w}: 문항 {len(bank)} < need {pr.get('need')}")
        for qq in bank:
            if len(qq.get("options", [])) < 2 or not 0 <= int(qq.get("answer", -1)) < len(qq["options"]):
                E(f"{w}: 문항 형식 오류 {qq.get('q', '')[:20]}")
    elif impl == "sliding" and not 3 <= int(pr.get("size", 3)) <= 5:
        E(f"{w}: size {pr.get('size')}")
    elif impl == "trace" and len(pr.get("points", m.get("params", {}).get("points", []))) < 3:
        E(f"{w}: 부적 점 3개 미만")
    elif impl == "timing" and not 0 < float(pr.get("zone", 0.1)) < 0.5:
        E(f"{w}: zone {pr.get('zone')}")
    elif impl == "gauge":
        b = pr.get("band", m.get("params", {}).get("band", [40, 60]))
        if not 0 <= b[0] < b[1] <= 100:
            E(f"{w}: band {b}")

# ================================================================ 보고
cnt = {"01": "heritage", "02": "items", "03": "specialties", "04": "foods", "05": "materials", "06": "life_gear", "07": "mounts",
       "08": "capture", "09": "herbal", "10": "herbs", "11": "food_recipes", "12": "enemies", "13": "companions", "14": "skills",
       "15": "books", "16": "mojak", "17": "instances", "19": "classes", "21": "minigames"}
print("=" * 72)
print("시트 커버리지 (현재 / 목표)")
for s in OV["sheets"]:
    k = cnt.get(s["no"])
    if k is None:
        continue
    n = len(S[k])
    print(f"  {s['no']} {s['name']:<24} {n:>4} / {s['target_count']:<4} {'완비' if n >= s['target_count'] else ''}")
print(f"  월드: 권역 {len(S['regions'])} · 노드 {len(S['nodes'])} · 간선 {len(REG['edges'])} · 국경 {len(REG['border_links'])} · 뱃길 {len(REG['sea_routes'])}")
print(f"  이벤트 {len(S['events'])} + 메인 {len(S['mains'])}×{len(S['mains'][0]['chapters'])}장 · 동선 큐 검증 {routes_checked}건")
print(f"  24 대화·서사: 퀘스트 {len(STORY.get('quests', []))} · 서사 {len(STORY.get('narratives', {}))} · 장면 {n_scene} · 선택지 {n_choice}"
      f" · 전설 잠금 {len(STORY.get('lore_gate', {}))} · 미니게임 변형 {len(STORY.get('mg_variants', {}))}")
print("  신분 임계:", th, f"≈ {OV['rank']['formula']['a']:,.0f}·(L−1)^{OV['rank']['formula']['k']}",
      f"· 명성 예산 최대 {rb.get('max', 0):,} / 기준 {rb.get('reference', 0):,} / 최소 {rb.get('min', 0):,}")
print("  도 5단계 요건:", {p["name"]: p["standing_req"][-1] for p in OV["provinces"]})
for w_ in warnings:
    print("  [경고]", w_)
print("=" * 72)
if errors:
    for e_ in errors:
        print("  [오류]", e_)
    print(f"FAIL — 오류 {len(errors)}건")
    sys.exit(1)
print(f"PASS — 레코드 {len(by)}건, 오류 0, 경고 {len(warnings)}")
