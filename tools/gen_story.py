#!/usr/bin/env python3
"""대화·서사·퀘스트·미니게임 변형 생성기 → data/24_story.json

구성
  quests       새 퀘스트 정의(레시피 비전 전수 recipe · 국보급 전설 lore) — 동선은 route_rules/lore_quest_rules 자동
  narratives   "quest:<퀘스트 id>" → {status, title, intro, steps[동선 노드 수], outro}  (영입·승급·장비·탈것·레시피·전설)
  lore_gate    유산 id → 전설 퀘스트 id (완수해야 답사 가능)
  mg_variants  유산 id → {minigame, params 덮어쓰기} — 같은 미니게임을 유산마다 문항·단계·난이도만 다르게
  minigames    새 미니게임 카탈로그(mg_heritage_quiz)

대화(scene) 형식: {bg, cast[], lines[{who, text}], choices[{id, text, req, effects, result}]}
  who = hero | 동료 id | npc:<역할>:<이름>

수정 방법(충돌 없음)
  data_src/story/drafts/*.json  ← 이 스크립트가 매번 새로 씀(직접 고치지 말 것)
  data_src/story/edits/*.json   ← 사람이 고치는 곳. 같은 키를 깊은 병합으로 덮어씀(절대 덮어쓰지 않음)
  tools/story_tool.py           ← 목록·보기·편집 파일 만들기·엑셀 왕복·검사
"""
import hashlib
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, SRC, load, save, quest_reward  # noqa: E402
from story_legends import LEGENDS, CATEGORY_TONE, ROLE_JOIN, KNOW_APPROACH  # noqa: E402

STORY = SRC / "story"
DRAFTS = STORY / "drafts"
EDITS = STORY / "edits"

OV = load("00_overview.json")
REG = load("regions.json")
NODES = {n["id"]: n for n in REG["nodes"]}
REGIONS = {r["id"]: r for r in REG["regions"]}
HER = load("01_heritage.json")["heritage"]
HERD = {h["id"]: h for h in HER}
COMP = load("13_companions.json")["companions"]
EQ = load("02_equipment.json")["items"]
MTS = load("07_mounts.json")["mounts"]
SPD = load("03_specialties.json")
SPEC = {s["id"]: s for s in SPD["specialties"]}
SPR = SPD["specialty_recipes"]
MG = {m["id"]: m for m in load("21_minigames.json")["minigames"]}
MG_DEFAULT = load("21_minigames.json")["node_type_default"]
ROWS = {}
for f in ("05_materials.json", "04_food_staples.json", "10_herbs.json"):
    for k, v in load(f).items():
        if isinstance(v, list):
            for r in v:
                if isinstance(r, dict) and "id" in r:
                    ROWS[r["id"]] = r
KNAME = {"yu": "유(儒)", "bul": "불(佛)", "seon": "선(仙)", "sa": "사(史)", "nong": "농(農)", "gong": "공(工)", "sang": "상(商)"}
FACTION_K = {"yu": "yu", "bul": "bul", "seon": "seon"}
CAT_K = {"architecture": "sa", "document": "yu", "metal": "gong", "ceramic_specialty": "gong", "folk_craft": "seon", "scenic": "sa"}
NT_K = {"temple": "bul", "stupa": "bul", "seowon": "yu", "tomb": "yu", "shrine": "seon"}
CAT_KO = {"architecture": "건축·석조", "document": "전적·기록", "metal": "금속 공예", "ceramic_specialty": "도자·특산", "folk_craft": "민속·불상 공예", "scenic": "명승"}


def h32(*parts):
    return int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def pick(seq, *key):
    return seq[h32(*key) % len(seq)]


def name_of(i):
    if i in NODES:
        return NODES[i]["name"]
    if i in HERD:
        return HERD[i]["name"]
    return i


def node_of(i):
    return i if i in NODES else HERD.get(i, {}).get("node", i)


def region_of(i):
    return NODES[i]["region"] if i in NODES else HERD.get(i, {}).get("region", "")


def josa(word, a, b):
    """받침 유무로 조사 선택 (이/가, 을/를, 은/는, 과/와, 으로/로)"""
    w = re.sub(r"[\s)\]』》」】]+$", "", word)
    if not w:
        return a
    c = w[-1]
    if "가" <= c <= "힣":
        jong = (ord(c) - 0xAC00) % 28
        if a == "으로" and jong == 8:
            return b
        return a if jong else b
    return a


_JOSA = re.compile(r"\(으\)로|\(이\)라|(을|이|은|과)\((를|가|는|와)\)")


def fix_josa(text):
    """'X(으)로 · X을(를) · X이(가) · X은(는) · X과(와)' 를 앞 글자 받침에 맞춰 확정"""
    def rep(m):
        prev = re.sub(r"[\s)\]』》」】'\"]+$", "", text[:m.start()])
        if m.group(0) == "(으)로":
            full, b = "으로", "로"
        elif m.group(0) == "(이)라":
            full, b = "이라", "라"
        else:
            full, b = m.group(1), m.group(2)
        return josa(prev, full, b) if prev else full
    return _JOSA.sub(rep, text)


def fix_all(o):
    if isinstance(o, str):
        return fix_josa(o)
    if isinstance(o, list):
        return [fix_all(x) for x in o]
    if isinstance(o, dict):
        return {k: fix_all(v) for k, v in o.items()}
    return o


# ================================================================ NPC (노드 유형 → 역할·호칭)
NPC_ROLE = {"city": ("official", "아전"), "temple": ("monk", "노승"), "station": ("soldier", "역졸"), "town": ("elder", "촌로"),
            "spring": ("innkeeper", "주모"), "fort": ("soldier", "군관"), "scenic": ("traveler", "유람객"), "tomb": ("official", "능참봉"),
            "seowon": ("scholar", "유생"), "shrine": ("shaman", "무녀"), "stupa": ("monk", "노승"), "ruin": ("elder", "촌로"),
            "wreck": ("fisher", "어부"), "beacon": ("soldier", "봉수군"), "port": ("fisher", "뱃사람"), "kiln": ("merchant", "도공")}
