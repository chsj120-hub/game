#!/usr/bin/env python3
"""DB-15 데이터셋 점검·수정기.

입력 : data_src/db15/DB15_원본.xlsx (첨부 원본, 15탭)
출력 : data_src/db15/DB15_수정본.xlsx   — 원본 15탭(수정 셀 노랑, 추가 열 초록) + 점검결과·노드참조·보충항목 탭
       data_src/db15/db15_game.json     — 게임 스키마(data/*.json)로 변환한 결과(병합 전 검토용)
       data_src/db15/issues.json        — 점검 항목 전체
기준 : data/*.json 의 공식·튜닝값(game_ref.py). 수치를 새로 만들지 않고 게임 공식/이미 검증된 값으로 맞춘다.
사용 : python3 tools/db15/audit_fix.py
"""
import json
import re
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import game_ref as G  # noqa: E402
import skillconv as SC  # noqa: E402
import xlsx_io  # noqa: E402
import companions as CP  # noqa: E402

DB = G.ROOT / "data_src" / "db15"
SRC = DB / "DB15_원본.xlsx"
RAW = xlsx_io.read(SRC)
TUNING = json.loads((DB / "tuning.json").read_text(encoding="utf-8")) if (DB / "tuning.json").exists() else {}
ISSUES = []
PARENT = {}      # 게임에 없는 장소 → 상위 노드
PROMO_ROWS = []  # 승급 퀘스트 전체
EXTRA_COMP = {}  # 게임 전용 동료의 산정값
FAC = {"유(儒)": "yu", "불(佛)": "bul", "선(仙)": "seon", "무(無)": "none"}
FAC_KO = {v: k for k, v in FAC.items()}
KIND_CAP = {"human": "유", "ghost": "불", "yokai": "선", "dragon": "선", "beast": "무"}
MAP_RE = re.compile(r"MAP_\d{2}")


def issue(tab, rid, field, cat, before, after, reason):
    ISSUES.append({"탭": tab, "ID": rid, "항목": field, "분류": cat, "원본": before, "수정": after, "사유": reason})


class Tab:
    def __init__(self, name):
        self.name = name
        rows = RAW[name]
        self.header = list(rows[0])
        self.n_orig = len(self.header)
        self.rows = [list(r) for r in rows[1:]]
        self.changed = set()

    def ci(self, col):
        return self.header.index(col)

    def g(self, r, col):
        return r[self.ci(col)] if col in self.header else ""

    def rid(self, r):
        return r[0] if self.header[0].endswith("id") else r[self.ci("item_id")] if "item_id" in self.header else r[1]

    def s(self, r, col, val, cat, reason, log=True):
        """셀 수정 + 변경 기록. 추가 열은 기록하지 않는다(보충 값이므로)."""
        if col not in self.header:
            self.add(col)
        i = self.ci(col)
        old = r[i]
        if str(old) == str(val):
            return
        r[i] = val
        if i < self.n_orig:
            self.changed.add((self.rows.index(r) + 1, i))
            if log:
                issue(self.name, self.rid(r), col, cat, old, val, reason)

    def add(self, col):
        if col not in self.header:
            self.header.append(col)
            for r in self.rows:
                r.append("")

    def fill(self, r, col, val):
        self.add(col)
        r[self.ci(col)] = val

    def out(self):
        return [self.header] + self.rows


def num(v, default=0):
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return default


def r5(v, step=5):
    """가격 반올림: 100 미만은 1냥, 1000 미만은 5냥, 이상은 10냥 단위."""
    if v < 100:
        return max(1, int(round(v)))
    if v < 1000:
        return int(round(v / step) * step)
    return int(round(v / 10) * 10)


def sell_of(buy):
    return max(1, int(round(buy * G.SELL_SPREAD)))


REGION_KW = {"MAP_01": "경기 북부|개성|강화|파주|연천|고양|가평|송도|임진", "MAP_02": "경기 남부|한양|수원|광주|여주|이천|용인|안산|마포|남양|화성",
             "MAP_03": "강원 북부|철원|춘천|인제|금강산|화천|양구|회양|설악|방태산", "MAP_04": "강원 남부|원주|강릉|삼척|평창|정선|영월|오대산|태백|울진|치악",
             "MAP_05": "충청 북부|충북|충주|청주|단양|보은|속리산|제천|소백산|달천|문경새재|조령",
             "MAP_06": "충청 남부|충남|공주|부여|서산|논산|천안|계룡|내포|홍주|아산|금산",
             "MAP_07": "전라 북부|전북|전주|남원|김제|익산|정읍|고창|부안|무주|만경|모악|호남평야|갈재|노령",
             "MAP_08": "전라 남부|전남|나주|순천|해남|강진|여수|진도|구례|지리산|영산강|광주목|장성|완도|법성포",
             "MAP_09": "경상 북부|경북|상주|안동|경주|영주|문경|청송|영양|의성|금오산",
             "MAP_10": "경상 남부|경남|대구|진주|동래|부산|통영|김해|밀양|합천|가야산|산청|울산|거제|진해|청도",
             "MAP_11": "황해 북부|황주|봉산|서흥|평산|곡산|수안|정방산|사리원|재령",
             "MAP_12": "황해 남부|해주|연안|옹진|장연|송화|배천|구월산|장산곶|수양산|인당수",
             "MAP_13": "평안 남부|평양|안주|진남포|대동강|강서|숙천|묘향산|청천강|성천",
             "MAP_14": "평안 북부|평북|의주|영변|강계|압록|정주|선천|삭주|철산",
             "MAP_15": "함경 남부|함흥|북청|영흥|낭림|개마|안변|원산|덕원",
             "MAP_16": "함경 북부|경성|회령|길주|백두산|두만강|육진|종성|온성|경원|칠보산",
             "MAP_17": "제주|탐라|한라산|서귀포|대정|백록담"}


def regions_in(text):
    t = str(text)
    ids = set(MAP_RE.findall(t))
    if re.search(r"전국|팔도", t):
        return ["*"]
    for mid, kw in REGION_KW.items():
        if re.search(kw, t):
            ids.add(mid)
    if "삼남" in t:
        ids |= {"MAP_05", "MAP_06", "MAP_07", "MAP_08", "MAP_09", "MAP_10"}
    if "영남" in t:
        ids |= {"MAP_09", "MAP_10"}
    if "기호" in t:
        ids |= {"MAP_01", "MAP_02", "MAP_05", "MAP_06"}
    if "호남" in t:
        ids |= {"MAP_07", "MAP_08"}
    return sorted(ids)


# ---------------------------------------------------------------- 노드 참조(지도 좌표) 점검
NODE_REFS = []  # 모든 위치 서술 → 게임 노드 해석 결과
MANUAL_NODE = {  # 서술 → (게임 노드 이름, 사유)  : 자동 일치가 안 되거나 권역이 어긋난 것
    "개성 고려궁지 외규장각": ("강화유수부", "외규장각은 강화에 있었다(개성 아님)"),
    "서산 인당수 앞바다 벼랑": ("장산곶 진보", "인당수 전승지는 황해도 장산곶 앞바다(MAP_12)"),
    "묘향산 보현사 수충사": ("묘향산 보현사", "게임 노드는 MAP_13(평안 남부)에 있음"),
    "묘향산 단군굴 암자": ("묘향산 단군굴", "게임 노드는 MAP_13"),
    "MAP_09 문경새재 제2관문(조곡관)": ("문경새재 조령관", "게임 노드는 MAP_05(충청 북부) 경계에 배치됨"),
    "지리산 천왕봉 북벽 성황당 터": ("지리산 천왕봉", "게임 노드는 MAP_10"),
    "개성 만월대 고려궁지 철광터": ("개성 만월대 옛터", ""),
    "밀양 영남루 아랑각 밀실": ("밀양 영남루", ""),
    "백두산 천지 용암호수 단애": ("백두산 천지", ""),
    "계룡산 신도안 천황봉 옛 제단": ("계룡산 천황봉", ""),
    "삼척 오십천 하구 촛대바위": ("삼척 안택선 침몰지", ""),
}


NEAR = {"산청": "진주목", "가평": "연천", "고양": "파주목", "서산": "해미", "안산": "남양", "논산": "부여", "화성": "수원화성", "뱀사골": "남원도호부",
        "울산": "동래현", "용인": "수원화성", "흥부골": "순천도호부", "철산": "선천", "구례": "순천도호부", "진해": "통영 통제영", "만경강": "익산",
        "안변": "덕원", "구월산": "송화", "백록담": "서귀포", "화전마을": "화천"}


def suggest_pos(parent, key):
    """상위 노드에서 약 4~6리(80~120px) 떨어진 빈 자리 — 기존 노드와 60px 이상 간격, 지도 가장자리 120px 안쪽."""
    import math
    h = sum(ord(c) for c in str(key))
    W, H = G.REG["map_size"]
    same = [n["pos"] for n in G.NODES if n["region"] == parent["region"]]
    for k in range(16):
        a = (h * 37 + k * 67) % 360 * math.pi / 180
        rad = 90 + (k % 3) * 20
        p = [round(min(W - 120, max(120, parent["pos"][0] + math.cos(a) * rad))), round(min(H - 120, max(120, parent["pos"][1] + math.sin(a) * rad)))]
        if all(math.dist(p, q) >= 60 for q in same):
            return p
    return p


def token_node(text, region=None):
    """어절 단위 일치(부분 문자열 오탐 방지): 어절 == 노드명, 노드명이 어절로 시작, 어절이 노드명으로 시작. 완전 일치·긴 이름 우선."""
    toks = [x for x in re.split(r"[^가-힣A-Za-z0-9]+", re.sub(r"MAP_\d{2}", " ", str(text))) if len(x) >= 2]
    best, score = None, 0
    for n in G.NODES:
        if region and n["region"] != region:
            continue
        nm = G.norm(n["name"])
        first = G.norm(n["name"].split()[0])
        for i, tk in enumerate(toks):
            two = tk + (toks[i + 1] if i + 1 < len(toks) else "")
            if tk == nm or two == nm:
                s = 100 + len(nm) + 2 * i  # 완전 일치는 뒤쪽 어절(더 구체적인 장소) 우선
            elif len(nm) >= 2 and (two.startswith(nm) or tk.startswith(nm)):
                s = 60 + len(nm)
            elif len(tk) >= 2 and (nm.startswith(tk) or first == tk):
                s = 40 + len(tk) - (5 if n["hidden"] else 0) + (5 if n["type"] == "city" else 0)
            else:
                continue
            if s < 100:
                s -= i  # 부분 일치는 앞쪽 어절(고을 이름) 우선
            if s > score:
                best, score = n, s
    return best, score


def resolve_node(tab, rid, text, map_hint=None):
    """위치 서술을 게임 노드로 해석하고, 권역 불일치·미존재를 기록한다."""
    text = str(text).strip()
    if not text or text.startswith("전국"):
        return None
    hints = MAP_RE.findall(str(map_hint)) if map_hint else []
    hint = hints[0] if hints else None
    manual = next((v for k, v in MANUAL_NODE.items() if k in text), None)
    node, note, status = None, "", "일치"
    if manual:
        node = next((n for n in G.NODES if n["name"] == manual[0]), None)
        note = manual[1]
        status = "일치" if (not hints or node["region"] in hints) else "권역 불일치"
    else:
        cands = [token_node(text, h) for h in hints] or [token_node(text)]
        node, sc = max(cands, key=lambda x: x[1])
        if node is not None and sc < 100:
            status = "근사(같은 고을 노드)"
            note = f"'{text}' 전용 노드 없음 → {node['name']} 에 부착하거나 은닉 노드 추가"
        elif node is None and hints:
            g, sc = token_node(text)
            if g is not None and sc >= 100:
                node, status = g, "권역 불일치"
    if node is None:
        regs = [m for m in regions_in(text) if m != "*"]
        reg = hint or (regs[0] if regs else None)
        toks = [x for x in re.split(r"[^가-힣]+", text) if len(x) >= 2]
        pool = [n for n in G.NODES if n["region"] == reg and not n["hidden"]]
        near = next((v for k, v in NEAR.items() if k in text), None)
        parent = next((n for n in pool if n["name"] == near), None) \
            or next((n for tk in toks for n in pool if n["name"][:2] == tk[:2]), None) \
            or next((n for n in G.NODES if reg and n["id"] == G.REGIONS[reg]["hub"]), None)
        pos = suggest_pos(parent, rid) if parent else ""
        if parent:
            PARENT[rid] = parent
        NODE_REFS.append({"탭": tab, "ID": rid, "원문 위치": text, "원문 권역": hint or "", "게임 노드": "", "노드 이름": "",
                          "게임 권역": reg or "", "좌표(px)": str(pos), "판정": "미존재 → 은닉 노드 추가 권장",
                          "권장": f"{G.REGION_NAME.get(reg, '?')} · 상위 노드 {parent['name'] if parent else '?'}{parent['pos'] if parent else ''} 옆 {pos} 에 은닉 노드 추가"})
        return None
    if status == "권역 불일치" and not note:
        note = f"게임 노드는 {node['region']}({G.REGION_NAME[node['region']]}) — 원본 권역 정정"
    NODE_REFS.append({"탭": tab, "ID": rid, "원문 위치": text, "원문 권역": hint or "", "게임 노드": node["id"], "노드 이름": node["name"],
                      "게임 권역": node["region"], "좌표(px)": str(node["pos"]), "판정": status, "권장": note})
    return node



# ================================================================ 01 식량
RICE_RE = re.compile(r"쌀|백미|나락|벼|산듸")
GAME_FOOD_MATCH = [(r"백미|쌀|나락|벼|산듸", "food_rice"), (r"보리", "food_barley"), (r"조\)|좁쌀|메조|차조|골\(조\)|기장|수수|피\(", "food_millet"),
                   (r"도토리", "food_acorn"), (r"칡", "food_kudzu"), (r"메밀", "food_buckwheat"), (r"토끼", "food_hare"), (r"꿩", "food_pheasant"),
                   (r"멧돼지|흑돼지", "food_boar"), (r"곰", "food_bear")]
GAME_MEAT_PRICE = {1: 12, 2: 30, 3: 90, 4: 260, 5: 800}      # 04_food_staples game 가격 곡선(×3)
GAME_MEAT_SATIETY = {1: 15, 2: 20, 3: 40, 4: 60, 5: 100}
FORAGE_REF = 3                                               # 04 forage T1 가격(도토리·칡)


