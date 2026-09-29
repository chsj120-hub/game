"""동료 시작 등급 산정 + 서사 맞춤 승급 퀘스트 자동 설계 (audit_fix.py · merge_companions.py 공용).

규칙
- 시작 등급 1~3: 점수 = 능력(DB-15 원래 등급) + 분류 가중 + 유명도 가중 → 점수순으로 3등분(골고루).
- 승급 퀘스트 t(=시작+1 … 5): 트리거 = 주인공 신분 Rank ≥ t · 해당 동료 동행 · 대표 지식 ≥ t · 시작 장소(영입지) 방문.
  동선은 00_overview.route_rules(1~2등급 동일 권역 2노드 / 3~4등급 인접 2~3권역 3노드 / 5등급 전국 3~5권역 4~5노드)를 따른다.
- 승급 효과: 스킬 숙련 배율 +per_tier(00.battle.party_merge.companion_skill_mult), 대표 지식 +1 → 지식 합 = 현재 등급.
"""
import hashlib
import json
import re

import game_ref as G

CAT_W = [(r"역사", 2.0), (r"신화|설화", 1.5), (r"소설/도사", 1.2), (r"소설", 1.0), (r"직업", 0.0)]
FAME = {  # 대중적 인지도 가중(능력과 별개)
    1.5: "이순신 정약용 허준 김정호 김홍도 신사임당 을지문덕 연개소문 원효대사 사명대사 서산대사(휴정) 정도전 장영실 홍길동 성춘향 심청 흥부 "
         "황진이 김정희 계백 권율 문익점 바리공주 전우치 신윤복",
    0.5: "박지원 채제공 신숙주 이천 남이 안견 의상대사 보조국사 지눌 이제마 처용(處容) 강림도령 이몽룡 허생 박씨부인 남사고",
}
FAME_OF = {n: w for w, s in FAME.items() for n in s.split()}
LIFE = {"sa": "사(관찰)", "nong": "농(의학·농업)", "gong": "공(제작·예술)", "sang": "상(상업)", "yu": "유교", "bul": "불교", "seon": "선도"}


def _h(*parts):
    return int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def score(name, orig_tier, category):
    cw = next((w for p, w in CAT_W if re.search(p, str(category))), 0.5)
    return float(orig_tier) + cw + FAME_OF.get(name, FAME_OF.get(name.split("(")[0], 0.0))


def start_tiers(entries):
    """entries = [(key, score)] → {key: 1|2|3}. 점수순 3등분(나머지는 중간 등급에)."""
    order = sorted(entries, key=lambda x: (-x[1], x[0]))
    n = len(order)
    top = n // 3
    bottom = n // 3
    out = {}
    for i, (k, _) in enumerate(order):
        out[k] = 3 if i < top else (1 if i >= n - bottom else 2)
    return out


def allocate_knowledge(total, faction, hits):
    """지식 합 = total. 세력 지식 1 + 탐험 성향(hits) 순환. 대표 지식 = 가장 큰 값(동률이면 첫 성향)."""
    kn = {}
    if faction != "none":
        kn[faction] = 1
    hits = hits or ["sa"]
    i = 0
    while sum(kn.values()) < total:
        k = hits[i % len(hits)]
        kn[k] = kn.get(k, 0) + 1
        i += 1
    primary = max(kn, key=lambda k: (kn[k], k in hits))
    return kn, primary


# ---------------------------------------------------------------- 서사 테마(노드 유형·행동 문구)
THEME_TYPES = {
    "yu": ["seowon", "city", "fort", "tomb"], "bul": ["temple", "stupa", "scenic"], "seon": ["shrine", "scenic", "tomb", "spring"],
    "none": ["town", "station", "city", "spring"], "military": ["fort", "beacon", "city"], "sea": ["wreck", "town", "fort"],
    "healer": ["city", "spring", "temple"], "art": ["scenic", "seowon", "ruin"], "craft": ["ruin", "town", "city"],
}
ACTION = {"seowon": "강학에 참석해 뜻을 가다듬는다", "city": "관아와 장터에서 옛 인연을 수소문한다", "fort": "진법을 익히며 옛 전장을 되짚는다",
          "tomb": "능역을 참배하고 비문을 탁본한다", "temple": "주지와 법담을 나누며 수행한다", "stupa": "탑돌이를 하며 발원한다",
          "scenic": "절경 앞에서 마음을 비우고 수련한다", "shrine": "제를 올려 신령의 뜻을 묻는다", "spring": "온천에서 몸과 기운을 다스린다",
          "town": "마을 사람들의 일을 거들며 솜씨를 보인다", "station": "역참에서 팔도 소식을 모은다", "wreck": "가라앉은 배를 조사한다",
          "ruin": "옛터를 발굴해 잊힌 기술을 되살린다", "beacon": "봉수를 올려 먼 곳과 신호를 주고받는다", "hazard": "험한 고개의 위험을 무릅쓴다"}