SURN = "김이박최정강조윤장임한오서신권황안송류홍전고문손배".replace("", " ").split()
MONK = ["혜명", "무진", "청허", "도안", "월조", "선각", "법운", "지공", "해안", "원명", "성우", "보각"]
SHAMAN = ["연화 만신", "옥분 만신", "금단 무녀", "달래 무녀", "명월 만신"]


def npc(node_id, salt=""):
    nd = NODES.get(node_of(node_id), {})
    role, title = NPC_ROLE.get(nd.get("type", "town"), ("elder", "촌로"))
    k = (node_of(node_id), salt)
    if role == "monk":
        nm = f"{title} {pick(MONK, *k)}"
    elif role == "shaman":
        nm = pick(SHAMAN, *k)
    else:
        nm = f"{title} {pick(SURN, *k)}씨"
    return f"npc:{role}:{nm}"


# ================================================================ 노드 유형별 장면 문구 ({thing}: 퀘스트의 대상)
ACT = {
    "city": ["관아 아전에게 {thing}의 행방을 수소문한다", "장터 객주들 사이에서 {thing} 이야기를 캐묻는다", "읍성 관문 기록을 뒤져 {thing}의 자취를 찾는다"],
    "town": ["마을 어귀 정자나무 아래서 {thing} 이야기를 듣는다", "우물가 아낙들이 {thing}에 얽힌 소문을 들려준다", "촌로의 사랑방에서 {thing}의 옛일을 묻는다"],
    "temple": ["노승에게 {thing}에 얽힌 인연을 여쭙는다", "절 마당을 쓸던 동자승이 {thing} 이야기를 꺼낸다", "법당 뒤 오래된 기록에서 {thing}의 이름을 찾는다"],
    "stupa": ["탑돌이 하던 노파가 {thing}을(를) 기억해 낸다", "탑신에 새겨진 글자에서 {thing}의 단서를 읽는다"],
    "station": ["역졸에게 {thing}을(를) 보았다는 파발꾼의 이야기를 듣는다", "역참 마구간에서 {thing}의 흔적을 찾는다"],
    "fort": ["군관이 성벽 위에서 {thing}에 얽힌 소문을 전한다", "진영 군기고 장부에서 {thing}의 행방을 짚는다"],
    "scenic": ["경치를 즐기던 유람객이 {thing} 이야기를 들려준다", "바위에 새겨진 옛 시에서 {thing}의 단서를 읽는다"],
    "seowon": ["유생들이 강당에서 {thing}에 대해 논한다", "서원 장서각에서 {thing}의 기록을 찾는다"],
    "shrine": ["무녀가 방울을 흔들며 {thing}의 행방을 점친다", "당산나무 금줄 아래서 {thing}의 이야기를 듣는다"],
    "tomb": ["능참봉이 {thing}에 얽힌 옛 제향 이야기를 들려준다", "능 앞 문인석 곁에서 {thing}의 자취를 찾는다"],
    "ruin": ["옛터에서 깨진 조각을 줍던 촌로가 {thing}을(를) 떠올린다", "잡초 우거진 주춧돌 사이에서 {thing}의 흔적을 찾는다"],
    "wreck": ["어부가 그물을 손질하며 {thing} 이야기를 꺼낸다", "갯벌에 드러난 옛 뱃조각에서 {thing}의 단서를 찾는다"],
    "spring": ["온천 주모가 탕에 들렀던 길손에게 들은 {thing} 이야기를 전한다"],
    "beacon": ["봉수군이 봉화대에서 본 {thing} 이야기를 전한다"],
}


def act(node_id, thing, salt):
    t = NODES.get(node_of(node_id), {}).get("type", "town")
    return pick(ACT.get(t, ACT["town"]), node_id, salt).format(thing=thing)


def line(who, text):
    return {"who": who, "text": text}


def scene(bg, lines, choices=None, cast=None):
    d = {"bg": bg, "lines": lines}
    if cast:
        d["cast"] = cast
    if choices:
        d["choices"] = choices
    return d


def cost_of(tier, share=0.3):
    return max(10, int(round(quest_reward(OV, tier, "gear", "money") * share / 10.0)) * 10)


def choice_set(tier, k, know_text, money_text, free_text, results=None, extra=None, salt=""):
    """선택지 3종(지식 조건 · 엽전 · 무조건). 조건 미충족 선택지는 화면에서 비활성+사유 표시."""
    need = max(1, min(8, tier + 1))
    cost = cost_of(tier)
    r = results or {}
    out = [
        {"id": "know", "text": f"〔{KNAME[k]} {need}〕 {know_text}", "req": {"knowledge": {k: need}},
         "effects": {"knowledge_xp": {k: 25 * tier}}, "result": r.get("know", "")},
        {"id": "pay", "text": f"〔엽전 {cost}냥〕 {money_text}", "req": {"money": cost},
         "effects": {"money": -cost, "knowledge_xp": {"sang": 10 * tier}, "flag": f"paid:{salt}"}, "result": r.get("pay", "")},
    ]
    if extra:
        out.append(extra)
    out.append({"id": "plain", "text": free_text, "req": {}, "effects": {}, "result": r.get("plain", "")})
    return out


# ================================================================ 동선 자동 생성 (규칙은 00_overview)
def adj_regions(r):
    out = set(REGIONS[r].get("adjacent", []))
    for s in REG.get("sea_routes", []):
        ra, rb = region_of(s["a"]), region_of(s["b"])
        if ra == r and rb != r:
            out.add(rb)
        if rb == r and ra != r:
            out.add(ra)
    return sorted(out)


def region_nodes(r, exclude=(), types=None, visible=True):
    xs = [n for n in REG["nodes"] if n["region"] == r and n["id"] not in exclude and (not visible or not n.get("hidden"))]
    if types:
        pref = [n for n in xs if n["type"] in types]
        if pref:
            xs = pref + [n for n in xs if n["type"] not in types]
    return xs


def hub(r, exclude=(), near=None):
    if near:  # 목적지에 가장 가까운 그 권역의 고을(도시·읍)
        xs = [n for n in region_nodes(r, exclude, None) if n["type"] in ("city", "town")]
        if xs:
            return min(xs, key=lambda n: dist(n["id"], near))["id"]
    h = REGIONS[r].get("hub")
    if h and h not in exclude:
        return h
    xs = region_nodes(r, exclude, ["city", "town"])
    return xs[0]["id"] if xs else None