def fix_01():
    t = Tab("01_식량_구황_수렵_105종")
    swap = {"MAP_11": "MAP_12", "MAP_12": "MAP_11"}
    for r in t.rows:
        m = t.g(r, "map_num")
        if m in swap and t.g(r, "region_name") != G.REGION_NAME[m]:
            t.s(r, "map_num", swap[m], "충돌", f"황해 북/남 뒤바뀜 — 품목({t.g(r, 'name_kr')})의 산지는 {G.REGION_NAME[swap[m]]}(게임 {swap[m]})")
        t.s(r, "region_name", G.REGION_NAME[t.g(r, "map_num")], "스키마", "게임 권역명으로 통일")
    ds_rice = {}
    for r in t.rows:
        if t.g(r, "category") == "주식곡물" and RICE_RE.search(t.g(r, "name_kr")):
            ds_rice[t.g(r, "map_num")] = num(t.g(r, "buy_price"))
    rice_ref = st.mean(ds_rice.values())
    med = {}
    for r in t.rows:
        if str(t.g(r, "category")).startswith("수렵"):
            med.setdefault(int(t.g(r, "tier")), []).append(num(t.g(r, "buy_price")))
    med = {k: st.median(v) for k, v in med.items()}
    forage_med = st.median(num(t.g(r, "buy_price")) for r in t.rows if "구황" in str(t.g(r, "category")))
    for r in t.rows:
        name, cat, tier, reg = t.g(r, "name_kr"), t.g(r, "category"), int(t.g(r, "tier")), t.g(r, "map_num")
        p = num(t.g(r, "buy_price"))
        gid = next((g for pat, g in GAME_FOOD_MATCH if re.search(pat, name)), "")
        rice = G.REGIONS[reg]["rice_price"]
        if cat == "주식곡물":
            kind, unit, weight, sat = "staple", "섬", 20.0, 0
            ref = ds_rice.get(reg, rice_ref)
            buy = rice if RICE_RE.search(name) else r5(rice * p / ref)
            sell = int(round(buy * G.RICE_SELL))
            why = (f"주식은 섬 단위 교역품: 쌀=권역 시세 regions.rice_price({rice}냥), 잡곡=권역 쌀 대비 원본 비율 유지. "
                   f"판매가=시세×{G.RICE_SELL}(TradeSystem 런타임 계산) — 원본은 권역 시세표(35~80냥)와 불일치")
            if re.search(r"주막에서만", str(t.g(r, "description"))):
                t.s(r, "description", t.g(r, "description").replace("주막에서만 구매 가능.", "도시·마을 상점에서 섬 단위로 거래."), "충돌",
                    "acquisition(도시/마을 상점)과 설명(주막 전용)이 모순")
        elif "구황" in cat:
            kind, unit, weight, sat = "forage", "줌", 0.5, 10 + 5 * (tier - 1)
            buy = max(1, int(round(FORAGE_REF * p / forage_med)))
            sell = sell_of(buy)
            why = f"야생 채집(무료 획득)품은 게임 구황 가격(1~6냥) 기준 — 원본(15~35냥) 그대로면 채집→판매 무한 파밍"
        else:
            kind, unit, weight, sat = "game", "근", 2.0, GAME_MEAT_SATIETY[tier]
            buy = r5(GAME_MEAT_PRICE[tier] * p / med[tier])
            sell = sell_of(buy)
            why = f"수렵육은 반복 획득 → 게임 수렵육 곡선(T{tier} {GAME_MEAT_PRICE[tier]}냥, ×3/등급)에 원본 상대가격 유지. 원본은 약 3배(적 처치 엽전 T{tier} {G.enemy_reward(tier)[1]}냥보다 큼)"
        t.s(r, "buy_price", buy, "밸런스", why)
        t.s(r, "sell_price", sell, "밸런스", f"판매가 = 게임 규칙(일반 {G.SELL_SPREAD} / 쌀 {G.RICE_SELL}) 런타임 계산값과 일치시킴", log=False)
        t.fill(r, "game_kind", kind)
        t.fill(r, "unit", unit)
        t.fill(r, "weight", weight)
        t.fill(r, "satiety", sat)
        t.fill(r, "perishable", kind == "game")
        t.fill(r, "game_id", gid)
        if gid and gid in G.FOODS and G.FOODS[gid]["tier"] != tier and kind != "staple":
            issue(t.name, t.rid(r), "tier", "충돌", f"게임 {gid} T{G.FOODS[gid]['tier']}", f"DB-15 T{tier}",
                  "같은 품목의 등급이 게임 04_food_staples 와 다름 → 병합 시 DB-15 등급 채택, 게임 행 가격 재계산 권장")
    return t


# ================================================================ 02 기초생필품
MAT_MATCH = [(r"사철", "mat_iron"), (r"숯", "mat_charcoal"), (r"소가죽", "mat_cowhide"), (r"부레풀|어교", "mat_fish_glue"), (r"옻칠", "mat_lacquer"),
             (r"천일염|소금", "mat_salt"), (r"무명 실|삼실", "mat_cotton"), (r"판재|원목", "mat_wood"), (r"점토|진흙", "mat_white_clay"),
             (r"부싯돌", "item_torch"), (r"밀랍초", "item_torch")]
BASE_PRICE = {"생필품": 20, "농산": 6, "수산": 10, "제작": 25}   # 게임 05_materials 평균대(원자재 25·소모품 5~25)
EXTRA_BASE = [  # 08 음식 레시피·13 모작 재료가 참조하지만 어느 탭에도 없는 항목(보충)
    ("농산 식자재(육류)", "수원 우시장 건포", "육포", 2, 30, "수원 우시장 쇠고기를 말린 건포. 국밥·설렁탕·신선로 재료."),
    ("수산 식자재(젓갈)", "서산 어리굴젓", "젓갈", 2, 25, "서산 간월도 굴을 삭힌 젓갈."),
    ("농산 식자재(양념)", "연안 참기름", "유지류", 2, 20, "황해도 연안의 참깨를 볶아 짠 기름."),
    ("농산 식자재(과일)", "북청 돌배", "과일", 1, 8, "함경도 북청의 단단한 돌배. 고기 재움 즙."),
    ("수산 식자재(해산)", "완도 완사 전복", "패류", 3, 90, "완도 바다의 참전복. 궁중 요리 재료."),
    ("농산 식자재(약선)", "금산 백삼", "약선", 3, 110, "금산 인삼을 껍질 벗겨 말린 백삼."),
    ("농산 식자재(양념)", "안동 덧간장", "발효장류", 3, 60, "해마다 새 간장을 덧부어 묵힌 종가 간장."),
    ("농산 식자재(견과)", "가평 잣", "견과", 2, 30, "가평 잣나무 숲의 잣."),
    ("농산 식자재(채소)", "콩나물", "기본채소", 1, 3, "시루에 기른 콩나물."),
    ("농산 식자재(축산)", "달걀", "축산", 1, 3, "장터 닭장의 달걀."),
    ("제작 재료(광물)", "정련 사철괴", "제철원료", 3, 80, "사철을 여러 번 녹여 불순물을 뺀 쇳덩이. 5등급 모작 재료."),
    ("제작 재료(광물)", "백은괴", "귀금속", 4, 300, "은광에서 제련한 은덩이."),
    ("제작 재료(광물)", "황금괴", "귀금속", 5, 900, "사금을 녹인 금덩이."),
    ("제작 재료(섬유)", "비단실", "직조원료", 2, 28, "명주실(게임 mat_silk_thread)."),
    ("제작 재료(섬유)", "금사(金絲)", "귀금속실", 4, 250, "금박을 감은 실. 금사 비단·금란가사 재료."),
    ("제작 재료(석재)", "백옥", "옥석", 4, 350, "희고 무른 옥. 패물 재료."),
    ("제작 재료(목재)", "벽조목(벼락 맞은 대추나무)", "영목", 4, 280, "벼락 맞은 대추나무. 오뢰목 도검·부적 재료."),
    ("제작 재료(석재)", "백두산 흑요석", "화산석", 5, 700, "백두산 화구의 흑요석."),
    ("제작 재료(가죽)", "호랑이 가죽", "특수가죽", 5, 1200, "백두산 호랑이 수렵 부산물(01 FOOD_0097)."),
    ("제작 재료(가죽)", "표범 모피", "특수가죽", 4, 450, "북방 표범 모피."),
    ("제작 재료(가죽)", "산노루 가죽", "피혁", 2, 35, "노루 수렵 부산물."),
    ("제작 재료(가죽)", "하얀 말가죽", "특수가죽", 5, 600, "제주 백마의 가죽."),
    ("제작 재료(광물)", "황동 고리·금강저", "합금", 3, 70, "구리·주석 합금(게임 mat_copper+mat_tin) 주물."),
    ("제작 재료(섬유)", "전주 한지", "종이", 2, 20, "게임 특산물 sp_jeonju_hanji 와 동일 품목."),
    ("제작 재료(식물)", "보리수 열매", "염주재료", 3, 60, "사찰 보리수 열매."),
    ("제작 재료(석재)", "현무암 옥석", "옥석", 5, 500, "한라산 현무암에서 나온 옥석."),
]


def fix_02():
    t = Tab("02_기초생필품_제작_44종")
    for r in t.rows:
        cat, name = str(t.g(r, "category")), t.g(r, "name_kr")
        gid = next((g for pat, g in MAT_MATCH if re.search(pat, name)), "")
        key = next(k for k in BASE_PRICE if cat.startswith(k))
        buy = G.MATERIALS[gid]["price"] if gid in G.MATERIALS else BASE_PRICE[key]
        if gid in G.MATERIALS:
            why = f"게임 05_materials {gid} 가격({buy}냥)과 통일"
        else:
            why = f"원본은 44종 전부 30/10·50/20 두 값뿐(등급·용도 구분 없음) → 분류별 게임 기준가({key} {buy}냥)"
        t.s(r, "buy_price", buy, "밸런스", why)
        t.s(r, "sell_price", sell_of(buy), "밸런스", "", log=False)
        t.fill(r, "game_id", gid)
        t.fill(r, "weight", 0.3 if key == "농산" or key == "수산" else 1.0)
        t.fill(r, "use", "recipe_ingredient" if key in ("농산", "수산") else ("craft_material" if key == "제작" else "consumable"))
        if name in ("보리쌀", "백미(흰쌀)", "조와 기장"):
            issue(t.name, t.rid(r), "name_kr", "충돌", name, "01탭 주식곡물(섬)과 중복",
                  "레시피 재료 '한 끼분(1/10섬)' 단위로 정의 — 01탭 섬 단위 교역품과 구분(ration=10 환산)")
        if name == "무쇠 솥":
            issue(t.name, t.rid(r), "name_kr", "충돌", "무쇠 솥 30냥", "게임 lg_musoe_sot(무쇠 노구솥, 300냥 행장)",
                  "야영 조리에 필요한 솥은 게임에서 행장 장비 → 이 행은 주막 비치품(플레이어 구매 불가)으로 표시")
            t.fill(r, "use", "facility_only")
    n = len(t.rows)
    for i, (cat, name, sub, tier, price, desc) in enumerate(EXTRA_BASE, 1):
        row = [""] * len(t.header)
        t.rows.append(row)
        for col, v in (("category", cat), ("name_kr", name), ("sub_type", sub), ("desc", desc), ("item_id", f"BASE_{n + i:04d}"),
                       ("tier", tier), ("buy_price", price), ("sell_price", sell_of(price))):
            row[t.ci(col)] = v
        t.fill(row, "use", "recipe_ingredient" if "식자재" in cat else "craft_material")
        t.fill(row, "weight", 0.3 if "식자재" in cat else 1.0)
        t.fill(row, "game_id", "mat_silk_thread" if name == "비단실" else ("sp_jeonju_hanji" if name == "전주 한지" else ""))
        t.fill(row, "보충", "신규")
        issue(t.name, f"BASE_{n + i:04d}", "행 추가", "보충", "", name, "08 음식·13 모작 재료가 참조하나 어느 탭에도 없음")
    return t



# ================================================================ 03 생활행장
# 게임 06_life_gear: 슬롯 4종(nav|carry|camp|record) · buffs 키는 기존 키만 · field_* 는 필드 스킬 효과.
# 원본 서술(영구 면역·100% 무효·전 지도 공개)은 생존·탐색·발견 명성 시스템을 무력화하므로 등급 상한 안에서 수치화.
LG = {  # tool_id: (slot, buffs, field, game_id, 변환 메모)
    "TOOL_001": ("carry", {"carry_capacity": 10}, {}, "lg_botjim", "+30kg → +10(기본 적재 30 대비 +33%)"),
    "TOOL_002": ("nav", {"travel_cost": -0.05}, {"field_search_radius_li": 3}, "lg_yundo", "조난 0%(게임에 조난 없음) → 탐색 반경 3리"),
    "TOOL_003": ("camp", {"fatigue_gain": -0.03}, {"field_night_torch": True}, "", "야간 시야 → 밤 이동 배율 횃불(0.75→0.9)"),
    "TOOL_004": ("camp", {"food_decay": -0.2}, {"field_gather_yield": 0.1}, "", "신선도 40% → 20%, 채집 +1개 → +10%"),
    "TOOL_005": ("camp", {}, {"field_weather_mult": {"rain": 0.9}}, "", "우천 감속 100% 무효 → 비 배율 0.8→0.9"),
    "TOOL_006": ("camp", {"capture_rate": 0.03}, {"field_hunt_rate": 0.1}, "", "수렵 +15% → +10%"),
    "TOOL_007": ("camp", {"fatigue_gain": -0.05}, {}, "", "갈증 수치 없음 → 피로 증가 -5%"),
    "TOOL_008": ("nav", {"travel_cost": -0.05}, {"field_checkpoint_fee": -0.5}, "", "통행료 50% 감면 유지(관문·나루 한정)"),
    "TOOL_009": ("carry", {"carry_capacity": 25}, {}, "lg_jige", "+70kg → +25 · 게임 lg_jige(T3 900냥 +40)와 등급 충돌"),
    "TOOL_010": ("nav", {"travel_cost": -0.1}, {"field_station_fare": -0.3}, "", "역마 무료 대여 → 역참 쾌속 이동 요금 -30%"),
    "TOOL_011": ("camp", {"fatigue_gain": -0.08}, {"field_disease_chance": -0.5}, "", "감기·동상 0% → 질병 확률 -50%"),
    "TOOL_012": ("camp", {}, {"field_gather_yield": 0.15}, "", "채광 +50% → 채집량 +15%"),
    "TOOL_013": ("camp", {"atk_pct": 0.03}, {"field_hunt_rate": 0.1}, "", "장전 속도(개념 없음) → 공격 +3%"),
    "TOOL_014": ("camp", {"food_decay": -0.35}, {}, "lg_chanhap", "부패 2배 연장 → -35% · 게임 lg_chanhap(T3 700냥 -50%)과 등급 충돌"),
    "TOOL_015": ("camp", {"fatigue_gain": -0.06}, {"field_terrain_mountain": 0.72}, "", "산악 스태미나 -35% → 산길 배율 0.65→0.72"),
    "TOOL_016": ("nav", {"travel_cost": -0.1}, {"field_checkpoint_fee": -1.0}, "", "국경 자유 통행 — Rank 3 해금 checkpoint_pass 와 중복 → min_rank 3"),
    "TOOL_017": ("camp", {}, {"field_herbal_heal": 0.15, "field_craft_anywhere": ["medicine_t1", "medicine_t2"]}, "", "치료 25% → 15%"),
    "TOOL_018": ("camp", {"res_all": 0.02}, {"field_camp_ambush": -0.5}, "", "피습 0% → 야영 피습 -50%"),
    "TOOL_019": ("nav", {}, {"field_search_radius_li": 5}, "", "명당·고분 자동 표식 → 탐색 반경 5리(은닉 노드는 '탐색' 행동으로만 발견)"),
    "TOOL_020": ("camp", {"res_all": 0.05}, {"field_disease_chance": -0.5}, "", "혹한 100% 면역 → 한랭 질병 -50%"),
    "TOOL_021": ("nav", {}, {"field_search_radius_li": 6}, "", "안개 해제 2.5배 → 탐색 반경 6리"),
    "TOOL_022": ("camp", {"capture_rate": 0.1}, {"field_hunt_rate": 0.1}, "", "맹수 포획 +20% → +10%"),
    "TOOL_023": ("nav", {"fatigue_gain": -0.1}, {}, "", "피로 -40% → -10%"),
    "TOOL_024": ("nav", {"travel_cost": -0.2}, {"field_station_fare": -0.5}, "", "역마 무료 무제한 → 요금 -50% (경제 싱크 보호)"),
    "TOOL_025": ("nav", {"travel_cost": -0.2}, {"field_route_preview": True}, "", "샛길 → 경로 미리보기(게임 대동여지도 분첩 동급)"),
    "TOOL_026": ("camp", {"food_decay": -0.6}, {}, "", "부패 영구 정지 → -60% (신선도 시스템 유지)"),
    "TOOL_027": ("nav", {"spd_bonus": 0.04, "travel_cost": -0.1}, {"field_terrain_mountain": 0.8}, "", "험로 감속 100% 무시 → 산길 0.65→0.8"),
    "TOOL_028": ("nav", {"travel_cost": -0.25}, {"field_search_radius_li": 10, "field_route_preview": True, "field_station_fare": -0.5}, "",
                 "전 지도 안개 100% 해제 → 도로·가시 노드만 공개(은닉 노드 공개는 발견 명성 35%를 무력화). 즉시 이동 → 역참 요금 -50%"),
    "TOOL_029": ("camp", {"fatigue_gain": -0.25}, {"field_gather_yield": 0.3, "field_clear_weather_per_day": 1}, "", "영구 피로 면역 → 피로 증가 -25%"),
    "TOOL_030": ("camp", {"res_all": 0.05}, {"field_disease_chance": -0.7, "field_make_item": {"id": "hr_sipjeon", "every_days": 7}}, "",
                 "모든 질병 영구 면역 → -70%, 하루 1회 완전회복 영약 → 7일마다 십전대보탕 1개"),
}


