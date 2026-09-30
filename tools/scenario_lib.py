"""시나리오 파일(data_src/scenarios/*.json) 읽기·노드 이름 해석·검사 — content_expand.py 와 scenario_tool.py 가 함께 쓴다.

파일 1개 = 시나리오 1편:
  scenario  시작 설정  {id, name, hero_name, class, start_node, money, items{}, desc, portrait?, costume?, prompt_who?}
  main      메인 시나리오 {id, name, lore, era_note?, chapters[{chapter, tier, title, stages[]}]}
  tutorial  튜토리얼 단계 [{id, title, text, hint, cond}] (없으면 [] — 튜토리얼 없이 시작)
  events    이 시나리오 전용 추가 이벤트 [] (20_events 형식, 누구에게나 열림)
노드 표기: 'ND_…' id, '@이름', 동명 노드가 여럿이면 '@권역이름:노드이름' (예: '@평안 남부:순천')
"""
import json
from collections import Counter, deque
from pathlib import Path

from common import DATA, SRC

SC_DIR = SRC / "scenarios"
ACTIONS = {"talk", "choice", "minigame", "deliver", "battle", "instance"}
CONDS = {"ack", "counter", "visited", "at_node", "has_item", "event_progress"}
COUNTERS = {"open_facilities", "open_map", "buy", "sell", "craft", "unpack", "heritage", "battle_win", "trade_accept", "trade_done",
            "save", "event_stage", "gather", "camp"}
EFFECT_KEYS = {"knowledge_xp", "money_mult", "money", "give", "take", "flag"}  # 24_story 대화 효과와 같은 키(명성 제외)


def _load(n):
    return json.loads((DATA / n).read_text(encoding="utf-8"))


class World:
    """노드 이름 → id 조회와 동선 규칙 검사에 필요한 데이터"""
    def __init__(self):
        reg = _load("regions.json")
        self.nodes = {n["id"]: n for n in reg["nodes"]}
        self.rname = {r["id"]: r["name"] for r in reg["regions"]}
        self.adj = {r["id"]: set(r["adjacent"]) for r in reg["regions"]}
        for s in reg["sea_routes"]:
            a, b = self.nodes[s["a"]]["region"], self.nodes[s["b"]]["region"]
            if a != b:
                self.adj[a].add(b)
                self.adj[b].add(a)
        self.by_name = {}
        cnt = Counter(n["name"] for n in reg["nodes"])
        for n in reg["nodes"]:
            self.by_name.setdefault(n["name"], []).append(n["id"])
            self.by_name[f"{self.rname[n['region']]}:{n['name']}"] = [n["id"]]
        self.dup = {k for k, v in cnt.items() if v > 1}
        self.rules = _load("00_overview.json")["route_rules"]
        self.ids = set()
        for f in DATA.glob("*.json"):
            d = json.loads(f.read_text(encoding="utf-8"))
            for v in d.values() if isinstance(d, dict) else []:
                if isinstance(v, list):
                    self.ids |= {r["id"] for r in v if isinstance(r, dict) and "id" in r}

    def resolve(self, ref, where, errs):
        if ref in self.nodes:
            return ref
        if isinstance(ref, str) and ref.startswith("@"):
            key = ref[1:]
            hit = self.by_name.get(key, [])
            if len(hit) == 1:
                return hit[0]
            if len(hit) > 1:
                opts = ", ".join(f"@{self.rname[self.nodes[i]['region']]}:{key}" for i in hit)
                errs.append(f"{where}: '{ref}' 같은 이름 노드가 {len(hit)}곳 → 권역을 붙이세요 ({opts})")
                return None
            near = [k for k in self.by_name if key in k or k in key][:5]
            errs.append(f"{where}: 노드 '{ref}' 없음" + (f" — 비슷한 이름: {', '.join('@' + k for k in near)}" if near else " (scenario_tool.py nodes 로 검색)"))
            return None
        errs.append(f"{where}: 노드 표기 '{ref}' — 'ND_…' id 또는 '@이름'")
        return None

    def check_route(self, ids, tier, where, errs):
        rule = self.rules[str(tier)]
        n0, n1 = rule["nodes"]
        if not n0 <= len(ids) <= n1:
            errs.append(f"{where}: {tier}등급 장은 단계(노드) {n0}~{n1}개 — 지금 {len(ids)}개")
        regs = list(dict.fromkeys(self.nodes[i]["region"] for i in ids))
        if rule["scope"] == "same_region" and len(regs) != 1:
            errs.append(f"{where}: {tier}등급 장은 한 권역 안 — 지금 {', '.join(self.rname[r] for r in regs)}")
        elif rule["scope"] in ("adjacent", "nationwide"):
            r0, r1 = rule["regions"]
            if not r0 <= len(regs) <= r1:
                errs.append(f"{where}: {tier}등급 장은 권역 {r0}~{r1}곳 — 지금 {len(regs)}곳({', '.join(self.rname[r] for r in regs)})")
            if rule["scope"] == "adjacent":
                seen, q = {regs[0]}, deque([regs[0]])
                while q:
                    c = q.popleft()
                    for nb in self.adj[c]:
                        if nb in regs and nb not in seen:
                            seen.add(nb)
                            q.append(nb)
                if len(seen) != len(regs):
                    errs.append(f"{where}: {tier}등급 장의 권역들이 서로 이웃(육로·뱃길)이 아님 — {', '.join(self.rname[r] for r in regs)}")


