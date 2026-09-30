#!/usr/bin/env python3
"""대화·서사 편집 도구 (data/24_story.json ← tools/gen_story.py ← drafts + edits)

  python3 tools/story_tool.py list [--kind recruit|promotion|gear|recipe|lore] [--status draft|edited|final]
  python3 tools/story_tool.py show q_cp_chakho            서사 전체를 대본처럼 출력 (quest: 접두 생략 가능)
  python3 tools/story_tool.py edit q_cp_chakho            편집용 사본을 data_src/story/edits/<종류>.json 에 만든다(이미 있으면 그대로)
  python3 tools/story_tool.py export [--out docs/대화_서사.xlsx]   엑셀로 내보내기(대사·선택지 한 줄씩)
  python3 tools/story_tool.py import docs/대화_서사.xlsx   엑셀에서 바뀐 칸만 edits/xlsx_import.json 에 기록
  python3 tools/story_tool.py check                       gen_story(병합) → validate_data 실행

원칙: drafts/ 는 생성기가 매번 새로 쓰고, 사람 손은 edits/ 에만 닿는다 → 초안을 다시 만들어도 수정본과 충돌하지 않는다.
edits 형식: {"narratives": {"quest:<id>": {바꿀 부분만}}, "quests": {id: {...}}, "mg_variants": {유산 id: {...}}, "lore_gate": {...}}
  리스트 안 한 칸만 바꿀 땐 {"steps": {"1": {"lines": {"0": {"text": "..."}}}}} 처럼 번호 키를 쓴다.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "db15"))
from common import DATA, ROOT  # noqa: E402
from gen_story import EDITS, deep_merge  # noqa: E402

HEAD = ["key", "part", "idx", "row", "who/choice_id", "text", "req(JSON)", "effects(JSON)", "result", "status", "title"]


def story():
    return json.loads((DATA / "24_story.json").read_text(encoding="utf-8"))


def kind_of(key):
    q = key.split(":", 1)[-1]
    if q.startswith("promo_"):
        return "promotion"
    if q.startswith("q_cp_"):
        return "recruit"
    if q.startswith("q_rcp_"):
        return "recipe"
    if q.startswith("q_lore_"):
        return "lore"
    return "gear"


def norm(key):
    return key if key.startswith("quest:") else "quest:" + key


def parts(nv):
    if "intro" in nv:
        yield "intro", -1, nv["intro"]
    for i, s in enumerate(nv.get("steps", [])):
        yield "step", i, s
    if "outro" in nv:
        yield "outro", -1, nv["outro"]


def speaker(who):
    if who.startswith("npc:"):
        return who.split(":", 2)[-1]
    return who


def cmd_list(a):
    d = story()
    rows = [(k, v) for k, v in d["narratives"].items() if (not a.kind or kind_of(k) == a.kind) and (not a.status or v.get("status") == a.status)]
    for k, v in rows:
        print(f"{v.get('status', ''):7} {kind_of(k):9} {k:40} {v.get('title', '')}")
    print(f"— {len(rows)}건")


def cmd_show(a):
    d = story()
    key = norm(a.key)
    nv = d["narratives"].get(key)
    if not nv:
        sys.exit(f"없음: {key}")
    q = next((x for x in d["quests"] if "quest:" + x["id"] == key), None)
    print(f"■ {nv.get('title', '')}  [{nv.get('status')}]  {key}")
    if q:
        print(f"  동선: {' → '.join(q['route'])}")
    for part, i, sc in parts(nv):
        print(f"\n── {part}{'' if i < 0 else ' ' + str(i + 1)}  (배경 {sc.get('bg', '')})")
        for ln in sc.get("lines", []):
            print(f"  {speaker(ln['who'])}: {ln['text']}")
        for c in sc.get("choices", []):
            req = json.dumps(c.get("req", {}), ensure_ascii=False)
            print(f"   ▷ [{c['id']}] {c['text']}   조건 {req}")
            if c.get("result"):
                print(f"       → {c['result']}")


def cmd_edit(a):
    d = story()
    key = norm(a.key)
    nv = d["narratives"].get(key)
    if not nv:
        sys.exit(f"없음: {key}")
    EDITS.mkdir(parents=True, exist_ok=True)
    p = EDITS / f"{a.file or kind_of(key)}.json"
    cur = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"_about": "사람이 고친 서사. gen_story 가 초안 위에 깊은 병합한다."}
    cur.setdefault("narratives", {})
    if key in cur["narratives"]:
        print(f"이미 편집본이 있습니다: {p.relative_to(ROOT)}")
        return
    body = json.loads(json.dumps(nv))
    body["status"] = "edited"
    cur["narratives"][key] = body
    p.write_text(json.dumps(cur, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"편집본 생성: {p.relative_to(ROOT)} → 고친 뒤 python3 tools/story_tool.py check")


def export_rows(d):
    rows = [HEAD]
    for key, nv in d["narratives"].items():
        for part, i, sc in parts(nv):
            for li, ln in enumerate(sc.get("lines", [])):
                rows.append([key, part, i, f"line{li}", ln["who"], ln["text"], "", "", "", nv.get("status", ""), nv.get("title", "")])
            for ci, c in enumerate(sc.get("choices", [])):
                rows.append([key, part, i, f"choice{ci}", c["id"], c["text"], json.dumps(c.get("req", {}), ensure_ascii=False),
                             json.dumps(c.get("effects", {}), ensure_ascii=False), c.get("result", ""), nv.get("status", ""), nv.get("title", "")])
    return rows


def cmd_export(a):
    import xlsx_io
    out = ROOT / (a.out or "docs/대화_서사.xlsx")
    rows = export_rows(story())
    xlsx_io.write(str(out), [("서사", rows)], widths={"서사": [30, 7, 5, 8, 26, 80, 30, 40, 40, 8, 30]})
    print(f"내보냄: {out} ({len(rows) - 1}줄)")


def _scene(nv, part, i):
    if part == "step":
        return nv["steps"][int(i)] if int(i) < len(nv.get("steps", [])) else {}
    return nv.get(part, {})


def prune(o):
    """빈 dict 제거(바뀐 칸만 남김)"""
    if isinstance(o, dict):
        o = {k: prune(v) for k, v in o.items()}
        return {k: v for k, v in o.items() if v != {}}
    return o


def cmd_import(a):
    import xlsx_io
    sh = xlsx_io.read(a.path)
    rows = sh.get("서사") or next(iter(sh.values()))
    d = story()
    patch = {}
    n = 0
    for r in rows[1:]:
        r = (list(r) + [""] * len(HEAD))[:len(HEAD)]
        key, part, idx, kind, who, text, req, fx, res = r[:9]
        if not key or key not in d["narratives"]:
            continue
        idx = int(idx) if str(idx) not in ("", "-1") else -1
        sc = _scene(d["narratives"][key], part, idx)
        slot = patch.setdefault(key, {})
        tgt = slot.setdefault("steps", {}).setdefault(str(idx), {}) if part == "step" else slot.setdefault(part, {})
        if str(kind).startswith("line"):
            li = int(str(kind)[4:])
            old = sc.get("lines", [])[li] if li < len(sc.get("lines", [])) else {}
            new = {"who": str(who), "text": str(text)}
            if old != new:
                tgt.setdefault("lines", {})[str(li)] = new
                n += 1
        elif str(kind).startswith("choice"):
            ci = int(str(kind)[6:])
            old = sc.get("choices", [])[ci] if ci < len(sc.get("choices", [])) else {}
            new = {"id": str(who), "text": str(text), "req": json.loads(req or "{}"), "effects": json.loads(fx or "{}"), "result": str(res)}
            diff = {k: v for k, v in new.items() if old.get(k, "" if k in ("result",) else {}) != v}
            if diff:
                tgt.setdefault("choices", {})[str(ci)] = diff
                n += 1
    patch = {k: v for k, v in ((k, prune(v)) for k, v in patch.items()) if v}
    for k in patch:
        patch[k]["status"] = "edited"
    if not patch:
        print("바뀐 칸이 없습니다.")
        return
    EDITS.mkdir(parents=True, exist_ok=True)
    p = EDITS / "xlsx_import.json"
    cur = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"_about": "story_tool import 로 엑셀에서 들여온 수정분(바뀐 칸만)."}
    cur["narratives"] = deep_merge(cur.get("narratives", {}), patch)
    p.write_text(json.dumps(cur, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"바뀐 칸 {n}개 · 서사 {len(patch)}건 → {p.relative_to(ROOT)}  (다음: python3 tools/story_tool.py check)")


def cmd_check(_a):
    for step in ("gen_story", "validate_data"):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / f"{step}.py")], cwd=ROOT, capture_output=True, text=True)
        print("\n".join((r.stdout + r.stderr).strip().splitlines()[-4:]))
        if r.returncode:
            sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("--kind")
    p.add_argument("--status")
    p = sub.add_parser("show")
    p.add_argument("key")
    p = sub.add_parser("edit")
    p.add_argument("key")
    p.add_argument("--file", help="edits/<이름>.json (기본: 종류별)")
    p = sub.add_parser("export")
    p.add_argument("--out")
    p = sub.add_parser("import")
    p.add_argument("path")
    sub.add_parser("check")
    a = ap.parse_args()
    {"list": cmd_list, "show": cmd_show, "edit": cmd_edit, "export": cmd_export, "import": cmd_import, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    main()
