"""생성기·시뮬레이터 공용 모듈: 한글 로마자 변환, 등급별 스탯 표, 가격·보상 자동 공식.

런타임(GDScript)은 이 표를 직접 읽지 않는다. 생성기가 계산 결과를 data/*.json 에 기록하고,
보상 공식(명성/엽전)은 00_overview.json economy 파라미터로 Balance.gd 와 여기서 동일하게 계산한다.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SRC = ROOT / "data_src"


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- 로마자 (국어의 로마자 표기법 간이판, 음운변동 생략)
_CHO = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
_JUNG = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i"]
_JONG = ["", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t", "ng", "t", "t", "k", "t", "p", "t"]


def romanize(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            cho, jung, jong = code // 588, (code % 588) // 28, code % 28
            out.append(_CHO[cho] + _JUNG[jung] + _JONG[jong])
        elif ch.isascii() and ch.isalnum():
            out.append(ch.lower())
    return "".join(out).upper()


# ---------------------------------------------------------------- 전투 스케일 (완전판 7.1: 주인공 HP 100 → 최대 250)
# 슬롯 × 등급 기준 스탯. 신발 spd 는 V_mount(px/s) 보너스, 장신구 res 는 속성 저항.
STAT_TABLE = {
    "weapon":    {1: {"atk": 4},  2: {"atk": 10}, 3: {"atk": 20}, 4: {"atk": 32}, 5: {"atk": 45}},
    "armor":     {1: {"def": 4, "hp": 0}, 2: {"def": 10, "hp": 10}, 3: {"def": 20, "hp": 20}, 4: {"def": 32, "hp": 35}, 5: {"def": 45, "hp": 60}},
    "shoes":     {1: {"spd": 10}, 2: {"spd": 15, "def": 1}, 3: {"spd": 20, "def": 3}, 4: {"spd": 25, "def": 5}, 5: {"spd": 30, "def": 8}},
    "accessory": {1: {"res": 0.03, "atk": 1}, 2: {"res": 0.06, "atk": 2}, 3: {"res": 0.10, "atk": 4}, 4: {"res": 0.14, "atk": 6}, 5: {"res": 0.18, "atk": 9}},
}
FAMILY_MULT = {  # 유·불·선 계열 특성
    "none": {"atk": 1.0, "def": 1.0, "res": 0.0},
    "yu":   {"atk": 1.0, "def": 1.0, "res": 0.0},
    "bul":  {"atk": 0.9, "def": 1.15, "res": 0.02},
    "seon": {"atk": 1.1, "def": 0.9, "res": 0.04},
}


def gear_stats(slot, tier, family="none", scale=1.0):
    f = FAMILY_MULT.get(family, FAMILY_MULT["none"])
    out = {}
    for k, v in STAT_TABLE[slot][tier].items():
        if k == "atk":
            v = v * f["atk"]
        elif k in ("def", "hp"):
            v = v * f["def"]
        elif k == "res":
            v = v + f["res"]
        v = v * scale
        out[k] = round(v, 3) if k == "res" else int(round(v))
    if "res" not in out and f["res"] > 0 and slot != "shoes":
        out["res"] = round(f["res"] * scale, 3)
    return out


# ---------------------------------------------------------------- 가격 자동 공식  price = base[cat] × growth^(tier-1)
_PRICE_CACHE = {}


def price(cat, tier):
    """00_overview.economy.price 단일 원천. 5냥 단위 반올림. (파일 수정 시각 기준 캐시 — 빌더가 수백 번 호출)"""
    f = DATA / "00_overview.json"
    key = f.stat().st_mtime_ns
    if _PRICE_CACHE.get("key") != key:
        _PRICE_CACHE.update(key=key, p=load("00_overview.json")["economy"]["price"])
    p = _PRICE_CACHE["p"]
    return int(round(p["base"][cat] * p["growth"] ** (tier - 1) / 5.0) * 5) or 5


# ---------------------------------------------------------------- 보상 공식 (Balance.gd 와 동일)
def overview():
    return load("00_overview.json")


def tier_curve(cfg, tier):
    return cfg["base"] * cfg["growth"] ** (tier - 1)


def heritage_reward(ov, tier, category, hidden, choice, rank=None, venue_mult=1.0):
    """choice: donate(명성) | sell(엽전). 무작위 편차(jitter) 제외한 기대값."""
    e = ov["economy"]
    key = "rep" if choice == "donate" else "money"
    base = tier_curve(e["heritage_" + key], tier)
    base *= e["category_mult"].get(category, {}).get(key, 1.0)
    if hidden:
        base *= e["hidden_mult"]
    if rank is not None and choice == "donate":
        base *= rank_gap_mult(e, tier, rank)
    return base * venue_mult


def rank_gap_mult(e, tier, rank):
    g = e["rank_gap"]
    gap = tier - rank
    if gap > 0:
        return 1.0 + g["above_bonus_per_tier"] * gap
    return max(g["floor"], 1.0 - g["below_penalty_per_tier"] * (-gap))


def quest_reward(ov, tier, qtype, key):
    e = ov["economy"]
    return tier_curve(e["quest_" + key], tier) * e["quest_type_mult"][qtype][key]


def enemy_reward(ov, tier, boss, key):
    e = ov["economy"]
    v = tier_curve(e["enemy_" + key], tier)
    return v * (e["boss_mult"][key] if boss else 1.0)


def parallel_map(fn, args_list):
    """결정적 병렬 실행: 각 작업이 자체 시드(random.Random)로 돌므로 결과는 순차 실행과 같다.
    fork 가 되는 OS(리눅스·맥)에서만 병렬, 작업 수 1 이하·SIM_JOBS=1 이면 순차. fn 은 모듈 최상위 함수."""
    import multiprocessing as mp
    import os
    n = int(os.environ.get("SIM_JOBS", os.cpu_count() or 1))
    if n <= 1 or len(args_list) < 2:
        return [fn(*a) for a in args_list]
    try:
        ctx = mp.get_context("fork")
    except ValueError:
        return [fn(*a) for a in args_list]
    with ctx.Pool(min(n, len(args_list))) as pool:
        return pool.starmap(fn, args_list)