def fix_03():
    t = Tab("03_생활행장_30종")
    for r in t.rows:
        tid, tier = t.g(r, "tool_id"), int(t.g(r, "tier"))
        slot, buffs, field, gid, memo = LG[tid]
        t.fill(r, "slot_game", slot)
        t.fill(r, "buffs_json", json.dumps(buffs, ensure_ascii=False))
        t.fill(r, "field_json", json.dumps(field, ensure_ascii=False))
        t.fill(r, "min_rank", 3 if tid == "TOOL_016" else max(1, tier))
        t.fill(r, "durability", 100)
        t.fill(r, "game_id", gid)
        t.fill(r, "변환메모", memo)
        t.s(r, "sell_price", sell_of(num(t.g(r, "buy_price"))), "밸런스", "", log=False)
        issue(t.name, tid, "passive_buff", "밸런스", t.g(r, "passive_buff"), json.dumps({**buffs, **field}, ensure_ascii=False), memo)
        if gid:
            gp = G.load("06_life_gear.json")
            grow = next(x for x in gp["life_gear"] if x["id"] == gid)
            if grow["tier"] != tier or grow.get("price") != num(t.g(r, "buy_price")):
                issue(t.name, tid, "tier/buy_price", "충돌", f"게임 {gid} T{grow['tier']} {grow.get('price')}냥",
                      f"DB-15 T{tier} {t.g(r, 'buy_price')}냥", "병합 시 DB-15 값 채택(게임 행 갱신) 권장")
    return t



# ================================================================ 04 탈것
MOUNT_GAME_ID = {"MNT_001": "mt_donkey", "MNT_006": "mt_jeju_pony", "MNT_025": "mt_white_tiger", "MNT_028": "mt_haetae", "MNT_031": "mt_cheonma"}
MOUNT_SKILL = {  # 4·5등급 퀘스트 탈것 — 원본 보상 효과의 게임 수치화
    "MNT_023": ({"field_encounter_mult": {"ghost": 0.5}, "field_night_torch": True}, "악령 조우 0% → 50%"),
    "MNT_024": ({"field_water_pass": True}, "수륙양용 → 수계 통행(terrain=water 겸용)"),
    "MNT_025": ({"battle_skill": "sk_mt_white_tiger"}, "게임 스킬 산군 포효(적 전체 기절 1턴, 재사용 4)"),
    "MNT_026": ({"field_terrain_mountain": 0.9}, "수직 절벽 도약 → 산길 배율 0.9"),
    "MNT_027": ({"def_pct": 0.1}, "물리 피해 40% 반감 → 방어 +10%"),
    "MNT_028": ({"battle_skill": "sk_mt_haetae", "res_map": {"fire": 0.2}}, "화염 100% 면역 → 화염 저항 20%"),
    "MNT_029": ({"field_storm_safe": True}, "폭풍 침몰 면역 유지(뱃길 풍향 결항 무시)"),
    "MNT_030": ({"field_terrain_trail": 1.0}, "밀림 +20% → 오솔길 감속 제거"),
    "MNT_031": ({"battle_skill": "sk_mt_cheonma", "field_fast_travel": True}, "게임 천마와 동일"),
    "MNT_032": ({"reputation_gain": 0.1, "field_persuade_bonus": 0.2}, "평판 2배·무혈 회유 100% → 명성 +10%·설득 +20%p"),
    "MNT_033": ({"field_fast_travel": True, "revive_once": {"hp_pct": 0.3, "boss": False}}, "사망 시 완전 소생 → 일반 전투 1회 30% 부활(보스전 제외)"),
    "MNT_034": ({"field_fast_travel": True, "res_map": {"holy": 0.2}}, "낙뢰 면역 → 뇌(holy) 저항 20%"),
    "MNT_035": ({"field_fast_travel": True, "fatigue_gain": -0.1}, "쿨타임 30% 감소(턴 단위 쿨다운과 비호환) → 피로 -10%"),
}
DEV_CITY = {"경주": "경주부", "의주": "의주목", "회령/경성": "경성도호부", "경성": "경성도호부", "한양 도성": "한양 경조", "한양": "한양 경조",
            "강릉/삼척": "강릉대도호부", "황주/사리원": "황주목", "평북 영변/의주": "영변대도호부", "부여 공산성/정림사지": "공주 충청감영",
            "평양": "평양부", "제주목": "제주목 제주읍성"}


def norm_prereq(text, tier):
    """명성 절대치·없는 시스템(세력 평판·민심)·발전도 대상 도시를 게임 규칙으로 치환."""
    s = str(text)
    notes = []
    if re.search(r"명성 [\d,]+ ?이상", s):
        s = re.sub(r"(?:전 지역 )?명성 [\d,]+ ?이상", f"신분 Rank {tier}", s)
        notes.append(f"명성 1,500/3,000 은 신분 임계(R4 {G.RANK_TABLE[3]['threshold']:,} · R5 {G.RANK_TABLE[4]['threshold']:,})와 20배 차이 → Rank 조건으로")
    if "세력 평판" in s:
        s = re.sub(r"유\(儒\) 세력 평판 최고 등급", "유교 지식 5랭크", s)
        notes.append("세력 평판 시스템 없음 → 유교 지식 랭크")
    if "민심" in s:
        s = re.sub(r"팔도 모든 권역 민심\(평판\) 최고치 달성", "전 도(道) 명성 5단계", s)
        notes.append("민심 시스템 없음 → 도 명성 단계")
    if "살생" in s:
        s = re.sub(r",? ?살생\(범죄\)[^,]*", "", s)
        notes.append("살생(범죄) 카운트 시스템 없음 → 삭제")
    for k, city in sorted(DEV_CITY.items(), key=lambda x: -len(x[0])):
        pat = re.escape(k) + r" (?:도시 )?발전도"
        if re.search(pat, s):
            s = re.sub(pat, f"{city} 발전도", s)
            if city.split()[0] not in k:
                notes.append(f"'{k}' → 발전 대상 대도시 {city}(소도시는 발전도 없음)")
            break
    if "탐방도" in s:
        s = s.replace("금강산 권역 탐방도 70% 이상", "MAP_03 콘텐츠 발견 70%")
        notes.append("탐방도 → 권역 콘텐츠 발견률")
    return s, notes


def fix_04():
    t = Tab("04_탈것_35종_퀘스트")
    vb = G.MOVE["v_base"]
    for r in t.rows:
        mid, tier = t.g(r, "mount_id"), int(t.g(r, "tier"))
        spd, kg, typ = num(t.g(r, "speed_bonus")), num(t.g(r, "weight_bonus")), str(t.g(r, "type"))
        terrain = "air" if re.search(r"비행|천상|선학|사신수", typ) else ("water" if re.search(r"수중|해상", typ) else "ground")
        t.fill(r, "terrain", terrain)
        t.fill(r, "v_mount", int(round(vb * spd / 100)))
        t.fill(r, "carry_capacity", int(round(kg * 0.25)))
        t.fill(r, "spd_bonus_ctb", round(0.02 * tier, 2))
        t.fill(r, "stamina", 100 + 20 * (tier - 1))
        t.fill(r, "min_rank", max(tier, int(num(t.g(r, "city_tier_req"), 1))))
        t.fill(r, "game_id", MOUNT_GAME_ID.get(mid, ""))
        if tier <= 3:
            t.fill(r, "acquire", "shop:yeokcham")
            t.s(r, "sell_price", sell_of(num(t.g(r, "buy_price"))), "밸런스", "", log=False)
        else:
            t.fill(r, "acquire", "quest")
            t.s(r, "buy_price", "", "스키마", "-1 은 숫자 칸의 누락 표기 → 빈칸 + acquire=quest")
            t.s(r, "sell_price", 0, "스키마", "퀘스트 탈것은 귀속(판매 불가) — -1 대신 0")
            rep, money = G.quest_reward(tier, "mount")
            t.fill(r, "reward_rep", rep)
            t.fill(r, "reward_money", money)
            fx, memo = MOUNT_SKILL[mid]
            t.fill(r, "mount_effect_json", json.dumps(fx, ensure_ascii=False))
            issue(t.name, mid, "quest_reward", "밸런스", t.g(r, "quest_reward"), json.dumps(fx, ensure_ascii=False), memo)
            new, notes = norm_prereq(t.g(r, "quest_prereq"), tier)
            if notes:
                t.s(r, "quest_prereq", new, "충돌", " / ".join(notes))
            steps = [x for x in re.split(r"\s*\d단계:\s*", str(t.g(r, "quest_steps"))) if x.strip()]
            t.fill(r, "quest_step_count", len(steps))
        if tier <= 3 and mid in MOUNT_GAME_ID:
            gm = G.MOUNTS[MOUNT_GAME_ID[mid]]
            issue(t.name, mid, "v_mount/carry", "충돌", f"게임 {gm['id']} v{gm['v_mount']}·짐{gm['carry_capacity']}",
                  f"DB-15 환산 v{int(round(vb * spd / 100))}·짐{int(round(kg * 0.25))}", "속도%·kg 을 게임 단위(px/s·무게)로 환산 — 병합 시 이 값 채택")
        if t.g(r, "type") and tier <= 3:
            node = resolve_node(t.name, mid, t.g(r, "region_req"), t.g(r, "region_req"))
            if node:
                t.fill(r, "shop_node", node["id"])
        elif tier >= 4:
            node = resolve_node(t.name, mid, t.g(r, "region_req"), t.g(r, "region_req"))
            t.fill(r, "quest_node", node["id"] if node else "")
    issue(t.name, "-", "speed_bonus/weight_bonus", "스키마", "% · kg", "v_mount(px/s) · carry_capacity(무게)",
          f"게임 이동식 V=(V_base {vb}+v_mount)… 과 적재 기준(맨몸 {G.MOVE['carry_base']})에 맞게 환산: v=V_base×%/100, 짐=kg×0.25")
    issue(t.name, "-", "행 누락", "보충", "", "황포돛배(T2 수상)·준마(T3)·징발 군마(T4)",
          "게임 07_mounts 에만 있음 — 1~3등급 수상 탈것이 DB-15에 없어 뱃길 교역(황포돛배)이 끊김 → 게임 행 유지 권장")
    return t


# ================================================================ 05 포획구
CAP_KIND = {"유": "human", "불": "ghost", "선": "yokai", "무": "beast"}
CAP_GAME = {"유": "yu", "불": "bul", "선": "seon", "무": "mu"}


def fix_05():
    t = Tab("05_포획구_20종")
    for r in t.rows:
        fam = re.search(r"CAP_(.)_", t.g(r, "item_id")).group(1)
        tier = int(t.g(r, "tier"))
        g = G.CAPTURE[f"cap_{CAP_GAME[fam]}_{tier}"]
        old_rate = re.search(r"(\d+)%", str(t.g(r, "description")))
        t.s(r, "buy_price", g["price"], "밸런스",
            f"원본 가격은 등급 간 등차(+180냥)라 5등급(성공률 최고)이 가장 가성비 좋음 → 게임 포획구 곡선(30/90/250/700/1800) 채택")
        t.s(r, "sell_price", sell_of(g["price"]), "밸런스", "", log=False)
        if old_rate:
            desc = str(t.g(r, "description")).replace(old_rate.group(0), f"{int(g['base_rate'] * 100)}%")
            t.s(r, "description", desc, "밸런스",
                f"성공률 {old_rate.group(0)} → 게임 base_rate {g['base_rate']} (빈사 HP≤30% 전제, 5등급 85%면 5등급 동료가 거의 확정 포획)")
        t.fill(r, "target_kind", CAP_KIND[fam])
        t.fill(r, "base_rate", g["base_rate"])
        t.fill(r, "method", g["method"])
        t.fill(r, "weight", g["weight"])
        t.fill(r, "game_id", g["id"])
        if fam == "불" and "요괴" in str(t.g(r, "description")):
            issue(t.name, t.rid(r), "description", "충돌", "불(염주)로 요괴/요마 포획", "원혼(ghost) 전용",
                  "게임 계통 규칙: 유=인간·불=원혼·선=요괴·무=맹수. 요괴는 선(부적) 계통")
    return t