def dist(a, b):
    pa, pb = NODES[node_of(a)]["pos"], NODES[node_of(b)]["pos"]
    return ((pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2) ** 0.5


def pick_nodes(r, n, exclude, types, seed, near=None):
    """권역 안에서 n개. near 가 있으면 그 목적지에 가까운 곳 위주(선호 유형 먼저) — 서사 동선이 한 고장 안에서 이어지도록"""
    pool = region_nodes(r, exclude, None)
    if len(pool) < n:
        pool = region_nodes(r, exclude, None, visible=False)
    if near:
        pool.sort(key=lambda x: dist(x["id"], near))
        pool = pool[:max(n * 4, 8)]
    if types:
        pool = [x for x in pool if x["type"] in types] + [x for x in pool if x["type"] not in types]
    k = min(len(pool), max(n * 2, 4))
    head = pool[:k]
    random.Random(seed).shuffle(head)
    return [x["id"] for x in head[:n]]


def route_for(end, tier, rule, seed, types=None):
    """end(노드 또는 유산 id)로 끝나는 동선. rule={nodes, scope, regions}"""
    nmin = int(rule["nodes"][0])
    r0 = region_of(end)
    ex = {node_of(end), end}
    scope = rule.get("scope", "same_region")
    if scope == "same_region":
        mids = pick_nodes(r0, nmin - 1, ex, types, seed, end)
        mids.sort(key=lambda x: -dist(x, end))   # 먼 곳 → 가까운 곳 → 목적지
        return mids + [end]
    rng = random.Random(seed)
    if scope == "adjacent":
        nb = adj_regions(r0)
        r1 = nb[rng.randrange(len(nb))]
        a = hub(r1, ex, end)
        mids = pick_nodes(r0, nmin - 2, ex | {a}, types, seed, end)
        return [a] + mids + [end]
    # nationwide: 3개 권역 이상을 거쳐 온다
    nb = adj_regions(r0)
    r1 = nb[rng.randrange(len(nb))]
    nb2 = [x for x in adj_regions(r1) if x not in (r0, r1)]
    r2 = nb2[rng.randrange(len(nb2))] if nb2 else r1
    a, b = hub(r2, ex, end), hub(r1, ex, end)
    mids = pick_nodes(r0, max(0, nmin - 3), ex | {a, b}, types, seed, end)
    return [a, b] + mids + [end]


def check_route(route, rule):
    n = rule["nodes"]
    if not (n[0] <= len(route) <= n[1]) or len(set(route)) != len(route):
        return False
    regs = {region_of(x) for x in route}
    if "" in regs:
        return False
    if rule.get("scope") == "same_region":
        return len(regs) == 1
    rr = rule.get("regions", [1, 17])
    return rr[0] <= len(regs) <= rr[1]


# ================================================================ 1) 동료 영입
def recruit_narr(c):
    cid, nm, sig = c["id"], c["name"], c.get("signature_item") or f"{c['name']}의 물건"
    route = c["recruit"]["route"]
    cond = c["recruit"].get("condition") or f"{nm}의 부탁을 들어주기"
    cond = re.sub(r"\s*(시 영입|퀘스트 완수|완수)$", "", cond).strip()
    tone = next((v for k, v in CATEGORY_TONE.items() if str(c.get("category") or "").startswith(k)), CATEGORY_TONE["역사 인물"])
    pk = c.get("primary_knowledge", "sa")
    desc = (c.get("desc") or "").split(". ")[0].rstrip(".")
    t = int(c["tier"])
    steps = []
    for i, node in enumerate(route):
        n0 = npc(node, cid)
        if i < len(route) - 1:
            steps.append(scene(node, [
                line(n0, f"{nm} 말이오? {desc + '. ' if desc and i == 0 else ''}요즘 {name_of(route[i + 1])} 쪽에서 보았다는 이가 있소."),
                line("hero", f"({act(node, nm, i)}) 고맙소. {name_of(route[i + 1])}(으)로 가 보겠소."),
            ], cast=["hero", n0]))
        else:
            steps.append(scene(node, [
                line(n0, f"저기 계신 분이 바로 {nm}, 그분이오."),
                line(cid, f"({tone['meet'].format(sig=sig)}) 나를 찾아왔다고? 그렇다면 청이 하나 있소 — 「{cond}」. 이 일을 해내면 함께 가겠소."),
                line("hero", "어떻게 도우면 좋겠소?"),
            ], choice_set(t, pk, KNOW_APPROACH.get(pk, "지혜를 모은다"), "필요한 물자를 넉넉히 사서 돕는다", "직접 발로 뛰어 돕는다",
                          {"know": f"{nm}: 역시 보는 눈이 있구려. 그 방법이면 되겠소.", "pay": f"{nm}: 이렇게까지… 신세를 졌소.",
                           "plain": f"{nm}: 땀 흘려 도와준 마음, 잊지 않겠소."}, salt=cid), cast=["hero", cid, n0]))
    outro = scene(route[-1], [
        line(cid, f"{tone['vow']} {ROLE_JOIN.get(c.get('role', 'support'), '')}"),
        line("hero", f"{nm}, 함께 팔도를 누빕시다."),
    ], cast=["hero", cid])
    intro = scene(route[0], [
        line(npc(route[0], cid + "i"), f"{nm}을(를) 찾는다면 먼저 {name_of(route[0])}에서 수소문해 보시오. 「{cond}」 — 이 일을 해내야 마음을 연다더이다."),
    ], cast=["hero", npc(route[0], cid + "i")])
    return {"status": "draft", "title": f"동료 영입: {nm}", "intro": intro, "steps": steps, "outro": outro}


# ================================================================ 2) 동료 승급
PROMO_THEME = {2: ("손에 익은 연장", "처음 받은 신뢰를 시험받는다"), 3: ("장인의 비법", "옛 인연을 찾아 이웃 고을까지 간다"),
               4: ("팔도 명인 겨루기", "이름이 알려진 만큼 더 큰 시험이 온다"), 5: ("명장의 칭호", "팔도를 돌아 서사를 완성한다")}


def promo_narr(c, p):
    cid, nm, sig = c["id"], c["name"], c.get("signature_item") or "옛 물건"
    t = int(p["tier"])
    route = p["route"]
    pk = c.get("primary_knowledge", "sa")
    theme = PROMO_THEME.get(t, ("성장", "스스로를 증명한다"))
    lore = p.get("lore", "")
    steps = []
    for i, node in enumerate(route):
        n0 = npc(node, p["id"])
        if i < len(route) - 1:
            steps.append(scene(node, [
                line("hero", f"({act(node, sig, p['id'] + str(i))})"),
                line(n0, f"{sig}? 그 물건이라면 {name_of(route[i + 1])}에 아는 이가 있을 게요."),
                line(cid, pick([f"{sig}을(를) 쥔 손에 힘이 들어가는군. 다음은 {name_of(route[i + 1])}요.",
                                f"여기까지 온 것도 그대 덕이오. {name_of(route[i + 1])}(으)로 갑시다.",
                                f"옛일이 떠오르는구려. {name_of(route[i + 1])}에서 매듭을 지어야겠소."], p["id"], i)),
            ], cast=["hero", cid, n0]))
        else:
            steps.append(scene(node, [
                line(n0, f"{nm}의 {theme[0]} — 그 시험을 여기서 치르겠다고?"),
                line(cid, f"그렇소. {lore[:60] + ('…' if len(lore) > 60 else '') if lore else theme[1]}"),
                line("hero", f"{nm}이(가) 시험을 치르는 동안 무엇을 도울까?"),
            ], choice_set(t, pk, f"{KNAME[pk]}의 지식으로 곁에서 조언한다", "귀한 재료를 구해 건넨다", "묵묵히 지켜보며 믿는다",
                          {"know": f"{nm}: 그대의 한마디에 막힌 곳이 뚫렸소.", "pay": f"{nm}: 이 재료라면 제대로 해낼 수 있겠소.",
                           "plain": f"{nm}: 믿어 주는 이가 있으니 두렵지 않소."}, salt=p["id"]), cast=["hero", cid, n0]))
    intro = scene(route[0], [
        line(cid, f"{name_of(route[0])}에 오니 마음이 설레는구려. {theme[1]} — {lore[:80] if lore else ''}"),
        line("hero", f"{describe(route)} — 함께 가 봅시다."),
    ], cast=["hero", cid])
    outro = scene(route[-1], [
        line(cid, f"({sig}을(를) 높이 들며) {t}등급 — {theme[0]}! 이제 한층 더 쓸모 있는 동료가 되겠소."),
        line("hero", "축하하오. 앞으로도 잘 부탁하오."),
    ], cast=["hero", cid])
    return {"status": "draft", "title": p.get("name", f"{nm} {t}등급 승급"), "intro": intro, "steps": steps, "outro": outro}


def describe(route):
    return " → ".join(name_of(x) for x in route)


# ================================================================ 3) 고등급 장비·탈것
FAMILY_TONE = {"yu": ("유학자 집안에 대대로 전하는", "scholar"), "bul": ("호국 승병이 지켰다는", "monk"), "seon": ("신선이 남겼다는", "shaman"), "none": ("명장이 벼렸다는", "official")}


def gear_narr(qid, name, qname, tier, route, fam, kind):
    thing = name
    tone = FAMILY_TONE.get(fam, FAMILY_TONE["none"])[0]
    k = {"yu": "yu", "bul": "bul", "seon": "seon"}.get(fam, "gong" if kind == "gear" else "sa")
    steps = []
    for i, node in enumerate(route):
        n0 = npc(node, qid)
        if i < len(route) - 1:
            steps.append(scene(node, [
                line("hero", f"({act(node, thing, qid + str(i))})"),
                line(n0, pick([f"{thing}(이)라… 다음 실마리는 {name_of(route[i + 1])}에 있다오.", f"옛 어른들 말로는 {name_of(route[i + 1])}에 그 내력을 아는 이가 있다 했소.",
                               f"{name_of(route[i + 1])}(으)로 가 보시오. 거기서부터는 길이 험하오."], qid, i)),
                line("hero", pick([f"{thing}… 한 걸음 가까워졌군.", f"{name_of(route[i + 1])}(으)로 서두르자.", "이 단서를 잘 적어 두어야겠다."], qid, i)),
            ], cast=["hero", n0]))
        else:
            steps.append(scene(node, [
                line(n0, f"{tone} {thing}이(가) 여기 있소. 다만 주인을 가려서 따른다 하오."),
                line("hero", f"{qname} — 여기서 끝을 봐야겠군."),
            ], choice_set(tier, k, f"{KNAME[k]}의 도리를 보여 자격을 증명한다", "수호자에게 예물을 바친다", "정성껏 예를 갖춰 청한다",
                          {"know": f"{name_of(node)}의 수호자: 과연 {thing}의 주인이 될 만하오.",
                           "pay": "수호자: 정성이 갸륵하니 내어 드리리다.",
                           "plain": "수호자: 먼 길을 온 발걸음을 믿어 보겠소."}, salt=qid), cast=["hero", n0]))
    intro = scene(route[0], [
        line(npc(route[0], qid + "i"), f"{thing} 이야기를 들으셨소? {tone} 물건이라, {describe(route)} 길을 거쳐야 닿는다고 하오."),
    ], cast=["hero", npc(route[0], qid + "i")])
    outro = scene(route[-1], [line("hero", f"{thing}을(를) 손에 넣었다. 무게만큼 책임도 무겁다.")], cast=["hero"])
    return {"status": "draft", "title": qname, "intro": intro, "steps": steps, "outro": outro}


# ================================================================ 4) 특산물 레시피 비전 전수(레시피북을 기증·매각해 잃었을 때의 두 번째 길)
def recipe_quests():
    quests, narr = [], {}
    her_by_reward = {h["reward"]: h for h in HER}
    trade_reward = {q.get("reward_item") for q in SPD["trade_quests"]}
    for r in SPR:
        if r["id"] in trade_reward:      # 무역 퀘스트가 이미 두 번째 길
            continue
        her = her_by_reward.get(r["id"])
        sp = SPEC.get(r.get("produces", ""), {})
        end = sp.get("node") or (her or {}).get("node")
        if not end or end not in NODES:
            continue
        t = int(r["tier"])
        rule = OV["route_rules"][str(t)]
        route = None
        for s in range(12):
            cand = route_for(end, t, rule, h32(r["id"], s), ["town", "city", "ruin", "temple"])
            if check_route(cand, rule):
                route = cand
                break
        if not route:
            continue
        qid = "q_rcp_" + r["id"][4:]
        spname = sp.get("name") or r["name"].strip("【】").replace(" 비전서", "")
        mats = r.get("materials", [])
        q = {"id": qid, "name": f"비전 전수: {spname}", "tier": t, "type": "recipe", "min_rank": max(1, t - 1), "route": route,
             "reward": {"item": r["id"]}, "avail": {"region": region_of(end), "not_has": r["id"]}}
        if her:
            q["avail"]["heritage_resolved"] = her["id"]
        quests.append(q)
        mat_txt = "·".join(ROWS.get(m["id"], {}).get("name", m["id"]) for m in mats[:2]) or "재료"
        steps = []
        for i, node in enumerate(route):
            n0 = npc(node, qid)
            if i < len(route) - 1:
                steps.append(scene(node, [
                    line(n0, pick([f"{spname} 비법이라… 그 집안 장인은 {name_of(route[i + 1])}(으)로 옮겨 갔소.",
                                   f"{mat_txt}을(를) 제대로 고르는 눈이 먼저요. {name_of(route[i + 1])}에 가 보시오.",
                                   f"비전서가 팔려 나간 뒤로 제대로 만드는 이가 드물지. {name_of(route[i + 1])}에 한 사람 남았소."], qid, i)),
                    line("hero", f"({act(node, spname + ' 비법', qid + str(i))}) 알겠소."),
                ], cast=["hero", n0]))
            else:
                master = f"npc:merchant:{spname.split()[0]} 늙은 장인"
                extra = None
                if mats:
                    need = {m["id"]: int(m["qty"]) for m in mats[:2]}
                    extra = {"id": "mats", "text": f"〔재료 지참〕 {mat_txt}을(를) 직접 가져와 함께 만들어 본다", "req": {"items": need},
                             "effects": {"take": need, "knowledge_xp": {"gong": 30 * t}}, "result": "장인: 손이 기억하는 법이지. 이제 비법은 자네 것이네."}
                steps.append(scene(node, [
                    line(master, f"비전서를 잃었다고? 허허, 글로 배운 것은 잃어도 손으로 배운 것은 남는 법이지."),
                    line(master, f"{spname} — 불과 흙, 물때를 한 번에 맞춰야 하네. 어디 자네 솜씨를 보세."),
                ], choice_set(t, "gong", "공(工)의 요령으로 공정의 순서를 짚어 낸다", "장인의 공방 수리비를 대고 배운다", "밤새 곁에서 허드렛일을 하며 배운다",
                              {"know": "장인: 순서를 아는구먼! 나머지는 금방이네.", "pay": "장인: 공방이 되살아나니 나도 신이 나는군.",
                               "plain": "장인: 땀 흘린 만큼 배운 게야."}, extra=extra, salt=qid), cast=["hero", master]))
        narr["quest:" + qid] = {"status": "draft", "title": q["name"],
                                "intro": scene(route[0], [line(npc(route[0], qid + "i"), f"{spname} 비전서를 잃으셨다고요? {describe(route)} — 그 길 끝에 옛 장인이 산다 합니다.")]),
                                "steps": steps,
                                "outro": scene(route[-1], [line("hero", f"【{spname} 비전】을 손으로 익혔다. 공방에서 다시 만들 수 있다.")], cast=["hero"])}
    return quests, narr


# ================================================================ 5) 국보급 유산 전설 퀘스트
def legend_for(h):
    for key, v in LEGENDS:
        if key in h["name"]:
            return key, v
    return None, None


def lore_targets():
    refs = set()
    for f in ("23_tutorial.json", "20_events.json"):
        refs |= set(re.findall(r"her_[a-z0-9_]+", (DATA / f).read_text(encoding="utf-8")))
    for p in (SRC / "scenarios").glob("*.json"):
        refs |= set(re.findall(r"her_[a-z0-9_]+", p.read_text(encoding="utf-8")))
    out = []
    for h in HER:
        if h["id"] in refs:
            continue
        if h.get("designation") in ("국보", "국보급", "세계기록유산") or (not h["id"].startswith("her_n") and int(h["tier"]) == 5):
            if int(h["tier"]) >= 4:
                out.append(h)
    return out


GENERIC_LORE = {
    "architecture": ["주춧돌에 남은 옛 먹줄 자국", "기와 끝 막새에 새겨진 문양", "중수할 때마다 적어 둔 상량문"],
    "document": ["책장 사이에 끼워진 낡은 쪽지", "필사한 이의 이름이 적힌 마지막 장", "서고 자물쇠의 열쇠를 맡은 이"],
    "metal": ["쇳물을 붓던 옛 공방터", "표면에 남은 망치 자국", "시주한 이의 이름을 새긴 명문"],
    "ceramic_specialty": ["가마터에 쌓인 깨진 조각", "유약 빛깔을 기억하는 늙은 도공", "흙을 캐던 골짜기"],
    "folk_craft": ["마을 굿에서만 꺼내는 물건", "대대로 지켜 온 금기", "장인의 이름이 전하지 않는 까닭"],
    "scenic": ["산마루에 오른 옛 선비의 시", "바위에 남은 제단 흔적", "새벽에만 보인다는 풍경"],
}


def lore_quests():
    quests, narr, gate = [], {}, {}
    rules = OV.get("lore_quest_rules") or {"4": {"nodes": [3, 3], "scope": "same_region"}, "5": {"nodes": [4, 4], "scope": "same_region"}}
    fk = {"yu": ["seowon", "city", "tomb"], "bul": ["temple", "stupa"], "seon": ["shrine", "scenic"]}
    for h in lore_targets():
        t = int(h["tier"])
        rule = rules[str(t)]
        k = FACTION_K.get(h.get("faction", "")) or NT_K.get(h.get("node_type", "")) or CAT_K.get(h["category"], "sa")
        route = None
        for s in range(12):
            cand = route_for(h["id"], t, rule, h32(h["id"], s), fk.get(h.get("faction", ""), ["town", "temple", "seowon", "city"]))
            if check_route(cand, rule) and len({node_of(x) for x in cand}) == len(cand):
                route = cand
                break
        if not route:
            continue
        qid = "q_lore_" + h["id"][4:]
        key, lg = legend_for(h)
        fig = (lg or {}).get("figure", "옛사람")
        clues = list((lg or {}).get("clues", GENERIC_LORE.get(h["category"], GENERIC_LORE["architecture"])))
        legend = (lg or {}).get("legend") or f"{h['name']}에는 {CAT_KO.get(h['category'], '유산')}의 오랜 내력이 전한다. {h.get('desc', '')}".strip()
        q = {"id": qid, "name": f"【전설】 {h['name']}", "tier": t, "type": "lore", "min_rank": max(1, t - 1), "route": route,
             "rules": "lore_quest_rules", "reward": {"heritage_unlock": h["id"]}, "avail": {"region": h["region"], "heritage_unvisited": h["id"]},
             "legend": {"key": key or "", "figure": fig, "source": "설화·기록 참조 가상 각색" if lg else "가상 창작"}}
        quests.append(q)
        gate[h["id"]] = qid
        steps = []
        for i, node in enumerate(route):
            n0 = npc(node, qid)
            clue = clues[i % len(clues)] if clues else ""
            if i < len(route) - 1:
                steps.append(scene(node, [
                    line(n0, f"{h['name']}? 그 이야기를 하자면 {fig}부터 꺼내야 하오. 단서라면 — {clue}."),
                    line("hero", f"({act(node, h['name'], qid + str(i))}) {name_of(route[i + 1])}(으)로 가면 이어지겠군."),
                ], cast=["hero", n0]))
            else:
                n1 = npc(node, qid + "g")
                steps.append(scene(node, [
                    line(n1, f"여기까지 오셨구려. {legend}"),
                    line(n1, "이 유산은 아무에게나 모습을 보이지 않소. 그대의 마음가짐을 보여 주시오."),
                ], choice_set(t, k, f"{KNAME[k]}의 식견으로 전설의 뜻을 풀어 말한다", "제물과 향촉을 올려 예를 갖춘다", f"{fig}의 이야기를 조용히 되새기며 기다린다",
                              {"know": f"{n1.split(':')[-1]}: 전설의 참뜻을 아는 분이군요. 문을 열어 드리리다.",
                               "pay": "향 연기가 곧게 오르오. 들어가 보시오.",
                               "plain": "기다림도 정성이지요. 이제 보실 때가 되었소."}, salt=qid), cast=["hero", n1]))
        narr["quest:" + qid] = {"status": "draft", "title": q["name"],
                                "intro": scene(route[0], [line(npc(route[0], qid + "i"), f"{h['name']}을(를) 보려거든 먼저 그 전설을 따라가 보시오. {fig}의 이야기가 {describe(route[:-1])}에 흩어져 있소.")]),
                                "steps": steps,
                                "outro": scene(route[-1], [line("hero", f"전설의 조각이 모두 맞춰졌다. 이제 {h['name']}을(를) 답사할 수 있다.")], cast=["hero"]),
                                "legend": legend}
    return quests, narr, gate


# ================================================================ 6) 미니게임 변형 (같은 미니게임 · 유산마다 문항/단계/난이도만 다르게)
STONE = re.compile(r"비$|비\(|비석|탑비|석당|순수비|적성비|고구려비|신라비|암각|석탑|석등|마애|석불|석조|모전")
PAINT = re.compile(r"도$|도\(|화첩|병풍|벽화|사신도|어진|초상")
BELLISH = re.compile(r"종|범종|동종|불상|불좌상|여래|철불|비로자나|마애")
BANK = {
    "architecture": [("목조 건물 기둥 가운데를 불룩하게 한 기법은?", ["배흘림", "민흘림", "주심포", "다포"]),
                     ("지붕 무게를 받치려 기둥 위에 짜 올린 부재는?", ["공포", "서까래", "주춧돌", "대들보"]),
                     ("탑의 꼭대기 장식 부분을 무엇이라 하나?", ["상륜부", "기단부", "탑신부", "옥개석"]),
                     ("성문 밖에 반원형으로 한 겹 더 두른 성벽은?", ["옹성", "여장", "치성", "해자"])],
    "document": [("나무판에 글자를 새겨 찍는 방식은?", ["목판 인쇄", "금속활자", "필사", "탁본"]),
                 ("실록을 볕에 말려 좀을 막는 일은?", ["포쇄", "봉안", "인출", "장황"]),
                 ("훈민정음 기본 모음 세 가지의 바탕은?", ["하늘·땅·사람", "해·달·별", "산·물·불", "동·서·남"])],
    "metal": [("청동 표면을 파고 은실을 박아 넣는 기법은?", ["은입사", "상감", "투각", "도금"]),
              ("신라 금관의 가지 장식 모양은?", ["出자형", "용 모양", "구름 모양", "연꽃 모양"]),
              ("범종 위에 달린 소리 대롱은?", ["음통", "용뉴", "당좌", "유곽"])],
    "ceramic_specialty": [("고려청자의 푸른빛을 부르는 말은?", ["비색", "순백", "흑유", "분청"]),
                          ("흙을 파낸 자리에 다른 흙을 메워 무늬 내는 기법은?", ["상감", "철화", "진사", "음각"]),
                          ("조선 초 회청색 흙에 백토를 바른 그릇은?", ["분청사기", "청자", "백자", "옹기"])],
    "folk_craft": [("하회 별신굿 탈 가운데 턱이 없는 탈은?", ["이매탈", "양반탈", "선비탈", "각시탈"]),
                   ("마을 입구를 지키는 나무 기둥 수호신은?", ["장승", "솟대", "당산", "서낭"]),
                   ("무속에서 신을 부를 때 흔드는 도구는?", ["방울", "징", "북", "피리"])],
}


def seeded_points(seed, n):
    rng = random.Random(seed)
    pts = []
    while len(pts) < n:
        p = [round(rng.uniform(0.12, 0.88), 2), round(rng.uniform(0.12, 0.88), 2)]
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 > 0.03 for q in pts):
            pts.append(p)
    return pts


