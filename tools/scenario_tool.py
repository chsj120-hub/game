#!/usr/bin/env python3
"""시나리오 작성 도우미 — 노드 찾기 · 새 시나리오 틀 만들기 · 검사(동선 규칙·참조·이동 시간).

  python3 tools/scenario_tool.py nodes 제주            이름·권역에 '제주'가 들어간 노드 (id · 유형 · 시설)
  python3 tools/scenario_tool.py nodes 평안 남부 --type city
  python3 tools/scenario_tool.py ids minigame          미니게임 id 목록 (enemy · item · instance · class 도 가능)
  python3 tools/scenario_tool.py new sc_my_story 김아무개 cls_merchant @한양 경조   새 파일 틀
  python3 tools/scenario_tool.py check                 전체 시나리오 파일 검사(+장별 이동 거리·게임 시간)
  python3 tools/scenario_tool.py check data_src/scenarios/sc_my_story.json
검사를 통과하면 python3 tools/run_pipeline.py --fast 로 게임 데이터에 반영.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scenario_lib as SL  # noqa: E402
from common import DATA  # noqa: E402


def nodes(args):
    w = SL.World()
    t = args[args.index("--type") + 1] if "--type" in args else None
    words = [a for i, a in enumerate(args) if not a.startswith("--") and not (i > 0 and args[i - 1] == "--type")]
    q = " ".join(words)
    rows = [n for n in w.nodes.values() if (q in n["name"] or q in w.rname[n["region"]]) and (not t or n["type"] == t)]
    for n in sorted(rows, key=lambda n: (n["region"], n["hidden"], n["type"], n["name"])):
        ref = f"@{w.rname[n['region']]}:{n['name']}" if n["name"] in w.dup else f"@{n['name']}"
        her = len(n.get("heritage_ids", [])) or (1 if n.get("heritage") else 0)
        print(f"  {ref:<32} {n['id']:<44} {w.rname[n['region']]:<6} {n.get('type_label', n['type']):<10}"
              f"{' 은닉' if n['hidden'] else '     '}  유산 {her}  시설 {','.join(n['facilities'])}")
    print(f"{len(rows)}곳 — 시나리오 파일에는 왼쪽 '@…' 표기나 id 를 그대로 쓰면 됩니다.")


KINDS = {"minigame": ("21_minigames.json", "minigames"), "enemy": ("12_enemies.json", "enemies"), "instance": ("17_instances.json", "instances"),
         "class": ("19_classes_knowledge.json", "classes")}


def ids(args):
    kind = args[0] if args else ""
    if kind == "item":
        for fn, key in (("03_specialties.json", "specialties"), ("04_food_staples.json", "foods"), ("05_materials.json", "materials"),
                        ("10_herbs.json", "herbs"), ("15_recipe_books.json", "books")):
            for r in json.loads((DATA / fn).read_text(encoding="utf-8"))[key]:
                print(f"  {r['id']:<30} {r['name']}  ({fn[:2]} · {r.get('tier', '')}등급)")
        return
    if kind not in KINDS:
        sys.exit("종류: minigame · enemy · instance · class · item")
    fn, key = KINDS[kind]
    for r in json.loads((DATA / fn).read_text(encoding="utf-8"))[key]:
        extra = r.get("impl", "") or (f"{r.get('tier')}등급 {r.get('kind', '')}" if kind == "enemy" else r.get("desc", "")[:30])
        print(f"  {r['id']:<30} {r['name']}  {extra}")


TEMPLATE = {
    "_안내": "시나리오 1편 = 이 파일 하나. 노드는 '@이름'(동명 노드는 '@권역:이름'). 저장 후 python3 tools/scenario_tool.py check",
    "scenario": {"id": "", "name": "", "hero_name": "", "class": "", "start_node": "", "money": 400, "items": {},
                 "desc": "시작 화면에 나오는 한두 줄 소개"},
    "main": {"name": "", "lore": "창작", "era_note": "",
             "chapters": [
                 {"chapter": 1, "tier": 1, "title": "1장 제목", "stages": [
                     {"node": "", "action": "talk", "text": "1장 첫 장면 대사"},
                     {"node": "", "action": "choice", "text": "선택 장면",
                      "choices": [{"id": "a", "text": "선택지 A", "effects": {"knowledge_xp": {"sang": 30}}},
                                  {"id": "b", "text": "선택지 B", "effects": {"money_mult": 1.3}}]}]},
                 {"chapter": 2, "tier": 2, "title": "", "stages": [{"node": "", "action": "talk", "text": ""}, {"node": "", "action": "talk", "text": ""}]},
                 {"chapter": 3, "tier": 3, "title": "", "stages": [{"node": "", "action": "talk", "text": ""}, {"node": "", "action": "talk", "text": ""}, {"node": "", "action": "talk", "text": ""}]},
                 {"chapter": 4, "tier": 4, "title": "", "stages": [{"node": "", "action": "talk", "text": ""}, {"node": "", "action": "talk", "text": ""}, {"node": "", "action": "talk", "text": ""}]},
                 {"chapter": 5, "tier": 5, "title": "", "stages": [{"node": "", "action": "talk", "text": ""}, {"node": "", "action": "talk", "text": ""}, {"node": "", "action": "talk", "text": ""}, {"node": "", "action": "talk", "text": ""}]}]},
    "tutorial": [],
    "events": [],
}


def new(args):
    if len(args) < 4:
        sys.exit("사용: new sc_아이디 주인공이름 cls_직업 @시작노드")
    sid, hero, cls, start = args[0], args[1], args[2], " ".join(args[3:])
    p = SL.SC_DIR / f"{sid}.json"
    if p.exists():
        sys.exit(f"이미 있음: {p}")
    d = json.loads(json.dumps(TEMPLATE, ensure_ascii=False))
    d["scenario"].update(id=sid, name=f"[시나리오] {hero} 편", hero_name=hero, **{"class": cls}, start_node=start)
    d["main"]["name"] = f"{hero} — (제목)"
    for ch in d["main"]["chapters"]:
        for st in ch["stages"]:
            st["node"] = start
    SL.SC_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✓ {p.relative_to(HERE.parent)} — 노드·대사를 채운 뒤 check 로 검사하세요(틀 상태로는 동선 규칙 오류가 나는 것이 정상).")


def travel_hours(w, a, b):
    """두 노드 사이 최단 게임 시간(h, 도보·배율 1) — 장 설계 참고용"""
    import heapq
    ov = json.loads((DATA / "00_overview.json").read_text(encoding="utf-8"))["movement"]
    reg = json.loads((DATA / "regions.json").read_text(encoding="utf-8"))
    g = {}
    for e in reg["edges"] + reg["border_links"]:
        h = e["li"] * reg["px_per_li"] / (ov["v_base"] + 10) / ov["terrain"].get(e["terrain"], 1.0) * ov["game_minutes_per_walk_second"] / 60
        g.setdefault(e["a"], []).append((e["b"], h, e["li"]))
        g.setdefault(e["b"], []).append((e["a"], h, e["li"]))
    for e in reg["sea_routes"]:
        g.setdefault(e["a"], []).append((e["b"], 24.0 * e["days"], 0))
        g.setdefault(e["b"], []).append((e["a"], 24.0 * e["days"], 0))
    dist, pq = {a: (0.0, 0.0)}, [(0.0, 0.0, a)]
    while pq:
        d, li, u = heapq.heappop(pq)
        if u == b:
            return d, li
        if d > dist[u][0]:
            continue
        for v, h, l in g.get(u, []):
            if d + h < dist.get(v, (1e18, 0))[0]:
                dist[v] = (d + h, li + l)
                heapq.heappush(pq, (d + h, li + l, v))
    return None, None


def check(args):
    w = SL.World()
    files = [Path(a) for a in args] or sorted(SL.SC_DIR.glob("*.json"))
    bad = 0
    for f in files:
        sc, main, steps, events, errs = SL.load_file(f, w)
        print(f"■ {f.name} — {sc.get('name')} ({sc.get('hero_name')}, {sc.get('class')})")
        if errs:
            bad += len(errs)
            for e in errs:
                print(f"   ✗ {e}")
            continue
        prev = sc["start_node"]
        for ch in main["chapters"]:
            legs = []
            for st in ch["stages"]:
                h, li = travel_hours(w, prev, st["node"])
                legs.append(f"{w.nodes[st['node']]['name']}({'?' if h is None else f'{li:.0f}리·{h:.0f}h'})")
                prev = st["node"]
            print(f"   ✓ {ch['chapter']}장 [{ch['tier']}등급·Rank {ch['tier']}] {ch.get('title', '')}: " + " → ".join(legs))
        print(f"   ✓ 튜토리얼 {len(steps)}단계 · 추가 이벤트 {len(events)}")
    print("\n검사 통과 — python3 tools/run_pipeline.py --fast 로 반영" if not bad else f"\n오류 {bad}건")
    return 1 if bad else 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("nodes", "ids", "new", "check"):
        print(__doc__)
        return 0
    return {"nodes": nodes, "ids": ids, "new": new, "check": check}[sys.argv[1]](sys.argv[2:]) or 0


if __name__ == "__main__":
    sys.exit(main())