# ================================================================ 07 약초
HERB_GAME = {"감초": "herb_gamcho", "생강": "herb_saenggang", "약쑥": "herb_ssuk", "대추": "herb_daechu", "황기": "herb_hwanggi", "작약": "herb_jakyak",
             "참당귀": "herb_danggwi", "숙지황": "herb_sukjihwang", "백출": "herb_baekchul", "백복령": "herb_bokryeong", "천궁": "herb_cheongung",
             "천연우황": "herb_uhwang", "사향": "herb_sahyang", "원용": "herb_nokyong", "천년천종산삼": "herb_sansam"}
GAME_HERB_MED = {1: 9, 2: 24, 3: 130, 4: 520, 5: 3000}      # 10_herbs 등급별 중앙 가격
EXTRA_HERB = ["herb_yeongji", "herb_insam", "herb_yukgye", "herb_geumeunhwa"]  # 게임에만 있고 레시피·보상이 참조
HUNT_RE = re.compile(r"우황|사향|녹용|원용|웅담")


def fix_07():
    t = Tab("07_약초재료_26종")
    ds_med = {}
    for r in t.rows:
        ds_med.setdefault(int(t.g(r, "tier")), []).append(num(t.g(r, "buy_price")))
    ds_med = {k: st.median(v) for k, v in ds_med.items()}
    for r in t.rows:
        nm, tier = G.norm(t.g(r, "name_kr")), int(t.g(r, "tier"))
        gid = HERB_GAME.get(nm, "")
        if gid:
            gh = G.HERBS[gid]
            if gh["tier"] != tier:
                t.s(r, "tier", gh["tier"], "충돌", f"게임 {gid}({gh['name']}) T{gh['tier']} — DB-15 는 흔한 약재를 1등급씩 높게 잡아 "
                    "2등급 탕약(쌍화탕·보중익기탕)이 3등급 재료를 쓰는 모순 발생")
            t.s(r, "buy_price", gh["price"], "밸런스", f"게임 {gid} 가격 {gh['price']}냥과 통일(원본은 약 10배 — 탕약 원가가 효과보다 비쌈)")
        else:
            t.s(r, "buy_price", r5(GAME_HERB_MED[tier] * num(t.g(r, "buy_price")) / ds_med[tier]), "밸런스",
                f"게임 약초 곡선(T{tier} 중앙 {GAME_HERB_MED[tier]}냥)에 원본 상대가격 유지")
        t.s(r, "sell_price", sell_of(num(t.g(r, "buy_price"))), "밸런스", "", log=False)
        tier = int(t.g(r, "tier"))
        src = "hunt" if HUNT_RE.search(nm) else ("yakbang" if tier <= 2 else "gather")
        t.fill(r, "source", src)
        t.fill(r, "regions", ",".join(regions_in(t.g(r, "habitat"))) or "*")
        t.fill(r, "weight", 0.2)
        t.fill(r, "perishable", tier <= 2)
        t.fill(r, "game_id", gid)
    n = len(t.rows)
    for i, gid in enumerate(EXTRA_HERB, 1):
        h = G.HERBS[gid]
        row = [""] * len(t.header)
        t.rows.append(row)
        for col, v in (("herb_id", f"HERB_{n + i:03d}"), ("name_kr", h["name"]), ("tier", h["tier"]), ("habitat", "게임 10_herbs 기존 품목"),
                       ("buy_price", h["price"]), ("sell_price", sell_of(h["price"])), ("desc", "게임 레시피·보상이 참조하는 약초(보충)"),
                       ("source", h["source"]), ("weight", h["weight"]), ("perishable", h["perishable"]), ("game_id", gid), ("보충", "신규")):
            t.fill(row, col, v)
        issue(t.name, f"HERB_{n + i:03d}", "행 추가", "보충", "", h["name"], "게임 탕약(십전대보탕·선단)과 14탭 보상(천년 영지)이 참조하나 DB-15 에 없음")
    return t


# ================================================================ 06 한방약
MED = {  # med_id: (게임 effect, battle_usable, game_id, 메모)
    "MED_0001": ({"heal_pct": 0.2, "cure_field": ["cold"]}, True, "", "체력 +50 → 20%(주인공 HP 100~250 기준)"),
    "MED_0002": ({"cure_field": ["fever"]}, False, "", "더위 먹음·배탈 → 필드 질병 열병 치료"),
    "MED_0003": ({"heal_pct": 0.1, "cure": ["burn", "poison"]}, True, "", ""),
    "MED_0004": ({"heal_pct": 0.15, "fatigue": -40, "field_immune": {"ids": ["cold"], "days": 1}}, True, "hr_ssanghwa", "게임 쌍화탕(T1)과 등급 충돌 — 1시간 면역 → 1일"),
    "MED_0005": ({"fatigue": -20, "buff": {"hp_pct": 0.08}}, True, "", "스태미나(게임 수치 없음) → 최대 HP +8%"),
    "MED_0006": ({"cure_field": ["fever"], "field_food_buff_mult": 1.25}, False, "", "음식 버프 1.5배 → 1.25배"),
    "MED_0007": ({"heal_pct": 0.6, "fatigue": -100, "cure": ["poison", "bleed"]}, True, "hr_sipjeon", "게임 십전대보탕과 동일(밸런스 시뮬 클러치 기준 아이템)"),
    "MED_0008": ({"heal_pct": 0.15, "cure": ["bleed"]}, True, "hr_geumchang", ""),
    "MED_0009": ({"field_immune": {"ids": ["fever"], "days": 1}, "field_buff": {"fatigue_gain_mult": 0.7, "days": 1}}, False, "", "1시간 → 1일"),
    "MED_0010": ({"cure": ["stun", "fear", "charm", "curse"]}, True, "hr_uhwang", "게임 우황청심원(T4)과 대응"),
    "MED_0011": ({"buff": {"hp_pct": 0.15}, "regen_pct_per_turn": 0.03}, True, "hr_gyeongok", "게임 경옥고 T3 ↔ DB-15 T4 등급 충돌"),
    "MED_0012": ({"heal_pct": 0.5, "buff": {"hp_pct": 0.1}}, True, "", "최대 체력 +150 → +10%(상한 250 대비 과대)"),
    "MED_0013": ({"buff": {"atk_pct": 0.12, "def_pct": 0.12}}, True, "hr_gongjin", "근력·민첩·지혜(게임에 없는 능력치) +25% → 공격·방어 +12%"),
    "MED_0014": ({"cure": ["poison"], "permanent_hp": 5, "once_per_save": True}, False, "", "반복 제작 가능한 영구 최대 HP +50 → 1회 한정 +5"),
    "MED_0015": ({"death_ward": {"turns": 3, "hp_floor": 1}}, True, "hr_seondan",
                 "부활 → 즉사 방지 버프: 복용 후 3턴 동안 치명타를 맞아도 HP 1 로 버티며 더 줄지 않음(동료 통합 전투는 주인공이 쓰러지면 즉시 패배라 부활이 무의미)"),
}
FAC_WORDS = [("모닥불", "campfire"), ("약방", "yakbang"), ("약령시", "yakryeongsi"), ("혜민서", "hyeminseo"), ("내의원", "hyeminseo"),
             ("감영", "yakbang"), ("심산|은둔|제단|비로봉|천지", "special_node")]


def herb_index(t07):
    idx = {}
    for r in t07.rows:
        idx[G.norm(t07.g(r, "name_kr"))] = r
    return idx


def fix_06(t07):
    t = Tab("06_한방약_레시피_15종")
    hidx = herb_index(t07)
    for r in t.rows:
        mid, tier = t.g(r, "med_id"), int(t.g(r, "tier"))
        ids, miss = [], []
        for part in str(t.g(r, "ingredients")).split(","):
            m = re.match(r"\s*(.+?)\s*x\s*(\d+)", part)
            if not m:
                continue
            h = hidx.get(G.norm(m.group(1)))
            if not h:
                miss.append(m.group(1))
                continue
            ids.append({"id": t07.g(h, "herb_id"), "qty": int(m.group(2))})
            ht = int(t07.g(h, "tier"))
            if ht > tier:
                if t07.g(h, "game_id"):
                    issue(t.name, mid, "tier", "충돌", f"T{tier}", f"재료 {t07.g(h, 'name_kr')} T{ht}", "게임 확정 약초보다 낮은 등급 — 레시피 등급 상향 필요")
                else:
                    t07.s(h, "tier", tier, "충돌", f"{t.g(r, 'name_kr')}(T{tier}, 비전서 해금 구조)에 쓰이는 재료가 T{ht} → 재료 등급을 레시피 등급으로")
                    np = r5(num(t07.g(h, "buy_price")) * GAME_HERB_MED[tier] / GAME_HERB_MED[ht])
                    t07.s(h, "buy_price", np, "밸런스", f"등급 T{ht}→T{tier} 에 맞춰 가격 재계산", log=False)
                    t07.s(h, "sell_price", sell_of(np), "밸런스", "", log=False)
                    t07.fill(h, "source", "yakbang")
                    t07.fill(h, "perishable", True)
        for mname in miss:
            issue(t.name, mid, "ingredients", "참조", mname, "", "07 약초에 없는 재료")
        fx, usable, gid, memo = MED[mid]
        t.fill(r, "ingredients_json", json.dumps(ids, ensure_ascii=False))
        t.fill(r, "effect_json", json.dumps(fx, ensure_ascii=False))
        t.fill(r, "battle_usable", usable)
        t.fill(r, "book", f"BOOK_MED_0{tier}")
        loc = str(t.g(r, "craft_location"))
        t.fill(r, "craft_at", ",".join(dict.fromkeys(f for w, f in FAC_WORDS if re.search(w, loc))))
        dev = re.search(r"발전도 (\d)", loc)
        t.fill(r, "craft_min_dev", int(dev.group(1)) if dev else 0)
        t.fill(r, "game_id", gid)
        issue(t.name, mid, "effect", "밸런스", t.g(r, "effect"), json.dumps(fx, ensure_ascii=False), memo or "서술 효과 → 게임 효과 키")
    issue(t.name, "MED_0012", "name_kr", "고증", "자하거탕", "재료에 자하거(태반)가 없음", "재료를 바꾸거나 이름을 '녹용대보탕'류로 변경 권장")
    issue(t.name, "-", "tool_req", "스키마", "약탕기·약연·제환기 등", "시설 비치 도구",
          "해당 도구가 어느 탭에도 아이템으로 없음 → 시설(craft_at) 조건으로 해석. 야외 조제만 행장 '무쇠 노구솥'(lg_musoe_sot) 필요")
    return t



# ================================================================ 이름 인덱스(재료·보상·드롭 해석)
ALIAS = {"소금": "천일염", "배": "북청돌배", "법성포굴비": "sp_yeonggwang_gulbi", "보은속리산대추": "대추", "묘향산석청": "석청", "석청": "석청",
         "사철괴": "사철", "정련사철괴": "정련사철괴", "백탄숯": "숯", "백탄": "숯", "숯": "숯", "참나무": "참나무원목", "어피": "어피",
         "부레풀": "민어부레풀", "옻칠원액": "옻칠원액", "옻칠": "옻칠원액", "무명포대": "무명무명포대", "삼실": "무명실과삼실", "삼끈": "무명실과삼실",
         "비단실": "비단실", "비단": "비단실", "비단끈": "비단실", "금사": "금사", "금사비단": "금사", "연꽃비단": "금사", "금박": "금사",
         "황동고리": "황동고리금강저", "황동금강저": "황동고리금강저", "소나무판재": "소나무판재", "왕골": "볏짚과왕골", "목화무명천": "무명실과삼실",
         "푸른무명포": "무명실과삼실", "닥나무실": "전주한지", "전주한지": "전주한지", "한지": "전주한지", "경면주사": "mat_cinnabar", "순금괴": "황금괴",
         "백은장식": "백은괴", "호랑이가죽": "호랑이가죽", "산삼잎": "천년천종산삼", "불로초조각": "삼신산불로초", "옹기점토": "옹기점토",
         "화강암석재": "화강암석재", "벽조목": "벽조목", "백두산흑요석": "백두산흑요석", "천년영지": "영지", "관아통행패": "item_tonghaengjeung"}


def build_name_index(tabs):
    idx = {}

    def put(name, ref):
        k = G.norm(name)
        if k and k not in idx:
            idx[k] = ref
    for tname, col_id in (("02_기초생필품_제작_44종", "item_id"), ("01_식량_구황_수렵_105종", "item_id"), ("07_약초재료_26종", "herb_id"),
                          ("03_생활행장_30종", "tool_id"), ("05_포획구_20종", "item_id"), ("12_제작비전서_24종", "book_id")):
        t = tabs[tname]
        for r in t.rows:
            put(t.g(r, "name_kr"), t.g(r, col_id))
    for d in (G.SPECIALTIES, G.MATERIALS, G.FOODS, G.HERBS):
        for k, v in d.items():
            put(v["name"], k)
    for h in G.HERITAGE:
        put(h["name"], h["id"])
    return idx


def resolve_name(idx, name):
    k = G.norm(name)
    for cand in (k, G.norm(ALIAS.get(k, "")), ALIAS.get(k, "")):
        if cand and (cand in idx):
            return idx[cand]
        if cand and re.match(r"^(sp|mat|item|herb|food)_", cand):
            return cand
    # 앞부분 일치(예: '야생 청둥오리' ↔ '야생 청둥오리 고기')
    hits = [v for kk, v in idx.items() if len(k) >= 2 and (kk.startswith(k) or k.startswith(kk)) and len(kk) >= 2]
    return hits[0] if len(hits) == 1 else None


def parse_ingredients(text):
    out = []
    for part in re.split(r",\s*(?![^()]*\))", str(text)):
        part = part.strip()
        m = re.match(r"^(.*?)\((.+?)\s*x\s*(\d+)\)$", part)          # 녹두전(메밀가루 x1) → 실제 재료
        if m:
            out.append((m.group(2).strip(), int(m.group(3)), m.group(1).strip()))
            continue
        m = re.match(r"^(.+?)\s*x\s*(\d+)$", part)
        if m:
            out.append((m.group(1).strip(), int(m.group(2)), ""))
    return out