def good_desc(h):
    d = h.get("desc", "")
    return d if d and "대동여지도 제" not in d and "유서 깊은 국가유산" not in d and len(d) > 8 else ""


def quiz_bank(h, seed):
    rng = random.Random(seed)
    qs = []

    def q(text, right, wrong):
        wrong = [w for w in dict.fromkeys(wrong) if w != right][:3]
        if len(wrong) < 3:
            return
        opts = [right] + wrong
        rng.shuffle(opts)
        qs.append({"q": text, "options": opts, "answer": opts.index(right)})
    regs = [r["name"] for r in REG["regions"]]
    q(f"{h['name']}이(가) 있는 권역은?", REGIONS[h["region"]]["name"], rng.sample([x for x in regs if x != REGIONS[h["region"]]["name"]], 3))
    same = [n["name"] for n in REG["nodes"] if n["region"] == h["region"] and n["id"] != h["node"] and not n.get("hidden")]
    if len(same) >= 3:
        q(f"{h['name']}을(를) 답사하려면 어느 곳으로 가야 하나?", NODES[h["node"]]["name"], rng.sample(same, 3))
    q(f"{h['name']}의 갈래는?", CAT_KO[h["category"]], [v for k, v in CAT_KO.items() if k != h["category"]])
    if h.get("designation") in ("국보", "보물", "사적", "명승", "세계기록유산", "국보급"):
        q(f"{h['name']}에 매겨진 등급(지정 구분)은?", h["designation"], ["사적", "보물", "명승", "민속자료", "국보"])
    if h.get("faction") in FACTION_K:
        fn = {"yu": "유교", "bul": "불교", "seon": "선도"}
        q(f"{h['name']}과(와) 가장 가까운 사상 계열은?", fn[h["faction"]], [v for k, v in fn.items() if k != h["faction"]] + ["무속"])
    d = good_desc(h)
    if d:
        others = [good_desc(x) for x in HER if x["id"] != h["id"] and x["category"] == h["category"] and good_desc(x)]
        if len(others) >= 3:
            q(f"{h['name']}에 대한 설명으로 옳은 것은?", d, rng.sample(others, 3))
    key, lg = legend_for(h)
    if lg:
        figs = [v["figure"] for k, v in LEGENDS if v["figure"] != lg["figure"]]
        q(f"{h['name']}의 전설과 얽힌 인물은?", lg["figure"], rng.sample(figs, 3))
    base = BANK.get(h["category"], BANK["architecture"])
    for text, opts in rng.sample(base, min(2, len(base))):
        q(text, opts[0], opts[1:])
    return qs