TITLES = {
    "역사": {2: "행장(行狀)의 첫 장", 3: "{p1}에 남은 자취", 4: "「{skill}」 재현", 5: "{fin}에 새긴 이름"},
    "소설": {2: "이야기의 첫 대목", 3: "{p1}에서 만난 운명", 4: "위기와 반전", 5: "대단원 — {fin}"},
    "신화": {2: "신이(神異)의 징조", 3: "{p1} 제의(祭儀)", 4: "하늘의 시험", 5: "{fin}에서의 현현"},
    "직업": {2: "손에 익은 연장", 3: "{p1} 장인의 비법", 4: "팔도 명인 겨루기", 5: "명장(名匠)의 칭호 — {fin}"},
}
LORE = {
    2: "{name_eun} {home}에서 {item_eul} 다시 꺼내 든다. 동행하며 쌓은 신뢰가 첫 시험으로 이어진다.",
    3: "{name}의 사연이 {p1_ro} 이어진다. {item}에 얽힌 옛 인연을 찾아 이웃 고을까지 발걸음을 옮긴다.",
    4: "이름이 알려진 {name}에게 「{skill}」{skill_eul} 온전히 펼칠 시험이 찾아온다. {p1}·{p2_eul} 거치며 스스로를 증명해야 한다.",
    5: "팔도를 두루 거쳐 {fin}에 이르러야 {name}의 서사가 완성된다. {desc}",
}


COASTAL = set(json.loads((G.ROOT / "data_src" / "world_table.json").read_text(encoding="utf-8"))["coastal"])
THEME_ACTION = {
    ("sea", "town"): "포구에서 배를 손보며 물길과 물때를 묻는다", ("sea", "city"): "수영(水營)과 포구를 살피며 뱃사람들을 모은다",
    ("sea", "fort"): "진(鎭)의 수군과 함께 해상 진법을 익힌다", ("sea", "wreck"): "가라앉은 배를 조사해 옛 해전의 흔적을 찾는다",
    ("craft", "town"): "장터 공방에서 솜씨를 겨루며 연장을 벼린다", ("craft", "city"): "관아 공방의 까다로운 주문을 받아 낸다",
    ("craft", "ruin"): "옛 가마·공방터를 발굴해 잊힌 기법을 되살린다", ("craft", "fort"): "무너진 성벽과 병기를 손보며 솜씨를 보탠다",
    ("healer", "city"): "약방·혜민서에서 병자를 돌본다", ("healer", "spring"): "온천에서 병든 이들을 요양시킨다",
    ("healer", "temple"): "절 약사전에서 약초를 달이며 수행한다", ("art", "scenic"): "절경을 화폭과 시문에 담는다",
    ("art", "seowon"): "서원 선비들과 시서화를 겨룬다", ("art", "ruin"): "옛터의 자취를 그림으로 남긴다",
    ("military", "fort"): "진법을 익히며 옛 전장을 되짚는다", ("military", "beacon"): "봉수를 올려 방어선을 점검한다",
    ("military", "city"): "병영의 군사를 조련한다",
}