# ================================================================ 08 음식 레시피
FOOD = {  # recipe_id: (effect, game_id, book, 메모)
    "RECIPE_FOOD_001": ({"satiety": 40, "fatigue": -10}, "", "BOOK_COOK_01", "스태미나 → 피로 회복"),
    "RECIPE_FOOD_002": ({"satiety": 60, "field_buff": {"satiety_decay_mult": 0.7, "days": 0.5}}, "fr_gukbap", "BOOK_COOK_01", ""),
    "RECIPE_FOOD_003": ({"satiety": 35, "field_buff": {"move_mult": 1.05, "days": 0.5}}, "", "BOOK_COOK_01", ""),
    "RECIPE_FOOD_004": ({"satiety": 75, "heal_pct": 0.1, "battle_buff": {"atk_pct": 0.05, "duration_battles": 2}}, "fr_seolleongtang", "BOOK_COOK_02",
                        "공격력 +10(고정) → +5%. 게임 설렁탕(hp +8%)과 효과 다름"),
    "RECIPE_FOOD_005": ({"satiety": 70, "battle_buff": {"hp_pct": 0.08, "duration_battles": 2}}, "", "BOOK_COOK_02", "최대 스태미나 → 최대 HP"),
    "RECIPE_FOOD_006": ({"satiety": 65, "fatigue": -30, "field_buff": {"weather_rain_mult": 0.9, "days": 0.5}}, "", "BOOK_COOK_02", ""),
    "RECIPE_FOOD_007": ({"satiety": 80, "battle_buff": {"atk_pct": 0.08, "duration_battles": 3}}, "", "BOOK_COOK_03", "치명타 +10% → 공격 +8%"),
    "RECIPE_FOOD_008": ({"satiety": 85, "field_buff": {"move_mult": 1.1, "days": 0.5}}, "", "BOOK_COOK_03", "이동 +15% → +10%"),
    "RECIPE_FOOD_009": ({"satiety": 85, "cure_field": ["cold"], "battle_buff": {"res_all": 0.05, "duration_battles": 3}}, "", "BOOK_COOK_03", ""),
    "RECIPE_FOOD_010": ({"satiety": 90, "battle_buff": {"atk_pct": 0.15, "duration_battles": 3}}, "", "BOOK_COOK_04", "근력 +20% → 공격 +15%(게임 갈비찜 동급)"),
    "RECIPE_FOOD_011": ({"satiety": 90, "battle_buff": {"hp_pct": 0.12, "duration_battles": 3}}, "", "BOOK_COOK_04", "'풍류 명성 획득' 삭제 — 반복 조리로 명성 파밍"),
    "RECIPE_FOOD_012": ({"satiety": 70, "fatigue": -50, "field_buff": {"persuade_bonus": 0.1, "days": 1}}, "", "BOOK_COOK_04", "교섭 +30% → +10%p"),
    "RECIPE_FOOD_013": ({"satiety": 80, "battle_buff": {"atk_pct": 0.12, "def_pct": 0.12, "spd_bonus": 0.05, "duration_battles": 3}}, "fr_sinseollo", "BOOK_COOK_05",
                        "게임 신선로(밸런스 시뮬 5등급 세팅 기준 음식) 효과 유지 — 생명력 +200·저항 15%는 과대"),
    "RECIPE_FOOD_014": ({"satiety": 80, "field_buff": {"move_mult": 1.1, "days": 0.5}, "battle_buff": {"res_all": 0.08, "duration_battles": 3}}, "fr_gujeolpan", "BOOK_COOK_05",
                        "게임 구절판(T3)과 등급 충돌"),
    "RECIPE_FOOD_015": ({"satiety": 100, "battle_buff": {"hp_pct": 0.15, "duration_battles": 3}}, "", "BOOK_COOK_05", "재생 2배 → 최대 HP +15%"),
    "RECIPE_FOOD_016": ({"satiety": 100, "battle_buff": {"atk_pct": 0.15, "def_pct": 0.15, "spd_bonus": 0.06, "duration_battles": 3}}, "", "BOOK_COOK_06",
                        "전 능력 +30% → 공·방 +15%·속도 +6%(음식 상한)"),
    "RECIPE_FOOD_017": ({"satiety": 90, "field_buff": {"storm_fatigue_immune": True, "days": 1}}, "fr_jeonbokcho", "BOOK_COOK_06", "게임 전복초(T3)와 등급 충돌"),
    "RECIPE_FOOD_018": ({"satiety": 100, "fatigue": -100, "cure_field": ["cold", "fever", "chill", "plague"]}, "", "BOOK_COOK_06", "'영구 소멸' → 현재 질병 치료"),
}
COOK_FAC = [("모닥불", "campfire"), ("주막", "jumak_gamasot"), ("식당|요리관|연회관|종가|숙수관|소주방|수라간|객주|분원", "restaurant")]


def fix_08(idx):
    t = Tab("08_음식_레시피_18종")
    for r in t.rows:
        rid = t.g(r, "recipe_id")
        ings, miss = [], []
        for name, q, dish in parse_ingredients(t.g(r, "ingredients")):
            ref = resolve_name(idx, name)
            (ings.append({"id": ref, "qty": q, "src": name}) if ref else miss.append(name))
        for m in miss:
            issue(t.name, rid, "ingredients", "참조", m, "", "어느 탭에도 없는 재료")
        fx, gid, book, memo = FOOD[rid]
        t.fill(r, "ingredients_json", json.dumps([{"id": i["id"], "qty": i["qty"]} for i in ings], ensure_ascii=False))
        t.fill(r, "effect_json", json.dumps(fx, ensure_ascii=False))
        fac = str(t.g(r, "facility"))
        t.fill(r, "cook_at", ",".join(dict.fromkeys(f for w, f in COOK_FAC if re.search(w, fac))))
        t.fill(r, "needs_tool", "lg_musoe_sot" if "모닥불" in fac else "")
        t.fill(r, "book", book)
        t.fill(r, "weight", 0.6)
        t.fill(r, "perishable", True)
        t.fill(r, "game_id", gid)
        issue(t.name, rid, "effect", "밸런스", t.g(r, "effect"), json.dumps(fx, ensure_ascii=False), memo or "서술 → 게임 음식 효과 키")
    issue(t.name, "-", "effect(시간)", "스키마", "30분·1시간·2시간", "duration_battles(전투 횟수)·days",
          "게임 음식 버프는 '다음 전투 N회' 또는 게임 일수 단위 — 실시간 분 단위 없음")
    return t



# ================================================================ 09 적
ENEMY_GAME = {"ENM_002": "en_bandit", "ENM_003": "en_wolf", "ENM_006": "en_dokkaebi_small", "ENM_011": "en_galjae_bandit",
              "ENM_012": "en_yagwanggwi", "ENM_015": "en_ghost", "ENM_022": "en_gumiho", "ENM_031": "en_bulgasari",
              "ENM_032": "en_imugi", "ENM_033": "en_jirisan_sanshin", "ENM_038": "en_arang", "ENM_039": "en_heukryong", "ENM_042": "en_yeokcheon"}
KIND_OF = [("인간형", "human"), ("야수형", "beast"), ("원혼형|원령|원귀", "ghost"), ("용족|사신수", "dragon"), ("요괴형|신수형|귀왕|타락신|타락도사|해소신|불마|마인", "yokai")]
ELEM_OF = [(r"불가사리|철", "metal"), (r"흑룡|화산|구미호|강철이|여우", "fire"), (r"이무기|척서귀|물귀신|수살|해", "water"), (r"도깨비|두억|지네|야광", "wood")]
TERRAIN_OF = [("road", r"관로|장터|마을|인가|주막|관아|뒷골목|나루|포구|해안|갈대|성|진지|수도터"), ("mountain", r"산|고개|암벽|봉우리|원시림|설산|동굴|바위|협곡"),
              ("water", r"강|늪|용소|해|바다|파도|연못|소택|침몰선"), ("trail", r"숲|들판|폐가|묘|고분|폐사지|절터|사찰|사당|황무지|하천|당산")]


def fix_09(idx, skills_by_owner):
    t = Tab("09_조선설화_적목록_42종")
    ref_n, ref_b = G.tier_ref_normal(), G.tier_ref_boss()
    ds = {}
    for r in t.rows:
        tier = int(t.g(r, "tier"))
        key = ("boss", tier) if tier >= 4 else ("n", tier)
        ds.setdefault(key, []).append(r)
    scale = {}
    for (kind, tier), rows in ds.items():
        if kind == "n":
            ref = ref_n[tier]
            src = rows
        else:
            pairs = [(r, G.ENEMIES[ENEMY_GAME[t.g(r, "enemy_id")]]) for r in rows if t.g(r, "enemy_id") in ENEMY_GAME]
            ref = {k: st.mean(g[k] for _, g in pairs) for k in ("hp", "atk", "def", "speed")}
            src = [p[0] for p in pairs]
        scale[(kind, tier)] = {k: ref[k] / st.mean(num(t.g(r, k)) for r in src) for k in ("hp", "atk", "def", "speed")}
    for r in t.rows:
        eid, tier = t.g(r, "enemy_id"), int(t.g(r, "tier"))
        boss = tier >= 4
        cat = str(t.g(r, "category"))
        kind = next(k for pat, k in KIND_OF if re.search(pat, cat))
        gid = ENEMY_GAME.get(eid, "")
        sc = scale[("boss" if boss else "n", tier)]
        if gid:
            g = G.ENEMIES[gid]
            new = {k: g[k] for k in ("hp", "atk", "def", "speed")}
            why = f"게임 {gid} 의 튜닝값 그대로(balance_sim PASS 기준)"
        else:
            new = {k: int(round(num(t.g(r, k)) * sc[k])) for k in ("hp", "atk", "def", "speed")}
            pool = [e for e in G.ENEMIES.values() if (e.get("boss_tier") == tier if boss else (e["tier"] == tier and not e.get("boss_tier")))]
            lo_s, hi_s = min(e["speed"] for e in pool), max(e["speed"] for e in pool)
            new["speed"] = max(lo_s - 5, min(hi_s + 5, new["speed"]))  # 속도는 턴 수를 직접 좌우 → 게임 동급 범위 ±5 안으로
            why = (f"등급 T{tier} 게임 {'보스' if boss else '일반'} 평균에 맞춘 배율(HP×{sc['hp']:.2f}·ATK×{sc['atk']:.2f}·DEF×{sc['def']:.2f}·SPD×{sc['speed']:.2f}), 원본 상대 강약 유지. "
                   "원본 수치는 주인공 HP 100~250·동료 통합 전투(주인공 1명이 모든 공격을 받음) 기준으로 약 2~2.5배 과대")
        t.fill(r, "hp_conv", new["hp"])
        t.fill(r, "atk_conv", new["atk"])
        tn = TUNING.get(eid, {})
        for k in ("hp", "atk"):
            if k in tn:
                new[k] = tn[k]
        if any(k in tn for k in ("hp", "atk")):
            why += " · 이후 CTB 시뮬레이터(balance_check.py)로 HP/ATK 보정"
        for k in ("hp", "atk", "def", "speed"):
            t.s(r, k, new[k], "밸런스", why if k == "hp" else f"({k}) 위와 같은 기준", log=True)
        t.s(r, "ap", 3, "충돌", "시작 AP 는 전 개체 3(+이동속도 보너스) — 원본 4~6이면 적이 첫 턴에 궁극기 연사", log=True)
        rep, money = G.enemy_reward(tier, boss)
        t.s(r, "exp", "", "충돌", "게임은 레벨 없는 성장(경험치 없음) → 처치 명성(reward_rep)으로 대체", log=False)
        t.fill(r, "reward_rep", rep)
        md = str(t.g(r, "money_drop"))
        if not md.startswith("0"):
            nm = f"{money}냥" if boss else f"{int(money * 0.7)}~{int(round(money * 1.3))}냥"
            t.s(r, "money_drop", nm, "밸런스", f"적 처치 엽전 공식(economy.enemy_money{' ×보스 15' if boss else ''}) 기준")
        t.fill(r, "kind", kind)
        t.fill(r, "yu_bul_seon_type", FAC.get(t.g(r, "faction"), "none"))
        t.fill(r, "enemy_tier", "BOSS" if boss else ("ELITE" if re.search(r"두목|수괴|사교주|만호|탈영|귀왕", t.g(r, "name_kr")) else "NORMAL"))
        t.fill(r, "boss_tier", tier if boss else "")
        t.fill(r, "combat_scale", G.ENEMIES[gid]["combat_scale"] if gid else (1.2 if boss else 1.25))
        t.fill(r, "element", G.ENEMIES[gid]["element"] if gid else next((e for p, e in ELEM_OF if re.search(p, t.g(r, "name_kr"))),
                                                                          {"human": "metal", "ghost": "yin", "yokai": "wood", "beast": "none", "dragon": "water"}[kind]))
        t.fill(r, "res_json", json.dumps(G.ENEMIES[gid]["res"] if gid else {"ghost": {"metal": 0.4, "holy": -0.4}, "yokai": {"holy": -0.3},
                                                                              "dragon": {"water": 0.5, "wood": -0.2}}.get(kind, {}), ensure_ascii=False))
        t.fill(r, "flee_rate", 0.0 if boss else {1: 0.95, 2: 0.85, 3: 0.8}[tier])
        t.fill(r, "capturable", not boss)
        t.fill(r, "enrage_json", json.dumps({"hp_ratio": 0.3, "atk_mult": 1.25 if tier == 4 else 1.3}) if boss else "")
        cap = str(t.g(r, "capture_tool"))
        if boss:
            t.s(r, "capture_tool", "포획 불가(보스)", "충돌", "게임 규칙: 보스는 포획 불가·도주 불가(flee_boss 0)")
        else:
            m = re.search(r"CAP_(.)_0(\d)", cap)
            want = KIND_CAP[kind]
            if m and m.group(1) != want:
                ct = max(int(m.group(2)), tier)
                newcap = f"CAP_{want}_0{ct}"
                t.s(r, "capture_tool", newcap, "충돌", f"포획 계통은 적 종류로 결정({kind}→{want}) — 원본은 세력({t.g(r, 'faction')}) 기준")
            elif m and int(m.group(2)) < tier:
                t.s(r, "capture_tool", f"CAP_{want}_0{tier}", "밸런스", "포획구 등급이 적 등급보다 낮음")
        drops, miss = [], []
        for d in re.split(r",\s*", str(t.g(r, "item_drops"))):
            d = re.sub(r"\(T\d\)", "", d).strip()
            if not d:
                continue
            ref = resolve_name(idx, d)
            drops.append({"id": ref, "rate": 0.3 if not boss else 1.0} if ref else {"new": d})
            if not ref:
                miss.append(d)
        t.fill(r, "drops_json", json.dumps(drops, ensure_ascii=False))
        t.fill(r, "drops_unresolved", ", ".join(miss))
        regs = regions_in(t.g(r, "spawn_regions"))
        t.fill(r, "spawn_regions_ids", ",".join(regs))
        terr = [k for k, p in TERRAIN_OF if re.search(p, str(t.g(r, "terrain")))] or ["road", "mountain"]
        t.fill(r, "spawn_terrains", ",".join(terr))
        tm = str(t.g(r, "time"))
        t.fill(r, "allowed_time", "NIGHT" if re.search(r"밤|심야|야간|축시|해질녘", tm) and "낮" not in tm else ("DAY" if tm == "낮" else "ANY"))
        cond = [w for w, p in (("rain", r"비|폭풍"), ("fog", r"안개|해무"), ("full_moon", r"보름"), ("new_year", r"설날|정월"), ("winter", r"겨울"),
                               ("eclipse", r"일식"), ("dark_moon", r"그믐")) if re.search(p, tm)]
        t.fill(r, "spawn_conditions_extra", ",".join(cond))
        if "eclipse" in cond or "dark_moon" in cond or "full_moon" in cond:
            issue(t.name, eid, "time", "충돌", tm, "이벤트 트리거로",
                  "게임에 달 모양·일식 시스템 없음 → 해당 인스턴스(14탭) 진입 조건으로만 사용 권장")
        sk_ids = skills_by_owner.get(eid, [])
        if "skills_game" in tn:
            issue(t.name, eid, "skills", "밸런스", ",".join(sk_ids), ",".join(tn["skills_game"]),
                  "DB-15 서술 스킬 변환본으로는 게임 보스 목표(클러치 승률·턴·패배 유도) 미충족 → 게임 튜닝 스킬 사용(서술은 연출용)")
            sk_ids = tn["skills_game"]
        t.fill(r, "skills", ",".join(sk_ids))
        t.fill(r, "game_id", gid)
        if boss:
            node = resolve_node(t.name, eid, t.g(r, "spawn_regions"), t.g(r, "spawn_regions"))
            if node:
                t.fill(r, "lair_node", node["id"])
                if node["region"] not in regs:
                    t.fill(r, "spawn_regions_ids", ",".join(sorted(set(regs) | {node["region"]})))
                    issue(t.name, eid, "spawn_regions", "좌표", t.g(r, "spawn_regions"), f"+{node['region']}",
                          f"보스 거처 노드 {node['name']}는 게임 {node['region']}에 있음 — 출현 권역에 추가")
    issue(t.name, "-", "구성", "보충", "4등급 7종 모두 보스", "4등급 일반 적 없음",
          "Rank 4 필드 조우용 일반 적이 없음(게임은 화산 이무기 새끼·역천 사도) → 게임 행 유지 또는 4등급 일반 적 2~3종 추가 권장")
    return t