def mg_for(h):
    """카테고리·노드 유형·이름 → 미니게임 id (유산에 minigame 지정이 있으면 런타임이 그것을 먼저 씀)"""
    nt, cat, nm = h.get("node_type", ""), h["category"], h["name"]
    if cat == "scenic" or nt == "scenic" and cat == "scenic":
        return ""
    if nt == "wreck":
        return "mg_salvage"
    if nt == "tomb":
        return "mg_jesa_table"
    if cat == "ceramic_specialty":
        return "mg_pottery_shard"
    if STONE.search(nm):
        return "mg_takbon"
    if PAINT.search(nm):
        return "mg_hanji_sliding"
    if cat == "metal":
        return "mg_bell" if BELLISH.search(nm) or nt in ("temple", "stupa") else "mg_forge"
    if cat == "folk_craft":
        return "mg_bell" if BELLISH.search(nm) else "mg_talisman_stroke"
    if cat == "document":
        return "mg_heritage_quiz"
    if nt in ("stupa",) and BELLISH.search(nm):
        return "mg_bell"
    return MG_DEFAULT.get(nt, "mg_heritage_quiz")


def variant_params(mg, h):
    t = int(h["tier"])
    s = h32(h["id"], "mg")
    impl = (MG.get(mg) or HQ).get("impl")
    base = (MG.get(mg) or HQ).get("params", {})
    if impl == "sliding":
        return {"size": 3 if t <= 2 else (4 if t <= 4 else 5), "image": f"res://assets/minigames/heritage/{h['id']}.png", "image_fallback": base.get("image", "")}
    if impl == "timing":
        return {"zone": round(float(base.get("zone", 0.14)) * (1 - 0.08 * (t - 1)), 3), "speed": round(float(base.get("speed", 1.0)) * (1 + 0.1 * (t - 1)), 2),
                "hits": int(base.get("hits", 3)) + (1 if t >= 4 else 0), "attempts": int(base.get("attempts", 5)) + (1 if t >= 4 else 0), "seed": s}
    if impl == "rubbing":
        return {"coverage": round(min(0.95, 0.72 + 0.04 * t), 2), "brush": max(28, 46 - 3 * t), "sheet": 20 + s % 80}
    if impl == "trace":
        return {"points": seeded_points(s, 4 + t), "ordered": True, "radius": max(26, 38 - 2 * t)}
    if impl == "gauge":
        b = base.get("band", [45, 60])
        w = max(8, (b[1] - b[0]) - 2 * (t - 1))
        c = (b[0] + b[1]) / 2
        return {"band": [round(c - w / 2), round(c + w / 2)], "drift": int(base.get("drift", 15)) + 2 * t, "hold_ratio": round(min(0.8, 0.55 + 0.04 * t), 2)}
    if impl == "rhythm":
        return {"seed": s, "gap_min": round(0.5 - 0.04 * t, 2), "gap_max": round(0.8 - 0.05 * t, 2)}
    if impl == "quiz":
        bank = quiz_bank(h, s)
        if mg == "mg_jesa_table":
            bank = bank[:3] + list(base.get("bank", []))
        return {"bank": bank, "need": 2 if t <= 2 else (3 if t <= 4 else 4), "note": f"— {h['name']} 문답"}
    return {}


