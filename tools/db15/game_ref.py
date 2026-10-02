"""게임 데이터(data/*.json)에서 DB-15 점검·수정의 기준값을 뽑는다. 수치는 모두 여기서만 읽는다(하드코딩 금지 원칙)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def load(n):
    return json.loads((DATA / n).read_text(encoding="utf-8"))


OV = load("00_overview.json")
ECO = OV["economy"]
TRADE = OV["trade"]
BATTLE = OV["battle"]
MOVE = OV["movement"]
REG = load("regions.json")
REGIONS = {r["id"]: r for r in REG["regions"]}
NODES = REG["nodes"]
HERITAGE = load("01_heritage.json")["heritage"]
ENEMIES = {e["id"]: e for e in load("12_enemies.json")["enemies"]}
COMPANIONS = {c["id"]: c for c in load("13_companions.json")["companions"]}
SKILLS = {s["id"]: s for s in load("14_skills.json")["skills"]}
MOJAK = {m["id"]: m for m in load("16_mojak_gear.json")["mojak"]}
MOUNTS = {m["id"]: m for m in load("07_mounts.json")["mounts"]}
CAPTURE = {c["id"]: c for c in load("08_capture_tools.json")["tools"]}
FOODS = {f["id"]: f for f in load("04_food_staples.json")["foods"]}
MATERIALS = {m["id"]: m for m in load("05_materials.json")["materials"]}
HERBS = {h["id"]: h for h in load("10_herbs.json")["herbs"]}
SPECIALTIES = {s["id"]: s for s in load("03_specialties.json")["specialties"]}
BOOKS = {b["id"]: b for b in load("15_recipe_books.json")["books"]}
INSTANCES = {i["id"]: i for i in load("17_instances.json")["instances"]}
STATUS_IDS = {s["id"] for s in load("18_status_effects.json")["battle"]}
CK = load("19_classes_knowledge.json")
RANK_TABLE = OV["rank"]["table"]

MAP_IDS = sorted(REGIONS)
_NODE_REG = {n["id"]: n["region"] for n in NODES}
SEA_ADJ = {}
for _s in REG["sea_routes"]:
    _a, _b = _NODE_REG[_s["a"]], _NODE_REG[_s["b"]]
    if _a != _b:
        SEA_ADJ.setdefault(_a, set()).add(_b)
        SEA_ADJ.setdefault(_b, set()).add(_a)


def adjacent(region):
    """육로 인접 + 뱃길 인접(동선 큐 규칙 — RouteQueue._connected·validate_data.connected 와 동일)."""
    return sorted(set(REGIONS[region]["adjacent"]) | SEA_ADJ.get(region, set()))
REGION_NAME = {k: v["name"] for k, v in REGIONS.items()}


def norm(s):
    """이름 비교용: 괄호·공백·기호 제거."""
    s = re.sub(r"[\(（《\[].*?[\)）》\]]", "", str(s))
    return re.sub(r"[\s·,/]", "", s)


def node_index():
    idx = {}
    for n in NODES:
        idx.setdefault(norm(n["name"]), []).append(n)
    return idx


NODE_IDX = node_index()


def find_node(text, region=None):
    """자유 서술 위치 문자열에서 게임 노드를 찾는다(가장 긴 이름 일치 우선)."""
    t = norm(text)
    best = None
    for n in NODES:
        nm = norm(n["name"])
        if len(nm) >= 2 and nm in t and (region is None or n["region"] == region):
            if best is None or len(nm) > len(norm(best["name"])):
                best = n
    return best


# ---------------------------------------------------------------- 경제 공식 (00_overview.economy)
def quest_reward(tier, qtype):
    m = ECO["quest_type_mult"][qtype]
    rep = ECO["quest_rep"]["base"] * ECO["quest_rep"]["growth"] ** (tier - 1) * m["rep"]
    money = ECO["quest_money"]["base"] * ECO["quest_money"]["growth"] ** (tier - 1) * m["money"]
    return round(rep, -1), round(money, -1)


def enemy_reward(tier, boss=False):
    rep = ECO["enemy_rep"]["base"] * ECO["enemy_rep"]["growth"] ** (tier - 1)
    money = ECO["enemy_money"]["base"] * ECO["enemy_money"]["growth"] ** (tier - 1)
    if boss:
        rep *= ECO["boss_mult"]["rep"]
        money *= ECO["boss_mult"]["money"]
    return round(rep), round(money)


def price_formula(kind, tier):
    p = ECO["price"]
    return p["base"][kind] * p["growth"] ** (tier - 1)


SELL_SPREAD = TRADE["sell_spread_general"]
RICE_SELL = TRADE["rice_sell_spread"]
WAGE = ECO["wage_per_day"]


def rank_min_for_tier(t):
    return max(1, min(5, int(t)))


# ---------------------------------------------------------------- 전투 기준 (게임에 이미 튜닝된 적/동료에서 등급별 기준값)
def tier_ref_normal():
    out = {}
    for t in range(1, 5):
        es = [e for e in ENEMIES.values() if e["tier"] == t and not e.get("boss_tier")]
        if es:
            out[t] = {k: sum(e[k] for e in es) / len(es) for k in ("hp", "atk", "def", "speed")}
            out[t]["combat_scale"] = sum(e["combat_scale"] for e in es) / len(es)
    return out


def tier_ref_boss():
    out = {}
    for t in (4, 5):
        es = [e for e in ENEMIES.values() if e.get("boss_tier") == t]
        out[t] = {k: sum(e[k] for e in es) / len(es) for k in ("hp", "atk", "def", "speed")}
    return out


def companion_template(tier):
    """게임 동료의 등급별 평균 스탯(동료 통합 전투라 스탯은 주인공에 합산되지 않고, 스킬 위력 산식·표시에만 쓰인다)."""
    # 게임 동료 2·3등급 평균(110/16/10/85 · 150/23/16/88)을 기준으로 등급당 약 ×1.35 — 표시·도감용(전투 합산 없음)
    table = {1: (82, 12, 7, 84), 2: (110, 16, 10, 85), 3: (150, 23, 16, 88), 4: (200, 31, 22, 90), 5: (260, 40, 29, 92)}
    return dict(zip(("hp", "atk", "def", "speed"), table[max(1, min(5, int(tier)))]))