# ================================================================ 10 동료
COMP_GAME = {"착호갑사": "cp_chakho", "정약용": "cp_jeongyakyong", "허준": "cp_heojun", "이순신": "cp_yisunsin", "사명대사": "cp_samyeong",
             "서산대사(휴정)": "cp_seosan", "전우치": "cp_jeonuchi", "바리공주": "cp_bari", "보부상(부상)": "cp_bobusang", "김홍도": "cp_kimhongdo",
             "황진이": "cp_hwangjini", "홍길동": "cp_honggildong"}
LIFE_KW = [("nong", r"채집|약초|의학|질병|역병|탕약|치유|회복|식량|수확|농산|육류|음식|부패"), ("gong", r"제작|단조|수리|내구|채광|공방|목공|옹기|축조|방벽|한지|부적|무기|기계"),
           ("sang", r"무역|판매|상점|거래|시세|수수료|금난전|은화|매점|보관함|소지 무게|적재"), ("sa", r"명성|관아|교섭|외교|비석|해독|탐색|감지|안개|시야|지도|은신|경계|탐지|독해")]
ROLE_KW = [("healer", r"힐러|부활|구원|정화"), ("tank", r"탱커|수호|농성|방어|결계"), ("attacker", r"딜러|암살|메이지|돌격|저격|검객|킬러|브루저|버서커|결전")]


def fix_10(skill_ids):
    t = Tab("10_동료_캐릭터_65종")
    ent, meta = [], {}
    for r in t.rows:
        name = t.g(r, "name_kr")
        ent.append((t.g(r, "companion_id"), CP.score(name, t.g(r, "tier"), t.g(r, "category_type"))))
    extra = [g for gid, g in G.COMPANIONS.items() if gid not in COMP_GAME.values() and not g.get("db15_id")]   # 게임에만 있는 동료(남사고·신윤복)
    for g in extra:
        ent.append((g["id"], CP.score(g["name"], g["tier"], "역사 인물")))
    st_t = CP.start_tiers(ent)
    PROMO_ROWS.clear()
    for r in t.rows:
        cid, name = t.g(r, "companion_id"), t.g(r, "name_kr")
        fam = FAC[t.g(r, "faction")]
        gid = COMP_GAME.get(name, "")
        orig = int(t.g(r, "tier"))
        tier = st_t[cid]
        t.s(r, "tier", tier, "충돌", f"시작 등급 1~3 재배치(능력 원래 {orig}등급 + 분류·유명도 점수 {dict(ent)[cid]:.1f} → 3등분). 승급 퀘스트로 최대 5등급")
        t.fill(r, "orig_tier", orig)
        t.fill(r, "start_tier", tier)
        t.fill(r, "max_tier", 5)
        tpl = G.companion_template(tier)
        text = f"{t.g(r, 'passive_exploration_buff')} {t.g(r, 'stat_bonus_json')}"
        hits = [k for k, pt in LIFE_KW if re.search(pt, text)] or ["sa"]
        kn, primary = CP.allocate_knowledge(tier, fam, hits)
        carry = 25 if "보부상" in name else (18 if re.search(r"적재|소지 무게|짐", text) else 8 + 2 * tier)
        if gid:
            carry = G.COMPANIONS[gid]["carry_bonus"]
        role = next((k for k, pt in ROLE_KW if re.search(pt, str(t.g(r, "combat_role")))), "support")
        node = resolve_node(t.name, cid, t.g(r, "spawn_node"), t.g(r, "spawn_map"))
        if node and node["region"] != t.g(r, "spawn_map"):
            t.s(r, "spawn_map", node["region"], "좌표", f"영입 장소 '{t.g(r, 'spawn_node')}' 는 게임 노드 {node['name']}({node['region']})")
        home = node or PARENT.get(cid)
        rc, notes = str(t.g(r, "recruit_condition")), []
        if "민심" in rc:
            rc = re.sub(r"(\S+) 민심 최고치(?: 달성)?", r"\1 도(道) 명성 5단계", rc)
            notes.append("민심 시스템 없음 → 도 명성 단계")
        if notes:
            t.s(r, "recruit_condition", rc, "충돌", " / ".join(notes))
        m = re.match(r"\[(.+?)\]", str(t.g(r, "combat_active_skill")))
        c = {"id": gid or f"cp_{cid.lower().replace('comp_', 'c')}", "db15": cid, "name": name, "start_tier": tier, "family": fam,
             "category": t.g(r, "category_type"), "role_text": t.g(r, "combat_role"), "desc": str(t.g(r, "description")),
             "item": t.g(r, "signature_item"), "skill": m.group(1) if m else "", "home": home, "primary": primary}
        promos = CP.promotions(c)
        PROMO_ROWS.extend(promos)
        route = CP.recruit_route(c["id"], home, tier)
        for k, v in (("family", fam), ("role", role), ("hp", tpl["hp"]), ("atk", tpl["atk"]), ("def", tpl["def"]), ("speed", tpl["speed"]),
                     ("knowledge_add_json", json.dumps(kn, ensure_ascii=False)), ("primary_knowledge", primary),
                     ("knowledge_per_promotion_json", json.dumps({primary: 1})), ("carry_bonus", carry),
                     ("wage_per_day", int(G.WAGE["base"] * G.WAGE["growth"] ** (tier - 1))), ("recruit_min_rank", tier),
                     ("recruit_node", home["id"]), ("recruit_route_json", json.dumps(route)), ("promotion_count", len(promos)),
                     ("skills", ",".join(skill_ids.get(cid, []))), ("game_id", c["id"])):
            t.fill(r, k, v)
        issue(t.name, cid, "passive_exploration_buff", "충돌", t.g(r, "passive_exploration_buff"), f"지식 {kn} · 짐 +{carry}",
              "합의된 동료 규칙(스킬 참전 + 지식 합산 + 짐 무게 가산, 스탯 합산 없음)에 따라 탐험 패시브는 지식 랭크로 환산(지식 합 = 현재 등급). "
              "원문 그대로면 명성 2~3배·시설 비용 -30%·이동 +30% 등이 경제·명성 곡선을 우회")
    for g in extra:  # 게임 전용 동료도 같은 규칙으로 승급 퀘스트 생성
        tier = st_t[g["id"]]
        home = next(n for n in G.NODES if n["id"] == g["recruit"]["route"][-1])
        kn, primary = CP.allocate_knowledge(tier, g["family"], [k for k in g["knowledge_add"] if k not in ("yu", "bul", "seon")] or ["sa"])
        c = {"id": g["id"], "db15": "", "name": g["name"], "start_tier": tier, "family": g["family"], "category": "역사 인물",
             "role_text": g["role"], "desc": "", "item": "", "skill": G.SKILLS[g["skills"][0]]["name"], "home": home, "primary": primary}
        PROMO_ROWS.extend(CP.promotions(c))
        EXTRA_COMP[g["id"]] = {"start_tier": tier, "knowledge_add": kn, "primary": primary, "route": CP.recruit_route(g["id"], home, tier)}
        issue(t.name, g["id"], "행 추가", "보충", "", f"{g['name']} 시작 {tier}등급",
              "게임 13_companions 에만 있는 동료 — 같은 규칙으로 시작 등급·승급 퀘스트 생성(65+2=67명)")
    dist = {k: sum(1 for v in st_t.values() if v == k) for k in (1, 2, 3)}
    issue(t.name, "-", "tier", "충돌", "원본 2~5등급", f"시작 1등급 {dist[1]} · 2등급 {dist[2]} · 3등급 {dist[3]}명",
          f"전원 1~3등급 시작 + 승급 퀘스트 {len(PROMO_ROWS)}건으로 최대 5등급")
    issue(t.name, "-", "stat_bonus_json", "충돌", "atk·def·crit 등 합산 스탯", "무시(지식·짐으로만 환산)", "동료 통합 전투: 동료 스탯은 주인공에 합산하지 않음")
    issue(t.name, "COMP_22", "name_kr", "고증", "채규서", "실존 확인 불가", "가상 인물이면 category_type 을 '가상 인물'로 표기 권장")
    issue(t.name, "COMP_01", "faction", "고증", "불(佛)", "무(無) 권장", "착호갑사는 군사 직업 — 게임 cp_chakho 도 무속성")
    return t


# ================================================================ 11 스킬
CLASS_AFF = {"A": "yu", "M": "yu", "D": "seon"}
CLASS_GAME = {"SKL_CLASS_A01": "sk_eosa_mapae", "SKL_CLASS_M02": "sk_mer_coin", "SKL_CLASS_D03": "sk_dosa_thunder", "SKL_CLASS_D01": "sk_dosa_ward"}
LIFE_MAIN = {"SKL_MAIN_P01": "sa", "SKL_MAIN_P02": "nong", "SKL_MAIN_P03": "gong", "SKL_MAIN_P04": "sang"}


def fix_11(t09, t10):
    t = Tab("11_전체스킬_통합_346종")
    etier = {t09.g(r, "enemy_id"): (int(t09.g(r, "tier")), FAC[t09.g(r, "faction")]) for r in t09.rows}
    ctier = {t10.g(r, "companion_id"): (int(t10.g(r, "tier")), FAC[t10.g(r, "faction")]) for r in t10.rows}
    by_owner = {}
    for c in ("owner_game", "target_game", "ap_cost", "power", "element", "affinity", "cooldown", "effects_json", "effect_game", "변환메모", "game_id"):
        t.add(c)
    for r in t.rows:
        sid, eff = t.g(r, "skill_id"), str(t.g(r, "effect"))
        conv = None
        if sid.startswith("SKL_CLASS"):
            ap = re.search(r"AP (\d)", eff)
            conv = SC.convert(eff, "hero", 3, CLASS_AFF[sid[10]], ap_hint=ap.group(1) if ap else None)
            if "패시브" in str(t.g(r, "type")):
                conv = ({"owner": "passive", "target": "self", "ap_cost": 0, "power": 0.0, "element": "none", "affinity": "none", "cooldown": 0,
                         "effects": {"passive": {"money_gain": 0.1, "drop_rate": 0.1}}}, ["엽전 +40%·드롭 1.5배 → +10%·+10%"])
            t.fill(r, "game_id", CLASS_GAME.get(sid, ""))
        elif sid.startswith("SKL_COMP") and sid.endswith("ACT"):
            cid = sid[4:11]
            _, fam = ctier[cid]
            conv = SC.convert(eff, "companion", 3, fam)   # 3등급 기준 수치 — 실제 위력은 현재 등급 숙련 배율(1등급 0.84 ~ 5등급 1.16)로
            by_owner.setdefault(cid, []).append(sid)
        elif sid.startswith("SKL_ENM"):
            eid = sid[4:11]
            tier, fam = etier[eid]
            conv = SC.convert(eff, "enemy", tier, fam, is_boss=tier >= 4)
            by_owner.setdefault(eid, []).append(sid)
        elif sid.startswith("SKL_CAP"):
            fam = CAP_GAME[sid[8]]
            conv = ({"owner": "capture", "target": "enemy", "ap_cost": 2, "power": 0.0, "element": "none", "affinity": "none", "cooldown": 0,
                     "effects": {"capture_family": fam, "capture_item": f"cap_{fam}_{sid[-1]}"}}, [f"게임 공용 스킬 sk_cap_{fam} + 포획구 등급"])
            t.fill(r, "game_id", f"sk_cap_{fam}")
        elif sid in LIFE_MAIN:
            k = LIFE_MAIN[sid]
            conv = ({"owner": "passive", "target": "self", "ap_cost": 0, "power": 0.0, "element": "none", "affinity": "none", "cooldown": 0,
                     "effects": {"life_knowledge": k, "per_rank": G.CK["life_effects"][k]}},
                    [f"원문 수치는 생활 지식 5랭크 누적값에 해당 — 게임 life_effects.{k}(랭크당) 로 연결"])
        else:
            owner = "life_gear" if sid.startswith("SKL_TOOL") else ("mount" if sid.startswith("SKL_MNT") else "passive")
            conv = ({"owner": owner, "target": "field", "ap_cost": 0, "power": 0.0, "element": "none", "affinity": "none", "cooldown": 0, "effects": {}},
                    ["필드/탐험 효과 — 수치는 03·04·10 탭 변환 열 참조"])
        sk, notes = conv
        vals = {"owner_game": sk["owner"], "target_game": sk["target"], "ap_cost": sk["ap_cost"], "power": sk["power"], "element": sk["element"],
                "affinity": sk["affinity"], "cooldown": sk["cooldown"], "effects_json": json.dumps(sk.get("effects", {}), ensure_ascii=False),
                "effect_game": SC.describe(sk) if sk["target"] != "field" else "필드 효과", "변환메모": " / ".join(notes)}
        for k, v in vals.items():
            t.fill(r, k, v)
        if notes and sk["target"] != "field" and any(re.search(r"상한|치환|→", n) for n in notes):
            issue(t.name, sid, "effect", "밸런스", eff, vals["effect_game"], vals["변환메모"])
    issue(t.name, "-", "메인 스킬", "보충", "클래스 4종 모두 AP 1~4 특수기", "1AP 기본 공격 없음",
          "게임은 클래스마다 1AP 기본기(일격·주판 치기·철선 타격, 턴당 1회)가 있어야 AP 소진 계산이 성립 → 게임 기본기 유지")
    issue(t.name, "-", "effect(서술형)", "스키마", "자유 서술", "ap_cost·power·effects_json 열 추가",
          "원본 스킬은 수치 필드가 없어 엔진이 읽을 수 없음 → 14_skills 스키마로 변환(원문은 보존)")
    return t, by_owner