HQ = {"id": "mg_heritage_quiz", "name": "유산 문답(답사 고증)", "impl": "quiz", "category": 4, "knowledge": "sa", "time": 40,
      "params": {"need": 3, "bank": [{"q": "국가유산을 답사할 때 먼저 할 일은?", "options": ["내력과 기록을 살핀다", "기와를 떼어 간다", "탑에 오른다", "불을 피운다"], "answer": 0}]},
      "used_by": "유산별 문답 변형(24_story mg_variants)", "desc": "유산 데이터(권역·지정·설명·전설)에서 자동 출제"}


def mg_variants(lore_ids):
    policy = {"min_tier_visible": 3, "note": "은닉 유산·기본 미니게임 노드 유형은 항상, 공개 유산은 min_tier_visible 등급 이상이거나 전설 퀘스트 대상일 때 변형 미니게임을 요구"}
    out = {}
    for h in HER:
        need = h.get("hidden") or h.get("node_type") in MG_DEFAULT or int(h["tier"]) >= policy["min_tier_visible"] or h["id"] in lore_ids
        if not need:
            continue
        mg = h.get("minigame") or mg_for(h)
        if not mg:
            continue
        out[h["id"]] = {"minigame": mg, "params": variant_params(mg, h)}
    return policy, fix_all(out)


