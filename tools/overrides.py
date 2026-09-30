#!/usr/bin/env python3
"""수정 덮어쓰기(overrides) — 생성기가 다시 만들어도 사람이 고친 값이 남도록, 파이프라인 중간에 마지막으로 얹는다.

  python3 tools/overrides.py where 목검              id 또는 이름 일부로 찾기 → 파일·시트·현재 값·고칠 곳 안내
  python3 tools/overrides.py set eq_w1_mokgeom atk 7         값 하나 고치기(data_src/overrides/local.json 에 기록 + 바로 적용)
  python3 tools/overrides.py set overview economy.quest_money.base 110
  python3 tools/overrides.py set doc:21_minigames.json node_type_default.ruin '"mg_takbon"'
  python3 tools/overrides.py unset eq_w1_mokgeom atk          되돌리기(원래 값 복원)
  python3 tools/overrides.py copy en_dokkaebi en_my_dokkaebi --name "새 도깨비"   기존 행을 복제해 새 행 추가
  python3 tools/overrides.py list                            지금 걸려 있는 덮어쓰기 전부
  python3 tools/overrides.py apply                           (파이프라인이 자동 실행) data_src/overrides/*.json 적용

파일 형식 (data_src/overrides/*.json, 파일 이름 순서로 합침 — 사람마다·주제마다 파일을 나누면 충돌이 없다):
  {"rows":     {"<행 id>": {"필드": 값, "중첩": {"키": 값}}},        # 모든 시트의 id 행(아이템·적·동료·노드·유산·스킬…)
   "overview": {"economy": {"quest_money": {"base": 110}}},          # 00_overview.json
   "docs":     {"21_minigames.json": {"node_type_default": {...}}},  # 행이 아닌 문서 칸
   "add":      {"12_enemies.json:enemies": [{"id": "en_new", ...}]}} # 새 행 추가(적용할 때마다 교체)
  dict 는 깊은 병합, 목록·숫자·문자열은 통째로 바꿈. 되돌리기 기록은 data_src/overrides/_applied.json(자동).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ROOT, SRC, load, save  # noqa: E402

OVD = SRC / "overrides"
APPLIED = OVD / "_applied.json"
LOCAL = OVD / "local.json"
TAG = "override"
MISSING = {"__missing__": True}
# 값을 덮어써도 economy_sim 이 다시 계산하는 칸 — 규칙(economy·content_plan)을 고쳐야 함
AUTO = ["rank.table", "rank.formula", "rank.reputation_budget", "rank.calibration_basis", "provinces"]
STORY_HINT = "24_story(대화·서사·전설·비전 전수·미니게임 변형)는 data_src/story/edits 에서 고칩니다 → tools/story_tool.py"
# 파일별 원천 안내(where 출력용)
SOURCE = {
    "regions.json": "data_src/world_table.json(노드·권역·뱃길) · node_geo.json(좌표) → build_world. 값만 바꿀 땐 overrides",
    "01_heritage.json": "data_src/heritage_curated.json(수작업 유산·등급) · heritage450/*.xlsx(국가유산 448) → build_world. 값만 바꿀 땐 overrides",
    "13_companions.json": "data_src/db15/DB15_원본.xlsx → db15/audit_fix → merge_companions. 값만 바꿀 땐 overrides",
    "08_capture_tools.json": "tools/gen_systematic.py 가 매번 생성 → overrides",
    "16_mojak_gear.json": "tools/gen_systematic.py 가 매번 생성 → overrides",
    "23_tutorial.json": "시나리오 튜토리얼은 data_src/scenarios/*.json, 나머지는 tools/content_expand.py → overrides",
    "20_events.json": "시나리오 메인은 data_src/scenarios/*.json, 역사·설화 이벤트는 tools/content_expand.py → overrides",
    "24_story.json": STORY_HINT,
}


# ---------------------------------------------------------------- 데이터 색인
def data_files():
    return sorted(p.name for p in DATA.glob("*.json"))


def row_index(docs):
    idx = {}
    for fn, d in docs.items():
        for key, rows in d.items():
            if isinstance(rows, list):
                for r in rows:
                    if isinstance(r, dict) and "id" in r:
                        idx.setdefault(r["id"], (fn, key, r))
    return idx


def load_overrides():
    acc = {"rows": {}, "overview": {}, "docs": {}, "add": {}}
    files = sorted(p for p in OVD.glob("*.json") if not p.name.startswith("_")) if OVD.exists() else []
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            sys.exit(f"[overrides] JSON 오류 {p.name}: {e}")
        for k in acc:
            v = d.get(k, {})
            if k == "add":
                for sk, rows in v.items():
                    acc["add"].setdefault(sk, []).extend(rows)
            else:
                acc[k] = merge(acc[k], v)
        for k in d:
            if not k.startswith("_") and k not in acc:
                sys.exit(f"[overrides] {p.name}: 알 수 없는 최상위 키 '{k}' (rows · overview · docs · add)")
    return acc, [p.name for p in files]


def merge(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = merge(a[k], v) if k in a else v
        return out
    return b


def leaves(obj, prefix=()):
    """중첩 dict → (경로, 값) 목록. dict 가 아닌 값(목록 포함)이 잎"""
    if isinstance(obj, dict):
        for k, v in obj.items():   # 빈 dict 는 건너뜀(unset 뒤 남은 빈 칸)
            yield from leaves(v, prefix + (k,))
    else:
        yield prefix, obj


def get_path(obj, path):
    for k in path:
        if not isinstance(obj, dict) or k not in obj:
            return MISSING
        obj = obj[k]
    return obj


def set_path(obj, path, val):
    for k in path[:-1]:
        if not isinstance(obj.get(k), dict):
            obj[k] = {}
        obj = obj[k]
    if val == MISSING:
        obj.pop(path[-1], None)
    else:
        obj[path[-1]] = val


# ---------------------------------------------------------------- 적용
def apply(verbose=True):
    ov, files = load_overrides()
    docs = {fn: load(fn) for fn in data_files()}
    idx = row_index(docs)
    applied = json.loads(APPLIED.read_text(encoding="utf-8")) if APPLIED.exists() else {}
    errs, now, dirty = [], {}, set()

    # 1) 이전 적용분 중 사라진 덮어쓰기는 원래 값으로 (그 사이 생성기가 새 값을 썼으면 그대로 둠)
    targets = []
    for rid, patch in ov["rows"].items():
        if rid not in idx:
            errs.append(f"rows: id '{rid}' 없음 (where 로 찾아 보세요)")
            continue
        fn, _, row = idx[rid]
        if fn == "24_story.json":
            errs.append(f"rows: {rid} — {STORY_HINT}")
            continue
        for path, val in leaves(patch):
            targets.append((f"row:{rid}", row, fn, path, val))
    for path, val in leaves(ov["overview"]):
        if any(".".join(path).startswith(a) for a in AUTO):
            errs.append(f"overview.{'.'.join(path)}: economy_sim 이 자동 보정하는 값 — economy·content_plan 규칙을 고치세요")
            continue
        targets.append(("doc:00_overview.json", docs["00_overview.json"], "00_overview.json", path, val))
    for fn, patch in ov["docs"].items():
        if fn not in docs:
            errs.append(f"docs: 파일 {fn} 없음")
            continue
        if fn == "24_story.json":
            errs.append(f"docs: {STORY_HINT}")
            continue
        for path, val in leaves(patch):
            targets.append((f"doc:{fn}", docs[fn], fn, path, val))
    if errs:
        for e in errs:
            print("  [오류]", e)
        sys.exit(f"[overrides] 오류 {len(errs)}건 — 적용하지 않았습니다")

    want = {f"{owner}|{'/'.join(path)}" for owner, _, _, path, _ in targets}
    for key, rec in list(applied.get("values", {}).items()):
        if key in want or key.startswith("add|"):
            continue
        owner, p = key.split("|", 1)
        path = tuple(p.split("/"))
        if owner.startswith("row:"):
            hit = idx.get(owner[4:])
            obj, fn = (hit[2], hit[0]) if hit else (None, None)
        else:
            fn = owner[4:]
            obj = docs.get(fn)
        if obj is not None and get_path(obj, path) == rec["set"]:
            set_path(obj, path, rec["orig"])
            dirty.add(fn)
            if verbose:
                print(f"  되돌림 {owner[4:]} {'.'.join(path)} → {rec['orig'] if rec['orig'] != MISSING else '(없음)'}")

    # 2) 덮어쓰기
    for owner, obj, fn, path, val in targets:
        key = f"{owner}|{'/'.join(path)}"
        cur = get_path(obj, path)
        prev = applied.get("values", {}).get(key)
        orig = prev["orig"] if prev and cur == prev["set"] else cur   # 생성기가 다시 만든 값이면 그것이 새 원래 값
        now[key] = {"orig": orig, "set": val}
        if cur != val:
            set_path(obj, path, val)
            dirty.add(fn)

    # 3) 새 행 (적용할 때마다 이전 override 행을 지우고 다시 넣음)
    n_add = 0
    for fn, d in docs.items():
        for key, rows in d.items():
            if isinstance(rows, list) and any(isinstance(r, dict) and r.get("generated") == TAG for r in rows):
                d[key] = [r for r in rows if not (isinstance(r, dict) and r.get("generated") == TAG)]
                dirty.add(fn)
    idx = row_index(docs)
    for sk, rows in ov["add"].items():
        fn, _, key = sk.partition(":")
        if fn not in docs or not isinstance(docs[fn].get(key), list):
            sys.exit(f"[overrides] add: '{sk}' — '파일.json:목록키' 형식이어야 함 (예 12_enemies.json:enemies)")
        for r in rows:
            if "id" not in r or r["id"] in idx:
                sys.exit(f"[overrides] add: id 없음 또는 중복 '{r.get('id')}'")
            docs[fn][key].append({**r, "generated": TAG})
            idx[r["id"]] = (fn, key, r)
            n_add += 1
            dirty.add(fn)

    for fn in sorted(dirty):
        save(fn, docs[fn])
    OVD.mkdir(parents=True, exist_ok=True)
    APPLIED.write_text(json.dumps({"_about": "overrides.py 자동 기록(되돌리기용). 직접 고치지 마세요.", "values": now},
                                  ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[overrides] 파일 {len(files)}개 · 값 {len(targets)}칸 · 새 행 {n_add} · 바뀐 데이터 파일 {len(dirty)}")


# ---------------------------------------------------------------- 편집 명령
def parse_target(t):
    if t == "overview":
        return "overview", None
    if t.startswith("doc:"):
        return "docs", t[4:]
    return "rows", t


def parse_value(s):
    try:
        return json.loads(s)
    except ValueError:
        return s   # 따옴표 없이 쓴 문자열


def edit_local(fn_mut):
    OVD.mkdir(parents=True, exist_ok=True)
    cur = json.loads(LOCAL.read_text(encoding="utf-8")) if LOCAL.exists() else {"_about": "overrides.py set/unset 으로 쌓인 수정값. 직접 고쳐도 됩니다."}
    fn_mut(cur)
    LOCAL.write_text(json.dumps(cur, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def cmd_set(a):
    kind, name = parse_target(a.target)
    path = a.path.split(".")
    val = parse_value(a.value)
    if kind == "overview" and any(a.path.startswith(x) for x in AUTO):
        sys.exit(f"overview.{a.path} 는 economy_sim 이 자동 보정합니다 — economy·content_plan 규칙을 고치세요")
    if kind == "rows":
        docs = {fn: load(fn) for fn in data_files()}
        hit = row_index(docs).get(name)
        if not hit:
            sys.exit(f"id '{name}' 없음 — python3 tools/overrides.py where {name}")
        old = get_path(hit[2], path)
        if old == MISSING:
            print(f"  (새 필드) {name}.{a.path}")
        elif type(old) is not type(val) and not (isinstance(old, (int, float)) and isinstance(val, (int, float))):
            print(f"  [주의] 원래 값 {old!r} 와 형식이 다릅니다 → {val!r}")

    def mut(cur):
        box = cur.setdefault(kind, {})
        if name:
            box = box.setdefault(name, {})
        set_path(box, path, val)
    edit_local(mut)
    print(f"기록: {LOCAL.relative_to(ROOT)} ← {a.target} {a.path} = {json.dumps(val, ensure_ascii=False)}")
    apply(verbose=True)
    print("다음: python3 tools/run_pipeline.py --fast (보정·검증까지 반영)")


def cmd_unset(a):
    kind, name = parse_target(a.target)
    path = a.path.split(".")

    def mut(cur):
        box = cur.get(kind, {})
        if name:
            box = box.get(name, {})
        set_path(box, path, MISSING)
        if name and not cur.get(kind, {}).get(name):
            cur.get(kind, {}).pop(name, None)
    edit_local(mut)
    apply(verbose=True)


def cmd_copy(a):
    """기존 행을 복제해 새 행으로 추가(형식이 맞는 새 콘텐츠를 만드는 가장 쉬운 길) → local.json add"""
    docs = {fn: load(fn) for fn in data_files()}
    idx = row_index(docs)
    if a.src not in idx:
        sys.exit(f"id '{a.src}' 없음")
    if a.new in idx:
        sys.exit(f"id '{a.new}' 는 이미 있습니다")
    fn, key, row = idx[a.src]
    if fn == "24_story.json":
        sys.exit(STORY_HINT)
    new = {k: v for k, v in json.loads(json.dumps(row)).items() if not k.startswith("_") and k != "generated"}
    new["id"] = a.new
    if a.name:
        new["name"] = a.name

    def mut(cur):
        cur.setdefault("add", {}).setdefault(f"{fn}:{key}", []).append(new)
    edit_local(mut)
    print(f"추가: {fn}:{key} ← {a.new} ({a.src} 복제) — {LOCAL.relative_to(ROOT)} 의 add 에서 값을 고치세요")
    apply(verbose=False)


def cmd_list(_a):
    ov, files = load_overrides()
    print(f"파일: {', '.join(files) or '(없음)'}")
    for rid, patch in ov["rows"].items():
        for path, val in leaves(patch):
            print(f"  행   {rid:32} {'.'.join(path):28} = {json.dumps(val, ensure_ascii=False)[:60]}")
    for path, val in leaves(ov["overview"]):
        print(f"  개요 {'.'.join(path):61} = {json.dumps(val, ensure_ascii=False)[:60]}")
    for fn, patch in ov["docs"].items():
        for path, val in leaves(patch):
            print(f"  문서 {fn}:{'.'.join(path):40} = {json.dumps(val, ensure_ascii=False)[:60]}")
    for sk, rows in ov["add"].items():
        print(f"  추가 {sk}: {', '.join(r.get('id', '?') for r in rows)}")


def cmd_where(a):
    docs = {fn: load(fn) for fn in data_files()}
    q = a.query
    ov, _ = load_overrides()
    hits = []
    for rid, (fn, key, row) in row_index(docs).items():
        if rid == q or q in rid or q in str(row.get("name", "")):
            hits.append((rid != q, rid, fn, key, row))
    hits.sort(key=lambda h: (h[0], h[1]))
    if not hits:
        sys.exit("찾지 못했습니다 — id 일부나 이름 일부로 다시 검색해 보세요")
    for _, rid, fn, key, row in hits[: a.limit]:
        tag = f" · 생성 행({row['generated']})" if row.get("generated") else ""
        print(f"■ {rid}  「{row.get('name', '')}」  {fn} → {key}{tag}")
        if len(hits) == 1 or rid == q:
            for k, v in row.items():
                if k.startswith("_"):
                    continue
                s = json.dumps(v, ensure_ascii=False)
                mark = "  ← 덮어쓰기 중" if k in ov["rows"].get(rid, {}) else ""
                print(f"    {k:18} {s[:100]}{'…' if len(s) > 100 else ''}{mark}")
        print(f"    고칠 곳: {SOURCE.get(fn, '값은 overrides(set), 새 행은 overrides add')}")
        if fn != "24_story.json":
            print(f"    예) python3 tools/overrides.py set {rid} <필드> <값>")
    if len(hits) > a.limit:
        print(f"… 외 {len(hits) - a.limit}건 (--limit)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("apply")
    sub.add_parser("list")
    p = sub.add_parser("where")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=12)
    p = sub.add_parser("set")
    p.add_argument("target", help="행 id | overview | doc:<파일.json>")
    p.add_argument("path", help="필드 경로(점으로 구분) 예: atk, economy.quest_money.base")
    p.add_argument("value", help="JSON 값(숫자·true·[..]·{..}) 또는 문자열")
    p = sub.add_parser("copy")
    p.add_argument("src", help="복제할 행 id")
    p.add_argument("new", help="새 id")
    p.add_argument("--name")
    p = sub.add_parser("unset")
    p.add_argument("target")
    p.add_argument("path")
    a = ap.parse_args()
    {"apply": lambda _: apply(), "list": cmd_list, "copy": cmd_copy, "where": cmd_where, "set": cmd_set, "unset": cmd_unset}[a.cmd](a)


if __name__ == "__main__":
    main()