# ================================================================ 12 비전서
BOOK_GAME = {"BOOK_COOK_01": "bk_food_jumak", "BOOK_COOK_02": "bk_food_gaekju", "BOOK_COOK_03": "bk_food_namdo", "BOOK_COOK_04": "bk_food_bukgwan",
             "BOOK_COOK_05": "bk_food_campfire", "BOOK_COOK_06": "bk_food_sura", "BOOK_MED_01": "bk_med_dongui", "BOOK_MED_02": "bk_med_jeonju",
             "BOOK_MED_03": "bk_med_hyemin", "BOOK_MED_04": "bk_med_daegu", "BOOK_MED_05": "bk_med_temple", "BOOK_TOOL_01": "bk_tool_repair",
             "BOOK_TOOL_02": "bk_tool_carpenter", "BOOK_TOOL_03": "bk_tool_gongbang", "BOOK_TOOL_04": "bk_tool_forge", "BOOK_TOOL_05": "bk_tool_capture",
             "BOOK_WEAP_01": "bk_mar_hwando", "BOOK_WEAP_02": "bk_mar_armor", "BOOK_WEAP_03": "bk_mar_bow", "BOOK_WEAP_04": "bk_mar_boots",
             "BOOK_WEAP_05": "bk_mar_charm", "BOOK_WEAP_06": "bk_mar_spear", "BOOK_WEAP_07": "bk_mar_shield", "BOOK_WEAP_08": "bk_mar_flail"}
MOJAK_BOOK = {"BOOK_WEAP_04": ("유(儒)", 4), "BOOK_WEAP_05": ("불(佛)", 4), "BOOK_WEAP_06": ("선(仙)", 4), "BOOK_WEAP_07": ("유(儒)", 5),
              "BOOK_WEAP_08": ("선(仙)", 5), "BOOK_WEAP_09": ("불(佛)", 5)}
BOOK_FAC = [("주막|객주", "jumak"), ("서책방|상설전|서고|관상감|서운관", "bookstore"), ("약방", "yakbang"), ("약령시|약재상", "yakryeongsi"),
            ("혜민서|약전", "hyeminseo"), ("대장간|철물점", "forge"), ("공방|목공소", "gongbang"), ("숙수관|행궁|소주방", "restaurant")]


def fix_12(tabs):
    t = Tab("12_제작비전서_24종")
    names = {}
    for tn, idc in (("08_음식_레시피_18종", "recipe_id"), ("06_한방약_레시피_15종", "med_id"), ("03_생활행장_30종", "tool_id"), ("02_기초생필품_제작_44종", "item_id")):
        tt = tabs[tn]
        for r in tt.rows:
            nm = tt.g(r, "food_name") if tn.startswith("08") else tt.g(r, "name_kr")
            names[G.norm(nm)] = (tt.g(r, idc), int(num(tt.g(r, "tier"), 1)))
    row = [""] * len(t.header)
    for col, v in (("book_id", "BOOK_WEAP_09"), ("name_kr", "《사명당 금강 병기도》"), ("category", "무예 단조서"), ("tier", 5),
                   ("shop_facility", "불(佛) 5등급 장비 판매 시 해금 또는 아랑사령 격파"), ("buy_price", ""), ("sell_price", 0),
                   ("unlocks", "[모작] 사명당 벽사 금강저 검, 통도사 금란 가사갑, 금강보타 연화 운혜, 화엄 만다라 108 보리수염주 해금"),
                   ("desc", "보충: 불(佛) 5등급 모작 세트(13탭 CRAFT_EQ_13~16)를 해금하는 비전서가 없었음")):
        row[t.ci(col)] = v
    t.rows.append(row)
    issue(t.name, "BOOK_WEAP_09", "행 추가", "보충", "", "불 5등급 모작 비전서", "13탭 CRAFT_EQ_13~16 을 해금하는 비전서 없음(유·선 5등급은 07·08)")
    craft = tabs["13_고유제작_전투장착_24종"]
    for r in t.rows:
        bid, tier, cat = t.g(r, "book_id"), int(num(t.g(r, "tier"), 1)), str(t.g(r, "category"))
        if bid in MOJAK_BOOK:
            fac, ct = MOJAK_BOOK[bid]
            ids = [craft.g(c, "craft_id") for c in craft.rows if craft.g(c, "faction") == fac and int(craft.g(c, "tier")) == ct]
        else:
            ids = []
            for part in re.split(r",\s*|\s등\s", re.sub(r"(등 )?\d티어.*$|해금$", "", str(t.g(r, "unlocks")))):
                hit = next((v for k, v in names.items() if G.norm(part) and (G.norm(part) in k or k in G.norm(part)) and len(G.norm(part)) >= 2), None)
                if hit:
                    ids.append(hit[0])
                    if hit[1] > tier:
                        issue(t.name, bid, "unlocks", "충돌", f"{part}(T{hit[1]})", f"책 T{tier}", "책보다 높은 등급 레시피 해금")
        t.fill(r, "unlock_ids", ",".join(dict.fromkeys(ids)))
        if not ids and not bid.startswith("BOOK_WEAP_0") or (bid in ("BOOK_WEAP_01", "BOOK_WEAP_02", "BOOK_WEAP_03") and not ids):
            t.fill(r, "unlock_ids", {"BOOK_WEAP_01": "eq_w2_hwando,eq_a1_cheollik", "BOOK_WEAP_02": "eq_w3_byeolungeom,eq_a2_dujeonggap",
                                     "BOOK_WEAP_03": "eq_w3_hwaseon"}.get(bid, ""))
        if "무예" in cat:
            t.fill(r, "acquire", "quest_or_drop")
            if str(t.g(r, "buy_price")) in ("-1", "-1.0"):
                t.s(r, "buy_price", "", "스키마", "-1 은 숫자 칸의 누락 표기 → 빈칸 + acquire=quest_or_drop")
            if num(t.g(r, "sell_price")) > 0:
                t.s(r, "sell_price", 0, "충돌", "무예 단조서는 소지해야 모작이 해금되는 귀속 아이템(판매 시 해금 상실) → 판매 불가")
        else:
            t.fill(r, "acquire", "shop")
            t.s(r, "sell_price", sell_of(num(t.g(r, "buy_price"))), "밸런스", "", log=False)
        shop = str(t.g(r, "shop_facility"))
        t.fill(r, "facility", next((f for p, f in BOOK_FAC if re.search(p, shop)), ""))
        t.fill(r, "regions", ",".join(regions_in(shop)) or "*")
        t.fill(r, "game_id", BOOK_GAME.get(bid, ""))
    tools = tabs["03_생활행장_30종"]
    covered = set(",".join(t.g(r, "unlock_ids") for r in t.rows).split(","))
    shop_only = [tools.g(r, "tool_id") for r in tools.rows if tools.g(r, "tool_id") not in covered]
    issue(t.name, "BOOK_TOOL_*", "unlocks", "보충", "", ", ".join(shop_only),
          "도구 제작서가 해금하지 않는 행장 — '상점 전용(제작 불가)'으로 명시하거나 제작서 해금 목록에 추가")
    issue(t.name, "BOOK_TOOL_01", "unlocks", "충돌", "무쇠 낫", "02탭 BASE_0005(생필품)", "행장이 아닌 생필품을 '1티어 행구'로 해금 — 생필품 제작 레시피로 분리")
    issue(t.name, "-", "game_id", "충돌", "게임 비전서 24종(권역별 구성)", "DB-15 24종(등급별 구성)",
          "권수는 같으나 구성 기준이 다름 → 병합 시 DB-15 구성 채택, 게임 음식·탕약의 book 필드를 unlock_ids 기준으로 재지정")
    return t


# ================================================================ 13 모작
SLOT = {"MAIN_HAND": "weapon", "BODY": "armor", "FEET": "shoes", "ACCESSORY": "accessory"}
SPECIAL = [(r"치명타", {"crit": 0.05}), (r"요마|악귀|신성|요괴", {"damage_vs": {"yokai": 0.1, "ghost": 0.1}}), (r"피해 \d+% ?(?:감소|반감|감면)|반감", {"res_all": 0.04}),
           (r"선제|첫 턴", {"gauge_start": 200}), (r"회피", {"def_pct": 0.04}), (r"포획", {"capture_rate": 0.1}), (r"평판|명성", {"reputation_gain": 0.05}),
           (r"재생|회복", {"regen_pct_per_turn": 0.02}), (r"이동|스태미나|감속|도하|험로|활공", {"fatigue_gain": -0.05}), (r"연쇄|벼락|감전", {"status_on_hit": {"id": "stun", "chance": 0.08}}),
           (r"저주|상태이상", {"res_all": 0.04}), (r"맹수", {"field_encounter_mult": {"beast": 0.7}})]


def fix_13(idx):
    t = Tab("13_고유제작_전투장착_24종")
    for r in t.rows:
        fam, slot, tier = FAC[t.g(r, "faction")], SLOT[t.g(r, "slot_type")], int(t.g(r, "tier"))
        gid = f"mj_{fam}_{slot}_{tier}"
        g = G.MOJAK[gid]
        s = g["stats"]
        new = {"atk": s.get("atk", 0), "def": s.get("def", 0), "speed": s.get("spd", 0), "hp_bonus": s.get("hp", 0)}
        for k, v in new.items():
            t.s(r, k, v, "밸런스", (f"게임 {gid}(원본 {g['original']}의 {int(g['ratio']*100)}%) 스탯 — 원본 수치는 주인공 HP 상한 250·"
                                   f"5등급 원본 무기 ATK 45~50 대비 약 3배(무기 {t.g(r, 'atk')}·HP +{t.g(r, 'hp_bonus')})") if k == "atk" else "", log=(k == "atk"))
        t.fill(r, "res", s.get("res", 0))
        t.s(r, "craft_req_rank", f"Rank {g['min_rank']}", "충돌", f"게임 모작 min_rank={g['min_rank']} — Rank 4 해금(tier4) 구조·보스 시뮬 세팅 기준. 원본은 1단계 낮음")
        mats, miss = [], []
        for name, q, _ in parse_ingredients(t.g(r, "base_materials")):
            ref = resolve_name(idx, name)
            (mats.append({"id": ref, "qty": q}) if ref else miss.append(name))
        for m in miss:
            issue(t.name, t.g(r, "craft_id"), "base_materials", "참조", m, "", "재료 미등록")
        fx = {}
        for p, v in SPECIAL:
            if re.search(p, str(t.g(r, "special_effect"))):
                fx.update(v)
        t.fill(r, "materials_json", json.dumps(mats, ensure_ascii=False))
        t.fill(r, "special_json", json.dumps(fx, ensure_ascii=False))
        t.fill(r, "slot_game", slot)
        t.fill(r, "element", g["element"])
        t.fill(r, "game_id", gid)
        t.fill(r, "book", {("yu", 4): "BOOK_WEAP_04", ("bul", 4): "BOOK_WEAP_05", ("seon", 4): "BOOK_WEAP_06", ("yu", 5): "BOOK_WEAP_07",
                           ("seon", 5): "BOOK_WEAP_08", ("bul", 5): "BOOK_WEAP_09"}[(fam, tier)])
        if t.g(r, "name_kr").replace("[모작] ", "") != g["name"].replace("[모작] ", ""):
            issue(t.name, t.g(r, "craft_id"), "name_kr", "충돌", f"게임 {g['name']}", t.g(r, "name_kr"), "같은 슬롯·계열·등급인데 이름 다름 → 병합 시 DB-15 이름 채택")
        issue(t.name, t.g(r, "craft_id"), "special_effect", "밸런스", t.g(r, "special_effect"), json.dumps(fx, ensure_ascii=False), "서술 효과 → 소폭 수치(모작은 원본의 75%)")
    return t


# ================================================================ 14 인스턴스
MG = [("씨름|일기토|백병|결박|호통", "ssireum"), ("궁술|사격|쇠뇌|활", "archery"), ("팔괘|진법", "bagua"), ("진언|리듬|가무", "rhythm")]
GENERIC_ENEMY = {"정예 화적": "ENM_002", "정예 침투조": "ENM_009", "흑천 사령": "ENM_026", "정예 사령 호위대": "ENM_026", "정예 마수": "ENM_028",
                 "사교 결사대 장수": "ENM_024", "조총 왜구": "ENM_018", "초립동이 도둑": "ENM_001", "수살귀": "ENM_007", "도굴꾼": "ENM_010"}


OVER_TIER_SWAP = {"ENM_029": "ENM_018", "ENM_026": "ENM_015", "ENM_030": "ENM_020", "ENM_024": "ENM_016", "ENM_027": "ENM_016", "ENM_021": "ENM_017"}
MID_BOSS_SWAP = {"ENM_035": "ENM_021", "ENM_037": "ENM_030", "ENM_034": "ENM_015", "ENM_036": "ENM_029", "ENM_031": "ENM_021",
                 "ENM_032": "ENM_025", "ENM_033": "ENM_023"}


def parse_wave(text, enames):
    out, unresolved = [], []
    for part in re.split(r",\s*|\s\+\s", str(text)):
        part = part.strip()
        if not part:
            continue
        q = re.search(r"x\s*(\d+)|(\d+)체", part)
        n = int(next(g for g in q.groups() if g)) if q else 1
        m = re.search(r"ENM_\d{3}", part)
        eid = m.group(0) if m else next((v for k, v in GENERIC_ENEMY.items() if k in part), None)
        if not eid:
            nm = G.norm(re.sub(r"x\s*\d+|\d+체|\(.*?\)", "", part))
            eid = next((k for k, v in enames.items() if nm and nm in v), None)
        (out.extend([eid] * n) if eid else unresolved.append(part))
    return out, unresolved