# ================================================================ 병합·저장
def deep_merge(base, over):
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = deep_merge(base.get(k), v) if k in base else v
        return out
    if isinstance(base, list) and isinstance(over, dict) and all(re.fullmatch(r"\d+", str(k)) for k in over):
        out = list(base)
        for k, v in over.items():
            i = int(k)
            if i < len(out):
                out[i] = deep_merge(out[i], v)
            else:
                out.append(v)
        return out
    return over


def load_edits():
    """edits/*.json 을 파일 이름 순서로 합친다. 형식: {"narratives": {key: 부분}, "quests": {id: 부분}, "mg_variants": {her: 부분}, "lore_gate": {...}}"""
    acc = {}
    if not EDITS.exists():
        return acc, []
    files = sorted(EDITS.glob("*.json"))
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            sys.exit(f"[gen_story] 편집 파일 JSON 오류: {p.name}: {e}")
        acc = deep_merge(acc, {k: v for k, v in d.items() if not k.startswith("_")})
    return acc, [p.name for p in files]


def main():
    DRAFTS.mkdir(parents=True, exist_ok=True)
    EDITS.mkdir(parents=True, exist_ok=True)
    ov = OV
    ov["economy"]["quest_type_mult"].setdefault("recipe", {"rep": 0.3, "money": 0.0})
    ov["economy"]["quest_type_mult"].setdefault("lore", {"rep": 0.0, "money": 0.0})
    ov.setdefault("lore_quest_rules", {"_note": "국보급 전설 퀘스트 동선: 같은 권역, 마지막 노드 = 유산", "4": {"nodes": [3, 3], "scope": "same_region"},
                                       "5": {"nodes": [4, 4], "scope": "same_region"}})
    save("00_overview.json", ov)

    narr = {"recruit": {}, "promotion": {}, "gear": {}, "recipe": {}, "lore": {}}
    for c in COMP:
        if c.get("recruit", {}).get("route"):
            narr["recruit"]["quest:q_" + c["id"]] = recruit_narr(c)
        for p in c.get("promotion", []):
            narr["promotion"]["quest:" + p["id"]] = promo_narr(c, p)
    for it in EQ:
        a = it.get("acquire", {})
        if a.get("type") == "quest":
            fam = next((f for f in ("yu", "bul", "seon") if it["id"].startswith(f"eq_{f}_")), it.get("family", "none"))
            narr["gear"]["quest:q_" + it["id"]] = gear_narr("q_" + it["id"], it["name"], a.get("quest_name", it["name"]), int(it["tier"]), a["route"], fam, "gear")
    for m in MTS:
        a = m.get("acquire", {})
        if a.get("type") == "quest":
            narr["gear"]["quest:q_" + m["id"]] = gear_narr("q_" + m["id"], m["name"], a["quest_name"], int(m["tier"]), a["route"], "none", "mount")
    rq, rn = recipe_quests()
    lq, ln, gate = lore_quests()
    narr["recipe"], narr["lore"] = rn, ln
    narr = fix_all(narr)
    rq, lq = fix_all(rq), fix_all(lq)
    policy, mgv = mg_variants(set(gate))

    drafts = {"quests": {q["id"]: q for q in rq + lq}, "narratives": {k: v for d in narr.values() for k, v in d.items()},
              "lore_gate": gate, "mg_variants": mgv}
    for kind, d in narr.items():
        (DRAFTS / f"narr_{kind}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (DRAFTS / "quests.json").write_text(json.dumps(drafts["quests"], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (DRAFTS / "mg_variants.json").write_text(json.dumps(mgv, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    edits, files = load_edits()
    merged = deep_merge(drafts, edits)
    edited = {k: sorted(v.keys()) for k, v in edits.items() if isinstance(v, dict)}
    for k in edited.get("narratives", []):
        if k in merged["narratives"] and merged["narratives"][k].get("status") == "draft":
            merged["narratives"][k]["status"] = "edited"
    out = {
        "_schema": "24_대화·서사. quests=새 퀘스트(recipe 비전 전수·lore 전설), narratives['quest:<id>']={status,title,intro,steps[동선 노드별],outro}, "
                   "장면={bg,cast,lines[{who,text}],choices[{id,text,req,effects,result}]}, who=hero|동료 id|npc:<역할>:<이름>, "
                   "req 키=rank·money·items·knowledge·party·class·flag·visited, effects 키=knowledge_xp·money·money_mult·give·take·flag·reputation. "
                   "초안은 tools/gen_story.py 가 생성, 수정은 data_src/story/edits/*.json(깊은 병합)",
        "edit_files": files,
        "quests": list(merged["quests"].values()),
        "narratives": merged["narratives"],
        "lore_gate": merged["lore_gate"],
        "mg_policy": policy,
        "mg_variants": merged["mg_variants"],
        "minigames": [HQ],
    }
    save("24_story.json", out)
    cnt = {k: len(v) for k, v in narr.items()}
    print(f"[gen_story] 서사 {sum(cnt.values())}건 {cnt} · 새 퀘스트 레시피 {len(rq)} · 전설 {len(lq)} · 미니게임 변형 {len(mgv)} · 편집 파일 {len(files)}개")


if __name__ == "__main__":
    main()