def josa(word, pair):
    """받침 유무로 조사 선택: pair = '은는'|'이가'|'을를'|'과와'|'으로로'."""
    w = re.sub(r"[\(\)（）《》\[\]\s]+$", "", str(word)) or str(word)
    ch = w[-1]
    code = ord(ch) - 0xAC00
    if not 0 <= code < 11172:
        return word + pair[: len(pair) // 2]
    jong = code % 28
    if pair == "으로로":
        return word + ("로" if jong in (0, 8) else "으로")
    a, b = pair[0], pair[1]
    return word + (a if jong else b)


FINALE = {  # 서사의 정점이 되는 실제 무대(게임 노드 이름). 없으면 테마 유산 노드 자동 선택
    "이순신": "명량 울돌목", "정약용": "수원화성", "김정호": "백두산 천지", "장영실": "한양 경조", "허준": "한양 경조", "정도전": "한양 경조",
    "사명대사": "해인사", "서산대사(휴정)": "묘향산 보현사", "원효대사": "경주 석굴암", "의상대사": "부석사", "보조국사 지눌": "송광사",
    "을지문덕": "안주목", "연개소문": "평양부", "계백": "부여", "권율": "남한산성", "김정희": "추사 유배지", "김홍도": "금강산 구룡폭",
    "신사임당": "강릉 오죽헌", "문익점": "진주목", "홍길동": "장성 백양사", "바리공주": "진도 씻김굿 당골판", "강림도령": "제주 칠머리당",
    "전우치": "개성 만월대 옛터", "황진이": "개성부", "성춘향": "남원도호부", "이몽룡": "남원도호부", "심청": "장산곶 진보",
    "흥부": "남원도호부", "박지원": "의주 통군정", "이천": "한양 경조", "신숙주": "동래현", "처용(處容)": "경주 대릉원",
    "착호갑사": "백두산 천지", "산포수": "개마고원 삼수갑산", "심마니": "백두산 천지", "뱃사공": "명량 울돌목", "뗏목사공": "영월 장릉",
}


def _cat(category):
    c = str(category)
    return "역사" if "역사" in c else ("신화" if re.search(r"신화|설화", c) else ("소설" if "소설" in c else "직업"))


def _themes(fam, role_text, desc, name=""):
    t = f"{name} {role_text} {desc}"
    keys = []
    if re.search(r"장인|제작|단조|대장|옹기|한지|옻칠|석공|석수|광부|짚신|채석|벼림|공방", t):
        keys.append("craft")
    if re.search(r"수군|해전|뱃|사공|항해|수로|바다|나루|뗏목|좌수영|학익진|왜구", t):
        keys.append("sea")
    if re.search(r"힐러|의원|의학|치유|약초|탕약|심마니|동의보감|사상", t):
        keys.append("healer")
    if re.search(r"화가|그림|화첩|시조|예술|풍속|붓|글씨|필체|거문고|비파", t):
        keys.append("art")
    if "craft" not in keys and re.search(r"장군|무장|무관|전술|지휘|진형|대원수|결사|농성|살수|군사|착호|포수", t):
        keys.append("military")
    keys.append(fam)
    out = []
    for k in keys:
        for ty in THEME_TYPES[k]:
            if ty not in out:
                out.append(ty)
    return out, keys


def _pick(region, types, exclude, key, prefer_heritage=False, coastal=False):
    pool = [n for n in G.NODES if n["region"] == region and n["id"] not in exclude]
    for ty in types:
        c = [n for n in pool if n["type"] == ty]
        if coastal and ty in ("town", "city", "fort"):
            c = [n for n in c if n["name"] in COASTAL or "ferry" in n["facilities"]]
        if prefer_heritage:
            c = [n for n in c if n.get("heritage")] or c
        if c:
            return sorted(c, key=lambda n: _h(key, n["id"]))[0]
    return sorted(pool, key=lambda n: _h(key, n["id"]))[0] if pool else None


def _adj(region):
    return G.adjacent(region)


def recruit_route(cid, home, tier):
    """영입 동선(시작 등급 규칙) — 마지막 노드 = 영입지."""
    R = home["region"]
    if tier <= 2:
        other = _pick(R, ["city", "town", "station"], {home["id"]}, cid + "r")
        return [other["id"], home["id"]]
    A = sorted(_adj(R), key=lambda r: _h(cid, r))[0]
    a = _pick(A, ["city", "station", "town"], set(), cid + "ra")
    hub = G.REGIONS[R]["hub"]
    mid = hub if hub != home["id"] else _pick(R, ["station", "town"], {home["id"]}, cid + "rm")["id"]
    return [a["id"], mid, home["id"]]


def promotions(c):
    """c = {id, name, start_tier, family, category, role_text, desc, item, skill, home(node), primary}"""
    out = []
    types, keys = _themes(c["family"], c["role_text"], c["desc"], c["name"])
    sea = "sea" in keys
    if sea:  # 바다 서사: 해안 권역 우선
        coast_regs = {n["region"] for n in G.NODES if n["name"] in COASTAL}
    home = c["home"]
    R = home["region"]
    cat = _cat(c["category"])
    for t in range(c["start_tier"] + 1, 6):
        key = f"{c['id']}:{t}"
        used = {home["id"]}
        if t <= 2:
            n1 = _pick(R, types, used, key, coastal=sea)
            route = [home["id"], n1["id"]]
        elif t <= 4:
            adjs = sorted(_adj(R), key=lambda r: (sea and r not in coast_regs, _h(key, r)))
            A = adjs[0]
            n1 = _pick(A, types, used, key + "a", coastal=sea)
            used.add(n1["id"])
            third_region = R if t == 3 else (adjs[1] if len(adjs) > 1 else R)
            n2 = _pick(third_region, types[1:] + types[:1], used, key + "b", coastal=sea)
            route = [home["id"], n1["id"], n2["id"]]
        else:
            A = sorted(_adj(R), key=lambda r: (sea and r not in coast_regs, _h(key, r)))[0]
            n1 = _pick(A, types, used, key + "a", coastal=sea)
            used.add(n1["id"])
            B = sorted([r for r in _adj(A) if r not in (R, A)] or [r for r in G.MAP_IDS if r not in (R, A)],
                       key=lambda r: (sea and r not in coast_regs, _h(key, r)))[0]
            n2 = _pick(B, types, used, key + "b", coastal=sea)
            used.add(n2["id"])
            regs = [r for r in G.MAP_IDS if r not in (R, A, B)]
            fin_pool = [n for n in G.NODES if n["region"] in regs and n.get("heritage") and n["type"] in types]
            fin_pool = sorted(fin_pool, key=lambda n: (-next((h["tier"] for h in G.HERITAGE if h["id"] == n["heritage"]), 0), _h(key, n["id"])))
            fin = fin_pool[0] if fin_pool else _pick(sorted(regs, key=lambda r: _h(key, r))[0], types, used, key + "f")
            sig = next((n for n in G.NODES if n["name"] == FINALE.get(c["name"])), None)
            if sig and sig["id"] not in used:
                fin = sig
            route = [home["id"], n1["id"], n2["id"], fin["id"]]
        nodes = [next(n for n in G.NODES if n["id"] == x) for x in route]
        fmt = dict(name=c["name"], home=home["name"], item=c["item"] or "손때 묻은 물건", skill=c["skill"] or "비기", desc=c["desc"][:60],
                   p1=nodes[1]["name"], p2=nodes[2]["name"] if len(nodes) > 2 else nodes[1]["name"], fin=nodes[-1]["name"])
        fmt.update(name_eun=josa(fmt["name"], "은는"), item_eul=josa(fmt["item"], "을를"), p1_ro=josa(fmt["p1"], "으로로"),
                   skill_eul=josa(fmt["skill"], "을를")[len(fmt["skill"]):], p2_eul=josa(fmt["p2"], "을를"))
        desc = re.split(r"(?<=[.다])\s", c["desc"].strip())[0] if c["desc"] else ""
        fmt["desc"] = desc
        title = TITLES[cat][t].format(**fmt)
        def act(n):
            for k in keys:
                if (k, n["type"]) in THEME_ACTION:
                    return THEME_ACTION[(k, n["type"])]
            return ACTION.get(n["type"], "뜻을 다진다")
        steps = [f"{i + 1}) {n['name']}: {act(n)}" for i, n in enumerate(nodes)]
        rep, money = G.quest_reward(t, "companion_promo") if "companion_promo" in G.ECO["quest_type_mult"] else G.quest_reward(t, "companion")
        out.append({"id": f"promo_{c['id']}_{t}", "companion": c["id"], "tier": t, "name": f"[{c['name']}] {t}등급 승급 — {title}",
                    "lore": LORE[t].format(**fmt), "min_rank": t, "trigger_node": home["id"],
                    "requires": {"in_party": True, "knowledge": {c["primary"]: t}}, "route": route, "steps": steps,
                    "reward": {"companion_tier": {"id": c["id"], "tier": t}}, "reward_rep": rep, "reward_money": money,
                    "effect": f"스킬 숙련 +{int(G.BATTLE['party_merge']['companion_skill_mult']['per_tier_from_3'] * 100)}% · {LIFE.get(c['primary'], c['primary'])} 지식 +1"})
    return out