def fix_14(t09, idx):
    t = Tab("14_탐색_미니게임_연속전투")
    enames = {t09.g(r, "enemy_id"): G.norm(t09.g(r, "name_kr")) for r in t09.rows}
    etier = {t09.g(r, "enemy_id"): int(t09.g(r, "tier")) for r in t09.rows}
    etype = {t09.g(r, "enemy_id"): t09.g(r, "enemy_tier") for r in t09.rows}
    for r in t.rows:
        wid = t.g(r, "instance_id")
        gi = G.INSTANCES[wid]
        tier = gi["tier"]
        cols = ["wave_1_enemies", "wave_2_enemies", "wave_3_enemies", "wave_3_boss", "wave_4_boss"]
        waves = []
        for c in cols:
            if str(t.g(r, c)).strip():
                w, un = parse_wave(t.g(r, c), enames)
                for u in un:
                    issue(t.name, wid, c, "참조", u, "", "적 목록(09탭)에서 찾을 수 없음")
                final = c in ("wave_3_boss", "wave_4_boss") or (c == "wave_3_enemies" and not str(t.g(r, "wave_4_boss")).strip())
                if tier <= 3:
                    down = [OVER_TIER_SWAP.get(e, e) if etier.get(e, 0) > tier else e for e in w]
                    if down != w:
                        issue(t.name, wid, c, "밸런스", ",".join(w), ",".join(down),
                              f"T{tier} 인스턴스에 T{max(etier.get(e, 0) for e in w)} 정예 — 같은 계열 T{tier} 정예로(권역 보스가 없는 저등급 인스턴스는 등급 이내)")
                        w = down
                if not final:
                    swapped = [MID_BOSS_SWAP.get(e, e) if etier.get(e, 0) >= 4 else e for e in w]
                    if swapped != w:
                        issue(t.name, wid, c, "밸런스", ",".join(w), ",".join(swapped),
                              "중간 웨이브의 4등급 보스(HP 2,000대) → 같은 계열 3등급 정예로(HP 이월 규칙상 최종 보스 전 소진)")
                        w = swapped
                cap_elite = 2 if final else (0 if tier <= 2 else 1)
                elites = [i for i, e in enumerate(w) if etype.get(e) == "ELITE"]
                if len(elites) > cap_elite:
                    filler = next((e for e in w if etype.get(e) == "NORMAL"), waves[0][0] if waves else w[0])
                    nw = list(w)
                    for i in elites[cap_elite:]:
                        nw[i] = filler
                    issue(t.name, wid, c, "밸런스", ",".join(w), ",".join(nw),
                          f"정예(두목급)는 {'최종' if final else '중간'} 웨이브당 {cap_elite}마리까지(T2 이하 인스턴스는 중간 웨이브 정예 없음) — 초과분은 같은 무리의 일반 적으로")
                    w = nw
                if len(w) > 3:
                    kinds = list(dict.fromkeys(w))
                    rr, i = [], 0
                    while len(rr) < 3:
                        k = kinds[i % len(kinds)]
                        if w.count(k) > rr.count(k):
                            rr.append(k)
                        i += 1
                    issue(t.name, wid, c, "밸런스", f"{len(w)}마리 ({','.join(w)})", f"3마리 ({','.join(rr)})",
                          "동료 통합 전투는 주인공 1명이 모든 공격을 받음 — 웨이브당 최대 3마리(게임 인스턴스 규격). 4~5마리면 T2 인스턴스 클리어율 0%")
                    w = rr
                waves.append(w)
        if int(t.g(r, "wave_count")) != len(waves):
            issue(t.name, wid, "wave_count", "스키마", t.g(r, "wave_count"), len(waves), "웨이브 열 개수와 불일치")
        t.fill(r, "waves_json", json.dumps(waves))
        t.fill(r, "boss", waves[-1][0] if waves and etier.get(waves[-1][0], 0) >= 4 else "")
        over = [e for w in waves[:-1] for e in w if etier.get(e, 0) > tier]
        if over:
            issue(t.name, wid, "waves", "밸런스", ",".join(sorted(set(over))), f"인스턴스 T{tier}",
                  "보스 전 웨이브에 인스턴스 등급보다 높은 적 — 결전 전 소모가 과도(게임은 같은/낮은 등급 잡몹)")
        t.fill(r, "tier", tier)
        t.fill(r, "minigame", next((g for p, g in MG if re.search(p, str(t.g(r, "minigame_type")))), ""))
        fl = str(t.g(r, "flee_allowed"))
        t.fill(r, "flee_bool", fl.upper().startswith("TRUE"))
        t.fill(r, "flee_note", re.sub(r"^(TRUE|FALSE)\s*", "", fl, flags=re.I).strip("() "))
        rep, money = G.quest_reward(tier, "instance")
        cr = str(t.g(r, "clear_reward"))
        m = re.search(r"명성 \+([\d,]+), 엽전 ([\d,]+)냥", cr)
        if m:
            new = cr.replace(m.group(0), f"명성 +{int(rep):,}, 엽전 {int(money):,}냥")
            t.s(r, "clear_reward", new, "밸런스",
                f"보상 자동 공식(quest type=instance, T{tier}) — 원본 합계 명성 20,600·엽전 28,950 은 공식의 약 2배·3배라 신분 임계·도 명성 요건이 틀어짐(처치 보상은 별도 지급)")
        if wid == "WAVE_003" and "BOOK_MED_05" in cr:
            t.s(r, "clear_reward", t.g(r, "clear_reward").replace("《동의보감》 단선비결(BOOK_MED_05)", "《제중신편》(BOOK_MED_03)"), "밸런스",
                "3등급 인스턴스가 5등급 의약서(3,500냥)를 줌 → 3등급 의약서")
        items = []
        for tok in re.split(r",\s*", re.sub(r"명성 \+[\d,]+, 엽전 [\d,]+냥,?\s*", "", t.g(r, "clear_reward"))):
            b = re.search(r"BOOK_\w+", tok)
            ref = b.group(0) if b else resolve_name(idx, re.sub(r"\[|\]|국보|전설 재료|\d+점", "", tok))
            items.append({"id": ref} if ref else {"new": tok.strip()})
        t.fill(r, "reward_rep", rep)
        t.fill(r, "reward_money", money)
        t.fill(r, "reward_items_json", json.dumps(items, ensure_ascii=False))
        node = resolve_node(t.name, wid, t.g(r, "region_node"), t.g(r, "region_node"))
        t.fill(r, "region_game", node["region"] if node else "")
        t.fill(r, "node_game", node["id"] if node else "")
        t.fill(r, "game_id", wid)
    issue(t.name, "WAVE_006~008", "wave_3_boss·wave_3_enemies·wave_4_boss", "스키마", "4웨이브는 wave_3_boss 를 비우고 뒤 두 열 사용",
          "waves_json(웨이브 배열)+boss 열로 통일", "3·4웨이브 인스턴스의 열 의미가 행마다 다름")
    return t



# ================================================================ 공통 스키마 점검(원본 기준)
ID_FMT = {"01": ("item_id", r"^FOOD_\d{4}$"), "02": ("item_id", r"^BASE_\d{4}$"), "03": ("tool_id", r"^TOOL_\d{3}$"), "04": ("mount_id", r"^MNT_\d{3}$"),
          "05": ("item_id", r"^CAP_[유불선무]_0\d$"), "06": ("med_id", r"^MED_\d{4}$"), "07": ("herb_id", r"^HERB_\d{3}$"), "08": ("recipe_id", r"^RECIPE_FOOD_\d{3}$"),
          "09": ("enemy_id", r"^ENM_\d{3}$"), "10": ("companion_id", r"^COMP_\d{2}$"), "11": ("skill_id", r"^SKL_"), "12": ("book_id", r"^BOOK_[A-Z]+_\d{2}$"),
          "13": ("craft_id", r"^CRAFT_EQ_\d{2}$"), "14": ("instance_id", r"^WAVE_\d{3}$")}


def schema_check():
    for name, rows in RAW.items():
        key = name[:2]
        if key == "00":
            for r in rows[1:]:
                tab = r[1]
                if tab in RAW and tab != name and int(num(r[3])) != len(RAW[tab]) - 1:
                    issue(name, r[0], "항목수", "스키마", r[3], len(RAW[tab]) - 1, "탭 실제 행 수와 불일치")
            continue
        head, body = rows[0], rows[1:]
        col, pat = ID_FMT[key]
        ci = head.index(col)
        seen = {}
        for r in body:
            v = str(r[ci])
            if not re.match(pat, v):
                issue(name, v, col, "스키마", v, "", f"ID 형식({pat}) 불일치")
            seen[v] = seen.get(v, 0) + 1
            if "tier" in head:
                tv = r[head.index("tier")]
                if not (isinstance(tv, (int, float)) and 1 <= tv <= 5):
                    issue(name, v, "tier", "스키마", tv, "", "등급은 1~5 정수")
            if "buy_price" in head and "sell_price" in head:
                b, s = r[head.index("buy_price")], r[head.index("sell_price")]
                if isinstance(b, (int, float)) and isinstance(s, (int, float)) and b >= 0 and s > b:
                    issue(name, v, "sell_price", "밸런스", s, "", "판매가 > 구매가(무한 차익)")
            for c, val in zip(head, r):
                for mid in MAP_RE.findall(str(val)):
                    if mid not in G.REGIONS:
                        issue(name, v, c, "참조", mid, "", "없는 권역 ID")
        for v, n in seen.items():
            if n > 1:
                issue(name, v, col, "스키마", f"{n}회", "", "ID 중복")
    # 이름 중복(탭 간)
    names = {}
    for name, rows in RAW.items():
        if "name_kr" in rows[0]:
            ci = rows[0].index("name_kr")
            for r in rows[1:]:
                names.setdefault(G.norm(r[ci]), []).append(f"{name[:2]}:{r[0] if name[:2] != '02' else r[4]}")
    for k, v in names.items():
        if len(v) > 1 and len({x[:2] for x in v}) > 1 and k:
            issue("공통", ",".join(v), "name_kr", "참조", k, "", "탭 간 같은 이름 — 같은 아이템인지(ID 통합) 별개인지 확인")


# ================================================================ 실행
def main():
    schema_check()
    raw11 = RAW["11_전체스킬_통합_346종"]
    skills_by = {}
    for r in raw11[1:]:
        m = re.match(r"SKL_(ENM_\d{3}|COMP_\d{2})_", r[0])
        if m and not r[0].endswith("PAS"):
            skills_by.setdefault(m.group(1), []).append(r[0])
    tabs = {}
    tabs["01_식량_구황_수렵_105종"] = fix_01()
    tabs["02_기초생필품_제작_44종"] = fix_02()
    tabs["03_생활행장_30종"] = fix_03()
    tabs["04_탈것_35종_퀘스트"] = fix_04()
    tabs["05_포획구_20종"] = fix_05()
    tabs["07_약초재료_26종"] = fix_07()
    tabs["06_한방약_레시피_15종"] = fix_06(tabs["07_약초재료_26종"])
    tabs["12_제작비전서_24종"] = Tab("12_제작비전서_24종")   # 이름 인덱스용 임시
    idx = build_name_index(tabs)
    tabs["08_음식_레시피_18종"] = fix_08(idx)
    tabs["10_동료_캐릭터_65종"] = fix_10(skills_by)
    tabs["09_조선설화_적목록_42종"] = fix_09(idx, skills_by)
    t11, _ = fix_11(tabs["09_조선설화_적목록_42종"], tabs["10_동료_캐릭터_65종"])
    tabs["11_전체스킬_통합_346종"] = t11
    tabs["13_고유제작_전투장착_24종"] = fix_13(idx)
    tabs["12_제작비전서_24종"] = fix_12(tabs)
    tabs["14_탐색_미니게임_연속전투"] = fix_14(tabs["09_조선설화_적목록_42종"], idx)
    t00 = Tab("00_총괄개요")
    for r in t00.rows:
        if r[1] in tabs:
            t00.s(r, "항목수", len(tabs[r[1]].rows), "보충", "보충 행 반영", log=False)
    # ---- 출력
    order = ["00_총괄개요"] + [n for n in RAW if n != "00_총괄개요"]
    tabs["00_총괄개요"] = t00
    sheets, marks = [], {}
    for n in order:
        t = tabs[n]
        sheets.append((n, t.out()))
        marks[n] = {"changed": t.changed, "added_from": t.n_orig}
    cats = ["오류", "충돌", "밸런스", "참조", "스키마", "좌표", "보충", "고증"]
    ISSUES.sort(key=lambda x: (x["탭"], cats.index(x["분류"]) if x["분류"] in cats else 99))
    ih = list(ISSUES[0].keys())
    sheets.append(("15_점검결과", [ih] + [[str(i[k]) for k in ih] for i in ISSUES]))
    ph = ["id", "동료", "승급 등급", "퀘스트명", "서사", "트리거(시작 장소)", "필요 신분", "필요 조건", "동선", "단계", "보상 명성", "보상 엽전", "승급 효과"]
    nm = lambda nid: next((n["name"] for n in G.NODES if n["id"] == nid), nid)
    cname = {c["id"]: c["name"] for c in G.COMPANIONS.values()}
    cname.update({q["companion"]: q["name"].split("]")[0][1:] for q in PROMO_ROWS})
    prow = [[q["id"], cname[q["companion"]], q["tier"], q["name"], q["lore"], nm(q["trigger_node"]), f"Rank {q['min_rank']}",
             "동행 + " + ", ".join(f"{CP.LIFE.get(k, k)} 지식 {v}" for k, v in q["requires"]["knowledge"].items()),
             " → ".join(nm(x) for x in q["route"]), "\n".join(q["steps"]), q["reward_rep"], q["reward_money"], q["effect"]] for q in PROMO_ROWS]
    sheets.append(("17_동료승급퀘스트", [ph] + prow))
    nh = list(NODE_REFS[0].keys())
    sheets.append(("16_노드참조_좌표", [nh] + [[x[k] for k in nh] for x in NODE_REFS]))
    summ = [["분류", "건수"]] + [[c, sum(1 for i in ISSUES if i["분류"] == c)] for c in cats]
    summ += [["", ""], ["탭", "건수"]] + [[n, sum(1 for i in ISSUES if i["탭"] == n)] for n in order + ["공통"]]
    summ += [["", ""], ["노드 참조 판정", "건수"]] + [[j, sum(1 for x in NODE_REFS if x["판정"] == j)] for j in sorted({x["판정"] for x in NODE_REFS})]
    sheets.insert(1, ("점검요약", summ))
    xlsx_io.write(DB / "DB15_수정본.xlsx", sheets, marks=marks)
    (DB / "issues.json").write_text(json.dumps(ISSUES, ensure_ascii=False, indent=1), encoding="utf-8")
    export = {}
    for n in order[1:]:
        t = tabs[n]
        recs = []
        for r in t.rows:
            d = {}
            for h, v in zip(t.header, r):
                if isinstance(v, str) and h.endswith("_json") and v:
                    v = json.loads(v)
                d[h] = v
            recs.append(d)
        export[n] = recs
    export["_node_refs"] = NODE_REFS
    export["_promotions"] = PROMO_ROWS
    export["_extra_companions"] = EXTRA_COMP
    (DB / "db15_game.json").write_text(json.dumps(export, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"점검 {len(ISSUES)}건 · 노드 참조 {len(NODE_REFS)}건")
    for row in summ[1:]:
        if row[0]:
            print("  ", row[0], row[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