def load_file(path, world):
    """시나리오 파일 1개 → (scenario, main, steps, events, 오류 목록). 노드 표기는 id 로 바꿔서 돌려준다."""
    errs = []
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    sc, main = dict(doc["scenario"]), json.loads(json.dumps(doc["main"]))
    sid = sc["id"]
    w = Path(path).name
    for k in ("id", "name", "hero_name", "class", "start_node"):
        if not sc.get(k):
            errs.append(f"{w} scenario.{k} 비어 있음")
    if not sid.startswith("sc_"):
        errs.append(f"{w}: scenario.id 는 'sc_' 로 시작")
    sc["start_node"] = world.resolve(sc["start_node"], f"{w} scenario.start_node", errs)
    if sc["class"] not in world.ids:
        errs.append(f"{w}: 직업 {sc['class']} 없음 (cls_eosa · cls_merchant · cls_dosa)")
    for it in sc.get("items", {}):
        if it not in world.ids:
            errs.append(f"{w}: 시작 아이템 {it} 없음")
    main.setdefault("id", "ev_main_" + sid[3:])
    main["class"], main["scenario"], main["type"] = sc["class"], sid, "main"
    main.setdefault("lore", "창작")
    sc["main"] = main["id"]
    last_tier = 0
    for ch in main.get("chapters", []):
        where = f"{w} {ch.get('chapter')}장"
        if ch.get("tier", 0) < last_tier:
            errs.append(f"{where}: 장 등급은 1→5 순서로 오름(신분 Rank = 등급에서 열림)")
        last_tier = ch.get("tier", 0)
        ids = []
        for i, st in enumerate(ch.get("stages", []), 1):
            sw = f"{where} {i}단계"
            nid = world.resolve(st.get("node"), sw, errs)
            st["node"] = nid
            ids.append(nid)
            a = st.get("action", "talk")
            if a not in ACTIONS:
                errs.append(f"{sw}: action '{a}' (가능: {', '.join(sorted(ACTIONS))})")
            if not st.get("text"):
                errs.append(f"{sw}: text(대사) 비어 있음")
            if a == "choice":
                ch_ = st.get("choices", [])
                if len(ch_) < 2:
                    errs.append(f"{sw}: 선택지는 2개 이상")
                for c in ch_:
                    for k in c.get("effects", {}):
                        if k not in EFFECT_KEYS:
                            errs.append(f"{sw}: 선택 효과 '{k}' (가능: {', '.join(sorted(EFFECT_KEYS))})")
            if a == "minigame" and st.get("minigame") not in world.ids:
                errs.append(f"{sw}: 미니게임 {st.get('minigame')} 없음")
            if a == "deliver" and st.get("item") not in world.ids:
                errs.append(f"{sw}: 납품 아이템 {st.get('item')} 없음")
            if a == "battle":
                for wv in st.get("waves", []):
                    for e in wv:
                        if e not in world.ids:
                            errs.append(f"{sw}: 적 {e} 없음")
            if a == "instance" and st.get("instance") not in world.ids:
                errs.append(f"{sw}: 연속전투 {st.get('instance')} 없음")
        if all(ids) and ids:
            world.check_route(ids, ch["tier"], where, errs)
    steps = []
    sc["tutorial"] = sc.get("tutorial") or ("tut_" + sid[3:] if doc.get("tutorial") else "")
    for i, st in enumerate(doc.get("tutorial", []), 1):
        st = dict(st)
        st.setdefault("id", f"{sc['tutorial']}_{i:02d}")
        st["tutorial"] = sc["tutorial"]
        c = st.get("cond", {"type": "ack"})
        tw = f"{w} 튜토리얼 {i}"
        if c.get("type") not in CONDS:
            errs.append(f"{tw}: 조건 '{c.get('type')}' (가능: {', '.join(sorted(CONDS))})")
        if c.get("type") == "counter" and c.get("key") not in COUNTERS:
            errs.append(f"{tw}: 카운터 '{c.get('key')}' (가능: {', '.join(sorted(COUNTERS))})")
        if c.get("type") == "at_node":
            c["node"] = world.resolve(c.get("node"), tw, errs)
        if c.get("type") == "has_item" and c.get("item") not in world.ids:
            errs.append(f"{tw}: 아이템 {c.get('item')} 없음")
        st["cond"] = c
        steps.append(st)
    events = []
    for e in doc.get("events", []):
        e = json.loads(json.dumps(e))
        for i, st in enumerate(e.get("stages", []), 1):
            st["node"] = world.resolve(st.get("node"), f"{w} 이벤트 {e.get('id')} {i}단계", errs)
        if all(s["node"] for s in e.get("stages", [])):
            world.check_route([s["node"] for s in e["stages"]], e.get("tier", 1), f"{w} 이벤트 {e.get('id')}", errs)
        events.append(e)
    return sc, main, steps, events, errs


def load_all():
    world = World()
    out = {"scenarios": [], "mains": [], "steps": [], "events": [], "errors": []}
    seen = set()
    for f in sorted(SC_DIR.glob("*.json")):
        sc, main, steps, events, errs = load_file(f, world)
        if sc["id"] in seen:
            errs.append(f"{f.name}: 시나리오 id {sc['id']} 중복")
        seen.add(sc["id"])
        out["scenarios"].append(sc)
        out["mains"].append(main)
        out["steps"] += steps
        out["events"] += events
        out["errors"] += errs
    return out
